"""Serializers de la API.

Las contraseñas se reciben exclusivamente como ``contrasena`` y se convierten
en un hash; ``contrasena_hash`` nunca forma parte de una respuesta JSON.
"""

import json
from copy import copy

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from .models import (
    validar_musculos,
    Administrador,
    Alerta,
    Asistencia,
    CategoriaGasto,
    Cliente,
    ClienteEntrenador,
    ClienteTerapeuta,
    Comida,
    Ejercicio,
    Entrenador,
    Entrenamiento,
    EventoAuditoria,
    Gasto,
    Gimnasio,
    Membresia,
    MetodoPago,
    Notificacion,
    Pago,
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
from .tenancy import es_plataforma, filtrar_por_gimnasio, gimnasio_id_de


class SerializerVacio(serializers.Serializer):
    pass


class RolResumenSerializer(serializers.Serializer):
    """Resumen ``id``/``nombre`` usado en los esquemas de roles efectivos."""

    id = serializers.IntegerField(read_only=True)
    nombre = serializers.CharField(read_only=True)


class PermisosRolPayloadSerializer(serializers.Serializer):
    """Cuerpo de ``PUT /roles/{id}/permisos/``."""

    permisos = serializers.ListField(
        child=serializers.CharField(), allow_empty=True
    )


class RolesUsuarioPayloadSerializer(serializers.Serializer):
    """Cuerpo de ``PATCH|PUT /usuarios/{id}/roles/``."""

    roles = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True
    )
    rol_principal = serializers.IntegerField(
        min_value=1, required=False, allow_null=True
    )


class LoginFailed(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Correo o contraseña incorrectos."
    default_code = "authentication_failed"


class SeguridadEscrituraMixin:
    """Reglas de escritura que no dependen de una tabla concreta."""

    def _actor(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_fields(self):
        """Limita toda clave foránea escribible al gimnasio del actor.

        Así un id de otro gimnasio responde "no existe" (400) en cualquier
        recurso, sin depender de que cada vista lo valide por su cuenta.
        """
        fields = super().get_fields()
        for nombre, campo in fields.items():
            # El mensaje de unicidad de Django en español es genérico
            # ("Ya existe un/a usuario con este/a correo."); se reemplaza.
            for validador in getattr(campo, "validators", []):
                mensaje = getattr(validador, "message", "")
                if isinstance(mensaje, str) and "un/a" in mensaje:
                    validador.message = MENSAJES_UNICOS.get(
                        nombre, "Ya existe un registro con este valor."
                    )
        actor = self._actor()
        if actor is None or not getattr(actor, "is_authenticated", False):
            return fields
        for campo in fields.values():
            relacion = getattr(campo, "child_relation", campo)
            queryset = getattr(relacion, "queryset", None)
            if queryset is None or getattr(relacion, "read_only", False):
                continue
            try:
                relacion.queryset = filtrar_por_gimnasio(queryset, actor)
            except ImproperlyConfigured:
                raise
        return fields

    def _gimnasio_para_alta(self):
        """Gimnasio de un registro nuevo: siempre el del actor autenticado."""
        actor = self._actor()
        gimnasio_id = gimnasio_id_de(actor)
        if gimnasio_id:
            return gimnasio_id
        if es_plataforma(actor):
            gimnasio_id = Gimnasio.unico_activo_id()
            if gimnasio_id:
                return gimnasio_id
        raise serializers.ValidationError(
            {"gimnasio": "No se pudo determinar el gimnasio del registro."}
        )

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

        if self.instance is None and hasattr(candidato, "asignar_gimnasio"):
            # Si el registro cuelga de un cliente, hereda su gimnasio; si no,
            # toma el del actor. Nunca se lee de la solicitud.
            candidato.asignar_gimnasio(self._actor())
            if not candidato.gimnasio_id:
                candidato.gimnasio_id = self._gimnasio_para_alta()
            attrs["gimnasio_id"] = candidato.gimnasio_id

        try:
            candidato.full_clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        return attrs


class RegistradoPorActorMixin:
    """``registrado_por`` es siempre quien hace la petición, nunca un dato del cliente."""

    def validate(self, attrs):
        if self.instance is None:
            actor = self._actor()
            if not isinstance(actor, Usuario):
                raise serializers.ValidationError(
                    {"registrado_por": "Esta operación requiere un usuario propio del gimnasio."}
                )
            attrs["registrado_por"] = actor
        return super().validate(attrs)


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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        recurso = (
            attrs.get("recurso")
            or (self.instance.recurso if self.instance is not None else "")
        )
        recurso = (recurso or "").strip().lower()
        # El catálogo solo admite recursos que tienen un ViewSet registrado.
        from .resources import RECURSOS_API

        permitidos = set(RECURSOS_API)
        if recurso and recurso not in permitidos:
            raise serializers.ValidationError(
                {
                    "recurso": (
                        "El recurso no está registrado en la API. Crea primero "
                        "su ViewSet y vuelve a intentarlo."
                    )
                }
            )
        return attrs


class RolSerializer(ModeloValidadoSerializer):
    es_del_sistema = serializers.BooleanField(read_only=True)
    permisos = serializers.SerializerMethodField()
    permisos_detalle = serializers.SerializerMethodField()
    recursos = serializers.SerializerMethodField()
    total_usuarios = serializers.SerializerMethodField()

    class Meta:
        model = Rol
        fields = (
            "id",
            "nombre",
            "descripcion",
            "is_active",
            "es_del_sistema",
            "created_at",
            "updated_at",
            "permisos",
            "permisos_detalle",
            "recursos",
            "total_usuarios",
        )
        read_only_fields = (
            "id",
            "es_del_sistema",
            "created_at",
            "updated_at",
            "permisos",
            "permisos_detalle",
            "recursos",
            "total_usuarios",
        )

    def _gimnasio_id(self):
        """Gimnasio cuya matriz se muestra: el indicado o el del actor."""
        if "gimnasio_id" in self.context:
            return self.context["gimnasio_id"]
        return gimnasio_id_de(self._actor())

    def _asignaciones(self, rol, relacion):
        gimnasio_id = self._gimnasio_id()
        return [
            asignacion
            for asignacion in getattr(rol, relacion).all()
            if asignacion.gimnasio_id == gimnasio_id
        ]

    def _permisos_activos(self, rol):
        permisos = [
            asignacion.permiso
            for asignacion in self._asignaciones(rol, "permisos_asignados")
            if asignacion.permiso.is_active
        ]
        permisos.sort(key=lambda permiso: permiso.codigo)
        return permisos

    @extend_schema_field({"type": "array", "items": {"type": "string"}})
    def get_permisos(self, rol):
        return [permiso.codigo for permiso in self._permisos_activos(rol)]

    @extend_schema_field(PermisoSerializer(many=True))
    def get_permisos_detalle(self, rol):
        return PermisoSerializer(self._permisos_activos(rol), many=True).data

    @extend_schema_field({"type": "array", "items": {"type": "string"}})
    def get_recursos(self, rol):
        return sorted(
            asignacion.recurso.nombre
            for asignacion in self._asignaciones(rol, "recursos_asignados")
            if asignacion.recurso.is_active
        )

    @extend_schema_field(OpenApiTypes.INT)
    def get_total_usuarios(self, rol):
        asignaciones = rol.asignaciones_usuarios.filter(activo=True)
        gimnasio_id = self._gimnasio_id()
        if gimnasio_id:
            asignaciones = asignaciones.filter(usuario__gimnasio_id=gimnasio_id)
        return asignaciones.values("usuario_id").distinct().count()


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


@extend_schema_field(OpenApiTypes.OBJECT)
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
        roles = list(filtrar_por_gimnasio(Rol.objects.filter(pk__in=ids), self._actor()))
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
        # Django nombra los atributos internos (first_name, email); se
        # traducen a los campos que el usuario ve en el formulario.
        nombres = {
            " a first_name": " al nombre",
            " a email": " al correo",
            " a username": " al nombre de usuario",
            "first_name": "el nombre",
            "email": "el correo",
            "username": "el nombre de usuario",
        }
        mensajes = []
        for mensaje in error.messages:
            for interno, visible in nombres.items():
                mensaje = mensaje.replace(interno, visible)
            mensajes.append(mensaje)
        raise serializers.ValidationError({"contrasena": mensajes}) from error


MENSAJES_UNICOS = {
    "correo": "Ya existe un usuario con este correo.",
    "username": "Ya existe un usuario con este nombre de usuario.",
}


def validar_modelo(candidato):
    try:
        candidato.full_clean()
    except DjangoValidationError as error:
        errores = {}
        for campo, mensajes in error.message_dict.items():
            # El mensaje de unicidad de Django en español es genérico
            # ("Ya existe un/a usuario con este/a correo."); se reemplaza.
            errores[campo] = [
                MENSAJES_UNICOS.get(campo, mensaje) if "Ya existe un/a" in mensaje else mensaje
                for mensaje in mensajes
            ]
        raise serializers.ValidationError(errores) from error


def administradores_efectivos_activos(excluir_pk=None, gimnasio_id=None):
    """Cuenta administradores por rol principal o por rol adicional activo."""

    queryset = (
        Usuario.objects.filter(is_active=True, deleted_at__isnull=True)
        .filter(
            Q(rol__nombre=Rol.Nombre.ADMINISTRADOR)
            | Q(
                asignaciones_usuarios__rol__nombre=Rol.Nombre.ADMINISTRADOR,
                asignaciones_usuarios__activo=True,
                asignaciones_usuarios__rol__is_active=True,
            )
        )
        .distinct()
    )
    if excluir_pk is not None:
        queryset = queryset.exclude(pk=excluir_pk)
    if gimnasio_id is not None:
        queryset = queryset.filter(gimnasio_id=gimnasio_id)
    return queryset


def existe_otro_administrador_activo(usuario):
    """Cada gimnasio debe conservar al menos un administrador activo."""
    return administradores_efectivos_activos(
        excluir_pk=usuario.pk, gimnasio_id=usuario.gimnasio_id
    ).exists()


class PerfilResumenMixin:
    @extend_schema_field({"type": "object", "nullable": True})
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


class GimnasioConfiguracionSerializer(serializers.ModelSerializer):
    """Datos y umbrales de alertas del gimnasio del usuario autenticado.

    El código (usado en el registro público) y el estado solo los cambia el
    personal de la plataforma.
    """

    class Meta:
        model = Gimnasio
        fields = (
            "id",
            "nombre",
            "codigo",
            "nit",
            "ciudad",
            "direccion",
            "telefono",
            "correo",
            "dias_inactividad_alerta",
            "limite_gastos_mensual",
            "porcentaje_caida_ingresos",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "codigo", "is_active", "created_at", "updated_at")

    def validate(self, attrs):
        candidato = copy(self.instance)
        for atributo, valor in attrs.items():
            setattr(candidato, atributo, valor)
        try:
            candidato.full_clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        return attrs


class GimnasioResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gimnasio
        fields = ("id", "nombre", "codigo", "ciudad")
        read_only_fields = fields


class UsuarioReadSerializer(PerfilResumenMixin, serializers.ModelSerializer):
    """DTO de detalle: identidad pública, roles y perfil resumido."""

    gimnasio = GimnasioResumenSerializer(read_only=True)
    rol_detalle = serializers.SerializerMethodField(read_only=True)
    roles_detalle = serializers.SerializerMethodField(read_only=True)
    permisos = serializers.SerializerMethodField(read_only=True)
    perfil_detalle = serializers.SerializerMethodField(read_only=True)
    es_administrador = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Usuario
        fields = (
            "id",
            "gimnasio",
            "rol",
            "rol_detalle",
            "roles_detalle",
            "permisos",
            "es_administrador",
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

    def _contexto_gimnasio(self, usuario):
        return {**self.context, "gimnasio_id": usuario.gimnasio_id}

    @extend_schema_field(RolSerializer)
    def get_rol_detalle(self, usuario):
        return RolSerializer(usuario.rol, context=self._contexto_gimnasio(usuario)).data

    @extend_schema_field(RolSerializer(many=True))
    def get_roles_detalle(self, usuario):
        return RolSerializer(
            usuario.roles_efectivos(), many=True, context=self._contexto_gimnasio(usuario)
        ).data

    @extend_schema_field({"type": "array", "items": {"type": "string"}})
    def get_permisos(self, usuario):
        return sorted(usuario.permisos_efectivos())

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_es_administrador(self, usuario):
        return es_administrador(usuario)


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

    @extend_schema_field(RolResumenSerializer(many=True))
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

    @extend_schema_field(RolSerializer(many=True))
    def get_roles_efectivos(self, usuario):
        return self.get_roles_detalle(usuario)

    @extend_schema_field({"type": "array", "items": {"type": "string"}})
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

    def to_internal_value(self, data):
        """Devuelve juntos los errores de campo y los de la contraseña.

        DRF corta en el primer campo inválido y no llega a ``validate()``,
        así que la contraseña débil se informaría en un segundo intento. Aquí
        se evalúa también cuando otro campo falla, para mostrar todo de una vez.
        """
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError as error:
            errores = dict(error.detail) if isinstance(error.detail, dict) else {}
            contrasena = data.get("contrasena") if hasattr(data, "get") else None
            if errores and isinstance(contrasena, str) and "contrasena" not in errores:
                candidato = Usuario(
                    nombre=str(data.get("nombre") or ""),
                    correo=str(data.get("correo") or ""),
                    username=data.get("username") or None,
                )
                try:
                    validar_contrasena_django(contrasena, candidato)
                except serializers.ValidationError as error_contrasena:
                    errores.update(error_contrasena.detail)
                    raise serializers.ValidationError(errores) from error
            raise

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
        attrs["gimnasio_id"] = self._gimnasio_para_alta()
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

        if es_administrador(self.instance):
            activo_nuevo = attrs.get("is_active", self.instance.is_active)
            sigue_siendo_admin = (
                rol.nombre == Rol.Nombre.ADMINISTRADOR
                or self.instance.asignaciones_usuarios.filter(
                    rol__nombre=Rol.Nombre.ADMINISTRADOR,
                    activo=True,
                    rol__is_active=True,
                ).exists()
            )
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


class RegistroPublicoSerializer(serializers.Serializer):
    """Alta pública de una cuenta de cliente.

    El rol y el estado se fijan en el servidor: el cuerpo de la solicitud no
    puede escalar privilegios ni crear cuentas inactivas.
    """

    nombre = serializers.CharField(max_length=150)
    correo = serializers.EmailField(max_length=191)
    contrasena = serializers.CharField(
        write_only=True, min_length=8, trim_whitespace=False
    )
    telefono = serializers.CharField(
        max_length=30, required=False, allow_blank=True, allow_null=True
    )
    fecha_nacimiento = serializers.DateField(required=False, allow_null=True)
    objetivo = serializers.CharField(
        max_length=255, required=False, allow_blank=True, allow_null=True
    )
    gimnasio = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        help_text="Código del gimnasio. Opcional si la plataforma tiene uno solo.",
    )

    def validate_gimnasio(self, codigo):
        codigo = (codigo or "").strip().lower()
        activos = Gimnasio.objects.filter(is_active=True, deleted_at__isnull=True)
        if codigo:
            gimnasio = activos.filter(codigo=codigo).first()
            if gimnasio is None:
                raise serializers.ValidationError(
                    "No hay un gimnasio activo con ese código."
                )
            return gimnasio
        return None

    def validate_correo(self, correo):
        correo = normalizar_correo(correo)
        if Usuario.objects.filter(correo=correo).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta registrada con este correo."
            )
        return correo

    def validate(self, attrs):
        rol = Rol.objects.filter(
            nombre=Rol.Nombre.CLIENTE, is_active=True
        ).first()
        if rol is None:
            raise serializers.ValidationError(
                "El registro público no está disponible en este momento."
            )

        gimnasio = attrs.get("gimnasio")
        if gimnasio is None:
            unico_id = Gimnasio.unico_activo_id()
            gimnasio = Gimnasio.objects.filter(pk=unico_id).first() if unico_id else None
        if gimnasio is None:
            raise serializers.ValidationError(
                {"gimnasio": "Indique el código de su gimnasio para registrarse."}
            )
        attrs["gimnasio"] = gimnasio

        contrasena = attrs["contrasena"]
        candidato = Usuario(
            gimnasio=gimnasio,
            rol=rol,
            nombre=attrs["nombre"],
            correo=attrs["correo"],
            telefono=attrs.get("telefono"),
        )
        candidato.set_password(contrasena)
        validar_modelo(candidato)
        validar_contrasena_django(contrasena, candidato)

        attrs["rol"] = rol
        return attrs

    def create(self, validated_data):
        contrasena = validated_data.pop("contrasena")
        rol = validated_data.pop("rol")
        gimnasio = validated_data.pop("gimnasio")
        datos_perfil = {
            clave: validated_data.pop(clave)
            for clave in ("fecha_nacimiento", "objetivo")
            if clave in validated_data
        }

        with transaction.atomic():
            usuario = Usuario(**validated_data, rol=rol, gimnasio=gimnasio)
            usuario.set_password(contrasena)
            usuario.save()

            perfil = Cliente(usuario=usuario, **datos_perfil)
            validar_modelo(perfil)
            perfil.save()
        return usuario


class LoginSerializer(serializers.Serializer):
    correo = serializers.EmailField()
    contrasena = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        usuario = (
            Usuario.objects.select_related("rol", "gimnasio")
            .filter(
                correo=normalizar_correo(attrs["correo"]),
                is_active=True,
                deleted_at__isnull=True,
                rol__is_active=True,
                gimnasio__is_active=True,
                gimnasio__deleted_at__isnull=True,
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
    """Ejercicio del catálogo con músculos e imagen de referencia privada.

    La imagen se sube como ``multipart`` en ``imagen``; enviar ``imagen`` vacío
    o ``quitar_imagen=true`` la elimina. Se lee por ``imagen_url``.
    """

    imagen = serializers.ImageField(write_only=True, required=False, allow_null=True)
    quitar_imagen = serializers.BooleanField(write_only=True, required=False, default=False)
    imagen_url = serializers.SerializerMethodField()
    musculos = serializers.JSONField(required=False)

    class Meta:
        model = Ejercicio
        fields = (
            "id", "nombre", "descripcion", "grupo_muscular", "musculos", "imagen", "quitar_imagen",
            "imagen_url", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_fields(self):
        fields = super().get_fields()
        # En multipart un booleano ausente valdría False (regla de formularios
        # HTML); así ``is_active`` no se desactiva al subir solo una imagen.
        for nombre in ("is_active", "quitar_imagen"):
            if nombre in fields:
                fields[nombre].default_empty_html = serializers.empty
        return fields

    def to_internal_value(self, data):
        # En multipart la lista de músculos llega como texto JSON o repetida.
        if hasattr(data, "getlist") and "musculos" in data:
            valores = data.getlist("musculos")
            datos = data.copy()
            if len(valores) == 1 and str(valores[0]).strip().startswith("["):
                datos["musculos"] = valores[0]
            else:
                datos.setlist("musculos", [])
                datos["musculos"] = json.dumps([v for v in valores if v])
            data = datos
        return super().to_internal_value(data)

    def validate_musculos(self, valor):
        if isinstance(valor, str):
            try:
                valor = json.loads(valor) if valor.strip() else []
            except ValueError as error:
                raise serializers.ValidationError("Envíe una lista de músculos.") from error
        try:
            validar_musculos(valor or [])
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return valor or []

    def validate(self, attrs):
        if attrs.pop("quitar_imagen", False):
            attrs["imagen"] = None
        return super().validate(attrs)

    def update(self, instance, validated_data):
        anterior = instance.imagen.name if instance.imagen else None
        instance = super().update(instance, validated_data)
        nueva = instance.imagen.name if instance.imagen else None
        if anterior and anterior != nueva:
            # No deja archivos huérfanos al reemplazar o quitar la imagen.
            instance.imagen.storage.delete(anterior)
        return instance

    @extend_schema_field({"type": "string", "format": "uri", "nullable": True})
    def get_imagen_url(self, ejercicio):
        if not ejercicio.imagen:
            return None
        ruta = reverse("gym:ejercicio-imagen", args=[ejercicio.pk])
        request = self.context.get("request")
        return request.build_absolute_uri(ruta) if request else ruta


class PlanEntrenamientoSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    entrenador_detalle = EntrenadorResumenSerializer(source="entrenador", read_only=True)

    class Meta:
        model = PlanEntrenamiento
        fields = (
            "id", "cliente", "cliente_detalle", "entrenador", "entrenador_detalle", "nombre", "objetivo",
            "fecha_inicio", "fecha_fin", "activo", "observaciones", "rutina", "is_active", "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PlanEntrenamientoEjercicioSerializer(ModeloValidadoSerializer):
    ejercicio_detalle = serializers.SerializerMethodField()

    class Meta:
        model = PlanEntrenamientoEjercicio
        fields = (
            "id", "plan", "ejercicio", "ejercicio_detalle", "dia_semana", "orden", "series", "repeticiones", "peso_kg",
            "descanso_segundos", "observaciones", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    @extend_schema_field(EjercicioSerializer)
    def get_ejercicio_detalle(self, fila):
        datos = EjercicioSerializer(fila.ejercicio, context=self.context).data
        if fila.ejercicio.imagen:
            # El cliente no tiene acceso al catálogo de ejercicios; ve la
            # imagen a través de la fila de su propio plan.
            ruta = reverse("gym:plan-entrenamiento-ejercicio-imagen", args=[fila.pk])
            request = self.context.get("request")
            datos["imagen_url"] = request.build_absolute_uri(ruta) if request else ruta
        return datos


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

    @extend_schema_field({"type": "string", "format": "uri", "nullable": True})
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


# =============================================================================
# SERIALIZERS FINANCIEROS
# =============================================================================

class MetodoPagoSerializer(ModeloValidadoSerializer):
    class Meta:
        model = MetodoPago
        fields = (
            "id",
            "nombre",
            "tipo",
            "descripcion",
            "is_active",
            "requiere_referencia",
            "orden",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class CategoriaGastoSerializer(ModeloValidadoSerializer):
    class Meta:
        model = CategoriaGasto
        fields = (
            "id",
            "nombre",
            "tipo",
            "descripcion",
            "is_active",
            "color",
            "orden",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PagoSerializer(RegistradoPorActorMixin, ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    metodo_pago_detalle = MetodoPagoSerializer(source="metodo_pago", read_only=True)
    membresia_detalle = serializers.SerializerMethodField()
    registrado_por_detalle = UsuarioResumenSerializer(source="registrado_por", read_only=True)

    class Meta:
        model = Pago
        fields = (
            "id",
            "cliente",
            "cliente_detalle",
            "concepto",
            "concepto_detalle",
            "membresia",
            "membresia_detalle",
            "fecha_pago",
            "valor",
            "metodo_pago",
            "metodo_pago_detalle",
            "referencia",
            "estado",
            "registrado_por",
            "registrado_por_detalle",
            "notas",
            "is_active",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = ("id", "registrado_por", "created_at", "updated_at", "deleted_at")

    def get_membresia_detalle(self, pago):
        if not pago.membresia:
            return None
        return {
            "id": pago.membresia.id,
            "nombre": pago.membresia.nombre,
            "tipo": pago.membresia.tipo,
            "estado": pago.membresia.estado,
        }


class GastoSerializer(RegistradoPorActorMixin, ModeloValidadoSerializer):
    categoria_detalle = CategoriaGastoSerializer(source="categoria", read_only=True)
    metodo_pago_detalle = MetodoPagoSerializer(source="metodo_pago", read_only=True)
    registrado_por_detalle = UsuarioResumenSerializer(source="registrado_por", read_only=True)
    aprobado_por_detalle = UsuarioResumenSerializer(source="aprobado_por", read_only=True)

    class Meta:
        model = Gasto
        fields = (
            "id",
            "descripcion",
            "categoria",
            "categoria_detalle",
            "valor",
            "fecha",
            "metodo_pago",
            "metodo_pago_detalle",
            "referencia",
            "estado",
            "registrado_por",
            "registrado_por_detalle",
            "aprobado_por",
            "aprobado_por_detalle",
            "fecha_aprobacion",
            "observaciones",
            "is_active",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = (
            "id",
            "registrado_por",
            "aprobado_por",
            "fecha_aprobacion",
            "created_at",
            "updated_at",
            "deleted_at",
        )

    def validate(self, attrs):
        # Quien pasa el gasto a aprobado o pagado queda como aprobador; el
        # cliente no puede declarar a otra persona.
        estado = attrs.get("estado") or getattr(self.instance, "estado", None)
        ya_aprobado = self.instance is not None and self.instance.aprobado_por_id
        if estado in (Gasto.Estado.APROBADO, Gasto.Estado.PAGADO) and not ya_aprobado:
            actor = self._actor()
            if isinstance(actor, Usuario):
                attrs["aprobado_por"] = actor
                attrs["fecha_aprobacion"] = timezone.now()
        return super().validate(attrs)


class MembresiaSerializer(RegistradoPorActorMixin, ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    entrenador_detalle = EntrenadorResumenSerializer(source="entrenador_asignado", read_only=True)
    registrado_por_detalle = UsuarioResumenSerializer(source="registrado_por", read_only=True)
    dias_para_vencer = serializers.SerializerMethodField()

    class Meta:
        model = Membresia
        fields = (
            "id",
            "cliente",
            "cliente_detalle",
            "tipo",
            "nombre",
            "precio",
            "fecha_inicio",
            "fecha_fin",
            "fecha_ultima_renovacion",
            "estado",
            "dias_congelados",
            "renovacion_automatica",
            "entrenador_asignado",
            "entrenador_detalle",
            "registrado_por",
            "registrado_por_detalle",
            "observaciones",
            "dias_para_vencer",
            "is_active",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = (
            "id",
            "registrado_por",
            "created_at",
            "updated_at",
            "deleted_at",
            "dias_para_vencer",
        )

    def get_dias_para_vencer(self, membresia):
        return membresia.dias_para_vencer()


class AlertaSerializer(ModeloValidadoSerializer):
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    membresia_detalle = serializers.SerializerMethodField()
    pago_detalle = serializers.SerializerMethodField()
    gasto_detalle = serializers.SerializerMethodField()
    leida_por_detalle = UsuarioResumenSerializer(source="leida_por", read_only=True)

    class Meta:
        model = Alerta
        fields = (
            "id",
            "tipo",
            "prioridad",
            "titulo",
            "mensaje",
            "cliente",
            "cliente_detalle",
            "membresia",
            "membresia_detalle",
            "pago",
            "pago_detalle",
            "gasto",
            "gasto_detalle",
            "leida",
            "leida_por",
            "leida_por_detalle",
            "leida_at",
            "datos_adicionales",
            "is_active",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = ("id", "leida", "leida_por", "leida_at", "created_at", "updated_at", "deleted_at")

    def get_membresia_detalle(self, alerta):
        if not alerta.membresia:
            return None
        return {
            "id": alerta.membresia.id,
            "nombre": alerta.membresia.nombre,
            "estado": alerta.membresia.estado,
        }

    def get_pago_detalle(self, alerta):
        if not alerta.pago:
            return None
        return {
            "id": alerta.pago.id,
            "valor": alerta.pago.valor,
            "concepto": alerta.pago.get_concepto_display(),
        }

    def get_gasto_detalle(self, alerta):
        if not alerta.gasto:
            return None
        return {
            "id": alerta.gasto.id,
            "descripcion": alerta.gasto.descripcion,
            "valor": alerta.gasto.valor,
        }
