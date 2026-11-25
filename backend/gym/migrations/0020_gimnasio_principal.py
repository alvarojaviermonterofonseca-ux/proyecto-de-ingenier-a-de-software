"""Asigna los datos existentes al "Gimnasio principal".

Hasta esta versión el proyecto atendía un único gimnasio implícito. Esta
migración crea ese gimnasio de forma explícita y le asigna todos los registros
que ya existían, de modo que nada se pierde al pasar a multi-gimnasio.

La matriz de permisos pasa a ser por gimnasio: cada fila existente se copia al
gimnasio principal y las de los roles del sistema se conservan, sin gimnasio,
como plantilla para los gimnasios que se creen después.
"""

from django.db import migrations

ROLES_SISTEMA = ("cliente", "entrenador", "terapeuta", "recepcionista", "administrador")


def crear_gimnasio_principal(apps, schema_editor):
    from gym.models import CATEGORIAS_GASTO_POR_DEFECTO, METODOS_PAGO_POR_DEFECTO

    Gimnasio = apps.get_model("gym", "Gimnasio")
    Rol = apps.get_model("gym", "Rol")
    RolPermiso = apps.get_model("gym", "RolPermiso")
    RolRecurso = apps.get_model("gym", "RolRecurso")
    MetodoPago = apps.get_model("gym", "MetodoPago")
    CategoriaGasto = apps.get_model("gym", "CategoriaGasto")

    principal = Gimnasio.objects.order_by("pk").first()
    if principal is None:
        principal = Gimnasio.objects.create(nombre="Gimnasio principal", codigo="principal")

    for modelo in (
        "Usuario",
        "Ejercicio",
        "MetodoPago",
        "CategoriaGasto",
        "Pago",
        "Gasto",
        "Membresia",
        "Alerta",
        "Asistencia",
    ):
        apps.get_model("gym", modelo).objects.filter(gimnasio__isnull=True).update(
            gimnasio=principal
        )

    # Los roles personalizados que ya existían eran del único gimnasio.
    Rol.objects.filter(gimnasio__isnull=True).exclude(nombre__in=ROLES_SISTEMA).update(
        gimnasio=principal
    )

    for Modelo, campo in ((RolPermiso, "permiso_id"), (RolRecurso, "recurso_id")):
        plantilla = Modelo.objects.filter(gimnasio__isnull=True)
        Modelo.objects.bulk_create(
            [
                Modelo(gimnasio=principal, rol_id=rol_id, **{campo: valor})
                for rol_id, valor in plantilla.values_list("rol_id", campo)
            ],
            ignore_conflicts=True,
        )
        # La plantilla solo conserva los roles del sistema.
        plantilla.exclude(rol__nombre__in=ROLES_SISTEMA).delete()

    if not MetodoPago.objects.filter(gimnasio=principal).exists():
        for datos in METODOS_PAGO_POR_DEFECTO:
            MetodoPago.objects.create(gimnasio=principal, **datos)
    if not CategoriaGasto.objects.filter(gimnasio=principal).exists():
        for datos in CATEGORIAS_GASTO_POR_DEFECTO:
            CategoriaGasto.objects.create(gimnasio=principal, **datos)


class Migration(migrations.Migration):

    dependencies = [
        ("gym", "0019_gimnasios_estructura"),
    ]

    operations = [
        migrations.RunPython(crear_gimnasio_principal, migrations.RunPython.noop),
    ]
