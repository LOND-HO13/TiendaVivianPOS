from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoriaViewSet, ProductoViewSet, ClienteViewSet, procesar_venta, registrar_abono, registrar_transaccion_bancaria, cierre_de_caja

router = DefaultRouter()
router.register(r'categorias', CategoriaViewSet)
router.register(r'productos', ProductoViewSet)
router.register(r'clientes', ClienteViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('procesar-venta/', procesar_venta, name='procesar_venta'),
    path('registrar-abono/', registrar_abono, name='registrar_abono'),
    path('transaccion-bancaria/', registrar_transaccion_bancaria, name='registrar_transaccion_bancaria'),
    path('cierre-caja/', cierre_de_caja, name='cierre_de_caja'),
    
]