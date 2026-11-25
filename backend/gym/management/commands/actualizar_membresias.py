from django.core.management.base import BaseCommand

from gym.models import Alerta, Membresia


class Command(BaseCommand):
    help = (
        "Actualiza el estado de las membresías según su fecha de fin "
        "(activa, por vencer o vencida) y crea las alertas que falten. "
        "Conviene programarlo una vez al día."
    )

    def handle(self, *args, **options):
        cambios = Membresia.sincronizar_estados()
        alertas = Alerta.generar_de_membresias()
        self.stdout.write(
            self.style.SUCCESS(
                "Membresías actualizadas - "
                f"vencidas: {cambios['vencidas']}, "
                f"por vencer: {cambios['por_vencer']}, "
                f"activas: {cambios['activas']}. "
                f"Alertas nuevas: {alertas}."
            )
        )
