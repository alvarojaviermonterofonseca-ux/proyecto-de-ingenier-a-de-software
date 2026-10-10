"""Formato uniforme para errores JSON de la API."""

from django.db import IntegrityError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        mensajes = {
            400: "La solicitud contiene datos no válidos.",
            401: "Debe autenticarse para realizar esta operación.",
            403: "No tiene permisos para realizar esta operación.",
            404: "No se encontró el recurso solicitado.",
            405: "El método HTTP no está permitido para este recurso.",
        }
        response.data = {
            "error": {
                "codigo": response.status_code,
                "mensaje": mensajes.get(response.status_code, "No se pudo completar la solicitud."),
                "detalles": response.data,
            }
        }
        return response

    if isinstance(exc, IntegrityError):
        return Response(
            {
                "error": {
                    "codigo": 409,
                    "mensaje": "La operación entra en conflicto con una restricción de integridad.",
                    "detalles": "Revise que las referencias y los campos únicos no estén duplicados.",
                }
            },
            status=409,
        )
    return None
