"""Gestión de alias (nombres personalizados) de recursos.

Los alias se persisten en un archivo JSON fuera de la base de datos para no
modificar el esquema ni los datos existentes. Cada entrada mapea el nombre
canonical del recurso (ej. ``clientes``) a un nombre de visualización
personalizado (ej. ``Mis Clientes``).
"""

import json
from pathlib import Path

ALIASES_FILE = Path(__file__).resolve().parent.parent / "resource_aliases.json"


def _load() -> dict[str, str]:
    try:
        with open(ALIASES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save(data: dict[str, str]) -> None:
    with open(ALIASES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_aliases() -> dict[str, str]:
    """Devuelve todos los alias configurados (nombre_original -> nombre_personalizado)."""
    return dict(_load())


def get_alias(nombre_original: str) -> str | None:
    """Devuelve el alias personalizado de un recurso, o None si no tiene uno."""
    return _load().get(nombre_original)


def set_alias(nombre_original: str, alias: str | None) -> None:
    """Establece o elimina el alias de un recurso."""
    data = _load()
    if alias:
        data[nombre_original] = alias
    else:
        data.pop(nombre_original, None)
    _save(data)


def resolve_name(nombre: str, recursos_validos: set[str]) -> str:
    """Resuelve un nombre (alias o original) al nombre original del recurso.

    Si ``nombre`` coincide con un alias conocido, devuelve el nombre original.
    Si ``nombre`` ya es un recurso válido, lo devuelve tal cual.
    De lo contrario, devuelve ``nombre`` sin cambios.
    """
    aliases = _load()
    for original, alias in aliases.items():
        if alias == nombre:
            return original
    if nombre in recursos_validos:
        return nombre
    return nombre
