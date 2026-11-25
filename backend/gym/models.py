"""Modelo relacional de Gym Control Pro.

El diseño corresponde al esquema ``gym_control_pro.sql``.  Se conserva el
borrado lógico de las entidades operativas para mantener el historial.
"""

import hashlib
import secrets
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.db.models.functions import Lower
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from .storage import AlmacenamientoFotosPrivadas


def normalizar_texto_opcional(valor):
    """Convierte cadenas vacías o solo espacios en ``None``."""
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


def normalizar_correo(valor):
    """El correo se compara y almacena siempre en minúsculas."""
    return (valor or "").strip().lower()


def normalizar_username(valor):
    return (normalizar_texto_opcional(valor) or "").lower() or None


def _valor_con_sufijo(valor, sufijo, max_length):
    if not valor:
        return valor
    disponible = max(0, max_length - len(sufijo))
    return f"{valor[:disponible]}{sufijo}"


def correo_liberado(correo, pk, max_length=191):
    """Correo tumba único para liberar el original tras un soft-delete."""
    correo = normalizar_correo(correo)
    local, separador, dominio = correo.partition("@")
    sufijo = f"+eliminado-{pk}"
    if not separador or len(dominio) + len(sufijo) + 2 > max_length:
        return f"eliminado-{pk}@invalid.local"
    disponible = max(1, max_length - len(dominio) - len(sufijo) - 1)
    return f"{local[:disponible]}{sufijo}@{dominio}"


FOTO_REGISTRO_EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}
FOTO_REGISTRO_FORMATOS = {"JPEG", "PNG", "WEBP"}


def ruta_foto_registro(instance, filename):
    """Genera un nombre opaco y evita rutas controladas por el cliente."""
    extension = Path(filename).suffix.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    if extension not in FOTO_REGISTRO_EXTENSIONES:
        extension = ".img"
    return (
        f"registros-comida/{timezone.now():%Y/%m}/"
        f"{uuid4().hex}{extension}"
    )


def ruta_imagen_ejercicio(instance, filename):
    """Nombre opaco para la imagen de referencia de un ejercicio."""
    extension = Path(filename).suffix.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    if extension not in FOTO_REGISTRO_EXTENSIONES:
        extension = ".img"
    return f"ejercicios/{timezone.now():%Y/%m}/{uuid4().hex}{extension}"


# Catálogo cerrado de músculos que se pueden marcar en ejercicios y rutinas.
# Grupos musculares (códigos originales): se siguen aceptando para no romper
# los datos ya guardados; en el modelo 3D equivalen a todos sus músculos.
GRUPOS_MUSCULARES = {
    "cuello": "Cuello",
    "trapecio": "Trapecio",
    "hombros": "Hombros",
    "pecho": "Pecho",
    "biceps": "Bíceps",
    "triceps": "Tríceps",
    "antebrazos": "Antebrazos",
    "abdomen": "Abdomen",
    "oblicuos": "Oblicuos",
    "dorsales": "Dorsales",
    "lumbares": "Lumbares",
    "gluteos": "Glúteos",
    "cuadriceps": "Cuádriceps",
    "isquiotibiales": "Isquiotibiales",
    "aductores": "Aductores",
    "pantorrillas": "Pantorrillas",
}

# Músculos detallados: cada uno es una malla del modelo anatómico 3D del
# frontend (``M_<codigo>_<lado>``). Valor: (nombre, grupo al que pertenece).
MUSCULOS_DETALLADOS = {
    "pectoral_mayor": ("Pectoral mayor", "pecho"),
    "pectoral_menor": ("Pectoral menor", "pecho"),
    "recto_abdominal": ("Recto abdominal", "abdomen"),
    "oblicuo_externo": ("Oblicuo externo", "oblicuos"),
    "oblicuo_interno": ("Oblicuo interno", "oblicuos"),
    "serrato_anterior": ("Serrato anterior", "oblicuos"),
    "intercostales": ("Intercostales", "pecho"),
    "trapecio": ("Trapecio", "trapecio"),
    "dorsal_ancho": ("Dorsal ancho", "dorsales"),
    "romboides": ("Romboides", "dorsales"),
    "redondo_mayor": ("Redondo mayor", "dorsales"),
    "redondo_menor": ("Redondo menor", "dorsales"),
    "infraespinoso": ("Infraespinoso", "dorsales"),
    "erectores_espinales": ("Erectores espinales", "lumbares"),
    "deltoides_anterior": ("Deltoides anterior", "hombros"),
    "deltoides_lateral": ("Deltoides lateral", "hombros"),
    "deltoides_posterior": ("Deltoides posterior", "hombros"),
    "biceps_braquial": ("Bíceps braquial", "biceps"),
    "braquial": ("Braquial", "biceps"),
    "triceps_braquial": ("Tríceps braquial", "triceps"),
    "braquiorradial": ("Braquiorradial", "antebrazos"),
    "flexores_antebrazo": ("Flexores del antebrazo", "antebrazos"),
    "extensores_antebrazo": ("Extensores del antebrazo", "antebrazos"),
    "gluteo_mayor": ("Glúteo mayor", "gluteos"),
    "gluteo_medio": ("Glúteo medio", "gluteos"),
    "gluteo_menor": ("Glúteo menor", "gluteos"),
    "recto_femoral": ("Recto femoral", "cuadriceps"),
    "vasto_lateral": ("Vasto lateral", "cuadriceps"),
    "vasto_medial": ("Vasto medial", "cuadriceps"),
    "vasto_intermedio": ("Vasto intermedio", "cuadriceps"),
    "sartorio": ("Sartorio", "cuadriceps"),
    "aductores": ("Aductores", "aductores"),
    "biceps_femoral": ("Bíceps femoral", "isquiotibiales"),
    "semitendinoso": ("Semitendinoso", "isquiotibiales"),
    "semimembranoso": ("Semimembranoso", "isquiotibiales"),
    "gastrocnemio": ("Gastrocnemio", "pantorrillas"),
    "soleo": ("Sóleo", "pantorrillas"),
    "tibial_anterior": ("Tibial anterior", "pantorrillas"),
    "esternocleidomastoideo": ("Esternocleidomastoideo", "cuello"),
}

# Todos los códigos válidos con su nombre (grupos + detallados).
MUSCULOS = {
    **GRUPOS_MUSCULARES,
    **{codigo: nombre for codigo, (nombre, _grupo) in MUSCULOS_DETALLADOS.items()},
}


def validar_musculos(valor):
    """Lista sin repetidos de códigos de ``MUSCULOS``."""
    if valor in (None, ""):
        return
    if not isinstance(valor, list) or not all(isinstance(item, str) for item in valor):
        raise ValidationError("Envíe una lista de músculos.")
    desconocidos = sorted(set(valor) - set(MUSCULOS))
    if desconocidos:
        raise ValidationError(f"Músculos no reconocidos: {', '.join(desconocidos)}.")
    if len(set(valor)) != len(valor):
        raise ValidationError("Hay músculos repetidos.")


def validar_foto_registro(archivo):
    """Valida tamaño, contenido real y dimensiones de la foto subida."""
    if not archivo:
        return

    limite = getattr(settings, "FOTO_REGISTRO_MAX_BYTES", 5 * 1024 * 1024)
    dimension_maxima = getattr(settings, "FOTO_REGISTRO_MAX_DIMENSION", 10000)
    tamano = getattr(archivo, "size", 0)
    if tamano <= 0:
        raise ValidationError("La foto está vacía.")
    if tamano > limite:
        raise ValidationError(
            f"La foto supera el tamaño máximo permitido de "
            f"{limite / (1024 * 1024):g} MB."
        )

    try:
        archivo.seek(0)
        contenido = archivo.read(limite + 1)
    finally:
        archivo.seek(0)

    if len(contenido) > limite:
        raise ValidationError("La foto supera el tamaño máximo permitido.")

    try:
        with Image.open(BytesIO(contenido)) as imagen:
            formato = (imagen.format or "").upper()
            ancho, alto = imagen.size
            imagen.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError(
            "El archivo debe ser una imagen válida en formato JPEG, PNG o WebP."
        ) from error

    if formato not in FOTO_REGISTRO_FORMATOS:
        raise ValidationError("Solo se permiten imágenes JPEG, PNG o WebP.")
    if ancho > dimension_maxima or alto > dimension_maxima:
        raise ValidationError(
            f"La imagen supera la dimensión máxima de {dimension_maxima} px por lado."
        )


class ModeloAuditable(models.Model):
    """Campos comunes a las tablas que el SQL marca como borrables lógicamente."""

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, validar=False, **kwargs):
        """Valida solo cuando la operación lo requiere explícitamente.

        La API valida en los serializers y el borrado lógico no debe pagar el
        coste de ``full_clean``. Para escrituras directas críticas use
        ``save(validar=True)``.
        """
        if validar:
            self.full_clean()
        return super().save(*args, **kwargs)

    def liberar_restricciones_unicas(self):
        """Valores que deben dejar de ocupar índices únicos al eliminar."""
        return {}

    def soft_delete(self):
        """Desactiva el registro y propaga el borrado a sus dependientes.

        El registro se marca primero para que una cascada que regrese al mismo
        objeto (por ejemplo, Cliente -> Usuario -> Cliente) sea idempotente.
        Todo el borrado se ejecuta en una transacción.
        """
        if self.deleted_at is not None:
            return

        with transaction.atomic():
            cambios = self.liberar_restricciones_unicas()
            self.is_active = False
            self.deleted_at = timezone.now()
            for campo, valor in cambios.items():
                setattr(self, campo, valor)
            self.save(
                update_fields=["is_active", "deleted_at", "updated_at", *cambios.keys()]
            )
            self.propagar_borrado_logico()

    def propagar_borrado_logico(self):
        """Hook para desactivar registros dependientes. Cada modelo lo define."""
        return None


class BorradoLogicoSimple:
    """Borrado lógico para catálogos que solo tienen ``is_active``.

    ``Rol`` y ``Permiso`` no tienen ``deleted_at`` en el esquema, por lo que su
    borrado lógico consiste en desactivarlos y ocultarlos de las consultas.
    """

    def soft_delete(self):
        if not self.is_active:
            return

        with transaction.atomic():
            self.is_active = False
            self.save(update_fields=["is_active", "updated_at"])
            self.propagar_borrado_logico()

    def propagar_borrado_logico(self):
        return None


METODOS_PAGO_POR_DEFECTO = (
    {"nombre": "Efectivo", "tipo": "efectivo", "descripcion": "Pago en efectivo", "orden": 1, "requiere_referencia": False},
    {"nombre": "Transferencia", "tipo": "transferencia", "descripcion": "Transferencia bancaria", "orden": 2, "requiere_referencia": True},
    {"nombre": "Tarjeta débito", "tipo": "tarjeta", "descripcion": "Tarjeta de débito", "orden": 3, "requiere_referencia": True},
    {"nombre": "Tarjeta crédito", "tipo": "tarjeta", "descripcion": "Tarjeta de crédito", "orden": 4, "requiere_referencia": True},
    {"nombre": "Nequi", "tipo": "transferencia", "descripcion": "Nequi", "orden": 5, "requiere_referencia": True},
    {"nombre": "DaviPlata", "tipo": "transferencia", "descripcion": "DaviPlata", "orden": 6, "requiere_referencia": True},
    {"nombre": "Otro", "tipo": "otro", "descripcion": "Otro método de pago", "orden": 99, "requiere_referencia": False},
)

CATEGORIAS_GASTO_POR_DEFECTO = (
    {"nombre": "Arriendo", "tipo": "arriendo", "descripcion": "Arriendo del local", "color": "#ef4444", "orden": 1},
    {"nombre": "Servicios públicos", "tipo": "servicios_publicos", "descripcion": "Energía, agua, gas", "color": "#f97316", "orden": 2},
    {"nombre": "Nómina", "tipo": "nomina", "descripcion": "Sueldos y prestaciones", "color": "#eab308", "orden": 3},
    {"nombre": "Mantenimiento", "tipo": "mantenimiento", "descripcion": "Mantenimiento de equipos e instalaciones", "color": "#22c55e", "orden": 4},
    {"nombre": "Equipamiento", "tipo": "equipamiento", "descripcion": "Compra de equipos y máquinas", "color": "#06b6d4", "orden": 5},
    {"nombre": "Limpieza", "tipo": "limpieza", "descripcion": "Servicios de limpieza e insumos", "color": "#8b5cf6", "orden": 6},
    {"nombre": "Publicidad", "tipo": "publicidad", "descripcion": "Marketing y publicidad", "color": "#ec4899", "orden": 7},
    {"nombre": "Internet", "tipo": "internet", "descripcion": "Servicio de internet", "color": "#6366f1", "orden": 8},
    {"nombre": "Otros", "tipo": "otro", "descripcion": "Gastos varios", "color": "#64748b", "orden": 99},
)


class Gimnasio(ModeloAuditable):
    """Gimnasio cliente de la plataforma (tenant).

    Cada usuario pertenece a un solo gimnasio y todos los datos operativos y
    financieros cuelgan de él, directa o indirectamente. Los gimnasios los crea
    el personal de la plataforma (superusuario de Django), nunca un usuario de
    otro gimnasio.
    """

    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    codigo = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Identificador corto y único; los clientes lo usan al registrarse.",
    )
    nit = models.CharField(max_length=30, null=True, blank=True)
    ciudad = models.CharField(max_length=100, null=True, blank=True)
    direccion = models.CharField(max_length=255, null=True, blank=True)
    telefono = models.CharField(max_length=30, null=True, blank=True)
    correo = models.EmailField(max_length=191, null=True, blank=True)
    # Configuración del centro de alertas.
    dias_inactividad_alerta = models.PositiveSmallIntegerField(
        default=15,
        help_text="Días sin asistir para alertar que un cliente dejó de venir.",
    )
    limite_gastos_mensual = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Alerta cuando los gastos del mes superan este valor. Vacío: sin límite.",
    )
    porcentaje_caida_ingresos = models.PositiveSmallIntegerField(
        default=30,
        help_text="Alerta cuando los ingresos del mes caen este porcentaje frente al mes anterior.",
    )

    class Meta:
        db_table = "gimnasios"
        ordering = ["nombre", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(limite_gastos_mensual__isnull=True) | Q(limite_gastos_mensual__gt=0),
                name="chk_gimnasio_limite_gastos",
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_caida_ingresos__lte=100),
                name="chk_gimnasio_caida_ingresos",
            ),
        ]

    def clean(self):
        super().clean()
        self.nombre = (self.nombre or "").strip()
        self.codigo = (self.codigo or "").strip().lower()
        for campo in ("nit", "ciudad", "direccion", "telefono"):
            setattr(self, campo, normalizar_texto_opcional(getattr(self, campo)))
        self.correo = normalizar_correo(self.correo) or None
        if not 1 <= (self.dias_inactividad_alerta or 0) <= 365:
            raise ValidationError(
                {"dias_inactividad_alerta": "Debe estar entre 1 y 365 días."}
            )
        if not 1 <= (self.porcentaje_caida_ingresos or 0) <= 100:
            raise ValidationError(
                {"porcentaje_caida_ingresos": "Debe estar entre 1 y 100."}
            )

    def save(self, *args, **kwargs):
        nuevo = self._state.adding
        self.nombre = (self.nombre or "").strip()
        self.codigo = (self.codigo or "").strip().lower()
        with transaction.atomic():
            resultado = super().save(*args, **kwargs)
            if nuevo:
                self.inicializar()
        return resultado

    def inicializar(self):
        """Deja listo un gimnasio recién creado: catálogos y matriz de permisos."""
        for datos in METODOS_PAGO_POR_DEFECTO:
            MetodoPago.objects.get_or_create(
                gimnasio=self, nombre=datos["nombre"], defaults=dict(datos)
            )
        for datos in CATEGORIAS_GASTO_POR_DEFECTO:
            CategoriaGasto.objects.get_or_create(
                gimnasio=self, nombre=datos["nombre"], defaults=dict(datos)
            )
        self.copiar_matriz_permisos()

    def copiar_matriz_permisos(self):
        """Copia la plantilla de permisos (filas sin gimnasio) a este gimnasio.

        Cada gimnasio tiene su propia matriz rol-permiso: así un administrador
        solo cambia lo que pueden hacer los roles dentro de su gimnasio.
        """
        RolPermiso.objects.bulk_create(
            [
                RolPermiso(gimnasio=self, rol_id=rol_id, permiso_id=permiso_id)
                for rol_id, permiso_id in RolPermiso.objects.filter(
                    gimnasio__isnull=True
                ).values_list("rol_id", "permiso_id")
            ],
            ignore_conflicts=True,
        )
        RolRecurso.objects.bulk_create(
            [
                RolRecurso(gimnasio=self, rol_id=rol_id, recurso_id=recurso_id)
                for rol_id, recurso_id in RolRecurso.objects.filter(
                    gimnasio__isnull=True
                ).values_list("rol_id", "recurso_id")
            ],
            ignore_conflicts=True,
        )

    @classmethod
    def unico_activo_id(cls):
        """Id del gimnasio si la plataforma tiene exactamente uno activo.

        Permite que comandos y escrituras directas sin gimnasio sigan
        funcionando en instalaciones de un solo gimnasio. Con dos o más no hay
        una respuesta segura y se devuelve ``None``.
        """
        ids = list(
            cls.objects.filter(is_active=True, deleted_at__isnull=True).values_list(
                "pk", flat=True
            )[:2]
        )
        return ids[0] if len(ids) == 1 else None

    def __str__(self):
        return self.nombre


class AsignaGimnasioMixin:
    """Resuelve el gimnasio de un registro antes de validarlo o guardarlo.

    ``ORIGENES_GIMNASIO`` lista rutas (``cliente.usuario``, ``membresia``...)
    hacia un objeto con ``gimnasio_id``. Si alguna resuelve, manda sobre lo que
    traiga el registro: un pago siempre es del gimnasio de su cliente. Si no,
    se usa el gimnasio del actor y, como último recurso, el único gimnasio
    activo de la plataforma.
    """

    ORIGENES_GIMNASIO = ()

    def asignar_gimnasio(self, actor=None):
        for ruta in self.ORIGENES_GIMNASIO:
            origen = self
            for parte in ruta.split("."):
                if origen is None:
                    break
                if not getattr(origen, f"{parte}_id", True):
                    origen = None
                    break
                origen = getattr(origen, parte, None)
            gimnasio_id = getattr(origen, "gimnasio_id", None)
            if gimnasio_id:
                self.gimnasio_id = gimnasio_id
                return
        if self.gimnasio_id:
            return
        gimnasio_id = getattr(actor, "gimnasio_id", None) if isinstance(actor, Usuario) else None
        self.gimnasio_id = gimnasio_id or Gimnasio.unico_activo_id()

    def clean_fields(self, exclude=None):
        # El gimnasio se resuelve antes de validar los campos obligatorios.
        self.asignar_gimnasio()
        return super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        self.validar_relaciones_del_gimnasio()

    def validar_relaciones_del_gimnasio(self):
        """Toda relación del registro debe ser del mismo gimnasio.

        La API ya filtra las claves foráneas por gimnasio; esto protege
        también las escrituras desde comandos o la consola.
        """
        if not self.gimnasio_id:
            return
        errores = {}
        for campo in self._meta.concrete_fields:
            if not campo.is_relation or campo.name == "gimnasio":
                continue
            if not getattr(self, campo.attname, None):
                continue
            relacionado = getattr(self, campo.name)
            gimnasio_id = getattr(relacionado, "gimnasio_id", None)
            if gimnasio_id is None and hasattr(relacionado, "usuario_id"):
                gimnasio_id = getattr(relacionado.usuario, "gimnasio_id", None)
            if gimnasio_id is not None and gimnasio_id != self.gimnasio_id:
                errores[campo.name] = "Pertenece a otro gimnasio."
        if errores:
            raise ValidationError(errores)

    def _gimnasio_antes_de_guardar(self):
        self.asignar_gimnasio()
        if not self.gimnasio_id:
            raise ValidationError(
                {"gimnasio": "Indique a qué gimnasio pertenece el registro."}
            )


class Recurso(BorradoLogicoSimple, models.Model):
    """Recurso protegible del sistema.

    Un recurso es la unidad que aparece en la matriz RBAC (por ejemplo,
    ``clientes`` o ``planes-entrenamiento``).  Las acciones concretas se
    mantienen en :class:`Permiso`; separar ambas entidades evita que el
    nombre del recurso sea una cadena sin integridad referencial.
    """

    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "recursos"
        indexes = [models.Index(fields=["is_active"], name="idx_recursos_active")]
        ordering = ["nombre"]

    def clean(self):
        super().clean()
        self.nombre = (self.nombre or "").strip().lower()

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip().lower()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Rol(BorradoLogicoSimple, models.Model):
    class Nombre(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        ENTRENADOR = "entrenador", "Entrenador"
        TERAPEUTA = "terapeuta", "Terapeuta"
        RECEPCIONISTA = "recepcionista", "Recepcionista"
        ADMINISTRADOR = "administrador", "Administrador"

    id = models.BigAutoField(primary_key=True)
    # Sin ``choices`` para permitir roles personalizados. ``Nombre`` se conserva
    # como catálogo de los roles base que tienen un perfil asociado.
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    # Vacío en los roles del sistema (compartidos por todos los gimnasios). Un
    # rol personalizado pertenece al gimnasio que lo creó y solo se ve allí.
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.CASCADE,
        related_name="roles_propios",
        db_column="gimnasio_id",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    permisos = models.ManyToManyField(
        "Permiso", through="RolPermiso", related_name="roles", blank=True
    )
    recursos = models.ManyToManyField(
        "Recurso", through="RolRecurso", related_name="roles", blank=True
    )

    class Meta:
        db_table = "roles"
        indexes = [models.Index(fields=["is_active"], name="idx_roles_active")]
        ordering = ["nombre"]

    @property
    def es_del_sistema(self):
        return self.gimnasio_id is None

    def propagar_borrado_logico(self):
        # Un rol inactivo deja de aportar permisos; sus asignaciones quedan
        # registradas para auditoría, pero se marcan como inactivas.
        self.asignaciones_usuarios.filter(activo=True).update(activo=False)

    def __str__(self):
        return self.nombre


class Permiso(BorradoLogicoSimple, models.Model):
    """Permiso atómico identificado por ``recurso:accion``."""

    class Accion(models.TextChoices):
        VIEW = "view", "Ver"
        CREATE = "create", "Crear"
        EDIT = "edit", "Editar"
        DELETE = "delete", "Eliminar"
        EXPORT = "export", "Exportar"

    id = models.BigAutoField(primary_key=True)
    codigo = models.CharField(max_length=100, unique=True)
    # Se conserva ``recurso`` como código estable para la API y los permisos
    # legibles, pero la FK es la fuente de integridad referencial.
    recurso_catalogo = models.ForeignKey(
        Recurso,
        on_delete=models.PROTECT,
        related_name="permisos",
        db_column="recurso_id",
        blank=True,
    )
    recurso = models.CharField(max_length=50)
    accion = models.CharField(max_length=20, choices=Accion.choices)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "permisos"
        constraints = [
            models.UniqueConstraint(fields=["recurso", "accion"], name="uq_permiso_recurso_accion")
        ]
        indexes = [
            models.Index(fields=["recurso"], name="idx_permiso_recurso"),
            models.Index(fields=["is_active"], name="idx_permiso_active"),
        ]
        ordering = ["recurso", "accion"]

    def clean(self):
        super().clean()
        self.recurso = (self.recurso or "").strip().lower()
        self.accion = (self.accion or "").strip().lower()
        self.codigo = f"{self.recurso}:{self.accion}"

    def save(self, *args, **kwargs):
        self.recurso = (self.recurso or "").strip().lower()
        self.accion = (self.accion or "").strip().lower()
        self.codigo = f"{self.recurso}:{self.accion}"
        # Mantiene el catálogo de recursos normalizado incluso para escrituras
        # directas desde comandos de gestión o la consola de Django.
        recurso, _ = Recurso.objects.get_or_create(nombre=self.recurso)
        self.recurso_catalogo = recurso
        resultado = super().save(*args, **kwargs)
        # Si se reclasifica un permiso ya concedido, sus roles también deben
        # quedar vinculados al nuevo recurso antes de poder usarlo.
        for rol_id, gimnasio_id in self.roles_asignados.values_list("rol_id", "gimnasio_id"):
            RolRecurso.objects.get_or_create(
                rol_id=rol_id, recurso=recurso, gimnasio_id=gimnasio_id
            )
        return resultado

    def __str__(self):
        return self.codigo


class RolPermiso(models.Model):
    """Asignación de un permiso atómico a un rol."""

    id = models.BigAutoField(primary_key=True)
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="permisos_asignados", db_column="rol_id")
    permiso = models.ForeignKey(
        Permiso, on_delete=models.CASCADE, related_name="roles_asignados", db_column="permiso_id"
    )
    # Gimnasio al que aplica la concesión. Las filas sin gimnasio son la
    # plantilla que se copia a cada gimnasio nuevo y no conceden nada.
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.CASCADE,
        related_name="rol_permisos",
        db_column="gimnasio_id",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rol_permiso"
        constraints = [
            models.UniqueConstraint(
                fields=["gimnasio", "rol", "permiso"], name="uq_gimnasio_rol_permiso"
            )
        ]
        indexes = [
            models.Index(fields=["rol"], name="idx_rolpermiso_rol"),
            models.Index(fields=["permiso"], name="idx_rolpermiso_permiso"),
        ]
        ordering = ["rol", "permiso"]

    def __str__(self):
        return f"{self.rol.nombre} -> {self.permiso.codigo}"

    def save(self, *args, **kwargs):
        resultado = super().save(*args, **kwargs)
        recurso, _ = Recurso.objects.get_or_create(nombre=self.permiso.recurso)
        RolRecurso.objects.get_or_create(
            rol=self.rol, recurso=recurso, gimnasio_id=self.gimnasio_id
        )
        return resultado


class RolRecurso(models.Model):
    """Puente N:M entre roles y recursos, equivalente a ``rol_has_recurso``.

    Se conserva separado de ``RolPermiso``: el puente expresa *a qué módulo*
    puede entrar un rol, mientras que los permisos expresan *qué operación*
    puede ejecutar dentro de ese módulo.
    """

    id = models.BigAutoField(primary_key=True)
    rol = models.ForeignKey(
        Rol, on_delete=models.CASCADE, related_name="recursos_asignados", db_column="rol_id"
    )
    recurso = models.ForeignKey(
        Recurso,
        on_delete=models.CASCADE,
        related_name="roles_asignados",
        db_column="recurso_id",
    )
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.CASCADE,
        related_name="rol_recursos",
        db_column="gimnasio_id",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rol_has_recurso"
        constraints = [
            models.UniqueConstraint(
                fields=["gimnasio", "rol", "recurso"], name="uq_gimnasio_rol_recurso"
            )
        ]
        indexes = [
            models.Index(fields=["rol"], name="idx_rolrecurso_rol"),
            models.Index(fields=["recurso"], name="idx_rolrecurso_recurso"),
        ]
        ordering = ["rol", "recurso"]

    def __str__(self):
        return f"{self.rol.nombre} -> {self.recurso.nombre}"


class Usuario(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    # Cada usuario pertenece a un único gimnasio; de él cuelgan sus datos.
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="usuarios",
        db_column="gimnasio_id",
    )
    # ``rol`` es el rol principal y se conserva para login/perfiles existentes.
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="usuarios", db_column="rol_id")
    roles = models.ManyToManyField(
        Rol,
        through="UsuarioRol",
        through_fields=("usuario", "rol"),
        related_name="usuarios_asignados",
        blank=True,
    )
    nombre = models.CharField(max_length=150)
    username = models.CharField(max_length=100, null=True, blank=True, unique=True)
    correo = models.EmailField(max_length=191, unique=True)
    # Nunca se expone a través del serializer: usa set_password/check_password.
    contrasena_hash = models.CharField(max_length=255)
    telefono = models.CharField(max_length=30, null=True, blank=True)

    class Meta:
        db_table = "usuarios"
        constraints = [
            models.UniqueConstraint(Lower("correo"), name="uq_usuario_correo_lower"),
            models.UniqueConstraint(Lower("username"), name="uq_usuario_username_lower"),
        ]
        indexes = [
            models.Index(fields=["gimnasio", "is_active"], name="idx_usuarios_gimnasio"),
            models.Index(fields=["rol", "is_active"], name="idx_usuarios_rol_activo"),
            models.Index(fields=["deleted_at"], name="idx_usuarios_deleted_at"),
            models.Index(fields=["nombre"], name="idx_usuarios_nombre"),
        ]
        ordering = ["nombre", "id"]

    def clean_fields(self, exclude=None):
        # En una plataforma de un solo gimnasio, el usuario pertenece a ese.
        if not self.gimnasio_id:
            self.gimnasio_id = Gimnasio.unico_activo_id()
        return super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        self.nombre = (self.nombre or "").strip()
        self.correo = normalizar_correo(self.correo)
        self.username = normalizar_username(self.username)
        self.telefono = normalizar_texto_opcional(self.telefono)

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.correo = normalizar_correo(self.correo)
        self.username = normalizar_username(self.username)
        self.telefono = normalizar_texto_opcional(self.telefono)
        if not self.gimnasio_id:
            self.gimnasio_id = Gimnasio.unico_activo_id()
            if not self.gimnasio_id:
                raise ValidationError(
                    {"gimnasio": "Indique a qué gimnasio pertenece el usuario."}
                )
        return super().save(*args, **kwargs)

    def liberar_restricciones_unicas(self):
        return {
            "correo": correo_liberado(self.correo, self.pk),
            "username": _valor_con_sufijo(self.username, f"__eliminado_{self.pk}", 100),
        }

    def propagar_borrado_logico(self):
        # La identidad y su perfil viven en tablas distintas, pero se eliminan
        # como una sola unidad. La cascada es idempotente por deleted_at.
        for relacion in ("cliente", "entrenador", "terapeuta", "recepcionista", "administrador"):
            try:
                perfil = getattr(self, relacion)
            except (ObjectDoesNotExist, AttributeError):
                continue
            perfil.soft_delete()
        self.asignaciones_usuarios.filter(activo=True).update(activo=False)
        self.notificaciones.filter(deleted_at__isnull=True).update(
            is_active=False, deleted_at=timezone.now()
        )
        self.sesiones.all().delete()

    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password

        self.contrasena_hash = make_password(raw_password)

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password

        return check_password(raw_password, self.contrasena_hash)

    def roles_efectivos(self):
        """Roles activos del usuario, incluyendo siempre su rol principal."""
        if not self.pk:
            return Rol.objects.none()
        return Rol.objects.filter(
            Q(pk=self.rol_id, is_active=True)
            | Q(
                asignaciones_usuarios__usuario_id=self.pk,
                asignaciones_usuarios__activo=True,
                is_active=True,
            )
        ).distinct()

    def permisos_efectivos(self):
        """Códigos de permisos vigentes para el usuario (deny-by-default)."""
        if not self.pk:
            return Permiso.objects.none()
        return (
            Permiso.objects.filter(
                is_active=True,
                roles_asignados__gimnasio_id=self.gimnasio_id,
                roles_asignados__rol__in=self.roles_efectivos(),
                roles_asignados__rol__recursos_asignados__gimnasio_id=self.gimnasio_id,
                roles_asignados__rol__recursos_asignados__recurso_id=F("recurso_catalogo_id"),
                roles_asignados__rol__recursos_asignados__recurso__is_active=True,
            )
            .values_list("codigo", flat=True)
            .distinct()
        )

    def tiene_permiso(self, codigo):
        if not self.pk:
            return False
        return (
            Permiso.objects.filter(
                codigo=codigo,
                is_active=True,
                roles_asignados__gimnasio_id=self.gimnasio_id,
                roles_asignados__rol__in=self.roles_efectivos(),
                roles_asignados__rol__recursos_asignados__gimnasio_id=self.gimnasio_id,
                roles_asignados__rol__recursos_asignados__recurso_id=F("recurso_catalogo_id"),
                roles_asignados__rol__recursos_asignados__recurso__is_active=True,
            )
            .exists()
        )

    def recursos_efectivos(self):
        """Recursos activos concedidos por cualquiera de sus roles activos."""
        if not self.pk:
            return Recurso.objects.none()
        return Recurso.objects.filter(
            is_active=True,
            roles_asignados__gimnasio_id=self.gimnasio_id,
            roles_asignados__rol__in=self.roles_efectivos(),
        ).distinct()

    def asignar_rol(self, rol, asignado_por=None, activo=True):
        """Crea o reactiva una asignación sin duplicarla (unique usuario+rol)."""
        asignacion, _ = UsuarioRol.objects.update_or_create(
            usuario=self,
            rol=rol,
            defaults={"activo": activo, "asignado_por": asignado_por},
        )
        return asignacion

    def cambiar_rol_principal(self, nuevo_rol):
        """Cambia el rol principal y adapta el perfil tipado.

        El perfil anterior solo se elimina cuando no tiene registros
        protegidos. Si los tiene, se propaga ``ProtectedError`` para que la
        API explique que primero deben reasignarse o eliminarse esos datos.
        """
        if not self.pk or nuevo_rol.pk == self.rol_id:
            return False

        perfil_anterior = None
        if self.rol.nombre in PERFILES_POR_ROL:
            try:
                perfil_anterior = getattr(self, self.rol.nombre)
            except ObjectDoesNotExist:
                perfil_anterior = None
        if perfil_anterior is not None:
            perfil_anterior.delete()

        self.rol = nuevo_rol
        self.save(update_fields=["rol", "updated_at"])

        modelo_perfil = PERFILES_POR_ROL.get(nuevo_rol.nombre)
        if modelo_perfil is not None and not modelo_perfil.objects.filter(
            pk=self.pk
        ).exists():
            perfil = modelo_perfil(usuario=self)
            perfil.full_clean()
            perfil.save()
        return True

    @property
    def is_authenticated(self):
        """Compatibilidad con ``IsAuthenticated`` de Django REST Framework."""
        return True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return f"{self.nombre} ({self.correo})"


class UsuarioRol(models.Model):
    """Asignación N:M entre usuarios y roles adicionales."""

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="asignaciones_usuarios", db_column="usuario_id"
    )
    rol = models.ForeignKey(
        Rol, on_delete=models.PROTECT, related_name="asignaciones_usuarios", db_column="rol_id"
    )
    activo = models.BooleanField(default=True)
    asignado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        related_name="asignaciones_realizadas",
        db_column="asignado_por_id",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "usuario_rol"
        constraints = [
            models.UniqueConstraint(fields=["usuario", "rol"], name="uq_usuario_rol")
        ]
        indexes = [
            models.Index(fields=["activo"], name="idx_usrrol_activo"),
            models.Index(fields=["usuario", "activo"], name="idx_usrrol_usuario_activo"),
            models.Index(fields=["rol", "activo"], name="idx_usrrol_rol_activo"),
        ]
        ordering = ["usuario", "rol"]

    def __str__(self):
        return f"{self.usuario.nombre} -> {self.rol.nombre}"


class Sesion(models.Model):
    """Sesión revocable para la autenticación Bearer de ``Usuario``.

    Solo se persiste el hash SHA-256 del secreto: si la base de datos se
    filtrara, no se puede usar directamente para entrar a la API.
    """

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="sesiones", db_column="usuario_id")
    token_hash = models.CharField(max_length=64, unique=True)
    creada_at = models.DateTimeField(auto_now_add=True)
    expira_at = models.DateTimeField()

    class Meta:
        db_table = "sesiones"
        indexes = [models.Index(fields=["usuario", "expira_at"], name="idx_sesion_usuario_expira")]

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def crear_para_usuario(cls, usuario):
        ahora = timezone.now()
        cls.objects.filter(usuario=usuario, expira_at__lte=ahora).delete()
        token = secrets.token_urlsafe(32)
        sesion = cls.objects.create(
            usuario=usuario,
            token_hash=cls.hash_token(token),
            expira_at=ahora + timedelta(hours=settings.AUTH_TOKEN_TTL_HOURS),
        )
        return token, sesion


class PerfilBase(ModeloAuditable):
    """Valida la correspondencia rol-perfil que en MySQL controla un trigger."""

    rol_requerido = None

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.usuario_id and self.rol_requerido:
            if self.usuario.rol.nombre != self.rol_requerido:
                raise ValidationError(
                    {"usuario": f"Este perfil requiere un usuario con rol '{self.rol_requerido}'."}
                )

    def propagar_borrado_logico(self):
        self.usuario.soft_delete()


class Cliente(PerfilBase):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, related_name="cliente", db_column="usuario_id"
    )
    tipo_documento = models.CharField(max_length=20, null=True, blank=True)
    numero_documento = models.CharField(max_length=30, null=True, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    objetivo = models.CharField(max_length=255, null=True, blank=True)
    peso_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    estatura_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rol_requerido = Rol.Nombre.CLIENTE

    class Meta:
        db_table = "cliente"
        constraints = [
            models.UniqueConstraint(
                Lower("tipo_documento"),
                Lower("numero_documento"),
                name="uq_cliente_documento_lower",
            ),
            models.CheckConstraint(condition=Q(peso_kg__isnull=True) | Q(peso_kg__gt=0), name="chk_cliente_peso"),
            models.CheckConstraint(
                condition=Q(estatura_cm__isnull=True) | Q(estatura_cm__gt=0), name="chk_cliente_estatura"
            ),
        ]
        indexes = [
            models.Index(fields=["objetivo"], name="idx_cliente_objetivo"),
            models.Index(fields=["is_active"], name="idx_cliente_active"),
        ]

    def _normalizar_campos(self):
        self.tipo_documento = normalizar_texto_opcional(self.tipo_documento)
        self.numero_documento = normalizar_texto_opcional(self.numero_documento)
        if self.tipo_documento:
            self.tipo_documento = self.tipo_documento.upper()
        if self.numero_documento:
            self.numero_documento = self.numero_documento.upper()
        self.objetivo = normalizar_texto_opcional(self.objetivo)

    def clean(self):
        self._normalizar_campos()
        super().clean()
        errores = {}
        if self.numero_documento:
            # Mismo criterio que ``uq_cliente_documento_lower``, pero con un
            # mensaje por campo en lugar del nombre interno de la restricción.
            if self.tipo_documento:
                repetido = Cliente.objects.filter(
                    tipo_documento__iexact=self.tipo_documento,
                    numero_documento__iexact=self.numero_documento,
                )
            else:
                repetido = Cliente.objects.filter(
                    tipo_documento__isnull=True,
                    numero_documento__iexact=self.numero_documento,
                )
            if repetido.exclude(pk=self.pk).exists():
                errores["numero_documento"] = "Ya existe un cliente con este tipo y número de documento."
        if self.peso_kg is not None and self.peso_kg <= 0:
            errores["peso_kg"] = "El peso debe ser mayor que cero."
        if self.estatura_cm is not None and self.estatura_cm <= 0:
            errores["estatura_cm"] = "La estatura debe ser mayor que cero."
        if self.fecha_nacimiento and self.fecha_nacimiento > timezone.localdate():
            errores["fecha_nacimiento"] = "La fecha de nacimiento no puede ser futura."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self._normalizar_campos()
        return super().save(*args, **kwargs)

    def liberar_restricciones_unicas(self):
        if self.tipo_documento and self.numero_documento:
            return {
                "numero_documento": _valor_con_sufijo(
                    self.numero_documento, f"-DEL-{self.pk}", 30
                )
            }
        return {}

    def propagar_borrado_logico(self):
        # Datos operativos del cliente: se ocultan con él para no dejar filas
        # huérfanas visibles en sus endpoints. Los planes propagan sus hijos.
        for relacion in (
            "asignaciones_entrenador",
            "asignaciones_terapeuta",
            "asistencias",
            "entrenamientos",
            "planes_entrenamiento",
            "planes_alimentacion",
            "registros_comida",
        ):
            for registro in getattr(self, relacion).filter(deleted_at__isnull=True):
                registro.soft_delete()
        super().propagar_borrado_logico()

    def __str__(self):
        return self.usuario.nombre


class Entrenador(PerfilBase):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, related_name="entrenador", db_column="usuario_id"
    )
    especialidad = models.CharField(max_length=150, null=True, blank=True)
    certificacion = models.CharField(max_length=255, null=True, blank=True)
    fecha_ingreso = models.DateField(null=True, blank=True)
    biografia = models.TextField(null=True, blank=True)
    rol_requerido = Rol.Nombre.ENTRENADOR

    class Meta:
        db_table = "entrenador"
        indexes = [
            models.Index(fields=["especialidad"], name="idx_entrenador_especialidad"),
            models.Index(fields=["is_active"], name="idx_entrenador_active"),
        ]

    def propagar_borrado_logico(self):
        # Libera a los clientes de una asignación activa antes de desactivar la
        # cuenta, para que puedan ser reasignados a otro entrenador.
        for asignacion in self.asignaciones_cliente.filter(deleted_at__isnull=True):
            asignacion.soft_delete()
        super().propagar_borrado_logico()

    def __str__(self):
        return self.usuario.nombre


class Administrador(PerfilBase):
    class NivelPermisos(models.TextChoices):
        OPERATIVO = "operativo", "Operativo"
        GESTION = "gestion", "Gestión"
        TOTAL = "total", "Total"

    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, related_name="administrador", db_column="usuario_id"
    )
    cargo = models.CharField(max_length=100, default="Administrador")
    fecha_ingreso = models.DateField(null=True, blank=True)
    nivel_permisos = models.CharField(max_length=10, choices=NivelPermisos.choices, default=NivelPermisos.GESTION)
    rol_requerido = Rol.Nombre.ADMINISTRADOR

    class Meta:
        db_table = "administrador"
        indexes = [models.Index(fields=["nivel_permisos"], name="idx_administrador_nivel")]

    def __str__(self):
        return self.usuario.nombre


class Terapeuta(PerfilBase):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, related_name="terapeuta", db_column="usuario_id"
    )
    especialidad = models.CharField(max_length=150, null=True, blank=True)
    licencia_profesional = models.CharField(max_length=100, null=True, blank=True, unique=True)
    fecha_ingreso = models.DateField(null=True, blank=True)
    rol_requerido = Rol.Nombre.TERAPEUTA

    class Meta:
        db_table = "terapeuta"
        constraints = [
            models.UniqueConstraint(
                Lower("licencia_profesional"), name="uq_terapeuta_licencia_lower"
            )
        ]
        indexes = [models.Index(fields=["especialidad"], name="idx_terapeuta_especialidad")]

    def _normalizar_campos(self):
        self.licencia_profesional = normalizar_texto_opcional(self.licencia_profesional)
        if self.licencia_profesional:
            self.licencia_profesional = self.licencia_profesional.upper()

    def clean(self):
        self._normalizar_campos()
        super().clean()

    def save(self, *args, **kwargs):
        self._normalizar_campos()
        return super().save(*args, **kwargs)

    def liberar_restricciones_unicas(self):
        if self.licencia_profesional:
            return {
                "licencia_profesional": _valor_con_sufijo(
                    self.licencia_profesional, f"-DEL-{self.pk}", 100
                )
            }
        return {}

    def propagar_borrado_logico(self):
        for asignacion in self.asignaciones_cliente.filter(deleted_at__isnull=True):
            asignacion.soft_delete()
        super().propagar_borrado_logico()

    def __str__(self):
        return self.usuario.nombre


class Recepcionista(PerfilBase):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, related_name="recepcionista", db_column="usuario_id"
    )
    fecha_ingreso = models.DateField(null=True, blank=True)
    turno_preferido = models.CharField(max_length=50, null=True, blank=True)
    rol_requerido = Rol.Nombre.RECEPCIONISTA

    class Meta:
        db_table = "recepcionista"
        indexes = [models.Index(fields=["is_active"], name="idx_recepcionista_active")]

    def __str__(self):
        return self.usuario.nombre


# Perfil que corresponde a cada rol base. Los roles personalizados no tienen
# perfil propio; al cambiar a uno de ellos solo se conserva la identidad.
PERFILES_POR_ROL = {
    Rol.Nombre.CLIENTE: Cliente,
    Rol.Nombre.ENTRENADOR: Entrenador,
    Rol.Nombre.TERAPEUTA: Terapeuta,
    Rol.Nombre.RECEPCIONISTA: Recepcionista,
    Rol.Nombre.ADMINISTRADOR: Administrador,
}


class ClienteEntrenador(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="asignaciones_entrenador", db_column="cliente_id")
    entrenador = models.ForeignKey(
        Entrenador, on_delete=models.PROTECT, related_name="asignaciones_cliente", db_column="entrenador_id"
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "cliente_entrenador"
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=F("fecha_inicio")), name="chk_ce_fechas"
            )
        ]
        indexes = [
            models.Index(fields=["cliente", "fecha_inicio", "fecha_fin"], name="idx_ce_cliente_periodo"),
            models.Index(fields=["entrenador", "fecha_inicio", "fecha_fin"], name="idx_ce_entrenador_periodo"),
            models.Index(fields=["activo", "is_active"], name="idx_ce_activo"),
        ]

    @classmethod
    def entrenador_asignado(cls, cliente_id, entrenador_id):
        return cls.objects.filter(
            cliente_id=cliente_id,
            entrenador_id=entrenador_id,
            activo=True,
            is_active=True,
            deleted_at__isnull=True,
            cliente__is_active=True,
            cliente__deleted_at__isnull=True,
            cliente__usuario__is_active=True,
            cliente__usuario__deleted_at__isnull=True,
            entrenador__is_active=True,
            entrenador__deleted_at__isnull=True,
            entrenador__usuario__is_active=True,
            entrenador__usuario__deleted_at__isnull=True,
        ).exists()

    def clean(self):
        super().clean()
        if (
            self.deleted_at is not None
            or not self.cliente_id
            or not self.entrenador_id
            or not self.fecha_inicio
        ):
            return

        if (
            not self.cliente.is_active
            or self.cliente.deleted_at is not None
            or not self.cliente.usuario.is_active
            or self.cliente.usuario.deleted_at is not None
        ):
            raise ValidationError({"cliente": "El cliente debe estar activo."})
        if (
            not self.entrenador.is_active
            or self.entrenador.deleted_at is not None
            or not self.entrenador.usuario.is_active
            or self.entrenador.usuario.deleted_at is not None
        ):
            raise ValidationError({"entrenador": "El entrenador debe estar activo."})

        if self.fecha_fin is not None and self.fecha_fin < self.fecha_inicio:
            raise ValidationError(
                {"fecha_fin": "La fecha fin no puede ser anterior a la fecha inicio."}
            )

        otras = type(self).objects.filter(
            cliente_id=self.cliente_id, deleted_at__isnull=True
        ).exclude(pk=self.pk)
        if self.activo and self.is_active and otras.filter(
            activo=True, is_active=True
        ).exists():
            raise ValidationError(
                {"activo": "El cliente ya tiene una asignación activa con otro entrenador."}
            )

        solapadas = otras
        if self.fecha_fin is not None:
            solapadas = solapadas.filter(fecha_inicio__lte=self.fecha_fin)
        solapadas = solapadas.filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=self.fecha_inicio)
        )
        if solapadas.exists():
            raise ValidationError(
                {"fecha_inicio": "El periodo se solapa con otra asignación del cliente."}
            )

    def __str__(self):
        return f"{self.cliente} - {self.entrenador}"


class ClienteTerapeuta(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="asignaciones_terapeuta",
        db_column="cliente_id",
    )
    terapeuta = models.ForeignKey(
        Terapeuta,
        on_delete=models.PROTECT,
        related_name="asignaciones_cliente",
        db_column="terapeuta_id",
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "cliente_terapeuta"
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=F("fecha_inicio")),
                name="chk_ct_fechas",
            )
        ]
        indexes = [
            models.Index(
                fields=["cliente", "fecha_inicio", "fecha_fin"],
                name="idx_ct_cliente_periodo",
            ),
            models.Index(
                fields=["terapeuta", "fecha_inicio", "fecha_fin"],
                name="idx_ct_terapeuta_periodo",
            ),
            models.Index(fields=["activo", "is_active"], name="idx_ct_activo"),
        ]

    def clean(self):
        super().clean()
        if self.deleted_at is not None or not self.cliente_id or not self.fecha_inicio:
            return
        if self.fecha_fin is not None and self.fecha_fin < self.fecha_inicio:
            raise ValidationError(
                {"fecha_fin": "La fecha fin no puede ser anterior a la fecha inicio."}
            )

        otras = type(self).objects.filter(
            cliente_id=self.cliente_id, deleted_at__isnull=True
        ).exclude(pk=self.pk)
        if self.activo and self.is_active and otras.filter(
            activo=True, is_active=True
        ).exists():
            raise ValidationError(
                {"activo": "El cliente ya tiene una asignación activa con otro terapeuta."}
            )

        solapadas = otras
        if self.fecha_fin is not None:
            solapadas = solapadas.filter(fecha_inicio__lte=self.fecha_fin)
        solapadas = solapadas.filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=self.fecha_inicio)
        )
        if solapadas.exists():
            raise ValidationError(
                {"fecha_inicio": "El periodo se solapa con otra asignación del cliente."}
            )

    def __str__(self):
        return f"{self.cliente} - {self.terapeuta}"


class Asistencia(AsignaGimnasioMixin, ModeloAuditable):
    class MetodoEntrada(models.TextChoices):
        QR = "qr", "Código QR"
        FACIAL = "facial", "Reconocimiento facial"
        MANUAL = "manual", "Manual"

    id = models.BigAutoField(primary_key=True)
    ORIGENES_GIMNASIO = ("cliente.usuario",)
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="asistencias",
        db_column="gimnasio_id",
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="asistencias", db_column="cliente_id")
    entrada_at = models.DateTimeField()
    salida_at = models.DateTimeField(null=True, blank=True)
    metodo_entrada = models.CharField(max_length=10, choices=MetodoEntrada.choices, default=MetodoEntrada.QR)
    identificador_evento = models.CharField(max_length=255, null=True, blank=True, unique=True)

    class Meta:
        db_table = "asistencias"
        constraints = [
            models.CheckConstraint(
                condition=Q(salida_at__isnull=True) | Q(salida_at__gte=F("entrada_at")),
                name="chk_asistencia_fechas",
            )
        ]
        indexes = [
            models.Index(fields=["gimnasio", "entrada_at"], name="idx_asistencia_gimnasio"),
            models.Index(fields=["cliente", "entrada_at"], name="idx_asistencia_cliente_fecha"),
            models.Index(fields=["entrada_at"], name="idx_asistencia_fecha"),
            models.Index(fields=["cliente", "salida_at"], name="idx_asistencia_abierta"),
            models.Index(fields=["metodo_entrada"], name="idx_asistencia_metodo"),
        ]

    def clean(self):
        super().clean()
        self.identificador_evento = normalizar_texto_opcional(self.identificador_evento)
        if self.deleted_at is not None or not self.cliente_id or not self.entrada_at:
            return
        if self.salida_at is not None and self.salida_at < self.entrada_at:
            raise ValidationError(
                {"salida_at": "La salida no puede ser anterior a la entrada."}
            )
        if self.salida_at is None and type(self).objects.filter(
            cliente_id=self.cliente_id,
            salida_at__isnull=True,
            is_active=True,
            deleted_at__isnull=True,
        ).exclude(pk=self.pk).exists():
            raise ValidationError(
                {"salida_at": "El cliente ya tiene una asistencia abierta."}
            )

    def save(self, *args, **kwargs):
        self._gimnasio_antes_de_guardar()
        self.identificador_evento = normalizar_texto_opcional(self.identificador_evento)
        return super().save(*args, **kwargs)


class Entrenamiento(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="entrenamientos", db_column="cliente_id")
    entrenador = models.ForeignKey(
        Entrenador, on_delete=models.SET_NULL, related_name="entrenamientos", db_column="entrenador_id", null=True, blank=True
    )
    inicio_at = models.DateTimeField()
    fin_at = models.DateTimeField(null=True, blank=True)
    # En MySQL es una columna generada. Aquí se recalcula al guardar para ser portable a SQLite.
    duracion_minutos = models.PositiveIntegerField(null=True, blank=True, editable=False)
    observaciones = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        db_table = "entrenamientos"
        constraints = [
            models.CheckConstraint(
                condition=Q(fin_at__isnull=True) | Q(fin_at__gte=F("inicio_at")), name="chk_entrenamiento_fechas"
            )
        ]
        indexes = [
            # Nombres abreviados para respetar el límite portable de 30 caracteres de Django.
            models.Index(fields=["cliente", "inicio_at"], name="idx_entrenamiento_cli_fecha"),
            models.Index(fields=["entrenador", "inicio_at"], name="idx_entrenamiento_ent_fecha"),
        ]

    def clean(self):
        super().clean()
        if self.deleted_at is not None or not self.cliente_id or not self.entrenador_id:
            return
        if not ClienteEntrenador.entrenador_asignado(self.cliente_id, self.entrenador_id):
            raise ValidationError(
                {"entrenador": "El entrenador no está asignado activamente al cliente."}
            )

    def save(self, *args, **kwargs):
        if self.fin_at is None:
            self.duracion_minutos = None
        elif self.inicio_at is not None:
            self.duracion_minutos = int((self.fin_at - self.inicio_at).total_seconds() // 60)
        return super().save(*args, **kwargs)


class Ejercicio(AsignaGimnasioMixin, ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="ejercicios",
        db_column="gimnasio_id",
    )
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(null=True, blank=True)
    grupo_muscular = models.CharField(max_length=100, null=True, blank=True)
    musculos = models.JSONField(default=list, blank=True, validators=[validar_musculos])
    # Imagen de referencia que sube el entrenador. Es privada: la API la
    # entrega por un endpoint autenticado, igual que las fotos de comidas.
    imagen = models.ImageField(
        upload_to=ruta_imagen_ejercicio,
        storage=AlmacenamientoFotosPrivadas(),
        validators=[validar_foto_registro],
        max_length=255,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "ejercicios"
        constraints = [
            models.UniqueConstraint(fields=["gimnasio", "nombre"], name="uq_ejercicio_gimnasio_nombre")
        ]
        indexes = [
            models.Index(fields=["gimnasio", "is_active"], name="idx_ejercicio_gimnasio"),
            models.Index(fields=["grupo_muscular"], name="idx_ejercicio_grupo"),
        ]
        ordering = ["nombre"]

    def save(self, *args, **kwargs):
        self._gimnasio_antes_de_guardar()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class PlanEntrenamiento(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="planes_entrenamiento", db_column="cliente_id")
    entrenador = models.ForeignKey(
        Entrenador, on_delete=models.PROTECT, related_name="planes_entrenamiento", db_column="entrenador_id"
    )
    nombre = models.CharField(max_length=150)
    objetivo = models.CharField(max_length=255)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(null=True, blank=True)
    # Rutina por día: {"lunes": {"titulo": "Empuje", "musculos": ["pecho", ...]}}.
    rutina = models.JSONField(default=dict, blank=True)
    ejercicios = models.ManyToManyField(Ejercicio, through="PlanEntrenamientoEjercicio", related_name="planes_entrenamiento")

    class Meta:
        db_table = "planes_entrenamiento"
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=F("fecha_inicio")),
                name="chk_plan_entrenamiento_fechas",
            )
        ]
        indexes = [
            models.Index(fields=["cliente"], name="idx_pet_cliente"),
            models.Index(fields=["entrenador"], name="idx_pet_entrenador"),
            models.Index(fields=["cliente", "activo", "fecha_inicio", "fecha_fin"], name="idx_pet_vigencia"),
        ]

    DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")

    def _validar_rutina(self):
        rutina = self.rutina or {}
        if not isinstance(rutina, dict):
            raise ValidationError({"rutina": "La rutina debe ser un objeto por día."})
        limpia = {}
        for dia, datos in rutina.items():
            if dia not in self.DIAS:
                raise ValidationError({"rutina": f"Día no válido: {dia}."})
            if not isinstance(datos, dict):
                raise ValidationError({"rutina": f"Datos no válidos para {dia}."})
            titulo = str(datos.get("titulo") or "").strip()
            if len(titulo) > 60:
                raise ValidationError({"rutina": "El título de cada día admite 60 caracteres."})
            musculos = datos.get("musculos") or []
            try:
                validar_musculos(musculos)
            except ValidationError as error:
                raise ValidationError({"rutina": f"{dia}: {error.messages[0]}"}) from error
            if titulo or musculos:
                limpia[dia] = {"titulo": titulo, "musculos": musculos}
        self.rutina = limpia

    def clean(self):
        super().clean()
        self._validar_rutina()
        if self.deleted_at is not None or not self.cliente_id or not self.entrenador_id:
            return
        if not ClienteEntrenador.entrenador_asignado(self.cliente_id, self.entrenador_id):
            raise ValidationError(
                {"entrenador": "El entrenador no está asignado activamente al cliente."}
            )

    def propagar_borrado_logico(self):
        # Las filas de un plan son composición, no historial independiente:
        # se eliminan físicamente al desaparecer el plan del API.
        self.ejercicios_planificados.all().delete()


class PlanEntrenamientoEjercicio(models.Model):
    class DiaSemana(models.TextChoices):
        LUNES = "lunes", "Lunes"
        MARTES = "martes", "Martes"
        MIERCOLES = "miercoles", "Miércoles"
        JUEVES = "jueves", "Jueves"
        VIERNES = "viernes", "Viernes"
        SABADO = "sabado", "Sábado"
        DOMINGO = "domingo", "Domingo"

    id = models.BigAutoField(primary_key=True)
    plan = models.ForeignKey(
        PlanEntrenamiento, on_delete=models.CASCADE, related_name="ejercicios_planificados", db_column="plan_id"
    )
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="en_planes", db_column="ejercicio_id")
    dia_semana = models.CharField(
        max_length=10, choices=DiaSemana.choices, default=DiaSemana.LUNES
    )
    orden = models.PositiveSmallIntegerField()
    series = models.PositiveSmallIntegerField(null=True, blank=True)
    repeticiones = models.PositiveSmallIntegerField(null=True, blank=True)
    peso_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    descanso_segundos = models.PositiveIntegerField(null=True, blank=True)
    observaciones = models.CharField(max_length=1000, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "plan_entrenamiento_ejercicio"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "dia_semana", "orden"], name="uq_pte_dia_orden"
            ),
            models.CheckConstraint(condition=Q(series__isnull=True) | Q(series__gt=0), name="chk_pte_series"),
            models.CheckConstraint(
                condition=Q(repeticiones__isnull=True) | Q(repeticiones__gt=0), name="chk_pte_repeticiones"
            ),
            models.CheckConstraint(condition=Q(peso_kg__isnull=True) | Q(peso_kg__gte=0), name="chk_pte_peso"),
        ]
        indexes = [
            models.Index(fields=["ejercicio"], name="idx_pte_ejercicio"),
            models.Index(fields=["plan", "dia_semana"], name="idx_pte_plan_dia"),
        ]
        ordering = ["plan", "dia_semana", "orden", "pk"]


class PlanAlimentacion(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="planes_alimentacion", db_column="cliente_id")
    responsable = models.ForeignKey(
        Entrenador, on_delete=models.PROTECT, related_name="planes_alimentacion", db_column="responsable_id"
    )
    nombre = models.CharField(max_length=150)
    objetivo = models.CharField(max_length=255)
    calorias_objetivo = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "planes_alimentacion"
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=F("fecha_inicio")),
                name="chk_plan_alimentacion_fechas",
            ),
            models.CheckConstraint(
                condition=Q(calorias_objetivo__isnull=True) | Q(calorias_objetivo__gt=0),
                name="chk_plan_alimentacion_calorias",
            ),
        ]
        indexes = [
            models.Index(fields=["cliente"], name="idx_pla_cliente"),
            models.Index(fields=["responsable"], name="idx_pla_responsable"),
            models.Index(fields=["cliente", "activo", "fecha_inicio", "fecha_fin"], name="idx_pla_vigencia"),
        ]

    def clean(self):
        super().clean()
        if self.deleted_at is not None or not self.cliente_id or not self.responsable_id:
            return
        if not ClienteEntrenador.entrenador_asignado(self.cliente_id, self.responsable_id):
            raise ValidationError(
                {"responsable": "El responsable no está asignado activamente al cliente."}
            )

    def propagar_borrado_logico(self):
        # Las comidas pertenecen al plan; los registros del cliente se
        # conservan como historial aunque referencien una comida inactiva.
        for comida in self.comidas.filter(deleted_at__isnull=True):
            comida.soft_delete()


class Comida(ModeloAuditable):
    class Tipo(models.TextChoices):
        DESAYUNO = "desayuno", "Desayuno"
        ALMUERZO = "almuerzo", "Almuerzo"
        CENA = "cena", "Cena"
        MERIENDA = "merienda", "Merienda"
        OTRA = "otra", "Otra"

    id = models.BigAutoField(primary_key=True)
    plan_alimentacion = models.ForeignKey(
        PlanAlimentacion, on_delete=models.CASCADE, related_name="comidas", db_column="plan_alimentacion_id"
    )
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    hora_sugerida = models.TimeField(null=True, blank=True)
    descripcion = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "comidas"
        indexes = [
            models.Index(fields=["plan_alimentacion"], name="idx_comida_plan"),
            models.Index(fields=["tipo"], name="idx_comida_tipo"),
        ]


class RegistroComida(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="registros_comida", db_column="cliente_id")
    comida = models.ForeignKey(
        Comida, on_delete=models.SET_NULL, related_name="registros", db_column="comida_id", null=True, blank=True
    )
    registrado_at = models.DateTimeField(default=timezone.now)
    # Archivo privado: nunca se sirve desde MEDIA_URL/static. La API entrega
    # una ruta autenticada y el nombre original no se conserva.
    foto = models.ImageField(
        upload_to=ruta_foto_registro,
        storage=AlmacenamientoFotosPrivadas(),
        validators=[validar_foto_registro],
        max_length=255,
        null=True,
        blank=True,
    )
    verificado = models.BooleanField(default=False)
    calificacion = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    revisado_por = models.ForeignKey(
        Entrenador, on_delete=models.SET_NULL, related_name="registros_revisados", db_column="revisado_por", null=True, blank=True
    )

    class Meta:
        db_table = "registros_comida"
        constraints = [
            models.CheckConstraint(
                condition=Q(calificacion__isnull=True) | (Q(calificacion__gte=0) & Q(calificacion__lte=5)),
                name="chk_registro_calificacion",
            )
        ]
        indexes = [
            models.Index(fields=["cliente", "registrado_at"], name="idx_registro_cliente_fecha"),
            models.Index(fields=["comida"], name="idx_registro_comida"),
            models.Index(fields=["revisado_por"], name="idx_registro_revisor"),
            models.Index(fields=["cliente", "verificado"], name="idx_registro_verificado"),
        ]

    def clean(self):
        super().clean()
        if self.deleted_at is not None or not self.cliente_id:
            return

        if self.comida_id:
            plan_cliente_id = (
                Comida.objects.filter(pk=self.comida_id)
                .values_list("plan_alimentacion__cliente_id", flat=True)
                .first()
            )
            if plan_cliente_id != self.cliente_id:
                raise ValidationError(
                    {
                        "comida": (
                            "La comida debe pertenecer a un plan de alimentación "
                            "del mismo cliente."
                        )
                    }
                )

        revisor_cambio = self._state.adding
        if not revisor_cambio and self.pk:
            anterior = (
                type(self)
                .objects.filter(pk=self.pk)
                .values("cliente_id", "revisado_por_id")
                .first()
            )
            revisor_cambio = anterior is None or (
                anterior["cliente_id"],
                anterior["revisado_por_id"],
            ) != (self.cliente_id, self.revisado_por_id)

        if self.revisado_por_id and revisor_cambio:
            if not ClienteEntrenador.entrenador_asignado(
                self.cliente_id, self.revisado_por_id
            ):
                raise ValidationError(
                    {
                        "revisado_por": (
                            "El revisor debe ser un entrenador activo asignado "
                            "al cliente."
                        )
                    }
                )
            if not self.revisado_por.usuario.tiene_permiso("registros-comida:edit"):
                raise ValidationError(
                    {
                        "revisado_por": (
                            "El revisor no tiene permiso para editar registros "
                            "de comida."
                        )
                    }
                )


class Notificacion(ModeloAuditable):
    class Tipo(models.TextChoices):
        RECORDATORIO_ASISTENCIA = "recordatorio_asistencia", "Recordatorio de asistencia"
        RECORDATORIO_COMIDA = "recordatorio_comida", "Recordatorio de comida"
        ALERTA = "alerta", "Alerta"
        SISTEMA = "sistema", "Sistema"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADA = "enviada", "Enviada"
        FALLIDA = "fallida", "Fallida"
        CANCELADA = "cancelada", "Cancelada"

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="notificaciones", db_column="usuario_id")
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    titulo = models.CharField(max_length=200)
    mensaje = models.TextField()
    programada_at = models.DateTimeField(null=True, blank=True)
    enviada_at = models.DateTimeField(null=True, blank=True)
    leida_at = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)

    class Meta:
        db_table = "notificaciones"
        indexes = [
            models.Index(fields=["usuario", "estado"], name="idx_notificacion_usr_estado"),
            models.Index(fields=["usuario", "leida_at"], name="idx_notificacion_usr_leida"),
            models.Index(fields=["estado", "programada_at"], name="idx_notificacion_programada"),
        ]

    def clean(self):
        super().clean()
        if self.deleted_at is not None or not self.usuario_id:
            return
        if (
            not self.usuario.is_active
            or self.usuario.deleted_at is not None
            or not self.usuario.rol.is_active
        ):
            raise ValidationError(
                {"usuario": "El destinatario debe ser un usuario activo con rol activo."}
            )


class EventoAuditoria(models.Model):
    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
        db_column="actor_id",
    )
    accion = models.CharField(max_length=50)
    recurso = models.CharField(max_length=50)
    objeto_id = models.CharField(max_length=64, null=True, blank=True)
    detalles = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auditoria_eventos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recurso", "created_at"], name="idx_auditoria_recurso"),
            models.Index(fields=["actor", "created_at"], name="idx_auditoria_actor"),
        ]

    def __str__(self):
        return f"{self.accion} {self.recurso} {self.objeto_id or ''}".strip()


# =============================================================================
# MODELOS FINANCIEROS Y ADMINISTRATIVOS
# =============================================================================

class MetodoPago(AsignaGimnasioMixin, ModeloAuditable):
    """Catálogo de métodos de pago disponibles."""

    class Tipo(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transferencia"
        TARJETA = "tarjeta", "Tarjeta"
        OTRO = "otro", "Otro"

    id = models.BigAutoField(primary_key=True)
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="metodos_pago",
        db_column="gimnasio_id",
    )
    nombre = models.CharField(max_length=50)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.OTRO)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    requiere_referencia = models.BooleanField(default=False)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "metodos_pago"
        ordering = ["orden", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["gimnasio", "nombre"], name="uq_metodo_pago_gimnasio_nombre")
        ]
        indexes = [
            models.Index(fields=["gimnasio", "is_active"], name="idx_metodo_pago_gimnasio"),
            models.Index(fields=["is_active"], name="idx_metodo_pago_active"),
        ]

    def clean(self):
        super().clean()
        self.nombre = (self.nombre or "").strip()
        self.descripcion = normalizar_texto_opcional(self.descripcion)

    def save(self, *args, **kwargs):
        self._gimnasio_antes_de_guardar()
        self.nombre = (self.nombre or "").strip()
        self.descripcion = normalizar_texto_opcional(self.descripcion)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class CategoriaGasto(AsignaGimnasioMixin, ModeloAuditable):
    """Categorías para clasificar los gastos del gimnasio."""

    class Tipo(models.TextChoices):
        ARRIENDO = "arriendo", "Arriendo"
        SERVICIOS_PUBLICOS = "servicios_publicos", "Servicios públicos"
        NOMINA = "nomina", "Nómina"
        MANTENIMIENTO = "mantenimiento", "Mantenimiento"
        EQUIPAMIENTO = "equipamiento", "Equipamiento"
        LIMPIEZA = "limpieza", "Limpieza"
        PUBLICIDAD = "publicidad", "Publicidad"
        INTERNET = "internet", "Internet"
        OTRO = "otro", "Otro"

    id = models.BigAutoField(primary_key=True)
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="categorias_gasto",
        db_column="gimnasio_id",
    )
    nombre = models.CharField(max_length=50)
    tipo = models.CharField(max_length=30, choices=Tipo.choices, default=Tipo.OTRO)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    color = models.CharField(max_length=7, default="#6366f1", help_text="Color hex para gráficas")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "categorias_gasto"
        ordering = ["orden", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["gimnasio", "nombre"], name="uq_categoria_gasto_gimnasio_nombre")
        ]
        indexes = [
            models.Index(fields=["gimnasio", "is_active"], name="idx_categoria_gimnasio"),
            models.Index(fields=["is_active"], name="idx_categoria_gasto_active"),
        ]

    def clean(self):
        super().clean()
        self.nombre = (self.nombre or "").strip()
        self.descripcion = normalizar_texto_opcional(self.descripcion)
        if self.color and not self.color.startswith("#"):
            self.color = f"#{self.color}"

    def save(self, *args, **kwargs):
        self._gimnasio_antes_de_guardar()
        self.nombre = (self.nombre or "").strip()
        self.descripcion = normalizar_texto_opcional(self.descripcion)
        if self.color and not self.color.startswith("#"):
            self.color = f"#{self.color}"
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Pago(AsignaGimnasioMixin, ModeloAuditable):
    """Registro de pagos/ingresos recibidos de los clientes."""

    class Estado(models.TextChoices):
        COMPLETADO = "completado", "Completado"
        PENDIENTE = "pendiente", "Pendiente"
        FALLIDO = "fallido", "Fallido"
        REEMBOLSADO = "reembolsado", "Reembolsado"

    class Concepto(models.TextChoices):
        MEMBRESIA = "membresia", "Membresía"
        RENOVACION = "renovacion", "Renovación"
        MATRICULA = "matricula", "Matrícula"
        ENTRENAMIENTO_PERSONAL = "entrenamiento_personal", "Entrenamiento personal"
        PLAN_ALIMENTACION = "plan_alimentacion", "Plan de alimentación"
        PRODUCTO = "producto", "Producto"
        OTRO = "otro", "Otro"

    id = models.BigAutoField(primary_key=True)
    ORIGENES_GIMNASIO = ("cliente.usuario",)
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="pagos",
        db_column="gimnasio_id",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="pagos",
        db_column="cliente_id",
    )
    concepto = models.CharField(max_length=30, choices=Concepto.choices)
    concepto_detalle = models.CharField(max_length=255, null=True, blank=True)
    membresia = models.ForeignKey(
        "Membresia",
        on_delete=models.SET_NULL,
        related_name="pagos",
        db_column="membresia_id",
        null=True,
        blank=True,
    )
    fecha_pago = models.DateTimeField(default=timezone.now)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.PROTECT,
        related_name="pagos",
        db_column="metodo_pago_id",
    )
    referencia = models.CharField(max_length=100, null=True, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.COMPLETADO,
    )
    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="pagos_registrados",
        db_column="registrado_por_id",
    )
    notas = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "pagos"
        indexes = [
            models.Index(fields=["gimnasio", "fecha_pago"], name="idx_pago_gimnasio_fecha"),
            models.Index(fields=["cliente", "fecha_pago"], name="idx_pago_cliente_fecha"),
            models.Index(fields=["fecha_pago"], name="idx_pago_fecha"),
            models.Index(fields=["estado"], name="idx_pago_estado"),
            models.Index(fields=["concepto"], name="idx_pago_concepto"),
            models.Index(fields=["metodo_pago"], name="idx_pago_metodo"),
            models.Index(fields=["registrado_por", "fecha_pago"], name="idx_pago_registrador_fecha"),
        ]
        ordering = ["-fecha_pago", "-pk"]

    def clean(self):
        super().clean()
        if self.deleted_at is not None or not self.cliente_id or self.valor is None:
            return
        if self.valor <= 0:
            raise ValidationError({"valor": "El valor del pago debe ser mayor a cero."})
        if self.estado == self.Estado.COMPLETADO and self.fecha_pago > timezone.now():
            raise ValidationError({"fecha_pago": "No se puede completar un pago con fecha futura."})
        if self.membresia_id and self.membresia.cliente_id != self.cliente_id:
            raise ValidationError(
                {"membresia": "La membresía no pertenece al cliente del pago."}
            )
        self.concepto_detalle = normalizar_texto_opcional(self.concepto_detalle)
        self.referencia = normalizar_texto_opcional(self.referencia)
        self.notas = normalizar_texto_opcional(self.notas)

    def save(self, *args, **kwargs):
        self._gimnasio_antes_de_guardar()
        self.concepto_detalle = normalizar_texto_opcional(self.concepto_detalle)
        self.referencia = normalizar_texto_opcional(self.referencia)
        self.notas = normalizar_texto_opcional(self.notas)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cliente} - ${self.valor:,.0f} - {self.get_concepto_display()}"


class Gasto(AsignaGimnasioMixin, ModeloAuditable):
    """Registro de gastos del gimnasio."""

    class Estado(models.TextChoices):
        REGISTRADO = "registrado", "Registrado"
        APROBADO = "aprobado", "Aprobado"
        PAGADO = "pagado", "Pagado"
        CANCELADO = "cancelado", "Cancelado"

    id = models.BigAutoField(primary_key=True)
    ORIGENES_GIMNASIO = ("categoria", "registrado_por")
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="gastos",
        db_column="gimnasio_id",
    )
    descripcion = models.CharField(max_length=255)
    categoria = models.ForeignKey(
        CategoriaGasto,
        on_delete=models.PROTECT,
        related_name="gastos",
        db_column="categoria_id",
    )
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateField()
    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.PROTECT,
        related_name="gastos",
        db_column="metodo_pago_id",
    )
    referencia = models.CharField(max_length=100, null=True, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.REGISTRADO,
    )
    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="gastos_registrados",
        db_column="registrado_por_id",
    )
    aprobado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        related_name="gastos_aprobados",
        db_column="aprobado_por_id",
        null=True,
        blank=True,
    )
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "gastos"
        indexes = [
            models.Index(fields=["gimnasio", "fecha"], name="idx_gasto_gimnasio_fecha"),
            models.Index(fields=["categoria", "fecha"], name="idx_gasto_cat_fecha"),
            models.Index(fields=["fecha"], name="idx_gasto_fecha"),
            models.Index(fields=["estado"], name="idx_gasto_estado"),
            models.Index(fields=["registrado_por", "fecha"], name="idx_gasto_registrador_fecha"),
        ]
        ordering = ["-fecha", "-pk"]

    def clean(self):
        super().clean()
        if self.deleted_at is not None or self.valor is None:
            return
        if self.valor <= 0:
            raise ValidationError({"valor": "El valor del gasto debe ser mayor a cero."})
        self.descripcion = (self.descripcion or "").strip()
        self.referencia = normalizar_texto_opcional(self.referencia)
        self.observaciones = normalizar_texto_opcional(self.observaciones)

    def save(self, *args, **kwargs):
        self._gimnasio_antes_de_guardar()
        self.descripcion = (self.descripcion or "").strip()
        self.referencia = normalizar_texto_opcional(self.referencia)
        self.observaciones = normalizar_texto_opcional(self.observaciones)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.categoria.nombre} - ${self.valor:,.0f} - {self.fecha}"


class Membresia(AsignaGimnasioMixin, ModeloAuditable):
    """Membresías de los clientes con vigencia y estado."""

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        VENCIDA = "vencida", "Vencida"
        POR_VENCER = "por_vencer", "Por vencer"
        CANCELADA = "cancelada", "Cancelada"
        CONGELADA = "congelada", "Congelada"

    class Tipo(models.TextChoices):
        MENSUAL = "mensual", "Mensual"
        TRIMESTRAL = "trimestral", "Trimestral"
        SEMESTRAL = "semestral", "Semestral"
        ANUAL = "anual", "Anual"
        VISITA = "visita", "Visita única"
        PERSONALIZADA = "personalizada", "Personalizada"

    id = models.BigAutoField(primary_key=True)
    ORIGENES_GIMNASIO = ("cliente.usuario",)
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="membresias",
        db_column="gimnasio_id",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="membresias",
        db_column="cliente_id",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.MENSUAL)
    nombre = models.CharField(max_length=100, help_text="Ej: Membresía Mensual Estándar")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    fecha_ultima_renovacion = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVA,
    )
    dias_congelados = models.PositiveIntegerField(default=0)
    renovacion_automatica = models.BooleanField(default=False)
    entrenador_asignado = models.ForeignKey(
        Entrenador,
        on_delete=models.SET_NULL,
        related_name="membresias_asignadas",
        db_column="entrenador_asignado_id",
        null=True,
        blank=True,
    )
    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="membresias_registradas",
        db_column="registrado_por_id",
    )
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "membresias"
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__gte=F("fecha_inicio")),
                name="chk_membresia_fechas",
            ),
            models.CheckConstraint(condition=Q(precio__gte=0), name="chk_membresia_precio"),
        ]
        indexes = [
            models.Index(fields=["gimnasio", "estado"], name="idx_membresia_gimnasio"),
            models.Index(fields=["cliente", "estado"], name="idx_membresia_cliente_estado"),
            models.Index(fields=["fecha_fin", "estado"], name="idx_membresia_vencimiento"),
            models.Index(fields=["estado"], name="idx_membresia_estado"),
            models.Index(fields=["tipo"], name="idx_membresia_tipo"),
        ]
        ordering = ["-fecha_inicio", "-pk"]

    def clean(self):
        super().clean()
        if self.deleted_at is not None or not self.cliente_id or self.precio is None:
            return
        if self.precio < 0:
            raise ValidationError({"precio": "El precio no puede ser negativo."})
        if self.fecha_fin and self.fecha_inicio and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({"fecha_fin": "La fecha fin no puede ser anterior a la fecha inicio."})
        self.nombre = (self.nombre or "").strip()
        self.observaciones = normalizar_texto_opcional(self.observaciones)

    def save(self, *args, **kwargs):
        self._gimnasio_antes_de_guardar()
        self.nombre = (self.nombre or "").strip()
        self.observaciones = normalizar_texto_opcional(self.observaciones)
        # Actualizar estado automáticamente basado en fechas
        if self.pk is None or self._state.adding:
            self.actualizar_estado_por_fecha()
        return super().save(*args, **kwargs)

    def actualizar_estado_por_fecha(self):
        """Actualiza el estado basado en la fecha actual."""
        hoy = timezone.localdate()
        if self.estado in (self.Estado.CANCELADA, self.Estado.CONGELADA):
            return
        if self.fecha_fin < hoy:
            self.estado = self.Estado.VENCIDA
        elif self.fecha_fin <= hoy + timedelta(days=7):
            self.estado = self.Estado.POR_VENCER
        else:
            self.estado = self.Estado.ACTIVA

    @classmethod
    def sincronizar_estados(cls, hoy=None, gimnasio_id=None):
        """Pone al día el estado de todas las membresías según ``fecha_fin``.

        ``save()`` solo calcula el estado al crear, así que sin esta pasada una
        membresía activa nunca llegaría a "por vencer" ni a "vencida". No toca
        las canceladas. Una congelada conserva su estado mientras siga dentro
        de su vigencia (que ``congelar`` ya extendió) y vence al pasar su
        fecha de fin. Devuelve cuántas filas cambió.
        """
        hoy = hoy or timezone.localdate()
        limite = hoy + timedelta(days=7)
        ahora = timezone.now()
        no_canceladas = cls.objects.filter(deleted_at__isnull=True).exclude(
            estado=cls.Estado.CANCELADA
        )
        if gimnasio_id:
            no_canceladas = no_canceladas.filter(gimnasio_id=gimnasio_id)
        vigentes = no_canceladas.exclude(estado=cls.Estado.CONGELADA)
        return {
            "vencidas": no_canceladas.filter(fecha_fin__lt=hoy)
            .exclude(estado=cls.Estado.VENCIDA)
            .update(estado=cls.Estado.VENCIDA, updated_at=ahora),
            "por_vencer": vigentes.filter(fecha_fin__gte=hoy, fecha_fin__lte=limite)
            .exclude(estado=cls.Estado.POR_VENCER)
            .update(estado=cls.Estado.POR_VENCER, updated_at=ahora),
            "activas": vigentes.filter(fecha_fin__gt=limite)
            .exclude(estado=cls.Estado.ACTIVA)
            .update(estado=cls.Estado.ACTIVA, updated_at=ahora),
        }

    def dias_para_vencer(self):
        """Retorna días restantes para vencer (negativo si ya venció)."""
        hoy = timezone.localdate()
        return (self.fecha_fin - hoy).days

    def __str__(self):
        return f"{self.cliente} - {self.nombre} ({self.get_estado_display()})"


class AlertaQuerySet(models.QuerySet):
    def por_prioridad(self):
        """Ordena de crítica a baja.

        ``prioridad`` es texto: ordenar por la columna la deja en orden
        alfabético (media, crítica, baja, alta).
        """
        return self.annotate(
            prioridad_orden=Case(
                When(prioridad="critica", then=Value(4)),
                When(prioridad="alta", then=Value(3)),
                When(prioridad="media", then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("-prioridad_orden", "-created_at", "-pk")


class Alerta(AsignaGimnasioMixin, ModeloAuditable):
    """Centro de alertas administrativas."""

    class Tipo(models.TextChoices):
        MEMBRESIA_POR_VENCER = "membresia_por_vencer", "Membresía por vencer"
        MEMBRESIA_VENCIDA = "membresia_vencida", "Membresía vencida"
        CLIENTE_INACTIVO = "cliente_inactivo", "Cliente inactivo"
        INGRESOS_BAJOS = "ingresos_bajos", "Ingresos bajos"
        GASTOS_ALTOS = "gastos_altos", "Gastos altos"
        NUEVO_GASTO = "nuevo_gasto", "Nuevo gasto registrado"
        PAGOS_PENDIENTES = "pagos_pendientes", "Pagos pendientes"
        ASISTENCIA_BAJA = "asistencia_baja", "Asistencia baja"

    class Prioridad(models.TextChoices):
        BAJA = "baja", "Baja"
        MEDIA = "media", "Media"
        ALTA = "alta", "Alta"
        CRITICA = "critica", "Crítica"

    id = models.BigAutoField(primary_key=True)
    ORIGENES_GIMNASIO = ("cliente.usuario", "membresia", "pago", "gasto")
    gimnasio = models.ForeignKey(
        Gimnasio,
        on_delete=models.PROTECT,
        related_name="alertas",
        db_column="gimnasio_id",
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    prioridad = models.CharField(max_length=10, choices=Prioridad.choices, default=Prioridad.MEDIA)
    titulo = models.CharField(max_length=200)
    mensaje = models.TextField()
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        related_name="alertas",
        db_column="cliente_id",
        null=True,
        blank=True,
    )
    membresia = models.ForeignKey(
        Membresia,
        on_delete=models.SET_NULL,
        related_name="alertas",
        db_column="membresia_id",
        null=True,
        blank=True,
    )
    pago = models.ForeignKey(
        Pago,
        on_delete=models.SET_NULL,
        related_name="alertas",
        db_column="pago_id",
        null=True,
        blank=True,
    )
    gasto = models.ForeignKey(
        Gasto,
        on_delete=models.SET_NULL,
        related_name="alertas",
        db_column="gasto_id",
        null=True,
        blank=True,
    )
    leida = models.BooleanField(default=False)
    leida_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        related_name="alertas_leidas",
        db_column="leida_por_id",
        null=True,
        blank=True,
    )
    leida_at = models.DateTimeField(null=True, blank=True)
    datos_adicionales = models.JSONField(default=dict, blank=True)

    objects = AlertaQuerySet.as_manager()

    class Meta:
        db_table = "alertas"
        indexes = [
            models.Index(fields=["gimnasio", "leida"], name="idx_alerta_gimnasio"),
            models.Index(fields=["tipo", "leida"], name="idx_alerta_tipo_leida"),
            models.Index(fields=["prioridad", "created_at"], name="idx_alerta_prioridad_fecha"),
            models.Index(fields=["cliente", "leida"], name="idx_alerta_cliente_leida"),
            models.Index(fields=["created_at"], name="idx_alerta_fecha"),
        ]
        ordering = ["-created_at", "-pk"]

    def clean(self):
        super().clean()
        self.titulo = (self.titulo or "").strip()
        self.mensaje = (self.mensaje or "").strip()

    def save(self, *args, **kwargs):
        self._gimnasio_antes_de_guardar()
        self.titulo = (self.titulo or "").strip()
        self.mensaje = (self.mensaje or "").strip()
        return super().save(*args, **kwargs)

    @classmethod
    def generar_de_membresias(cls, gimnasio_id=None):
        """Crea las alertas de membresías por vencer y vencidas que falten.

        Es idempotente: cada membresía recibe una sola alerta por tipo y por
        fecha de fin, de modo que una renovación vuelve a avisar más adelante.
        Devuelve cuántas alertas creó.
        """
        tipo_por_estado = {
            Membresia.Estado.POR_VENCER: cls.Tipo.MEMBRESIA_POR_VENCER,
            Membresia.Estado.VENCIDA: cls.Tipo.MEMBRESIA_VENCIDA,
        }
        del_gimnasio = {"gimnasio_id": gimnasio_id} if gimnasio_id else {}
        existentes = {
            (membresia_id, tipo, (datos or {}).get("fecha_fin"))
            for membresia_id, tipo, datos in cls.objects.filter(
                tipo__in=tipo_por_estado.values(), membresia__isnull=False, **del_gimnasio
            ).values_list("membresia_id", "tipo", "datos_adicionales")
        }
        membresias = Membresia.objects.filter(
            estado__in=tipo_por_estado.keys(),
            deleted_at__isnull=True,
            cliente__deleted_at__isnull=True,
            cliente__is_active=True,
            **del_gimnasio,
        ).select_related("cliente__usuario")
        nuevas = []
        for membresia in membresias:
            tipo = tipo_por_estado[membresia.estado]
            fecha_fin = membresia.fecha_fin.isoformat()
            if (membresia.pk, tipo, fecha_fin) in existentes:
                continue
            nombre = membresia.cliente.usuario.nombre
            vencida = tipo == cls.Tipo.MEMBRESIA_VENCIDA
            nuevas.append(
                cls(
                    tipo=tipo,
                    prioridad=cls.Prioridad.ALTA if vencida else cls.Prioridad.MEDIA,
                    titulo=(
                        f"Membresía vencida: {nombre}"
                        if vencida
                        else f"Membresía por vencer: {nombre}"
                    )[:200],
                    mensaje=(
                        f"La membresía \"{membresia.nombre}\" de {nombre} "
                        + ("venció" if vencida else "vence")
                        + f" el {membresia.fecha_fin:%d/%m/%Y}."
                    ),
                    gimnasio_id=membresia.gimnasio_id,
                    cliente=membresia.cliente,
                    membresia=membresia,
                    datos_adicionales={"fecha_fin": fecha_fin},
                )
            )
        cls.objects.bulk_create(nuevas)
        return len(nuevas)

    def marcar_como_leida(self, usuario):
        """Marca la alerta como leída por un usuario."""
        if not self.leida:
            self.leida = True
            self.leida_por = usuario if isinstance(usuario, Usuario) else None
            self.leida_at = timezone.now()
            self.save(update_fields=["leida", "leida_por", "leida_at", "updated_at"])

    def __str__(self):
        return f"[{self.get_prioridad_display()}] {self.titulo}"
