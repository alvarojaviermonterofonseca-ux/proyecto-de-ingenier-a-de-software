"""Serializers de la API.

Las contraseñas se reciben exclusivamente como ``contrasena`` y se convierten
en un hash; ``contrasena_hash`` nunca forma parte de una respuesta JSON.
"""

from copy import copy

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.urls import reverse
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from .models import (
    Administrador,
    Asistencia,
    Cliente,
    ClienteEntrenador,
    ClienteTerapeuta,
    Comida,
    Ejercicio,
    Entrenador,
    Entrenamiento,
    EventoAuditoria,
    Notificacion,
    Permiso,
    PlanAlimentacion,
    PlanEntrenamiento,
    PlanEntrenamientoEjercicio,
    Recepcionista,
    RegistroComida,
    Rol,
    RolPermiso,
    Terapeuta,
    Usuario,
    UsuarioRol,
    normalizar_correo,
)
from .permissions import es_administrador


class SerializerVacio(serializers.Serializer):
    pass


class LoginFailed(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Correo o contraseña incorrectos."
    default_code = "authentication_failed"


class SeguridadEscrituraMixin:
    """Reglas de escritura que no dependen de una tabla concreta."""

    def _actor(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def _validar_campos_sensibles(self, attrs):
        if "is_active" in attrs and not es_administrador(self._actor()):
            raise serializers.ValidationError(
                {"is_active": "Solo un administrador puede cambiar el estado de activación."}
            )

    def _validar_relaciones_inmutables(self, attrs):
        """Impide que un no administrador mueva un registro entre entidades."""
        if self.instance is None or es_administrador(self._actor()):
            return

        modelo = self.Meta.model
        for campo, valor in attrs.items():
            try:
                field = modelo._meta.get_field(campo)
            except FieldDoesNotExist:
                continue
            if not (field.is_relation and field.concrete and not field.many_to_many):
                continue
            actual = getattr(self.instance, field.attname)
            nuevo = getattr(valor, "pk", valor)
            if actual != nuevo:
                raise serializers.ValidationError(
                    {
                        campo: (
                            "Solo un administrador puede cambiar las relaciones "
                            "de un registro existente."
                        )
                    }
                )


class ModeloValidadoSerializer(SeguridadEscrituraMixin, serializers.ModelSerializer):
    """Ejecuta ``clean`` y las restricciones del modelo antes de guardar."""

    def validate(self, attrs):
        self._validar_campos_sensibles(attrs)
        self._validar_relaciones_inmutables(attrs)

        model = self.Meta.model
        if self.instance is None:
            candidato = model()
        else:
            # No se modifica la instancia que está siendo serializada durante is_valid().
            candidato = copy(self.instance)

        for atributo, valor in attrs.items():
            setattr(candidato, atributo, valor)

        try:
            candidato.full_clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        return attrs


class PermisoSerializer(ModeloValidadoSerializer):
    class Meta:
        model = Permiso
        fields = (
            "id",
            "codigo",
            "recurso",
            "accion",
            "descripcion",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "codigo", "created_at", "updated_at")


class RolSerializer(ModeloValidadoSerializer):
    permisos = serializers.SerializerMethodField()
    permisos_detalle = serializers.SerializerMethodField()
    total_usuarios = serializers.SerializerMethodField()

    class Meta:
        model = Rol
        fields = (
            "id",
            "nombre",
            "descripcion",
            "is_active",
            "created_at",
            "updated_at",
            "permisos",
            "permisos_detalle",
            "total_usuarios",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "permisos",
            "permisos_detalle",
            "total_usuarios",
        )

    def get_permisos(self, rol):
        return sorted(
            rol.permisos_asignados.filter(permiso__is_active=True).values_list("permiso__codigo", flat=True)
        )

    def get_permisos_detalle(self, rol):
        permisos = [asignacion.permiso for asignacion in rol.permisos_asignados.all() if asignacion.permiso.is_active]
        permisos.sort(key=lambda permiso: permiso.codigo)
        return PermisoSerializer(permisos, many=True).data

    def get_total_usuarios(self, rol):
        return rol.asignaciones_usuarios.filter(activo=True).values("usuario_id").distinct().count()


class RolPermisoSerializer(ModeloValidadoSerializer):
    rol_nombre = serializers.CharField(source="rol.nombre", read_only=True)
    permiso_codigo = serializers.CharField(source="permiso.codigo", read_only=True)

    class Meta:
        model = RolPermiso
        fields = ("id", "rol", "rol_nombre", "permiso", "permiso_codigo", "created_at")
        read_only_fields = ("id", "rol_nombre", "permiso_codigo", "created_at")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        permiso = attrs.get("permiso", self.instance.permiso if self.instance else None)
        if permiso is not None and not permiso.is_active:
            raise serializers.ValidationError({"permiso": "Solo puede asignar permisos activos."})
        return attrs


class UsuarioRolSerializer(ModeloValidadoSerializer):
    usuario_nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    rol_nombre = serializers.CharField(source="rol.nombre", read_only=True)
    asignado_por_nombre = serializers.CharField(source="asignado_por.nombre", read_only=True)

    class Meta:
        model = UsuarioRol
        fields = (
            "id",
            "usuario",
            "rol",
            "usuario_nombre",
            "rol_nombre",
            "activo",
            "asignado_por",
            "asignado_por_nombre",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "usuario_nombre",
            "rol_nombre",
            "asignado_por",
            "asignado_por_nombre",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        rol = attrs.get("rol", self.instance.rol if self.instance else None)
        if rol is not None and not rol.is_active:
            raise serializers.ValidationError({"rol": "Solo puede asignar roles activos."})
        usuario = attrs.get("usuario", self.instance.usuario if self.instance else None)
        if usuario is not None and not usuario.is_active:
            raise serializers.ValidationError({"usuario": "No puede asignar roles a un usuario inactivo."})
        return attrs


class UsuarioResumenSerializer(serializers.ModelSerializer):
    rol_nombre = serializers.CharField(source="rol.nombre", read_only=True)

    class Meta:
        model = Usuario
        fields = ("id", "nombre", "correo", "username", "telefono", "rol", "rol_nombre", "is_active")
        read_only_fields = fields


class ClienteResumenSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    correo = serializers.EmailField(source="usuario.correo", read_only=True)

    class Meta:
        model = Cliente
        fields = ("usuario", "nombre", "correo")
        read_only_fields = fields


class EntrenadorResumenSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    correo = serializers.EmailField(source="usuario.correo", read_only=True)

    class Meta:
        model = Entrenador
        fields = ("usuario", "nombre", "correo", "especialidad")
        read_only_fields = fields


class TerapeutaResumenSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    correo = serializers.EmailField(source="usuario.correo", read_only=True)

    class Meta:
        model = Terapeuta
        fields = ("usuario", "nombre", "correo", "especialidad")
        read_only_fields = fields


class ClientePerfilResumenSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    correo = serializers.EmailField(source="usuario.correo", read_only=True)

    class Meta:
        model = Cliente
        fields = ("usuario", "nombre", "correo", "objetivo")
        read_only_fields = fields


class EntrenadorPerfilResumenSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    correo = serializers.EmailField(source="usuario.correo", read_only=True)

    class Meta:
        model = Entrenador
        fields = ("usuario", "nombre", "correo", "especialidad")
        read_only_fields = fields


class TerapeutaPerfilResumenSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    correo = serializers.EmailField(source="usuario.correo", read_only=True)

    class Meta:
        model = Terapeuta
        fields = ("usuario", "nombre", "correo", "especialidad")
        read_only_fields = fields


class RecepcionistaPerfilResumenSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    correo = serializers.EmailField(source="usuario.correo", read_only=True)

    class Meta:
        model = Recepcionista
        fields = ("usuario", "nombre", "correo", "turno_preferido")
        read_only_fields = fields


class AdministradorPerfilResumenSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="usuario.nombre", read_only=True)
    correo = serializers.EmailField(source="usuario.correo", read_only=True)

    class Meta:
        model = Administrador
        fields = ("usuario", "nombre", "correo", "cargo")
        read_only_fields = fields


class PerfilSerializerBase(ModeloValidadoSerializer):
    usuario_detalle = UsuarioResumenSerializer(source="usuario", read_only=True)

    class Meta:
        abstract = True
        read_only_fields = ("created_at", "updated_at", "deleted_at")

    def get_fields(self):
        fields = super().get_fields()
        if "usuario" in fields and (
            self.instance is not None
            or self.context.get("validando_perfil_sin_usuario")
        ):
            fields["usuario"].read_only = True
            fields["usuario"].required = False
        return fields

    def validate(self, attrs):
        if self.instance is None and self.context.get("validando_perfil_sin_usuario"):
            # Primera fase: valida tipos, obligatorios, únicos y check
            # constraints del perfil antes de crear el usuario. La relación
            # ``usuario`` se omite porque todavía no existe.
            candidato = self.Meta.model()
            for atributo, valor in attrs.items():
                setattr(candidato, atributo, valor)
            try:
                candidato.full_clean(exclude=["usuario"])
            except DjangoValidationError as error:
                raise serializers.ValidationError(error.message_dict) from error
            return attrs

        attrs = super().validate(attrs)
        if self.instance is not None and "usuario" in attrs:
            if attrs["usuario"].pk != self.instance.usuario_id:
                raise serializers.ValidationError(
                    {
                        "usuario": (
                            "No puede reasignar un perfil existente a otra persona. "
                            "Cree un perfil nuevo para el usuario destino."
                        )
                    }
                )
        return attrs


class ClienteSerializer(PerfilSerializerBase):
    class Meta(PerfilSerializerBase.Meta):
        model = Cliente
        fields = (
            "usuario",
            "usuario_detalle",
            "tipo_documento",
            "numero_documento",
            "fecha_nacimiento",
            "objetivo",
            "peso_kg",
            "estatura_cm",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = PerfilSerializerBase.Meta.read_only_fields


class ClienteOperativoSerializer(ClienteSerializer):
    class Meta(ClienteSerializer.Meta):
        fields = (
            "usuario",
            "usuario_detalle",
            "tipo_documento",
            "numero_documento",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ClienteSerializer.Meta.read_only_fields


class EventoAuditoriaSerializer(serializers.ModelSerializer):
    actor_nombre = serializers.CharField(source="actor.nombre", read_only=True)

    class Meta:
        model = EventoAuditoria
        fields = [
            "id",
            "actor",
            "actor_nombre",
            "accion",
            "recurso",
            "objeto_id",
            "detalles",
            "created_at",
        ]


class EntrenadorSerializer(PerfilSerializerBase):
    class Meta(PerfilSerializerBase.Meta):
        model = Entrenador
        fields = (
            "usuario",
            "usuario_detalle",
            "especialidad",
            "certificacion",
            "fecha_ingreso",
            "biografia",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = PerfilSerializerBase.Meta.read_only_fields


class AdministradorSerializer(PerfilSerializerBase):
    class Meta(PerfilSerializerBase.Meta):
        model = Administrador
        fields = (
            "usuario",
            "usuario_detalle",
            "cargo",
            "fecha_ingreso",
            "nivel_permisos",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = PerfilSerializerBase.Meta.read_only_fields


class TerapeutaSerializer(PerfilSerializerBase):
    class Meta(PerfilSerializerBase.Meta):
        model = Terapeuta
        fields = (
            "usuario",
            "usuario_detalle",
            "especialidad",
            "licencia_profesional",
            "fecha_ingreso",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = PerfilSerializerBase.Meta.read_only_fields


class RecepcionistaSerializer(PerfilSerializerBase):
    class Meta(PerfilSerializerBase.Meta):
        model = Recepcionista
        fields = (
            "usuario",
            "usuario_detalle",
            "fecha_ingreso",
            "turno_preferido",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = PerfilSerializerBase.Meta.read_only_fields


PERFIL_SERIALIZERS = {
    Rol.Nombre.CLIENTE: ClienteSerializer,
    Rol.Nombre.ENTRENADOR: EntrenadorSerializer,
    Rol.Nombre.TERAPEUTA: TerapeutaSerializer,
    Rol.Nombre.RECEPCIONISTA: RecepcionistaSerializer,
    Rol.Nombre.ADMINISTRADOR: AdministradorSerializer,
}


class ClientePerfilPropioSerializer(ClienteSerializer):
    class Meta(ClienteSerializer.Meta):
        read_only_fields = (
            *ClienteSerializer.Meta.read_only_fields,
            "usuario",
            "is_active",
        )


class EntrenadorPerfilPropioSerializer(EntrenadorSerializer):
    class Meta(EntrenadorSerializer.Meta):
        read_only_fields = (
            *EntrenadorSerializer.Meta.read_only_fields,
            "usuario",
            "fecha_ingreso",
            "is_active",
        )


class TerapeutaPerfilPropioSerializer(TerapeutaSerializer):
    class Meta(TerapeutaSerializer.Meta):
        read_only_fields = (
            *TerapeutaSerializer.Meta.read_only_fields,
            "usuario",
            "fecha_ingreso",
            "is_active",
        )


class RecepcionistaPerfilPropioSerializer(RecepcionistaSerializer):
    class Meta(RecepcionistaSerializer.Meta):
        read_only_fields = (
            *RecepcionistaSerializer.Meta.read_only_fields,
            "usuario",
            "fecha_ingreso",
            "is_active",
        )


class AdministradorPerfilPropioSerializer(AdministradorSerializer):
    class Meta(AdministradorSerializer.Meta):
        read_only_fields = (
            *AdministradorSerializer.Meta.read_only_fields,
            "usuario",
            "fecha_ingreso",
            "nivel_permisos",
            "is_active",
        )


PERFIL_PROPIO_SERIALIZERS = {
    Rol.Nombre.CLIENTE: ClientePerfilPropioSerializer,
    Rol.Nombre.ENTRENADOR: EntrenadorPerfilPropioSerializer,
    Rol.Nombre.TERAPEUTA: TerapeutaPerfilPropioSerializer,
    Rol.Nombre.RECEPCIONISTA: RecepcionistaPerfilPropioSerializer,
    Rol.Nombre.ADMINISTRADOR: AdministradorPerfilPropioSerializer,
}

PERFIL_RESUMEN_SERIALIZERS = {
    Rol.Nombre.CLIENTE: ClientePerfilResumenSerializer,
    Rol.Nombre.ENTRENADOR: EntrenadorPerfilResumenSerializer,
    Rol.Nombre.TERAPEUTA: TerapeutaPerfilResumenSerializer,
    Rol.Nombre.RECEPCIONISTA: RecepcionistaPerfilResumenSerializer,
    Rol.Nombre.ADMINISTRADOR: AdministradorPerfilResumenSerializer,
}


class PerfilPorRolField(serializers.Field):
    """Valida ``perfil`` con el serializer del rol indicado en la misma entrada."""

    default_error_messages = {
        "objeto": "El perfil debe ser un objeto.",
        "rol_sin_perfil": "Este rol no tiene un perfil predefinido; envíe un objeto vacío u omita el campo.",
    }

    def _rol_por_id(self, valor):
        if isinstance(valor, Rol):
            return valor
        try:
            return Rol.objects.filter(pk=valor).first()
        except (TypeError, ValueError):
            return None

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            self.fail("objeto")

        datos = getattr(self.parent, "initial_data", {}) or {}
        rol = self._rol_por_id(datos.get("rol"))
        if rol is None:
            # El campo ``rol`` reportará el error correspondiente.
            return data

        serializer_clase = PERFIL_SERIALIZERS.get(rol.nombre)
        if serializer_clase is None:
            if data:
                self.fail("rol_sin_perfil")
            return {}

        serializer = serializer_clase(
            context={
                **self.parent.context,
                "validando_perfil_sin_usuario": True,
            }
        )
        solo_lectura = {
            "usuario",
            "usuario_detalle",
            "created_at",
            "updated_at",
            "deleted_at",
        }
        permitidos = set(serializer.fields) - solo_lectura
        desconocidos = sorted(set(data) - permitidos)
        if desconocidos:
            raise serializers.ValidationError(
                f"Campos no permitidos en perfil: {', '.join(desconocidos)}."
            )

        serializer = serializer_clase(
            data=data,
            context={
                **self.parent.context,
                "validando_perfil_sin_usuario": True,
            },
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def to_representation(self, value):
        return value


class UsuarioRolesMixin:
    """Sincronización y validación de roles adicionales compartida."""

    def _asignado_por(self):
        request = self.context.get("request")
        usuario = getattr(request, "user", None)
        return usuario if isinstance(usuario, Usuario) else None

    def _sincronizar_roles(self, usuario, roles_ids):
        deseados = set(roles_ids or [])
        deseados.add(usuario.rol_id)
        existentes = {
            asignacion.rol_id: asignacion
            for asignacion in usuario.asignaciones_usuarios.all()
        }
        for rol_id in deseados:
            asignacion = existentes.get(rol_id)
            if asignacion is None:
                usuario.asignar_rol(
                    Rol.objects.get(pk=rol_id),
                    asignado_por=self._asignado_por(),
                    activo=True,
                )
            elif not asignacion.activo:
                asignacion.activo = True
                asignacion.asignado_por = self._asignado_por()
                asignacion.save(
                    update_fields=["activo", "asignado_por", "updated_at"]
                )
        for rol_id, asignacion in existentes.items():
            if rol_id not in deseados and asignacion.activo:
                asignacion.activo = False
                asignacion.save(update_fields=["activo", "updated_at"])

    def _validar_roles_asignados(self, attrs):
        if "roles_asignados" not in attrs:
            return
        ids = list(dict.fromkeys(attrs["roles_asignados"]))
        roles = list(Rol.objects.filter(pk__in=ids))
        if len(roles) != len(ids):
            raise serializers.ValidationError(
                {"roles_asignados": "Uno o más roles no existen."}
            )
        if any(not rol_item.is_active for rol_item in roles):
            raise serializers.ValidationError(
                {"roles_asignados": "Solo puede asignar roles activos."}
            )
        attrs["roles_asignados"] = ids


def validar_contrasena_django(contrasena, candidato):
    """Aplica ``AUTH_PASSWORD_VALIDATORS`` y devuelve errores DRF."""
    candidato.email = candidato.correo
    candidato.first_name = candidato.nombre
    try:
        validate_password(contrasena, candidato)
    except DjangoValidationError as error:
        raise serializers.ValidationError(
            {"contrasena": list(error.messages)}
        ) from error


def validar_modelo(candidato):
    try:
        candidato.full_clean()
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.message_dict) from error


def existe_otro_administrador_activo(usuario):
    return (
        Usuario.objects.filter(
            rol__nombre=Rol.Nombre.ADMINISTRADOR,
            is_active=True,
            deleted_at__isnull=True,
        )
        .exclude(pk=usuario.pk)
        .exists()
    )


class PerfilResumenMixin:
    def get_perfil_detalle(self, usuario):
        serializer_clase = PERFIL_RESUMEN_SERIALIZERS.get(usuario.rol.nombre)
        if serializer_clase is None:
            return None
        try:
            perfil = getattr(usuario, usuario.rol.nombre)
        except (
            Cliente.DoesNotExist,
            Entrenador.DoesNotExist,
            Terapeuta.DoesNotExist,
            Recepcionista.DoesNotExist,
            Administrador.DoesNotExist,
        ):
            return None
        return serializer_clase(perfil, context=self.context).data


class UsuarioReadSerializer(PerfilResumenMixin, serializers.ModelSerializer):
    """DTO de detalle: identidad pública, roles y perfil resumido."""

    rol_detalle = RolSerializer(source="rol", read_only=True)
    roles_detalle = serializers.SerializerMethodField(read_only=True)
    permisos = serializers.SerializerMethodField(read_only=True)
    perfil_detalle = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Usuario
        fields = (
            "id",
            "rol",
            "rol_detalle",
            "roles_detalle",
            "permisos",
            "nombre",
            "username",
            "correo",
            "telefono",
            "is_active",
            "created_at",
            "updated_at",
            "perfil_detalle",
        )
        read_only_fields = fields

    def get_roles_detalle(self, usuario):
        return RolSerializer(
            usuario.roles_efectivos(), many=True, context=self.context
        ).data

    def get_permisos(self, usuario):
        return sorted(usuario.permisos_efectivos())


class UsuarioListSerializer(PerfilResumenMixin, serializers.ModelSerializer):
    """DTO ligero para listados; incluye solo nombres de roles efectivos."""

    rol_nombre = serializers.CharField(source="rol.nombre", read_only=True)
    roles_efectivos = serializers.SerializerMethodField(read_only=True)
    perfil_detalle = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Usuario
        fields = (
            "id",
            "rol",
            "rol_nombre",
            "roles_efectivos",
            "nombre",
            "username",
            "correo",
            "telefono",
            "is_active",
            "perfil_detalle",
        )
        read_only_fields = fields

    def get_roles_efectivos(self, usuario):
        roles = {}
        for asignacion in usuario.asignaciones_usuarios.all():
            if asignacion.activo and asignacion.rol.is_active:
                roles[asignacion.rol_id] = asignacion.rol.nombre
        if usuario.rol.is_active:
            roles[usuario.rol_id] = usuario.rol.nombre
        return [
            {"id": rol_id, "nombre": roles[rol_id]}
            for rol_id in sorted(roles)
        ]


class UsuarioMeSerializer(UsuarioReadSerializer):
    """DTO estable de /api/me/ con roles y permisos efectivos."""

    roles_efectivos = serializers.SerializerMethodField(read_only=True)
    permisos_efectivos = serializers.SerializerMethodField(read_only=True)

    class Meta(UsuarioReadSerializer.Meta):
        fields = UsuarioReadSerializer.Meta.fields + (
            "roles_efectivos",
            "permisos_efectivos",
        )
        read_only_fields = fields

    def get_roles_efectivos(self, usuario):
        return self.get_roles_detalle(usuario)

    def get_permisos_efectivos(self, usuario):
        return self.get_permisos(usuario)


class UsuarioCreateSerializer(
    UsuarioRolesMixin, SeguridadEscrituraMixin, serializers.ModelSerializer
):
    """Alta atómica de usuario, roles adicionales y perfil tipado por rol."""

    contrasena = serializers.CharField(
        write_only=True, min_length=8, trim_whitespace=False
    )
    perfil = PerfilPorRolField(write_only=True, required=False)
    roles_asignados = serializers.ListField(
        child=serializers.IntegerField(min_value=1), write_only=True, required=False
    )

    class Meta:
        model = Usuario
        fields = (
            "rol",
            "nombre",
            "username",
            "correo",
            "contrasena",
            "telefono",
            "is_active",
            "roles_asignados",
            "perfil",
        )

    def validate(self, attrs):
        actor_admin = es_administrador(self._actor())
        self._validar_campos_sensibles(attrs)

        if not actor_admin:
            raise serializers.ValidationError(
                {"rol": "Solo un administrador puede crear usuarios y asignarles un rol."}
            )

        contrasena = attrs.get("contrasena")
        if not contrasena:
            raise serializers.ValidationError(
                {"contrasena": "La contraseña es obligatoria al crear un usuario."}
            )

        rol = attrs.get("rol")
        if rol is None or not rol.is_active:
            raise serializers.ValidationError(
                {"rol": "Solo puede asignar roles activos."}
            )

        perfil_requerido = rol.nombre in PERFIL_SERIALIZERS
        if perfil_requerido and "perfil" not in attrs:
            raise serializers.ValidationError(
                {
                    "perfil": (
                        "Debe incluir los datos del perfil correspondiente al rol "
                        "en la misma solicitud."
                    )
                }
            )
        if not perfil_requerido and attrs.get("perfil"):
            raise serializers.ValidationError(
                {
                    "perfil": (
                        "Este rol no tiene un perfil predefinido; envíe un objeto "
                        "vacío u omita el campo."
                    )
                }
            )

        self._validar_roles_asignados(attrs)

        # ``contrasena``, ``perfil`` y ``roles_asignados`` no son columnas del
        # modelo, por ello se excluyen de la validación genérica.
        datos_modelo = {
            clave: valor
            for clave, valor in attrs.items()
            if clave not in {"contrasena", "perfil", "roles_asignados"}
        }
        candidato = Usuario(**datos_modelo)
        candidato.set_password(contrasena)
        validar_modelo(candidato)
        validar_contrasena_django(contrasena, candidato)
        return attrs

    def create(self, validated_data):
        contrasena = validated_data.pop("contrasena")
        roles_ids = validated_data.pop("roles_asignados", [])
        datos_perfil = validated_data.pop("perfil", {})
        with transaction.atomic():
            usuario = Usuario(**validated_data)
            usuario.set_password(contrasena)
            usuario.save()
            self._sincronizar_roles(usuario, roles_ids)

            if usuario.rol.nombre in PERFIL_SERIALIZERS:
                modelo_perfil = PERFIL_SERIALIZERS[usuario.rol.nombre].Meta.model
                perfil = modelo_perfil(usuario=usuario, **datos_perfil)
                try:
                    perfil.full_clean()
                except DjangoValidationError as error:
                    raise serializers.ValidationError(
                        {"perfil": error.message_dict}
                    ) from error
                perfil.save()
        return usuario


class UsuarioUpdateSerializer(
    UsuarioRolesMixin, SeguridadEscrituraMixin, serializers.ModelSerializer
):
    """Edición de identidad sin perfil ni asignación de roles adicionales."""

    contrasena = serializers.CharField(
        write_only=True, min_length=8, trim_whitespace=False, required=False
    )

    class Meta:
        model = Usuario
        fields = (
            "rol",
            "nombre",
            "username",
            "correo",
            "contrasena",
            "telefono",
            "is_active",
        )

    def validate(self, attrs):
        if "roles_asignados" in getattr(self, "initial_data", {}):
            raise serializers.ValidationError(
                {
                    "roles_asignados": (
                        "Use PATCH /api/usuarios/{id}/roles/ para modificar "
                        "los roles adicionales."
                    )
                }
            )

        actor_admin = es_administrador(self._actor())
        self._validar_campos_sensibles(attrs)
        self._validar_relaciones_inmutables(attrs)

        if "rol" in attrs and not actor_admin:
            raise serializers.ValidationError(
                {"rol": "Solo un administrador puede cambiar el rol principal."}
            )

        if "contrasena" in attrs and not actor_admin:
            actor = self._actor()
            if not isinstance(actor, Usuario) or actor.pk != self.instance.pk:
                raise serializers.ValidationError(
                    {
                        "contrasena": (
                            "Solo puede cambiar su propia contraseña o un "
                            "administrador la de otro usuario."
                        )
                    }
                )

        rol = attrs.get("rol", self.instance.rol)
        if not rol.is_active:
            raise serializers.ValidationError(
                {"rol": "Solo puede asignar roles activos."}
            )

        if rol != self.instance.rol:
            for relacion in (
                "cliente",
                "entrenador",
                "terapeuta",
                "recepcionista",
                "administrador",
            ):
                if hasattr(self.instance, relacion):
                    raise serializers.ValidationError(
                        {
                            "rol": (
                                "No puede cambiar el rol de un usuario que ya "
                                "tiene un perfil asociado."
                            )
                        }
                    )

        if self.instance.rol.nombre == Rol.Nombre.ADMINISTRADOR:
            activo_nuevo = attrs.get("is_active", self.instance.is_active)
            sigue_siendo_admin = rol.nombre == Rol.Nombre.ADMINISTRADOR
            if (not sigue_siendo_admin or not activo_nuevo) and not existe_otro_administrador_activo(
                self.instance
            ):
                campo = "is_active" if sigue_siendo_admin else "rol"
                raise serializers.ValidationError(
                    {
                        campo: (
                            "No puede desactivar ni cambiar el rol del último "
                            "administrador activo."
                        )
                    }
                )

        datos_modelo = {
            clave: valor
            for clave, valor in attrs.items()
            if clave not in {"contrasena"}
        }
        candidato = copy(self.instance)
        for atributo, valor in datos_modelo.items():
            setattr(candidato, atributo, valor)
        if attrs.get("contrasena"):
            candidato.set_password(attrs["contrasena"])
        validar_modelo(candidato)

        if attrs.get("contrasena"):
            validar_contrasena_django(attrs["contrasena"], candidato)
        return attrs

    def update(self, instance, validated_data):
        contrasena = validated_data.pop("contrasena", None)
        desactivar = validated_data.get("is_active") is False
        with transaction.atomic():
            for atributo, valor in validated_data.items():
                setattr(instance, atributo, valor)
            if contrasena:
                instance.set_password(contrasena)
            instance.save()
            if contrasena or desactivar or "rol" in validated_data:
                instance.sesiones.all().delete()
            if "rol" in validated_data:
                self._sincronizar_roles(instance, None)
        return instance


class LoginSerializer(serializers.Serializer):
    correo = serializers.EmailField()
    contrasena = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        usuario = (
            Usuario.objects.select_related("rol")
            .filter(
                correo=normalizar_correo(attrs["correo"]),
                is_active=True,
                deleted_at__isnull=True,
                rol__is_active=True,
            )
            .first()
        )
        if usuario is None or not usuario.check_password(attrs["contrasena"]):
            raise LoginFailed()
        attrs["usuario"] = usuario
        return attrs


class ClienteEntrenadorSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    entrenador_detalle = EntrenadorResumenSerializer(source="entrenador", read_only=True)

    class Meta:
        model = ClienteEntrenador
        fields = (
            "id", "cliente", "cliente_detalle", "entrenador", "entrenador_detalle", "fecha_inicio", "fecha_fin",
            "activo", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ClienteTerapeutaSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    terapeuta_detalle = TerapeutaResumenSerializer(source="terapeuta", read_only=True)

    class Meta:
        model = ClienteTerapeuta
        fields = (
            "id",
            "cliente",
            "cliente_detalle",
            "terapeuta",
            "terapeuta_detalle",
            "fecha_inicio",
            "fecha_fin",
            "activo",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class AsistenciaSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)

    class Meta:
        model = Asistencia
        fields = (
            "id", "cliente", "cliente_detalle", "entrada_at", "salida_at", "metodo_entrada", "identificador_evento",
            "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class EntrenamientoSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    entrenador_detalle = EntrenadorResumenSerializer(source="entrenador", read_only=True)

    class Meta:
        model = Entrenamiento
        fields = (
            "id", "cliente", "cliente_detalle", "entrenador", "entrenador_detalle", "inicio_at", "fin_at",
            "duracion_minutos", "observaciones", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "duracion_minutos", "created_at", "updated_at")


class EjercicioSerializer(ModeloValidadoSerializer):
    class Meta:
        model = Ejercicio
        fields = ("id", "nombre", "descripcion", "grupo_muscular", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class PlanEntrenamientoSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    entrenador_detalle = EntrenadorResumenSerializer(source="entrenador", read_only=True)

    class Meta:
        model = PlanEntrenamiento
        fields = (
            "id", "cliente", "cliente_detalle", "entrenador", "entrenador_detalle", "nombre", "objetivo",
            "fecha_inicio", "fecha_fin", "activo", "observaciones", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PlanEntrenamientoEjercicioSerializer(ModeloValidadoSerializer):
    ejercicio_detalle = EjercicioSerializer(source="ejercicio", read_only=True)

    class Meta:
        model = PlanEntrenamientoEjercicio
        fields = (
            "id", "plan", "ejercicio", "ejercicio_detalle", "orden", "series", "repeticiones", "peso_kg",
            "descanso_segundos", "observaciones", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PlanAlimentacionSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    responsable_detalle = EntrenadorResumenSerializer(source="responsable", read_only=True)

    class Meta:
        model = PlanAlimentacion
        fields = (
            "id", "cliente", "cliente_detalle", "responsable", "responsable_detalle", "nombre", "objetivo",
            "calorias_objetivo", "fecha_inicio", "fecha_fin", "activo", "observaciones", "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ComidaSerializer(ModeloValidadoSerializer):
    class Meta:
        model = Comida
        fields = (
            "id", "plan_alimentacion", "nombre", "tipo", "hora_sugerida", "descripcion", "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class RegistroComidaSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    revisado_por_detalle = EntrenadorResumenSerializer(source="revisado_por", read_only=True)
    comida_nombre = serializers.CharField(source="comida.nombre", read_only=True)
    foto = serializers.ImageField(write_only=True, required=False, allow_null=True)
    foto_url = serializers.SerializerMethodField()

    class Meta:
        model = RegistroComida
        fields = (
            "id", "cliente", "cliente_detalle", "comida", "comida_nombre", "registrado_at", "foto", "foto_url",
            "verificado", "calificacion", "observaciones", "revisado_por", "revisado_por_detalle", "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        if "foto_url" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "foto_url": "No se aceptan URLs externas. Suba la imagen en el campo 'foto'."
                }
            )
        actor = self._actor()
        if (
            isinstance(actor, Usuario)
            and getattr(actor.rol, "nombre", None) == Rol.Nombre.CLIENTE
        ):
            prohibidos = {"verificado", "calificacion", "revisado_por"}.intersection(
                attrs
            )
            if prohibidos:
                raise serializers.ValidationError(
                    {
                        campo: "Solo el personal autorizado puede modificar este campo."
                        for campo in sorted(prohibidos)
                    }
                )
        return super().validate(attrs)

    def get_foto_url(self, registro):
        if not registro.foto:
            return None
        ruta = reverse("gym:registro-comida-foto", args=[registro.pk])
        request = self.context.get("request")
        return request.build_absolute_uri(ruta) if request else ruta


def destinatario_permitido(actor, usuario):
    """Administrador, el propio usuario o un profesional asignado al cliente."""
    if usuario is None:
        return False
    if es_administrador(actor):
        return True
    if not isinstance(actor, Usuario):
        return False
    if actor.pk == usuario.pk:
        return True

    if hasattr(actor, "entrenador") and hasattr(usuario, "cliente"):
        return ClienteEntrenador.entrenador_asignado(usuario.pk, actor.pk)

    if hasattr(actor, "terapeuta") and hasattr(usuario, "cliente"):
        return ClienteTerapeuta.objects.filter(
            cliente_id=usuario.pk,
            terapeuta_id=actor.pk,
            activo=True,
            is_active=True,
            deleted_at__isnull=True,
            cliente__is_active=True,
            cliente__deleted_at__isnull=True,
            cliente__usuario__is_active=True,
            terapeuta__is_active=True,
            terapeuta__deleted_at__isnull=True,
            terapeuta__usuario__is_active=True,
        ).exists()

    return False


class NotificacionSerializer(ModeloValidadoSerializer):
    usuario_detalle = UsuarioResumenSerializer(source="usuario", read_only=True)

    class Meta:
        model = Notificacion
        fields = (
            "id", "usuario", "usuario_detalle", "tipo", "titulo", "mensaje", 
"programada_at", "enviada_at", "leida_at",
            "estado", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "leida_at", "created_at", "updated_at")
    def validate(self, attrs):
        attrs = super().validate(attrs)
        usuario = attrs.get(
            "usuario", self.instance.usuario if self.instance is not None else None
        )
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if usuario is not None and not destinatario_permitido(actor, usuario):
            raise serializers.ValidationError(
                {
                    "usuario": (
                        "Solo un administrador, el propio destinatario o un "
                        "profesional activo asignado al cliente puede crear "
                        "esta notificación."
                    )
                }
            )
        return attrs


class PerfilActualUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ("nombre", "username", "correo", "telefono")

    def validate(self, attrs):
        candidato = copy(self.instance)
        for campo, valor in attrs.items():
            setattr(candidato, campo, valor)
        # ``validar_modelo`` ejecuta ``clean()``, que normaliza la identidad.
        validar_modelo(candidato)
        return attrs

    def update(self, instance, validated_data):
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        return instance


class PerfilActualPasswordSerializer(serializers.Serializer):
    contrasena_actual = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )
    contrasena_nueva = serializers.CharField(
        write_only=True, min_length=8, max_length=128, trim_whitespace=False
    )
    confirmacion = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )

    def validate(self, attrs):
        usuario = self.context["request"].user
        if not usuario.check_password(attrs["contrasena_actual"]):
            raise serializers.ValidationError(
                {"contrasena_actual": "La contraseña actual no es correcta."}
            )
        if attrs["contrasena_nueva"] != attrs["confirmacion"]:
            raise serializers.ValidationError(
                {"confirmacion": "La confirmación no coincide con la nueva contraseña."}
            )
        if attrs["contrasena_nueva"] == attrs["contrasena_actual"]:
            raise serializers.ValidationError(
                {"contrasena_nueva": "La nueva contraseña debe ser diferente a la actual."}
            )
        candidato = copy(usuario)
        candidato.email = usuario.correo
        candidato.first_name = usuario.nombre
        try:
            validate_password(attrs["contrasena_nueva"], candidato)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {"contrasena_nueva": list(error.messages)}
            ) from error
        return attrs
