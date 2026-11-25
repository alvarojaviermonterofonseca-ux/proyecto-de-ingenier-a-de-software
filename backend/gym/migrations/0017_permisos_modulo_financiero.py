# Generated manually because this project keeps migrations under source control.

from django.db import migrations


RECURSOS = (
    "metodos-pago",
    "categorias-gasto",
    "pagos",
    "gastos",
    "membresias",
    "alertas",
)

ACCIONES = ("view", "create", "edit", "delete", "export")

DESCRIPCION_ACCION = {
    "view": "Ver",
    "create": "Crear",
    "edit": "Editar",
    "delete": "Eliminar",
    "export": "Exportar",
}


def sembrar_permisos_financieros(apps, schema_editor):
    """Registra los recursos financieros en el catálogo RBAC.

    Sin estas filas ``tiene_permiso()`` niega el acceso incluso al
    administrador. Solo se conceden al rol administrador; los demás roles se
    habilitan desde la matriz de permisos. Es idempotente.
    """

    Permiso = apps.get_model("gym", "Permiso")
    Recurso = apps.get_model("gym", "Recurso")
    Rol = apps.get_model("gym", "Rol")
    RolPermiso = apps.get_model("gym", "RolPermiso")
    RolRecurso = apps.get_model("gym", "RolRecurso")

    admin = Rol.objects.filter(nombre="administrador").first()

    for nombre in RECURSOS:
        recurso, _ = Recurso.objects.get_or_create(nombre=nombre)
        if admin is not None:
            RolRecurso.objects.get_or_create(rol_id=admin.pk, recurso_id=recurso.pk)
        for accion in ACCIONES:
            permiso, _ = Permiso.objects.update_or_create(
                codigo=f"{nombre}:{accion}",
                defaults={
                    "recurso": nombre,
                    "recurso_catalogo_id": recurso.pk,
                    "accion": accion,
                    "descripcion": f"{DESCRIPCION_ACCION[accion]} {nombre}",
                    "is_active": True,
                },
            )
            if admin is not None:
                RolPermiso.objects.get_or_create(
                    rol_id=admin.pk, permiso_id=permiso.pk
                )


class Migration(migrations.Migration):

    dependencies = [
        ("gym", "0016_categoriagasto_membresia_metodopago_gasto_pago_and_more"),
    ]

    operations = [
        migrations.RunPython(sembrar_permisos_financieros, migrations.RunPython.noop),
    ]
