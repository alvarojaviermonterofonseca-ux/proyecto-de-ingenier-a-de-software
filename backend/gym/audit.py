from .models import EventoAuditoria, Usuario


def registrar_evento(request, accion, recurso, objeto=None, objeto_id=None, detalles=None):
    actor = getattr(request, "user", None)
    if not isinstance(actor, Usuario) or not actor.is_authenticated:
        actor = None
    if objeto is not None and objeto_id is None:
        objeto_id = str(objeto.pk)
    return EventoAuditoria.objects.create(
        actor=actor,
        accion=accion,
        recurso=recurso,
        objeto_id=str(objeto_id) if objeto_id is not None else None,
        detalles=detalles or {},
    )
