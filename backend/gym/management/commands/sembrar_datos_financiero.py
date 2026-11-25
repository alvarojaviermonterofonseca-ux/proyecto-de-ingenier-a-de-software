"""Siembra los métodos de pago y categorías de gasto por defecto de cada gimnasio."""

from django.core.management.base import BaseCommand
from django.db import transaction

from gym.management.gimnasios import resolver_gimnasio
from gym.models import (
    CATEGORIAS_GASTO_POR_DEFECTO,
    METODOS_PAGO_POR_DEFECTO,
    CategoriaGasto,
    Gimnasio,
    MetodoPago,
)


class Command(BaseCommand):
    help = (
        "Crea los métodos de pago y categorías de gasto por defecto que falten. "
        "Sin --gimnasio recorre todos los gimnasios activos. Es idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument("--gimnasio", help="Código del gimnasio. Por defecto, todos.")

    def handle(self, *args, **options):
        if options.get("gimnasio"):
            gimnasios = [resolver_gimnasio(options["gimnasio"])]
        else:
            gimnasios = list(Gimnasio.objects.filter(is_active=True, deleted_at__isnull=True))

        with transaction.atomic():
            for gimnasio in gimnasios:
                creados = 0
                for datos in METODOS_PAGO_POR_DEFECTO:
                    _, nuevo = MetodoPago.objects.get_or_create(
                        gimnasio=gimnasio, nombre=datos["nombre"], defaults=dict(datos)
                    )
                    creados += nuevo
                for datos in CATEGORIAS_GASTO_POR_DEFECTO:
                    _, nuevo = CategoriaGasto.objects.get_or_create(
                        gimnasio=gimnasio, nombre=datos["nombre"], defaults=dict(datos)
                    )
                    creados += nuevo
                self.stdout.write(f"{gimnasio.nombre}: {creados} registros nuevos.")

        self.stdout.write(self.style.SUCCESS("Datos financieros iniciales sembrados correctamente."))
