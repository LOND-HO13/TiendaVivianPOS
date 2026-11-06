# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.utils import timezone
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

class Gastos(models.Model):
    id_gasto = models.AutoField(primary_key=True)
    tipo_gasto = models.CharField(max_length=50, default='Proveedor')  # Proveedor, Caja Menor, Servicios
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'gastos'

    def __str__(self):
        return f"{self.tipo_gasto}: {self.descripcion} (-${self.monto})"


class Abonos(models.Model):
    id_abono = models.AutoField(primary_key=True)
    id_cuenta = models.ForeignKey('CuentasPorCobrar', models.CASCADE, db_column='id_cuenta', blank=True, null=True)
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    fecha_pago = models.DateTimeField(blank=True, null=True)
    monto_total_pagado = models.DecimalField(max_digits=12, decimal_places=2)
    interes_pagado = models.DecimalField(max_digits=12, decimal_places=2)
    capital_reducido = models.DecimalField(max_digits=12, decimal_places=2)


class Abono(models.Model):
    # Apuntamos exactamente al modelo Clientes
    cliente = models.ForeignKey('Clientes', on_delete=models.CASCADE, related_name='historial_abonos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"${self.monto} - {self.cliente.nombre_completo}"


class CajaDiaria(models.Model):
    id_caja = models.AutoField(primary_key=True)
    id_usuario_apertura = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario_apertura', blank=True, null=True)
    id_usuario_cierre = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario_cierre', related_name='cajadiaria_id_usuario_cierre_set', blank=True, null=True)
    fecha_apertura = models.DateTimeField(blank=True, null=True)
    fecha_cierre = models.DateTimeField(blank=True, null=True)
    base_inicial = models.DecimalField(max_digits=12, decimal_places=2)
    total_efectivo_ventas = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    total_efectivo_corresponsal = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    estado = models.CharField(max_length=20, blank=True, null=True)


class Categorias(models.Model):
    id_categoria = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)


class Clientes(models.Model):
    id_cliente = models.AutoField(primary_key=True)
    documento_identidad = models.CharField(unique=True, max_length=20, blank=True, null=True)
    nombre_completo = models.CharField(max_length=150)
    telefono = models.CharField(unique=True, max_length=20)
    acepta_notificaciones_whatsapp = models.BooleanField(blank=True, null=True)
    cupo_credito = models.DecimalField(max_digits=12, decimal_places=2)
    estado_riesgo = models.CharField(max_length=20, blank=True, null=True)
    deuda_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cupo_credito = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    deuda_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(Decimal('0.00'))])


class CuentasPorCobrar(models.Model):
    id_cuenta = models.AutoField(primary_key=True)
    id_venta = models.OneToOneField('Ventas', models.DO_NOTHING, db_column='id_venta', blank=True, null=True)
    id_cliente = models.ForeignKey(Clientes, models.DO_NOTHING, db_column='id_cliente', blank=True, null=True)
    capital_original = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)
    interes_acumulado = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=20, blank=True, null=True)


class DetalleVentas(models.Model):
    id_detalle = models.AutoField(primary_key=True)
    id_venta = models.ForeignKey('Ventas', models.CASCADE, db_column='id_venta', blank=True, null=True)
    id_producto = models.ForeignKey('Productos', models.DO_NOTHING, db_column='id_producto', blank=True, null=True)
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)
    precio_unitario_aplicado = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)


class InteraccionesWhatsapp(models.Model):
    id_mensaje = models.AutoField(primary_key=True)
    id_cliente = models.ForeignKey(Clientes, models.CASCADE, db_column='id_cliente', blank=True, null=True)
    tipo_interaccion = models.CharField(max_length=20)
    mensaje_texto = models.TextField()
    fecha_hora = models.DateTimeField(blank=True, null=True)
    estado_entrega = models.CharField(max_length=20, blank=True, null=True)


class PlantillasMensajes(models.Model):
    id_plantilla = models.AutoField(primary_key=True)
    proposito = models.CharField(unique=True, max_length=50)
    contenido_texto = models.TextField()
    activo = models.BooleanField(blank=True, null=True)


class Productos(models.Model):
    id_producto = models.AutoField(primary_key=True)
    codigo_barras = models.CharField(unique=True, max_length=50, blank=True, null=True)
    nombre = models.CharField(max_length=150)
    id_categoria = models.ForeignKey(Categorias, models.DO_NOTHING, db_column='id_categoria', blank=True, null=True)
    precio_detal = models.DecimalField(max_digits=12, decimal_places=2)
    precio_mayorista = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_minima_mayorista = models.IntegerField(blank=True, null=True)
    unidad_medida = models.CharField(max_length=10)
    permite_decimales = models.BooleanField()
    stock_actual = models.DecimalField(max_digits=10, decimal_places=3)
    fecha_creacion = models.DateTimeField(blank=True, null=True)
    precio_detal = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    precio_mayorista = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    stock_actual = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.000'))])
    stock_actual = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.000'))])
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=3, default=5.000, validators=[MinValueValidator(Decimal('0.000'))])


class Roles(models.Model):
    id_rol = models.AutoField(primary_key=True)
    nombre_rol = models.CharField(unique=True, max_length=50)


class TransaccionesFinancieras(models.Model):
    id_transaccion = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    fecha_hora = models.DateTimeField(blank=True, null=True)
    tipo_movimiento = models.CharField(max_length=50)
    entidad_bancaria = models.CharField(max_length=50)
    monto_transaccion = models.DecimalField(max_digits=12, decimal_places=2)
    comision_ganada = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=20, blank=True, null=True)


class Usuarios(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    username = models.CharField(unique=True, max_length=50)
    password_hash = models.CharField(max_length=255)
    id_rol = models.ForeignKey(Roles, models.DO_NOTHING, db_column='id_rol', blank=True, null=True)
    nombre_empleado = models.CharField(max_length=150)
    estado_activo = models.BooleanField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(blank=True, null=True)


class Ventas(models.Model):
    id_venta = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey(Usuarios, models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    id_cliente = models.ForeignKey(Clientes, models.DO_NOTHING, db_column='id_cliente', blank=True, null=True)
    fecha_hora = models.DateTimeField(blank=True, null=True)
    total_venta = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago = models.CharField(max_length=50)
    estado = models.CharField(max_length=20, blank=True, null=True)