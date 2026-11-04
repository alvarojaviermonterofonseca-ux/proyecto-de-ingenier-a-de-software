"""Lista canónica de recursos registrados en la API.

Este módulo evita importaciones circulares entre ``views`` y ``serializers``.
"""

# Recursos que tienen ViewSet y aparecen en el menú/conteos.
RECURSOS_MENU: frozenset[str] = frozenset(
    {
        "usuarios",
        "usuarios-roles",
        "roles",
        "permisos",
        "clientes",
        "entrenadores",
        "terapeutas",
        "recepcionistas",
        "administradores",
        "asignaciones-cliente-entrenador",
        "clientes-terapeutas",
        "asistencias",
        "entrenamientos",
        "ejercicios",
        "planes-entrenamiento",
        "planes-alimentacion",
        "comidas",
        "registros-comida",
        "notificaciones",
        "auditoria",
    }
)

# Recursos con ViewSet propio aunque no aparezcan como sección del menú.
RECURSOS_API: frozenset[str] = RECURSOS_MENU | {"planes-entrenamiento-ejercicios"}