"""
Modelos para el sistema de gestión de casos legales
"""
import os
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from datetime import date, timedelta


def upload_documento_path(instance, filename):
    """Genera la ruta para subir documentos"""
    return f'documentos/caso_{instance.caso.id}/{filename}'


class Caso(models.Model):
    """Modelo principal para casos legales"""
    
    TIPO_CASO_CHOICES = [
        ('AMPARO', 'Recurso de Amparo'),
        ('PROTECCION', 'Recurso de Protección'),
        ('CDE', 'CDE (Contencioso Administrativo)'),
    ]
    
    ESTADO_CHOICES = [
        ('EN_TRAMITACION', 'En Tramitación'),
        ('CERRADO', 'Cerrado'),
        ('SUSPENDIDO', 'Suspendido'),
        ('EN_APELACION', 'En Apelación'),
    ]
    
    TRIBUNAL_CHOICES = [
        ('CORTE_APELACIONES_SANTIAGO', 'Corte de Apelaciones de Santiago'),
        ('CORTE_APELACIONES_VALPARAISO', 'Corte de Apelaciones de Valparaíso'),
        ('CORTE_APELACIONES_CONCEPCION', 'Corte de Apelaciones de Concepción'),
        ('CORTE_SUPREMA', 'Corte Suprema'),
        ('TRIBUNAL_CONSTITUCIONAL', 'Tribunal Constitucional'),
        ('CONTRALORIA', 'Contraloría General de la República'),
        ('OTRO', 'Otro Tribunal'),
    ]
    
    # Campos principales
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CASO_CHOICES,
        verbose_name='Tipo de Caso'
    )
    rol = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Rol del Caso',
        help_text='Ejemplo: C-123-2024'
    )
    recurrente = models.CharField(
        max_length=200,
        verbose_name='Recurrente/Demandante'
    )
    recurrido = models.CharField(
        max_length=200,
        verbose_name='Recurrido/Demandado',
        blank=True,
        null=True
    )
    tribunal = models.CharField(
        max_length=50,
        choices=TRIBUNAL_CHOICES,
        verbose_name='Tribunal'
    )
    
    # Fechas importantes
    fecha_presentacion = models.DateField(
        verbose_name='Fecha de Presentación'
    )
    fecha_vencimiento = models.DateField(
        verbose_name='Fecha de Vencimiento/Plazo',
        help_text='Fecha límite para próximas acciones'
    )
    fecha_notificacion = models.DateField(
        verbose_name='Fecha de Notificación',
        blank=True,
        null=True
    )
    
    # Estado y seguimiento
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='EN_TRAMITACION',
        verbose_name='Estado del Caso'
    )
    
    # Información adicional
    materia = models.CharField(
        max_length=300,
        verbose_name='Materia del Caso',
        help_text='Breve descripción de la materia'
    )
    notas = models.TextField(
        blank=True,
        null=True,
        verbose_name='Notas y Observaciones'
    )
    
    # Metadatos
    usuario_responsable = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Usuario Responsable'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    # Campos calculados
    urgente = models.BooleanField(
        default=False,
        verbose_name='Caso Urgente',
        help_text='Se marca automáticamente si el vencimiento es próximo'
    )
    
    class Meta:
        verbose_name = 'Caso'
        verbose_name_plural = 'Casos'
        ordering = ['-fecha_vencimiento', '-fecha_creacion']
        indexes = [
            models.Index(fields=['estado', 'fecha_vencimiento']),
            models.Index(fields=['tipo', 'tribunal']),
            models.Index(fields=['usuario_responsable', 'estado']),
        ]
    
    def __str__(self):
        return f"{self.get_tipo_display()} - {self.rol} - {self.recurrente}"
    
    def save(self, *args, **kwargs):
        """Sobrescribir save para marcar casos urgentes automáticamente"""
        # Marcar como urgente si faltan 7 días o menos
        if self.fecha_vencimiento:
            days_until_deadline = (self.fecha_vencimiento - date.today()).days
            self.urgente = days_until_deadline <= 7
        super().save(*args, **kwargs)
    
    @property
    def dias_hasta_vencimiento(self):
        """Calcula días hasta el vencimiento"""
        if self.fecha_vencimiento:
            return (self.fecha_vencimiento - date.today()).days
        return None
    
    @property
    def estado_vencimiento(self):
        """Retorna el estado del vencimiento con colores CSS"""
        dias = self.dias_hasta_vencimiento
        if dias is None:
            return {'estado': 'sin-fecha', 'clase': 'text-muted'}
        elif dias < 0:
            return {'estado': 'vencido', 'clase': 'text-danger'}
        elif dias <= 3:
            return {'estado': 'critico', 'clase': 'text-danger'}
        elif dias <= 7:
            return {'estado': 'urgente', 'clase': 'text-warning'}
        else:
            return {'estado': 'normal', 'clase': 'text-success'}
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('Casos:detalle', kwargs={'pk': self.pk})


class DocumentoCaso(models.Model):
    """Modelo para documentos adjuntos a casos"""
    
    caso = models.ForeignKey(
        Caso,
        on_delete=models.CASCADE,
        related_name='documentos',
        verbose_name='Caso'
    )
    titulo = models.CharField(
        max_length=200,
        verbose_name='Título del Documento'
    )
    archivo = models.FileField(
        upload_to=upload_documento_path,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'jpg', 'png'])],
        verbose_name='Archivo'
    )
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name='Descripción'
    )
    fecha_subida = models.DateTimeField(auto_now_add=True)
    usuario_subida = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Usuario que subió'
    )
    
    class Meta:
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'
        ordering = ['-fecha_subida']
    
    def __str__(self):
        return f"{self.titulo} - {self.caso.rol}"
    
    @property
    def tamaño_archivo(self):
        """Retorna el tamaño del archivo en formato legible"""
        if self.archivo:
            size = self.archivo.size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
        return "0 B"
    
    def delete(self, *args, **kwargs):
        """Eliminar el archivo físico al borrar el registro"""
        if self.archivo:
            if os.path.isfile(self.archivo.path):
                os.remove(self.archivo.path)
        super().delete(*args, **kwargs)


class Alerta(models.Model):
    """Modelo para alertas y recordatorios de casos"""
    
    TIPO_ALERTA_CHOICES = [
        ('VENCIMIENTO', 'Vencimiento de Plazo'),
        ('AUDIENCIA', 'Audiencia Programada'),
        ('SEGUIMIENTO', 'Seguimiento General'),
        ('NOTIFICACION', 'Notificación Recibida'),
    ]
    
    caso = models.ForeignKey(
        Caso,
        on_delete=models.CASCADE,
        related_name='alertas',
        verbose_name='Caso'
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_ALERTA_CHOICES,
        default='VENCIMIENTO',
        verbose_name='Tipo de Alerta'
    )
    mensaje = models.TextField(verbose_name='Mensaje de Alerta')
    fecha_alerta = models.DateTimeField(
        verbose_name='Fecha y Hora de Alerta'
    )
    
    # Estado de la alerta
    enviada = models.BooleanField(
        default=False,
        verbose_name='Alerta Enviada'
    )
    fecha_envio = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Fecha de Envío'
    )
    leida = models.BooleanField(
        default=False,
        verbose_name='Alerta Leída'
    )
    
    # Configuración de envío
    enviar_email = models.BooleanField(
        default=True,
        verbose_name='Enviar por Email'
    )
    email_destinatario = models.EmailField(
        blank=True,
        null=True,
        verbose_name='Email Destinatario'
    )
    
    # Metadatos
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    usuario_creador = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Usuario Creador'
    )
    
    class Meta:
        verbose_name = 'Alerta'
        verbose_name_plural = 'Alertas'
        ordering = ['-fecha_alerta']
        indexes = [
            models.Index(fields=['enviada', 'fecha_alerta']),
            models.Index(fields=['caso', 'tipo']),
        ]
    
    def __str__(self):
        return f"Alerta {self.get_tipo_display()} - {self.caso.rol}"
    
    def marcar_como_enviada(self):
        """Marca la alerta como enviada"""
        self.enviada = True
        self.fecha_envio = timezone.now()
        self.save(update_fields=['enviada', 'fecha_envio'])
    
    @property
    def vencida(self):
        """Verifica si la alerta ya venció"""
        return timezone.now() > self.fecha_alerta


class MovimientoCaso(models.Model):
    """Modelo para registrar movimientos/actuaciones en casos"""
    
    caso = models.ForeignKey(
        Caso,
        on_delete=models.CASCADE,
        related_name='movimientos',
        verbose_name='Caso'
    )
    fecha_movimiento = models.DateTimeField(
        default=timezone.now,
        verbose_name='Fecha del Movimiento'
    )
    descripcion = models.TextField(
        verbose_name='Descripción del Movimiento'
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Usuario'
    )
    importante = models.BooleanField(
        default=False,
        verbose_name='Movimiento Importante'
    )
    
    class Meta:
        verbose_name = 'Movimiento'
        verbose_name_plural = 'Movimientos'
        ordering = ['-fecha_movimiento']
    
    def __str__(self):
        return f"{self.caso.rol} - {self.fecha_movimiento.strftime('%d/%m/%Y')}"
