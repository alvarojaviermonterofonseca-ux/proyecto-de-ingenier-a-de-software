"""ViewSets CRUD para todos los recursos de Gym Control Pro."""

import mimetypes
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import logout as django_logout
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import renderers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

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
    Sesion,
    Terapeuta,
    Usuario,
    UsuarioRol,
)
from .audit import registrar_evento
from .permissions import (
    SoloAdministrador,
    SoloAdministradorParaEscritura,
    TienePermisoRecurso,
    es_administrador,
)
from .scoping import (
    clientes_clinicos,
    clientes_operativos,
    filtrar_asignaciones_entrenador,
    filtrar_asignaciones_terapeuta,
    filtrar_clientes,
    filtrar_perfil,
    usuarios_visibles,
)
from .serializers import (
    AdministradorSerializer,
    AsistenciaSerializer,
    ClienteEntrenadorSerializer,
    ClienteOperativoSerializer,
    ClienteSerializer,
    ClienteTerapeutaSerializer,
    ComidaSerializer,
    EjercicioSerializer,
    EntrenadorSerializer,
    EntrenamientoSerializer,
    EventoAuditoriaSerializer,
    LoginSerializer,
    NotificacionSerializer,
    PerfilActualPasswordSerializer,
    PerfilActualUpdateSerializer,
    PERFIL_PROPIO_SERIALIZERS,
    PermisoSerializer,
    PlanAlimentacionSerializer,
    PlanEntrenamientoEjercicioSerializer,
    PlanEntrenamientoSerializer,
    RecepcionistaSerializer,
    RegistroComidaSerializer,
    RolPermisoSerializer,
    RolSerializer,
    SerializerVacio,
    TerapeutaSerializer,
    UsuarioCreateSerializer,
    UsuarioListSerializer,
    UsuarioMeSerializer,
    UsuarioReadSerializer,
    UsuarioRolSerializer,
    UsuarioUpdateSerializer,
)


def usuarios_con_rol(rol):
    return Usuario.objects.filter(
        Q(rol=rol)
        | Q(
            asignaciones_usuarios__rol=rol,
            asignaciones_usuarios__activo=True,
        )
    ).distinct()


def revocar_sesiones_de_rol(rol):
    Sesion.objects.filter(usuario__in=usuarios_con_rol(rol)).delete()


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses={200: OpenApiResponse(description="Token y datos del usuario.")},
        auth=[],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.validated_data["usuario"]
        token, sesion = Sesion.crear_para_usuario(usuario)
        return Response(
            {
                "mensaje": "Inicio de sesión exitoso.",
                "token": token,
                "tipo_token": "Bearer",
                "expira_at": sesion.expira_at,
                "usuario": UsuarioReadSerializer(usuario, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """Revoca únicamente la sesión que acompaña la solicitud actual."""

    permission_classes = [IsAuthenticated]
    serializer_class = SerializerVacio

    @extend_schema(responses={200: OpenApiResponse(description="Sesión cerrada.")})
    def post(self, request):
        if isinstance(request.auth, Sesion):
            request.auth.delete()
        else:
            django_logout(request)
        # Se devuelve contenido para que la respuesta sea consistente tanto
        # para JSON como para el navegador de DRF durante el desarrollo.
        return Response({"mensaje": "Sesión cerrada correctamente."}, status=status.HTTP_200_OK)


class LogoutAllView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SerializerVacio

    @extend_schema(responses={200: OpenApiResponse(description="Sesiones revocadas.")})
    def post(self, request):
        if isinstance(request.user, Usuario):
            cantidad, _ = request.user.sesiones.all().delete()
            mensaje = "Todas las sesiones fueron revocadas."
        else:
            django_logout(request)
            cantidad = 0
            mensaje = "Sesión web cerrada correctamente."
        return Response(
            {"mensaje": mensaje, "sesiones_revocadas": cantidad},
            status=status.HTTP_200_OK,
        )


class PerfilActualView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UsuarioMeSerializer)
    def get(self, request):
        if isinstance(request.user, Usuario):
            return Response(UsuarioMeSerializer(request.user, context={"request": request}).data)
        return Response(
            {
                "id": request.user.pk,
                "username": request.user.get_username(),
                "correo": request.user.email,
                "es_administrador": request.user.is_staff,
            }
        )

    @extend_schema(
        request=PerfilActualUpdateSerializer,
        responses={200: UsuarioMeSerializer},
    )
    def patch(self, request):
        if not isinstance(request.user, Usuario):
            raise ValidationError(
                {"detalle": "El autoservicio de identidad solo está disponible para usuarios propios."}
            )
        serializer = PerfilActualUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        registrar_evento(request, "actualizar-perfil", "usuarios", objeto=usuario)
        return Response(
            UsuarioMeSerializer(usuario, context={"request": request}).data
        )


class CambiarContrasenaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=PerfilActualPasswordSerializer,
        responses={200: OpenApiResponse(description="Contraseña actualizada.")},
    )
    def post(self, request):
        if not isinstance(request.user, Usuario):
            raise ValidationError(
                {"detalle": "El cambio de contraseña solo está disponible para usuarios propios."}
            )
        serializer = PerfilActualPasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        usuario = request.user
        usuario.set_password(serializer.validated_data["contrasena_nueva"])
        usuario.save(update_fields=["contrasena_hash", "updated_at"])
        sesion_actual = request.auth if isinstance(request.auth, Sesion) else None
        sesiones = usuario.sesiones.all()
        if sesion_actual is not None:
            sesiones = sesiones.exclude(pk=sesion_actual.pk)
        sesiones.delete()
        registrar_evento(request, "cambiar-contrasena", "usuarios", objeto=usuario)
        return Response({"mensaje": "Contraseña actualizada correctamente."})


class PerfilActualDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def _perfil(self, request):
        if not isinstance(request.user, Usuario):
            raise NotFound("El usuario autenticado no tiene un perfil propio.")
        serializer_clase = PERFIL_PROPIO_SERIALIZERS.get(request.user.rol.nombre)
        if serializer_clase is None:
            raise NotFound("El rol del usuario no tiene un perfil asociado.")
        try:
            perfil = getattr(request.user, request.user.rol.nombre)
        except (ObjectDoesNotExist, AttributeError) as error:
            raise NotFound("El usuario no tiene un perfil asociado.") from error
        return perfil, serializer_clase

    @extend_schema(responses={200: OpenApiResponse(description="Perfil del usuario autenticado.")})
    def get(self, request):
        perfil, serializer_clase = self._perfil(request)
        return Response(
            serializer_clase(perfil, context={"request": request}).data
        )

    @extend_schema(
        request=OpenApiResponse(description="Campos editables del perfil propio."),
        responses={200: OpenApiResponse(description="Perfil actualizado.")},
    )
    def patch(self, request):
        perfil, serializer_clase = self._perfil(request)
        serializer = serializer_clase(
            perfil,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        perfil = serializer.save()
        registrar_evento(request, "actualizar-perfil-detalle", "usuarios", objeto=perfil.usuario)
        return Response(serializer.data)


class ResumenView(APIView):
    """Indicadores agregados y actividad reciente respetando el alcance por rol."""

    permission_classes = [IsAuthenticated]

    def _puede(self, permiso):
        usuario = self.request.user
        if not isinstance(usuario, Usuario):
            return bool(getattr(usuario, "is_staff", False))
        return usuario.tiene_permiso(permiso)

    @extend_schema(responses={200: OpenApiResponse(description="Resumen del panel.")})
    def get(self, request):
        usuario = request.user
        rol = getattr(getattr(usuario, "rol", None), "nombre", None)
        es_cliente = rol == Rol.Nombre.CLIENTE
        es_recepcionista = rol == Rol.Nombre.RECEPCIONISTA

        clientes = (
            clientes_operativos(usuario)
            if es_recepcionista
            else clientes_clinicos(usuario)
        )
        usuarios = usuarios_visibles(usuario)
        asistencias = Asistencia.objects.filter(
            cliente__in=clientes,
            is_active=True,
            deleted_at__isnull=True,
        )
        entrenamientos = Entrenamiento.objects.filter(
            cliente__in=clientes,
            is_active=True,
            deleted_at__isnull=True,
        )
        planes_entrenamiento = PlanEntrenamiento.objects.filter(
            cliente__in=clientes,
            is_active=True,
            deleted_at__isnull=True,
        )
        planes_alimentacion = PlanAlimentacion.objects.filter(
            cliente__in=clientes,
            is_active=True,
            deleted_at__isnull=True,
        )
        registros = RegistroComida.objects.filter(
            cliente__in=clientes,
            is_active=True,
            deleted_at__isnull=True,
        )
        notificaciones = Notificacion.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        if not es_administrador(usuario):
            notificaciones = notificaciones.filter(usuario=usuario)

        inicio_dia = timezone.localtime().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fin_dia = inicio_dia + timedelta(days=1)

        metricas = {
            "usuarios_activos": usuarios.filter(is_active=True, deleted_at__isnull=True).count(),
            "clientes_activos": clientes.filter(is_active=True, deleted_at__isnull=True).count(),
            "entrenadores_activos": (
                Entrenador.objects.filter(
                    is_active=True,
                    deleted_at__isnull=True,
                    pk__in=(
                        usuarios.filter(is_active=True, rol__nombre=Rol.Nombre.ENTRENADOR)
                        .values("pk")
                    ),
                ).count()
                if self._puede("entrenadores:view")
                else 0
            ),
            "terapeutas_activos": (
                Terapeuta.objects.filter(
                    is_active=True,
                    deleted_at__isnull=True,
                    pk__in=(
                        usuarios.filter(is_active=True, rol__nombre=Rol.Nombre.TERAPEUTA)
                        .values("pk")
                    ),
                ).count()
                if self._puede("terapeutas:view")
                else 0
            ),
            "asistencias_hoy": (
                asistencias.filter(
                    entrada_at__gte=inicio_dia,
                    entrada_at__lt=fin_dia,
                ).count()
                if self._puede("asistencias:view")
                else 0
            ),
            "asistencias_abiertas": (
                asistencias.filter(salida_at__isnull=True).count()
                if self._puede("asistencias:view")
                else 0
            ),
            "entrenamientos_hoy": (
                entrenamientos.filter(
                    inicio_at__gte=inicio_dia,
                    inicio_at__lt=fin_dia,
                ).count()
                if self._puede("entrenamientos:view")
                else 0
            ),
            "planes_entrenamiento_activos": (
                planes_entrenamiento.filter(activo=True).count()
                if self._puede("planes-entrenamiento:view")
                else 0
            ),
            "planes_alimentacion_activos": (
                planes_alimentacion.filter(activo=True).count()
                if self._puede("planes-alimentacion:view")
                else 0
            ),
            "registros_comida_pendientes": (
                registros.filter(verificado=False).count()
                if self._puede("registros-comida:view")
                else 0
            ),
            "notificaciones_pendientes": (
                notificaciones.filter(estado=Notificacion.Estado.PENDIENTE).count()
                if self._puede("notificaciones:view")
                else 0
            ),
        }

        contexto = {"request": request}
        asistencias_recientes = []
        if self._puede("asistencias:view"):
            asistencias_recientes = AsistenciaSerializer(
                asistencias.select_related("cliente__usuario")
                .order_by("-entrada_at", "-pk")[:6],
                many=True,
                context=contexto,
            ).data

        notificaciones_recientes = []
        if self._puede("notificaciones:view"):
            notificaciones_recientes = NotificacionSerializer(
                notificaciones.select_related("usuario__rol")
                .order_by("-created_at", "-pk")[:6],
                many=True,
                context=contexto,
            ).data

        actividad_reciente = []
        if es_administrador(usuario):
            actividad_reciente = EventoAuditoriaSerializer(
                EventoAuditoria.objects.select_related("actor").order_by("-created_at")[:8],
                many=True,
                context=contexto,
            ).data

        return Response(
            {
                "rol_principal": rol,
                "es_cliente": es_cliente,
                "metricas": metricas,
                "asistencias_recientes": asistencias_recientes,
                "notificaciones_recientes": notificaciones_recientes,
                "actividad_reciente": actividad_reciente,
            }
        )


class ViewSetBase(viewsets.ModelViewSet):
    """Respuestas JSON CRUD, borrado lógico y autorización RBAC de base de datos.

    Cada ViewSet declara ``recurso_permiso``. La acción se deriva del método
    HTTP (view/create/edit/delete) y se valida contra los permisos efectivos del
    usuario autenticado.

    ``politica_borrado`` define el DELETE del recurso:

    - ``logico`` (predeterminado): usa ``soft_delete()`` y oculta el registro.
      Los modelos con ``deleted_at`` se filtran por esa columna; los catálogos
      que solo tienen ``is_active`` (roles y permisos) se filtran por estado.
    - ``fisico``: el registro es una fila de composición o una asignación sin
      historial propio (``UsuarioRol``, ``RolPermiso`` y las filas de ejercicios
      de un plan). Se elimina de la base de datos.
    """

    permission_classes = [IsAuthenticated, TienePermisoRecurso]
    recurso_permiso = None
    politica_borrado = "logico"

    def queryset_base(self):
        queryset = super().get_queryset()
        campos = {field.name for field in queryset.model._meta.fields}
        incluir_eliminados = (
            getattr(self, "action", None) == "list"
            and self.request.query_params.get("incluir_eliminados") in {"1", "true"}
            and es_administrador(self.request.user)
        )
        if "deleted_at" in campos:
            if not incluir_eliminados:
                queryset = queryset.filter(deleted_at__isnull=True)
        elif self.politica_borrado == "logico" and "is_active" in campos:
            if not incluir_eliminados:
                queryset = queryset.filter(is_active=True)
        if not queryset.ordered:
            queryset = queryset.order_by("-created_at", "-pk")
        return queryset

    def filtrar_alcance(self, queryset):
        return queryset

    def get_queryset(self):
        return self.filtrar_alcance(self.queryset_base())

    def objeto_permitido(self, request, obj):
        if es_administrador(request.user):
            return True
        return self.filtrar_alcance(self.queryset_base()).filter(pk=obj.pk).exists()

    def respuesta_lista(self, queryset, serializer_class):
        pagina = self.paginate_queryset(queryset)
        contexto = self.get_serializer_context()
        if pagina is not None:
            return self.get_paginated_response(
                serializer_class(pagina, many=True, context=contexto).data
            )
        return Response(serializer_class(queryset, many=True, context=contexto).data)

    def registrar_evento(self, accion, instance=None, detalles=None):
        return registrar_evento(
            self.request,
            accion,
            self.recurso_permiso,
            objeto=instance,
            detalles=detalles,
        )

    def validar_escritura(self, serializer):
        return None

    def validar_cliente_relacionado(
        self, serializer, campo="cliente", operativo=False
    ):
        cliente = serializer.validated_data.get(campo)
        if cliente is None:
            return
        permitidos = (
            clientes_operativos(self.request.user)
            if operativo
            else clientes_clinicos(self.request.user)
        )
        if not permitidos.filter(pk=cliente.pk).exists():
            raise ValidationError(
                {campo: "El cliente no pertenece a su alcance de acceso."}
            )

    def validar_usuario_relacionado(self, serializer, campo):
        usuario = serializer.validated_data.get(campo)
        if usuario is None:
            return
        usuario = getattr(usuario, "usuario", usuario)
        if not usuarios_visibles(self.request.user).filter(pk=usuario.pk).exists():
            raise ValidationError(
                {campo: "El usuario no pertenece a su alcance de acceso."}
            )

    def perform_create(self, serializer):
        self.validar_escritura(serializer)
        instance = serializer.save()
        self.registrar_evento("crear", instance)
        return instance

    def perform_update(self, serializer):
        self.validar_escritura(serializer)
        instance = serializer.save()
        self.registrar_evento("actualizar", instance)
        return instance

    def perform_destroy(self, instance):
        self.registrar_evento("eliminar", instance)
        if self.politica_borrado == "logico":
            instance.soft_delete()
            return
        try:
            instance.delete()
        except ProtectedError as error:
            raise ValidationError(
                {"detalle": "No se puede eliminar porque el registro tiene datos relacionados."}
            ) from error

    def _activar_instancia(self, instancia):
        campos = {field.name for field in instancia._meta.fields}
        cambios = []
        if "deleted_at" in campos:
            instancia.deleted_at = None
            cambios.append("deleted_at")
        if "is_active" in campos:
            instancia.is_active = True
            cambios.append("is_active")
        if "updated_at" in campos:
            instancia.updated_at = timezone.now()
            cambios.append("updated_at")
        try:
            instancia.full_clean()
            instancia.save(update_fields=cambios)
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict) from error
        except IntegrityError as error:
            raise ValidationError(
                {"detalle": "No se puede restaurar porque sus datos únicos ya están en uso."}
            ) from error

    def _restaurar_dependencias(self, instancia):
        perfiles = (Cliente, Entrenador, Terapeuta, Recepcionista, Administrador)
        if isinstance(instancia, Usuario):
            for relacion in ("cliente", "entrenador", "terapeuta", "recepcionista", "administrador"):
                try:
                    perfil = getattr(instancia, relacion)
                except (ObjectDoesNotExist, AttributeError):
                    continue
                if perfil.deleted_at is not None:
                    self._activar_instancia(perfil)
        elif isinstance(instancia, perfiles):
            usuario = instancia.usuario
            if usuario.deleted_at is not None:
                self._activar_instancia(usuario)

    @action(detail=True, methods=["post"], url_path="restaurar")
    def restaurar(self, request, pk=None):
        if not es_administrador(request.user):
            raise PermissionDenied("Solo un administrador puede restaurar registros.")

        modelo = self.queryset.model
        campos = {field.name for field in modelo._meta.fields}
        if "deleted_at" not in campos and "is_active" not in campos:
            raise ValidationError(
                {"detalle": "Este recurso no admite restauración."}
            )

        try:
            instancia = modelo.objects.get(pk=pk)
        except modelo.DoesNotExist as error:
            raise NotFound("No se encontró el recurso solicitado.") from error

        ya_activo = (
            ("deleted_at" not in campos or instancia.deleted_at is None)
            and ("is_active" not in campos or instancia.is_active)
        )
        if ya_activo:
            raise ValidationError({"detalle": "El registro ya está activo."})

        with transaction.atomic():
            self._restaurar_dependencias(instancia)
            self._activar_instancia(instancia)
            self.registrar_evento("restaurar", instancia)

        return Response(
            {
                "mensaje": "Registro restaurado correctamente.",
                "registro": self.get_serializer(instancia).data,
            }
        )


class RolViewSet(ViewSetBase):
    queryset = Rol.objects.prefetch_related("permisos_asignados__permiso", "asignaciones_usuarios")
    serializer_class = RolSerializer
    recurso_permiso = "roles"
    filterset_fields = ("is_active",)
    search_fields = ("nombre", "descripcion")
    ordering_fields = ("nombre", "created_at")
    # Catálogo sin deleted_at: el DELETE desactiva el rol y lo oculta.
    politica_borrado = "logico"

    def perform_update(self, serializer):
        es_rol_admin = serializer.instance.nombre == Rol.Nombre.ADMINISTRADOR
        if es_rol_admin and "nombre" in serializer.validated_data:
            if serializer.validated_data["nombre"] != Rol.Nombre.ADMINISTRADOR:
                raise ValidationError(
                    {"nombre": "El rol administrador base no puede renombrarse."}
                )
        if es_rol_admin and serializer.validated_data.get("is_active") is False:
            raise ValidationError(
                {"is_active": "El rol administrador base no puede desactivarse."}
            )
        if "nombre" in serializer.validated_data and serializer.validated_data["nombre"] != serializer.instance.nombre:
            asignado = (
                serializer.instance.usuarios.exists()
                or serializer.instance.asignaciones_usuarios.filter(activo=True).exists()
            )
            if asignado:
                raise ValidationError({"nombre": "No puede cambiar el nombre de un rol ya asignado a usuarios."})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.nombre == Rol.Nombre.ADMINISTRADOR:
            raise ValidationError(
                {"detalle": "El rol administrador base no puede eliminarse."}
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=["get", "put"], url_path="permisos")
    def permisos(self, request, pk=None):
        """Consulta o reemplaza atómicamente los permisos de un rol."""
        rol = self.get_object()

        if request.method == "PUT":
            if not es_administrador(request.user):
                raise PermissionDenied(
                    "Solo un administrador puede modificar los permisos de un rol."
                )
            codigos = request.data.get("permisos")
            if not isinstance(codigos, list) or not all(isinstance(codigo, str) for codigo in codigos):
                raise ValidationError({"permisos": "Envíe una lista de códigos de permiso."})

            codigos = list(dict.fromkeys(codigos))
            permisos = list(Permiso.objects.filter(codigo__in=codigos, is_active=True))
            encontrados = {permiso.codigo for permiso in permisos}
            faltantes = sorted(set(codigos) - encontrados)
            if faltantes:
                raise ValidationError(
                    {"permisos": f"Permisos inexistentes o inactivos: {', '.join(faltantes)}."}
                )

            with transaction.atomic():
                RolPermiso.objects.filter(rol=rol).exclude(permiso__in=permisos).delete()
                existentes = set(
                    RolPermiso.objects.filter(rol=rol).values_list("permiso_id", flat=True)
                )
                RolPermiso.objects.bulk_create(
                    [
                        RolPermiso(rol=rol, permiso=permiso)
                        for permiso in permisos
                        if permiso.pk not in existentes
                    ]
                )
                revocar_sesiones_de_rol(rol)
                registrar_evento(
                    request,
                    "actualizar-permisos",
                    "roles",
                    rol,
                    detalles={"permisos": codigos},
                )

        asignaciones = rol.permisos_asignados.select_related("permiso").filter(permiso__is_active=True)
        return Response(
            {
                "rol": rol.pk,
                "nombre": rol.nombre,
                "permisos": sorted(asignacion.permiso.codigo for asignacion in asignaciones),
                "detalle": PermisoSerializer(
                    [asignacion.permiso for asignacion in asignaciones], many=True
                ).data,
            }
        )

    def perform_destroy(self, instance):
        usuarios = list(usuarios_con_rol(instance).values_list("pk", flat=True))
        with transaction.atomic():
            super().perform_destroy(instance)
            Sesion.objects.filter(usuario_id__in=usuarios).delete()


class PermisoViewSet(ViewSetBase):
    queryset = Permiso.objects.all()
    serializer_class = PermisoSerializer
    recurso_permiso = "permisos"
    filterset_fields = ("recurso", "accion", "is_active")
    search_fields = ("codigo", "descripcion")
    ordering_fields = ("codigo", "recurso", "accion")
    # Catálogo sin deleted_at: el DELETE desactiva el permiso y lo oculta.
    politica_borrado = "logico"


class RolPermisoViewSet(ViewSetBase):
    queryset = RolPermiso.objects.select_related("rol", "permiso")
    serializer_class = RolPermisoSerializer
    recurso_permiso = "roles"
    filterset_fields = ("rol", "permiso")
    permission_classes = [IsAuthenticated, TienePermisoRecurso, SoloAdministradorParaEscritura]
    # Tabla puente sin historial propio: se elimina físicamente.
    politica_borrado = "fisico"

    def perform_create(self, serializer):
        with transaction.atomic():
            asignacion = serializer.save()
            revocar_sesiones_de_rol(asignacion.rol)
            self.registrar_evento(
                "asignar-permiso",
                asignacion.rol,
                detalles={"permiso": asignacion.permiso.codigo},
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            asignacion = serializer.save()
            revocar_sesiones_de_rol(asignacion.rol)
            self.registrar_evento(
                "actualizar-permiso-rol",
                asignacion.rol,
                detalles={"permiso": asignacion.permiso.codigo},
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            rol = instance.rol
            permiso = instance.permiso.codigo
            super().perform_destroy(instance)
            revocar_sesiones_de_rol(rol)
            self.registrar_evento(
                "revocar-permiso", rol, detalles={"permiso": permiso}
            )


class UsuarioViewSet(ViewSetBase):
    queryset = Usuario.objects.select_related(
        "rol",
        "cliente",
        "entrenador",
        "terapeuta",
        "recepcionista",
        "administrador",
    )
    serializer_class = UsuarioReadSerializer
    recurso_permiso = "usuarios"
    filterset_fields = ("rol", "is_active")
    search_fields = ("nombre", "username", "correo", "telefono")
    ordering_fields = ("nombre", "correo", "created_at", "is_active")

    # Usuario.soft_delete propaga a perfil, roles, notificaciones y sesiones.
    politica_borrado = "logico"

    def filtrar_alcance(self, queryset):
        return queryset.filter(pk__in=usuarios_visibles(self.request.user).values("pk"))

    def perform_destroy(self, instance):
        if isinstance(self.request.user, Usuario) and instance.pk == self.request.user.pk:
            raise ValidationError(
                {"detalle": "No puede eliminar su propia cuenta."}
            )
        if instance.rol.nombre == Rol.Nombre.ADMINISTRADOR:
            administradores = Usuario.objects.filter(
                rol__nombre=Rol.Nombre.ADMINISTRADOR,
                is_active=True,
                deleted_at__isnull=True,
            )
            if administradores.count() <= 1:
                raise ValidationError(
                    {"detalle": "No puede eliminar al último administrador activo."}
                )
        super().perform_destroy(instance)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            return queryset.prefetch_related("asignaciones_usuarios__rol")
        return queryset.prefetch_related(
            "asignaciones_usuarios__rol", "rol__permisos_asignados__permiso"
        )

    def get_serializer_class(self):
        if self.action == "list":
            return UsuarioListSerializer
        if self.action == "create":
            return UsuarioCreateSerializer
        if self.action in {"update", "partial_update"}:
            return UsuarioUpdateSerializer
        return UsuarioReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        lectura = UsuarioReadSerializer(
            serializer.instance, context=self.get_serializer_context()
        )
        headers = self.get_success_headers(lectura.data)
        return Response(lectura.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}
        return Response(
            UsuarioReadSerializer(
                instance, context=self.get_serializer_context()
            ).data
        )

    @action(detail=True, methods=["get", "patch", "put"], url_path="roles")
    def roles(self, request, pk=None):
        """Consulta o reemplaza los roles adicionales activos de un usuario."""
        usuario = self.get_object()
        mutando = request.method in {"PATCH", "PUT"}

        if mutando:
            if not es_administrador(request.user):
                raise PermissionDenied(
                    "Solo un administrador puede modificar los roles de un usuario."
                )
            roles_ids = request.data.get("roles")
            if not isinstance(roles_ids, list) or not all(isinstance(valor, int) for valor in roles_ids):
                raise ValidationError({"roles": "Envíe una lista de identificadores de rol."})

            roles_ids = list(dict.fromkeys(roles_ids))
            roles = list(Rol.objects.filter(pk__in=roles_ids))
            if len(roles) != len(roles_ids):
                raise ValidationError({"roles": "Uno o más roles no existen."})
            if any(not rol.is_active for rol in roles):
                raise ValidationError({"roles": "Solo puede asignar roles activos."})

            deseados = set(roles_ids)
            deseados.add(usuario.rol_id)
            asignado_por = request.user if isinstance(request.user, Usuario) else None
            with transaction.atomic():
                existentes = {
                    asignacion.rol_id: asignacion
                    for asignacion in usuario.asignaciones_usuarios.select_for_update()
                }
                for rol_id in deseados:
                    asignacion = existentes.get(rol_id)
                    if asignacion is None:
                        UsuarioRol.objects.create(
                            usuario=usuario,
                            rol_id=rol_id,
                            activo=True,
                            asignado_por=asignado_por,
                        )
                    elif not asignacion.activo:
                        asignacion.activo = True
                        asignacion.asignado_por = asignado_por
                        asignacion.save(update_fields=["activo", "asignado_por", "updated_at"])
                for rol_id, asignacion in existentes.items():
                    if rol_id not in deseados and asignacion.activo:
                        asignacion.activo = False
                        asignacion.save(update_fields=["activo", "updated_at"])
                Sesion.objects.filter(usuario=usuario).delete()
                registrar_evento(
                    request,
                    "actualizar-roles",
                    "usuarios",
                    usuario,
                    detalles={"roles": roles_ids},
                )

        asignaciones = usuario.asignaciones_usuarios.select_related("rol", "asignado_por")
        if mutando:
            return Response(UsuarioReadSerializer(usuario, context={"request": request}).data)
        return Response(
            {
                "usuario": usuario.pk,
                "rol_principal": RolSerializer(usuario.rol, context={"request": request}).data,
                "roles": [
                    {
                        "id": asignacion.rol_id,
                        "nombre": asignacion.rol.nombre,
                        "activo": asignacion.activo,
                        "asignado_por": asignacion.asignado_por_id,
                    }
                    for asignacion in asignaciones
                ],
                "roles_efectivos": list(usuario.roles_efectivos().values_list("id", flat=True)),
            }
        )


class UsuarioRolViewSet(ViewSetBase):
    queryset = UsuarioRol.objects.select_related("usuario", "rol", "asignado_por")
    serializer_class = UsuarioRolSerializer
    recurso_permiso = "usuarios"
    filterset_fields = ("usuario", "rol", "activo")
    permission_classes = [IsAuthenticated, TienePermisoRecurso, SoloAdministrador]
    # Tabla puente sin historial propio: se elimina físicamente.
    politica_borrado = "fisico"

    def perform_create(self, serializer):
        asignado_por = self.request.user if isinstance(self.request.user, Usuario) else None
        with transaction.atomic():
            asignacion = serializer.save(asignado_por=asignado_por)
            asignacion.usuario.sesiones.all().delete()
            self.registrar_evento(
                "asignar-rol",
                asignacion.usuario,
                detalles={"rol": asignacion.rol.nombre},
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            usuario = instance.usuario
            rol = instance.rol.nombre
            super().perform_destroy(instance)
            usuario.sesiones.all().delete()
            self.registrar_evento("revocar-rol", usuario, detalles={"rol": rol})


class ClienteViewSet(ViewSetBase):
    queryset = Cliente.objects.select_related("usuario__rol")
    serializer_class = ClienteSerializer
    recurso_permiso = "clientes"
    filterset_fields = ("is_active", "tipo_documento")
    search_fields = ("usuario__nombre", "usuario__correo", "numero_documento", "objetivo")
    ordering_fields = ("usuario__nombre", "created_at", "is_active")

    def get_serializer_class(self):
        if getattr(getattr(self.request.user, "rol", None), "nombre", None) == Rol.Nombre.RECEPCIONISTA:
            return ClienteOperativoSerializer
        return ClienteSerializer

    def validar_escritura(self, serializer):
        self.validar_usuario_relacionado(serializer, "usuario")

    def filtrar_alcance(self, queryset):
        queryset = queryset.filter(
            pk__in=clientes_operativos(self.request.user).values("pk")
        )
        terapeuta_id = self.request.query_params.get(
            "terapeuta"
        ) or self.request.query_params.get("terapeuta_id")
        if terapeuta_id is None:
            return queryset
        if not str(terapeuta_id).isdigit():
            return queryset.none()
        return queryset.filter(
            asignaciones_terapeuta__terapeuta_id=int(terapeuta_id),
            asignaciones_terapeuta__activo=True,
            asignaciones_terapeuta__is_active=True,
            asignaciones_terapeuta__deleted_at__isnull=True,
        ).distinct()

    @action(detail=True, methods=["get"], url_path="asistencias")
    def asistencias(self, request, pk=None):
        if not es_administrador(request.user) and not request.user.tiene_permiso(
            "asistencias:view"
        ):
            raise PermissionDenied("No tienes permiso para consultar asistencias.")
        cliente = self.get_object()
        return self.respuesta_lista(
            cliente.asistencias.filter(deleted_at__isnull=True)
            .select_related("cliente__usuario")
            .order_by("-entrada_at", "-pk"),
            AsistenciaSerializer,
        )

    @action(detail=True, methods=["get"], url_path="planes-entrenamiento")
    def planes_entrenamiento(self, request, pk=None):
        if not es_administrador(request.user) and not request.user.tiene_permiso(
            "planes-entrenamiento:view"
        ):
            raise PermissionDenied(
                "No tienes permiso para consultar planes de entrenamiento."
            )
        cliente = self.get_object()
        return self.respuesta_lista(
            cliente.planes_entrenamiento.filter(deleted_at__isnull=True)
            .select_related("cliente__usuario", "entrenador__usuario")
            .order_by("-fecha_inicio", "-pk"),
            PlanEntrenamientoSerializer,
        )


class EntrenadorViewSet(ViewSetBase):
    queryset = Entrenador.objects.select_related("usuario__rol")
    serializer_class = EntrenadorSerializer
    recurso_permiso = "entrenadores"
    search_fields = ("usuario__nombre", "usuario__correo", "especialidad")
    ordering_fields = ("usuario__nombre", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_perfil(queryset, self.request.user, Rol.Nombre.ENTRENADOR)

    def validar_escritura(self, serializer):
        self.validar_usuario_relacionado(serializer, "usuario")

    @action(detail=True, methods=["get"], url_path="clientes")
    def clientes(self, request, pk=None):
        if not es_administrador(request.user) and not request.user.tiene_permiso(
            "clientes:view"
        ):
            raise PermissionDenied("No tienes permiso para consultar clientes.")
        entrenador = self.get_object()
        return self.respuesta_lista(
            Cliente.objects.filter(
                asignaciones_entrenador__entrenador=entrenador,
                asignaciones_entrenador__activo=True,
                asignaciones_entrenador__is_active=True,
                asignaciones_entrenador__deleted_at__isnull=True,
                deleted_at__isnull=True,
            )
            .select_related("usuario__rol")
            .order_by("usuario__nombre", "pk")
            .distinct(),
            ClienteSerializer,
        )


class TerapeutaViewSet(ViewSetBase):
    queryset = Terapeuta.objects.select_related("usuario__rol")
    serializer_class = TerapeutaSerializer
    recurso_permiso = "terapeutas"
    search_fields = ("usuario__nombre", "usuario__correo", "especialidad")
    ordering_fields = ("usuario__nombre", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_perfil(queryset, self.request.user, Rol.Nombre.TERAPEUTA)

    def validar_escritura(self, serializer):
        self.validar_usuario_relacionado(serializer, "usuario")


class RecepcionistaViewSet(ViewSetBase):
    queryset = Recepcionista.objects.select_related("usuario__rol")
    serializer_class = RecepcionistaSerializer
    recurso_permiso = "recepcionistas"
    search_fields = ("usuario__nombre", "usuario__correo", "turno_preferido")
    ordering_fields = ("usuario__nombre", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_perfil(queryset, self.request.user, Rol.Nombre.RECEPCIONISTA)

    def validar_escritura(self, serializer):
        self.validar_usuario_relacionado(serializer, "usuario")


class AdministradorViewSet(ViewSetBase):
    queryset = Administrador.objects.select_related("usuario__rol")
    serializer_class = AdministradorSerializer
    recurso_permiso = "administradores"
    search_fields = ("usuario__nombre", "usuario__correo", "cargo")
    ordering_fields = ("usuario__nombre", "created_at")
    permission_classes = [IsAuthenticated, TienePermisoRecurso, SoloAdministrador]

    def filtrar_alcance(self, queryset):
        return filtrar_perfil(queryset, self.request.user, Rol.Nombre.ADMINISTRADOR)


class ClienteEntrenadorViewSet(ViewSetBase):
    queryset = ClienteEntrenador.objects.select_related("cliente__usuario", "entrenador__usuario")
    serializer_class = ClienteEntrenadorSerializer
    recurso_permiso = "asignaciones-cliente-entrenador"
    filterset_fields = ("activo", "cliente", "entrenador")
    ordering_fields = ("fecha_inicio", "fecha_fin", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_asignaciones_entrenador(queryset, self.request.user)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer, operativo=True)
        self.validar_usuario_relacionado(serializer, "entrenador")


class ClienteTerapeutaViewSet(ViewSetBase):
    queryset = ClienteTerapeuta.objects.select_related(
        "cliente__usuario", "terapeuta__usuario"
    )
    serializer_class = ClienteTerapeutaSerializer
    recurso_permiso = "clientes-terapeutas"
    filterset_fields = ("activo", "cliente", "terapeuta")
    ordering_fields = ("fecha_inicio", "fecha_fin", "created_at")

    def filtrar_alcance(self, queryset):
        queryset = filtrar_asignaciones_terapeuta(queryset, self.request.user)

        terapeuta_id = self.request.query_params.get(
            "terapeuta"
        ) or self.request.query_params.get("terapeuta_id")
        if terapeuta_id is not None:
            if not str(terapeuta_id).isdigit():
                return queryset.none()
            queryset = queryset.filter(terapeuta_id=int(terapeuta_id))

        cliente_id = self.request.query_params.get("cliente")
        if cliente_id is not None:
            if not str(cliente_id).isdigit():
                return queryset.none()
            queryset = queryset.filter(cliente_id=int(cliente_id))

        activo = self.request.query_params.get("activo")
        if activo is not None:
            normalizado = activo.strip().lower()
            if normalizado in {"true", "1"}:
                queryset = queryset.filter(activo=True)
            elif normalizado in {"false", "0"}:
                queryset = queryset.filter(activo=False)
            else:
                return queryset.none()
        return queryset

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer, operativo=True)
        self.validar_usuario_relacionado(serializer, "terapeuta")


class AsistenciaViewSet(ViewSetBase):
    queryset = Asistencia.objects.select_related("cliente__usuario")
    serializer_class = AsistenciaSerializer
    recurso_permiso = "asistencias"
    filterset_fields = ("cliente",)
    ordering_fields = ("entrada_at", "salida_at", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_clientes(queryset, "cliente", self.request.user, operativo=True)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer, operativo=True)


class EntrenamientoViewSet(ViewSetBase):
    queryset = Entrenamiento.objects.select_related("cliente__usuario", "entrenador__usuario")
    serializer_class = EntrenamientoSerializer
    recurso_permiso = "entrenamientos"
    filterset_fields = ("cliente", "entrenador")
    ordering_fields = ("inicio_at", "fin_at", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_clientes(queryset, "cliente", self.request.user)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer)
        self.validar_usuario_relacionado(serializer, "entrenador")


class EjercicioViewSet(ViewSetBase):
    queryset = Ejercicio.objects.all()
    serializer_class = EjercicioSerializer
    recurso_permiso = "ejercicios"
    filterset_fields = ("grupo_muscular", "is_active")
    search_fields = ("nombre", "descripcion", "grupo_muscular")
    ordering_fields = ("nombre", "grupo_muscular", "created_at")


class PlanEntrenamientoViewSet(ViewSetBase):
    queryset = PlanEntrenamiento.objects.select_related("cliente__usuario", "entrenador__usuario")
    serializer_class = PlanEntrenamientoSerializer
    recurso_permiso = "planes-entrenamiento"
    filterset_fields = ("cliente", "entrenador", "activo")
    search_fields = ("nombre", "objetivo")
    ordering_fields = ("fecha_inicio", "fecha_fin", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_clientes(queryset, "cliente", self.request.user)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer)
        self.validar_usuario_relacionado(serializer, "entrenador")


class PlanEntrenamientoEjercicioViewSet(ViewSetBase):
    queryset = PlanEntrenamientoEjercicio.objects.select_related("plan", "ejercicio")
    serializer_class = PlanEntrenamientoEjercicioSerializer
    recurso_permiso = "planes-entrenamiento-ejercicios"
    filterset_fields = ("plan", "ejercicio")
    # Fila de composición del plan (sin deleted_at ni is_active): DELETE físico.
    politica_borrado = "fisico"

    def filtrar_alcance(self, queryset):
        queryset = queryset.filter(plan__deleted_at__isnull=True)
        return filtrar_clientes(queryset, "plan__cliente", self.request.user)

    def validar_escritura(self, serializer):
        plan = serializer.validated_data.get("plan")
        if plan is None:
            return
        if plan.deleted_at is not None or not clientes_clinicos(
            self.request.user
        ).filter(pk=plan.cliente_id).exists():
            raise ValidationError(
                {"plan": "El plan no pertenece a su alcance de acceso."}
            )


class PlanAlimentacionViewSet(ViewSetBase):
    queryset = PlanAlimentacion.objects.select_related("cliente__usuario", "responsable__usuario")
    serializer_class = PlanAlimentacionSerializer
    recurso_permiso = "planes-alimentacion"
    filterset_fields = ("cliente", "responsable", "activo")
    search_fields = ("nombre", "objetivo")
    ordering_fields = ("fecha_inicio", "fecha_fin", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_clientes(queryset, "cliente", self.request.user)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer)
        self.validar_usuario_relacionado(serializer, "responsable")


class ComidaViewSet(ViewSetBase):
    queryset = Comida.objects.select_related("plan_alimentacion")
    serializer_class = ComidaSerializer
    recurso_permiso = "comidas"
    filterset_fields = ("plan_alimentacion", "tipo")
    search_fields = ("nombre", "descripcion")
    ordering_fields = ("nombre", "hora_sugerida", "created_at")

    def filtrar_alcance(self, queryset):
        queryset = queryset.filter(plan_alimentacion__deleted_at__isnull=True)
        return filtrar_clientes(
            queryset, "plan_alimentacion__cliente", self.request.user
        )

    def validar_escritura(self, serializer):
        plan = serializer.validated_data.get("plan_alimentacion")
        if plan is None:
            return
        if plan.deleted_at is not None or not clientes_clinicos(
            self.request.user
        ).filter(pk=plan.cliente_id).exists():
            raise ValidationError(
                {"plan_alimentacion": "El plan no pertenece a su alcance de acceso."}
            )


class RendererFotoPrivada(renderers.BaseRenderer):
    """Permite que el navegador pida la imagen con ``Accept: image/*``."""

    media_type = "*/*"
    format = "bin"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class RegistroComidaViewSet(ViewSetBase):
    queryset = RegistroComida.objects.select_related("cliente__usuario", "comida", "revisado_por__usuario")
    serializer_class = RegistroComidaSerializer
    recurso_permiso = "registros-comida"
    filterset_fields = ("cliente", "verificado")
    ordering_fields = ("registrado_at", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_clientes(queryset, "cliente", self.request.user)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer)

    def objeto_permitido(self, request, obj):
        if not super().objeto_permitido(request, obj):
            return False
        if es_administrador(request.user):
            return True
        if getattr(request.user, "rol", None) and request.user.rol.nombre == Rol.Nombre.CLIENTE:
            return not obj.verificado
        return True

    def get_renderers(self):
        if getattr(self, "action", None) == "foto":
            return [RendererFotoPrivada()]
        return super().get_renderers()

    @action(detail=True, methods=["get"], url_path="foto")
    def foto(self, request, pk=None):
        """Entrega la foto privada solo a usuarios con permiso de lectura."""
        registro = self.get_object()
        if not registro.foto:
            raise NotFound("El registro no tiene una foto adjunta.")

        try:
            archivo = registro.foto.storage.open(registro.foto.name, "rb")
        except (FileNotFoundError, OSError) as error:
            raise NotFound("La foto adjunta ya no está disponible.") from error

        tipo_contenido = mimetypes.guess_type(registro.foto.name)[0] or "application/octet-stream"
        respuesta = FileResponse(archivo, content_type=tipo_contenido)
        respuesta["Content-Disposition"] = (
            f'inline; filename="{Path(registro.foto.name).name}"'
        )
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta


class NotificacionViewSet(ViewSetBase):
    queryset = Notificacion.objects.select_related("usuario__rol")
    serializer_class = NotificacionSerializer
    recurso_permiso = "notificaciones"
    filterset_fields = ("usuario", "estado", "tipo")
    ordering_fields = ("created_at", "programada_at", "enviada_at")

    def filtrar_alcance(self, queryset):
        if es_administrador(self.request.user):
            return queryset
        if isinstance(self.request.user, Usuario):
            return queryset.filter(usuario_id=self.request.user.pk)
        return queryset.none()

    @action(detail=True, methods=["post"], url_path="leer")
    def leer(self, request, pk=None):
        notificacion = self.get_object()
        if notificacion.leida_at is None:
            notificacion.leida_at = timezone.now()
            notificacion.save(update_fields=["leida_at", "updated_at"])
        return Response(self.get_serializer(notificacion).data)

    @action(detail=False, methods=["post"], url_path="marcar-todas")
    def marcar_todas(self, request):
        if not isinstance(request.user, Usuario):
            raise ValidationError({"detalle": "Esta operación requiere un usuario propio."})
        cantidad = Notificacion.objects.filter(
            usuario=request.user,
            deleted_at__isnull=True,
            is_active=True,
            leida_at__isnull=True,
        ).update(leida_at=timezone.now(), updated_at=timezone.now())
        return Response(
            {"mensaje": "Notificaciones marcadas como leídas.", "cantidad": cantidad}
        )


class EventoAuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de auditoría, reservada a administradores."""

    queryset = EventoAuditoria.objects.select_related("actor")
    serializer_class = EventoAuditoriaSerializer
    permission_classes = [IsAuthenticated, TienePermisoRecurso]
    recurso_permiso = "usuarios"
    filterset_fields = ("actor", "accion", "recurso")
    search_fields = ("recurso", "objeto_id")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        queryset = super().get_queryset()
        if es_administrador(self.request.user):
            return queryset
        return queryset.none()

