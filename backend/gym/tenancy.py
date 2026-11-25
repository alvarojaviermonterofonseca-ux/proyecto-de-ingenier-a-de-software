"""Aislamiento de datos entre gimnasios (multi-tenant).

Gym Control Pro atiende varios gimnasios en una sola base de datos. Cada
usuario pertenece a un gimnasio y solo puede ver y modificar los datos de ese
gimnasio. El gimnasio **siempre** se toma del usuario autenticado en el
servidor; nunca de un ``gimnasio`` o ``gym_id`` enviado por el cliente.

``RUTA_GIMNASIO`` dice, para cada modelo, por qué relación llega a su
gimnasio. ``filtrar_por_gimnasio`` es el único punto que aplica ese filtro y lo
usan las vistas, los serializers (para las claves foráneas) y el alcance de
datos. Un modelo que no figure aquí ni en ``MODELOS_GLOBALES`` hace fallar la
consulta en vez de devolver datos de todos los gimnasios.
"""

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q

from .models import Usuario

RUTA_GIMNASIO = {
    "Usuario": "gimnasio",
    "Cliente": "usuario__gimnasio",
    "Entrenador": "usuario__gimnasio",
    "Terapeuta": "usuario__gimnasio",
    "Recepcionista": "usuario__gimnasio",
    "Administrador": "usuario__gimnasio",
    "UsuarioRol": "usuario__gimnasio",
    "Sesion": "usuario__gimnasio",
    "Notificacion": "usuario__gimnasio",
    "EventoAuditoria": "actor__gimnasio",
    "ClienteEntrenador": "cliente__usuario__gimnasio",
    "ClienteTerapeuta": "cliente__usuario__gimnasio",
    "Entrenamiento": "cliente__usuario__gimnasio",
    "PlanEntrenamiento": "cliente__usuario__gimnasio",
    "PlanAlimentacion": "cliente__usuario__gimnasio",
    "RegistroComida": "cliente__usuario__gimnasio",
    "PlanEntrenamientoEjercicio": "plan__cliente__usuario__gimnasio",
    "Comida": "plan_alimentacion__cliente__usuario__gimnasio",
    "Asistencia": "gimnasio",
    "Ejercicio": "gimnasio",
    "MetodoPago": "gimnasio",
    "CategoriaGasto": "gimnasio",
    "Pago": "gimnasio",
    "Gasto": "gimnasio",
    "Membresia": "gimnasio",
    "Alerta": "gimnasio",
    "RolPermiso": "gimnasio",
    "RolRecurso": "gimnasio",
}

# Catálogos de la plataforma, iguales para todos los gimnasios. Solo los
# modifica el personal de la plataforma.
MODELOS_GLOBALES = {"Gimnasio", "Recurso", "Permiso"}

# Roles: los del sistema (sin gimnasio) se comparten; los personalizados son
# del gimnasio que los creó.
MODELOS_COMPARTIDOS = {"Rol"}


def es_plataforma(user):
    """Personal de la plataforma: usuario de Django con ``is_staff``.

    Administra todos los gimnasios desde ``/admin/`` y no pertenece a ninguno.
    """
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and not isinstance(user, Usuario)
        and getattr(user, "is_staff", False)
    )


def gimnasio_id_de(user):
    """Gimnasio del usuario autenticado, o ``None`` si no tiene."""
    if isinstance(user, Usuario):
        return user.gimnasio_id
    return None


def ruta_gimnasio(modelo):
    nombre = modelo.__name__
    if nombre in RUTA_GIMNASIO:
        return RUTA_GIMNASIO[nombre]
    if nombre in MODELOS_GLOBALES or nombre in MODELOS_COMPARTIDOS:
        return None
    raise ImproperlyConfigured(
        f"El modelo {nombre} no declara cómo se aísla por gimnasio. "
        "Agréguelo a RUTA_GIMNASIO o a MODELOS_GLOBALES en gym/tenancy.py."
    )


def filtrar_por_gimnasio(queryset, user):
    """Restringe ``queryset`` al gimnasio de ``user``.

    El personal de la plataforma ve todos los gimnasios. Cualquier otro actor
    sin gimnasio no ve nada.
    """
    modelo = queryset.model
    ruta = ruta_gimnasio(modelo)
    if modelo.__name__ in MODELOS_GLOBALES:
        return queryset
    if es_plataforma(user):
        return queryset
    gimnasio_id = gimnasio_id_de(user)
    if not gimnasio_id:
        return queryset.none()
    if modelo.__name__ in MODELOS_COMPARTIDOS:
        return queryset.filter(Q(gimnasio__isnull=True) | Q(gimnasio_id=gimnasio_id))
    return queryset.filter(**{ruta: gimnasio_id})


def pertenece_al_gimnasio(objeto, user):
    """Indica si un objeto ya cargado es visible para ``user``."""
    if objeto is None:
        return True
    modelo = type(objeto)
    return filtrar_por_gimnasio(modelo._default_manager.filter(pk=objeto.pk), user).exists()
