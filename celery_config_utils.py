# gestor_casos/__init__.py
"""
Configuración inicial del proyecto
"""
from .celery import app as celery_app

__all__ = ('celery_app',)

# apps/__init__.py
# Archivo vacío para hacer apps un paquete Python

# apps/casos/__init__.py
default_app_config = 'apps.casos.apps.CasosConfig'

# apps/casos/apps.py
"""
Configuración de la app casos
"""
from django.apps import AppConfig


class CasosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.casos'
    verbose_name = 'Gestión de Casos'
    
    def ready(self):
        """Importar signals cuando la app esté lista"""
        import apps.casos.signals


# apps/casos/signals.py
"""
Señales para automatizar acciones en casos
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import Caso, Alerta, MovimientoCaso


@receiver(pre_save, sender=Caso)
def marcar_urgente_automatico(sender, instance, **kwargs):
    """Marcar casos como urgentes automáticamente"""
    if instance.fecha_vencimiento:
        days_until = (instance.fecha_vencimiento - timezone.now().date()).days
        instance.urgente = days_until <= 7


@receiver(post_save, sender=Caso)
def crear_movimiento_inicial(sender, instance, created, **kwargs):
    """Crear movimiento inicial cuando se crea un caso"""
    if created:
        MovimientoCaso.objects.create(
            caso=instance,
            descripcion=f"Caso creado: {instance.get_tipo_display()} - {instance.materia[:100]}",
            usuario=instance.usuario_responsable,
            importante=True
        )


@receiver(post_save, sender=Caso)
def crear_alerta_automatica(sender, instance, created, **kwargs):
    """Crear alerta automática para casos próximos a vencer"""
    if not created:  # Solo para casos actualizados
        return
    
    if instance.fecha_vencimiento and instance.estado == 'EN_TRAMITACION':
        days_until = (instance.fecha_vencimiento - timezone.now().date()).days
        
        if days_until <= 7:  # Crear alerta si vence en 7 días o menos
            Alerta.objects.create(
                caso=instance,
                tipo='VENCIMIENTO',
                mensaje=f'El caso {instance.rol} vence en {days_until} días. '
                       f'Fecha de vencimiento: {instance.fecha_vencimiento.strftime("%d/%m/%Y")}',
                fecha_alerta=timezone.now() + timedelta(hours=1),
                usuario_creador=instance.usuario_responsable,
                email_destinatario=instance.usuario_responsable.email
            )


# apps/core/utils.py
"""
Utilidades generales del sistema
"""
import os
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from io import BytesIO
import xlsxwriter


def generar_reporte_pdf(casos):
    """
    Genera un reporte PDF de casos
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Título
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#2E86AB'),
        alignment=1  # Center
    )
    story.append(Paragraph("Reporte de Casos Legales", title_style))
    story.append(Spacer(1, 20))
    
    # Información general
    info_data = [
        ['Total de Casos:', str(casos.count())],
        ['Fecha de Generación:', timezone.now().strftime('%d/%m/%Y %H:%M')],
        ['Sistema:', 'Gestor de Casos Legales']
    ]
    
    info_table = Table(info_data, colWidths=[120, 200])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8F9FA')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DEE2E6'))
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 30))
    
    # Tabla de casos
    if casos.exists():
        # Encabezados
        data = [['Rol', 'Tipo', 'Recurrente', 'Estado', 'Vencimiento', 'Días']]
        
        for caso in casos:
            dias = caso.dias_hasta_vencimiento if caso.dias_hasta_vencimiento is not None else '--'
            data.append([
                caso.rol,
                caso.get_tipo_display(),
                caso.recurrente[:30] + ('...' if len(caso.recurrente) > 30 else ''),
                caso.get_estado_display(),
                caso.fecha_vencimiento.strftime('%d/%m/%Y'),
                str(dias)
            ])
        
        table = Table(data, colWidths=[80, 80, 140, 80, 80, 50])
        table.setStyle(TableStyle([
            # Encabezado
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E86AB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            
            # Contenido
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DEE2E6')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generar_reporte_excel(casos):
    """
    Genera un reporte Excel de casos
    """
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
    worksheet = workbook.add_worksheet('Casos')
    
    # Formatos
    header_format = workbook.add_format({
        'bold': True,
        'font_color': 'white',
        'bg_color': '#2E86AB',
        'border': 1,
        'align': 'center',
        'valign': 'vcenter'
    })
    
    cell_format = workbook.add_format({
        'border': 1,
        'align': 'left',
        'valign': 'vcenter'
    })
    
    date_format = workbook.add_format({
        'border': 1,
        'align': 'center',
        'num_format': 'dd/mm/yyyy'
    })
    
    # Encabezados
    headers = [
        'Rol', 'Tipo', 'Recurrente', 'Recurrido', 'Tribunal', 
        'Fecha Presentación', 'Fecha Vencimiento', 'Estado', 
        'Materia', 'Usuario Responsable', 'Días al Vencimiento'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)
    
    # Datos
    for row, caso in enumerate(casos, start=1):
        worksheet.write(row, 0, caso.rol, cell_format)
        worksheet.write(row, 1, caso.get_tipo_display(), cell_format)
        worksheet.write(row, 2, caso.recurrente, cell_format)
        worksheet.write(row, 3, caso.recurrido or '', cell_format)
        worksheet.write(row, 4, caso.get_tribunal_display(), cell_format)
        worksheet.write(row, 5, caso.fecha_presentacion, date_format)
        worksheet.write(row, 6, caso.fecha_vencimiento, date_format)
        worksheet.write(row, 7, caso.get_estado_display(), cell_format)
        worksheet.write(row, 8, caso.materia, cell_format)
        worksheet.write(row, 9, caso.usuario_responsable.get_full_name() or caso.usuario_responsable.username, cell_format)
        worksheet.write(row, 10, caso.dias_hasta_vencimiento if caso.dias_hasta_vencimiento is not None else '', cell_format)
    
    # Ajustar ancho de columnas
    worksheet.set_column('A:A', 15)  # Rol
    worksheet.set_column('B:B', 20)  # Tipo
    worksheet.set_column('C:C', 30)  # Recurrente
    worksheet.set_column('D:D', 30)  # Recurrido
    worksheet.set_column('E:E', 35)  # Tribunal
    worksheet.set_column('F:G', 18)  # Fechas
    worksheet.set_column('H:H', 15)  # Estado
    worksheet.set_column('I:I', 50)  # Materia
    worksheet.set_column('J:J', 20)  # Usuario
    worksheet.set_column('K:K', 18)  # Días
    
    workbook.close()
    buffer.seek(0)
    return buffer.getvalue()


def enviar_email_personalizado(destinatario, asunto, mensaje, archivo_adjunto=None):
    """
    Envía un email personalizado
    """
    try:
        email = EmailMessage(
            subject=asunto,
            body=mensaje,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinatario]
        )
        
        if archivo_adjunto:
            email.attach_file(archivo_adjunto)
        
        email.send()
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False


def validar_rol_caso(rol):
    """
    Valida el formato del rol de un caso
    Formato esperado: LETRA-NÚMERO-AÑO (ej: A-123-2024)
    """
    import re
    patron = r'^[A-Z]-\d{1,4}-\d{4}$'
    return bool(re.match(patron, rol.upper()))


def calcular_dias_habiles(fecha_inicio, fecha_fin):
    """
    Calcula días hábiles entre dos fechas (excluyendo fines de semana)
    """
    from datetime import timedelta
    
    dias = 0
    fecha_actual = fecha_inicio
    
    while fecha_actual <= fecha_fin:
        # 0=Lunes, 6=Domingo
        if fecha_actual.weekday() < 5:  # Lunes a Viernes
            dias += 1
        fecha_actual += timedelta(days=1)
    
    return dias


def formatear_numero_chile(numero):
    """
    Formatea números con separador de miles chileno
    """
    return f"{numero:,.0f}".replace(',', '.')


def limpiar_archivos_temporales():
    """
    Limpia archivos temporales antiguos
    """
    import os
    import time
    from django.conf import settings
    
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
    if not os.path.exists(temp_dir):
        return
    
    # Eliminar archivos de más de 24 horas
    now = time.time()
    for filename in os.listdir(temp_dir):
        filepath = os.path.join(temp_dir, filename)
        if os.path.isfile(filepath):
            # Si el archivo tiene más de 24 horas
            if now - os.path.getctime(filepath) > 24 * 3600:
                try:
                    os.remove(filepath)
                    print(f"Archivo temporal eliminado: {filename}")
                except OSError:
                    pass


# apps/core/email.py
"""
Utilidades para manejo de emails
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings


class EmailManager:
    """Clase para gestionar envío de emails del sistema"""
    
    @staticmethod
    def enviar_alerta_caso(alerta):
        """Envía email de alerta para un caso"""
        try:
            caso = alerta.caso
            
            context = {
                'alerta': alerta,
                'caso': caso,
                'dias_vencimiento': caso.dias_hasta_vencimiento,
                'url_caso': f"https://{settings.ALLOWED_HOSTS[0]}{caso.get_absolute_url()}" if settings.ALLOWED_HOSTS else "",
                'sistema_nombre': 'Gestor de Casos Legales'
            }
            
            # Renderizar templates
            html_content = render_to_string('emails/alerta.html', context)
            text_content = render_to_string('emails/alerta.txt', context)
            
            # Preparar email
            subject = f"🔔 Alerta: {alerta.get_tipo_display()} - {caso.rol}"
            from_email = settings.DEFAULT_FROM_EMAIL
            to_email = alerta.email_destinatario or caso.usuario_responsable.email
            
            # Crear y enviar
            msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            
            return True
            
        except Exception as e:
            print(f"Error enviando email de alerta: {e}")
            return False
    
    @staticmethod
    def enviar_reporte_casos(user, casos, formato='pdf'):
        """Envía reporte de casos por email"""
        try:
            from .utils import generar_reporte_pdf, generar_reporte_excel
            
            # Generar reporte
            if formato == 'pdf':
                archivo_reporte = generar_reporte_pdf(casos)
                content_type = 'application/pdf'
                extension = 'pdf'
            else:
                archivo_reporte = generar_reporte_excel(casos)
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                extension = 'xlsx'
            
            # Preparar email
            subject = f"Reporte de Casos - {timezone.now().strftime('%d/%m/%Y')}"
            
            context = {
                'user': user,
                'total_casos': casos.count(),
                'fecha_reporte': timezone.now().strftime('%d/%m/%Y %H:%M')
            }
            
            html_content = render_to_string('emails/reporte.html', context)
            text_content = render_to_string('emails/reporte.txt', context)
            
            # Crear mensaje
            msg = EmailMultiAlternatives(
                subject, 
                text_content, 
                settings.DEFAULT_FROM_EMAIL, 
                [user.email]
            )
            msg.attach_alternative(html_content, "text/html")
            
            # Adjuntar reporte
            filename = f"reporte_casos_{timezone.now().strftime('%Y%m%d_%H%M')}.{extension}"
            msg.attach(filename, archivo_reporte, content_type)
            
            msg.send()
            return True
            
        except Exception as e:
            print(f"Error enviando reporte: {e}")
            return False


# utils/decorators.py
"""
Decoradores personalizados para el sistema
"""
from functools import wraps
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from Apps.Casos.models import Caso


def staff_required(function):
    """Decorador que requiere que el usuario sea staff"""
    def check_staff(user):
        return user.is_staff
    
    actual_decorator = user_passes_test(check_staff)
    return actual_decorator(function)


def caso_owner_required(view_func):
    """Decorador que verifica que el usuario sea propietario del caso"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Obtener ID del caso de los kwargs
        caso_id = kwargs.get('pk') or kwargs.get('caso_pk')
        if caso_id:
            caso = get_object_or_404(Caso, pk=caso_id)
            if caso.usuario_responsable != request.user:
                raise PermissionDenied("No tienes permisos para acceder a este caso")
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def ajax_required(view_func):
    """Decorador que requiere que la petición sea AJAX"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            raise PermissionDenied("Esta vista requiere una petición AJAX")
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view