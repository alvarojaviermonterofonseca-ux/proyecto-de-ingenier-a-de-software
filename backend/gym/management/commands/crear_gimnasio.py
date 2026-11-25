"""Da de alta un gimnasio nuevo en la plataforma (uso del personal de la plataforma)."""

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from gym.models import Gimnasio


class Command(BaseCommand):
    help = (
        "Crea un gimnasio con sus métodos de pago, categorías de gasto y matriz de "
        "permisos. Con --admin-correo crea también su primer administrador."
    )

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True, help="Nombre comercial del gimnasio.")
        parser.add_argument("--codigo", help="Código corto y único (por defecto, a partir del nombre).")
        parser.add_argument("--ciudad")
        parser.add_argument("--nit")
        parser.add_argument("--admin-nombre", help="Nombre del primer administrador.")
        parser.add_argument("--admin-correo", help="Correo del primer administrador.")
        parser.add_argument("--admin-contrasena", help="Contraseña; si se omite se pide de forma oculta.")

    def handle(self, *args, **options):
        codigo = slugify(options["codigo"] or options["nombre"])[:50]
        if not codigo:
            raise CommandError("No se pudo generar un código válido; indíquelo con --codigo.")
        if Gimnasio.objects.filter(codigo=codigo).exists():
            raise CommandError(f"Ya existe un gimnasio con el código '{codigo}'.")
        if options["admin_correo"] and not options["admin_nombre"]:
            raise CommandError("Indique también --admin-nombre.")

        with transaction.atomic():
            gimnasio = Gimnasio(
                nombre=options["nombre"],
                codigo=codigo,
                ciudad=options["ciudad"],
                nit=options["nit"],
            )
            try:
                gimnasio.full_clean()
            except ValidationError as error:
                raise CommandError(error.message_dict) from error
            gimnasio.save()
            if options["admin_correo"]:
                argumentos = {
                    "nombre": options["admin_nombre"],
                    "correo": options["admin_correo"],
                    "gimnasio": codigo,
                }
                if options["admin_contrasena"]:
                    argumentos["contrasena"] = options["admin_contrasena"]
                call_command("crear_administrador_gym", stdout=self.stdout, **argumentos)

        self.stdout.write(
            self.style.SUCCESS(
                f"Gimnasio '{gimnasio.nombre}' creado con el código '{gimnasio.codigo}'."
            )
        )
