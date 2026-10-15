"""Carga datos de demostración completos para Gym Control Pro."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from gym.models import (
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


class Command(BaseCommand):
    help = "Crea usuarios y datos de demostración completos en todas las tablas operativas."

    prefijo_correo = "demo.usuario"
    contrasena_predeterminada = "DemoGym2026!"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cantidad",
            type=int,
            default=100,
            help="Cantidad total de usuarios demo a crear. Debe ser al menos 5. Por defecto: 100.",
        )
        parser.add_argument(
            "--contrasena",
            default=self.contrasena_predeterminada,
            help="Contraseña común para las cuentas demo.",
        )
        parser.add_argument(
            "--por-rol",
            type=int,
            help="Cantidad objetivo de cuentas demo por cada rol. Tiene prioridad sobre --cantidad.",
        )

    def handle(self, *args, **options):
        cantidad = options["cantidad"]
        cantidad_por_rol = options["por_rol"]
        if cantidad_por_rol is None and cantidad < 5:
            raise CommandError("La cantidad debe ser al menos 5 para incluir los cinco roles.")
        if cantidad_por_rol is not None and cantidad_por_rol < 1:
            raise CommandError("La cantidad por rol debe ser al menos 1.")
        if len(options["contrasena"]) < 8:
            raise CommandError("La contraseña debe tener al menos 8 caracteres.")

        nombres_rol = [nombre for nombre, _ in Rol.Nombre.choices]
        roles = {rol.nombre: rol for rol in Rol.objects.filter(nombre__in=nombres_rol, is_active=True)}
        faltantes = set(nombres_rol) - set(roles)
        if faltantes:
            raise CommandError(f"Faltan roles iniciales: {', '.join(sorted(faltantes))}. Ejecute las migraciones.")

        if cantidad_por_rol is not None:
            objetivos = {nombre: cantidad_por_rol for nombre in nombres_rol}
        else:
            base, restante = divmod(cantidad, len(nombres_rol))
            objetivos = {nombre: base + (posicion < restante) for posicion, nombre in enumerate(nombres_rol)}

        usuarios_demo = list(
            Usuario.objects.filter(correo__startswith=self.prefijo_correo).select_related("rol")
        )
        actuales = {nombre: 0 for nombre in nombres_rol}
        for usuario in usuarios_demo:
            if usuario.rol.nombre in actuales:
                actuales[usuario.rol.nombre] += 1

        faltan_por_rol = {nombre: max(0, objetivos[nombre] - actuales[nombre]) for nombre in nombres_rol}
        if not any(faltan_por_rol.values()):
            self.stdout.write(self.style.WARNING("La base ya alcanza la cantidad demo solicitada por rol."))
            return

        hash_contrasena = make_password(options["contrasena"])
        hoy = date.today()
        ahora = timezone.now()
        por_rol = {nombre: [] for nombre in nombres_rol}
        correos_demo = {usuario.correo for usuario in usuarios_demo}
        siguiente_indice = 1

        with transaction.atomic():
            for nombre_rol in nombres_rol:
                for _ in range(faltan_por_rol[nombre_rol]):
                    while f"{self.prefijo_correo}{siguiente_indice:03d}@gymcontrol.local" in correos_demo:
                        siguiente_indice += 1
                    usuario = Usuario.objects.create(
                        rol=roles[nombre_rol],
                        nombre=f"Usuario Demo {siguiente_indice:03d}",
                        username=f"demo_usuario_{siguiente_indice:03d}",
                        correo=f"{self.prefijo_correo}{siguiente_indice:03d}@gymcontrol.local",
                        contrasena_hash=hash_contrasena,
                        telefono=f"+57 300 555 {siguiente_indice:04d}",
                        is_active=True,
                    )
                    correos_demo.add(usuario.correo)
                    por_rol[nombre_rol].append(usuario)
                    siguiente_indice += 1

            clientes = por_rol[Rol.Nombre.CLIENTE]
            entrenadores = por_rol[Rol.Nombre.ENTRENADOR]

            for usuario in clientes:
                indice = usuario.pk
                Cliente.objects.create(
                    usuario=usuario,
                    tipo_documento="CC",
                    numero_documento=f"10{indice:08d}",
                    fecha_nacimiento=hoy - timedelta(days=365 * (20 + (indice % 25))),
                    objetivo="Mejorar condición física y hábitos saludables.",
                    peso_kg=Decimal("60.00") + Decimal(indice),
                    estatura_cm=Decimal("160.00") + Decimal(indice),
                )

            for usuario in entrenadores:
                indice = usuario.pk
                Entrenador.objects.create(
                    usuario=usuario,
                    especialidad=("Fuerza y acondicionamiento", "Entrenamiento funcional", "Resistencia cardiovascular")[
                        (indice - 1) % 3
                    ],
                    certificacion=f"Certificación internacional de entrenamiento {indice:03d}",
                    fecha_ingreso=hoy - timedelta(days=365 * (1 + indice)),
                    biografia=f"Entrenador demo {indice:03d} con experiencia en programas personalizados.",
                )

            for usuario in por_rol[Rol.Nombre.TERAPEUTA]:
                indice = usuario.pk
                Terapeuta.objects.create(
                    usuario=usuario,
                    especialidad=("Fisioterapia deportiva", "Rehabilitación funcional", "Movilidad articular")[
                        (indice - 1) % 3
                    ],
                    licencia_profesional=f"LIC-DEMO-{indice:04d}",
                    fecha_ingreso=hoy - timedelta(days=365 * (1 + indice)),
                )

            for usuario in por_rol[Rol.Nombre.RECEPCIONISTA]:
                indice = usuario.pk
                Recepcionista.objects.create(
                    usuario=usuario,
                    fecha_ingreso=hoy - timedelta(days=180 + indice),
                    turno_preferido=("Mañana", "Tarde", "Noche")[(indice - 1) % 3],
                )

            for usuario in por_rol[Rol.Nombre.ADMINISTRADOR]:
                indice = usuario.pk
                Administrador.objects.create(
                    usuario=usuario,
                    cargo=f"Administrador de operaciones {indice:03d}",
                    fecha_ingreso=hoy - timedelta(days=365 * (2 + indice)),
                    nivel_permisos=Administrador.NivelPermisos.TOTAL,
                )

            ejercicios = []
            grupos_musculares = ("Pecho", "Espalda", "Piernas", "Core", "Hombros")
            ejercicio_inicial = Ejercicio.objects.filter(nombre__startswith="Ejercicio demo ").count()
            for indice in range(1, max(2, len(clientes)) + 1):
                numero_ejercicio = ejercicio_inicial + indice
                ejercicios.append(
                    Ejercicio.objects.create(
                        nombre=f"Ejercicio demo {numero_ejercicio:03d}",
                        descripcion=f"Descripción completa del ejercicio demo {numero_ejercicio:03d}.",
                        grupo_muscular=grupos_musculares[(indice - 1) % len(grupos_musculares)],
                    )
                )

            entrenadores_demo = list(
                Entrenador.objects.filter(usuario__correo__startswith=self.prefijo_correo).order_by("pk")
            )
            for indice, cliente_usuario in enumerate(clientes, start=1):
                cliente = Cliente.objects.get(pk=cliente_usuario.pk)
                entrenador = entrenadores_demo[(indice - 1) % len(entrenadores_demo)]
                inicio = ahora - timedelta(days=indice, hours=1)
                fin = inicio + timedelta(minutes=60)

                ClienteEntrenador.objects.create(
                    cliente=cliente,
                    entrenador=entrenador,
                    fecha_inicio=hoy - timedelta(days=30 + indice),
                    fecha_fin=hoy + timedelta(days=180),
                    activo=True,
                )
                Asistencia.objects.create(
                    cliente=cliente,
                    entrada_at=inicio,
                    salida_at=fin,
                    metodo_entrada=(Asistencia.MetodoEntrada.QR, Asistencia.MetodoEntrada.FACIAL, Asistencia.MetodoEntrada.MANUAL)[
                        (indice - 1) % 3
                    ],
                    identificador_evento=f"demo-asistencia-{cliente.pk}",
                )
                Entrenamiento.objects.create(
                    cliente=cliente,
                    entrenador=entrenador,
                    inicio_at=inicio,
                    fin_at=fin,
                    observaciones=f"Entrenamiento demo completo para el cliente {indice:03d}.",
                )

                plan_entrenamiento = PlanEntrenamiento.objects.create(
                    cliente=cliente,
                    entrenador=entrenador,
                    nombre=f"Plan de entrenamiento demo {indice:03d}",
                    objetivo="Mejorar fuerza, movilidad y resistencia.",
                    fecha_inicio=hoy - timedelta(days=7),
                    fecha_fin=hoy + timedelta(days=83),
                    activo=True,
                    observaciones="Plan creado automáticamente para datos de demostración.",
                )
                for orden in (1, 2):
                    PlanEntrenamientoEjercicio.objects.create(
                        plan=plan_entrenamiento,
                        ejercicio=ejercicios[(indice + orden - 2) % len(ejercicios)],
                        orden=orden,
                        series=3 + orden,
                        repeticiones=10 + orden,
                        peso_kg=Decimal("15.00") + Decimal(indice),
                        descanso_segundos=60 + (orden * 15),
                        observaciones=f"Instrucciones completas del ejercicio {orden}.",
                    )

                plan_alimentacion = PlanAlimentacion.objects.create(
                    cliente=cliente,
                    responsable=entrenador,
                    nombre=f"Plan de alimentación demo {indice:03d}",
                    objetivo="Mantener una alimentación equilibrada.",
                    calorias_objetivo=Decimal("2200.00") + Decimal(indice * 10),
                    fecha_inicio=hoy - timedelta(days=7),
                    fecha_fin=hoy + timedelta(days=83),
                    activo=True,
                    observaciones="Plan nutricional completo para demostración.",
                )
                comidas = []
                for tipo, nombre, hora in (
                    (Comida.Tipo.DESAYUNO, "Desayuno balanceado", time(7, 30)),
                    (Comida.Tipo.ALMUERZO, "Almuerzo proteico", time(12, 30)),
                    (Comida.Tipo.CENA, "Cena ligera", time(19, 0)),
                    (Comida.Tipo.MERIENDA, "Merienda saludable", time(16, 0)),
                ):
                    comidas.append(
                        Comida.objects.create(
                            plan_alimentacion=plan_alimentacion,
                            nombre=f"{nombre} {indice:03d}",
                            tipo=tipo,
                            hora_sugerida=hora,
                            descripcion=f"Descripción e indicaciones completas para {nombre.lower()}.",
                        )
                    )
                RegistroComida.objects.create(
                    cliente=cliente,
                    comida=comidas[0],
                    registrado_at=ahora - timedelta(hours=indice),
                    foto_url=f"https://example.com/demo/comida-{cliente.pk}.jpg",
                    verificado=True,
                    calificacion=Decimal("4.50"),
                    observaciones="Registro de comida validado para demostración.",
                    revisado_por=entrenador,
                )

            for indice, usuarios in enumerate(por_rol.values(), start=1):
                for usuario in usuarios:
                    Notificacion.objects.create(
                        usuario=usuario,
                        tipo=Notificacion.Tipo.SISTEMA,
                        titulo="Bienvenido a Gym Control Pro",
                        mensaje=f"Notificación demo generada para {usuario.nombre}.",
                        programada_at=ahora - timedelta(minutes=indice),
                        enviada_at=ahora,
                        estado=Notificacion.Estado.ENVIADA,
                    )

        creados = sum(len(usuarios) for usuarios in por_rol.values())
        resumen_roles = ", ".join(
            f"{nombre}: {actuales[nombre] + len(por_rol[nombre])}" for nombre in nombres_rol
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Se crearon {creados} usuarios demo, sus perfiles y datos relacionados. "
                f"Totales demo por rol: {resumen_roles}. "
                f"Contraseña de las cuentas demo: {options['contrasena']}"
            )
        )
