"""Ajustes del esquema OpenAPI generado por drf-spectacular."""


def desambiguar_operation_ids(result=None, generator=None, request=None, public=False):
    """Garantiza ``operationId`` únicos antes de la sanitización final.

    Las acciones con ``operation_id`` explícito se documentan dos veces: bajo
    la versión canónica ``/api/v1/`` y bajo el alias de compatibilidad
    ``/api/``. Como comparten identificador, drf-spectacular los renombra con
    sufijos numéricos y emite advertencias. Este hook conserva el id limpio
    para la ruta canónica y añade un sufijo legible al montaje del alias.
    """
    rutas = result.get("paths", {})
    # Las rutas canónicas se procesan primero para que conserven el id limpio.
    ordenadas = sorted(
        rutas, key=lambda ruta: (not ruta.startswith("/api/v1/"), ruta)
    )

    vistos = set()
    for ruta in ordenadas:
        sufijo = "v1" if ruta.startswith("/api/v1/") else "compat"
        for operacion in rutas[ruta].values():
            if not isinstance(operacion, dict):
                continue
            operation_id = operacion.get("operationId")
            if not operation_id:
                continue

            candidato = operation_id
            if candidato in vistos:
                candidato = f"{operation_id}_{sufijo}"
            while candidato in vistos:
                candidato = f"{candidato}_"

            operacion["operationId"] = candidato
            vistos.add(candidato)

    return result
