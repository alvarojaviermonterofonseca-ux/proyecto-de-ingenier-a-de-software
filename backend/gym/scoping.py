from .models import Cliente, ClienteEntrenador, ClienteTerapeuta, Rol, Usuario
from .permissions import es_administrador


def rol_principal(user):
    if not isinstance(user, Usuario):
        return None
    return getattr(getattr(user, "rol", None), "nombre", None)


def roles_efectivos_nombres(user):
    """Nombres de todos los roles activos del usuario (principal y adicionales).

    El alcance de datos se construye con la unión de estos roles, igual que los
    permisos efectivos. Así, conceder un rol adicional no solo habilita las
    acciones: también abre los datos que ese rol puede ver.
    """
    if not isinstance(user, Usuario) or not user.pk:
        return set()
    return set(user.roles_efectivos().values_list("nombre", flat=True))


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
    roles = roles_efectivos_nombres(user)
    permitidos = Cliente.objects.none()
    if Rol.Nombre.CLIENTE in roles:
        permitidos |= Cliente.objects.filter(pk=user.pk)
    if Rol.Nombre.ENTRENADOR in roles:
        permitidos |= _clientes_asignados(
            user, "asignaciones_entrenador", "entrenador"
        )
    if Rol.Nombre.TERAPEUTA in roles:
        permitidos |= _clientes_asignados(
            user, "asignaciones_terapeuta", "terapeuta"
        )
    return permitidos.distinct()


def clientes_operativos(user):
    if es_administrador(user) or es_personal_django(user):
        return Cliente.objects.all()
    if Rol.Nombre.RECEPCIONISTA in roles_efectivos_nombres(user):
        return Cliente.objects.all()
    return clientes_clinicos(user)


def usuarios_visibles(user):
    if es_administrador(user) or es_personal_django(user):
        return Usuario.objects.all()
    if not isinstance(user, Usuario):
        return Usuario.objects.none()
    visibles = Usuario.objects.filter(pk=user.pk)
    if Rol.Nombre.RECEPCIONISTA in roles_efectivos_nombres(user):
        visibles |= Usuario.objects.filter(
            rol__nombre__in=(
                Rol.Nombre.CLIENTE,
                Rol.Nombre.ENTRENADOR,
                Rol.Nombre.RECEPCIONISTA,
            )
        )
    return visibles.distinct()


def filtrar_clientes(queryset, campo, user, operativo=False):
    clientes = clientes_operativos(user) if operativo else clientes_clinicos(user)
    return queryset.filter(**{f"{campo}__in": clientes.values("pk")})


def filtrar_asignaciones_entrenador(queryset, user):
    if es_administrador(user) or es_personal_django(user):
        return queryset
    if not isinstance(user, Usuario):
        return queryset.none()
    roles = roles_efectivos_nombres(user)
    visibles = queryset.none()
    if Rol.Nombre.ENTRENADOR in roles:
        visibles |= queryset.filter(entrenador_id=user.pk)
    if Rol.Nombre.CLIENTE in roles:
        visibles |= queryset.filter(cliente_id=user.pk)
    return visibles.distinct()


def filtrar_asignaciones_terapeuta(queryset, user):
    if es_administrador(user) or es_personal_django(user):
        return queryset
    if not isinstance(user, Usuario):
        return queryset.none()
    roles = roles_efectivos_nombres(user)
    visibles = queryset.none()
    if Rol.Nombre.TERAPEUTA in roles:
        visibles |= queryset.filter(terapeuta_id=user.pk)
    if Rol.Nombre.CLIENTE in roles:
        visibles |= queryset.filter(cliente_id=user.pk)
    return visibles.distinct()


def filtrar_perfil(queryset, user, nombre_perfil):
    if es_administrador(user) or es_personal_django(user):
        return queryset
    if not isinstance(user, Usuario):
        return queryset.none()
    roles = roles_efectivos_nombres(user)
    if nombre_perfil in roles:
        return queryset.filter(pk=user.pk)
    if (
        nombre_perfil == Rol.Nombre.TERAPEUTA
        and Rol.Nombre.CLIENTE in roles
    ):
        return queryset.filter(
            asignaciones_cliente__cliente_id=user.pk,
            asignaciones_cliente__activo=True,
            asignaciones_cliente__is_active=True,
            asignaciones_cliente__deleted_at__isnull=True,
        ).distinct()
    return queryset.none()
