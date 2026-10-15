"""ViewSets CRUD para todos los recursos de Gym Control Pro."""

from django.db.models.deletion import ProtectedError
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

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
from .serializers import (
    AdministradorSerializer,
    AsistenciaSerializer,
    ClienteEntrenadorSerializer,
    ClienteSerializer,
    ComidaSerializer,
    EjercicioSerializer,
    EntrenadorSerializer,
    EntrenamientoSerializer,
    LoginSerializer,
    NotificacionSerializer,
    PlanAlimentacionSerializer,
    PlanEntrenamientoEjercicioSerializer,
    PlanEntrenamientoSerializer,
    RecepcionistaSerializer,
    RegistroComidaSerializer,
    RolSerializer,
    TerapeutaSerializer,
    UsuarioSerializer,
)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.validated_data["usuario"]
        return Response(
            {
                "mensaje": "Inicio de sesión exitoso.",
                "usuario": UsuarioSerializer(usuario, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class ViewSetBase(viewsets.ModelViewSet):
    """Respuestas JSON CRUD y borrado lógico cuando el modelo lo admite.

    La API queda sin autenticación para facilitar la conexión inicial del
    frontend. Antes de exponerla a Internet, sustituya ``AllowAny`` por una
    política de autenticación/autorización acorde con los roles de negocio.
    """

    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        # Todos los modelos que heredan ModeloAuditable tienen deleted_at.
        if any(field.name == "deleted_at" for field in queryset.model._meta.fields):
            queryset = queryset.filter(deleted_at__isnull=True)
        # Evita páginas inestables aun en modelos sin Meta.ordering.
        if not queryset.ordered:
            queryset = queryset.order_by("-created_at", "-pk")
        return queryset

    def perform_destroy(self, instance):
        if hasattr(instance, "soft_delete"):
            instance.soft_delete()
            return
        try:
            instance.delete()
        except ProtectedError as error:
            raise ValidationError(
                {"detalle": "No se puede eliminar porque el registro tiene datos relacionados."}
            ) from error


class RolViewSet(ViewSetBase):
    queryset = Rol.objects.all()
    serializer_class = RolSerializer

    def perform_update(self, serializer):
        if "nombre" in serializer.validated_data and serializer.validated_data["nombre"] != serializer.instance.nombre:
            if serializer.instance.usuarios.exists():
                raise ValidationError({"nombre": "No puede cambiar el nombre de un rol ya asignado a usuarios."})
        serializer.save()


class UsuarioViewSet(ViewSetBase):
    queryset = Usuario.objects.select_related("rol")
    serializer_class = UsuarioSerializer

    def perform_destroy(self, instance):
        # Mantiene coherente la identidad y el perfil asociado en el borrado lógico.
        for relacion in ("cliente", "entrenador", "terapeuta", "recepcionista", "administrador"):
            try:
                perfil = getattr(instance, relacion)
            except (Cliente.DoesNotExist, Entrenador.DoesNotExist, Terapeuta.DoesNotExist, Recepcionista.DoesNotExist, Administrador.DoesNotExist):
                continue
            perfil.soft_delete()
        instance.soft_delete()


class ClienteViewSet(ViewSetBase):
    queryset = Cliente.objects.select_related("usuario__rol")
    serializer_class = ClienteSerializer


class EntrenadorViewSet(ViewSetBase):
    queryset = Entrenador.objects.select_related("usuario__rol")
    serializer_class = EntrenadorSerializer


class TerapeutaViewSet(ViewSetBase):
    queryset = Terapeuta.objects.select_related("usuario__rol")
    serializer_class = TerapeutaSerializer


class RecepcionistaViewSet(ViewSetBase):
    queryset = Recepcionista.objects.select_related("usuario__rol")
    serializer_class = RecepcionistaSerializer


class AdministradorViewSet(ViewSetBase):
    queryset = Administrador.objects.select_related("usuario__rol")
    serializer_class = AdministradorSerializer


class ClienteEntrenadorViewSet(ViewSetBase):
    queryset = ClienteEntrenador.objects.select_related("cliente__usuario", "entrenador__usuario")
    serializer_class = ClienteEntrenadorSerializer


class AsistenciaViewSet(ViewSetBase):
    queryset = Asistencia.objects.select_related("cliente__usuario")
    serializer_class = AsistenciaSerializer


class EntrenamientoViewSet(ViewSetBase):
    queryset = Entrenamiento.objects.select_related("cliente__usuario", "entrenador__usuario")
    serializer_class = EntrenamientoSerializer


class EjercicioViewSet(ViewSetBase):
    queryset = Ejercicio.objects.all()
    serializer_class = EjercicioSerializer


class PlanEntrenamientoViewSet(ViewSetBase):
    queryset = PlanEntrenamiento.objects.select_related("cliente__usuario", "entrenador__usuario")
    serializer_class = PlanEntrenamientoSerializer


class PlanEntrenamientoEjercicioViewSet(ViewSetBase):
    queryset = PlanEntrenamientoEjercicio.objects.select_related("plan", "ejercicio")
    serializer_class = PlanEntrenamientoEjercicioSerializer


class PlanAlimentacionViewSet(ViewSetBase):
    queryset = PlanAlimentacion.objects.select_related("cliente__usuario", "responsable__usuario")
    serializer_class = PlanAlimentacionSerializer


class ComidaViewSet(ViewSetBase):
    queryset = Comida.objects.select_related("plan_alimentacion")
    serializer_class = ComidaSerializer


class RegistroComidaViewSet(ViewSetBase):
    queryset = RegistroComida.objects.select_related("cliente__usuario", "comida", "revisado_por__usuario")
    serializer_class = RegistroComidaSerializer


class NotificacionViewSet(ViewSetBase):
    queryset = Notificacion.objects.select_related("usuario__rol")
    serializer_class = NotificacionSerializer
