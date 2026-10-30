from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from api_tienda.models import CuentasPorCobrar

class Command(BaseCommand):
    help = 'Calcula y suma el interés diario a las cuentas en mora'

    def handle(self, *args, **kwargs):
        hoy = timezone.now().date()
        
        # Filtramos las cuentas que no se han pagado y cuya fecha ya venció
        cuentas_mora = CuentasPorCobrar.objects.filter(
            estado='Pendiente', 
            fecha_vencimiento__lt=hoy
        )
        
        # Ejemplo: Tasa de interés de mora del 10% mensual (0.10 / 30 días)
        tasa_diaria = Decimal('0.10') / Decimal('30')
        cuentas_afectadas = 0

        for cuenta in cuentas_mora:
            interes_previo = cuenta.interes_acumulado if cuenta.interes_acumulado is not None else Decimal('0.00')
            saldo = cuenta.saldo_pendiente if cuenta.saldo_pendiente is not None else Decimal('0.00')
            
            if saldo > 0:
                # El interés se calcula sobre el capital que aún deben, no sobre la deuda original
                nuevo_interes_del_dia = saldo * tasa_diaria
                cuenta.interes_acumulado = interes_previo + nuevo_interes_del_dia
                cuenta.save()
                cuentas_afectadas += 1

        self.stdout.write(self.style.SUCCESS(f'Éxito: Se aplicó interés de mora a {cuentas_afectadas} cuentas el {hoy}.'))