"""Carga de variables de entorno desde ``backend/.env``.

Permite definir la configuración local en ``backend/.env`` (ver
``backend/.env.example``) sin exportar variables en la terminal. Se ejecuta
antes de leer ``settings`` y nunca sobrescribe variables que ya existan en el
proceso, de modo que la terminal y el archivo pueden combinarse.
"""

import os
from pathlib import Path


def cargar_env(ruta: Path) -> None:
    """Completa ``os.environ`` con las claves de un archivo ``CLAVE=valor``.

    Ignora líneas vacías, comentarios, el prefijo ``export`` y cualquier línea
    sin ``=`` o con un nombre de clave inválido. Los valores pueden ir entre
    comillas simples o dobles. Si el archivo no existe, no hace nada.
    """
    try:
        contenido = ruta.read_text(encoding="utf-8-sig")
    except OSError:
        return

    for linea in contenido.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        if linea.startswith("export "):
            linea = linea[len("export ") :].strip()

        clave, separador, valor = linea.partition("=")
        clave = clave.strip()
        if not separador or not clave or not clave[0].isalpha():
            continue
        if not clave.replace("_", "").isalnum():
            continue

        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]

        os.environ.setdefault(clave, valor)
