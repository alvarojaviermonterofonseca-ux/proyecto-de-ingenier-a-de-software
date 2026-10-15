"""Comando de arranque para crear la primera cuenta con acceso a la API."""

from getpass import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from gym.models import Administrador, Rol, Usuario


class Command(BaseCommand):
    help = "Crea una cuenta de administrador inicial para Gym Control Pro."

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True, help="Nombre visible de la persona administradora.")
        parser.add_argument("--correo", required=True, help="Correo para iniciar sesión.")
        parser.add_argument("--username", help="Nombre de usuario opcional.")
        parser.add_argument("--contrasena", help="Contraseña. Si se omite, se solicitará de forma oculta.")

    def handle(self, *args, **options):
        contrasena = options["contrasena"]
        if not contrasena:
            contrasena = getpass("Contraseña: ")
            confirmacion = getpass("Repita la contraseña: ")
            if contrasena != confirmacion:
                raise CommandError("Las contraseñas no coinciden.")

        if len(contrasena) < 8:
            raise CommandError("La contraseña debe tener al menos 8 caracteres.")

        if Usuario.objects.filter(correo__iexact=options["correo"]).exists():
            raise CommandError("Ya existe un usuario con ese correo.")
        if options["username"] and Usuario.objects.filter(username=options["username"]).exists():
            raise CommandError("Ya existe un usuario con ese username.")

        rol = Rol.objects.filter(nombre=Rol.Nombre.ADMINISTRADOR, is_active=True).first()
        if rol is None:
            raise CommandError("No existe el rol administrador. Ejecute primero las migraciones.")

        with transaction.atomic():
            usuario = Usuario(
                rol=rol,
                nombre=options["nombre"],
                correo=options["correo"],
                username=options["username"],
            )
            usuario.set_password(contrasena)
            usuario.full_clean()
            usuario.save()
            Administrador.objects.create(
                usuario=usuario,
                nivel_permisos=Administrador.NivelPermisos.TOTAL,
            )

        self.stdout.write(self.style.SUCCESS(f"Administrador creado para {usuario.correo}."))
