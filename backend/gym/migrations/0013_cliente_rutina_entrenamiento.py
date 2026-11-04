from django.db import migrations


CODIGO = "planes-entrenamiento-ejercicios:view"


def conceder_rutina_al_cliente(apps, schema_editor):
    """Permite al cliente consultar los ejercicios de su plan de entrenamiento."""

    Permiso = apps.get_model("gym", "Permiso")
    Rol = apps.get_model("gym", "Rol")
    RolPermiso = apps.get_model("gym", "RolPermiso")

    permiso, _ = Permiso.objects.update_or_create(
        codigo=CODIGO,
        defaults={
            "recurso": "planes-entrenamiento-ejercicios",
            "accion": "view",
            "descripcion": "Ver planes-entrenamiento-ejercicios",
            "is_active": True,
        },
    )
    rol = Rol.objects.filter(nombre="cliente").first()
    if rol is None:
        return
    RolPermiso.objects.get_or_create(rol_id=rol.pk, permiso_id=permiso.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("gym", "0012_plan_entrenamiento_dia_semana"),
    ]

    operations = [
        migrations.RunPython(conceder_rutina_al_cliente, migrations.RunPython.noop),
    ]
