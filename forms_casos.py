"""
Formularios para la aplicación de casos
"""
from django import forms
from django.core.exceptions import ValidationError
from datetime import date
from .models import Caso, DocumentoCaso, Alerta, MovimientoCaso


class CasoForm(forms.ModelForm):
    """Formulario para crear/editar casos"""
    
    class Meta:
        model = Caso
        fields = [
            'tipo', 'rol', 'recurrente', 'recurrido', 'tribunal',
            'fecha_presentacion', 'fecha_vencimiento', 'fecha_notificacion',
            'estado', 'materia', 'notas'
        ]
        widgets = {
            'fecha_presentacion': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'fecha_vencimiento': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'fecha_notificacion': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'rol': forms.TextInput(attrs={'class': 'form-control'}),
            'recurrente': forms.TextInput(attrs={'class': 'form-control'}),
            'recurrido': forms.TextInput(attrs={'class': 'form-control'}),
            'tribunal': forms.Select(attrs={'class': 'form-control'}),
            'estado': forms.Select(attrs={'class': 'form-control'}),
            'materia': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Hacer algunos campos requeridos
        self.fields['rol'].required = True
        self.fields['recurrente'].required = True
        self.fields['fecha_presentacion'].required = True
        self.fields['fecha_vencimiento'].required = True
        self.fields['materia'].required = True
        
        # Agregar placeholders
        self.fields['rol'].widget.attrs.update({
            'placeholder': 'Ej: C-123-2024'
        })
        self.fields['recurrente'].widget.attrs.update({
            'placeholder': 'Nombre del recurrente/demandante'
        })
        self.fields['recurrido'].widget.attrs.update({
            'placeholder': 'Nombre del recurrido/demandado (opcional)'
        })
        self.fields['materia'].widget.attrs.update({
            'placeholder': 'Breve descripción de la materia del caso'
        })
        self.fields['notas'].widget.attrs.update({
            'placeholder': 'Notas adicionales, observaciones, etc. (opcional)'
        })
    
    def clean_fecha_presentacion(self):
        """Validar fecha de presentación"""
        fecha = self.cleaned_data.get('fecha_presentacion')
        if fecha and fecha > date.today():
            raise ValidationError(
                "La fecha de presentación no puede ser futura."
            )
        return fecha
    
    def clean_fecha_vencimiento(self):
        """Validar fecha de vencimiento"""
        fecha = self.cleaned_data.get('fecha_vencimiento')
        if fecha and fecha < date.today():
            raise ValidationError(
                "La fecha de vencimiento no puede ser pasada."
            )
        return fecha
    
    def clean_rol(self):
        """Validar unicidad del rol"""
        rol = self.cleaned_data.get('rol')
        if rol:
            rol = rol.strip().upper()
            
            # Verificar unicidad (excluyendo el objeto actual en edición)
            queryset = Caso.objects.filter(rol=rol)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise ValidationError(
                    f"Ya existe un caso con el rol '{rol}'"
                )
        
        return rol
    
    def clean(self):
        """Validaciones adicionales del formulario"""
        cleaned_data = super().clean()
        fecha_presentacion = cleaned_data.get('fecha_presentacion')
        fecha_vencimiento = cleaned_data.get('fecha_vencimiento')
        fecha_notificacion = cleaned_data.get('fecha_notificacion')
        
        # Validar que fecha de vencimiento sea posterior a presentación
        if fecha_presentacion and fecha_vencimiento:
            if fecha_vencimiento <= fecha_presentacion:
                raise ValidationError(
                    "La fecha de vencimiento debe ser posterior a la fecha de presentación."
                )
        
        # Validar fecha de notificación
        if fecha_notificacion and fecha_presentacion:
            if fecha_notificacion < fecha_presentacion:
                raise ValidationError(
                    "La fecha de notificación no puede ser anterior a la presentación."
                )
        
        return cleaned_data


class DocumentoCasoForm(forms.ModelForm):
    """Formulario para subir documentos a casos"""
    
    class Meta:
        model = DocumentoCaso
        fields = ['titulo', 'archivo', 'descripcion']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'archivo': forms.FileInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['titulo'].required = True
        self.fields['archivo'].required = True
        
        # Placeholders
        self.fields['titulo'].widget.attrs.update({
            'placeholder': 'Ej: Demanda inicial, Resolución, etc.'
        })
        self.fields['descripcion'].widget.attrs.update({
            'placeholder': 'Descripción opcional del documento'
        })
    
    def clean_archivo(self):
        """Validar tamaño y tipo de archivo"""
        archivo = self.cleaned_data.get('archivo')
        
        if archivo:
            # Validar tamaño (10MB máximo)
            if archivo.size > 10 * 1024 * 1024:
                raise ValidationError(
                    "El archivo no puede ser mayor a 10MB."
                )
            
            # Validar extensión
            extensiones_permitidas = ['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png']
            extension = archivo.name.split('.')[-1].lower()
            
            if extension not in extensiones_permitidas:
                raise ValidationError(
                    f"Extensión '{extension}' no permitida. "
                    f"Extensiones permitidas: {', '.join(extensiones_permitidas)}"
                )
        
        return archivo


class AlertaForm(forms.ModelForm):
    """Formulario para crear alertas"""
    
    class Meta:
        model = Alerta
        fields = [
            'caso', 'tipo', 'mensaje', 'fecha_alerta', 
            'enviar_email', 'email_destinatario'
        ]
        widgets = {
            'caso': forms.Select(attrs={'class': 'form-control'}),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'mensaje': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'fecha_alerta': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'}
            ),
            'email_destinatario': forms.EmailInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filtrar casos por usuario si no es staff
        if user and not user.is_staff:
            self.fields['caso'].queryset = Caso.objects.filter(
                usuario_responsable=user
            )
        
        self.fields['mensaje'].required = True
        self.fields['fecha_alerta'].required = True
        
        # Placeholders
        self.fields['mensaje'].widget.attrs.update({
            'placeholder': 'Describe el motivo de la alerta...'
        })
        self.fields['email_destinatario'].widget.attrs.update({
            'placeholder': 'email@ejemplo.com'
        })
    
    def clean_fecha_alerta(self):
        """Validar fecha de alerta"""
        from django.utils import timezone
        fecha = self.cleaned_data.get('fecha_alerta')
        
        if fecha and fecha < timezone.now():
            raise ValidationError(
                "La fecha de alerta no puede ser en el pasado."
            )
        
        return fecha


class MovimientoCasoForm(forms.ModelForm):
    """Formulario para crear movimientos en casos"""
    
    class Meta:
        model = MovimientoCaso
        fields = ['descripcion', 'importante']
        widgets = {
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'importante': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['descripcion'].required = True
        
        # Placeholder
        self.fields['descripcion'].widget.attrs.update({
            'placeholder': 'Describe el movimiento o actuación realizada...'
        })


class BusquedaCasoForm(forms.Form):
    """Formulario para búsqueda avanzada de casos"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por rol, recurrente, materia...'
        })
    )
    
    tipo = forms.ChoiceField(
        choices=[('', 'Todos los tipos')] + Caso.TIPO_CASO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    estado = forms.ChoiceField(
        choices=[('', 'Todos los estados')] + Caso.ESTADO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    tribunal = forms.ChoiceField(
        choices=[('', 'Todos los tribunales')] + Caso.TRIBUNAL_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    solo_urgentes = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def clean(self):
        """Validar rango de fechas"""
        cleaned_data = super().clean()
        fecha_desde = cleaned_data.get('fecha_desde')
        fecha_hasta = cleaned_data.get('fecha_hasta')
        
        if fecha_desde and fecha_hasta:
            if fecha_desde > fecha_hasta:
                raise ValidationError(
                    "La fecha 'desde' no puede ser posterior a la fecha 'hasta'."
                )
        
        return cleaned_data


class ImportarCasosForm(forms.Form):
    """Formulario para importar casos desde archivo CSV"""
    
    archivo_csv = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv'
        }),
        help_text='Archivo CSV con casos a importar'
    )
    
    sobrescribir_existentes = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Marcar para actualizar casos existentes con el mismo rol'
    )
    
    def clean_archivo_csv(self):
        """Validar archivo CSV"""
        archivo = self.cleaned_data.get('archivo_csv')
        
        if archivo:
            if not archivo.name.endswith('.csv'):
                raise ValidationError("El archivo debe tener extensión .csv")
            
            if archivo.size > 5 * 1024 * 1024:  # 5MB
                raise ValidationError("El archivo no puede ser mayor a 5MB")
        
        return archivo


class ReporteCasosForm(forms.Form):
    """Formulario para generar reportes de casos"""
    
    FORMATO_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
    ]
    
    TIPO_REPORTE_CHOICES = [
        ('general', 'Reporte General'),
        ('vencimientos', 'Próximos Vencimientos'),
        ('por_tribunal', 'Por Tribunal'),
        ('por_tipo', 'Por Tipo de Caso'),
    ]
    
    tipo_reporte = forms.ChoiceField(
        choices=TIPO_REPORTE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    formato = forms.ChoiceField(
        choices=FORMATO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text='Opcional: filtrar desde esta fecha'
    )
    
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text='Opcional: filtrar hasta esta fecha'
    )
    
    incluir_cerrados = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Incluir casos cerrados en el reporte'
    )
    
    def clean(self):
        """Validar fechas del reporte"""
        cleaned_data = super().clean()
        fecha_desde = cleaned_data.get('fecha_desde')
        fecha_hasta = cleaned_data.get('fecha_hasta')
        
        if fecha_desde and fecha_hasta:
            if fecha_desde > fecha_hasta:
                raise ValidationError(
                    "La fecha 'desde' no puede ser posterior a la fecha 'hasta'."
                )
        
        return cleaned_data


class ConfiguracionAlertasForm(forms.Form):
    """Formulario para configurar alertas automáticas"""
    
    dias_anticipacion_vencimiento = forms.IntegerField(
        min_value=1,
        max_value=90,
        initial=7,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text='Días antes del vencimiento para crear alerta automática'
    )
    
    enviar_email_automatico = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Enviar emails automáticamente'
    )
    
    email_recordatorio = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        help_text='Email para recibir recordatorios (opcional)'
    )
    
    horario_envio = forms.TimeField(
        initial='09:00',
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        help_text='Hora preferida para recibir alertas'
    )
    
    dias_laborables_solo = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Enviar alertas solo en días laborables'
    )