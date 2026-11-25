"""Reportes administrativos del gimnasio en Excel (.xlsx) y PDF.

Cada reporte se arma primero como una estructura neutra (``Reporte``: resumen
y tablas con columnas tipadas) a partir de datos reales del gimnasio, y luego
se dibuja en Excel con openpyxl o en PDF con reportlab. Así ambos formatos
muestran exactamente las mismas cifras.

El gimnasio lo decide la vista a partir del usuario autenticado; aquí solo se
recibe ya resuelto y todas las consultas se restringen a él.
"""

import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import Asistencia, Cliente, Gasto, Membresia, Pago
from .tenancy import ruta_gimnasio

# Límite de filas de detalle. Excel admite muchas más, pero un PDF de miles de
# páginas no sirve a nadie: allí se avisa que el detalle está recortado.
MAX_FILAS_EXCEL = 50000
MAX_FILAS_PDF = 1500
MAX_DIAS_RANGO = 366 * 5

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

# Tipos de columna: texto, moneda, entero, decimal, porcentaje, fecha, fechahora.


@dataclass
class Tabla:
    titulo: str
    columnas: list  # [(nombre, tipo)]
    filas: list = field(default_factory=list)
    totales: list | None = None
    nota: str = ""


@dataclass
class Reporte:
    tipo: str
    titulo: str
    descripcion: str
    gimnasio: str
    desde: date
    hasta: date
    generado_por: str
    generado_en: datetime
    resumen: list = field(default_factory=list)  # [(etiqueta, valor, tipo)]
    tablas: list = field(default_factory=list)


TIPOS_REPORTE = {
    "financiero": ("Reporte financiero", "Ingresos, gastos y ganancia neta del período."),
    "ingresos": ("Reporte de ingresos", "Pagos registrados en el período (fecha del pago)."),
    "gastos": ("Reporte de gastos", "Egresos registrados en el período (fecha del gasto)."),
    "asistencia": ("Reporte de asistencia", "Entradas de clientes registradas en el período."),
    "clientes": ("Reporte de clientes", "Clientes del gimnasio y su situación de membresía."),
    "membresias": (
        "Reporte de membresías",
        "Membresías vigentes en algún momento del período.",
    ),
    "crecimiento": (
        "Reporte de crecimiento",
        "Evolución mensual de clientes, membresías, ingresos y asistencias.",
    ),
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _del_gimnasio(queryset, gimnasio_id):
    return queryset.filter(**{ruta_gimnasio(queryset.model): gimnasio_id})


def _inicio(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


def _rango_momentos(desde, hasta):
    return _inicio(desde), _inicio(hasta + timedelta(days=1))


def _meses_del_rango(desde, hasta):
    meses = []
    actual = date(desde.year, desde.month, 1)
    while actual <= hasta:
        meses.append(actual)
        actual = date(actual.year + (actual.month // 12), actual.month % 12 + 1, 1)
    return meses


def _clave_mes(fecha):
    return date(fecha.year, fecha.month, 1)


def _nombre_mes(mes):
    return f"{MESES[mes.month - 1].capitalize()} {mes.year}"


def _local(momento):
    return timezone.localtime(momento) if momento else None


def _porcentaje(parte, total):
    if not total:
        return Decimal("0")
    return (Decimal(parte) * 100 / Decimal(total)).quantize(Decimal("0.1"))


def _etiqueta(choices, valor):
    return dict(choices).get(valor, valor or "")


def formato_moneda(valor):
    """``$ 150.000`` (pesos colombianos, sin decimales)."""
    numero = int(round(Decimal(valor or 0)))
    signo = "-" if numero < 0 else ""
    return f"{signo}$ {abs(numero):,}".replace(",", ".")


def formato_valor(valor, tipo):
    if valor is None or valor == "":
        return ""
    if isinstance(valor, str):
        # Etiquetas como "Total" en columnas numéricas o de fecha.
        return valor
    if tipo == "moneda":
        return formato_moneda(valor)
    if tipo == "entero":
        return f"{int(valor):,}".replace(",", ".")
    if tipo == "decimal":
        return f"{Decimal(valor):.1f}".replace(".", ",")
    if tipo == "porcentaje":
        return f"{Decimal(valor):.1f} %".replace(".", ",")
    if tipo == "fecha":
        return valor.strftime("%d/%m/%Y")
    if tipo == "fechahora":
        return _local(valor).strftime("%d/%m/%Y %H:%M")
    return str(valor)


# ---------------------------------------------------------------------------
# Constructores de cada reporte
# ---------------------------------------------------------------------------


def _pagos(gimnasio_id, desde, hasta):
    inicio, fin = _rango_momentos(desde, hasta)
    return _del_gimnasio(
        Pago.objects.filter(deleted_at__isnull=True, fecha_pago__gte=inicio, fecha_pago__lt=fin),
        gimnasio_id,
    ).select_related("cliente__usuario", "metodo_pago", "membresia", "registrado_por")


def _gastos(gimnasio_id, desde, hasta):
    return _del_gimnasio(
        Gasto.objects.filter(deleted_at__isnull=True, fecha__gte=desde, fecha__lte=hasta),
        gimnasio_id,
    ).select_related("categoria", "metodo_pago", "registrado_por", "aprobado_por")


def _asistencias(gimnasio_id, desde, hasta):
    inicio, fin = _rango_momentos(desde, hasta)
    return _del_gimnasio(
        Asistencia.objects.filter(
            deleted_at__isnull=True, entrada_at__gte=inicio, entrada_at__lt=fin
        ),
        gimnasio_id,
    ).select_related("cliente__usuario")


def _clientes(gimnasio_id):
    return _del_gimnasio(
        Cliente.objects.filter(deleted_at__isnull=True, usuario__deleted_at__isnull=True),
        gimnasio_id,
    ).select_related("usuario")


def _reporte_financiero(reporte, gimnasio_id):
    pagos = list(_pagos(gimnasio_id, reporte.desde, reporte.hasta))
    gastos = list(_gastos(gimnasio_id, reporte.desde, reporte.hasta))
    completados = [pago for pago in pagos if pago.estado == Pago.Estado.COMPLETADO]
    pendientes = [pago for pago in pagos if pago.estado == Pago.Estado.PENDIENTE]
    vigentes = [gasto for gasto in gastos if gasto.estado != Gasto.Estado.CANCELADO]

    total_ingresos = sum((pago.valor for pago in completados), Decimal("0"))
    total_pendiente = sum((pago.valor for pago in pendientes), Decimal("0"))
    total_gastos = sum((gasto.valor for gasto in vigentes), Decimal("0"))
    ganancia = total_ingresos - total_gastos
    reporte.resumen = [
        ("Ingresos completados", total_ingresos, "moneda"),
        ("Gastos", total_gastos, "moneda"),
        ("Ganancia neta", ganancia, "moneda"),
        ("Margen neto", _porcentaje(ganancia, total_ingresos), "porcentaje"),
        ("Pagos pendientes", total_pendiente, "moneda"),
        ("Transacciones completadas", len(completados), "entero"),
    ]

    ingresos_mes = defaultdict(Decimal)
    for pago in completados:
        ingresos_mes[_clave_mes(_local(pago.fecha_pago))] += pago.valor
    gastos_mes = defaultdict(Decimal)
    for gasto in vigentes:
        gastos_mes[_clave_mes(gasto.fecha)] += gasto.valor
    filas = []
    for mes in _meses_del_rango(reporte.desde, reporte.hasta):
        ingreso, gasto = ingresos_mes[mes], gastos_mes[mes]
        filas.append([_nombre_mes(mes), ingreso, gasto, ingreso - gasto])
    reporte.tablas.append(
        Tabla(
            "Resultado por mes",
            [("Mes", "texto"), ("Ingresos", "moneda"), ("Gastos", "moneda"), ("Ganancia neta", "moneda")],
            filas,
            ["Total", total_ingresos, total_gastos, ganancia],
        )
    )

    por_concepto = defaultdict(lambda: [0, Decimal("0")])
    por_metodo = defaultdict(lambda: [0, Decimal("0")])
    for pago in completados:
        por_concepto[pago.get_concepto_display()][0] += 1
        por_concepto[pago.get_concepto_display()][1] += pago.valor
        por_metodo[pago.metodo_pago.nombre][0] += 1
        por_metodo[pago.metodo_pago.nombre][1] += pago.valor
    for titulo, datos, columna in (
        ("Ingresos por concepto", por_concepto, "Concepto"),
        ("Ingresos por método de pago", por_metodo, "Método"),
    ):
        filas = sorted(
            ([nombre, cantidad, valor, _porcentaje(valor, total_ingresos)]
             for nombre, (cantidad, valor) in datos.items()),
            key=lambda fila: -fila[2],
        )
        reporte.tablas.append(
            Tabla(
                titulo,
                [(columna, "texto"), ("Pagos", "entero"), ("Valor", "moneda"), ("Participación", "porcentaje")],
                filas,
                ["Total", len(completados), total_ingresos, Decimal("100") if filas else Decimal("0")],
            )
        )

    reporte.tablas.append(_tabla_gastos_por_categoria(vigentes, total_gastos))


def _tabla_gastos_por_categoria(vigentes, total_gastos):
    por_categoria = defaultdict(lambda: [0, Decimal("0")])
    for gasto in vigentes:
        por_categoria[gasto.categoria.nombre][0] += 1
        por_categoria[gasto.categoria.nombre][1] += gasto.valor
    filas = sorted(
        ([nombre, cantidad, valor, _porcentaje(valor, total_gastos)]
         for nombre, (cantidad, valor) in por_categoria.items()),
        key=lambda fila: -fila[2],
    )
    return Tabla(
        "Gastos por categoría",
        [("Categoría", "texto"), ("Gastos", "entero"), ("Valor", "moneda"), ("Participación", "porcentaje")],
        filas,
        ["Total", len(vigentes), total_gastos, Decimal("100") if filas else Decimal("0")],
    )


def _reporte_ingresos(reporte, gimnasio_id):
    pagos = list(_pagos(gimnasio_id, reporte.desde, reporte.hasta).order_by("fecha_pago", "id"))
    por_estado = defaultdict(lambda: [0, Decimal("0")])
    for pago in pagos:
        por_estado[pago.estado][0] += 1
        por_estado[pago.estado][1] += pago.valor
    completado = por_estado[Pago.Estado.COMPLETADO]
    reporte.resumen = [
        ("Ingresos completados", completado[1], "moneda"),
        ("Pagos completados", completado[0], "entero"),
        ("Pendiente por cobrar", por_estado[Pago.Estado.PENDIENTE][1], "moneda"),
        ("Pagos pendientes", por_estado[Pago.Estado.PENDIENTE][0], "entero"),
        ("Reembolsado", por_estado[Pago.Estado.REEMBOLSADO][1], "moneda"),
        ("Ticket promedio", completado[1] / completado[0] if completado[0] else 0, "moneda"),
    ]
    reporte.tablas.append(
        Tabla(
            "Pagos por estado",
            [("Estado", "texto"), ("Pagos", "entero"), ("Valor", "moneda")],
            [
                [_etiqueta(Pago.Estado.choices, estado), cantidad, valor]
                for estado, (cantidad, valor) in por_estado.items()
                if cantidad
            ],
        )
    )
    reporte.tablas.append(
        Tabla(
            "Detalle de pagos",
            [
                ("Fecha", "fechahora"), ("Cliente", "texto"), ("Concepto", "texto"),
                ("Tipo de membresía", "texto"), ("Valor", "moneda"), ("Método", "texto"),
                ("Estado", "texto"), ("Registrado por", "texto"), ("Referencia", "texto"),
            ],
            [
                [
                    pago.fecha_pago,
                    pago.cliente.usuario.nombre,
                    pago.get_concepto_display(),
                    pago.membresia.get_tipo_display() if pago.membresia else "",
                    pago.valor,
                    pago.metodo_pago.nombre,
                    pago.get_estado_display(),
                    pago.registrado_por.nombre,
                    pago.referencia or "",
                ]
                for pago in pagos
            ],
            ["Total completado", "", "", "", completado[1], "", "", "", ""],
        )
    )


def _reporte_gastos(reporte, gimnasio_id):
    gastos = list(_gastos(gimnasio_id, reporte.desde, reporte.hasta).order_by("fecha", "id"))
    vigentes = [gasto for gasto in gastos if gasto.estado != Gasto.Estado.CANCELADO]
    total = sum((gasto.valor for gasto in vigentes), Decimal("0"))
    dias = (reporte.hasta - reporte.desde).days + 1
    reporte.resumen = [
        ("Total de gastos", total, "moneda"),
        ("Gastos registrados", len(vigentes), "entero"),
        ("Promedio diario", total / dias, "moneda"),
        ("Gastos anulados", len(gastos) - len(vigentes), "entero"),
        (
            "Pendiente de pago",
            sum((g.valor for g in vigentes if g.estado != Gasto.Estado.PAGADO), Decimal("0")),
            "moneda",
        ),
    ]
    reporte.tablas.append(_tabla_gastos_por_categoria(vigentes, total))
    reporte.tablas.append(
        Tabla(
            "Detalle de gastos",
            [
                ("Fecha", "fecha"), ("Descripción", "texto"), ("Categoría", "texto"),
                ("Valor", "moneda"), ("Método", "texto"), ("Estado", "texto"),
                ("Registrado por", "texto"), ("Aprobado por", "texto"), ("Referencia", "texto"),
            ],
            [
                [
                    gasto.fecha,
                    gasto.descripcion,
                    gasto.categoria.nombre,
                    gasto.valor,
                    gasto.metodo_pago.nombre,
                    gasto.get_estado_display(),
                    gasto.registrado_por.nombre,
                    gasto.aprobado_por.nombre if gasto.aprobado_por else "",
                    gasto.referencia or "",
                ]
                for gasto in gastos
            ],
            ["Total (sin anulados)", "", "", total, "", "", "", "", ""],
        )
    )


def _reporte_asistencia(reporte, gimnasio_id):
    asistencias = list(
        _asistencias(gimnasio_id, reporte.desde, reporte.hasta).order_by("entrada_at", "id")
    )
    entradas = [_local(asistencia.entrada_at) for asistencia in asistencias]
    por_dia = Counter(momento.date() for momento in entradas)
    por_hora = Counter(momento.hour for momento in entradas)
    dias = (reporte.hasta - reporte.desde).days + 1
    hora_pico = max(por_hora.items(), key=lambda par: (par[1], -par[0]))[0] if por_hora else None
    reporte.resumen = [
        ("Asistencias", len(asistencias), "entero"),
        ("Clientes distintos", len({a.cliente_id for a in asistencias}), "entero"),
        ("Promedio diario", Decimal(len(asistencias)) / dias, "decimal"),
        ("Hora pico", f"{hora_pico:02d}:00" if hora_pico is not None else "Sin datos", "texto"),
    ]
    reporte.tablas.append(
        Tabla(
            "Asistencias por día",
            [("Fecha", "fecha"), ("Asistencias", "entero")],
            [
                [reporte.desde + timedelta(days=i), por_dia.get(reporte.desde + timedelta(days=i), 0)]
                for i in range(dias)
            ],
            ["Total", len(asistencias)],
        )
    )
    reporte.tablas.append(
        Tabla(
            "Asistencias por hora",
            [("Hora", "texto"), ("Asistencias", "entero"), ("Participación", "porcentaje")],
            [
                [f"{hora:02d}:00", total, _porcentaje(total, len(asistencias))]
                for hora, total in sorted(por_hora.items())
            ],
        )
    )
    filas = []
    for asistencia in asistencias:
        duracion = ""
        if asistencia.salida_at:
            duracion = int((asistencia.salida_at - asistencia.entrada_at).total_seconds() // 60)
        filas.append([
            asistencia.entrada_at,
            asistencia.salida_at,
            asistencia.cliente.usuario.nombre,
            duracion,
            asistencia.get_metodo_entrada_display(),
        ])
    reporte.tablas.append(
        Tabla(
            "Detalle de asistencias",
            [("Entrada", "fechahora"), ("Salida", "fechahora"), ("Cliente", "texto"),
             ("Minutos", "entero"), ("Método", "texto")],
            filas,
        )
    )


def _membresia_actual_por_cliente(gimnasio_id):
    """Última membresía (por fecha de fin) de cada cliente del gimnasio."""
    actuales = {}
    membresias = _del_gimnasio(
        Membresia.objects.filter(deleted_at__isnull=True), gimnasio_id
    ).order_by("cliente_id", "fecha_fin", "id")
    for membresia in membresias:
        actuales[membresia.cliente_id] = membresia
    return actuales


def _reporte_clientes(reporte, gimnasio_id):
    hoy = timezone.localdate()
    clientes = list(_clientes(gimnasio_id).order_by("usuario__nombre"))
    membresias = _membresia_actual_por_cliente(gimnasio_id)
    ultimas = {}
    for cliente_id, entrada in _del_gimnasio(
        Asistencia.objects.filter(deleted_at__isnull=True), gimnasio_id
    ).values_list("cliente_id", "entrada_at"):
        if cliente_id not in ultimas or entrada > ultimas[cliente_id]:
            ultimas[cliente_id] = entrada
    inicio, fin = _rango_momentos(reporte.desde, reporte.hasta)

    vigentes = (Membresia.Estado.ACTIVA, Membresia.Estado.POR_VENCER)
    filas = []
    activos = nuevos = por_vencer = 0
    for cliente in clientes:
        membresia = membresias.get(cliente.pk)
        activo = bool(
            cliente.is_active and membresia and membresia.estado in vigentes and membresia.fecha_fin >= hoy
        )
        activos += activo
        es_nuevo = inicio <= cliente.created_at < fin
        nuevos += es_nuevo
        if membresia and membresia.estado == Membresia.Estado.POR_VENCER:
            por_vencer += 1
        filas.append([
            cliente.usuario.nombre,
            cliente.usuario.correo,
            " ".join(filter(None, (cliente.tipo_documento, cliente.numero_documento))),
            cliente.usuario.telefono or "",
            _local(cliente.created_at).date(),
            "Sí" if es_nuevo else "No",
            "Activo" if activo else "Inactivo",
            membresia.get_tipo_display() if membresia else "Sin membresía",
            membresia.fecha_fin if membresia else None,
            _local(ultimas[cliente.pk]).date() if cliente.pk in ultimas else None,
        ])
    reporte.resumen = [
        ("Clientes registrados", len(clientes), "entero"),
        ("Nuevos en el período", nuevos, "entero"),
        ("Activos (membresía vigente)", activos, "entero"),
        ("Inactivos", len(clientes) - activos, "entero"),
        ("Membresías por vencer", por_vencer, "entero"),
        ("Tasa de actividad", _porcentaje(activos, len(clientes)), "porcentaje"),
    ]
    reporte.tablas.append(
        Tabla(
            "Clientes",
            [
                ("Nombre", "texto"), ("Correo", "texto"), ("Documento", "texto"),
                ("Teléfono", "texto"), ("Registro", "fecha"), ("Nuevo en el período", "texto"),
                ("Estado", "texto"), ("Membresía actual", "texto"), ("Vence", "fecha"),
                ("Última asistencia", "fecha"),
            ],
            filas,
        )
    )


def _reporte_membresias(reporte, gimnasio_id):
    membresias = list(
        _del_gimnasio(
            Membresia.objects.filter(
                deleted_at__isnull=True,
                fecha_inicio__lte=reporte.hasta,
                fecha_fin__gte=reporte.desde,
            ),
            gimnasio_id,
        )
        .select_related("cliente__usuario")
        .order_by("fecha_fin", "id")
    )
    por_estado = Counter(membresia.estado for membresia in membresias)
    por_tipo = defaultdict(lambda: [0, Decimal("0")])
    for membresia in membresias:
        por_tipo[membresia.tipo][0] += 1
        por_tipo[membresia.tipo][1] += membresia.precio or Decimal("0")
    inicio, fin = _rango_momentos(reporte.desde, reporte.hasta)
    vendidas = sum(1 for membresia in membresias if inicio <= membresia.created_at < fin)
    reporte.resumen = [
        ("Membresías en el período", len(membresias), "entero"),
        ("Vendidas en el período", vendidas, "entero"),
        ("Activas", por_estado[Membresia.Estado.ACTIVA], "entero"),
        ("Por vencer", por_estado[Membresia.Estado.POR_VENCER], "entero"),
        ("Vencidas", por_estado[Membresia.Estado.VENCIDA], "entero"),
        ("Congeladas o canceladas",
         por_estado[Membresia.Estado.CONGELADA] + por_estado[Membresia.Estado.CANCELADA], "entero"),
    ]
    reporte.tablas.append(
        Tabla(
            "Membresías por tipo",
            [("Tipo", "texto"), ("Cantidad", "entero"), ("Valor total", "moneda"), ("Participación", "porcentaje")],
            sorted(
                ([_etiqueta(Membresia.Tipo.choices, tipo), cantidad, valor, _porcentaje(cantidad, len(membresias))]
                 for tipo, (cantidad, valor) in por_tipo.items()),
                key=lambda fila: -fila[1],
            ),
        )
    )
    reporte.tablas.append(
        Tabla(
            "Detalle de membresías",
            [
                ("Cliente", "texto"), ("Membresía", "texto"), ("Tipo", "texto"),
                ("Inicio", "fecha"), ("Fin", "fecha"), ("Estado", "texto"), ("Precio", "moneda"),
            ],
            [
                [
                    membresia.cliente.usuario.nombre,
                    membresia.nombre,
                    membresia.get_tipo_display(),
                    membresia.fecha_inicio,
                    membresia.fecha_fin,
                    membresia.get_estado_display(),
                    membresia.precio,
                ]
                for membresia in membresias
            ],
        )
    )


def _reporte_crecimiento(reporte, gimnasio_id):
    meses = _meses_del_rango(reporte.desde, reporte.hasta)
    inicio, fin = _rango_momentos(reporte.desde, reporte.hasta)
    clientes = _clientes(gimnasio_id)
    previos = clientes.filter(created_at__lt=inicio).count()

    def contar(momentos):
        return Counter(_clave_mes(_local(momento)) for momento in momentos)

    nuevos = contar(clientes.filter(created_at__gte=inicio, created_at__lt=fin).values_list("created_at", flat=True))
    vendidas = contar(
        _del_gimnasio(Membresia.objects.filter(deleted_at__isnull=True), gimnasio_id)
        .filter(created_at__gte=inicio, created_at__lt=fin)
        .values_list("created_at", flat=True)
    )
    asistencias = contar(_asistencias(gimnasio_id, reporte.desde, reporte.hasta).values_list("entrada_at", flat=True))
    ingresos = defaultdict(Decimal)
    for momento, valor in _pagos(gimnasio_id, reporte.desde, reporte.hasta).filter(
        estado=Pago.Estado.COMPLETADO
    ).values_list("fecha_pago", "valor"):
        ingresos[_clave_mes(_local(momento))] += valor

    filas = []
    acumulado = previos
    anterior = None
    for mes in meses:
        acumulado += nuevos[mes]
        variacion = (
            _porcentaje(ingresos[mes] - anterior, anterior) if anterior else None
        )
        filas.append([
            _nombre_mes(mes), nuevos[mes], acumulado, vendidas[mes],
            asistencias[mes], ingresos[mes], variacion,
        ])
        anterior = ingresos[mes]

    total_nuevos = sum(nuevos.values())
    reporte.resumen = [
        ("Clientes al inicio", previos, "entero"),
        ("Clientes nuevos", total_nuevos, "entero"),
        ("Clientes al cierre", acumulado, "entero"),
        ("Crecimiento de la base", _porcentaje(total_nuevos, previos) if previos else Decimal("0"), "porcentaje"),
        ("Membresías vendidas", sum(vendidas.values()), "entero"),
        ("Ingresos completados", sum(ingresos.values(), Decimal("0")), "moneda"),
    ]
    reporte.tablas.append(
        Tabla(
            "Evolución mensual",
            [
                ("Mes", "texto"), ("Clientes nuevos", "entero"), ("Clientes acumulados", "entero"),
                ("Membresías vendidas", "entero"), ("Asistencias", "entero"),
                ("Ingresos", "moneda"), ("Variación ingresos", "porcentaje"),
            ],
            filas,
            nota="La variación compara los ingresos de cada mes con los del mes anterior.",
        )
    )


CONSTRUCTORES = {
    "financiero": _reporte_financiero,
    "ingresos": _reporte_ingresos,
    "gastos": _reporte_gastos,
    "asistencia": _reporte_asistencia,
    "clientes": _reporte_clientes,
    "membresias": _reporte_membresias,
    "crecimiento": _reporte_crecimiento,
}


def construir_reporte(tipo, gimnasio, desde, hasta, generado_por):
    titulo, descripcion = TIPOS_REPORTE[tipo]
    reporte = Reporte(
        tipo=tipo,
        titulo=titulo,
        descripcion=descripcion,
        gimnasio=gimnasio.nombre,
        desde=desde,
        hasta=hasta,
        generado_por=generado_por,
        generado_en=timezone.localtime(),
    )
    CONSTRUCTORES[tipo](reporte, gimnasio.pk)
    return reporte


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

FORMATOS_EXCEL = {
    "moneda": '"$" #,##0',
    "entero": "#,##0",
    "decimal": "#,##0.0",
    "porcentaje": '0.0" %"',
    "fecha": "dd/mm/yyyy",
    "fechahora": "dd/mm/yyyy hh:mm",
}


def _valor_excel(valor, tipo):
    if valor is None or valor == "":
        return None
    if tipo in ("moneda", "decimal", "porcentaje") and not isinstance(valor, str):
        return float(valor)
    if tipo == "fechahora" and isinstance(valor, datetime):
        # Excel no maneja zonas horarias: se escribe la hora local de Bogotá.
        return _local(valor).replace(tzinfo=None)
    if tipo == "texto" and isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@"):
        # Evita que un texto se interprete como fórmula al abrir el archivo.
        return "'" + valor
    return valor


def a_excel(reporte):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Resumen"
    titulo = Font(bold=True, size=14, color="1E293B")
    negrita = Font(bold=True)
    encabezado = Font(bold=True, color="FFFFFF")
    relleno = PatternFill("solid", fgColor="2563EB")
    relleno_total = PatternFill("solid", fgColor="E2E8F0")
    borde = Border(bottom=Side(style="thin", color="CBD5E1"))

    hoja["A1"] = reporte.titulo
    hoja["A1"].font = titulo
    hoja["A2"] = reporte.gimnasio
    hoja["A2"].font = negrita
    hoja["A3"] = f"Período: {formato_valor(reporte.desde, 'fecha')} a {formato_valor(reporte.hasta, 'fecha')}"
    hoja["A4"] = (
        f"Generado el {reporte.generado_en.strftime('%d/%m/%Y %H:%M')} por {reporte.generado_por}"
    )
    hoja["A5"] = reporte.descripcion
    fila = 7
    hoja.cell(row=fila, column=1, value="Indicador").font = encabezado
    hoja.cell(row=fila, column=2, value="Valor").font = encabezado
    hoja.cell(row=fila, column=1).fill = relleno
    hoja.cell(row=fila, column=2).fill = relleno
    for etiqueta, valor, tipo in reporte.resumen:
        fila += 1
        hoja.cell(row=fila, column=1, value=etiqueta).border = borde
        celda = hoja.cell(row=fila, column=2, value=_valor_excel(valor, tipo))
        celda.border = borde
        if tipo in FORMATOS_EXCEL:
            celda.number_format = FORMATOS_EXCEL[tipo]
        celda.alignment = Alignment(horizontal="right")
    hoja.column_dimensions["A"].width = 34
    hoja.column_dimensions["B"].width = 22

    nombres = {"Resumen"}
    for tabla in reporte.tablas:
        nombre = tabla.titulo[:31]
        while nombre in nombres:
            nombre = nombre[:29] + str(len(nombres))
        nombres.add(nombre)
        hoja = libro.create_sheet(nombre)
        hoja["A1"] = tabla.titulo
        hoja["A1"].font = titulo
        hoja["A2"] = (
            f"{reporte.gimnasio} · {formato_valor(reporte.desde, 'fecha')} a "
            f"{formato_valor(reporte.hasta, 'fecha')}"
        )
        inicio = 4
        for indice, (nombre_columna, _tipo) in enumerate(tabla.columnas, start=1):
            celda = hoja.cell(row=inicio, column=indice, value=nombre_columna)
            celda.font = encabezado
            celda.fill = relleno
            celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        anchos = [len(nombre) + 2 for nombre, _ in tabla.columnas]
        filas = tabla.filas[:MAX_FILAS_EXCEL]
        for desplazamiento, datos in enumerate(filas, start=1):
            for indice, ((_, tipo), valor) in enumerate(zip(tabla.columnas, datos), start=1):
                celda = hoja.cell(row=inicio + desplazamiento, column=indice, value=_valor_excel(valor, tipo))
                if tipo in FORMATOS_EXCEL:
                    celda.number_format = FORMATOS_EXCEL[tipo]
                anchos[indice - 1] = max(anchos[indice - 1], min(len(formato_valor(valor, tipo)) + 2, 48))
        ultima = inicio + len(filas)
        if not filas:
            hoja.cell(row=inicio + 1, column=1, value="Sin registros en el período.")
            ultima += 1
        if tabla.totales:
            ultima += 1
            for indice, ((_, tipo), valor) in enumerate(zip(tabla.columnas, tabla.totales), start=1):
                celda = hoja.cell(row=ultima, column=indice, value=_valor_excel(valor, tipo))
                celda.font = negrita
                celda.fill = relleno_total
                if tipo in FORMATOS_EXCEL:
                    celda.number_format = FORMATOS_EXCEL[tipo]
        notas = [tabla.nota] if tabla.nota else []
        if len(tabla.filas) > MAX_FILAS_EXCEL:
            notas.append(f"Se muestran las primeras {MAX_FILAS_EXCEL} filas de {len(tabla.filas)}.")
        for nota in notas:
            ultima += 2
            hoja.cell(row=ultima, column=1, value=nota).font = Font(italic=True, color="64748B")
        for indice, ancho in enumerate(anchos, start=1):
            hoja.column_dimensions[get_column_letter(indice)].width = ancho
        hoja.freeze_panes = hoja.cell(row=inicio + 1, column=1)
        if filas:
            hoja.auto_filter.ref = (
                f"A{inicio}:{get_column_letter(len(tabla.columnas))}{inicio + len(filas)}"
            )

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def a_pdf(reporte):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    salida = io.BytesIO()
    ancho_columnas = max((len(tabla.columnas) for tabla in reporte.tablas), default=0)
    pagina = landscape(A4) if ancho_columnas > 5 else A4
    documento = SimpleDocTemplate(
        salida,
        pagesize=pagina,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"{reporte.titulo} - {reporte.gimnasio}",
        author="Gym Control Pro",
    )
    estilos = getSampleStyleSheet()
    celda = ParagraphStyle("celda", parent=estilos["BodyText"], fontSize=8, leading=10)
    celda_derecha = ParagraphStyle("celda_derecha", parent=celda, alignment=TA_RIGHT)
    cabecera = ParagraphStyle("cabecera", parent=celda, textColor=colors.white, fontName="Helvetica-Bold")
    cabecera_derecha = ParagraphStyle("cabecera_derecha", parent=cabecera, alignment=TA_RIGHT)
    nota = ParagraphStyle("nota", parent=celda, textColor=colors.HexColor("#64748B"), fontName="Helvetica-Oblique")
    azul = colors.HexColor("#2563EB")
    gris = colors.HexColor("#E2E8F0")
    numericos = {"moneda", "entero", "decimal", "porcentaje"}

    def texto(valor, tipo="texto", estilo=None):
        from xml.sax.saxutils import escape

        if estilo is None:
            estilo = celda_derecha if tipo in numericos else celda
        return Paragraph(escape(formato_valor(valor, tipo)), estilo)

    historia = [
        Paragraph(f"{reporte.titulo}", estilos["Title"]),
        Paragraph(f"<b>{reporte.gimnasio}</b>", estilos["Normal"]),
        Paragraph(
            f"Período: {formato_valor(reporte.desde, 'fecha')} a {formato_valor(reporte.hasta, 'fecha')}"
            f" · Generado el {reporte.generado_en.strftime('%d/%m/%Y %H:%M')} por {reporte.generado_por}",
            estilos["Normal"],
        ),
        Paragraph(reporte.descripcion, nota),
        Spacer(1, 0.4 * cm),
    ]

    resumen = [[Paragraph("Indicador", cabecera), Paragraph("Valor", cabecera_derecha)]]
    resumen += [[texto(etiqueta), texto(valor, tipo, celda_derecha)] for etiqueta, valor, tipo in reporte.resumen]
    tabla_resumen = Table(resumen, colWidths=[8 * cm, 5 * cm], hAlign="LEFT")
    tabla_resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), azul),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, gris),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    historia += [tabla_resumen, Spacer(1, 0.6 * cm)]

    disponible = pagina[0] - 3 * cm
    for tabla in reporte.tablas:
        historia.append(Paragraph(tabla.titulo, estilos["Heading2"]))
        filas = tabla.filas[:MAX_FILAS_PDF]
        datos = [[
            Paragraph(nombre, cabecera_derecha if tipo in numericos else cabecera)
            for nombre, tipo in tabla.columnas
        ]]
        for fila in filas:
            datos.append([texto(valor, tipo) for (_, tipo), valor in zip(tabla.columnas, fila)])
        if not filas:
            datos.append([texto("Sin registros en el período.")] + [""] * (len(tabla.columnas) - 1))
        if tabla.totales:
            datos.append([
                texto(valor, tipo, celda_derecha if tipo in numericos else celda)
                for (_, tipo), valor in zip(tabla.columnas, tabla.totales)
            ])
        pdf_tabla = Table(
            datos,
            colWidths=[disponible / len(tabla.columnas)] * len(tabla.columnas),
            repeatRows=1,
            hAlign="LEFT",
        )
        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), azul),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, gris),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        if tabla.totales:
            estilo.append(("BACKGROUND", (0, -1), (-1, -1), gris))
        if not filas:
            estilo.append(("SPAN", (0, 1), (-1, 1)))
        pdf_tabla.setStyle(TableStyle(estilo))
        historia.append(pdf_tabla)
        if tabla.nota:
            historia.append(Paragraph(tabla.nota, nota))
        if len(tabla.filas) > MAX_FILAS_PDF:
            historia.append(Paragraph(
                f"Se muestran las primeras {MAX_FILAS_PDF} filas de {len(tabla.filas)}. "
                "Descargue el Excel para ver el detalle completo.",
                nota,
            ))
        historia.append(Spacer(1, 0.5 * cm))

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(1.5 * cm, 0.8 * cm, f"Gym Control Pro · {reporte.gimnasio}")
        canvas.drawRightString(pagina[0] - 1.5 * cm, 0.8 * cm, f"Página {doc.page}")
        canvas.restoreState()

    documento.build(historia, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()
