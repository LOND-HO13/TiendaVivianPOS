from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from decimal import Decimal
from django.shortcuts import render
from rest_framework import viewsets
from .models import Categorias, Productos, Clientes
from .serializers import CategoriaSerializer, ProductoSerializer, ClienteSerializer
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum
from .models import Productos, Ventas, DetalleVentas, Clientes, CuentasPorCobrar, Abonos, TransaccionesFinancieras, CajaDiaria

@api_view(['POST'])
def cierre_de_caja(request):
    try:
        hoy = timezone.now().date()
        
        # 1. Sumar todos los ingresos en efectivo para el CAJÓN DE LA TIENDA
        ventas_efectivo = Ventas.objects.filter(
            fecha_hora__date=hoy, 
            metodo_pago='Efectivo'
        ).aggregate(total=Sum('total_venta'))['total'] or Decimal('0.00')
        
        total_abonos = Abonos.objects.filter(
            fecha_pago__date=hoy
        ).aggregate(total=Sum('monto_total_pagado'))['total'] or Decimal('0.00')
        
        # Extraemos los recargos cobrados a los clientes por hacer transacciones
        recargos_tienda = TransaccionesFinancieras.objects.filter(
            fecha_hora__date=hoy
        ).aggregate(total=Sum('comision_ganada'))['total'] or Decimal('0.00')
        
        # El montón de billetes de la tienda ahora incluye las ventas, los fiados pagados y la ganancia del banco
        efectivo_tienda = ventas_efectivo + total_abonos + recargos_tienda

        # 2. Calcular el flujo estricto para el CAJÓN DEL BANCO
        consignaciones = TransaccionesFinancieras.objects.filter(
            fecha_hora__date=hoy, 
            tipo_movimiento='Consignación'
        ).aggregate(total=Sum('monto_transaccion'))['total'] or Decimal('0.00')
        
        retiros = TransaccionesFinancieras.objects.filter(
            fecha_hora__date=hoy, 
            tipo_movimiento='Retiro'
        ).aggregate(total=Sum('monto_transaccion'))['total'] or Decimal('0.00')
        
        # El montón de billetes del banco solo refleja lo que entra o sale de la terminal
        flujo_corresponsal = consignaciones - retiros

        with transaction.atomic():
            cierre = CajaDiaria.objects.create(
                fecha_cierre=timezone.now(),
                base_inicial=Decimal('0.00'), 
                total_efectivo_ventas=efectivo_tienda,
                total_efectivo_corresponsal=flujo_corresponsal,
                estado='Cerrada'
            )

        return Response({
            'mensaje': 'Caja cerrada exitosamente',
            'id_cierre': cierre.id_caja,
            'cuadre_fisico_tienda': efectivo_tienda,      # Ventas + Abonos + Recargos
            'cuadre_fisico_cajero': flujo_corresponsal    # Consignaciones - Retiros
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

        # 1. Validación estricta para fiados
        if metodo_pago == 'Crédito' and not id_cliente_opcional:
            return Response({'error': 'Para ventas a crédito, es obligatorio enviar el id_cliente'}, status=status.HTTP_400_BAD_REQUEST)

        if not carrito:
            return Response({'error': 'El carrito está vacío'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            total_venta_calculado = Decimal('0.00')
            detalles_a_crear = []
            
            nueva_venta = Ventas.objects.create(
                metodo_pago=metodo_pago,
                total_venta=0,
                id_cliente_id=id_cliente_opcional 
            )

            for item in carrito:
                producto = Productos.objects.select_for_update().get(pk=item['id_producto'])
                cantidad_solicitada = Decimal(str(item['cantidad']))

                if producto.stock_actual < cantidad_solicitada:
                    raise ValueError(f'Stock insuficiente para el producto: {producto.nombre}')

                if producto.cantidad_minima_mayorista > 0 and cantidad_solicitada >= producto.cantidad_minima_mayorista:
                    precio_aplicado = producto.precio_mayorista
                else:
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

            # 2. Lógica de crédito con interés inmediato
            if metodo_pago == 'Crédito':
                cliente = Clientes.objects.get(pk=id_cliente_opcional)
                fecha_corte = timezone.now().date() + timedelta(days=30)
                
                # Tasa inicial por el favor de fiar (10% = 0.10)
                tasa_fianza = Decimal('0.10')
                interes_inicial = total_venta_calculado * tasa_fianza

                CuentasPorCobrar.objects.create(
                    id_venta=nueva_venta,
                    id_cliente=cliente,
                    capital_original=total_venta_calculado,
                    saldo_pendiente=total_venta_calculado,
                    interes_acumulado=interes_inicial, # <-- Se carga la deuda inmediatamente
                    fecha_vencimiento=fecha_corte,
                    estado='Pendiente'
                )

        return Response({
            'mensaje': 'Venta procesada con éxito', 
            'id_venta': nueva_venta.id_venta,
            'total': total_venta_calculado
        }, status=status.HTTP_201_CREATED)

    except Productos.DoesNotExist:
        return Response({'error': 'Un producto del carrito no existe'}, status=status.HTTP_404_NOT_FOUND)
    except Clientes.DoesNotExist:
        return Response({'error': 'El cliente especificado no existe'}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': f'Error interno: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categorias.objects.all()
    serializer_class = CategoriaSerializer

class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Productos.objects.all()
    serializer_class = ProductoSerializer

class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Clientes.objects.all()
    serializer_class = ClienteSerializer