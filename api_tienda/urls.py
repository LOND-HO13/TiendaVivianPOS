from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# 1. Configurar los ViewSets automáticos
router = DefaultRouter()
router.register(r'clientes-auto', views.ClienteViewSet, basename='cliente')
router.register(r'productos-auto', views.ProductoViewSet, basename='producto')
router.register(r'categorias-auto', views.CategoriaViewSet, basename='categoria')

urlpatterns = [
    # 2. FUNCIONES PERSONALIZADAS PRIMERO (Sin el prefijo "api/")
    path('categorias/', views.gestionar_categorias),
    path('productos/crear/', views.crear_producto),
    path('productos/<int:id_producto>/editar/', views.editar_producto),
    
    path('productos/', views.ProductoViewSet.as_view({'get': 'list'})), 
    path('clientes/', views.ClienteViewSet.as_view({'get': 'list', 'post': 'create'})),

    path('procesar-venta/', views.procesar_venta),
    path('ventas/historial/', views.historial_ventas_completas),
    path('abonos/', views.registrar_abono),
    path('gastos/', views.gestionar_gastos),
    path('cartera/detalles/<int:id_cliente>/', views.detalles_deuda_cliente),
    path('cierre-caja/', views.cierre_de_caja),
    path('cierre-caja/historial/', views.historial_cierres_caja),
    
    # 3. RUTAS AUTOMÁTICAS AL FINAL
    path('auto/', include(router.urls)),
]