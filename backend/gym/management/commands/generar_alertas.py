from django.core.management.base import BaseCommand

from gym.alertas import generar_alertas
from gym.management.gimnasios import resolver_gimnasio
from gym.models import Gimnasio


class Command(BaseCommand):
    help = (
        "Pone al día los estados de las membresías y genera las alertas del centro "
        "de alertas (vencimientos, clientes inactivos, ingresos bajos, gastos sobre "
        "el límite y pagos pendientes). Conviene programarlo una vez al día."
    )

    def add_arguments(self, parser):
        parser.add_argument("--gimnasio", help="Código del gimnasio. Por defecto, todos.")

    def handle(self, *args, **options):
        if options.get("gimnasio"):
            gimnasios = [resolver_gimnasio(options["gimnasio"])]
        else:
            gimnasios = Gimnasio.objects.filter(is_active=True, deleted_at__isnull=True)
        for gimnasio in gimnasios:
            conteo = generar_alertas(gimnasio)
            resumen = ", ".join(f"{clave}: {valor}" for clave, valor in conteo.items())
            self.stdout.write(f"{gimnasio.nombre} - alertas nuevas ({resumen}).")
        self.stdout.write(self.style.SUCCESS("Alertas generadas."))
