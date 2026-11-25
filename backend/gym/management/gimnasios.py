"""Utilidades de los comandos de gestión para elegir el gimnasio."""

from django.core.management.base import CommandError

from gym.models import Gimnasio


def resolver_gimnasio(codigo=None):
    """Gimnasio por código o, si se omite, el único activo de la plataforma."""
    activos = Gimnasio.objects.filter(is_active=True, deleted_at__isnull=True)
    if codigo:
        gimnasio = activos.filter(codigo=codigo.strip().lower()).first()
        if gimnasio is None:
            raise CommandError(f"No existe un gimnasio activo con el código '{codigo}'.")
        return gimnasio
    gimnasios = list(activos[:2])
    if len(gimnasios) == 1:
        return gimnasios[0]
    if not gimnasios:
        raise CommandError("No hay gimnasios activos. Cree uno con 'crear_gimnasio'.")
    raise CommandError("Hay varios gimnasios: indique cuál con --gimnasio <codigo>.")
