from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("gym", "0003_alter_registrocomida_foto_url")]

    operations = [
        migrations.CreateModel(
            name="Sesion",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("creada_at", models.DateTimeField(auto_now_add=True)),
                ("expira_at", models.DateTimeField()),
                (
                    "usuario",
                    models.ForeignKey(
                        db_column="usuario_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sesiones",
                        to="gym.usuario",
                    ),
                ),
            ],
            options={"db_table": "sesiones"},
        ),
        migrations.AddIndex(
            model_name="sesion",
            index=models.Index(fields=["usuario", "expira_at"], name="idx_sesion_usuario_expira"),
        ),
    ]
