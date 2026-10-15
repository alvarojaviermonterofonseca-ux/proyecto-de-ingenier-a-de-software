"""Rutas REST de la aplicación Gym Control Pro."""

from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter

from .views import (
    AdministradorViewSet,
    AsistenciaViewSet,
    ClienteEntrenadorViewSet,
    ClienteViewSet,
    ComidaViewSet,
    EjercicioViewSet,
    EntrenadorViewSet,
    EntrenamientoViewSet,
    LoginView,
    LogoutView,
    NotificacionViewSet,
    PlanAlimentacionViewSet,
    PlanEntrenamientoEjercicioViewSet,
    PlanEntrenamientoViewSet,
    RecepcionistaViewSet,
    RegistroComidaViewSet,
    RolViewSet,
    TerapeutaViewSet,
    UsuarioViewSet,
    PerfilActualView,
)

app_name = "gym"


class PublicApiRootView(DefaultRouter.APIRootView):
    """Muestra el índice de la API sin exponer los recursos."""

    authentication_classes = []
    permission_classes = [AllowAny]


class GymRouter(DefaultRouter):
    APIRootView = PublicApiRootView


router = GymRouter()
router.register("roles", RolViewSet, basename="rol")
router.register("usuarios", UsuarioViewSet, basename="usuario")
router.register("clientes", ClienteViewSet, basename="cliente")
router.register("entrenadores", EntrenadorViewSet, basename="entrenador")
router.register("terapeutas", TerapeutaViewSet, basename="terapeuta")
router.register("recepcionistas", RecepcionistaViewSet, basename="recepcionista")
router.register("administradores", AdministradorViewSet, basename="administrador")
router.register("asignaciones-cliente-entrenador", ClienteEntrenadorViewSet, basename="asignacion-cliente-entrenador")
router.register("asistencias", AsistenciaViewSet, basename="asistencia")
router.register("entrenamientos", EntrenamientoViewSet, basename="entrenamiento")
router.register("ejercicios", EjercicioViewSet, basename="ejercicio")
router.register("planes-entrenamiento", PlanEntrenamientoViewSet, basename="plan-entrenamiento")
router.register("planes-entrenamiento-ejercicios", PlanEntrenamientoEjercicioViewSet, basename="plan-entrenamiento-ejercicio")
router.register("planes-alimentacion", PlanAlimentacionViewSet, basename="plan-alimentacion")
router.register("comidas", ComidaViewSet, basename="comida")
router.register("registros-comida", RegistroComidaViewSet, basename="registro-comida")
router.register("notificaciones", NotificacionViewSet, basename="notificacion")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", PerfilActualView.as_view(), name="perfil-actual"),
    *router.urls,
]
