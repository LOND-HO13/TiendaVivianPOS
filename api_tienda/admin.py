from django.contrib import admin
from .models import Categorias, Productos, Clientes, Ventas, DetalleVentas, CuentasPorCobrar, Abonos

# Registramos las tablas para que aparezcan en el panel web
admin.site.register(Categorias)
admin.site.register(Productos)
admin.site.register(Clientes)
admin.site.register(Ventas)
admin.site.register(DetalleVentas)
admin.site.register(CuentasPorCobrar)
admin.site.register(Abonos)