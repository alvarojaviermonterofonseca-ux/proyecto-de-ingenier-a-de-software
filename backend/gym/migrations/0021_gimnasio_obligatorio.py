"""Hace obligatorio el gimnasio una vez asignados los datos existentes."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gym", "0020_gimnasio_principal"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usuario",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="usuarios",
                to="gym.gimnasio",
            ),
        ),
        migrations.AlterField(
            model_name="ejercicio",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ejercicios",
                to="gym.gimnasio",
            ),
        ),
        migrations.AlterField(
            model_name="metodopago",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="metodos_pago",
                to="gym.gimnasio",
            ),
        ),
        migrations.AlterField(
            model_name="categoriagasto",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="categorias_gasto",
                to="gym.gimnasio",
            ),
        ),
        migrations.AlterField(
            model_name="pago",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pagos",
                to="gym.gimnasio",
            ),
        ),
        migrations.AlterField(
            model_name="gasto",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="gastos",
                to="gym.gimnasio",
            ),
        ),
        migrations.AlterField(
            model_name="membresia",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="membresias",
                to="gym.gimnasio",
            ),
        ),
        migrations.AlterField(
            model_name="alerta",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="alertas",
                to="gym.gimnasio",
            ),
        ),
        migrations.AlterField(
            model_name="asistencia",
            name="gimnasio",
            field=models.ForeignKey(
                db_column="gimnasio_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="asistencias",
                to="gym.gimnasio",
            ),
        ),
    ]
