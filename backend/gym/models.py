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
from django.db.models import F, Q
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
        for rol_id in self.roles_asignados.values_list("rol_id", flat=True):
            RolRecurso.objects.get_or_create(rol_id=rol_id, recurso=recurso)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rol_permiso"
        constraints = [
            models.UniqueConstraint(fields=["rol", "permiso"], name="uq_rol_permiso")
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
        RolRecurso.objects.get_or_create(rol=self.rol, recurso=recurso)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rol_has_recurso"
        constraints = [
            models.UniqueConstraint(fields=["rol", "recurso"], name="uq_rol_recurso")
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
            models.Index(fields=["rol", "is_active"], name="idx_usuarios_rol_activo"),
            models.Index(fields=["deleted_at"], name="idx_usuarios_deleted_at"),
            models.Index(fields=["nombre"], name="idx_usuarios_nombre"),
        ]
        ordering = ["nombre", "id"]

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
                roles_asignados__rol__in=self.roles_efectivos(),
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
                roles_asignados__rol__in=self.roles_efectivos(),
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


class Asistencia(ModeloAuditable):
    class MetodoEntrada(models.TextChoices):
        QR = "qr", "Código QR"
        FACIAL = "facial", "Reconocimiento facial"
        MANUAL = "manual", "Manual"

    id = models.BigAutoField(primary_key=True)
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


class Ejercicio(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=150, unique=True)
    descripcion = models.TextField(null=True, blank=True)
    grupo_muscular = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "ejercicios"
        indexes = [models.Index(fields=["grupo_muscular"], name="idx_ejercicio_grupo")]
        ordering = ["nombre"]

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

    def clean(self):
        super().clean()
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
