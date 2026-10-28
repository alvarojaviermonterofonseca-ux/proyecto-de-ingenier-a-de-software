"""Entrega del build Angular desde Django en ``/app/``."""

from pathlib import Path
import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404


def _dist_root() -> Path:
    return Path(settings.PROJECT_ROOT) / "frontend" / "dist" / "gym-control-rbac" / "browser"


def spa_view(request, path=""):
    root = _dist_root().resolve()
    index = root / "index.html"
    if not index.is_file():
        raise Http404("El frontend no está compilado. Ejecute npm run build en frontend/.")

    if path:
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise Http404("Ruta no válida.") from error
        if candidate.is_file():
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            response = FileResponse(candidate.open("rb"), content_type=content_type)
            if candidate.name == "index.html":
                response["Cache-Control"] = "no-cache"
            else:
                response["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
        if Path(path).suffix:
            raise Http404("Recurso no encontrado.")

    response = FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
