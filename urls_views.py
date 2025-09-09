# apps/casos/urls.py
"""
URLs para la aplicación de casos
"""
from django.urls import path
from . import views

app_name = 'casos'

urlpatterns = [
    # Dashboard principal
    path('', views.DashboardView.as_view(), name='dashboard'),
    
    # Casos
    path('casos/', views.CasoListView.as_view(), name='lista'),
    path('casos/<int:pk>/', views.CasoDetailView.as_view(), name='detalle'),
    path('casos/crear/', views.CasoCreateView.as_view(), name='crear'),
    path('casos/<int:pk>/editar/', views.CasoUpdateView.as_view(), name='editar'),
    
    # API endpoints para gráficos
    path('api/casos-por-tipo/', views.casos_por_tipo_api, name='api_casos_tipo'),
    path('api/casos-por-estado/', views.casos_por_estado_api, name='api_casos_estado'),
    path('api/proximos-vencimientos/', views.proximos_vencimientos_api, name='api_vencimientos'),
    
    # Documentos
    path('casos/<int:caso_pk>/documentos/subir/', views.SubirDocumentoView.as_view(), name='subir_documento'),
    path('documentos/<int:pk>/descargar/', views.descargar_documento, name='descargar_documento'),
    
    # Alertas
    path('alertas/', views.AlertaListView.as_view(), name='alertas'),
    path('alertas/<int:pk>/marcar-leida/', views.marcar_alerta_leida, name='marcar_alerta_leida'),
]

# apps/casos/views.py
"""
Vistas para la aplicación de casos
"""
import json
from datetime import date, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import (
    ListView, DetailView, CreateView, 
    UpdateView, TemplateView
)
from django.http import JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.db.models import Q, Count
from django.urls import reverse_lazy
from django.utils import timezone
from .models import Caso, DocumentoCaso, Alerta, MovimientoCaso
from .forms import CasoForm, DocumentoCasoForm


class DashboardView(LoginRequiredMixin, TemplateView):
    """Vista principal del dashboard con estadísticas"""
    template_name = 'casos/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Filtrar casos por usuario si no es staff
        if self.request.user.is_staff:
            casos_queryset = Caso.objects.all()
        else:
            casos_queryset = Caso.objects.filter(usuario_responsable=self.request.user)
        
        # Estadísticas generales
        context['total_casos'] = casos_queryset.count()
        context['casos_abiertos'] = casos_queryset.filter(estado='EN_TRAMITACION').count()
        context['casos_cerrados'] = casos_queryset.filter(estado='CERRADO').count()
        context['casos_urgentes'] = casos_queryset.filter(urgente=True).count()
        
        # Casos próximos a vencer (7 días)
        fecha_limite = date.today() + timedelta(days=7)
        context['proximos_vencimientos'] = casos_queryset.filter(
            estado='EN_TRAMITACION',
            fecha_vencimiento__lte=fecha_limite
        ).order_by('fecha_vencimiento')[:10]
        
        # Casos vencidos
        context['casos_vencidos'] = casos_queryset.filter(
            estado='EN_TRAMITACION',
            fecha_vencimiento__lt=date.today()
        ).order_by('fecha_vencimiento')[:5]
        
        # Alertas pendientes
        if self.request.user.is_staff:
            alertas_queryset = Alerta.objects.all()
        else:
            alertas_queryset = Alerta.objects.filter(
                caso__usuario_responsable=self.request.user
            )
        
        context['alertas_pendientes'] = alertas_queryset.filter(
            enviada=False,
            leida=False
        ).order_by('fecha_alerta')[:5]
        
        # Actividad reciente
        context['movimientos_recientes'] = MovimientoCaso.objects.filter(
            caso__in=casos_queryset
        ).order_by('-fecha_movimiento')[:10]
        
        return context


class CasoListView(LoginRequiredMixin, ListView):
    """Vista de lista de casos"""
    model = Caso
    template_name = 'casos/caso_list.html'
    context_object_name = 'casos'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = Caso.objects.select_related('usuario_responsable')
        
        # Filtrar por usuario si no es staff
        if not self.request.user.is_staff:
            queryset = queryset.filter(usuario_responsable=self.request.user)
        
        # Filtros de búsqueda
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(rol__icontains=search) |
                Q(recurrente__icontains=search) |
                Q(recurrido__icontains=search) |
                Q(materia__icontains=search)
            )
        
        # Filtros adicionales
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        estado = self.request.GET.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)
        
        tribunal = self.request.GET.get('tribunal')
        if tribunal:
            queryset = queryset.filter(tribunal=tribunal)
        
        return queryset.order_by('-fecha_vencimiento', '-fecha_creacion')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        context['tipo_selected'] = self.request.GET.get('tipo', '')
        context['estado_selected'] = self.request.GET.get('estado', '')
        context['tribunal_selected'] = self.request.GET.get('tribunal', '')
        
        # Opciones para filtros
        context['tipos'] = Caso.TIPO_CASO_CHOICES
        context['estados'] = Caso.ESTADO_CHOICES
        context['tribunales'] = Caso.TRIBUNAL_CHOICES
        
        return context


class CasoDetailView(LoginRequiredMixin, DetailView):
    """Vista de detalle de caso"""
    model = Caso
    template_name = 'casos/caso_detail.html'
    context_object_name = 'caso'
    
    def get_queryset(self):
        queryset = Caso.objects.select_related('usuario_responsable')
        if not self.request.user.is_staff:
            queryset = queryset.filter(usuario_responsable=self.request.user)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        caso = self.get_object()
        
        # Documentos del caso
        context['documentos'] = caso.documentos.all().order_by('-fecha_subida')
        
        # Alertas del caso
        context['alertas'] = caso.alertas.all().order_by('-fecha_alerta')
        
        # Movimientos del caso
        context['movimientos'] = caso.movimientos.all().order_by('-fecha_movimiento')
        
        # Formulario para subir documentos
        context['documento_form'] = DocumentoCasoForm()
        
        return context


class CasoCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear nuevo caso"""
    model = Caso
    form_class = CasoForm
    template_name = 'casos/caso_form.html'
    success_url = reverse_lazy('casos:lista')
    
    def form_valid(self, form):
        form.instance.usuario_responsable = self.request.user
        messages.success(self.request, 'Caso creado exitosamente.')
        return super().form_valid(form)


class CasoUpdateView(LoginRequiredMixin, UpdateView):
    """Vista para editar caso"""
    model = Caso
    form_class = CasoForm
    template_name = 'casos/caso_form.html'
    
    def get_queryset(self):
        queryset = Caso.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(usuario_responsable=self.request.user)
        return queryset
    
    def form_valid(self, form):
        messages.success(self.request, 'Caso actualizado exitosamente.')
        return super().form_valid(form)


class SubirDocumentoView(LoginRequiredMixin, CreateView):
    """Vista para subir documentos a un caso"""
    model = DocumentoCaso
    form_class = DocumentoCasoForm
    template_name = 'casos/subir_documento.html'
    
    def dispatch(self, request, *args, **kwargs):
        self.caso = get_object_or_404(Caso, pk=kwargs['caso_pk'])
        
        # Verificar permisos
        if not request.user.is_staff and self.caso.usuario_responsable != request.user:
            raise Http404("No tienes permisos para acceder a este caso")
        
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.caso = self.caso
        form.instance.usuario_subida = self.request.user
        messages.success(self.request, 'Documento subido exitosamente.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('casos:detalle', kwargs={'pk': self.caso.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['caso'] = self.caso
        return context


class AlertaListView(LoginRequiredMixin, ListView):
    """Vista de lista de alertas"""
    model = Alerta
    template_name = 'casos/alerta_list.html'
    context_object_name = 'alertas'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = Alerta.objects.select_related('caso', 'usuario_creador')
        
        if not self.request.user.is_staff:
            queryset = queryset.filter(caso__usuario_responsable=self.request.user)
        
        return queryset.order_by('-fecha_alerta')


# API Views para gráficos
@login_required
def casos_por_tipo_api(request):
    """API para gráfico de casos por tipo"""
    if request.user.is_staff:
        casos = Caso.objects.all()
    else:
        casos = Caso.objects.filter(usuario_responsable=request.user)
    
    datos = casos.values('tipo').annotate(total=Count('tipo'))
    
    labels = []
    values = []
    colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0']
    
    for i, item in enumerate(datos):
        labels.append(dict(Caso.TIPO_CASO_CHOICES)[item['tipo']])
        values.append(item['total'])
    
    return JsonResponse({
        'labels': labels,
        'datasets': [{
            'data': values,
            'backgroundColor': colors[:len(values)],
            'borderColor': colors[:len(values)],
            'borderWidth': 1
        }]
    })


@login_required
def casos_por_estado_api(request):
    """API para gráfico de casos por estado"""
    if request.user.is_staff:
        casos = Caso.objects.all()
    else:
        casos = Caso.objects.filter(usuario_responsable=request.user)
    
    datos = casos.values('estado').annotate(total=Count('estado'))
    
    labels = []
    values = []
    colors = ['#28a745', '#dc3545', '#ffc107', '#17a2b8']
    
    for i, item in enumerate(datos):
        labels.append(dict(Caso.ESTADO_CHOICES)[item['estado']])
        values.append(item['total'])
    
    return JsonResponse({
        'labels': labels,
        'datasets': [{
            'data': values,
            'backgroundColor': colors[:len(values)],
            'borderColor': colors[:len(values)],
            'borderWidth': 1
        }]
    })


@login_required
def proximos_vencimientos_api(request):
    """API para gráfico de próximos vencimientos"""
    if request.user.is_staff:
        casos = Caso.objects.all()
    else:
        casos = Caso.objects.filter(usuario_responsable=request.user)
    
    # Casos próximos 30 días
    fecha_limite = date.today() + timedelta(days=30)
    casos_proximos = casos.filter(
        estado='EN_TRAMITACION',
        fecha_vencimiento__gte=date.today(),
        fecha_vencimiento__lte=fecha_limite
    ).order_by('fecha_vencimiento')[:10]
    
    labels = []
    values = []
    colors = []
    
    for caso in casos_proximos:
        labels.append(f"{caso.rol} - {caso.recurrente[:30]}")
        values.append(caso.dias_hasta_vencimiento)
        
        # Color según urgencia
        if caso.dias_hasta_vencimiento <= 3:
            colors.append('#dc3545')  # Rojo
        elif caso.dias_hasta_vencimiento <= 7:
            colors.append('#ffc107')  # Amarillo
        else:
            colors.append('#28a745')  # Verde
    
    return JsonResponse({
        'labels': labels,
        'datasets': [{
            'label': 'Días hasta vencimiento',
            'data': values,
            'backgroundColor': colors,
            'borderColor': colors,
            'borderWidth': 1
        }]
    })


# Funciones auxiliares
@login_required
def descargar_documento(request, pk):
    """Descargar documento adjunto"""
    documento = get_object_or_404(DocumentoCaso, pk=pk)
    
    # Verificar permisos
    if not request.user.is_staff and documento.caso.usuario_responsable != request.user:
        raise Http404("No tienes permisos para descargar este documento")
    
    if documento.archivo:
        response = HttpResponse(
            documento.archivo.read(),
            content_type='application/octet-stream'
        )
        response['Content-Disposition'] = f'attachment; filename="{documento.archivo.name.split("/")[-1]}"'
        return response
    
    raise Http404("Archivo no encontrado")


@login_required
def marcar_alerta_leida(request, pk):
    """Marcar alerta como leída"""
    alerta = get_object_or_404(Alerta, pk=pk)
    
    # Verificar permisos
    if not request.user.is_staff and alerta.caso.usuario_responsable != request.user:
        raise Http404("No tienes permisos para esta alerta")
    
    alerta.leida = True
    alerta.save(update_fields=['leida'])
    
    messages.success(request, 'Alerta marcada como leída.')
    return redirect('Casos:alertas')