"""Autorización RBAC basada en la base de datos.

Cada ViewSet declara el recurso que protege (``recurso_permiso``) y la acción
se deduce del método HTTP o de ``accion_permiso`` para acciones personalizadas.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Rol, Usuario

ACCION_POR_METODO = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "create",
    "PUT": "edit",
    "PATCH": "edit",
    "DELETE": "delete",
}


def es_administrador(user):
    """Indica si el usuario puede administrar identidad, roles y permisos.

    Basta con que el usuario tenga el rol ``administrador`` entre sus roles
    efectivos (principal o adicional). Así, cuando un administrador concede
    todos los roles a otra cuenta, esa cuenta recibe el mismo control. El
    personal de Django conserva el acceso de solo lectura/escritura de staff.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not isinstance(user, Usuario):
        return bool(getattr(user, "is_staff", False))
    return user.roles_efectivos().filter(nombre=Rol.Nombre.ADMINISTRADOR).exists()


class TienePermisoRecurso(BasePermission):
    """Deny-by-default para usuarios propios; el staff de Django conserva acceso."""

    mensaje = "No tienes permiso para realizar esta operación."

    def _accion(self, request, view):
        accion = getattr(view, "accion_permiso", None)
        if accion:
            return accion
        por_accion = getattr(view, "accion_permiso_por_accion", None) or {}
        accion = por_accion.get(getattr(view, "action", None))
        if accion:
            return accion
        return ACCION_POR_METODO.get(request.method, "view")

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False

        if not isinstance(user, Usuario):
            return bool(getattr(user, "is_staff", False))

        recurso = getattr(view, "recurso_permiso", None)
        if not recurso:
            return True

        accion = self._accion(request, view)
        return user.tiene_permiso(f"{recurso}:{accion}")

    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if es_administrador(user):
            return True
        if not isinstance(user, Usuario):
            return False

        recurso = getattr(view, "recurso_permiso", None)
        if recurso and not user.tiene_permiso(
            f"{recurso}:{self._accion(request, view)}"
        ):
            return False

        verificador = getattr(view, "objeto_permitido", None)
        if not callable(verificador):
            return True
        return verificador(request, obj)


class SoloAdministradorParaEscritura(BasePermission):
    """Permite consultar, pero reserva las mutaciones al rol administrador."""

    mensaje = "Solo un administrador puede modificar asignaciones de roles o permisos."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return es_administrador(getattr(request, "user", None))


class SoloAdministrador(BasePermission):
    mensaje = "Solo un administrador puede consultar o modificar este recurso."

    def has_permission(self, request, view):
        return es_administrador(getattr(request, "user", None))
