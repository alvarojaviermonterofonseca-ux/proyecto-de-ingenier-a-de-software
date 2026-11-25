"""ViewSets CRUD para todos los recursos de Gym Control Pro."""

import calendar
import csv
import io
import json
import mimetypes
from collections import Counter
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import logout as django_logout
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
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
    Recurso,
    Recepcionista,
    RegistroComida,
    Rol,
    RolPermiso,
    RolRecurso,
    Sesion,
    Terapeuta,
    Usuario,
    UsuarioRol,
)
from .audit import registrar_evento
from .permissions import (
    SoloAdministrador,
    TienePermisoRecurso,
    es_administrador,
)
from .alertas import alerta_nuevo_gasto, generar_alertas_de
from .reportes import MAX_DIAS_RANGO, TIPOS_REPORTE, a_excel, a_pdf, construir_reporte
from .tenancy import es_plataforma, filtrar_por_gimnasio, gimnasio_id_de
from .scoping import (
    clientes_clinicos,
    clientes_operativos,
    filtrar_asignaciones_entrenador,
    filtrar_asignaciones_terapeuta,
    filtrar_clientes,
    filtrar_perfil,
    roles_efectivos_nombres,
    usuarios_visibles,
)
from .resource_aliases import get_all_aliases, get_alias, resolve_name, set_alias
from .resources import RECURSOS_API, RECURSOS_MENU
from .serializers import (
    AdministradorSerializer,
    AlertaSerializer,
    AsistenciaSerializer,
    CategoriaGastoSerializer,
    ClienteEntrenadorSerializer,
    ClienteOperativoSerializer,
    ClienteSerializer,
    ClienteTerapeutaSerializer,
    ComidaSerializer,
    EjercicioSerializer,
    EntrenadorSerializer,
    EntrenamientoSerializer,
    EventoAuditoriaSerializer,
    GastoSerializer,
    GimnasioConfiguracionSerializer,
    LoginSerializer,
    MembresiaSerializer,
    MetodoPagoSerializer,
    NotificacionSerializer,
    PagoSerializer,
    PerfilActualPasswordSerializer,
    PerfilActualUpdateSerializer,
    PERFIL_PROPIO_SERIALIZERS,
    PermisoSerializer,
    PermisosRolPayloadSerializer,
    PlanAlimentacionSerializer,
    PlanEntrenamientoEjercicioSerializer,
    PlanEntrenamientoSerializer,
    RecepcionistaSerializer,
    RegistroComidaSerializer,
    RegistroPublicoSerializer,
    RolesUsuarioPayloadSerializer,
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
    existe_otro_administrador_activo,
)


def usuarios_con_rol(rol):
    return Usuario.objects.filter(
        Q(rol=rol)
        | Q(
            asignaciones_usuarios__rol=rol,
            asignaciones_usuarios__activo=True,
        )
    ).distinct()


def _sumar_meses(fecha, meses):
    """Suma meses a una fecha; si el día no existe usa el último del mes."""
    indice = fecha.month - 1 + meses
    anio = fecha.year + indice // 12
    mes = indice % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


PERIODOS_MESES_DASHBOARD = (3, 6, 12, 24)
PERIODOS_DIAS_DASHBOARD = (7, 14, 30, 90)


def _periodo_param(request, nombre, permitidos, por_defecto):
    """Lee un período entero de la URL y lo valida contra ``permitidos``."""
    valor = request.query_params.get(nombre)
    if valor in (None, ""):
        return por_defecto
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        numero = None
    if numero not in permitidos:
        opciones = ", ".join(str(opcion) for opcion in permitidos)
        raise ValidationError({nombre: f"Valor no permitido. Use uno de: {opciones}."})
    return numero


def _fecha_param(request, nombre):
    """Lee una fecha ``AAAA-MM-DD`` de la URL; responde 400 si no es válida."""
    valor = request.query_params.get(nombre)
    if not valor:
        return None
    try:
        fecha = parse_date(valor)
    except ValueError:
        fecha = None
    if fecha is None:
        raise ValidationError({nombre: "Use una fecha válida con formato AAAA-MM-DD."})
    return fecha


def _inicio_del_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


def _entero_param(datos, nombre, minimo, maximo, predeterminado=None):
    """Entero acotado tomado del cuerpo de la petición; responde 400 si no lo es."""
    valor = datos.get(nombre, predeterminado)
    if isinstance(valor, bool):
        valor = None
    try:
        valor = int(valor)
    except (TypeError, ValueError) as error:
        raise ValidationError({nombre: "Debe ser un número entero."}) from error
    if not minimo <= valor <= maximo:
        raise ValidationError({nombre: f"Debe estar entre {minimo} y {maximo}."})
    return valor


def _es_numero(texto):
    try:
        float(texto)
    except ValueError:
        return False
    return True


def _valor_csv(valor):
    if valor is None:
        return ""
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)
    texto = str(valor)
    # Excel y LibreOffice ejecutan como fórmula las celdas que empiezan por
    # estos caracteres; el apóstrofo las deja como texto.
    if texto[:1] in ("=", "+", "-", "@", "\t", "\r") and not _es_numero(texto):
        return "'" + texto
    return texto


def respuesta_csv(filas, nombre):
    """Genera una descarga CSV a partir de una lista de diccionarios."""
    buffer = io.StringIO()
    if filas:
        campos = list(filas[0].keys())
        escritor = csv.DictWriter(buffer, fieldnames=campos)
        escritor.writeheader()
        for fila in filas:
            escritor.writerow(
                {campo: _valor_csv(fila.get(campo)) for campo in campos}
            )
    # La marca BOM hace que Excel lea el archivo como UTF-8 y no rompa las tildes.
    respuesta = HttpResponse(
        "\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8"
    )
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.csv"'
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


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


class RegistroView(APIView):
    """Registro público: crea una cuenta con rol de cliente y abre sesión."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "registro"

    @extend_schema(
        request=RegistroPublicoSerializer,
        responses={
            201: OpenApiResponse(
                description="Cuenta creada; devuelve token y datos del usuario."
            )
        },
        auth=[],
    )
    def post(self, request):
        serializer = RegistroPublicoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        token, sesion = Sesion.crear_para_usuario(usuario)
        return Response(
            {
                "mensaje": "Cuenta creada correctamente.",
                "token": token,
                "tipo_token": "Bearer",
                "expira_at": sesion.expira_at,
                "usuario": UsuarioReadSerializer(
                    usuario, context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED,
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
        request=OpenApiTypes.OBJECT,
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
        roles = roles_efectivos_nombres(usuario)
        rol = getattr(getattr(usuario, "rol", None), "nombre", None)
        es_cliente = Rol.Nombre.CLIENTE in roles
        es_recepcionista = Rol.Nombre.RECEPCIONISTA in roles

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
        notificaciones = filtrar_por_gimnasio(notificaciones, usuario)
        if not es_administrador(usuario):
            notificaciones = notificaciones.filter(usuario=usuario)

        inicio_dia = timezone.localtime().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fin_dia = inicio_dia + timedelta(days=1)
        inicio_semana = inicio_dia - timedelta(days=inicio_dia.weekday())

        # El cliente ve su propio historial aunque su rol no tenga
        # ``asistencias:view``: el alcance ya lo limita a su perfil.
        puede_ver_asistencias = es_cliente or self._puede("asistencias:view")
        entradas_semana = (
            list(
                asistencias.filter(entrada_at__gte=inicio_semana).values_list(
                    "entrada_at", flat=True
                )
            )
            if puede_ver_asistencias
            else []
        )
        dias_semana = []
        for desplazamiento, etiqueta in enumerate(
            ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
        ):
            fecha = (inicio_semana + timedelta(days=desplazamiento)).date()
            dias_semana.append(
                {
                    "fecha": fecha.isoformat(),
                    "etiqueta": etiqueta,
                    "total": sum(
                        1
                        for entrada in entradas_semana
                        if timezone.localtime(entrada).date() == fecha
                    ),
                }
            )

        asistencia_abierta = None
        if es_cliente:
            abierta = (
                asistencias.filter(salida_at__isnull=True)
                .order_by("-entrada_at", "-pk")
                .first()
            )
            if abierta is not None:
                asistencia_abierta = {
                    "id": abierta.pk,
                    "entrada_at": abierta.entrada_at,
                }

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
            "visitas_semana": len(entradas_semana),
            "visitas_semana_dias": dias_semana,
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
                filtrar_por_gimnasio(
                    EventoAuditoria.objects.select_related("actor"), usuario
                ).order_by("-created_at")[:8],
                many=True,
                context=contexto,
            ).data

        return Response(
            {
                "rol_principal": rol,
                "es_cliente": es_cliente,
                "metricas": metricas,
                "asistencia_abierta": asistencia_abierta,
                "asistencias_recientes": asistencias_recientes,
                "notificaciones_recientes": notificaciones_recientes,
                "actividad_reciente": actividad_reciente,
            }
        )


class DashboardFinancieroView(APIView):
    """
    Dashboard financiero y administrativo completo para administradores.

    Proporciona métricas consolidadas de clientes, asistencias, ingresos,
    gastos, membresías y gráficas para visualización.
    Solo accesible para administradores del gimnasio.
    """

    permission_classes = [IsAuthenticated]

    def _puede(self, permiso):
        usuario = self.request.user
        if not isinstance(usuario, Usuario):
            return bool(getattr(usuario, "is_staff", False))
        return usuario.tiene_permiso(permiso)

    @extend_schema(responses={200: OpenApiResponse(description="Dashboard financiero completo.")})
    def get(self, request):
        usuario = request.user

        # Solo administradores pueden ver el dashboard financiero
        if not es_administrador(usuario):
            raise PermissionDenied("Solo administradores pueden acceder al dashboard financiero.")

        # Períodos de las gráficas: ``?meses=`` para series mensuales y
        # ``?dias=`` para asistencias diarias. Se validan contra listas cerradas.
        num_meses = _periodo_param(request, "meses", PERIODOS_MESES_DASHBOARD, 12)
        num_dias = _periodo_param(request, "dias", PERIODOS_DIAS_DASHBOARD, 30)

        # Las membresías solo calculan su estado al crearse: se ponen al día
        # antes de contar para que "por vencer" y "vencidas" sean reales.
        # Pone al día estados de membresía y alertas del gimnasio antes de
        # contar, para que "por vencer", "vencidas" y las alertas sean reales.
        generar_alertas_de(usuario)

        # Todo se calcula sobre el gimnasio del usuario autenticado.
        clientes = clientes_operativos(usuario)
        usuarios = usuarios_visibles(usuario)

        # Fechas de referencia
        ahora = timezone.localtime()
        inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        fin_dia = inicio_dia + timedelta(days=1)
        inicio_semana = inicio_dia - timedelta(days=inicio_dia.weekday())
        inicio_mes = inicio_dia.replace(day=1)
        inicio_anio = inicio_dia.replace(month=1, day=1)

        # =====================================================================
        # MÉTRICAS DE CLIENTES
        # =====================================================================
        clientes_base = clientes.filter(is_active=True, deleted_at__isnull=True)
        membresias_activas = Membresia.objects.filter(
            cliente__in=clientes_base,
            estado__in=[Membresia.Estado.ACTIVA, Membresia.Estado.POR_VENCER],
            deleted_at__isnull=True,
        )

        hoy = timezone.localdate()
        clientes_nuevos_dia = clientes_base.filter(created_at__gte=inicio_dia, created_at__lt=fin_dia).count()
        clientes_nuevos_mes = clientes_base.filter(created_at__gte=inicio_mes).count()
        clientes_por_vencer = membresias_activas.filter(
            estado=Membresia.Estado.POR_VENCER,
            fecha_fin__lte=hoy + timedelta(days=7),
        ).count()
        # Clientes cuya membresía venció y no tienen otra vigente.
        vencidas_sin_vigente = Membresia.objects.filter(
            cliente__in=clientes_base,
            estado=Membresia.Estado.VENCIDA,
            deleted_at__isnull=True,
        ).exclude(cliente__in=membresias_activas.values("cliente"))
        clientes_vencidos = vencidas_sin_vigente.values("cliente").distinct().count()
        clientes_sin_renovar = (
            vencidas_sin_vigente.filter(fecha_fin__gte=hoy - timedelta(days=30))
            .values("cliente")
            .distinct()
            .count()
        )

        metricas_clientes = {
            "total_registrados": clientes_base.count(),
            "activos": clientes_base.filter(
                pk__in=membresias_activas.values("cliente")
            ).count(),
            "inactivos": clientes_base.exclude(
                pk__in=membresias_activas.values("cliente")
            ).count(),
            "membresias_vencidas": clientes_vencidos,
            "nuevos_dia": clientes_nuevos_dia,
            "nuevos_mes": clientes_nuevos_mes,
            "por_vencer": clientes_por_vencer,
            "sin_renovar": clientes_sin_renovar,
        }

        # =====================================================================
        # MÉTRICAS DE ASISTENCIAS
        # =====================================================================
        asistencias = Asistencia.objects.filter(
            cliente__in=clientes_base,
            is_active=True,
            deleted_at__isnull=True,
        )

        asistencias_hoy = asistencias.filter(entrada_at__gte=inicio_dia, entrada_at__lt=fin_dia)
        asistencias_semana = asistencias.filter(entrada_at__gte=inicio_semana)
        asistencias_mes = asistencias.filter(entrada_at__gte=inicio_mes)

        # Día y hora se calculan en Python con la hora local. Así no dependen de
        # las tablas de zonas horarias del motor: MySQL las necesita para
        # ``__date`` y ``__hour`` y, si no están cargadas, devuelve vacío.
        hace_30_dias = inicio_dia - timedelta(days=29)
        asistencias_30 = asistencias.filter(entrada_at__gte=hace_30_dias)
        inicio_ventana = inicio_dia - timedelta(days=max(num_dias, 30) - 1)
        entradas_ventana = [
            timezone.localtime(momento)
            for momento in asistencias.filter(entrada_at__gte=inicio_ventana).values_list(
                "entrada_at", flat=True
            )
        ]
        fecha_30 = hace_30_dias.date()
        entradas_30 = [momento for momento in entradas_ventana if momento.date() >= fecha_30]
        asistencias_por_fecha_ventana = Counter(momento.date() for momento in entradas_ventana)
        asistencias_por_fecha = Counter(momento.date() for momento in entradas_30)
        asistencias_por_hora = Counter(momento.hour for momento in entradas_30)
        promedio_diario = round(
            len(entradas_30) / max(len(asistencias_por_fecha), 1), 1
        )

        # Horarios de mayor/menor afluencia (por hora)
        horas_por_afluencia = sorted(
            asistencias_por_hora.items(), key=lambda par: (-par[1], par[0])
        )
        hora_pico = horas_por_afluencia[0][0] if horas_por_afluencia else None
        hora_valle = horas_por_afluencia[-1][0] if horas_por_afluencia else None

        # Top clientes que más asisten
        top_clientes_asistencia = (
            asistencias_30.values("cliente__usuario__nombre", "cliente_id")
            .annotate(total=models.Count("id"))
            .order_by("-total")[:10]
        )

        metricas_asistencias = {
            "hoy": asistencias_hoy.count(),
            "semana": asistencias_semana.count(),
            "mes": asistencias_mes.count(),
            "promedio_diario": promedio_diario,
            "hora_pico": f"{hora_pico:02d}:00" if hora_pico is not None else None,
            "hora_valle": f"{hora_valle:02d}:00" if hora_valle is not None else None,
            "top_clientes": list(top_clientes_asistencia),
        }

        # =====================================================================
        # MÉTRICAS FINANCIERAS
        # =====================================================================
        # Los pagos se toman por gimnasio y no por clientes activos: el dinero
        # recibido de un cliente que luego se dio de baja sigue siendo ingreso.
        pagos = filtrar_por_gimnasio(Pago.objects.filter(deleted_at__isnull=True), usuario)
        # Los gastos anulados (cancelados) no restan de la ganancia.
        gastos = filtrar_por_gimnasio(
            Gasto.objects.filter(deleted_at__isnull=True), usuario
        ).exclude(estado=Gasto.Estado.CANCELADO)

        # Ingresos (solo pagos completados)
        pagos_completados = pagos.filter(estado=Pago.Estado.COMPLETADO)
        pagos_pendientes = pagos.filter(estado=Pago.Estado.PENDIENTE)

        ingresos_dia = pagos_completados.filter(fecha_pago__gte=inicio_dia, fecha_pago__lt=fin_dia).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")
        ingresos_semana = pagos_completados.filter(fecha_pago__gte=inicio_semana).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")
        ingresos_mes = pagos_completados.filter(fecha_pago__gte=inicio_mes).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")
        ingresos_anio = pagos_completados.filter(fecha_pago__gte=inicio_anio).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")

        pendientes_dia = pagos_pendientes.filter(fecha_pago__gte=inicio_dia, fecha_pago__lt=fin_dia).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")
        pendientes_mes = pagos_pendientes.filter(fecha_pago__gte=inicio_mes).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")

        # Gastos
        gastos_dia = gastos.filter(fecha__gte=inicio_dia, fecha__lt=fin_dia).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")
        gastos_mes = gastos.filter(fecha__gte=inicio_mes).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")
        gastos_anio = gastos.filter(fecha__gte=inicio_anio).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")

        # Ganancia neta = Ingresos completados - Gastos
        ganancia_dia = ingresos_dia - gastos_dia
        ganancia_mes = ingresos_mes - gastos_mes
        ganancia_anio = ingresos_anio - gastos_anio

        # Distribución de ingresos por concepto
        ingresos_por_concepto = list(
            pagos_completados.filter(fecha_pago__gte=inicio_mes)
            .values("concepto")
            .annotate(total=Sum("valor"), count=models.Count("id"))
            .order_by("-total")
        )

        # Distribución de gastos por categoría
        gastos_por_categoria = list(
            gastos.filter(fecha__gte=inicio_mes)
            .values("categoria__nombre", "categoria__color")
            .annotate(total=Sum("valor"), count=models.Count("id"))
            .order_by("-total")
        )

        metricas_financieras = {
            "ingresos": {
                "dia": float(ingresos_dia),
                "semana": float(ingresos_semana),
                "mes": float(ingresos_mes),
                "anio": float(ingresos_anio),
                "pendientes_dia": float(pendientes_dia),
                "pendientes_mes": float(pendientes_mes),
                "por_concepto": ingresos_por_concepto,
            },
            "gastos": {
                "dia": float(gastos_dia),
                "mes": float(gastos_mes),
                "anio": float(gastos_anio),
                "por_categoria": gastos_por_categoria,
            },
            "ganancia_neta": {
                "dia": float(ganancia_dia),
                "mes": float(ganancia_mes),
                "anio": float(ganancia_anio),
            },
        }

        # =====================================================================
        # MÉTRICAS DE MEMBRESÍAS
        # =====================================================================
        membresias = Membresia.objects.filter(
            cliente__in=clientes_base,
            deleted_at__isnull=True,
        )

        membresias_mes = membresias.filter(fecha_inicio__gte=inicio_mes)
        renovaciones_mes = membresias.filter(
            fecha_ultima_renovacion__gte=inicio_mes,
            fecha_ultima_renovacion__isnull=False,
        )

        metricas_membresias = {
            "activas": membresias.filter(estado__in=[Membresia.Estado.ACTIVA, Membresia.Estado.POR_VENCER]).count(),
            "vencidas": membresias.filter(estado=Membresia.Estado.VENCIDA).count(),
            "por_vencer": membresias.filter(estado=Membresia.Estado.POR_VENCER).count(),
            "nuevas_mes": membresias_mes.count(),
            "renovaciones_mes": renovaciones_mes.count(),
            "canceladas": membresias.filter(estado=Membresia.Estado.CANCELADA).count(),
            "ingresos_membresias": float(
                pagos_completados.filter(
                    concepto__in=[Pago.Concepto.MEMBRESIA, Pago.Concepto.RENOVACION],
                    fecha_pago__gte=inicio_mes,
                ).aggregate(total=Sum("valor"))["total"] or Decimal("0")
            ),
            "por_tipo": dict(
                membresias.filter(estado__in=[Membresia.Estado.ACTIVA, Membresia.Estado.POR_VENCER])
                .values("tipo")
                .annotate(count=models.Count("id"))
                .values_list("tipo", "count")
            ),
        }

        # =====================================================================
        # DATOS PARA GRÁFICAS
        # =====================================================================

        # Los ``num_meses`` meses terminan en el actual. Cada serie se resuelve
        # con una sola consulta de agregados condicionales, no una por mes.
        meses = [_sumar_meses(inicio_mes, -i) for i in range(num_meses - 1, -1, -1)]
        rangos = [(mes, _sumar_meses(mes, 1)) for mes in meses]

        def por_mes(queryset, campo, agregado, fechas=False):
            return queryset.aggregate(
                **{
                    f"m{i}": agregado(
                        Q(
                            **{
                                f"{campo}__gte": desde.date() if fechas else desde,
                                f"{campo}__lt": hasta.date() if fechas else hasta,
                            }
                        )
                    )
                    for i, (desde, hasta) in enumerate(rangos)
                }
            )

        ingresos_por_mes = por_mes(
            pagos_completados, "fecha_pago", lambda filtro: Sum("valor", filter=filtro)
        )
        gastos_por_mes = por_mes(
            gastos, "fecha", lambda filtro: Sum("valor", filter=filtro), fechas=True
        )
        clientes_por_mes = por_mes(
            clientes_base, "created_at", lambda filtro: Count("pk", filter=filtro)
        )

        # 1. Ingresos vs Gastos (últimos 12 meses)
        ingresos_gastos_mensual = []
        for i, mes in enumerate(meses):
            ing = ingresos_por_mes[f"m{i}"] or Decimal("0")
            gas = gastos_por_mes[f"m{i}"] or Decimal("0")
            ingresos_gastos_mensual.append({
                "mes": mes.strftime("%Y-%m"),
                "ingresos": float(ing),
                "gastos": float(gas),
                "ganancia": float(ing - gas),
            })

        # 2. Ganancias por mes (últimos 12 meses)
        ganancias_mensual = [
            {"mes": item["mes"], "ganancia": item["ganancia"]}
            for item in ingresos_gastos_mensual
        ]

        # 3. Asistencias por día (últimos ``num_dias`` días)
        asistencias_por_dia = []
        for i in range(num_dias - 1, -1, -1):
            fecha = (inicio_dia - timedelta(days=i)).date()
            asistencias_por_dia.append({
                "fecha": fecha.isoformat(),
                "total": asistencias_por_fecha_ventana.get(fecha, 0),
            })

        # 4. Crecimiento de clientes (últimos 12 meses)
        crecimiento_clientes = [
            {"mes": mes.strftime("%Y-%m"), "nuevos": clientes_por_mes[f"m{i}"] or 0}
            for i, mes in enumerate(meses)
        ]

        # 5. Distribución de membresías
        distribucion_membresias = list(
            membresias.filter(estado__in=[Membresia.Estado.ACTIVA, Membresia.Estado.POR_VENCER])
            .values("tipo")
            .annotate(count=models.Count("id"))
        )

        # 6. Activos vs Inactivos
        activos_count = metricas_clientes["activos"]
        inactivos_count = metricas_clientes["inactivos"]

        # 7. Horarios de mayor asistencia (por hora)
        horarios_formateados = [
            {"hora": f"{hora:02d}:00", "total": total}
            for hora, total in sorted(asistencias_por_hora.items())
        ]

        graficas = {
            "ingresos_vs_gastos": ingresos_gastos_mensual,
            "ganancias_mensuales": ganancias_mensual,
            "asistencias_por_dia": asistencias_por_dia,
            "crecimiento_clientes": crecimiento_clientes,
            "distribucion_membresias": distribucion_membresias,
            "clientes_activos_vs_inactivos": {
                "activos": activos_count,
                "inactivos": inactivos_count,
            },
            "horarios_asistencia": horarios_formateados,
            "periodo": {"meses": num_meses, "dias": num_dias},
        }

        # =====================================================================
        # ALERTAS RECIENTES
        # =====================================================================
        alertas_recientes = (
            filtrar_por_gimnasio(Alerta.objects.por_prioridad(), usuario)
            .filter(deleted_at__isnull=True, leida=False)
            .select_related("cliente__usuario", "membresia", "pago", "gasto", "leida_por")[:10]
        )

        alertas_data = AlertaSerializer(alertas_recientes, many=True, context={"request": request}).data

        return Response({
            "metricas_clientes": metricas_clientes,
            "metricas_asistencias": metricas_asistencias,
            "metricas_financieras": metricas_financieras,
            "metricas_membresias": metricas_membresias,
            "graficas": graficas,
            "alertas_recientes": alertas_data,
        })


class FiltroFechasMixin:
    """Añade ``?fecha_desde=`` y ``?fecha_hasta=`` (inclusive) al listado.

    Se aplica en ``filter_queryset``, así que el listado, la exportación y las
    estadísticas del recurso filtran exactamente igual.
    """

    campo_fecha = None
    campo_fecha_con_hora = False

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        desde = _fecha_param(self.request, "fecha_desde")
        hasta = _fecha_param(self.request, "fecha_hasta")
        if desde and hasta and desde > hasta:
            raise ValidationError(
                {"fecha_hasta": "No puede ser anterior a fecha_desde."}
            )
        campo = self.campo_fecha
        if desde:
            valor = _inicio_del_dia(desde) if self.campo_fecha_con_hora else desde
            queryset = queryset.filter(**{f"{campo}__gte": valor})
        if hasta:
            if self.campo_fecha_con_hora:
                limite = _inicio_del_dia(hasta + timedelta(days=1))
                queryset = queryset.filter(**{f"{campo}__lt": limite})
            else:
                queryset = queryset.filter(**{f"{campo}__lte": hasta})
        return queryset


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
    accion_permiso = None
    accion_permiso_por_accion = {"exportar": "export"}
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

    def filtrar_gimnasio(self, queryset):
        """Aísla los datos por gimnasio antes de cualquier otro alcance."""
        return filtrar_por_gimnasio(queryset, self.request.user)

    def get_queryset(self):
        return self.filtrar_alcance(self.filtrar_gimnasio(self.queryset_base()))

    def objeto_permitido(self, request, obj):
        if es_administrador(request.user):
            return True
        return self.get_queryset().filter(pk=obj.pk).exists()

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
            instancia = self.filtrar_gimnasio(modelo.objects.all()).get(pk=pk)
        except (modelo.DoesNotExist, ValueError) as error:
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

    @extend_schema(
        responses={200: OpenApiResponse(description="Descarga CSV del listado.")},
        description=(
            "Exporta el listado visible para el usuario en CSV. Requiere el "
            "permiso export del recurso y respeta el mismo alcance que el listado."
        ),
    )
    @action(detail=False, methods=["get"], url_path="exportar")
    def exportar(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        filas = self.get_serializer(queryset, many=True).data
        return respuesta_csv(filas, self.recurso_permiso or "exportacion")


class RolViewSet(ViewSetBase):
    # La matriz se precarga en get_queryset, filtrada por gimnasio.
    queryset = Rol.objects.prefetch_related("asignaciones_usuarios")
    serializer_class = RolSerializer
    recurso_permiso = "roles"
    filterset_fields = ("is_active",)
    search_fields = ("nombre", "descripcion")
    ordering_fields = ("nombre", "created_at")
    # El catálogo de roles y su matriz se gestionan con permisos RBAC.
    permission_classes = [IsAuthenticated, TienePermisoRecurso]
    # Catálogo sin deleted_at: el DELETE desactiva el rol y lo oculta.
    politica_borrado = "logico"

    def get_queryset(self):
        queryset = super().get_queryset()
        gimnasio_id = gimnasio_id_de(self.request.user)
        # Cada gimnasio ve su propia matriz; el personal de la plataforma, la
        # plantilla que reciben los gimnasios nuevos.
        filtro = {"gimnasio_id": gimnasio_id} if gimnasio_id else {"gimnasio__isnull": True}
        return queryset.prefetch_related(
            models.Prefetch(
                "permisos_asignados",
                queryset=RolPermiso.objects.filter(**filtro).select_related("permiso"),
            ),
            models.Prefetch(
                "recursos_asignados",
                queryset=RolRecurso.objects.filter(**filtro).select_related("recurso"),
            ),
        )

    def _proteger_rol_del_sistema(self, rol, accion):
        if rol.gimnasio_id is None and not es_plataforma(self.request.user):
            raise PermissionDenied(
                f"Los roles del sistema son compartidos por todos los gimnasios y no "
                f"se pueden {accion} desde un gimnasio. Puede cambiar sus permisos."
            )

    def perform_create(self, serializer):
        # Un rol creado desde un gimnasio es propio de ese gimnasio.
        instance = serializer.save(gimnasio_id=gimnasio_id_de(self.request.user))
        self.registrar_evento("crear", instance)
        return instance

    def perform_update(self, serializer):
        self._proteger_rol_del_sistema(serializer.instance, "modificar")
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
        self._proteger_rol_del_sistema(instance, "eliminar")
        usuarios_principales = instance.usuarios.filter(
            is_active=True, deleted_at__isnull=True
        )
        if usuarios_principales.exists():
            raise ValidationError(
                {
                    "detalle": (
                        "No puede eliminar un rol que es el rol principal de "
                        "usuarios activos. Reasigne primero esos usuarios."
                    )
                }
            )
        usuarios = list(usuarios_con_rol(instance).values_list("pk", flat=True))
        with transaction.atomic():
            super().perform_destroy(instance)
            Sesion.objects.filter(usuario_id__in=usuarios).delete()

    @extend_schema(
        methods=["GET"],
        operation_id="rol_permisos_consultar",
        responses={200: OpenApiResponse(description="Permisos asignados al rol.")},
    )
    @extend_schema(
        methods=["PUT"],
        operation_id="rol_permisos_reemplazar",
        request=PermisosRolPayloadSerializer,
        responses={200: OpenApiResponse(description="Permisos del rol actualizados.")},
    )
    @action(detail=True, methods=["get", "put"], url_path="permisos")
    def permisos(self, request, pk=None):
        """Consulta o reemplaza atómicamente los permisos de un rol.

        La matriz es por gimnasio: solo se leen y cambian las concesiones del
        gimnasio del usuario autenticado.
        """
        rol = self.get_object()
        gimnasio_id = gimnasio_id_de(request.user)
        del_gimnasio = (
            {"gimnasio_id": gimnasio_id} if gimnasio_id else {"gimnasio__isnull": True}
        )

        if request.method == "PUT":
            if not (es_administrador(request.user) or request.user.tiene_permiso("roles:edit")):
                raise PermissionDenied(
                    "Solo un usuario con permiso para modificar roles puede actualizar sus permisos."
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
                # Recursos que tenía el rol antes del cambio
                recursos_antes = set(
                    RolRecurso.objects.filter(
                        rol=rol, recurso__is_active=True, **del_gimnasio
                    ).values_list("recurso__nombre", flat=True)
                )
                RolPermiso.objects.filter(rol=rol, **del_gimnasio).exclude(
                    permiso__in=permisos
                ).delete()
                existentes = set(
                    RolPermiso.objects.filter(rol=rol, **del_gimnasio).values_list(
                        "permiso_id", flat=True
                    )
                )
                RolPermiso.objects.bulk_create(
                    [
                        RolPermiso(rol=rol, permiso=permiso, gimnasio_id=gimnasio_id)
                        for permiso in permisos
                        if permiso.pk not in existentes
                    ]
                )
                # ``bulk_create`` no ejecuta ``RolPermiso.save()``, así que
                # sincronizamos explícitamente el puente rol↔recurso.
                recursos = {
                    permiso.recurso: permiso for permiso in permisos
                }
                for nombre_recurso in recursos:
                    recurso, _ = Recurso.objects.get_or_create(nombre=nombre_recurso)
                    RolRecurso.objects.get_or_create(
                        rol=rol, recurso=recurso, gimnasio_id=gimnasio_id
                    )
                # Eliminar RolRecurso de recursos que ya no tienen permisos en este rol
                recursos_despues = set(recursos.keys())
                recursos_a_eliminar = recursos_antes - recursos_despues
                if recursos_a_eliminar:
                    RolRecurso.objects.filter(
                        rol=rol, recurso__nombre__in=recursos_a_eliminar, **del_gimnasio
                    ).delete()
                registrar_evento(
                    request,
                    "actualizar-permisos",
                    "roles",
                    rol,
                    detalles={"permisos": codigos},
                )

        asignaciones = RolPermiso.objects.select_related("permiso").filter(
            rol=rol, permiso__is_active=True, **del_gimnasio
        )
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


class PermisoViewSet(ViewSetBase):
    queryset = Permiso.objects.all()
    serializer_class = PermisoSerializer
    recurso_permiso = "permisos"
    permission_classes = [IsAuthenticated, TienePermisoRecurso]
    filterset_fields = ("recurso", "accion", "is_active")
    search_fields = ("codigo", "descripcion")
    ordering_fields = ("codigo", "recurso", "accion")
    # Catálogo sin deleted_at: el DELETE desactiva el permiso y lo oculta.
    politica_borrado = "logico"

    def check_permissions(self, request):
        super().check_permissions(request)
        # El catálogo de permisos es de toda la plataforma: cambiarlo desde un
        # gimnasio alteraría a los demás. Los gimnasios lo consultan y asignan
        # permisos a sus roles desde la matriz.
        if request.method not in ("GET", "HEAD", "OPTIONS") and not es_plataforma(request.user):
            raise PermissionDenied(
                "El catálogo de permisos es común a todos los gimnasios; solo el "
                "personal de la plataforma puede modificarlo."
            )


class RolPermisoViewSet(ViewSetBase):
    queryset = RolPermiso.objects.select_related("rol", "permiso")
    serializer_class = RolPermisoSerializer
    recurso_permiso = "roles"
    filterset_fields = ("rol", "permiso")
    permission_classes = [IsAuthenticated, TienePermisoRecurso]
    # Tabla puente sin historial propio: se elimina físicamente.
    politica_borrado = "fisico"

    def perform_create(self, serializer):
        with transaction.atomic():
            asignacion = serializer.save(gimnasio_id=gimnasio_id_de(self.request.user))
            self.registrar_evento(
                "asignar-permiso",
                asignacion.rol,
                detalles={"permiso": asignacion.permiso.codigo},
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            asignacion = serializer.save()
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
        if es_administrador(instance):
            administradores = (
                Usuario.objects.filter(
                    gimnasio_id=instance.gimnasio_id,
                    is_active=True,
                    deleted_at__isnull=True,
                )
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

    @extend_schema(
        methods=["GET"],
        operation_id="usuario_roles_consultar",
        responses={200: OpenApiResponse(description="Roles del usuario.")},
    )
    @extend_schema(
        methods=["PATCH"],
        operation_id="usuario_roles_actualizar",
        request=RolesUsuarioPayloadSerializer,
        responses={200: OpenApiResponse(description="Roles del usuario actualizados.")},
    )
    @extend_schema(
        methods=["PUT"],
        operation_id="usuario_roles_reemplazar",
        request=RolesUsuarioPayloadSerializer,
        responses={200: OpenApiResponse(description="Roles del usuario reemplazados.")},
    )
    @action(detail=True, methods=["get", "patch", "put"], url_path="roles")
    def roles(self, request, pk=None):
        """Consulta o reemplaza los roles adicionales y el rol principal."""
        usuario = self.get_object()
        mutando = request.method in {"PATCH", "PUT"}

        if mutando:
            if not (
                es_administrador(request.user)
                or request.user.tiene_permiso("usuarios:edit")
                or request.user.tiene_permiso("roles:edit")
            ):
                raise PermissionDenied(
                    "Solo un usuario con permiso puede modificar los roles de un usuario."
                )
            roles_ids = request.data.get("roles")
            if not isinstance(roles_ids, list) or not all(
                isinstance(valor, int) and not isinstance(valor, bool)
                for valor in roles_ids
            ):
                raise ValidationError({"roles": "Envíe una lista de identificadores de rol."})

            roles_ids = list(dict.fromkeys(roles_ids))
            roles = list(filtrar_por_gimnasio(Rol.objects.filter(pk__in=roles_ids), request.user))
            if len(roles) != len(roles_ids):
                raise ValidationError({"roles": "Uno o más roles no existen."})
            if any(not rol.is_active for rol in roles):
                raise ValidationError({"roles": "Solo puede asignar roles activos."})

            nuevo_principal = None
            rol_principal_id = request.data.get("rol_principal")
            if rol_principal_id is not None:
                if isinstance(rol_principal_id, bool) or not isinstance(
                    rol_principal_id, int
                ):
                    raise ValidationError(
                        {"rol_principal": "Envíe un identificador de rol válido."}
                    )
                nuevo_principal = filtrar_por_gimnasio(
                    Rol.objects.filter(pk=rol_principal_id), request.user
                ).first()
                if nuevo_principal is None:
                    raise ValidationError(
                        {"rol_principal": "El rol principal no existe."}
                    )
                cambia_principal = nuevo_principal.pk != usuario.rol_id
                if cambia_principal and not nuevo_principal.is_active:
                    raise ValidationError(
                        {"rol_principal": "Solo puede asignar roles activos."}
                    )
                if cambia_principal and not es_administrador(request.user):
                    raise ValidationError(
                        {
                            "rol_principal": (
                                "Solo un administrador puede cambiar el rol "
                                "principal."
                            )
                        }
                    )
            else:
                cambia_principal = False

            deseados = set(roles_ids)
            if nuevo_principal is not None:
                deseados.add(nuevo_principal.pk)
            else:
                deseados.add(usuario.rol_id)

            era_admin = es_administrador(usuario)
            seguira_admin = (
                usuario.is_active
                and Rol.Nombre.ADMINISTRADOR
                in set(
                    Rol.objects.filter(pk__in=deseados, is_active=True)
                    .values_list("nombre", flat=True)
                )
            )
            if (
                era_admin
                and not seguira_admin
                and not existe_otro_administrador_activo(usuario)
            ):
                campo = "rol_principal" if cambia_principal else "roles"
                raise ValidationError(
                    {
                        campo: (
                            "No puede quitar el rol administrador al último "
                            "administrador activo."
                        )
                    }
                )
            asignado_por = request.user if isinstance(request.user, Usuario) else None
            with transaction.atomic():
                if cambia_principal:
                    try:
                        usuario.cambiar_rol_principal(nuevo_principal)
                    except ProtectedError as error:
                        raise ValidationError(
                            {
                                "rol_principal": (
                                    "No puede cambiar el rol principal porque el "
                                    "perfil actual tiene datos asociados. Reasigne "
                                    "o elimine esos datos primero."
                                )
                            }
                        ) from error
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
                sesiones = Sesion.objects.filter(usuario=usuario)
                sesion_actual = request.auth if isinstance(request.auth, Sesion) else None
                if sesion_actual is not None:
                    sesiones = sesiones.exclude(pk=sesion_actual.pk)
                sesiones.delete()
                registrar_evento(
                    request,
                    "actualizar-roles",
                    "usuarios",
                    usuario,
                    detalles={
                        "roles": roles_ids,
                        "rol_principal": usuario.rol_id,
                    },
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
    permission_classes = [IsAuthenticated, TienePermisoRecurso]
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
        usuario = instance.usuario
        if (
            instance.rol.nombre == Rol.Nombre.ADMINISTRADOR
            and instance.activo
            and usuario.is_active
            and not (
                usuario.rol.is_active
                and usuario.rol.nombre == Rol.Nombre.ADMINISTRADOR
            )
            and not usuario.asignaciones_usuarios.filter(
                rol__nombre=Rol.Nombre.ADMINISTRADOR,
                activo=True,
                rol__is_active=True,
            )
            .exclude(pk=instance.pk)
            .exists()
            and not existe_otro_administrador_activo(usuario)
        ):
            raise ValidationError(
                {
                    "detalle": (
                        "No puede quitar el rol administrador al último "
                        "administrador activo."
                    )
                }
            )
        with transaction.atomic():
            rol = instance.rol.nombre
            super().perform_destroy(instance)
            usuario.sesiones.all().delete()
            self.registrar_evento("revocar-rol", usuario, detalles={"rol": rol})


class ClienteViewSet(FiltroFechasMixin, ViewSetBase):
    campo_fecha = "created_at"
    campo_fecha_con_hora = True
    queryset = Cliente.objects.select_related("usuario__rol")
    serializer_class = ClienteSerializer
    recurso_permiso = "clientes"
    filterset_fields = ("is_active", "tipo_documento")
    search_fields = ("usuario__nombre", "usuario__correo", "numero_documento", "objetivo")
    ordering_fields = ("usuario__nombre", "created_at", "is_active")

    def get_serializer_class(self):
        roles = roles_efectivos_nombres(self.request.user)
        solo_recepcion = (
            Rol.Nombre.RECEPCIONISTA in roles
            and not roles
            & {
                Rol.Nombre.ADMINISTRADOR,
                Rol.Nombre.ENTRENADOR,
                Rol.Nombre.TERAPEUTA,
            }
        )
        if solo_recepcion:
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


class AsistenciaViewSet(FiltroFechasMixin, ViewSetBase):
    campo_fecha = "entrada_at"
    campo_fecha_con_hora = True
    queryset = Asistencia.objects.select_related("cliente__usuario")
    serializer_class = AsistenciaSerializer
    recurso_permiso = "asistencias"
    filterset_fields = ("cliente",)
    ordering_fields = ("entrada_at", "salida_at", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_clientes(queryset, "cliente", self.request.user, operativo=True)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer, operativo=True)

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="El cliente ya tenía una entrada abierta."),
            201: AsistenciaSerializer,
        },
        description=(
            "Registra la llegada del cliente autenticado con la hora del servidor. "
            "No requiere el permiso asistencias:create y no duplica una entrada "
            "que siga abierta."
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="registrar-entrada",
        permission_classes=[IsAuthenticated],
    )
    def registrar_entrada(self, request):
        """Marca la llegada del propio cliente, sin pedirle datos ni hora."""
        cliente = self._cliente_propio(request)

        with transaction.atomic():
            # Serializa dos pulsaciones simultáneas del mismo cliente.
            cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
            abierta = (
                Asistencia.objects.filter(
                    cliente=cliente,
                    salida_at__isnull=True,
                    is_active=True,
                    deleted_at__isnull=True,
                )
                .order_by("-entrada_at", "-pk")
                .first()
            )
            if abierta is not None:
                return Response(
                    {
                        "creado": False,
                        "mensaje": "Ya tienes una entrada abierta.",
                        "asistencia": AsistenciaSerializer(
                            abierta, context={"request": request}
                        ).data,
                    }
                )

            asistencia = Asistencia(
                cliente=cliente,
                entrada_at=timezone.now(),
                metodo_entrada=Asistencia.MetodoEntrada.MANUAL,
            )
            try:
                asistencia.full_clean()
            except DjangoValidationError as error:
                raise ValidationError(error.message_dict) from error
            asistencia.save()
            registrar_evento(
                request, "registrar-entrada", "asistencias", asistencia
            )

        return Response(
            {
                "creado": True,
                "mensaje": "Llegada registrada.",
                "asistencia": AsistenciaSerializer(
                    asistencia, context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=None,
        responses={200: AsistenciaSerializer},
        description=(
            "Cierra la entrada abierta del cliente autenticado con la hora del "
            "servidor, para que pueda volver a marcar su llegada."
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="registrar-salida",
        permission_classes=[IsAuthenticated],
    )
    def registrar_salida(self, request):
        """Marca la salida del propio cliente."""
        cliente = self._cliente_propio(request)

        with transaction.atomic():
            abierta = (
                Asistencia.objects.select_for_update()
                .filter(
                    cliente_id=cliente.pk,
                    salida_at__isnull=True,
                    is_active=True,
                    deleted_at__isnull=True,
                )
                .order_by("-entrada_at", "-pk")
                .first()
            )
            if abierta is None:
                raise ValidationError(
                    {"asistencia": "No tienes una entrada abierta que cerrar."}
                )
            abierta.salida_at = timezone.now()
            try:
                abierta.full_clean()
            except DjangoValidationError as error:
                raise ValidationError(error.message_dict) from error
            abierta.save(update_fields=["salida_at", "updated_at"])
            registrar_evento(
                request, "registrar-salida", "asistencias", abierta
            )

        return Response(
            {
                "mensaje": "Salida registrada.",
                "asistencia": AsistenciaSerializer(
                    abierta, context={"request": request}
                ).data,
            }
        )

    def _cliente_propio(self, request):
        usuario = request.user
        cliente = getattr(usuario, "cliente", None) if isinstance(usuario, Usuario) else None
        if cliente is None:
            raise ValidationError(
                {
                    "cliente": (
                        "Solo una cuenta con perfil de cliente puede registrar "
                        "su propia entrada o salida."
                    )
                }
            )
        if not cliente.is_active or cliente.deleted_at is not None:
            raise ValidationError({"cliente": "Tu perfil de cliente está inactivo."})
        return cliente


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


def respuesta_imagen_privada(campo, no_encontrada="El ejercicio no tiene imagen de referencia."):
    """Entrega un archivo de ``AlmacenamientoFotosPrivadas`` sin caché pública."""
    if not campo:
        raise NotFound(no_encontrada)
    try:
        archivo = campo.storage.open(campo.name, "rb")
    except (FileNotFoundError, OSError) as error:
        raise NotFound("La imagen ya no está disponible.") from error
    tipo_contenido = mimetypes.guess_type(campo.name)[0] or "application/octet-stream"
    respuesta = FileResponse(archivo, content_type=tipo_contenido)
    respuesta["Content-Disposition"] = f'inline; filename="{Path(campo.name).name}"'
    respuesta["Cache-Control"] = "private, max-age=300"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


class EjercicioViewSet(ViewSetBase):
    queryset = Ejercicio.objects.all()
    serializer_class = EjercicioSerializer
    recurso_permiso = "ejercicios"
    accion_permiso_por_accion = {"imagen": "view"}
    filterset_fields = ("grupo_muscular", "is_active")
    search_fields = ("nombre", "descripcion", "grupo_muscular")
    ordering_fields = ("nombre", "grupo_muscular", "created_at")

    def get_renderers(self):
        if getattr(self, "action", None) == "imagen":
            return [RendererFotoPrivada()]
        return super().get_renderers()

    @action(detail=True, methods=["get"], url_path="imagen")
    def imagen(self, request, pk=None):
        """Imagen de referencia del ejercicio (personal con acceso al catálogo)."""
        return respuesta_imagen_privada(self.get_object().imagen)


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
        actor = self.request.user
        entrenador = serializer.validated_data.get("entrenador")
        if (
            entrenador is not None
            and not es_administrador(actor)
            and isinstance(actor, Usuario)
            and hasattr(actor, "entrenador")
            and entrenador.pk != actor.pk
        ):
            # Un entrenador arma planes a su nombre; el administrador puede
            # elegir cualquier entrenador asignado al cliente.
            raise ValidationError({"entrenador": "Solo puede crear planes a su propio nombre."})


class PlanEntrenamientoEjercicioViewSet(ViewSetBase):
    queryset = PlanEntrenamientoEjercicio.objects.select_related("plan", "ejercicio")
    serializer_class = PlanEntrenamientoEjercicioSerializer
    recurso_permiso = "planes-entrenamiento-ejercicios"
    accion_permiso_por_accion = {"imagen": "view"}
    filterset_fields = ("plan", "ejercicio")
    # Fila de composición del plan (sin deleted_at ni is_active): DELETE físico.
    politica_borrado = "fisico"

    def get_renderers(self):
        if getattr(self, "action", None) == "imagen":
            return [RendererFotoPrivada()]
        return super().get_renderers()

    @action(detail=True, methods=["get"], url_path="imagen")
    def imagen(self, request, pk=None):
        """Imagen del ejercicio vista desde el plan (el cliente la ve así)."""
        return respuesta_imagen_privada(self.get_object().ejercicio.imagen)

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
    accion_permiso_por_accion = {"leer": "view", "marcar_todas": "view"}
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


# =============================================================================
# VIEWSETS FINANCIEROS
# =============================================================================

class MetodoPagoViewSet(ViewSetBase):
    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    recurso_permiso = "metodos-pago"
    filterset_fields = ("tipo", "is_active")
    search_fields = ("nombre", "descripcion")
    ordering_fields = ("orden", "nombre", "created_at")
    politica_borrado = "logico"

    def filtrar_alcance(self, queryset):
        if es_administrador(self.request.user):
            return queryset
        return queryset.none()


class CategoriaGastoViewSet(ViewSetBase):
    queryset = CategoriaGasto.objects.all()
    serializer_class = CategoriaGastoSerializer
    recurso_permiso = "categorias-gasto"
    filterset_fields = ("tipo", "is_active")
    search_fields = ("nombre", "descripcion")
    ordering_fields = ("orden", "nombre", "created_at")
    politica_borrado = "logico"

    def filtrar_alcance(self, queryset):
        if es_administrador(self.request.user):
            return queryset
        return queryset.none()


class PagoViewSet(FiltroFechasMixin, ViewSetBase):
    campo_fecha = "fecha_pago"
    campo_fecha_con_hora = True
    queryset = Pago.objects.select_related(
        "cliente__usuario", "metodo_pago", "membresia", "registrado_por"
    )
    serializer_class = PagoSerializer
    recurso_permiso = "pagos"
    filterset_fields = ("cliente", "concepto", "estado", "metodo_pago")
    search_fields = ("cliente__usuario__nombre", "referencia", "notas")
    ordering_fields = ("fecha_pago", "valor", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_clientes(queryset, "cliente", self.request.user)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer)

    @extend_schema(
        responses={200: OpenApiResponse(description="Estadísticas de ingresos.")},
    )
    @action(detail=False, methods=["get"], url_path="estadisticas")
    def estadisticas(self, request):
        """Estadísticas agregadas de ingresos con filtros de fecha."""
        # ``filter_queryset`` ya aplica fecha_desde y fecha_hasta.
        queryset = self.filter_queryset(self.get_queryset())

        # Solo pagos completados para ingresos reales
        completados = queryset.filter(estado=Pago.Estado.COMPLETADO)
        pendientes = queryset.filter(estado=Pago.Estado.PENDIENTE)

        stats = {
            "total_ingresos": completados.aggregate(total=Sum("valor"))["total"] or Decimal("0"),
            "total_pendientes": pendientes.aggregate(total=Sum("valor"))["total"] or Decimal("0"),
            "count_completados": completados.count(),
            "count_pendientes": pendientes.count(),
            "por_concepto": list(
                completados.values("concepto")
                .annotate(total=Sum("valor"), count=models.Count("id"))
                .order_by("-total")
            ),
            "por_metodo": list(
                completados.values("metodo_pago__nombre")
                .annotate(total=Sum("valor"), count=models.Count("id"))
                .order_by("-total")
            ),
        }
        return Response(stats)


class GastoViewSet(FiltroFechasMixin, ViewSetBase):
    campo_fecha = "fecha"
    queryset = Gasto.objects.select_related(
        "categoria", "metodo_pago", "registrado_por", "aprobado_por"
    )
    serializer_class = GastoSerializer
    recurso_permiso = "gastos"
    filterset_fields = ("categoria", "estado", "metodo_pago")
    search_fields = ("descripcion", "referencia", "observaciones")
    ordering_fields = ("fecha", "valor", "created_at")

    def filtrar_alcance(self, queryset):
        if es_administrador(self.request.user):
            return queryset
        return queryset.none()

    def perform_create(self, serializer):
        with transaction.atomic():
            gasto = super().perform_create(serializer)
            alerta_nuevo_gasto(gasto)
        return gasto

    @extend_schema(
        responses={200: OpenApiResponse(description="Estadísticas de gastos.")},
    )
    @action(detail=False, methods=["get"], url_path="estadisticas")
    def estadisticas(self, request):
        """Estadísticas agregadas de gastos con filtros de fecha."""
        # ``filter_queryset`` ya aplica fecha_desde y fecha_hasta.
        queryset = self.filter_queryset(self.get_queryset())
        # Los anulados se informan por estado, pero no suman al total.
        vigentes = queryset.exclude(estado=Gasto.Estado.CANCELADO)

        stats = {
            "total_gastos": vigentes.aggregate(total=Sum("valor"))["total"] or Decimal("0"),
            "count": vigentes.count(),
            "count_anulados": queryset.filter(estado=Gasto.Estado.CANCELADO).count(),
            "por_categoria": list(
                vigentes.values("categoria__nombre", "categoria__color")
                .annotate(total=Sum("valor"), count=models.Count("id"))
                .order_by("-total")
            ),
            "por_estado": list(
                queryset.values("estado")
                .annotate(total=Sum("valor"), count=models.Count("id"))
                .order_by("-total")
            ),
        }
        return Response(stats)


class MembresiaViewSet(FiltroFechasMixin, ViewSetBase):
    # El rango de fechas se aplica al vencimiento de la membresía.
    campo_fecha = "fecha_fin"
    accion_permiso_por_accion = {
        "exportar": "export",
        "renovar": "edit",
        "congelar": "edit",
        "activar": "edit",
    }
    queryset = Membresia.objects.select_related(
        "cliente__usuario", "entrenador_asignado__usuario", "registrado_por"
    )
    serializer_class = MembresiaSerializer
    recurso_permiso = "membresias"
    filterset_fields = ("cliente", "tipo", "estado", "entrenador_asignado")
    search_fields = ("nombre", "cliente__usuario__nombre")
    ordering_fields = ("fecha_inicio", "fecha_fin", "estado", "created_at")

    def filtrar_alcance(self, queryset):
        return filtrar_clientes(queryset, "cliente", self.request.user)

    def validar_escritura(self, serializer):
        self.validar_cliente_relacionado(serializer)

    @action(detail=True, methods=["post"], url_path="renovar")
    def renovar(self, request, pk=None):
        """Renueva una membresía extendiendo su fecha de fin."""
        membresia = self.get_object()
        nuevo_tipo = request.data.get("tipo", membresia.tipo)
        if nuevo_tipo not in Membresia.Tipo.values:
            raise ValidationError({"tipo": "El tipo de membresía no es válido."})
        meses = _entero_param(request.data, "meses", 1, 120, predeterminado=1)

        nueva_fecha_fin = _sumar_meses(membresia.fecha_fin, meses)

        with transaction.atomic():
            membresia.fecha_ultima_renovacion = membresia.fecha_fin
            membresia.fecha_fin = nueva_fecha_fin
            membresia.tipo = nuevo_tipo
            membresia.estado = Membresia.Estado.ACTIVA
            # Si aun renovada sigue vencida o a días de vencer, se refleja.
            membresia.actualizar_estado_por_fecha()
            membresia.save()
            self.registrar_evento("renovar", membresia, {"meses": meses})

        return Response(self.get_serializer(membresia).data)

    @action(detail=True, methods=["post"], url_path="congelar")
    def congelar(self, request, pk=None):
        """Congela una membresía vigente y corre su vencimiento esos días."""
        membresia = self.get_object()
        dias = _entero_param(request.data, "dias", 1, 365)

        if membresia.estado not in (
            Membresia.Estado.ACTIVA,
            Membresia.Estado.POR_VENCER,
        ):
            raise ValidationError(
                {"estado": "Solo se pueden congelar membresías vigentes."}
            )

        with transaction.atomic():
            membresia.estado = Membresia.Estado.CONGELADA
            membresia.dias_congelados += dias
            # El tiempo congelado no se pierde: la vigencia se corre.
            membresia.fecha_fin += timedelta(days=dias)
            membresia.save(
                update_fields=["estado", "dias_congelados", "fecha_fin", "updated_at"]
            )
            self.registrar_evento("congelar", membresia, {"dias": dias})

        return Response(self.get_serializer(membresia).data)

    @action(detail=True, methods=["post"], url_path="activar")
    def activar(self, request, pk=None):
        """Reactiva una membresía congelada."""
        membresia = self.get_object()

        if membresia.estado != Membresia.Estado.CONGELADA:
            raise ValidationError({"estado": "Solo se pueden activar membresías congeladas."})

        with transaction.atomic():
            membresia.estado = Membresia.Estado.ACTIVA
            # Puede volver ya vencida o a pocos días de vencer.
            membresia.actualizar_estado_por_fecha()
            membresia.save(update_fields=["estado", "updated_at"])
            self.registrar_evento("activar", membresia)

        return Response(self.get_serializer(membresia).data)

    @extend_schema(
        responses={200: OpenApiResponse(description="Estadísticas de membresías.")},
    )
    @action(detail=False, methods=["get"], url_path="estadisticas")
    def estadisticas(self, request):
        """Estadísticas agregadas de membresías."""
        queryset = self.filter_queryset(self.get_queryset())

        stats = {
            "total": queryset.count(),
            "por_estado": dict(
                queryset.values("estado").annotate(count=models.Count("id")).values_list("estado", "count")
            ),
            "por_tipo": dict(
                queryset.values("tipo").annotate(count=models.Count("id")).values_list("tipo", "count")
            ),
            "proximas_a_vencer": queryset.filter(
                estado__in=[Membresia.Estado.ACTIVA, Membresia.Estado.POR_VENCER],
                fecha_fin__lte=timezone.localdate() + timedelta(days=30),
            ).count(),
            "vencidas": queryset.filter(estado=Membresia.Estado.VENCIDA).count(),
        }
        return Response(stats)


class AlertaViewSet(ViewSetBase):
    queryset = Alerta.objects.por_prioridad().select_related(
        "cliente__usuario", "membresia", "pago", "gasto", "leida_por"
    )
    serializer_class = AlertaSerializer
    recurso_permiso = "alertas"
    accion_permiso_por_accion = {
        "exportar": "export",
        "marcar_leida": "edit",
        "marcar_todas_leidas": "edit",
    }
    filterset_fields = ("tipo", "prioridad", "leida", "cliente")
    search_fields = ("titulo", "mensaje")
    ordering_fields = ("prioridad_orden", "created_at")

    def filtrar_alcance(self, queryset):
        if es_administrador(self.request.user):
            return queryset
        # Los no administradores solo ven alertas de sus clientes asignados
        return filtrar_clientes(queryset, "cliente", self.request.user)

    def _actualizar_alertas(self):
        # Las reglas son idempotentes; generarlas al consultar evita depender
        # de una tarea programada para ver alertas al día.
        if es_administrador(self.request.user):
            generar_alertas_de(self.request.user)

    def list(self, request, *args, **kwargs):
        self._actualizar_alertas()
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="marcar-leida")
    def marcar_leida(self, request, pk=None):
        alerta = self.get_object()
        if not alerta.leida:
            alerta.marcar_como_leida(request.user)
        return Response(self.get_serializer(alerta).data)

    @action(detail=False, methods=["post"], url_path="marcar-todas-leidas")
    def marcar_todas_leidas(self, request):
        ahora = timezone.now()
        pendientes = self.filter_queryset(self.get_queryset()).filter(leida=False)
        # ``update`` no admite consultas anotadas ni ordenadas: se filtra por id.
        count = Alerta.objects.filter(pk__in=pendientes.values("pk")).update(
            leida=True,
            leida_por=request.user if isinstance(request.user, Usuario) else None,
            leida_at=ahora,
            updated_at=ahora,
        )
        return Response({"mensaje": f"{count} alertas marcadas como leídas.", "cantidad": count})

    @extend_schema(
        responses={200: OpenApiResponse(description="Estadísticas de alertas.")},
    )
    @action(detail=False, methods=["get"], url_path="estadisticas")
    def estadisticas(self, request):
        self._actualizar_alertas()
        queryset = self.filter_queryset(self.get_queryset())

        stats = {
            "total": queryset.count(),
            "no_leidas": queryset.filter(leida=False).count(),
            "por_tipo": dict(
                queryset.values("tipo").annotate(count=models.Count("id")).values_list("tipo", "count")
            ),
            "por_prioridad": dict(
                queryset.values("prioridad").annotate(count=models.Count("id")).values_list("prioridad", "count")
            ),
        }
        return Response(stats)


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
        queryset = filtrar_por_gimnasio(super().get_queryset(), self.request.user)
        if es_administrador(self.request.user):
            return queryset
        return queryset.none()


# Recursos con conteo en el menú de la SPA. La clave es la que consume el
# frontend y el valor es el ViewSet que define el alcance de cada listado, de
# modo que el número del menú coincide siempre con el total del recurso.
_RECURSOS_MENU_VIEWSETS = {
    "usuarios": UsuarioViewSet,
    "usuarios-roles": UsuarioRolViewSet,
    "roles": RolViewSet,
    "permisos": PermisoViewSet,
    "clientes": ClienteViewSet,
    "entrenadores": EntrenadorViewSet,
    "terapeutas": TerapeutaViewSet,
    "recepcionistas": RecepcionistaViewSet,
    "administradores": AdministradorViewSet,
    "asignaciones-cliente-entrenador": ClienteEntrenadorViewSet,
    "clientes-terapeutas": ClienteTerapeutaViewSet,
    "asistencias": AsistenciaViewSet,
    "entrenamientos": EntrenamientoViewSet,
    "ejercicios": EjercicioViewSet,
    "planes-entrenamiento": PlanEntrenamientoViewSet,
    "planes-alimentacion": PlanAlimentacionViewSet,
    "comidas": ComidaViewSet,
    "registros-comida": RegistroComidaViewSet,
    "notificaciones": NotificacionViewSet,
    "auditoria": EventoAuditoriaViewSet,
    "metodos-pago": MetodoPagoViewSet,
    "categorias-gasto": CategoriaGastoViewSet,
    "pagos": PagoViewSet,
    "gastos": GastoViewSet,
    "membresias": MembresiaViewSet,
    "alertas": AlertaViewSet,
}


class GimnasioActualView(APIView):
    """Datos y configuración del gimnasio del usuario autenticado.

    Cualquier usuario del gimnasio puede consultarlos; solo un administrador
    puede cambiarlos. El gimnasio sale de la sesión, nunca de la URL.
    """

    permission_classes = [IsAuthenticated]

    def _gimnasio(self, request):
        gimnasio_id = gimnasio_id_de(request.user)
        if not gimnasio_id:
            raise NotFound("Esta cuenta no pertenece a ningún gimnasio.")
        return Gimnasio.objects.get(pk=gimnasio_id)

    @extend_schema(responses=GimnasioConfiguracionSerializer)
    def get(self, request):
        return Response(GimnasioConfiguracionSerializer(self._gimnasio(request)).data)

    @extend_schema(request=GimnasioConfiguracionSerializer, responses=GimnasioConfiguracionSerializer)
    def patch(self, request):
        if not es_administrador(request.user):
            raise PermissionDenied("Solo un administrador puede cambiar la configuración del gimnasio.")
        gimnasio = self._gimnasio(request)
        serializer = GimnasioConfiguracionSerializer(gimnasio, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
            registrar_evento(
                request,
                "actualizar-configuracion",
                "gimnasio",
                gimnasio,
                detalles={"campos": sorted(serializer.validated_data)},
            )
        return Response(serializer.data)


FORMATOS_REPORTE = {
    "xlsx": (
        a_excel,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    "pdf": (a_pdf, "application/pdf"),
}


class ReporteView(APIView):
    """Descarga un reporte administrativo en Excel o PDF.

    ``GET /api/v1/reportes/<tipo>/?formato=xlsx|pdf&fecha_desde=&fecha_hasta=``

    Solo para administradores. El gimnasio sale del usuario autenticado; el
    personal de la plataforma (sin gimnasio propio) debe indicar
    ``?gimnasio=<código>``. Por defecto el período es el mes en curso.
    """

    permission_classes = [IsAuthenticated]

    def _gimnasio(self, request):
        usuario = request.user
        if isinstance(usuario, Usuario):
            # Un usuario del gimnasio nunca elige el gimnasio por parámetro.
            return Gimnasio.objects.get(pk=usuario.gimnasio_id)
        codigo = request.query_params.get("gimnasio")
        if not codigo:
            raise ValidationError({"gimnasio": "Indique el código del gimnasio."})
        gimnasio = Gimnasio.objects.filter(codigo=codigo).first()
        if gimnasio is None:
            raise NotFound("No existe un gimnasio con ese código.")
        return gimnasio

    @extend_schema(
        responses={200: OpenApiResponse(description="Archivo .xlsx o .pdf del reporte.")},
    )
    def get(self, request, tipo):
        if not es_administrador(request.user):
            raise PermissionDenied("Solo administradores pueden descargar reportes.")
        if tipo not in TIPOS_REPORTE:
            raise NotFound("Tipo de reporte desconocido.")
        formato = request.query_params.get("formato", "xlsx")
        if formato not in FORMATOS_REPORTE:
            raise ValidationError({"formato": "Use xlsx o pdf."})

        hoy = timezone.localdate()
        desde = _fecha_param(request, "fecha_desde") or hoy.replace(day=1)
        hasta = _fecha_param(request, "fecha_hasta") or hoy
        if desde > hasta:
            raise ValidationError({"fecha_hasta": "No puede ser anterior a fecha_desde."})
        if (hasta - desde).days > MAX_DIAS_RANGO:
            raise ValidationError({"fecha_desde": "El período no puede superar cinco años."})

        gimnasio = self._gimnasio(request)
        if not gimnasio.is_active or gimnasio.deleted_at is not None:
            raise PermissionDenied("El gimnasio no está activo.")
        usuario = request.user
        autor = getattr(usuario, "nombre", None) or usuario.get_username()
        reporte = construir_reporte(tipo, gimnasio, desde, hasta, autor)
        generar, tipo_contenido = FORMATOS_REPORTE[formato]
        contenido = generar(reporte)
        registrar_evento(
            request,
            "exportar-reporte",
            "reportes",
            gimnasio,
            detalles={
                "tipo": tipo,
                "formato": formato,
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat(),
            },
        )
        nombre = f"reporte_{tipo}_{desde:%Y%m%d}_{hasta:%Y%m%d}.{formato}"
        respuesta = HttpResponse(contenido, content_type=tipo_contenido)
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
        respuesta["Cache-Control"] = "private, no-store"
        return respuesta


class ConteoRecursosView(APIView):
    """Total de registros por recurso para los distintivos del menú.

    Reutiliza los ViewSets de los listados, así que respeta el mismo alcance por
    rol y el mismo borrado lógico: si el listado muestra 10 registros, el menú
    muestra 10. Solo aparecen los recursos sobre los que el usuario tiene
    permiso de lectura.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiResponse(description="Conteo por recurso.")})
    def get(self, request):
        conteos = {}
        for recurso, viewset_clase in _RECURSOS_MENU_VIEWSETS.items():
            if not self._puede_ver(recurso, viewset_clase):
                continue
            conteos[recurso] = self._contar(viewset_clase)
        return Response(conteos)

    def _puede_ver(self, recurso, viewset_clase):
        usuario = self.request.user
        if not isinstance(usuario, Usuario):
            return bool(getattr(usuario, "is_staff", False))
        if es_administrador(usuario):
            return True
        if recurso in {"auditoria"} and not es_administrador(usuario):
            return False
        return usuario.tiene_permiso(f"{viewset_clase.recurso_permiso}:view")

    def _contar(self, viewset_clase):
        vista = viewset_clase()
        vista.request = self.request
        vista.action = "list"
        vista.format_kwarg = None
        return vista.get_queryset().count()


class ResourceAliasListView(APIView):
    """Lista todos los recursos del menú con su nombre de visualización actual.

    El nombre actual es el alias personalizado si existe, o el nombre original
    del recurso en caso contrario. Solo administradores pueden editar, pero
    cualquier usuario autenticado puede consultar.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        aliases = get_all_aliases()
        items = []
        for nombre in sorted(RECURSOS_MENU):
            actual = aliases.get(nombre, nombre)
            items.append(
                {
                    "nombre_original": nombre,
                    "nombre_actual": actual,
                    "tiene_alias": nombre in aliases,
                }
            )
        return Response(items)


class ResourceAliasDetailView(APIView):
    """Actualiza el nombre de visualización (alias) de un recurso."""

    permission_classes = [IsAuthenticated, SoloAdministrador]

    def put(self, request, nombre_original):
        # Los nombres visibles se guardan en un archivo común a todos los
        # gimnasios: solo el personal de la plataforma puede cambiarlos.
        if not es_plataforma(request.user):
            raise PermissionDenied(
                "Los nombres de recursos son comunes a todos los gimnasios; solo el "
                "personal de la plataforma puede cambiarlos."
            )
        if nombre_original not in RECURSOS_MENU:
            return Response(
                {
                    "error": {
                        "codigo": 404,
                        "mensaje": "Recurso no encontrado.",
                        "detalles": {},
                    }
                },
                status=404,
            )

        nuevo_nombre = request.data.get("nombre_actual")
        # Un texto vacío es válido: significa quitar el alias (ver más abajo).
        if not isinstance(nuevo_nombre, str):
            return Response(
                {
                    "error": {
                        "codigo": 400,
                        "mensaje": "El campo nombre_actual es requerido.",
                        "detalles": {},
                    }
                },
                status=400,
            )

        nuevo_nombre = nuevo_nombre.strip()
        if not nuevo_nombre:
            set_alias(nombre_original, None)
            return Response(
                {
                    "nombre_original": nombre_original,
                    "nombre_actual": nombre_original,
                    "tiene_alias": False,
                }
            )

        aliases = get_all_aliases()
        for orig, alias in aliases.items():
            if alias == nuevo_nombre and orig != nombre_original:
                return Response(
                    {
                        "error": {
                            "codigo": 409,
                            "mensaje": "Este nombre ya está en uso por otro recurso.",
                            "detalles": {},
                        }
                    },
                    status=409,
                )

        set_alias(nombre_original, nuevo_nombre)
        return Response(
            {
                "nombre_original": nombre_original,
                "nombre_actual": nuevo_nombre,
                "tiene_alias": True,
            }
        )


class ResourceAliasResolveView(APIView):
    """Resuelve un nombre (alias o original) al nombre original del recurso."""

    permission_classes = [IsAuthenticated]

    def get(self, request, nombre):
        original = resolve_name(nombre, RECURSOS_MENU)
        return Response({"nombre": nombre, "nombre_original": original})

