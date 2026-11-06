from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from decimal import Decimal
from django.shortcuts import render
from rest_framework import viewsets
from .models import Abono
from .serializers import CategoriaSerializer, ProductoSerializer, ClienteSerializer
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum
from .models import Productos, Ventas, DetalleVentas, Clientes, CuentasPorCobrar, Abonos, TransaccionesFinancieras, CajaDiaria, Categorias


@api_view(['GET', 'POST'])
def gestionar_categorias(request):
    if request.method == 'GET':
        categorias = list(Categorias.objects.values('id_categoria', 'nombre', 'descripcion'))
        return Response(categorias)
    
    if request.method == 'POST':
        nombre = request.data.get('nombre', '').strip()
        if not nombre:
            return Response({'error': 'El nombre de la categoría es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)
        cat = Categorias.objects.create(
            nombre=nombre,
            descripcion=request.data.get('descripcion', '')
        )
        return Response({'id_categoria': cat.id_categoria, 'nombre': cat.nombre}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def crear_producto(request):
    data = request.data
    codigo = data.get('codigo_barras')
    codigo_limpio = codigo.strip() if codigo and str(codigo).strip() != '' else None

    if codigo_limpio and Productos.objects.filter(codigo_barras=codigo_limpio).exists():
        return Response({'error': 'Ya existe un producto con este código de barras.'}, status=status.HTTP_400_BAD_REQUEST)

    es_pesaje = bool(data.get('permite_decimales', False))
    precio_venta = Decimal(str(data.get('precio_detal', 0)))
    precio_costo = Decimal(str(data.get('precio_costo', precio_venta)))

    # VALIDACIÓN CRÍTICA: No permitir crear/editar si el costo es mayor a la venta
    if precio_venta < precio_costo:
        return Response({'error': 'El precio de venta no puede ser menor al costo del comerciante. Generaría pérdida.'}, status=status.HTTP_400_BAD_REQUEST)

    producto = Productos.objects.create(
        codigo_barras=codigo_limpio,
        nombre=data.get('nombre', '').strip(),
        id_categoria_id=data.get('id_categoria') or None,
        precio_detal=precio_venta,
        precio_mayorista=precio_costo,
        cantidad_minima_mayorista=0, # En 0 para que siempre cobre a precio de venta
        unidad_medida='KG' if es_pesaje else 'UND',
        permite_decimales=es_pesaje,
        stock_actual=data.get('stock_actual', 0),
        fecha_creacion=timezone.now()
    )
    return Response({'mensaje': 'Producto creado', 'id_producto': producto.id_producto}, status=status.HTTP_201_CREATED)


@api_view(['PUT', 'PATCH'])
def editar_producto(request, id_producto):
    try:
        producto = Productos.objects.get(pk=id_producto)
    except Productos.DoesNotExist:
        return Response({'error': 'Producto no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    if 'nombre' in data:
        producto.nombre = data['nombre'].strip()
    if 'precio_detal' in data:
        producto.precio_detal = Decimal(str(data['precio_detal']))
    if 'precio_costo' in data:
        producto.precio_mayorista = Decimal(str(data['precio_costo']))
    if 'id_categoria' in data:
        producto.id_categoria_id = data['id_categoria'] or None
    if 'codigo_barras' in data:
        cod = data['codigo_barras']
        producto.codigo_barras = cod.strip() if cod and str(cod).strip() != '' else None
    if 'permite_decimales' in data:
        es_pesaje = bool(data['permite_decimales'])
        producto.permite_decimales = es_pesaje
        producto.unidad_medida = 'KG' if es_pesaje else 'UND'
    if 'stock_actual' in data:
        producto.stock_actual = data['stock_actual']

    producto.save()
    return Response({'mensaje': 'Producto actualizado correctamente.'})

@api_view(['GET'])
def detalles_deuda_cliente(request, id_cliente):
    try:
        # Filtramos las cuentas que aún no están pagadas de ese cliente
        cuentas = CuentasPorCobrar.objects.filter(id_cliente=id_cliente, estado='Pendiente')
        
        datos = []
        for cuenta in cuentas:
            total_factura = cuenta.saldo_pendiente + cuenta.interes_acumulado
            datos.append({
                'id_cuenta': cuenta.pk,
                'id_venta': cuenta.id_venta.id_venta if cuenta.id_venta else 'N/A',
                'saldo_pendiente': str(cuenta.saldo_pendiente),
                'interes_acumulado': str(cuenta.interes_acumulado),
                'total': str(total_factura)
            })
            
        return Response(datos, status=200)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
def cierre_de_caja(request):
    try:
        ahora = timezone.localtime(timezone.now())
        hoy = ahora.date()

        ventas_hoy_qs = Ventas.objects.filter(fecha_hora__date=hoy)
        
        ventas_efectivo = ventas_hoy_qs.filter(metodo_pago__iexact='Efectivo').aggregate(total=Sum('total_venta'))['total'] or Decimal('0.00')
        cant_ventas_efectivo = ventas_hoy_qs.filter(metodo_pago__iexact='Efectivo').count()

        ventas_credito = ventas_hoy_qs.filter(metodo_pago__iexact='Crédito').aggregate(total=Sum('total_venta'))['total'] or Decimal('0.00')
        cant_ventas_credito = ventas_hoy_qs.filter(metodo_pago__iexact='Crédito').count()

        abonos_hoy_qs = Abono.objects.filter(fecha_registro__date=hoy)
        abonos_totales_hoy = abonos_hoy_qs.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        cant_abonos = abonos_hoy_qs.count()

        # Cálculo de Ganancia Neta sobre todo lo vendido hoy
        detalles_hoy = DetalleVentas.objects.select_related('id_producto').filter(id_venta__fecha_hora__date=hoy)
        ganancia_estimada_hoy = Decimal('0.00')
        for d in detalles_hoy:
            if d.id_producto:
                costo = d.id_producto.precio_mayorista or Decimal('0.00')
                ganancia_estimada_hoy += (d.precio_unitario_aplicado - costo) * d.cantidad

        ingresos_efectivo_hoy = ventas_efectivo + abonos_totales_hoy

        cierres_previos_hoy = CajaDiaria.objects.filter(
            fecha_cierre__date=hoy
        ).aggregate(total=Sum('total_efectivo_ventas'))['total'] or Decimal('0.00')

        nuevo_efectivo = ingresos_efectivo_hoy - cierres_previos_hoy

        if nuevo_efectivo <= 0 and cant_ventas_credito == 0:
            return Response({'error': 'No hay movimientos nuevos registrados en este turno para cerrar.'}, status=status.HTTP_400_BAD_REQUEST)

        if nuevo_efectivo > 0:
            with transaction.atomic():
                CajaDiaria.objects.create(
                    fecha_cierre=ahora,
                    base_inicial=Decimal('0.00'),
                    total_efectivo_ventas=nuevo_efectivo,
                    total_efectivo_corresponsal=Decimal('0.00'),
                    estado='Cerrada'
                )

        return Response({
            'mensaje': 'Corte de caja generado',
            'fecha_hora_corte': ahora.strftime('%d/%m/%Y %I:%M:%S %p'),
            'nuevo_efectivo': str(nuevo_efectivo),
            'cierres_previos': str(cierres_previos_hoy),
            'total_efectivo_dia': str(ingresos_efectivo_hoy),
            'ventas_efectivo': str(ventas_efectivo),
            'cant_ventas_efectivo': cant_ventas_efectivo,
            'ventas_credito': str(ventas_credito),
            'cant_ventas_credito': cant_ventas_credito,
            'abonos_hoy': str(abonos_totales_hoy),
            'cant_abonos': cant_abonos,
            'ganancia_neta_dia': str(ganancia_estimada_hoy.quantize(Decimal('0.01')))
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': f'Error interno: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)        
        
@api_view(['POST'])
def registrar_transaccion_bancaria(request):
    try:
        tipo_movimiento = request.data.get('tipo_movimiento')
        entidad_bancaria = request.data.get('entidad_bancaria')
        monto_transaccion = Decimal(str(request.data.get('monto_transaccion', '0.00')))
        recargo_tienda = Decimal(str(request.data.get('recargo_tienda', '0.00')))

        if not tipo_movimiento or not entidad_bancaria:
            return Response({'error': 'Faltan datos obligatorios (tipo_movimiento, entidad_bancaria)'}, status=status.HTTP_400_BAD_REQUEST)

        if monto_transaccion <= 0:
            return Response({'error': 'El monto debe ser mayor a cero'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            nueva_transaccion = TransaccionesFinancieras.objects.create(
                tipo_movimiento=tipo_movimiento,
                entidad_bancaria=entidad_bancaria,
                monto_transaccion=monto_transaccion,
               recargo_tienda=recargo_tienda,
                estado='Completada',
                fecha_hora=timezone.now()
                # id_usuario_id=request.user.id # (Descomentar al implementar login de cajeros)
            )

        return Response({
            'mensaje': f'{tipo_movimiento} registrado exitosamente',
            'id_transaccion': nueva_transaccion.id_transaccion,
            'ganancia_cajon_tienda': recargo_tienda
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': f'Error interno: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def registrar_abono(request):
    try:
        id_cuenta_cobrar = request.data.get('id_cuenta')
        monto_ingresado = Decimal(str(request.data.get('monto_abono', '0.00')))

        if monto_ingresado <= 0:
            return Response({'error': 'El monto del abono debe ser mayor a cero'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            cuenta = CuentasPorCobrar.objects.select_for_update().get(pk=id_cuenta_cobrar)

            if cuenta.estado == 'Pagada':
                return Response({'error': 'Esta cuenta ya está totalmente pagada'}, status=status.HTTP_400_BAD_REQUEST)

            # CORRECCIÓN: Evitar valores None convirtiéndolos a Decimal 0.00
            interes_actual = cuenta.interes_acumulado if cuenta.interes_acumulado is not None else Decimal('0.00')
            saldo_actual = cuenta.saldo_pendiente if cuenta.saldo_pendiente is not None else Decimal('0.00')

            # Distribución inteligente del dinero
            if monto_ingresado >= interes_actual:
                pago_interes = interes_actual
                pago_capital = monto_ingresado - pago_interes
            else:
                pago_interes = monto_ingresado
                pago_capital = Decimal('0.00')

            if pago_capital > saldo_actual:
                return Response({'error': f'El abono supera la deuda. Pago máximo permitido: {interes_actual + saldo_actual}'}, status=status.HTTP_400_BAD_REQUEST)

            # Aplicar los descuentos a la cuenta
            cuenta.interes_acumulado = interes_actual - pago_interes
            cuenta.saldo_pendiente = saldo_actual - pago_capital

            if cuenta.saldo_pendiente == Decimal('0.00') and cuenta.interes_acumulado == Decimal('0.00'):
                cuenta.estado = 'Pagada'
            
            cuenta.save()

            Abonos.objects.create(
                id_cuenta=cuenta,
                monto_total_pagado=monto_ingresado,
                interes_pagado=pago_interes,
                capital_reducido=pago_capital
            )

        return Response({
            'mensaje': 'Abono registrado exitosamente',
            'saldo_restante': cuenta.saldo_pendiente,
            'interes_restante': cuenta.interes_acumulado,
            'estado_cuenta': cuenta.estado
        }, status=status.HTTP_201_CREATED)

    except CuentasPorCobrar.DoesNotExist:
        return Response({'error': 'La cuenta por cobrar no existe'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': f'Error interno: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    
@api_view(['POST'])
def procesar_venta(request):
    try:
        metodo_pago = request.data.get('metodo_pago', 'Efectivo')
        id_cliente_opcional = request.data.get('id_cliente', None)
        carrito = request.data.get('carrito', [])

        if metodo_pago == 'Crédito' and not id_cliente_opcional:
            return Response({'error': 'Para ventas a crédito, es obligatorio enviar el id_cliente'}, status=status.HTTP_400_BAD_REQUEST)

        if not carrito:
            return Response({'error': 'El carrito está vacío'}, status=status.HTTP_400_BAD_REQUEST)

        # TODO el proceso debe estar dentro de transaction.atomic()
        with transaction.atomic():
            total_venta_calculado = Decimal('0.00')
            detalles_a_crear = []
            
            nueva_venta = Ventas.objects.create(
                metodo_pago=metodo_pago,
                total_venta=0,
                id_cliente_id=id_cliente_opcional,
                fecha_hora=timezone.now(),
                estado='Completada'
            )

            for item in carrito:
                id_prod = item.get('id_producto') or item.get('id')
                if not id_prod:
                    raise ValueError('Un ítem del carrito no tiene un ID de producto válido.')

                producto = Productos.objects.select_for_update().get(pk=id_prod)
                cantidad_solicitada = Decimal(str(item.get('cantidad', 1)))

                if producto.stock_actual < cantidad_solicitada:
                    raise ValueError(f'Stock insuficiente para: {producto.nombre}')

                precio_aplicado = producto.precio_detal
                subtotal_item = precio_aplicado * cantidad_solicitada
                total_venta_calculado += subtotal_item

                detalles_a_crear.append(DetalleVentas(
                    id_venta=nueva_venta,
                    id_producto=producto,
                    cantidad=cantidad_solicitada,
                    precio_unitario_aplicado=precio_aplicado,
                    subtotal=subtotal_item
                ))

                producto.stock_actual -= cantidad_solicitada
                producto.save()

            DetalleVentas.objects.bulk_create(detalles_a_crear)
            nueva_venta.total_venta = total_venta_calculado
            nueva_venta.save()

            if metodo_pago == 'Crédito':
                # El select_for_update ahora está correctamente DENTRO de transaction.atomic()
                cliente = Clientes.objects.select_for_update().get(pk=id_cliente_opcional)
                
                tasa_fianza = Decimal('0.10')
                interes_inicial = total_venta_calculado * tasa_fianza
                total_deuda_nueva = total_venta_calculado + interes_inicial
                
                deuda_proyectada = (cliente.deuda_actual or Decimal('0.00')) + total_deuda_nueva
                
                # Validación de cupo de crédito
                if deuda_proyectada > cliente.cupo_credito:
                    raise ValueError(f'Venta rechazada: Excede el cupo de crédito del vecino. Cupo máximo: ${cliente.cupo_credito}, Deuda proyectada: ${deuda_proyectada}')
                
                cliente.deuda_actual = deuda_proyectada
                cliente.save()

                fecha_corte = timezone.now().date() + timedelta(days=30)
                CuentasPorCobrar.objects.create(
                    id_venta=nueva_venta,
                    id_cliente=cliente,
                    capital_original=total_venta_calculado,
                    saldo_pendiente=total_venta_calculado,
                    interes_acumulado=interes_inicial,
                    fecha_vencimiento=fecha_corte,
                    estado='Pendiente'
                )

        return Response({
            'mensaje': 'Venta procesada con éxito', 
            'id_venta': nueva_venta.id_venta,
            'total': total_venta_calculado
        }, status=status.HTTP_201_CREATED)

    except ValueError as e:
        # Errores de validación (cupo, stock)
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        # Otros errores
        return Response({'error': f'Error interno: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def historial_ventas_completas(request):
    try:
        ventas = Ventas.objects.select_related('id_cliente').all().order_by('-id_venta')[:60]
        datos = []
        
        for venta in ventas:
            detalles_query = DetalleVentas.objects.select_related('id_producto').filter(id_venta=venta)
            lista_productos = []
            ganancia_venta = Decimal('0.00')
            
            for det in detalles_query:
                nombre_prod = det.id_producto.nombre if det.id_producto else "Producto eliminado"
                unidad = det.id_producto.unidad_medida if det.id_producto else "UND"
                costo_unit = det.id_producto.precio_mayorista if det.id_producto else det.precio_unitario_aplicado
                
                ganancia_item = (det.precio_unitario_aplicado - costo_unit) * det.cantidad
                ganancia_venta += ganancia_item

                lista_productos.append({
                    'nombre': nombre_prod,
                    'cantidad': str(det.cantidad),
                    'unidad': unidad,
                    'precio_unitario': str(det.precio_unitario_aplicado),
                    'subtotal': str(det.subtotal)
                })
            
            fecha_local = timezone.localtime(venta.fecha_hora) if venta.fecha_hora else None
            fecha_str = fecha_local.strftime('%d/%m/%Y %I:%M %p') if fecha_local else 'Sin fecha'
            nombre_cliente = venta.id_cliente.nombre_completo if venta.id_cliente else 'Cliente de Contado'
                
            datos.append({
                'id_venta': venta.id_venta,
                'fecha_hora': fecha_str,
                'metodo_pago': venta.metodo_pago,
                'cliente': nombre_cliente,
                'total': str(venta.total_venta),
                'ganancia': str(ganancia_venta.quantize(Decimal('0.01'))),
                'productos': lista_productos
            })
            
        return Response(datos, status=200)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
            
@api_view(['POST'])
def registrar_abono(request):
    try:
        id_cliente = request.data.get('id_cliente')
        monto = request.data.get('monto')

        if not id_cliente or not monto:
            return Response({'error': 'Faltan datos del cliente o el monto.'}, status=status.HTTP_400_BAD_REQUEST)

        # Buscamos usando el modelo Clientes
        cliente = Clientes.objects.get(id_cliente=id_cliente)
        monto_decimal = Decimal(str(monto))

        if monto_decimal <= 0:
            return Response({'error': 'El abono debe ser mayor a 0.'}, status=status.HTTP_400_BAD_REQUEST)

        cliente.deuda_actual -= monto_decimal
        
        if cliente.deuda_actual < 0:
            cliente.deuda_actual = Decimal('0.00')
            
        cliente.save()

        Abono.objects.create(cliente=cliente, monto=monto_decimal)

        return Response({
            'mensaje': 'Abono registrado correctamente', 
            'nueva_deuda': cliente.deuda_actual
        }, status=status.HTTP_200_OK)

    # Capturamos el error usando el modelo Clientes
    except Clientes.DoesNotExist:
        return Response({'error': 'Cliente no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
def historial_abonos(request, id_cliente):
    try:
        # Filtramos los abonos por cliente y los ordenamos por fecha descendente (-)
        abonos = Abono.objects.filter(cliente__id_cliente=id_cliente).order_by('-fecha_registro')
        
        datos = []
        for abono in abonos:
            datos.append({
                'id': abono.id,
                'monto': str(abono.monto),
                # Convertimos la fecha de la base de datos a formato Día/Mes/Año Hora:Minuto
                'fecha': abono.fecha_registro.strftime('%d/%m/%Y %H:%M')
            })
            
        return Response(datos, status=200)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categorias.objects.all()
    serializer_class = CategoriaSerializer

class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Productos.objects.all()
    serializer_class = ProductoSerializer

class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Clientes.objects.all()
    serializer_class = ClienteSerializer