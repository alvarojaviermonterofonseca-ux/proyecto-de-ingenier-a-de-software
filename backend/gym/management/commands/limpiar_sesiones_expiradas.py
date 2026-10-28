from django.core.management.base import BaseCommand
from django.utils import timezone

from gym.models import Sesion


class Command(BaseCommand):
    help = "Elimina las sesiones Bearer que ya expiraron."

    def handle(self, *args, **options):
        cantidad, _ = Sesion.objects.filter(expira_at__lte=timezone.now()).delete()
        self.stdout.write(
            self.style.SUCCESS(f"Sesiones expiradas eliminadas: {cantidad}.")
        )
