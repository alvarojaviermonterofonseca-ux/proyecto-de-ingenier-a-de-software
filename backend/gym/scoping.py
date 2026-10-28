from .models import Cliente, ClienteEntrenador, ClienteTerapeuta, Rol, Usuario
from .permissions import es_administrador


def rol_principal(user):
    if not isinstance(user, Usuario):
        return None
    return getattr(getattr(user, "rol", None), "nombre", None)


def es_personal_django(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and not isinstance(user, Usuario)
        and getattr(user, "is_staff", False)
    )


def _clientes_asignados(usuario, relacion, perfil):
    filtro = {
        f"{relacion}__activo": True,
        f"{relacion}__is_active": True,
        f"{relacion}__deleted_at__isnull": True,
        f"{relacion}__{perfil}__is_active": True,
        f"{relacion}__{perfil}__deleted_at__isnull": True,
        f"{relacion}__{perfil}__usuario__is_active": True,
        "is_active": True,
        "deleted_at__isnull": True,
        f"{relacion}__{perfil}_id": usuario.pk,
    }
    return Cliente.objects.filter(**filtro)


def clientes_clinicos(user):
    if es_administrador(user) or es_personal_django(user):
        return Cliente.objects.all()
    if not isinstance(user, Usuario):
        return Cliente.objects.none()
    rol = rol_principal(user)
    if rol == Rol.Nombre.CLIENTE:
        return Cliente.objects.filter(pk=user.pk)
    if rol == Rol.Nombre.ENTRENADOR:
        return _clientes_asignados(user, "asignaciones_entrenador", "entrenador")
    if rol == Rol.Nombre.TERAPEUTA:
        return _clientes_asignados(user, "asignaciones_terapeuta", "terapeuta")
    return Cliente.objects.none()


def clientes_operativos(user):
    if es_administrador(user) or es_personal_django(user):
        return Cliente.objects.all()
    if rol_principal(user) == Rol.Nombre.RECEPCIONISTA:
        return Cliente.objects.all()
    return clientes_clinicos(user)


def usuarios_visibles(user):
    if es_administrador(user) or es_personal_django(user):
        return Usuario.objects.all()
    if not isinstance(user, Usuario):
        return Usuario.objects.none()
    if rol_principal(user) == Rol.Nombre.RECEPCIONISTA:
        return Usuario.objects.filter(
            rol__nombre__in=(
                Rol.Nombre.CLIENTE,
                Rol.Nombre.ENTRENADOR,
                Rol.Nombre.RECEPCIONISTA,
            )
        )
    return Usuario.objects.filter(pk=user.pk)


def filtrar_clientes(queryset, campo, user, operativo=False):
    clientes = clientes_operativos(user) if operativo else clientes_clinicos(user)
    return queryset.filter(**{f"{campo}__in": clientes.values("pk")})


def filtrar_asignaciones_entrenador(queryset, user):
    if es_administrador(user) or es_personal_django(user):
        return queryset
    if not isinstance(user, Usuario):
        return queryset.none()
    rol = rol_principal(user)
    if rol == Rol.Nombre.ENTRENADOR:
        return queryset.filter(entrenador_id=user.pk)
    if rol == Rol.Nombre.CLIENTE:
        return queryset.filter(cliente_id=user.pk)
    return queryset.none()


def filtrar_asignaciones_terapeuta(queryset, user):
    if es_administrador(user) or es_personal_django(user):
        return queryset
    if not isinstance(user, Usuario):
        return queryset.none()
    rol = rol_principal(user)
    if rol == Rol.Nombre.TERAPEUTA:
        return queryset.filter(terapeuta_id=user.pk)
    if rol == Rol.Nombre.CLIENTE:
        return queryset.filter(cliente_id=user.pk)
    return queryset.none()


def filtrar_perfil(queryset, user, nombre_perfil):
    if es_administrador(user) or es_personal_django(user):
        return queryset
    if not isinstance(user, Usuario):
        return queryset.none()
    if rol_principal(user) == nombre_perfil:
        return queryset.filter(pk=user.pk)
    if nombre_perfil == Rol.Nombre.TERAPEUTA and rol_principal(user) == Rol.Nombre.CLIENTE:
        return queryset.filter(
            asignaciones_cliente__cliente_id=user.pk,
            asignaciones_cliente__activo=True,
            asignaciones_cliente__is_active=True,
            asignaciones_cliente__deleted_at__isnull=True,
        ).distinct()
    return queryset.none()
