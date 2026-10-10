from django.db import migrations


ROLES_INICIALES = (
    ("cliente", "Usuario que recibe servicios y registra su actividad física"),
    ("entrenador", "Profesional que diseña y supervisa entrenamientos"),
    ("terapeuta", "Profesional que acompaña procesos terapéuticos o de rehabilitación"),
    ("recepcionista", "Personal que gestiona recepción y asistencia operativa"),
    ("administrador", "Gestiona la configuración y operación general del sistema"),
)


def crear_roles(apps, schema_editor):
    Rol = apps.get_model("gym", "Rol")
    for nombre, descripcion in ROLES_INICIALES:
        Rol.objects.update_or_create(nombre=nombre, defaults={"descripcion": descripcion, "is_active": True})


class Migration(migrations.Migration):
    dependencies = [("gym", "0001_initial")]

    operations = [migrations.RunPython(crear_roles, migrations.RunPython.noop)]
