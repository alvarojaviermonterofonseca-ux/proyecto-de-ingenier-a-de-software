"""Centro de alertas: genera las alertas administrativas de cada gimnasio.

Todas las reglas son idempotentes: cada alerta lleva en ``datos_adicionales``
una clave (la fecha de fin de la membresía, el mes evaluado, la última
asistencia...) y no se repite mientras esa clave no cambie. Así se pueden
ejecutar tantas veces como se quiera (al abrir el dashboard, al listar alertas
o desde el comando diario ``generar_alertas``).

Los umbrales se configuran por gimnasio (``Gimnasio.dias_inactividad_alerta``,
``limite_gastos_mensual`` y ``porcentaje_caida_ingresos``).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone

from .models import Alerta, Cliente, Gasto, Gimnasio, Membresia, Pago


def _inicio_del_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


def _inicio_mes(fecha):
    return fecha.replace(day=1)


def _mes_anterior(primer_dia):
    return (primer_dia - timedelta(days=1)).replace(day=1)


def _moneda(valor):
    """Formato colombiano: $ 150.000."""
    entero = int(Decimal(valor).quantize(Decimal("1")))
    return "$ " + f"{entero:,}".replace(",", ".")


def _claves_existentes(gimnasio, tipo, campo):
    return {
        (datos or {}).get(campo)
        for datos in Alerta.objects.filter(gimnasio=gimnasio, tipo=tipo).values_list(
            "datos_adicionales", flat=True
        )
    }


def _clientes_inactivos(gimnasio, hoy):
    """Clientes con membresía vigente que dejaron de asistir."""
    dias = gimnasio.dias_inactividad_alerta
    limite = _inicio_del_dia(hoy - timedelta(days=dias))
    vigentes = Membresia.objects.filter(
        gimnasio=gimnasio,
        deleted_at__isnull=True,
        estado__in=(Membresia.Estado.ACTIVA, Membresia.Estado.POR_VENCER),
    ).values("cliente_id")
    clientes = (
        Cliente.objects.filter(
            usuario__gimnasio=gimnasio,
            is_active=True,
            deleted_at__isnull=True,
            pk__in=vigentes,
        )
        .annotate(
            ultima=Max(
                "asistencias__entrada_at",
                filter=Q(asistencias__deleted_at__isnull=True),
            )
        )
        .filter(Q(ultima__lt=limite) | Q(ultima__isnull=True, created_at__lt=limite))
        .select_related("usuario")
    )
    existentes = {
        (cliente_id, (datos or {}).get("ultima_asistencia"))
        for cliente_id, datos in Alerta.objects.filter(
            gimnasio=gimnasio, tipo=Alerta.Tipo.CLIENTE_INACTIVO
        ).values_list("cliente_id", "datos_adicionales")
    }
    nuevas = []
    for cliente in clientes:
        ultima = timezone.localtime(cliente.ultima).date().isoformat() if cliente.ultima else None
        if (cliente.pk, ultima) in existentes:
            continue
        nombre = cliente.usuario.nombre
        detalle = (
            f"no asiste desde el {timezone.localtime(cliente.ultima):%d/%m/%Y}"
            if cliente.ultima
            else "no ha registrado ninguna asistencia"
        )
        nuevas.append(
            Alerta(
                gimnasio=gimnasio,
                tipo=Alerta.Tipo.CLIENTE_INACTIVO,
                prioridad=Alerta.Prioridad.MEDIA,
                titulo=f"Cliente inactivo: {nombre}"[:200],
                mensaje=(
                    f"{nombre} tiene la membresía vigente pero {detalle} "
                    f"(más de {gimnasio.dias_inactividad_alerta} días)."
                ),
                cliente=cliente,
                datos_adicionales={"ultima_asistencia": ultima},
            )
        )
    return nuevas


def _ingresos_bajos(gimnasio, hoy):
    """Compara el último mes cerrado con el anterior."""
    mes_cerrado = _mes_anterior(_inicio_mes(hoy))
    mes_previo = _mes_anterior(mes_cerrado)
    periodo = mes_cerrado.strftime("%Y-%m")
    if periodo in _claves_existentes(gimnasio, Alerta.Tipo.INGRESOS_BAJOS, "periodo"):
        return []
    completados = Pago.objects.filter(
        gimnasio=gimnasio, deleted_at__isnull=True, estado=Pago.Estado.COMPLETADO
    )

    def total(desde, hasta):
        inicio, fin = _inicio_del_dia(desde), _inicio_del_dia(hasta)
        return completados.filter(fecha_pago__gte=inicio, fecha_pago__lt=fin).aggregate(
            total=Sum("valor")
        )["total"] or Decimal("0")

    actual = total(mes_cerrado, _inicio_mes(hoy))
    anterior = total(mes_previo, mes_cerrado)
    if anterior <= 0:
        return []
    caida = (anterior - actual) / anterior * 100
    if caida < gimnasio.porcentaje_caida_ingresos:
        return []
    return [
        Alerta(
            gimnasio=gimnasio,
            tipo=Alerta.Tipo.INGRESOS_BAJOS,
            prioridad=Alerta.Prioridad.ALTA,
            titulo=f"Los ingresos cayeron {caida:.0f} % en {mes_cerrado:%m/%Y}",
            mensaje=(
                f"En {mes_cerrado:%m/%Y} se recibieron {_moneda(actual)}, frente a "
                f"{_moneda(anterior)} del mes anterior."
            ),
            datos_adicionales={
                "periodo": periodo,
                "ingresos": str(actual),
                "ingresos_anterior": str(anterior),
                "caida_porcentaje": round(float(caida), 1),
            },
        )
    ]


def _gastos_altos(gimnasio, hoy):
    """Gastos del mes en curso por encima del límite configurado."""
    if not gimnasio.limite_gastos_mensual:
        return []
    periodo = hoy.strftime("%Y-%m")
    if periodo in _claves_existentes(gimnasio, Alerta.Tipo.GASTOS_ALTOS, "periodo"):
        return []
    total = Gasto.objects.filter(
        gimnasio=gimnasio,
        deleted_at__isnull=True,
        fecha__gte=_inicio_mes(hoy),
        fecha__lte=hoy,
    ).exclude(estado=Gasto.Estado.CANCELADO).aggregate(total=Sum("valor"))["total"] or Decimal("0")
    if total <= gimnasio.limite_gastos_mensual:
        return []
    return [
        Alerta(
            gimnasio=gimnasio,
            tipo=Alerta.Tipo.GASTOS_ALTOS,
            prioridad=Alerta.Prioridad.CRITICA,
            titulo=f"Los gastos de {hoy:%m/%Y} superan el límite",
            mensaje=(
                f"Van {_moneda(total)} en gastos este mes; el límite configurado es "
                f"{_moneda(gimnasio.limite_gastos_mensual)}."
            ),
            datos_adicionales={
                "periodo": periodo,
                "gastos": str(total),
                "limite": str(gimnasio.limite_gastos_mensual),
            },
        )
    ]


def _pagos_pendientes(gimnasio):
    """Una alerta por pago pendiente; las de pagos ya resueltos se cierran."""
    ahora = timezone.now()
    Alerta.objects.filter(
        gimnasio=gimnasio,
        tipo=Alerta.Tipo.PAGOS_PENDIENTES,
        leida=False,
        pago__isnull=False,
    ).exclude(pago__estado=Pago.Estado.PENDIENTE, pago__deleted_at__isnull=True).update(
        leida=True, leida_at=ahora, updated_at=ahora
    )
    con_alerta = Alerta.objects.filter(
        gimnasio=gimnasio, tipo=Alerta.Tipo.PAGOS_PENDIENTES, pago__isnull=False
    ).values("pago_id")
    pendientes = (
        Pago.objects.filter(
            gimnasio=gimnasio, deleted_at__isnull=True, estado=Pago.Estado.PENDIENTE
        )
        .exclude(pk__in=con_alerta)
        .select_related("cliente__usuario")
    )
    return [
        Alerta(
            gimnasio=gimnasio,
            tipo=Alerta.Tipo.PAGOS_PENDIENTES,
            prioridad=Alerta.Prioridad.MEDIA,
            titulo=f"Pago pendiente: {pago.cliente.usuario.nombre}"[:200],
            mensaje=(
                f"{pago.cliente.usuario.nombre} tiene un pago pendiente de "
                f"{_moneda(pago.valor)} ({pago.get_concepto_display().lower()})."
            ),
            cliente=pago.cliente,
            pago=pago,
        )
        for pago in pendientes
    ]


def alerta_nuevo_gasto(gasto):
    """Avisa a la administración de cada gasto registrado."""
    return Alerta.objects.create(
        gimnasio_id=gasto.gimnasio_id,
        tipo=Alerta.Tipo.NUEVO_GASTO,
        prioridad=Alerta.Prioridad.BAJA,
        titulo=f"Nuevo gasto: {gasto.descripcion}"[:200],
        mensaje=(
            f"{gasto.registrado_por.nombre} registró un gasto de {_moneda(gasto.valor)} "
            f"en {gasto.categoria.nombre} con fecha {gasto.fecha:%d/%m/%Y}."
        ),
        gasto=gasto,
    )


def generar_alertas(gimnasio, hoy=None):
    """Actualiza estados de membresía y crea las alertas que falten."""
    hoy = hoy or timezone.localdate()
    with transaction.atomic():
        Membresia.sincronizar_estados(hoy=hoy, gimnasio_id=gimnasio.pk)
        conteo = {"membresias": Alerta.generar_de_membresias(gimnasio_id=gimnasio.pk)}
        for nombre, nuevas in (
            ("clientes_inactivos", _clientes_inactivos(gimnasio, hoy)),
            ("ingresos_bajos", _ingresos_bajos(gimnasio, hoy)),
            ("gastos_altos", _gastos_altos(gimnasio, hoy)),
            ("pagos_pendientes", _pagos_pendientes(gimnasio)),
        ):
            Alerta.objects.bulk_create(nuevas)
            conteo[nombre] = len(nuevas)
    return conteo


def generar_alertas_de(usuario):
    """Genera las alertas del gimnasio de ``usuario`` (o de todos, para la plataforma)."""
    gimnasio_id = getattr(usuario, "gimnasio_id", None)
    gimnasios = Gimnasio.objects.filter(is_active=True, deleted_at__isnull=True)
    if gimnasio_id:
        gimnasios = gimnasios.filter(pk=gimnasio_id)
    for gimnasio in gimnasios:
        generar_alertas(gimnasio)
