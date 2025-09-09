"""
Configuración del panel de administración para casos legales
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import date
from .models import Caso, DocumentoCaso, Alerta, MovimientoCaso


class DocumentoCasoInline(admin.TabularInline):
    """Inline para documentos en el admin de casos"""
    model = DocumentoCaso
    extra = 0
    fields = ('titulo', 'archivo', 'descripcion')
    readonly_fields = ('fecha_subida', 'usuario_subida')
    
    def save_model(self, request, obj, form, change):
        """Asignar usuario actual al subir documento"""
        if not obj.usuario_subida_id:
            obj.usuario_subida = request.user
        super().save_model(request, obj, form, change)


class AlertaInline(admin.TabularInline):
    """Inline para alertas en el admin de casos"""
    model = Alerta
    extra = 0
    fields = ('tipo', 'mensaje', 'fecha_alerta', 'enviar_email', 'enviada')
    readonly_fields = ('fecha_envio', 'usuario_creador')


class MovimientoCasoInline(admin.TabularInline):
    """Inline para movimientos en el admin de casos"""
    model = MovimientoCaso
    extra = 0
    fields = ('fecha_movimiento', 'descripcion', 'importante')
    readonly_fields = ('usuario',)
    
    def save_model(self, request, obj, form, change):
        """Asignar usuario actual al crear movimiento"""
        if not obj.usuario_id:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)


@admin.register(Caso)
class CasoAdmin(admin.ModelAdmin):
    """Admin principal para casos"""
    
    list_display = [
        'rol', 'tipo', 'recurrente', 'tribunal', 'estado', 
        'fecha_vencimiento', 'estado_vencimiento_display', 
        'urgente_display', 'usuario_responsable'
    ]
    
    list_filter = [
        'tipo', 'estado', 'tribunal', 'urgente', 
        'fecha_presentacion', 'fecha_vencimiento', 'usuario_responsable'
    ]
    
    search_fields = [
        'rol', 'recurrente', 'recurrido', 'materia', 'notas'
    ]
    
    date_hierarchy = 'fecha_vencimiento'
    
    fieldsets = (
        ('Información Básica', {
            'fields': (
                'tipo', 'rol', 'recurrente', 'recurrido', 
                'tribunal', 'materia', 'estado'
            )
        }),
        ('Fechas Importantes', {
            'fields': (
                'fecha_presentacion', 'fecha_vencimiento', 
                'fecha_notificacion'
            )
        }),
        ('Seguimiento', {
            'fields': (
                'usuario_responsable', 'notas', 'urgente'
            )
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion', 'urgente']
    
    inlines = [MovimientoCasoInline, AlertaInline, DocumentoCasoInline]
    
    list_per_page = 25
    
    ordering = ['-fecha_vencimiento', '-fecha_creacion']
    
    actions = ['marcar_como_cerrado', 'crear_alerta_vencimiento', 'marcar_urgente']
    
    def save_model(self, request, obj, form, change):
        """Asignar usuario responsable al crear caso"""
        if not change and not obj.usuario_responsable_id:
            obj.usuario_responsable = request.user
        super().save_model(request, obj, form, change)
    
    def estado_vencimiento_display(self, obj):
        """Muestra el estado del vencimiento con colores"""
        dias = obj.dias_hasta_vencimiento
        estado_info = obj.estado_vencimiento
        
        if dias is None:
            return format_html('<span class="text-muted">Sin fecha</span>')
        elif dias < 0:
            return format_html(
                '<span class="text-danger"><strong>Vencido ({} días)</strong></span>', 
                abs(dias)
            )
        elif dias == 0:
            return format_html('<span class="text-danger"><strong>¡HOY!</strong></span>')
        elif dias <= 3:
            return format_html(
                '<span class="text-danger"><strong>{} días</strong></span>', 
                dias
            )
        elif dias <= 7:
            return format_html(
                '<span class="text-warning"><strong>{} días</strong></span>', 
                dias
            )
        else:
            return format_html(
                '<span class="text-success">{} días</span>', 
                dias
            )
    
    estado_vencimiento_display.short_description = 'Días al vencimiento'
    estado_vencimiento_display.admin_order_field = 'fecha_vencimiento'
    
    def urgente_display(self, obj):
        """Muestra ícono si el caso es urgente"""
        if obj.urgente:
            return format_html(
                '<span style="color: red;">⚠️</span>'
            )
        return ''
    
    urgente_display.short_description = 'Urgente'
    urgente_display.admin_order_field = 'urgente'
    
    # Acciones personalizadas
    def marcar_como_cerrado(self, request, queryset):
        """Acción para cerrar casos seleccionados"""
        updated = queryset.update(estado='CERRADO')
        self.message_user(
            request, 
            f'{updated} casos marcados como cerrados.'
        )
    
    marcar_como_cerrado.short_description = "Marcar casos como cerrados"
    
    def crear_alerta_vencimiento(self, request, queryset):
        """Crear alertas automáticas para casos próximos a vencer"""
        alertas_creadas = 0
        
        for caso in queryset:
            if caso.dias_hasta_vencimiento and caso.dias_hasta_vencimiento <= 7:
                # Crear alerta si no existe una reciente
                alerta_existente = Alerta.objects.filter(
                    caso=caso,
                    tipo='VENCIMIENTO',
                    fecha_alerta__gte=timezone.now().date()
                ).exists()
                
                if not alerta_existente:
                    Alerta.objects.create(
                        caso=caso,
                        tipo='VENCIMIENTO',
                        mensaje=f'El caso {caso.rol} vence en {caso.dias_hasta_vencimiento} días.',
                        fecha_alerta=timezone.now() + timezone.timedelta(hours=1),
                        usuario_creador=request.user,
                        email_destinatario=caso.usuario_responsable.email
                    )
                    alertas_creadas += 1
        
        self.message_user(
            request,
            f'{alertas_creadas} alertas de vencimiento creadas.'
        )
    
    crear_alerta_vencimiento.short_description = "Crear alertas de vencimiento"
    
    def marcar_urgente(self, request, queryset):
        """Marcar casos como urgentes"""
        updated = queryset.update(urgente=True)
        self.message_user(
            request,
            f'{updated} casos marcados como urgentes.'
        )
    
    marcar_urgente.short_description = "Marcar como urgentes"


@admin.register(DocumentoCaso)
class DocumentoCasoAdmin(admin.ModelAdmin):
    """Admin para documentos de casos"""
    
    list_display = [
        'titulo', 'caso', 'archivo', 'tamaño_archivo', 
        'fecha_subida', 'usuario_subida'
    ]
    
    list_filter = [
        'fecha_subida', 'usuario_subida', 'caso__tipo'
    ]
    
    search_fields = [
        'titulo', 'descripcion', 'caso__rol', 'caso__recurrente'
    ]
    
    readonly_fields = [
        'fecha_subida', 'usuario_subida', 'tamaño_archivo'
    ]
    
    def save_model(self, request, obj, form, change):
        """Asignar usuario actual al subir documento"""
        if not change:
            obj.usuario_subida = request.user
        super().save_model(request, obj, form, change)


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    """Admin para alertas"""
    
    list_display = [
        'caso', 'tipo', 'fecha_alerta', 'enviada', 
        'leida', 'email_destinatario'
    ]
    
    list_filter = [
        'tipo', 'enviada', 'leida', 'enviar_email',
        'fecha_alerta', 'fecha_creacion'
    ]
    
    search_fields = [
        'mensaje', 'caso__rol', 'caso__recurrente', 'email_destinatario'
    ]
    
    readonly_fields = [
        'fecha_creacion', 'fecha_envio', 'usuario_creador'
    ]
    
    fieldsets = (
        ('Información de la Alerta', {
            'fields': (
                'caso', 'tipo', 'mensaje', 'fecha_alerta'
            )
        }),
        ('Configuración de Envío', {
            'fields': (
                'enviar_email', 'email_destinatario'
            )
        }),
        ('Estado', {
            'fields': (
                'enviada', 'fecha_envio', 'leida'
            )
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'usuario_creador'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['marcar_como_enviadas', 'reenviar_alertas']
    
    def save_model(self, request, obj, form, change):
        """Asignar usuario creador al crear alerta"""
        if not change:
            obj.usuario_creador = request.user
            # Asignar email por defecto del usuario responsable del caso
            if not obj.email_destinatario:
                obj.email_destinatario = obj.caso.usuario_responsable.email
        super().save_model(request, obj, form, change)
    
    def marcar_como_enviadas(self, request, queryset):
        """Marcar alertas como enviadas"""
        updated = queryset.update(
            enviada=True, 
            fecha_envio=timezone.now()
        )
        self.message_user(
            request,
            f'{updated} alertas marcadas como enviadas.'
        )
    
    marcar_como_enviadas.short_description = "Marcar como enviadas"
    
    def reenviar_alertas(self, request, queryset):
        """Reenviar alertas seleccionadas"""
        updated = queryset.update(enviada=False, fecha_envio=None)
        self.message_user(
            request,
            f'{updated} alertas programadas para reenvío.'
        )
    
    reenviar_alertas.short_description = "Programar para reenvío"


@admin.register(MovimientoCaso)
class MovimientoCasoAdmin(admin.ModelAdmin):
    """Admin para movimientos de casos"""
    
    list_display = [
        'caso', 'fecha_movimiento', 'descripcion_corta', 
        'importante', 'usuario'
    ]
    
    list_filter = [
        'importante', 'fecha_movimiento', 'usuario', 'caso__tipo'
    ]
    
    search_fields = [
        'descripcion', 'caso__rol', 'caso__recurrente'
    ]
    
    readonly_fields = ['fecha_movimiento']
    
    def descripcion_corta(self, obj):
        """Muestra descripción truncada"""
        if len(obj.descripcion) > 50:
            return obj.descripcion[:50] + '...'
        return obj.descripcion
    
    descripcion_corta.short_description = 'Descripción'
    
    def save_model(self, request, obj, form, change):
        """Asignar usuario actual al crear movimiento"""
        if not change:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)


# Personalizar el título del admin
admin.site.site_header = 'Gestor de Casos Legales'
admin.site.site_title = 'Gestor de Casos'
admin.site.index_title = 'Panel de Administración'

# Personalizar la página de inicio del admin
def admin_view_casos_urgentes(request):
    """Vista personalizada para mostrar casos urgentes en admin"""
    from django.template.response import TemplateResponse
    from datetime import timedelta
    
    casos_urgentes = Caso.objects.filter(
        estado='EN_TRAMITACION',
        fecha_vencimiento__lte=date.today() + timedelta(days=7)
    ).order_by('fecha_vencimiento')[:10]
    
    alertas_pendientes = Alerta.objects.filter(
        enviada=False,
        fecha_alerta__lte=timezone.now()
    ).count()
    
    context = {
        'title': 'Resumen de Casos',
        'casos_urgentes': casos_urgentes,
        'alertas_pendientes': alertas_pendientes,
    }
    
    return TemplateResponse(request, 'admin/casos_dashboard.html', context)