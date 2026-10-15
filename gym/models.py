"""Modelo relacional de Gym Control Pro.

El diseño corresponde al esquema ``gym_control_pro.sql``.  Se conserva el
borrado lógico de las entidades operativas para mantener el historial.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ModeloAuditable(models.Model):
    """Campos comunes a las tablas que el SQL marca como borrables lógicamente."""

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        """Desactiva el registro sin perder sus referencias históricas."""
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at", "updated_at"])


class Rol(models.Model):
    class Nombre(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        ENTRENADOR = "entrenador", "Entrenador"
        TERAPEUTA = "terapeuta", "Terapeuta"
        RECEPCIONISTA = "recepcionista", "Recepcionista"
        ADMINISTRADOR = "administrador", "Administrador"

    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=50, unique=True, choices=Nombre.choices)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roles"
        indexes = [models.Index(fields=["is_active"], name="idx_roles_active")]
        ordering = ["nombre"]

    def __str__(self):
        return self.get_nombre_display()


class Usuario(ModeloAuditable):
    id = models.BigAutoField(primary_key=True)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="usuarios", db_column="rol_id")
    nombre = models.CharField(max_length=150)
    username = models.CharField(max_length=100, null=True, blank=True, unique=True)
    correo = models.EmailField(max_length=191, unique=True)
    # Nunca se expone a través del serializer: usa set_password/check_password.
    contrasena_hash = models.CharField(max_length=255)
    telefono = models.CharField(max_length=30, null=True, blank=True)

    class Meta:
        db_table = "usuarios"
        indexes = [
            models.Index(fields=["rol", "is_active"], name="idx_usuarios_rol_activo"),
            models.Index(fields=["deleted_at"], name="idx_usuarios_deleted_at"),
            models.Index(fields=["nombre"], name="idx_usuarios_nombre"),
        ]
        ordering = ["nombre", "id"]

    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password

        self.contrasena_hash = make_password(raw_password)

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password

        return check_password(raw_password, self.contrasena_hash)

    @property
    def is_authenticated(self):
        """Compatibilidad con ``IsAuthenticated`` de Django REST Framework."""
        return True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return f"{self.nombre} ({self.correo})"


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
        token = secrets.token_urlsafe(32)
        sesion = cls.objects.create(
            usuario=usuario,
            token_hash=cls.hash_token(token),
            expira_at=timezone.now() + timedelta(hours=settings.AUTH_TOKEN_TTL_HOURS),
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

    def save(self, *args, **kwargs):
        # Hace cumplir el equivalente de los triggers incluso fuera de la API.
        self.full_clean()
        return super().save(*args, **kwargs)


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
            models.UniqueConstraint(fields=["tipo_documento", "numero_documento"], name="uq_cliente_documento"),
            models.CheckConstraint(condition=Q(peso_kg__isnull=True) | Q(peso_kg__gt=0), name="chk_cliente_peso"),
            models.CheckConstraint(
                condition=Q(estatura_cm__isnull=True) | Q(estatura_cm__gt=0), name="chk_cliente_estatura"
            ),
        ]
        indexes = [
            models.Index(fields=["objetivo"], name="idx_cliente_objetivo"),
            models.Index(fields=["is_active"], name="idx_cliente_active"),
        ]

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
        indexes = [models.Index(fields=["especialidad"], name="idx_terapeuta_especialidad")]

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


class PlanEntrenamientoEjercicio(models.Model):
    id = models.BigAutoField(primary_key=True)
    plan = models.ForeignKey(
        PlanEntrenamiento, on_delete=models.CASCADE, related_name="ejercicios_planificados", db_column="plan_id"
    )
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="en_planes", db_column="ejercicio_id")
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
            models.UniqueConstraint(fields=["plan", "orden"], name="uq_pte_orden"),
            models.CheckConstraint(condition=Q(series__isnull=True) | Q(series__gt=0), name="chk_pte_series"),
            models.CheckConstraint(
                condition=Q(repeticiones__isnull=True) | Q(repeticiones__gt=0), name="chk_pte_repeticiones"
            ),
            models.CheckConstraint(condition=Q(peso_kg__isnull=True) | Q(peso_kg__gte=0), name="chk_pte_peso"),
        ]
        indexes = [models.Index(fields=["ejercicio"], name="idx_pte_ejercicio")]
        ordering = ["plan", "orden"]


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
    # El SQL permite una URL o un identificador protegido de almacenamiento.
    foto_url = models.CharField(max_length=2048)
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
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)

    class Meta:
        db_table = "notificaciones"
        indexes = [
            models.Index(fields=["usuario", "estado"], name="idx_notificacion_usr_estado"),
            models.Index(fields=["estado", "programada_at"], name="idx_notificacion_programada"),
        ]
