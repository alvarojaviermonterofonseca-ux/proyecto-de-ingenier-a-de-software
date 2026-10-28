"""Autenticación Bearer para el modelo de identidad propio del proyecto."""

from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

from gym.models import Sesion


class UsuarioTokenAuthentication(authentication.BaseAuthentication):
    """Resuelve ``Authorization: Bearer <token>`` a una sesión vigente."""

    keyword = "bearer"

    def authenticate(self, request):
        authorization = request.META.get("HTTP_AUTHORIZATION", "")
        if not authorization:
            return None

        partes = authorization.split()
        if len(partes) != 2 or partes[0].lower() != self.keyword or not partes[1]:
            raise AuthenticationFailed("El encabezado Authorization debe usar el formato Bearer <token>.")

        sesion = (
            Sesion.objects.select_related("usuario__rol")
            .filter(token_hash=Sesion.hash_token(partes[1]), expira_at__gt=timezone.now())
            .first()
        )
        if sesion is None:
            raise AuthenticationFailed("El token no es válido o ya expiró.")

        usuario = sesion.usuario
        if not usuario.is_active or usuario.deleted_at is not None or not usuario.rol.is_active:
            raise AuthenticationFailed("La cuenta no está disponible.")

        return usuario, sesion

    def authenticate_header(self, request):
        return "Bearer"


class AdminSessionAuthentication(authentication.SessionAuthentication):
    """Acepta una sesión web de Django únicamente para el personal admin."""

    def authenticate(self, request):
        resultado = super().authenticate(request)
        if resultado is None:
            return None

        usuario, autenticacion = resultado
        if not usuario.is_staff or not usuario.is_superuser:
            return None
        return usuario, autenticacion


class UsuarioTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "config.authentication.UsuarioTokenAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer"}


class AdminSessionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "config.authentication.AdminSessionAuthentication"
    name = "AdminSession"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "sessionid"}
