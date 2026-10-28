"""Almacenamiento privado para archivos sensibles."""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.functional import cached_property


class AlmacenamientoFotosPrivadas(FileSystemStorage):
    """Guarda archivos fuera de la carpeta estática y sin URL pública.

    La ubicación se lee dinámicamente de ``PRIVATE_MEDIA_ROOT`` para que las
    pruebas puedan aislar sus archivos y para permitir cambiarla por entorno.
    """

    def __init__(self):
        super().__init__(base_url=None)

    @cached_property
    def base_location(self):
        return os.path.abspath(settings.PRIVATE_MEDIA_ROOT)

    def _clear_cached_properties(self, setting, **kwargs):
        if setting == "PRIVATE_MEDIA_ROOT":
            self.__dict__.pop("base_location", None)
            self.__dict__.pop("location", None)
        super()._clear_cached_properties(setting, **kwargs)

    def url(self, name):
        raise ValueError(
            "Las fotos privadas solo se sirven mediante el endpoint autenticado "
            "de la API."
        )
