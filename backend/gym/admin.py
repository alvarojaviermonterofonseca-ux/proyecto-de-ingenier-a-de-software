"""Panel de la plataforma (``/admin/``): alta y administración de gimnasios."""

from django.contrib import admin

from .models import Gimnasio


@admin.register(Gimnasio)
class GimnasioAdmin(admin.ModelAdmin):
    """Al crear un gimnasio se siembran sus catálogos y su matriz de permisos.

    El primer administrador se crea con
    ``python backend\\manage.py crear_administrador_gym --gimnasio <codigo> ...``.
    """

    list_display = ("nombre", "codigo", "ciudad", "is_active", "total_usuarios", "created_at")
    list_filter = ("is_active", "ciudad")
    search_fields = ("nombre", "codigo", "nit")
    readonly_fields = ("created_at", "updated_at", "deleted_at")
    fieldsets = (
        (None, {"fields": ("nombre", "codigo", "nit", "is_active")}),
        ("Contacto", {"fields": ("ciudad", "direccion", "telefono", "correo")}),
        (
            "Centro de alertas",
            {
                "fields": (
                    "dias_inactividad_alerta",
                    "limite_gastos_mensual",
                    "porcentaje_caida_ingresos",
                )
            },
        ),
        ("Registro", {"fields": ("created_at", "updated_at", "deleted_at")}),
    )

    @admin.display(description="Usuarios")
    def total_usuarios(self, gimnasio):
        return gimnasio.usuarios.filter(deleted_at__isnull=True).count()

    def has_delete_permission(self, request, obj=None):
        # Un gimnasio con datos no se borra: se desactiva (is_active).
        return False
