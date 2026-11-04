# Generated manually because this project keeps migrations under source control.

import django.db.models.deletion
from django.db import migrations, models


def crear_recursos_y_asignaciones(apps, schema_editor):
    """Convierte los nombres de recurso ya presentes en permisos en catálogo.

    La migración es idempotente para que también funcione sobre instalaciones
    que hayan importado datos antes de llegar a esta versión.
    """

    Permiso = apps.get_model("gym", "Permiso")
    Recurso = apps.get_model("gym", "Recurso")
    RolPermiso = apps.get_model("gym", "RolPermiso")
    RolRecurso = apps.get_model("gym", "RolRecurso")

    recursos = {}
    for nombre in Permiso.objects.values_list("recurso", flat=True).distinct():
        nombre = (nombre or "").strip().lower()
        if not nombre:
            continue
        recurso, _ = Recurso.objects.get_or_create(nombre=nombre)
        recursos[nombre] = recurso.pk

    for permiso_id, nombre in Permiso.objects.values_list("id", "recurso").iterator():
        recurso_id = recursos.get((nombre or "").strip().lower())
        if recurso_id:
            Permiso.objects.filter(pk=permiso_id).update(recurso_catalogo_id=recurso_id)

    for rol_id, recurso_nombre in (
        RolPermiso.objects.select_related("permiso")
        .values_list("rol_id", "permiso__recurso")
        .iterator()
    ):
        recurso_id = recursos.get((recurso_nombre or "").strip().lower())
        if recurso_id:
            RolRecurso.objects.get_or_create(rol_id=rol_id, recurso_id=recurso_id)


class Migration(migrations.Migration):

    dependencies = [
        ("gym", "0013_cliente_rutina_entrenamiento"),
    ]

    operations = [
        migrations.CreateModel(
            name="Recurso",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("nombre", models.CharField(max_length=50, unique=True)),
                ("descripcion", models.CharField(blank=True, max_length=255, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "recursos",
                "ordering": ["nombre"],
                "indexes": [models.Index(fields=["is_active"], name="idx_recursos_active")],
            },
        ),
        migrations.AddField(
            model_name="permiso",
            name="recurso_catalogo",
            field=models.ForeignKey(
                blank=True,
                db_column="recurso_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="permisos",
                to="gym.recurso",
            ),
        ),
        migrations.CreateModel(
            name="RolRecurso",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "recurso",
                    models.ForeignKey(
                        db_column="recurso_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="roles_asignados",
                        to="gym.recurso",
                    ),
                ),
                (
                    "rol",
                    models.ForeignKey(
                        db_column="rol_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recursos_asignados",
                        to="gym.rol",
                    ),
                ),
            ],
            options={
                "db_table": "rol_has_recurso",
                "ordering": ["rol", "recurso"],
                "indexes": [
                    models.Index(fields=["rol"], name="idx_rolrecurso_rol"),
                    models.Index(fields=["recurso"], name="idx_rolrecurso_recurso"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("rol", "recurso"), name="uq_rol_recurso")
                ],
            },
        ),
        migrations.AddField(
            model_name="rol",
            name="recursos",
            field=models.ManyToManyField(
                blank=True,
                related_name="roles",
                through="gym.RolRecurso",
                to="gym.recurso",
            ),
        ),
        migrations.RunPython(crear_recursos_y_asignaciones, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="permiso",
            name="recurso_catalogo",
            field=models.ForeignKey(
                blank=True,
                db_column="recurso_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="permisos",
                to="gym.recurso",
            ),
        ),
    ]
