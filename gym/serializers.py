"""Serializers de la API.

Las contraseñas se reciben exclusivamente como ``contrasena`` y se convierten
en un hash; ``contrasena_hash`` nunca forma parte de una respuesta JSON.
"""

from copy import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from .models import (
    Administrador,
    Asistencia,
    Cliente,
    ClienteEntrenador,
    Comida,
    Ejercicio,
    Entrenador,
    Entrenamiento,
    Notificacion,
    PlanAlimentacion,
    PlanEntrenamiento,
    PlanEntrenamientoEjercicio,
    Recepcionista,
    RegistroComida,
    Rol,
    Terapeuta,
    Usuario,
)


class LoginFailed(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Correo o contraseña incorrectos."
    default_code = "authentication_failed"


class ModeloValidadoSerializer(serializers.ModelSerializer):
    """Ejecuta ``clean`` y las restricciones del modelo antes de guardar."""

    def validate(self, attrs):
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


class RolSerializer(ModeloValidadoSerializer):
    class Meta:
        model = Rol
        fields = ("id", "nombre", "descripcion", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


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


class PerfilSerializerBase(ModeloValidadoSerializer):
    usuario_detalle = UsuarioResumenSerializer(source="usuario", read_only=True)

    class Meta:
        abstract = True
        read_only_fields = ("created_at", "updated_at", "deleted_at")


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


class UsuarioSerializer(ModeloValidadoSerializer):
    """Alta atómica de un usuario y del perfil determinado por su rol.

    Para crear se envía ``contrasena`` y un objeto ``perfil`` con los campos
    propios del rol. En actualizaciones, los perfiles se editan en su endpoint.
    """

    contrasena = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False, required=False)
    perfil = serializers.DictField(write_only=True, required=False)
    rol_detalle = RolSerializer(source="rol", read_only=True)
    perfil_detalle = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Usuario
        fields = (
            "id",
            "rol",
            "rol_detalle",
            "nombre",
            "username",
            "correo",
            "contrasena",
            "telefono",
            "is_active",
            "created_at",
            "updated_at",
            "perfil",
            "perfil_detalle",
        )
        read_only_fields = ("id", "created_at", "updated_at", "rol_detalle", "perfil_detalle")

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get("contrasena"):
                raise serializers.ValidationError({"contrasena": "La contraseña es obligatoria al crear un usuario."})
            if "perfil" not in attrs:
                raise serializers.ValidationError(
                    {"perfil": "Debe incluir los datos del perfil correspondiente al rol en la misma solicitud."}
                )
        elif "perfil" in attrs:
            raise serializers.ValidationError({"perfil": "Actualice el perfil en su endpoint específico."})

        rol = attrs.get("rol", self.instance.rol if self.instance else None)
        if self.instance is not None and "rol" in attrs and rol != self.instance.rol:
            for relacion, rol_esperado in (
                ("cliente", Rol.Nombre.CLIENTE),
                ("entrenador", Rol.Nombre.ENTRENADOR),
                ("terapeuta", Rol.Nombre.TERAPEUTA),
                ("recepcionista", Rol.Nombre.RECEPCIONISTA),
                ("administrador", Rol.Nombre.ADMINISTRADOR),
            ):
                if hasattr(self.instance, relacion) and rol.nombre != rol_esperado:
                    raise serializers.ValidationError(
                        {"rol": "No puede cambiar el rol de un usuario que ya tiene un perfil asociado."}
                    )

        # ``contrasena`` y ``perfil`` no son columnas del modelo, por ello se
        # excluyen de la validación genérica del serializer base.
        datos_modelo = {k: v for k, v in attrs.items() if k not in {"contrasena", "perfil"}}
        if self.instance is None:
            candidato = Usuario(**datos_modelo)
            if attrs.get("contrasena"):
                candidato.set_password(attrs["contrasena"])
        else:
            candidato = copy(self.instance)
            for atributo, valor in datos_modelo.items():
                setattr(candidato, atributo, valor)
            if attrs.get("contrasena"):
                candidato.set_password(attrs["contrasena"])
        try:
            candidato.full_clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        return attrs

    def create(self, validated_data):
        contrasena = validated_data.pop("contrasena")
        datos_perfil = validated_data.pop("perfil")
        with transaction.atomic():
            usuario = Usuario(**validated_data)
            usuario.set_password(contrasena)
            usuario.full_clean()
            usuario.save()

            serializer_perfil = PERFIL_SERIALIZERS[usuario.rol.nombre](
                data={**datos_perfil, "usuario": usuario.pk}, context=self.context
            )
            try:
                serializer_perfil.is_valid(raise_exception=True)
                serializer_perfil.save()
            except serializers.ValidationError as error:
                raise serializers.ValidationError({"perfil": error.detail}) from error
        return usuario

    def update(self, instance, validated_data):
        validated_data.pop("perfil", None)
        contrasena = validated_data.pop("contrasena", None)
        for atributo, valor in validated_data.items():
            setattr(instance, atributo, valor)
        if contrasena:
            instance.set_password(contrasena)
        instance.full_clean()
        instance.save()
        return instance

    def get_perfil_detalle(self, usuario):
        serializer_clase = PERFIL_SERIALIZERS.get(usuario.rol.nombre)
        if serializer_clase is None:
            return None
        try:
            perfil = getattr(usuario, usuario.rol.nombre)
        except (Cliente.DoesNotExist, Entrenador.DoesNotExist, Terapeuta.DoesNotExist, Recepcionista.DoesNotExist, Administrador.DoesNotExist):
            return None
        return serializer_clase(perfil, context=self.context).data


class LoginSerializer(serializers.Serializer):
    correo = serializers.EmailField()
    contrasena = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        usuario = (
            Usuario.objects.select_related("rol")
            .filter(
                correo__iexact=attrs["correo"],
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

    class Meta:
        model = RegistroComida
        fields = (
            "id", "cliente", "cliente_detalle", "comida", "comida_nombre", "registrado_at", "foto_url",
            "verificado", "calificacion", "observaciones", "revisado_por", "revisado_por_detalle", "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class NotificacionSerializer(ModeloValidadoSerializer):
    usuario_detalle = UsuarioResumenSerializer(source="usuario", read_only=True)

    class Meta:
        model = Notificacion
        fields = (
            "id", "usuario", "usuario_detalle", "tipo", "titulo", "mensaje", "programada_at", "enviada_at",
            "estado", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
