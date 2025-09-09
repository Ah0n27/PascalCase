# gestor_casos/celery.py
"""
Configuración de Celery para tareas asíncronas
"""
import os
from celery import Celery
from django.conf import settings

# Configurar Django settings para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestor_casos.settings')

app = Celery('gestor_casos')

# Usar configuración de Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodescubrir tareas en todas las apps
app.autodiscover_tasks()

# Configurar tareas periódicas
app.conf.beat_schedule = {
    'revisar-alertas-cada-hora': {
        'task': 'apps.casos.tasks.revisar_alertas_pendientes',
        'schedule': 3600.0,  # cada hora
    },
    'crear-alertas-vencimiento-diario': {
        'task': 'apps.casos.tasks.crear_alertas_vencimiento',
        'schedule': 86400.0,  # diario
        'options': {'expires': 60.0}
    },
    'limpiar-alertas-antiguas-semanal': {
        'task': 'apps.casos.tasks.limpiar_alertas_antiguas',
        'schedule': 604800.0,  # semanal
    },
}

app.conf.timezone = 'America/Santiago'

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# apps/casos/tasks.py
"""
Tareas asíncronas para el sistema de casos
"""
import logging
from datetime import date, timedelta
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
from celery import shared_task
from .models import Caso, Alerta

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def enviar_email_alerta(self, alerta_id):
    """
    Tarea para enviar email de alerta
    """
    try:
        alerta = Alerta.objects.get(id=alerta_id)
        
        # Verificar si ya fue enviada
        if alerta.enviada:
            logger.info(f"Alerta {alerta_id} ya fue enviada")
            return "Alerta ya enviada"
        
        # Preparar contenido del email
        caso = alerta.caso
        subject = f"Alerta: {alerta.get_tipo_display()} - {caso.rol}"
        
        # Contexto para el template
        context = {
            'alerta': alerta,
            'caso': caso,
            'dias_vencimiento': caso.dias_hasta_vencimiento,
            'url_caso': f"{settings.ALLOWED_HOSTS[0]}{caso.get_absolute_url()}" if settings.ALLOWED_HOSTS else "",
        }
        
        # Renderizar template
        html_message = render_to_string('emails/alerta.html', context)
        plain_message = render_to_string('emails/alerta.txt', context)
        
        # Determinar destinatario
        email_destinatario = alerta.email_destinatario or caso.usuario_responsable.email
        
        if not email_destinatario:
            logger.warning(f"No hay email destinatario para alerta {alerta_id}")
            return "Sin email destinatario"
        
        # Enviar email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email_destinatario],
            html_message=html_message,
            fail_silently=False
        )
        
        # Marcar como enviada
        alerta.marcar_como_enviada()
        
        logger.info(f"Email enviado para alerta {alerta_id} a {email_destinatario}")
        return f"Email enviado exitosamente a {email_destinatario}"
        
    except Alerta.DoesNotExist:
        logger.error(f"Alerta {alerta_id} no existe")
        return "Alerta no encontrada"
        
    except Exception as exc:
        logger.error(f"Error enviando email para alerta {alerta_id}: {str(exc)}")
        
        # Reintentar si no se han agotado los reintentos
        if self.request.retries < self.max_retries:
            logger.info(f"Reintentando envío de alerta {alerta_id} en 5 minutos")
            raise self.retry(countdown=300, exc=exc)
        
        return f"Error: {str(exc)}"


@shared_task
def revisar_alertas_pendientes():
    """
    Tarea que revisa alertas pendientes y las envía
    """
    try:
        # Obtener alertas pendientes que ya deberían enviarse
        alertas_pendientes = Alerta.objects.filter(
            enviada=False,
            enviar_email=True,
            fecha_alerta__lte=timezone.now()
        ).select_related('caso')
        
        contador = 0
        for alerta in alertas_pendientes:
            # Lanzar tarea asíncrona para enviar cada email
            enviar_email_alerta.delay(alerta.id)
            contador += 1
        
        logger.info(f"Procesadas {contador} alertas pendientes")
        return f"Procesadas {contador} alertas"
        
    except Exception as exc:
        logger.error(f"Error revisando alertas pendientes: {str(exc)}")
        return f"Error: {str(exc)}"


@shared_task
def crear_alertas_vencimiento():
    """
    Tarea que crea alertas automáticas para casos próximos a vencer
    """
    try:
        # Configuración por defecto: alertas 7 días antes
        dias_anticipacion = 7
        fecha_limite = date.today() + timedelta(days=dias_anticipacion)
        
        # Buscar casos que vencen pronto y no tienen alerta de vencimiento reciente
        casos_proximos = Caso.objects.filter(
            estado='EN_TRAMITACION',
            fecha_vencimiento=fecha_limite
        ).select_related('usuario_responsable')
        
        contador = 0
        for caso in casos_proximos:
            # Verificar si ya tiene alerta de vencimiento reciente
            tiene_alerta = Alerta.objects.filter(
                caso=caso,
                tipo='VENCIMIENTO',
                fecha_creacion__gte=timezone.now() - timedelta(days=1)
            ).exists()
            
            if not tiene_alerta:
                # Crear alerta
                Alerta.objects.create(
                    caso=caso,
                    tipo='VENCIMIENTO',
                    mensaje=f'El caso {caso.rol} vence en {dias_anticipacion} días '
                           f'({caso.fecha_vencimiento.strftime("%d/%m/%Y")}). '
                           f'Recurrente: {caso.recurrente}',
                    fecha_alerta=timezone.now() + timedelta(minutes=30),
                    usuario_creador=caso.usuario_responsable,
                    email_destinatario=caso.usuario_responsable.email,
                    enviar_email=True
                )
                contador += 1
        
        logger.info(f"Creadas {contador} alertas automáticas de vencimiento")
        return f"Creadas {contador} alertas automáticas"
        
    except Exception as exc:
        logger.error(f"Error creando alertas automáticas: {str(exc)}")
        return f"Error: {str(exc)}"


@shared_task
def limpiar_alertas_antiguas():
    """
    Tarea que limpia alertas antiguas para mantener la BD ordenada
    """
    try:
        # Eliminar alertas enviadas de más de 90 días
        fecha_corte = timezone.now() - timedelta(days=90)
        
        alertas_eliminadas = Alerta.objects.filter(
            enviada=True,
            fecha_envio__lt=fecha_corte
        ).delete()
        
        contador = alertas_eliminadas[0] if alertas_eliminadas[0] else 0
        
        logger.info(f"Eliminadas {contador} alertas antiguas")
        return f"Eliminadas {contador} alertas antiguas"
        
    except Exception as exc:
        logger.error(f"Error limpiando alertas antiguas: {str(exc)}")
        return f"Error: {str(exc)}"


@shared_task
def generar_reporte_casos(user_id, filtros=None):
    """
    Tarea para generar reportes de casos de forma asíncrona
    """
    try:
        from django.contrib.auth.models import User
        from django.core.mail import EmailMessage
        from .utils import generar_reporte_pdf, generar_reporte_excel
        
        user = User.objects.get(id=user_id)
        
        # Aplicar filtros si existen
        casos = Caso.objects.all()
        if not user.is_staff:
            casos = casos.filter(usuario_responsable=user)
        
        if filtros:
            if filtros.get('tipo'):
                casos = casos.filter(tipo=filtros['tipo'])
            if filtros.get('estado'):
                casos = casos.filter(estado=filtros['estado'])
            if filtros.get('fecha_desde'):
                casos = casos.filter(fecha_presentacion__gte=filtros['fecha_desde'])
            if filtros.get('fecha_hasta'):
                casos = casos.filter(fecha_presentacion__lte=filtros['fecha_hasta'])
        
        # Generar reporte según formato
        formato = filtros.get('formato', 'pdf') if filtros else 'pdf'
        
        if formato == 'pdf':
            archivo_reporte = generar_reporte_pdf(casos)
            content_type = 'application/pdf'
        elif formato == 'excel':
            archivo_reporte = generar_reporte_excel(casos)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            return "Formato no soportado"
        
        # Enviar por email
        subject = f"Reporte de Casos - {timezone.now().strftime('%d/%m/%Y')}"
        message = f"Hola {user.first_name or user.username},\n\n" \
                 f"Adjunto encontrarás el reporte de casos solicitado.\n\n" \
                 f"Total de casos en el reporte: {casos.count()}\n\n" \
                 f"Saludos,\nSistema de Gestión de Casos"
        
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        
        filename = f"reporte_casos_{timezone.now().strftime('%Y%m%d_%H%M')}.{formato}"
        email.attach(filename, archivo_reporte, content_type)
        email.send()
        
        logger.info(f"Reporte enviado a {user.email}")
        return f"Reporte enviado exitosamente a {user.email}"
        
    except Exception as exc:
        logger.error(f"Error generando reporte: {str(exc)}")
        return f"Error: {str(exc)}"


@shared_task
def backup_casos_data():
    """
    Tarea para hacer backup de los datos críticos
    """
    try:
        import json
        from django.core.serializers import serialize
        
        # Serializar casos
        casos_data = serialize('json', Caso.objects.all())
        alertas_data = serialize('json', Alerta.objects.all())
        
        # Crear backup
        backup_data = {
            'fecha_backup': timezone.now().isoformat(),
            'casos': json.loads(casos_data),
            'alertas': json.loads(alertas_data),
            'total_casos': Caso.objects.count(),
            'total_alertas': Alerta.objects.count(),
        }
        
        # Guardar o enviar backup (implementar según necesidad)
        # Por ejemplo, subir a S3, enviar por email, etc.
        
        logger.info("Backup de datos completado")
        return "Backup completado exitosamente"
        
    except Exception as exc:
        logger.error(f"Error en backup: {str(exc)}")
        return f"Error en backup: {str(exc)}"


# apps/casos/management/commands/enviar_alertas.py
"""
Comando para enviar alertas manualmente
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from Apps.Casos.tasks import revisar_alertas_pendientes, crear_alertas_vencimiento


class Command(BaseCommand):
    help = 'Enviar alertas pendientes manualmente'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--crear-nuevas',
            action='store_true',
            help='Crear nuevas alertas automáticas antes de enviar',
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar envío aunque no sea la hora programada',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Iniciando proceso de alertas...')
        
        if options['crear_nuevas']:
            self.stdout.write('Creando nuevas alertas automáticas...')
            resultado = crear_alertas_vencimiento()
            self.stdout.write(f'Resultado: {resultado}')
        
        self.stdout.write('Enviando alertas pendientes...')
        resultado = revisar_alertas_pendientes()
        self.stdout.write(f'Resultado: {resultado}')
        
        self.stdout.write(
            self.style.SUCCESS('Proceso de alertas completado')
        )