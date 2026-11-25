from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from config.env import cargar_env

from .models import (
    Administrador,
    Alerta,
    Asistencia,
    CategoriaGasto,
    Cliente,
    ClienteEntrenador,
    ClienteTerapeuta,
    Comida,
    Ejercicio,
    Entrenador,
    Entrenamiento,
    EventoAuditoria,
    Gasto,
    Gimnasio,
    Membresia,
    MetodoPago,
    Notificacion,
    Pago,
    Permiso,
    PlanAlimentacion,
    PlanEntrenamiento,
    PlanEntrenamientoEjercicio,
    Recurso,
    Recepcionista,
    RegistroComida,
    Rol,
    RolPermiso,
    RolRecurso,
    Sesion,
    Terapeuta,
    Usuario,
    UsuarioRol,
)


def gimnasio_principal():
    """Gimnasio que la migración 0020 crea para los datos existentes."""
    return Gimnasio.objects.get(codigo="principal")


class GymApiTests(APITestCase):
    def test_panel_web_publica_carga_archivos_del_cliente(self):
        respuesta = self.client.get("/panel/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Iniciar sesión")
        self.assertContains(respuesta, 'value="entrenadores"')
        self.assertContains(respuesta, "/static/panel.js")

    def setUp(self):
        """Crea una cuenta de operación para probar rutas ya protegidas."""
        cache.clear()
        rol = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)
        self.operador = Usuario(rol=rol, nombre="Operador", correo="operador@example.com")
        self.operador.set_password("OtraClaveSegura123")
        self.operador.full_clean()
        self.operador.save()

    def autenticar(self):
        token = getattr(self, "_token_operador", None)
        if token:
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            return token
        respuesta = self.client.post(
            "/api/login/",
            {"correo": self.operador.correo, "contrasena": "OtraClaveSegura123"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200)
        self._token_operador = respuesta.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")
        return respuesta.data["token"]

    def autenticar_como(self, correo, contrasena):
        self.client.credentials()
        respuesta = self.client.post(
            "/api/login/",
            {"correo": correo, "contrasena": contrasena},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")
        return respuesta.data["usuario"]

    def crear_cliente(self):
        self.autenticar()
        rol = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        respuesta = self.client.post(
            "/api/usuarios/",
            {
                "rol": rol.pk,
                "nombre": "Ana Gómez",
                "correo": "ana@example.com",
                "contrasena": "UnaClaveSegura123",
                "perfil": {
                    "tipo_documento": "CC",
                    "numero_documento": "123456789",
                    "objetivo": "Mejorar resistencia",
                },
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201)
        return respuesta

    def crear_usuario_con_rol(self, nombre_rol, correo, nombre=None):
        self.autenticar()
        rol = Rol.objects.get(nombre=nombre_rol)
        perfil = {}
        if nombre_rol == Rol.Nombre.CLIENTE:
            perfil = {
                "tipo_documento": "CC",
                "numero_documento": f"DOC-{correo.split('@')[0].upper()}"[:30],
            }
        respuesta = self.client.post(
            "/api/usuarios/",
            {
                "rol": rol.pk,
                "nombre": nombre or correo,
                "correo": correo,
                "contrasena": "UnaClaveSegura123",
                "perfil": perfil,
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return respuesta.data

    def crear_imagen(self, nombre="comida.png", formato="PNG", tamano=(8, 8)):
        buffer = BytesIO()
        Image.new("RGB", tamano, (20, 120, 40)).save(buffer, format=formato)
        return SimpleUploadedFile(
            nombre,
            buffer.getvalue(),
            content_type=f"image/{formato.lower()}",
        )

    def test_resumen_requiere_autenticacion_y_respeta_alcance(self):
        self.assertEqual(self.client.get("/api/resumen/").status_code, 401)

        self.autenticar()
        respuesta = self.client.get("/api/resumen/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["rol_principal"], Rol.Nombre.ADMINISTRADOR)
        self.assertIn("clientes_activos", respuesta.data["metricas"])

        self.crear_cliente()
        self.client.credentials()
        self.autenticar_como("ana@example.com", "UnaClaveSegura123")
        respuesta = self.client.get("/api/resumen/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["rol_principal"], Rol.Nombre.CLIENTE)
        self.assertEqual(respuesta.data["metricas"]["clientes_activos"], 1)
        self.assertEqual(respuesta.data["metricas"]["usuarios_activos"], 1)
        self.assertEqual(respuesta.data["actividad_reciente"], [])

    def test_conteos_por_recurso_coinciden_con_los_listados(self):
        self.assertEqual(self.client.get("/api/conteos/").status_code, 401)

        self.crear_cliente()
        self.autenticar()
        conteos = self.client.get("/api/v1/conteos/").data

        self.assertIn("usuarios", conteos)
        for recurso in ("usuarios", "clientes", "roles"):
            with self.subTest(recurso=recurso):
                listado = self.client.get(f"/api/v1/{recurso}/").data
                self.assertEqual(conteos[recurso], listado["count"])

    def test_conteos_omiten_borrados_y_respetan_permisos(self):
        self.crear_cliente()
        self.autenticar()
        base = self.client.get("/api/v1/conteos/").data["usuarios"]

        extra = Usuario(rol=Rol.objects.get(nombre=Rol.Nombre.CLIENTE), nombre="Borrado", correo="borrado@example.com")
        extra.set_password("UnaClaveSegura123")
        extra.full_clean()
        extra.save()
        self.assertEqual(self.client.get("/api/v1/conteos/").data["usuarios"], base + 1)

        extra.soft_delete()
        self.assertEqual(self.client.get("/api/v1/conteos/").data["usuarios"], base)

        self.client.credentials()
        self.autenticar_como("ana@example.com", "UnaClaveSegura123")
        conteos_cliente = self.client.get("/api/v1/conteos/").data
        self.assertEqual(conteos_cliente["clientes"], 1)
        self.assertEqual(conteos_cliente["entrenamientos"], 0)
        self.assertNotIn("usuarios", conteos_cliente)
        self.assertNotIn("roles", conteos_cliente)
        self.assertNotIn("auditoria", conteos_cliente)

    def test_roles_iniciales_y_rutas_crud_requieren_autenticacion(self):
        self.assertEqual(Rol.objects.count(), 5)
        self.assertEqual(self.client.get("/api/").status_code, 200)
        self.assertEqual(self.client.get("/api/roles/").status_code, 401)

        self.autenticar()
        recursos = (
            "roles",
            "usuarios",
            "clientes",
            "entrenadores",
            "terapeutas",
            "recepcionistas",
            "administradores",
            "asignaciones-cliente-entrenador",
            "clientes-terapeutas",
            "asistencias",
            "entrenamientos",
            "ejercicios",
            "planes-entrenamiento",
            "planes-entrenamiento-ejercicios",
            "planes-alimentacion",
            "comidas",
            "registros-comida",
            "notificaciones",
        )
        for ruta in recursos:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(f"/api/{ruta}/").status_code, 200)

    def test_sesion_de_admin_autoriza_la_api(self):
        admin = get_user_model().objects.create_superuser(
            username="admin_django",
            email="admin-django@example.com",
            password="ClaveAdminSegura123",
        )
        self.assertTrue(self.client.login(username=admin.username, password="ClaveAdminSegura123"))

        self.assertEqual(self.client.get("/api/usuarios/").status_code, 200)
        respuesta = self.client.get("/api/me/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data["es_administrador"])

    def test_comando_sembrar_datos_demo_crea_perfiles_y_relaciones(self):
        call_command("sembrar_datos_demo", cantidad=5, verbosity=0)

        self.assertEqual(Usuario.objects.filter(correo__startswith="demo.usuario").count(), 5)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Entrenador.objects.count(), 1)
        self.assertEqual(Terapeuta.objects.count(), 1)
        self.assertEqual(Recepcionista.objects.count(), 1)
        self.assertEqual(Administrador.objects.count(), 1)
        self.assertEqual(ClienteEntrenador.objects.count(), 1)
        self.assertEqual(ClienteTerapeuta.objects.count(), 1)
        self.assertEqual(Asistencia.objects.count(), 1)
        self.assertEqual(Entrenamiento.objects.count(), 1)
        self.assertEqual(Ejercicio.objects.count(), 2)
        self.assertEqual(PlanEntrenamiento.objects.count(), 1)
        self.assertEqual(PlanEntrenamientoEjercicio.objects.count(), 2)
        self.assertEqual(PlanAlimentacion.objects.count(), 1)
        self.assertEqual(Comida.objects.count(), 4)
        self.assertEqual(RegistroComida.objects.count(), 1)
        self.assertEqual(Notificacion.objects.count(), 5)

    def test_comando_sembrar_datos_demo_alcanza_objetivo_por_rol(self):
        call_command("sembrar_datos_demo", cantidad=5, verbosity=0)
        call_command("sembrar_datos_demo", por_rol=2, verbosity=0)

        for nombre_rol, _ in Rol.Nombre.choices:
            with self.subTest(rol=nombre_rol):
                self.assertEqual(
                    Usuario.objects.filter(correo__startswith="demo.usuario", rol__nombre=nombre_rol).count(),
                    2,
                )

    def test_alta_usuario_crea_perfil_y_no_expone_hash(self):
        respuesta = self.crear_cliente()
        self.assertNotIn("contrasena", respuesta.data)
        self.assertNotIn("contrasena_hash", respuesta.data)
        self.assertEqual(respuesta.data["perfil_detalle"]["objetivo"], "Mejorar resistencia")

        usuario = Usuario.objects.get(correo="ana@example.com")
        self.assertTrue(usuario.check_password("UnaClaveSegura123"))
        self.assertTrue(usuario.contrasena_hash.startswith("argon2"))
        self.assertTrue(Cliente.objects.filter(pk=usuario.pk).exists())

    def test_contrasena_se_valida_con_los_validadores_de_django(self):
        self.autenticar()
        rol = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        respuesta = self.client.post(
            "/api/usuarios/",
            {
                "rol": rol.pk,
                "nombre": "Contraseña Débil",
                "correo": "debil@example.com",
                "contrasena": "12345678",
                "perfil": {"tipo_documento": "CC", "numero_documento": "DEBIL-1"},
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("contrasena", respuesta.data["error"]["detalles"])
        self.assertFalse(Usuario.objects.filter(correo="debil@example.com").exists())

    def test_perfil_tiene_contrato_explicito_por_rol(self):
        self.autenticar()
        rol = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        def alta(correo, perfil):
            return self.client.post(
                "/api/usuarios/",
                {
                    "rol": rol.pk,
                    "nombre": "Perfil Contrato",
                    "correo": correo,
                    "contrasena": "UnaClaveSegura123",
                    "perfil": perfil,
                },
                format="json",
            )

        desconocido = alta(
            "perfil.desconocido@example.com",
            {"tipo_documento": "CC", "numero_documento": "DESC-1", "campo_inventado": "x"},
        )
        self.assertEqual(desconocido.status_code, 400)
        self.assertIn("campo_inventado", str(desconocido.data["error"]["detalles"]["perfil"]))

        ajeno = alta(
            "perfil.ajeno@example.com",
            {
                "tipo_documento": "CC",
                "numero_documento": "AJENO-1",
                "licencia_profesional": "LIC-1",
            },
        )
        self.assertEqual(ajeno.status_code, 400)
        self.assertIn("licencia_profesional", str(ajeno.data["error"]["detalles"]["perfil"]))

    def test_no_administrador_no_puede_cambiar_rol_estado_ni_asignaciones(self):
        self.autenticar()
        rol_gestor = Rol.objects.create(gimnasio=gimnasio_principal(), nombre="gestor-usuarios")
        for codigo in ("usuarios:view", "usuarios:create", "usuarios:edit"):
            RolPermiso.objects.create(
                gimnasio=gimnasio_principal(),
                rol=rol_gestor, permiso=Permiso.objects.get(codigo=codigo)
            )

        objetivo = Usuario(rol=rol_gestor, nombre="Objetivo", correo="objetivo@example.com")
        objetivo.set_password("UnaClaveSegura123")
        objetivo.save()
        gestor = Usuario(rol=rol_gestor, nombre="Gestor", correo="gestor@example.com")
        gestor.set_password("UnaClaveSegura123")
        gestor.save()

        self.autenticar_como("gestor@example.com", "UnaClaveSegura123")
        cliente_role = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        entrenador_role = Rol.objects.get(nombre=Rol.Nombre.ENTRENADOR)

        casos = (
            ({"is_active": False}, "is_active"),
            ({"rol": cliente_role.pk}, "rol"),
            ({"roles_asignados": [entrenador_role.pk]}, "roles_asignados"),
        )
        for datos, campo in casos:
            with self.subTest(campo=campo):
                respuesta = self.client.patch(
                    f"/api/usuarios/{objetivo.pk}/", datos, format="json"
                )
                self.assertEqual(respuesta.status_code, 404, respuesta.data)

        roles_put = self.client.put(
            f"/api/usuarios/{objetivo.pk}/roles/",
            {"roles": [cliente_role.pk]},
            format="json",
        )
        self.assertEqual(roles_put.status_code, 404)

        ajeno = self.client.patch(
            f"/api/usuarios/{objetivo.pk}/",
            {"nombre": "Objetivo Actualizado"},
            format="json",
        )
        self.assertEqual(ajeno.status_code, 404, ajeno.data)

        permitido = self.client.patch(
            f"/api/usuarios/{gestor.pk}/",
            {"nombre": "Gestor Actualizado"},
            format="json",
        )
        self.assertEqual(permitido.status_code, 200, permitido.data)
        self.assertEqual(permitido.data["nombre"], "Gestor Actualizado")

    def test_cliente_no_puede_desactivar_su_propia_cuenta(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.estado.propio@example.com"
        )
        rol_gestor = Rol.objects.create(gimnasio=gimnasio_principal(), nombre="gestor-estado-propio")
        for codigo in ("usuarios:view", "usuarios:edit"):
            RolPermiso.objects.create(
                gimnasio=gimnasio_principal(),
                rol=rol_gestor, permiso=Permiso.objects.get(codigo=codigo)
            )
        UsuarioRol.objects.create(
            usuario_id=cliente["id"], rol=rol_gestor, activo=True
        )

        self.autenticar_como(
            "cliente.estado.propio@example.com", "UnaClaveSegura123"
        )
        respuesta = self.client.patch(
            f"/api/usuarios/{cliente['id']}/",
            {"is_active": False},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("is_active", respuesta.data["error"]["detalles"])
        self.assertTrue(Usuario.objects.get(pk=cliente["id"]).is_active)

    def test_contrasena_ajena_requiere_administrador_y_revoca_sesiones(self):
        rol_gestor = Rol.objects.create(gimnasio=gimnasio_principal(), nombre="gestor-contrasenas")
        for codigo in ("usuarios:view", "usuarios:edit"):
            RolPermiso.objects.create(
                gimnasio=gimnasio_principal(),
                rol=rol_gestor, permiso=Permiso.objects.get(codigo=codigo)
            )

        objetivo = Usuario(
            rol=rol_gestor, nombre="Objetivo Clave", correo="objetivo.clave@example.com"
        )
        objetivo.set_password("UnaClaveSegura123")
        objetivo.save()
        gestor = Usuario(
            rol=rol_gestor, nombre="Gestor Clave", correo="gestor.clave@example.com"
        )
        gestor.set_password("UnaClaveSegura123")
        gestor.save()

        self.autenticar_como("gestor.clave@example.com", "UnaClaveSegura123")
        _token, _sesion = Sesion.crear_para_usuario(objetivo)

        ajena = self.client.patch(
            f"/api/usuarios/{objetivo.pk}/",
            {"contrasena": "NuevaClaveAjena123"},
            format="json",
        )
        self.assertEqual(ajena.status_code, 404, ajena.data)
        objetivo.refresh_from_db()
        self.assertTrue(objetivo.check_password("UnaClaveSegura123"))
        self.assertEqual(Sesion.objects.filter(usuario=objetivo).count(), 1)

        propia = self.client.patch(
            f"/api/usuarios/{gestor.pk}/",
            {"contrasena": "MiNuevaClave123"},
            format="json",
        )
        self.assertEqual(propia.status_code, 200, propia.data)
        gestor.refresh_from_db()
        self.assertTrue(gestor.check_password("MiNuevaClave123"))
        self.assertFalse(Sesion.objects.filter(usuario=gestor).exists())

        self.autenticar()
        Sesion.crear_para_usuario(objetivo)
        admin = self.client.patch(
            f"/api/usuarios/{objetivo.pk}/",
            {"contrasena": "ClaveAdminSegura123"},
            format="json",
        )
        self.assertEqual(admin.status_code, 200, admin.data)
        objetivo.refresh_from_db()
        self.assertTrue(objetivo.check_password("ClaveAdminSegura123"))
        self.assertFalse(Sesion.objects.filter(usuario=objetivo).exists())

    def test_desactivar_usuario_revoca_sus_sesiones(self):
        self.autenticar()
        usuario = self.crear_usuario_con_rol(
            Rol.Nombre.RECEPCIONISTA, "recepcion.sesiones@example.com"
        )
        Sesion.crear_para_usuario(Usuario.objects.get(pk=usuario["id"]))

        respuesta = self.client.patch(
            f"/api/usuarios/{usuario['id']}/", {"is_active": False}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertFalse(
            Sesion.objects.filter(usuario_id=usuario["id"]).exists()
        )

    def test_perfil_anidado_valida_los_tipos_del_rol_antes_de_crear(self):
        self.autenticar()
        rol = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        respuesta = self.client.post(
            "/api/usuarios/",
            {
                "rol": rol.pk,
                "nombre": "Perfil Inválido",
                "correo": "perfil.invalido@example.com",
                "contrasena": "UnaClaveSegura123",
                "perfil": {
                    "tipo_documento": "CC",
                    "numero_documento": "INVALIDO-1",
                    "peso_kg": "no-es-numero",
                },
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400, respuesta.data)
        self.assertIn("peso_kg", str(respuesta.data["error"]["detalles"]["perfil"]))
        self.assertFalse(
            Usuario.objects.filter(correo="perfil.invalido@example.com").exists()
        )

    def test_perfil_ignora_reasignacion_de_usuario_y_protege_estado(self):
        cliente_a = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.perfil.a@example.com"
        )
        cliente_b = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.perfil.b@example.com"
        )
        self.crear_usuario_con_rol(
            Rol.Nombre.RECEPCIONISTA, "recepcion.perfil@example.com"
        )
        self.autenticar_como("recepcion.perfil@example.com", "UnaClaveSegura123")
        ruta = f"/api/clientes/{cliente_a['id']}/"

        reasignar = self.client.patch(
            ruta, {"usuario": cliente_b["id"]}, format="json"
        )
        self.assertEqual(reasignar.status_code, 200, reasignar.data)
        self.assertEqual(reasignar.data["usuario"], cliente_a["id"])
        self.assertEqual(
            Cliente.objects.get(pk=cliente_a["id"]).usuario_id, cliente_a["id"]
        )

        desactivar = self.client.patch(ruta, {"is_active": False}, format="json")
        self.assertEqual(desactivar.status_code, 400, desactivar.data)
        self.assertIn("is_active", desactivar.data["error"]["detalles"])

        permitido = self.client.patch(ruta, {"objetivo": "Resistencia"}, format="json")
        self.assertEqual(permitido.status_code, 200, permitido.data)
        self.assertNotIn("objetivo", permitido.data)
        self.assertIsNone(Cliente.objects.get(pk=cliente_a["id"]).objetivo)

        self.autenticar()
        reasignar_admin = self.client.patch(
            ruta, {"usuario": cliente_b["id"]}, format="json"
        )
        self.assertEqual(reasignar_admin.status_code, 200, reasignar_admin.data)
        self.assertEqual(reasignar_admin.data["usuario"], cliente_a["id"])

        clinico_admin = self.client.patch(
            ruta, {"objetivo": "Resistencia"}, format="json"
        )
        self.assertEqual(clinico_admin.status_code, 200, clinico_admin.data)
        self.assertEqual(clinico_admin.data["objetivo"], "Resistencia")

    def test_listado_usuarios_precarga_perfiles(self):
        for indice in range(3):
            self.crear_usuario_con_rol(
                Rol.Nombre.CLIENTE, f"cliente.n1.{indice}@example.com"
            )
        self.autenticar()

        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.client.get("/api/usuarios/")

        self.assertEqual(respuesta.status_code, 200)
        tablas_perfil = ("cliente", "entrenador", "terapeuta", "recepcionista", "administrador")
        consultas_perfil = [
            consulta["sql"]
            for consulta in consultas.captured_queries
            if any(f'FROM "{tabla}"' in consulta["sql"] for tabla in tablas_perfil)
        ]
        self.assertEqual(consultas_perfil, [])

        item = respuesta.data["results"][0]
        self.assertIn("rol_nombre", item)
        self.assertIn("roles_efectivos", item)
        self.assertIn("perfil_detalle", item)
        self.assertNotIn("roles_detalle", item)
        self.assertNotIn("permisos", item)
        self.assertNotIn("contrasena_hash", item)
        self.assertNotIn("deleted_at", item)

    def test_entrenamiento_requiere_entrenador_asignado_al_cliente(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.entrenamiento@example.com"
        )
        entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.entrenamiento@example.com"
        )
        datos = {
            "cliente": cliente["id"],
            "entrenador": entrenador["id"],
            "inicio_at": "2026-03-01T10:00:00-05:00",
            "fin_at": "2026-03-01T11:00:00-05:00",
        }

        sin_asignacion = self.client.post(
            "/api/entrenamientos/", datos, format="json"
        )
        self.assertEqual(sin_asignacion.status_code, 400)
        self.assertIn("entrenador", sin_asignacion.data["error"]["detalles"])

        asignacion = self.client.post(
            "/api/asignaciones-cliente-entrenador/",
            {
                "cliente": cliente["id"],
                "entrenador": entrenador["id"],
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-12-31",
                "activo": True,
            },
            format="json",
        )
        self.assertEqual(asignacion.status_code, 201, asignacion.data)
        self.assertEqual(
            self.client.post("/api/entrenamientos/", datos, format="json").status_code,
            201,
        )

    def test_login_valido_devuelve_usuario_sin_exponer_contrasena(self):
        self.crear_cliente()

        respuesta = self.client.post(
            "/api/login/",
            {"correo": "ANA@example.com", "contrasena": "UnaClaveSegura123"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data["token"])
        self.assertEqual(respuesta.data["tipo_token"], "Bearer")
        self.assertIn("expira_at", respuesta.data)
        self.assertEqual(respuesta.data["usuario"]["correo"], "ana@example.com")
        self.assertNotIn("contrasena", respuesta.data["usuario"])
        self.assertNotIn("contrasena_hash", respuesta.data["usuario"])

    def test_login_invalido_devuelve_error(self):
        self.crear_cliente()

        respuesta = self.client.post(
            "/api/login/",
            {"correo": "ana@example.com", "contrasena": "incorrecta"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 401)

    def test_registro_publico_crea_cliente_y_abre_sesion(self):
        respuesta = self.client.post(
            "/api/v1/registro/",
            {
                "nombre": "  Laura Pérez  ",
                "correo": "LAURA@Example.com",
                "contrasena": "ClaveSegura123",
                "telefono": "3001234567",
                "objetivo": "Ganar fuerza",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertTrue(respuesta.data["token"])
        self.assertEqual(respuesta.data["tipo_token"], "Bearer")
        self.assertIn("expira_at", respuesta.data)
        self.assertEqual(respuesta.data["usuario"]["correo"], "laura@example.com")
        self.assertEqual(
            respuesta.data["usuario"]["rol_detalle"]["nombre"],
            Rol.Nombre.CLIENTE,
        )
        self.assertNotIn("contrasena", respuesta.data["usuario"])
        self.assertNotIn("contrasena_hash", respuesta.data["usuario"])

        usuario = Usuario.objects.get(correo="laura@example.com")
        self.assertEqual(usuario.nombre, "Laura Pérez")
        self.assertEqual(usuario.rol.nombre, Rol.Nombre.CLIENTE)
        self.assertTrue(usuario.is_active)
        self.assertTrue(usuario.check_password("ClaveSegura123"))
        self.assertTrue(usuario.contrasena_hash.startswith("argon2"))
        self.assertTrue(
            Cliente.objects.filter(
                pk=usuario.pk, objetivo="Ganar fuerza"
            ).exists()
        )

        perfil = self.client.get(
            "/api/v1/me/",
            HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}",
        )
        self.assertEqual(perfil.status_code, 200)
        self.assertEqual(perfil.data["correo"], "laura@example.com")

    def test_registro_publico_ignora_rol_y_estado_enviados(self):
        rol_admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)

        respuesta = self.client.post(
            "/api/v1/registro/",
            {
                "nombre": "Intruso",
                "correo": "intruso@example.com",
                "contrasena": "ClaveSegura123",
                "rol": rol_admin.pk,
                "roles_asignados": [rol_admin.pk],
                "is_active": False,
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        usuario = Usuario.objects.get(correo="intruso@example.com")
        self.assertEqual(usuario.rol.nombre, Rol.Nombre.CLIENTE)
        self.assertTrue(usuario.is_active)
        self.assertFalse(
            usuario.asignaciones_usuarios.filter(rol=rol_admin).exists()
        )

    def test_registro_publico_rechaza_correo_duplicado(self):
        self.crear_cliente()
        self.client.credentials()

        respuesta = self.client.post(
            "/api/v1/registro/",
            {
                "nombre": "Ana Duplicada",
                "correo": "ANA@example.com",
                "contrasena": "OtraClaveSegura123",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400, respuesta.data)
        self.assertIn("correo", respuesta.data["error"]["detalles"])
        self.assertEqual(
            Usuario.objects.filter(correo="ana@example.com").count(), 1
        )

    def test_registro_publico_valida_contrasena(self):
        respuesta = self.client.post(
            "/api/v1/registro/",
            {
                "nombre": "Clave Débil",
                "correo": "debil@example.com",
                "contrasena": "12345678",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400, respuesta.data)
        self.assertIn("contrasena", respuesta.data["error"]["detalles"])
        self.assertFalse(Usuario.objects.filter(correo="debil@example.com").exists())

    def test_token_permite_consultar_perfil_y_logout_lo_revoca(self):
        token = self.autenticar()

        respuesta = self.client.get("/api/me/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["correo"], self.operador.correo)

        respuesta = self.client.post("/api/logout/", format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["mensaje"], "Sesión cerrada correctamente.")

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/roles/").status_code, 401)

    def test_fechas_invalidas_devuelven_error_json(self):
        respuesta = self.crear_cliente()
        respuesta = self.client.post(
            "/api/asistencias/",
            {
                "cliente": respuesta.data["id"],
                "entrada_at": "2026-10-10T10:00:00-05:00",
                "salida_at": "2026-10-10T09:00:00-05:00",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data["error"]["codigo"], 400)

    def test_migracion_siembra_permisos_y_politicas_por_rol(self):
        self.assertEqual(Permiso.objects.count(), 125)
        admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)
        principal = gimnasio_principal()
        # La matriz existe dos veces: como plantilla (sin gimnasio) para los
        # gimnasios nuevos y como matriz efectiva del gimnasio principal.
        for gimnasio in (None, principal):
            with self.subTest(gimnasio=gimnasio):
                self.assertEqual(
                    RolPermiso.objects.filter(rol=admin, gimnasio=gimnasio).count(), 125
                )
                self.assertEqual(
                    RolRecurso.objects.filter(rol=admin, gimnasio=gimnasio).count(),
                    Recurso.objects.count(),
                )
        self.assertEqual(
            Recurso.objects.count(),
            Permiso.objects.values("recurso").distinct().count(),
        )
        self.autenticar()
        rol_api = self.client.get(f"/api/roles/{admin.pk}/")
        self.assertEqual(rol_api.status_code, 200)
        self.assertIn("usuarios", rol_api.data["recursos"])
        cliente = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        codigos = set(
            RolPermiso.objects.filter(rol=cliente, gimnasio=principal).values_list(
                "permiso__codigo", flat=True
            )
        )
        self.assertIn("clientes:view", codigos)
        self.assertIn("registros-comida:create", codigos)
        self.assertNotIn("usuarios:create", codigos)
        terapeuta = Rol.objects.get(nombre=Rol.Nombre.TERAPEUTA)
        self.assertTrue(
            RolPermiso.objects.filter(
                rol=terapeuta, permiso__codigo="clientes-terapeutas:view", gimnasio=principal
            ).exists()
        )

    def test_me_expone_roles_y_permisos_efectivos(self):
        self.autenticar()

        respuesta = self.client.get("/api/me/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("administrador", [rol["nombre"] for rol in respuesta.data["roles_detalle"]])
        self.assertIn("usuarios:edit", respuesta.data["permisos"])
        self.assertIn("permisos", respuesta.data)
        self.assertIn(
            "administrador",
            [rol["nombre"] for rol in respuesta.data["roles_efectivos"]],
        )
        self.assertIn("usuarios:edit", respuesta.data["permisos_efectivos"])
        self.assertNotIn("contrasena_hash", respuesta.data)

    def test_endpoint_reemplaza_permisos_de_un_rol(self):
        self.autenticar()
        cliente = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        respuesta = self.client.put(
            f"/api/roles/{cliente.pk}/permisos/",
            {"permisos": ["clientes:view", "clientes:export"]},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.data["permisos"]), {"clientes:view", "clientes:export"})
        principal = gimnasio_principal()
        self.assertEqual(RolPermiso.objects.filter(rol=cliente, gimnasio=principal).count(), 2)
        self.assertTrue(
            RolRecurso.objects.filter(
                rol=cliente, recurso__nombre="clientes", gimnasio=principal
            ).exists()
        )
        # La plantilla de los gimnasios nuevos no cambia.
        self.assertGreater(RolPermiso.objects.filter(rol=cliente, gimnasio=None).count(), 2)

    def test_permiso_exige_puente_rol_recurso_activo(self):
        """No basta la concesión por acción: debe existir rol_has_recurso."""
        admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)
        puente = RolRecurso.objects.get(
            rol=admin, recurso__nombre="usuarios", gimnasio=gimnasio_principal()
        )

        self.assertTrue(self.operador.tiene_permiso("usuarios:view"))
        puente.delete()
        self.assertFalse(self.operador.tiene_permiso("usuarios:view"))

    def test_guardar_permisos_conserva_sesiones_y_aplica_al_instante(self):
        """Cambiar permisos no debe expulsar a nadie: se leen en cada petición."""
        self.crear_cliente()
        cliente_usuario = Usuario.objects.get(correo="ana@example.com")
        token_cliente, sesion_cliente = Sesion.crear_para_usuario(cliente_usuario)

        self.autenticar()
        token_admin = self._token_operador
        rol_cliente = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        respuesta = self.client.put(
            f"/api/v1/roles/{rol_cliente.pk}/permisos/",
            {"permisos": ["clientes:view", "clientes:export"]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)

        # La sesión del administrador que guardó sigue viva.
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 200)
        self.assertTrue(
            Sesion.objects.filter(token_hash=Sesion.hash_token(token_admin)).exists()
        )

        # La del cliente también: el cambio se refleja sin volver a iniciar sesión.
        self.assertTrue(Sesion.objects.filter(pk=sesion_cliente.pk).exists())
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_cliente}")
        perfil = self.client.get("/api/v1/me/")
        self.assertEqual(perfil.status_code, 200)
        self.assertIn("clientes:export", perfil.data["permisos_efectivos"])
        # El catálogo de roles sigue reservado a administradores.
        self.assertEqual(self.client.get("/api/v1/roles/").status_code, 403)

    def test_registrar_entrada_marca_la_llegada_del_cliente_autenticado(self):
        self.crear_cliente()
        cliente_usuario = Usuario.objects.get(correo="ana@example.com")
        token, _ = Sesion.crear_para_usuario(cliente_usuario)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertFalse(cliente_usuario.tiene_permiso("asistencias:create"))

        respuesta = self.client.post(
            "/api/v1/asistencias/registrar-entrada/", {}, format="json"
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertTrue(respuesta.data["creado"])
        asistencia = Asistencia.objects.get(cliente_id=cliente_usuario.pk)
        self.assertEqual(asistencia.metodo_entrada, Asistencia.MetodoEntrada.MANUAL)
        self.assertIsNone(asistencia.salida_at)
        self.assertLessEqual(
            abs((asistencia.entrada_at - timezone.now()).total_seconds()), 5
        )

        # Pulsar de nuevo no duplica la entrada abierta.
        repetida = self.client.post(
            "/api/v1/asistencias/registrar-entrada/", {}, format="json"
        )
        self.assertEqual(repetida.status_code, 200, repetida.data)
        self.assertFalse(repetida.data["creado"])
        self.assertEqual(repetida.data["asistencia"]["id"], asistencia.pk)
        self.assertEqual(Asistencia.objects.filter(cliente_id=cliente_usuario.pk).count(), 1)

        # La visita de la semana anterior no cuenta en el acumulado.
        Asistencia.objects.create(
            cliente_id=cliente_usuario.pk,
            entrada_at=timezone.now() - timedelta(days=8),
            salida_at=timezone.now() - timedelta(days=8, hours=-1),
            metodo_entrada=Asistencia.MetodoEntrada.MANUAL,
        )
        resumen = self.client.get("/api/v1/resumen/")
        self.assertEqual(resumen.status_code, 200)
        self.assertTrue(resumen.data["es_cliente"])
        self.assertEqual(resumen.data["metricas"]["visitas_semana"], 1)
        self.assertEqual(len(resumen.data["metricas"]["visitas_semana_dias"]), 7)
        self.assertEqual(
            resumen.data["asistencia_abierta"]["id"],
            asistencia.pk,
        )

    def test_registrar_salida_cierra_la_entrada_y_permite_volver(self):
        self.crear_cliente()
        cliente_usuario = Usuario.objects.get(correo="ana@example.com")
        token, _ = Sesion.crear_para_usuario(cliente_usuario)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        entrada = self.client.post(
            "/api/v1/asistencias/registrar-entrada/", {}, format="json"
        )
        self.assertEqual(entrada.status_code, 201, entrada.data)

        salida = self.client.post(
            "/api/v1/asistencias/registrar-salida/", {}, format="json"
        )
        self.assertEqual(salida.status_code, 200, salida.data)
        asistencia = Asistencia.objects.get(pk=entrada.data["asistencia"]["id"])
        self.assertIsNotNone(asistencia.salida_at)
        self.assertGreaterEqual(asistencia.salida_at, asistencia.entrada_at)

        repetida = self.client.post(
            "/api/v1/asistencias/registrar-salida/", {}, format="json"
        )
        self.assertEqual(repetida.status_code, 400)

        nueva = self.client.post(
            "/api/v1/asistencias/registrar-entrada/", {}, format="json"
        )
        self.assertEqual(nueva.status_code, 201, nueva.data)
        self.assertNotEqual(nueva.data["asistencia"]["id"], asistencia.pk)
        self.assertEqual(
            Asistencia.objects.filter(cliente_id=cliente_usuario.pk).count(), 2
        )

    def test_registrar_entrada_rechaza_cuentas_sin_perfil_de_cliente(self):
        self.autenticar()

        respuesta = self.client.post(
            "/api/v1/asistencias/registrar-entrada/", {}, format="json"
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("cliente", respuesta.data["error"]["detalles"])

    def test_usuario_puede_recibir_roles_adicionales_y_permisos(self):
        self.autenticar()
        cliente_role = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        entrenador_role = Rol.objects.get(nombre=Rol.Nombre.ENTRENADOR)
        respuesta = self.crear_cliente()
        usuario = Usuario.objects.get(pk=respuesta.data["id"])

        rechazo = self.client.patch(
            f"/api/usuarios/{usuario.pk}/",
            {"roles_asignados": [entrenador_role.pk]},
            format="json",
        )
        self.assertEqual(rechazo.status_code, 400)
        self.assertIn("roles_asignados", rechazo.data["error"]["detalles"])

        respuesta = self.client.patch(
            f"/api/usuarios/{usuario.pk}/roles/",
            {"roles": [cliente_role.pk, entrenador_role.pk]},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(UsuarioRol.objects.filter(usuario=usuario, rol=cliente_role, activo=True).exists())
        self.assertTrue(UsuarioRol.objects.filter(usuario=usuario, rol=entrenador_role, activo=True).exists())
        self.assertIn("entrenamientos:create", set(usuario.permisos_efectivos()))

        self.client.patch(
            f"/api/usuarios/{usuario.pk}/roles/",
            {"roles": [cliente_role.pk]},
            format="json",
        )

        self.assertFalse(UsuarioRol.objects.get(usuario=usuario, rol=entrenador_role).activo)
        self.assertNotIn("entrenamientos:create", set(usuario.permisos_efectivos()))

    def test_puede_cambiar_rol_principal_desde_asignacion_de_roles(self):
        self.autenticar()
        respuesta = self.crear_cliente()
        usuario = Usuario.objects.get(pk=respuesta.data["id"])
        cliente_role = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        entrenador_role = Rol.objects.get(nombre=Rol.Nombre.ENTRENADOR)

        cambio = self.client.patch(
            f"/api/usuarios/{usuario.pk}/roles/",
            {"roles": [], "rol_principal": entrenador_role.pk},
            format="json",
        )

        self.assertEqual(cambio.status_code, 200, cambio.data)
        usuario.refresh_from_db()
        self.assertEqual(usuario.rol_id, entrenador_role.pk)
        self.assertFalse(Cliente.objects.filter(pk=usuario.pk).exists())
        self.assertTrue(Entrenador.objects.filter(pk=usuario.pk).exists())
        self.assertTrue(
            UsuarioRol.objects.filter(
                usuario=usuario, rol=entrenador_role, activo=True
            ).exists()
        )
        self.assertFalse(
            UsuarioRol.objects.filter(
                usuario=usuario, rol=cliente_role, activo=True
            ).exists()
        )
        self.assertEqual(cambio.data["rol_detalle"]["nombre"], Rol.Nombre.ENTRENADOR)

    def test_cambio_de_rol_principal_no_borra_perfil_con_datos(self):
        self.autenticar()
        respuesta = self.crear_cliente()
        usuario = Usuario.objects.get(pk=respuesta.data["id"])
        Asistencia.objects.create(
            cliente=usuario.cliente, entrada_at=timezone.now()
        )
        entrenador_role = Rol.objects.get(nombre=Rol.Nombre.ENTRENADOR)

        cambio = self.client.patch(
            f"/api/usuarios/{usuario.pk}/roles/",
            {"roles": [], "rol_principal": entrenador_role.pk},
            format="json",
        )

        self.assertEqual(cambio.status_code, 400, cambio.data)
        self.assertIn("rol_principal", cambio.data["error"]["detalles"])
        usuario.refresh_from_db()
        self.assertEqual(usuario.rol.nombre, Rol.Nombre.CLIENTE)
        self.assertTrue(Cliente.objects.filter(pk=usuario.pk).exists())

    def test_roles_endpoint_protege_al_ultimo_administrador(self):
        self.autenticar()
        cliente_role = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        cambio = self.client.patch(
            f"/api/usuarios/{self.operador.pk}/roles/",
            {"roles": [], "rol_principal": cliente_role.pk},
            format="json",
        )

        self.assertEqual(cambio.status_code, 400, cambio.data)
        self.assertIn("rol_principal", cambio.data["error"]["detalles"])
        self.operador.refresh_from_db()
        self.assertEqual(self.operador.rol.nombre, Rol.Nombre.ADMINISTRADOR)

    def test_solo_administrador_puede_cambiar_rol_principal(self):
        self.autenticar()
        usuario = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "delegado.roles@example.com"
        )
        rol_delegado = self.client.post(
            "/api/roles/",
            {"nombre": "delegado-roles", "descripcion": "Puede asignar roles"},
            format="json",
        )
        self.assertEqual(rol_delegado.status_code, 201, rol_delegado.data)
        rol_id = rol_delegado.data["id"]
        permisos = self.client.put(
            f"/api/roles/{rol_id}/permisos/",
            {"permisos": ["usuarios:edit", "roles:edit"]},
            format="json",
        )
        self.assertEqual(permisos.status_code, 200, permisos.data)
        asignacion = self.client.patch(
            f"/api/usuarios/{usuario['id']}/roles/",
            {"roles": [rol_id]},
            format="json",
        )
        self.assertEqual(asignacion.status_code, 200, asignacion.data)

        self.client.credentials()
        self.autenticar_como("delegado.roles@example.com", "UnaClaveSegura123")
        entrenador_role = Rol.objects.get(nombre=Rol.Nombre.ENTRENADOR)
        cambio = self.client.patch(
            f"/api/usuarios/{usuario['id']}/roles/",
            {"roles": [rol_id], "rol_principal": entrenador_role.pk},
            format="json",
        )

        self.assertEqual(cambio.status_code, 400, cambio.data)
        self.assertIn("rol_principal", cambio.data["error"]["detalles"])
        usuario_db = Usuario.objects.get(pk=usuario["id"])
        self.assertEqual(usuario_db.rol.nombre, Rol.Nombre.CLIENTE)

    def test_administrador_adicional_puede_gestionar_roles_y_permisos(self):
        self.autenticar()
        usuario = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "admin.adicional@example.com"
        )
        rol_admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)

        asignacion = self.client.patch(
            f"/api/usuarios/{usuario['id']}/roles/",
            {"roles": [rol_admin.pk]},
            format="json",
        )
        self.assertEqual(asignacion.status_code, 200, asignacion.data)

        self.client.credentials()
        self.autenticar_como(
            "admin.adicional@example.com", "UnaClaveSegura123"
        )
        perfil = self.client.get("/api/me/")
        self.assertEqual(perfil.status_code, 200)
        self.assertTrue(perfil.data["es_administrador"])
        self.assertIn(
            rol_admin.pk, [rol["id"] for rol in perfil.data["roles_efectivos"]]
        )

        # El rol adicional le concede las mismas funciones administrativas.
        self.assertEqual(self.client.get("/api/roles/").status_code, 200)
        self.assertEqual(self.client.get("/api/permisos/").status_code, 200)

        rol_cliente = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        permisos = self.client.put(
            f"/api/roles/{rol_cliente.pk}/permisos/",
            {"permisos": ["clientes:view", "clientes:export"]},
            format="json",
        )
        self.assertEqual(permisos.status_code, 200, permisos.data)
        self.assertEqual(
            set(permisos.data["permisos"]), {"clientes:view", "clientes:export"}
        )

        nuevo = self.client.post(
            "/api/usuarios/",
            {
                "rol": Rol.objects.get(nombre=Rol.Nombre.RECEPCIONISTA).pk,
                "nombre": "Recepción adicional",
                "correo": "recepcion.adicional@example.com",
                "contrasena": "UnaClaveSegura123",
                "perfil": {},
            },
            format="json",
        )
        self.assertEqual(nuevo.status_code, 201, nuevo.data)

    def test_rol_administrador_y_ultimo_admin_no_pueden_eliminarse(self):
        self.autenticar()
        rol_admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)

        borrado = self.client.delete(
            f"/api/roles/{rol_admin.pk}/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(borrado.status_code, 400, borrado.data)
        rol_admin.refresh_from_db()
        self.assertTrue(rol_admin.is_active)

        # El único administrador tampoco puede desactivarse ni cambiarse de rol.
        desactivar = self.client.patch(
            f"/api/usuarios/{self.operador.pk}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(desactivar.status_code, 400, desactivar.data)

        cambiar_rol = self.client.patch(
            f"/api/usuarios/{self.operador.pk}/",
            {"rol": Rol.objects.get(nombre=Rol.Nombre.CLIENTE).pk},
            format="json",
        )
        self.assertEqual(cambiar_rol.status_code, 400, cambiar_rol.data)

        # Con un segundo administrador, las mismas operaciones sí son posibles.
        segundo = self.crear_usuario_con_rol(
            Rol.Nombre.ADMINISTRADOR, "segundo.admin@example.com"
        )
        self.assertTrue(segundo["is_active"])
        self.assertEqual(
            self.client.patch(
                f"/api/usuarios/{self.operador.pk}/",
                {"is_active": False},
                format="json",
            ).status_code,
            200,
        )

    def test_alcance_de_datos_incluye_roles_adicionales(self):
        mixto = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "mixto.alcance@example.com"
        )
        cliente_ajeno = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "ajeno.alcance@example.com"
        )
        entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.alcance@example.com"
        )
        rol_recepcion = Rol.objects.get(nombre=Rol.Nombre.RECEPCIONISTA)

        # El rol adicional de recepción amplía el alcance sin cambiar el rol
        # principal del usuario (que sigue siendo cliente).
        asignacion = self.client.patch(
            f"/api/usuarios/{mixto['id']}/roles/",
            {"roles": [rol_recepcion.pk]},
            format="json",
        )
        self.assertEqual(asignacion.status_code, 200, asignacion.data)
        usuario_mixto = Usuario.objects.get(pk=mixto["id"])
        self.assertEqual(usuario_mixto.rol.nombre, Rol.Nombre.CLIENTE)
        self.assertIn("usuarios:view", set(usuario_mixto.permisos_efectivos()))

        self.client.credentials()
        self.autenticar_como("mixto.alcance@example.com", "UnaClaveSegura123")

        visibles = self.client.get("/api/usuarios/")
        self.assertEqual(visibles.status_code, 200)
        ids_visibles = {item["id"] for item in visibles.data["results"]}
        self.assertIn(cliente_ajeno["id"], ids_visibles)
        self.assertIn(entrenador["id"], ids_visibles)

        clientes = self.client.get("/api/clientes/")
        self.assertEqual(clientes.status_code, 200)
        ids_clientes = {item["usuario"] for item in clientes.data["results"]}
        self.assertIn(cliente_ajeno["id"], ids_clientes)

    def test_cliente_puede_marcar_sus_notificaciones_como_leidas(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "notificado@example.com"
        )
        creada = self.client.post(
            "/api/notificaciones/",
            {
                "usuario": cliente["id"],
                "tipo": "sistema",
                "titulo": "Aviso",
                "mensaje": "Contenido de prueba",
            },
            format="json",
        )
        self.assertEqual(creada.status_code, 201, creada.data)
        notificacion_id = creada.data["id"]

        self.client.credentials()
        self.autenticar_como("notificado@example.com", "UnaClaveSegura123")
        leida = self.client.post(
            f"/api/notificaciones/{notificacion_id}/leer/", {}, format="json"
        )
        self.assertEqual(leida.status_code, 200, leida.data)
        self.assertIsNotNone(
            Notificacion.objects.get(pk=notificacion_id).leida_at
        )
        todas = self.client.post(
            "/api/notificaciones/marcar-todas/", {}, format="json"
        )
        self.assertEqual(todas.status_code, 200, todas.data)

    def test_exportar_csv_respeta_permiso_y_alcance(self):
        self.crear_cliente()

        self.autenticar()
        exportacion = self.client.get("/api/clientes/exportar/")
        self.assertEqual(exportacion.status_code, 200)
        self.assertIn("text/csv", exportacion["Content-Type"])
        self.assertIn("attachment;", exportacion["Content-Disposition"])
        contenido = exportacion.content.decode("utf-8")
        self.assertIn("ana@example.com", contenido)

        rol_cliente = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        self.client.put(
            f"/api/roles/{rol_cliente.pk}/permisos/",
            {"permisos": ["clientes:view"]},
            format="json",
        )
        self.client.credentials()
        self.autenticar_como("ana@example.com", "UnaClaveSegura123")
        self.assertEqual(self.client.get("/api/clientes/exportar/").status_code, 403)

    def test_plan_de_entrenamiento_se_organiza_por_dias_y_lo_ve_el_cliente(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "rutina@example.com"
        )
        entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.rutina@example.com"
        )
        self.client.post(
            "/api/asignaciones-cliente-entrenador/",
            {
                "cliente": cliente["id"],
                "entrenador": entrenador["id"],
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-12-31",
                "activo": True,
            },
            format="json",
        )
        plan = self.client.post(
            "/api/planes-entrenamiento/",
            {
                "cliente": cliente["id"],
                "entrenador": entrenador["id"],
                "nombre": "Rutina semanal",
                "objetivo": "Fuerza",
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-12-31",
            },
            format="json",
        )
        self.assertEqual(plan.status_code, 201, plan.data)
        plan_id = plan.data["id"]

        press = self.client.post(
            "/api/ejercicios/",
            {"nombre": "Press banca", "grupo_muscular": "Pecho"},
            format="json",
        )
        self.assertEqual(press.status_code, 201, press.data)
        sentadilla = self.client.post(
            "/api/ejercicios/",
            {"nombre": "Sentadilla", "grupo_muscular": "Piernas"},
            format="json",
        )
        self.assertEqual(sentadilla.status_code, 201, sentadilla.data)

        lunes = self.client.post(
            "/api/planes-entrenamiento-ejercicios/",
            {
                "plan": plan_id,
                "ejercicio": press.data["id"],
                "dia_semana": "lunes",
                "orden": 1,
                "series": 4,
                "repeticiones": 10,
            },
            format="json",
        )
        self.assertEqual(lunes.status_code, 201, lunes.data)
        self.assertEqual(lunes.data["dia_semana"], "lunes")

        martes = self.client.post(
            "/api/planes-entrenamiento-ejercicios/",
            {
                "plan": plan_id,
                "ejercicio": sentadilla.data["id"],
                "dia_semana": "martes",
                "orden": 1,
                "series": 3,
                "repeticiones": 12,
            },
            format="json",
        )
        self.assertEqual(martes.status_code, 201, martes.data)

        duplicado = self.client.post(
            "/api/planes-entrenamiento-ejercicios/",
            {
                "plan": plan_id,
                "ejercicio": sentadilla.data["id"],
                "dia_semana": "lunes",
                "orden": 1,
            },
            format="json",
        )
        self.assertEqual(duplicado.status_code, 400, duplicado.data)

        self.client.credentials()
        self.autenticar_como("rutina@example.com", "UnaClaveSegura123")
        rutina = self.client.get(
            "/api/planes-entrenamiento-ejercicios/", {"plan": plan_id}
        )
        self.assertEqual(rutina.status_code, 200, rutina.data)
        dias = [item["dia_semana"] for item in rutina.data["results"]]
        self.assertEqual(dias, ["lunes", "martes"])
        self.assertEqual(
            rutina.data["results"][0]["ejercicio_detalle"]["grupo_muscular"],
            "Pecho",
        )

    def test_rbac_del_servidor_deniega_recursos_no_concedidos(self):
        respuesta = self.crear_cliente()
        self.assertEqual(respuesta.status_code, 201)
        self.client.credentials()

        login = self.client.post(
            "/api/login/",
            {"correo": "ana@example.com", "contrasena": "UnaClaveSegura123"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")

        self.assertEqual(self.client.get("/api/clientes/").status_code, 200)
        self.assertEqual(self.client.get("/api/usuarios/").status_code, 403)
        self.assertEqual(self.client.get("/api/roles/").status_code, 403)
        self.assertEqual(self.client.post("/api/permisos/", {}, format="json").status_code, 403)

    def test_normaliza_correo_username_y_campos_opcionales(self):
        self.autenticar()
        rol = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        respuesta = self.client.post(
            "/api/usuarios/",
            {
                "rol": rol.pk,
                "nombre": "  Ana Normalizada  ",
                "username": "  Ana.User  ",
                "correo": "  Ana@Example.COM  ",
                "contrasena": "UnaClaveSegura123",
                "telefono": "   ",
                "perfil": {
                    "tipo_documento": " cc ",
                    "numero_documento": " 001 ",
                    "objetivo": "   ",
                },
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["correo"], "ana@example.com")
        self.assertEqual(respuesta.data["username"], "ana.user")
        self.assertEqual(respuesta.data["telefono"], None)
        usuario = Usuario.objects.get(pk=respuesta.data["id"])
        cliente = Cliente.objects.get(pk=usuario.pk)
        self.assertEqual(usuario.nombre, "Ana Normalizada")
        self.assertEqual(cliente.tipo_documento, "CC")
        self.assertEqual(cliente.numero_documento, "001")
        self.assertIsNone(cliente.objetivo)

    def test_correo_y_username_son_unicos_sin_importar_mayusculas(self):
        self.autenticar()
        rol = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        datos = {
            "rol": rol.pk,
            "nombre": "Usuario Único",
            "username": "unico.user",
            "correo": "unico@example.com",
            "contrasena": "UnaClaveSegura123",
            "perfil": {"tipo_documento": "CC", "numero_documento": "UNICO-1"},
        }
        self.assertEqual(self.client.post("/api/usuarios/", datos, format="json").status_code, 201)

        por_correo = self.client.post(
            "/api/usuarios/",
            {
                **datos,
                "username": "otro.user",
                "correo": "UNICO@EXAMPLE.COM",
                "perfil": {"tipo_documento": "CC", "numero_documento": "UNICO-2"},
            },
            format="json",
        )
        self.assertEqual(por_correo.status_code, 400)
        self.assertIn("correo", por_correo.data["error"]["detalles"])

        por_username = self.client.post(
            "/api/usuarios/",
            {
                **datos,
                "username": "UNICO.USER",
                "correo": "otro@example.com",
                "perfil": {"tipo_documento": "CC", "numero_documento": "UNICO-3"},
            },
            format="json",
        )
        self.assertEqual(por_username.status_code, 400)
        self.assertIn("username", por_username.data["error"]["detalles"])

    def test_campos_opcionales_vacios_no_ocupan_unicos(self):
        self.autenticar()
        rol = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        for indice in (1, 2):
            respuesta = self.client.post(
                "/api/usuarios/",
                {
                    "rol": rol.pk,
                    "nombre": f"Sin Documento {indice}",
                    "username": "   ",
                    "correo": f"sin-documento-{indice}@example.com",
                    "contrasena": "UnaClaveSegura123",
                    "perfil": {
                        "tipo_documento": "   ",
                        "numero_documento": "   ",
                    },
                },
                format="json",
            )
            self.assertEqual(respuesta.status_code, 201)
            usuario = Usuario.objects.get(pk=respuesta.data["id"])
            cliente = Cliente.objects.get(pk=usuario.pk)
            self.assertIsNone(usuario.username)
            self.assertIsNone(cliente.tipo_documento)
            self.assertIsNone(cliente.numero_documento)

    def test_soft_delete_libera_correo_username_y_documento(self):
        self.autenticar()
        rol = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        datos = {
            "rol": rol.pk,
            "nombre": "Cuenta Reutilizable",
            "username": "cuenta.reutilizable",
            "correo": "reutilizable@example.com",
            "contrasena": "UnaClaveSegura123",
            "perfil": {
                "tipo_documento": "CC",
                "numero_documento": "REUTILIZABLE-1",
            },
        }
        creada = self.client.post("/api/usuarios/", datos, format="json")
        self.assertEqual(creada.status_code, 201)
        usuario_id = creada.data["id"]

        eliminada = self.client.delete(
            f"/api/usuarios/{usuario_id}/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(eliminada.status_code, 204)

        usuario_borrado = Usuario.objects.get(pk=usuario_id)
        cliente_borrado = Cliente.objects.get(pk=usuario_id)
        self.assertIsNotNone(usuario_borrado.deleted_at)
        self.assertNotEqual(usuario_borrado.correo, "reutilizable@example.com")
        self.assertNotEqual(usuario_borrado.username, "cuenta.reutilizable")
        self.assertNotEqual(cliente_borrado.numero_documento, "REUTILIZABLE-1")

        reutilizada = self.client.post(
            "/api/usuarios/",
            {
                **datos,
                "nombre": "Cuenta Nueva",
                "contrasena": "OtraClaveSegura123",
            },
            format="json",
        )
        self.assertEqual(reutilizada.status_code, 201)
        self.assertNotEqual(reutilizada.data["id"], usuario_id)

    def test_cliente_entrenador_impide_activas_y_solapamientos(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.asignacion@example.com"
        )
        entrenador_1 = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.uno@example.com"
        )
        entrenador_2 = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.dos@example.com"
        )
        datos = {
            "cliente": cliente["id"],
            "entrenador": entrenador_1["id"],
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-01-31",
            "activo": True,
        }
        self.assertEqual(
            self.client.post(
                "/api/asignaciones-cliente-entrenador/", datos, format="json"
            ).status_code,
            201,
        )

        otra_activa = self.client.post(
            "/api/asignaciones-cliente-entrenador/",
            {
                **datos,
                "entrenador": entrenador_2["id"],
                "fecha_inicio": "2027-01-01",
                "fecha_fin": "2027-01-31",
            },
            format="json",
        )
        self.assertEqual(otra_activa.status_code, 400)
        self.assertIn("activo", otra_activa.data["error"]["detalles"])

        solapada = self.client.post(
            "/api/asignaciones-cliente-entrenador/",
            {
                **datos,
                "entrenador": entrenador_2["id"],
                "fecha_inicio": "2026-01-15",
                "fecha_fin": "2026-02-15",
                "activo": False,
            },
            format="json",
        )
        self.assertEqual(solapada.status_code, 400)
        self.assertIn("fecha_inicio", solapada.data["error"]["detalles"])

    def test_asignacion_exige_cliente_y_entrenador_activos(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.asignacion.inactiva@example.com"
        )
        entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.asignacion.inactivo@example.com"
        )
        datos = {
            "cliente": cliente["id"],
            "entrenador": entrenador["id"],
            "fecha_inicio": "2026-01-01",
            "activo": True,
        }

        Usuario.objects.filter(pk=entrenador["id"]).update(is_active=False)
        entrenador_inactivo = self.client.post(
            "/api/asignaciones-cliente-entrenador/", datos, format="json"
        )
        self.assertEqual(entrenador_inactivo.status_code, 400)
        self.assertIn(
            "entrenador", entrenador_inactivo.data["error"]["detalles"]
        )

        Usuario.objects.filter(pk=entrenador["id"]).update(is_active=True)
        Usuario.objects.filter(pk=cliente["id"]).update(is_active=False)
        cliente_inactivo = self.client.post(
            "/api/asignaciones-cliente-entrenador/", datos, format="json"
        )
        self.assertEqual(cliente_inactivo.status_code, 400)
        self.assertIn("cliente", cliente_inactivo.data["error"]["detalles"])

    def test_asistencia_impide_dos_abiertas_para_el_mismo_cliente(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.asistencia@example.com"
        )
        datos = {
            "cliente": cliente["id"],
            "entrada_at": "2026-10-10T10:00:00-05:00",
            "metodo_entrada": "qr",
        }
        primera = self.client.post("/api/asistencias/", datos, format="json")
        self.assertEqual(primera.status_code, 201)

        segunda = self.client.post(
            "/api/asistencias/",
            {**datos, "entrada_at": "2026-10-10T11:00:00-05:00"},
            format="json",
        )
        self.assertEqual(segunda.status_code, 400)
        self.assertIn("salida_at", segunda.data["error"]["detalles"])

        salida_invalida = self.client.patch(
            f"/api/asistencias/{primera.data['id']}/",
            {"salida_at": "2026-10-10T09:30:00-05:00"},
            format="json",
        )
        self.assertEqual(salida_invalida.status_code, 400)
        self.assertIn("salida_at", salida_invalida.data["error"]["detalles"])

        cierre = self.client.patch(
            f"/api/asistencias/{primera.data['id']}/",
            {"salida_at": "2026-10-10T11:30:00-05:00"},
            format="json",
        )
        self.assertEqual(cierre.status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/asistencias/",
                {**datos, "entrada_at": "2026-10-10T12:00:00-05:00"},
                format="json",
            ).status_code,
            201,
        )

    def test_planes_requieren_entrenador_asignado_al_cliente(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.plan@example.com"
        )
        entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.plan@example.com"
        )
        otro_entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.otro@example.com"
        )
        plan_entrenamiento = {
            "cliente": cliente["id"],
            "entrenador": entrenador["id"],
            "nombre": "Plan de fuerza",
            "objetivo": "Mejorar fuerza",
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
        }
        sin_asignacion = self.client.post(
            "/api/planes-entrenamiento/", plan_entrenamiento, format="json"
        )
        self.assertEqual(sin_asignacion.status_code, 400)
        self.assertIn("entrenador", sin_asignacion.data["error"]["detalles"])

        self.assertEqual(
            self.client.post(
                "/api/asignaciones-cliente-entrenador/",
                {
                    "cliente": cliente["id"],
                    "entrenador": entrenador["id"],
                    "fecha_inicio": "2026-01-01",
                    "fecha_fin": "2026-12-31",
                    "activo": True,
                },
                format="json",
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.post(
                "/api/planes-entrenamiento/", plan_entrenamiento, format="json"
            ).status_code,
            201,
        )

        plan_alimentacion = {
            "cliente": cliente["id"],
            "responsable": entrenador["id"],
            "nombre": "Plan equilibrado",
            "objetivo": "Mejorar hábitos",
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
        }
        self.assertEqual(
            self.client.post(
                "/api/planes-alimentacion/", plan_alimentacion, format="json"
            ).status_code,
            201,
        )
        sin_responsable = self.client.post(
            "/api/planes-alimentacion/",
            {**plan_alimentacion, "responsable": otro_entrenador["id"]},
            format="json",
        )
        self.assertEqual(sin_responsable.status_code, 400)
        self.assertIn("responsable", sin_responsable.data["error"]["detalles"])

    def test_registro_comida_debe_pertenecer_al_plan_del_cliente(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.comida@example.com"
        )
        otro_cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.comida.otro@example.com"
        )
        entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.comida@example.com"
        )
        for cliente_actual in (cliente, otro_cliente):
            self.assertEqual(
                self.client.post(
                    "/api/asignaciones-cliente-entrenador/",
                    {
                        "cliente": cliente_actual["id"],
                        "entrenador": entrenador["id"],
                        "fecha_inicio": "2026-01-01",
                        "fecha_fin": "2026-12-31",
                        "activo": True,
                    },
                    format="json",
                ).status_code,
                201,
            )

        planes = {}
        comidas = {}
        for clave, cliente_actual in (("propio", cliente), ("ajeno", otro_cliente)):
            plan = self.client.post(
                "/api/planes-alimentacion/",
                {
                    "cliente": cliente_actual["id"],
                    "responsable": entrenador["id"],
                    "nombre": f"Plan {clave}",
                    "objetivo": "Alimentación equilibrada",
                    "fecha_inicio": "2026-01-01",
                    "fecha_fin": "2026-12-31",
                },
                format="json",
            )
            self.assertEqual(plan.status_code, 201, plan.data)
            planes[clave] = plan.data["id"]
            comida = self.client.post(
                "/api/comidas/",
                {
                    "plan_alimentacion": planes[clave],
                    "nombre": f"Comida {clave}",
                    "tipo": "desayuno",
                },
                format="json",
            )
            self.assertEqual(comida.status_code, 201, comida.data)
            comidas[clave] = comida.data["id"]

        invalido = self.client.post(
            "/api/registros-comida/",
            {
                "cliente": cliente["id"],
                "comida": comidas["ajeno"],
            },
            format="json",
        )
        self.assertEqual(invalido.status_code, 400)
        self.assertIn("comida", invalido.data["error"]["detalles"])

        valido = self.client.post(
            "/api/registros-comida/",
            {
                "cliente": cliente["id"],
                "comida": comidas["propio"],
            },
            format="json",
        )
        self.assertEqual(valido.status_code, 201)

        otro_entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "entrenador.comida.otro@example.com"
        )
        revisor_invalido = self.client.post(
            "/api/registros-comida/",
            {
                "cliente": cliente["id"],
                "comida": comidas["propio"],
                "revisado_por": otro_entrenador["id"],
            },
            format="json",
        )
        self.assertEqual(revisor_invalido.status_code, 400)
        self.assertIn(
            "revisado_por", revisor_invalido.data["error"]["detalles"]
        )

        rol_terapeuta = Rol.objects.get(nombre=Rol.Nombre.TERAPEUTA)
        asignacion_permiso = self.client.patch(
            f"/api/usuarios/{entrenador['id']}/roles/",
            {"roles": [rol_terapeuta.pk]},
            format="json",
        )
        self.assertEqual(asignacion_permiso.status_code, 200, asignacion_permiso.data)

        revisor_valido = self.client.post(
            "/api/registros-comida/",
            {
                "cliente": cliente["id"],
                "comida": comidas["propio"],
                "revisado_por": entrenador["id"],
            },
            format="json",
        )
        self.assertEqual(revisor_valido.status_code, 201, revisor_valido.data)

        RolPermiso.objects.filter(
            rol__nombre=Rol.Nombre.TERAPEUTA,
            permiso__codigo="registros-comida:edit",
            gimnasio=gimnasio_principal(),
        ).delete()
        sin_permiso = self.client.post(
            "/api/registros-comida/",
            {
                "cliente": cliente["id"],
                "comida": comidas["propio"],
                "revisado_por": entrenador["id"],
            },
            format="json",
        )
        self.assertEqual(sin_permiso.status_code, 400)
        self.assertIn("revisado_por", sin_permiso.data["error"]["detalles"])

    def test_notificacion_exige_destinatario_activo_y_permitido(self):
        objetivo = self.crear_usuario_con_rol(
            Rol.Nombre.RECEPCIONISTA, "destino.notificacion@example.com"
        )
        datos = {
            "usuario": objetivo["id"],
            "tipo": "sistema",
            "titulo": "Aviso",
            "mensaje": "Contenido de prueba",
        }
        permitida = self.client.post("/api/notificaciones/", datos, format="json")
        self.assertEqual(permitida.status_code, 201, permitida.data)

        Usuario.objects.filter(pk=objetivo["id"]).update(is_active=False)
        inactiva = self.client.post("/api/notificaciones/", datos, format="json")
        self.assertEqual(inactiva.status_code, 400)
        self.assertIn("usuario", inactiva.data["error"]["detalles"])
        Usuario.objects.filter(pk=objetivo["id"]).update(is_active=True)

        rol_emisor = Rol.objects.create(gimnasio=gimnasio_principal(), nombre="emisor-notificaciones")
        for codigo in ("notificaciones:view", "notificaciones:create"):
            RolPermiso.objects.create(
                gimnasio=gimnasio_principal(),
                rol=rol_emisor, permiso=Permiso.objects.get(codigo=codigo)
            )
        emisor = Usuario(
            rol=rol_emisor,
            nombre="Emisor",
            correo="emisor.notificacion@example.com",
        )
        emisor.set_password("UnaClaveSegura123")
        emisor.save()
        self.autenticar_como(
            "emisor.notificacion@example.com", "UnaClaveSegura123"
        )

        ajeno = self.client.post("/api/notificaciones/", datos, format="json")
        self.assertEqual(ajeno.status_code, 400)
        self.assertIn("usuario", ajeno.data["error"]["detalles"])

        propio = self.client.post(
            "/api/notificaciones/",
            {**datos, "usuario": emisor.pk},
            format="json",
        )
        self.assertEqual(propio.status_code, 201, propio.data)

    def test_foto_registro_comida_es_privada_y_requiere_autenticacion(self):
        with TemporaryDirectory() as carpeta_privada:
            with self.settings(PRIVATE_MEDIA_ROOT=carpeta_privada):
                call_command("sembrar_datos_demo", por_rol=1, verbosity=0)
                registro = RegistroComida.objects.get()
                self.autenticar()

                subida = self.client.patch(
                    f"/api/registros-comida/{registro.pk}/",
                    {"foto": self.crear_imagen()},
                    format="multipart",
                )
                self.assertEqual(subida.status_code, 200, subida.data)
                self.assertNotIn("foto", subida.data)

                ruta_foto = f"/api/v1/registros-comida/{registro.pk}/foto/"
                self.assertTrue(subida.data["foto_url"].endswith(ruta_foto))
                self.assertNotIn("/media/", subida.data["foto_url"])

                registro.refresh_from_db()
                self.assertTrue(registro.foto.name.startswith("registros-comida/"))
                self.assertTrue(registro.foto.storage.exists(registro.foto.name))
                self.assertTrue(
                    Path(registro.foto.path).is_relative_to(Path(carpeta_privada))
                )
                self.assertEqual(
                    self.client.get(f"/media/{registro.foto.name}").status_code,
                    404,
                )

                self.client.credentials()
                sin_sesion = self.client.get(
                    ruta_foto, HTTP_ACCEPT="application/json"
                )
                self.assertEqual(sin_sesion.status_code, 401)

                self.autenticar()
                descarga = self.client.get(ruta_foto, HTTP_ACCEPT="image/png")
                self.assertEqual(descarga.status_code, 200)
                self.assertEqual(descarga["Content-Type"], "image/png")
                self.assertEqual(descarga["Cache-Control"], "private, no-store")
                self.assertEqual(descarga["X-Content-Type-Options"], "nosniff")
                self.assertGreater(len(b"".join(descarga.streaming_content)), 0)

    def test_foto_registro_comida_rechaza_urls_y_archivos_invalidos(self):
        with TemporaryDirectory() as carpeta_privada:
            with self.settings(PRIVATE_MEDIA_ROOT=carpeta_privada):
                call_command("sembrar_datos_demo", por_rol=1, verbosity=0)
                registro = RegistroComida.objects.get()
                self.autenticar()
                ruta = f"/api/registros-comida/{registro.pk}/"

                url_externa = self.client.patch(
                    ruta,
                    {"foto_url": "https://example.com/privada.jpg"},
                    format="json",
                )
                self.assertEqual(url_externa.status_code, 400)
                self.assertIn("foto_url", url_externa.data["error"]["detalles"])

                archivo_falso = self.client.patch(
                    ruta,
                    {
                        "foto": SimpleUploadedFile(
                            "comida.jpg",
                            b"esto no es una imagen",
                            content_type="image/jpeg",
                        )
                    },
                    format="multipart",
                )
                self.assertEqual(archivo_falso.status_code, 400)
                self.assertIn("foto", archivo_falso.data["error"]["detalles"])

                with self.settings(FOTO_REGISTRO_MAX_BYTES=100):
                    demasiado_grande = self.client.patch(
                        ruta,
                        {"foto": self.crear_imagen(tamano=(50, 50))},
                        format="multipart",
                    )
                self.assertEqual(demasiado_grande.status_code, 400)
                self.assertIn("foto", demasiado_grande.data["error"]["detalles"])

    def test_cliente_terapeuta_permite_filtrar_clientes_por_terapeuta(self):
        cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.terapia@example.com"
        )
        otro_cliente = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "cliente.sin.terapia@example.com"
        )
        terapeuta = self.crear_usuario_con_rol(
            Rol.Nombre.TERAPEUTA, "terapeuta.filtro@example.com"
        )

        asignacion = self.client.post(
            "/api/clientes-terapeutas/",
            {
                "cliente": cliente["id"],
                "terapeuta": terapeuta["id"],
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-12-31",
                "activo": True,
            },
            format="json",
        )
        self.assertEqual(asignacion.status_code, 201, asignacion.data)

        clientes = self.client.get(f"/api/clientes/?terapeuta={terapeuta['id']}")
        self.assertEqual(clientes.status_code, 200)
        self.assertEqual(
            [item["usuario"] for item in clientes.data["results"]], [cliente["id"]]
        )
        self.assertNotIn(otro_cliente["id"], [item["usuario"] for item in clientes.data["results"]])

        asignaciones = self.client.get(
            f"/api/clientes-terapeutas/?terapeuta={terapeuta['id']}"
        )
        self.assertEqual(asignaciones.status_code, 200)
        self.assertEqual(asignaciones.data["count"], 1)
        self.assertEqual(
            asignaciones.data["results"][0]["cliente"], cliente["id"]
        )

    def test_crear_rol_personalizado_y_usuario_sin_perfil(self):
        self.autenticar()

        rol = self.client.post(
            "/api/roles/",
            {"nombre": "supervisor", "descripcion": "Rol personalizado"},
            format="json",
        )
        self.assertEqual(rol.status_code, 201)

        usuario = self.client.post(
            "/api/usuarios/",
            {
                "rol": rol.data["id"],
                "nombre": "Supervisora",
                "correo": "supervisora@example.com",
                "contrasena": "UnaClaveSegura123",
                "perfil": {},
            },
            format="json",
        )

        self.assertEqual(usuario.status_code, 201)
        self.assertIsNone(usuario.data["perfil_detalle"])
        self.assertTrue(UsuarioRol.objects.filter(usuario_id=usuario.data["id"], rol_id=rol.data["id"]).exists())

    def test_validar_true_mantiene_la_validacion_para_escrituras_criticas(self):
        cliente = Cliente(usuario=self.operador)

        with self.assertRaises(ValidationError):
            cliente.save(validar=True)

    def test_soft_delete_de_perfil_no_ejecuta_full_clean(self):
        call_command("sembrar_datos_demo", por_rol=1, verbosity=0)
        cliente = Cliente.objects.get()
        cliente_id = cliente.pk

        with patch.object(
            Cliente,
            "full_clean",
            side_effect=AssertionError("soft_delete no debe ejecutar full_clean"),
        ):
            cliente.soft_delete()

        self.assertIsNotNone(Cliente.objects.get(pk=cliente_id).deleted_at)

    def test_borrado_cliente_propaga_a_usuario_y_datos_dependientes(self):
        call_command("sembrar_datos_demo", por_rol=1, verbosity=0)
        cliente = Cliente.objects.get()
        cliente_id = cliente.pk
        asignacion_entrenador = ClienteEntrenador.objects.get(cliente_id=cliente_id)
        asignacion_terapeuta = ClienteTerapeuta.objects.get(cliente_id=cliente_id)
        asistencia = Asistencia.objects.get(cliente_id=cliente_id)
        entrenamiento = Entrenamiento.objects.get(cliente_id=cliente_id)
        plan_entrenamiento = PlanEntrenamiento.objects.get(cliente_id=cliente_id)
        plan_alimentacion = PlanAlimentacion.objects.get(cliente_id=cliente_id)
        comidas = list(Comida.objects.filter(plan_alimentacion=plan_alimentacion))
        registro = RegistroComida.objects.get(cliente_id=cliente_id)
        notificacion = Notificacion.objects.get(usuario_id=cliente_id)
        self.assertTrue(PlanEntrenamientoEjercicio.objects.filter(plan=plan_entrenamiento).exists())

        self.autenticar()
        respuesta = self.client.delete(
            f"/api/clientes/{cliente_id}/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(respuesta.status_code, 204, respuesta.data)

        usuario = Usuario.objects.get(pk=cliente_id)
        self.assertIsNotNone(usuario.deleted_at)
        self.assertFalse(usuario.is_active)
        self.assertIsNotNone(Cliente.objects.get(pk=cliente_id).deleted_at)
        for registro_relacionado in (
            asignacion_entrenador,
            asignacion_terapeuta,
            asistencia,
            entrenamiento,
            plan_entrenamiento,
            plan_alimentacion,
            registro,
        ):
            registro_relacionado.refresh_from_db()
            with self.subTest(modelo=type(registro_relacionado).__name__):
                self.assertIsNotNone(registro_relacionado.deleted_at)
                self.assertFalse(registro_relacionado.is_active)

        self.assertEqual(PlanEntrenamientoEjercicio.objects.filter(plan=plan_entrenamiento).count(), 0)
        for comida in comidas:
            comida.refresh_from_db()
            self.assertIsNotNone(comida.deleted_at)
        notificacion.refresh_from_db()
        self.assertIsNotNone(notificacion.deleted_at)
        self.assertFalse(notificacion.is_active)

    def test_borrado_rol_y_permiso_es_logico_y_oculta_el_catalogo(self):
        self.autenticar()
        rol_respuesta = self.client.post(
            "/api/roles/",
            {"nombre": "auditor", "descripcion": "Solo lectura"},
            format="json",
        )
        self.assertEqual(rol_respuesta.status_code, 201)
        permiso = Permiso.objects.create(recurso="auditoria", accion="view")

        rol = Rol.objects.get(pk=rol_respuesta.data["id"])
        asignacion = UsuarioRol.objects.create(usuario=self.operador, rol=rol, activo=True)

        respuesta_rol = self.client.delete(
            f"/api/roles/{rol.pk}/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(respuesta_rol.status_code, 204, respuesta_rol.data)

        self._token_operador = None
        self.autenticar()
        # El catálogo de permisos es común a todos los gimnasios: un
        # administrador de gimnasio no puede borrarlo.
        self.assertEqual(
            self.client.delete(
                f"/api/permisos/{permiso.pk}/", HTTP_ACCEPT="application/json"
            ).status_code,
            403,
        )
        plataforma = APIClient()
        get_user_model().objects.create_superuser(
            username="plataforma", email="plataforma@example.com", password="ClavePlataforma123"
        )
        self.assertTrue(plataforma.login(username="plataforma", password="ClavePlataforma123"))
        respuesta_permiso = plataforma.delete(
            f"/api/permisos/{permiso.pk}/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(respuesta_permiso.status_code, 204, respuesta_permiso.data)

        rol.refresh_from_db()
        permiso.refresh_from_db()
        asignacion.refresh_from_db()
        self.assertFalse(rol.is_active)
        self.assertFalse(permiso.is_active)
        self.assertFalse(asignacion.activo)
        self.assertEqual(
            self.client.get(
                f"/api/roles/{rol.pk}/", HTTP_ACCEPT="application/json"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/permisos/{permiso.pk}/", HTTP_ACCEPT="application/json"
            ).status_code,
            404,
        )
        self.assertNotIn(
            rol.pk,
            [
                item["id"]
                for item in self.client.get(
                    "/api/roles/", HTTP_ACCEPT="application/json"
                ).data["results"]
            ],
        )
        self.assertNotIn(
            permiso.pk,
            [
                item["id"]
                for item in self.client.get(
                    "/api/permisos/", HTTP_ACCEPT="application/json"
                ).data["results"]
            ],
        )

    def test_borrado_entrenador_desactiva_cuenta_y_asignaciones(self):
        call_command("sembrar_datos_demo", por_rol=1, verbosity=0)
        entrenador = Entrenador.objects.get()
        asignacion = ClienteEntrenador.objects.get(entrenador=entrenador)

        self.autenticar()
        respuesta = self.client.delete(
            f"/api/entrenadores/{entrenador.pk}/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(respuesta.status_code, 204, respuesta.data)

        entrenador.refresh_from_db()
        asignacion.refresh_from_db()
        usuario = Usuario.objects.get(pk=entrenador.pk)
        self.assertIsNotNone(entrenador.deleted_at)
        self.assertIsNotNone(asignacion.deleted_at)
        self.assertFalse(asignacion.is_active)
        self.assertIsNotNone(usuario.deleted_at)

    def test_api_v1_y_alias_legacy_comparten_contrato(self):
        self.autenticar()

        for prefijo in ("/api/v1", "/api"):
            self.assertEqual(self.client.get(f"{prefijo}/").status_code, 200)
            self.assertEqual(self.client.get(f"{prefijo}/roles/").status_code, 200)
            self.assertEqual(self.client.get(f"{prefijo}/me/").status_code, 200)

        self.assertEqual(self.client.get("/api/v1/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/docs/").status_code, 200)

    def test_cliente_solo_ve_su_propio_perfil_y_usuario(self):
        cliente_a = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "alcance.cliente.a@example.com"
        )
        cliente_b = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "alcance.cliente.b@example.com"
        )

        self.autenticar_como("alcance.cliente.a@example.com", "UnaClaveSegura123")
        self.assertEqual(
            self.client.get(f"/api/v1/clientes/{cliente_b['id']}/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/usuarios/{cliente_b['id']}/").status_code,
            403,
        )

        listado = self.client.get("/api/v1/clientes/")
        self.assertEqual(listado.status_code, 200)
        self.assertEqual(
            [item["usuario"] for item in listado.data["results"]], [cliente_a["id"]]
        )

    def test_entrenador_solo_ve_clientes_asignados_y_acciones_anidadas(self):
        entrenador = self.crear_usuario_con_rol(
            Rol.Nombre.ENTRENADOR, "alcance.entrenador@example.com"
        )
        cliente_a = self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "alcance.asignado@example.com"
        )
        self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "alcance.no.asignado@example.com"
        )
        ClienteEntrenador.objects.create(
            cliente_id=cliente_a["id"],
            entrenador_id=entrenador["id"],
            fecha_inicio=date.today(),
        )
        PlanEntrenamiento.objects.create(
            cliente_id=cliente_a["id"],
            entrenador_id=entrenador["id"],
            nombre="Plan asignado",
            objetivo="Fuerza",
            fecha_inicio=date.today(),
        )

        self.autenticar_como("alcance.entrenador@example.com", "UnaClaveSegura123")
        listado = self.client.get("/api/v1/clientes/")
        self.assertEqual(listado.status_code, 200)
        self.assertEqual(
            [item["usuario"] for item in listado.data["results"]], [cliente_a["id"]]
        )

        planes = self.client.get(
            f"/api/v1/clientes/{cliente_a['id']}/planes-entrenamiento/"
        )
        self.assertEqual(planes.status_code, 200, planes.data)
        self.assertEqual(len(planes.data["results"]), 1)

        clientes = self.client.get(
            f"/api/v1/entrenadores/{entrenador['id']}/clientes/"
        )
        self.assertEqual(clientes.status_code, 200, clientes.data)
        self.assertEqual(
            [item["usuario"] for item in clientes.data["results"]], [cliente_a["id"]]
        )

    def test_restaurar_requiere_administrador_y_recupera_el_registro(self):
        ejercicio = Ejercicio.objects.create(nombre="Ejercicio restaurable")
        self.autenticar()
        borrado = self.client.delete(
            f"/api/v1/ejercicios/{ejercicio.pk}/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(borrado.status_code, 204, borrado.data)

        self.crear_usuario_con_rol(
            Rol.Nombre.CLIENTE, "alcance.restaurar@example.com"
        )
        self.autenticar_como("alcance.restaurar@example.com", "UnaClaveSegura123")
        denegado = self.client.post(
            f"/api/v1/ejercicios/{ejercicio.pk}/restaurar/", format="json"
        )
        self.assertEqual(denegado.status_code, 403)

        self.autenticar()
        restaurado = self.client.post(
            f"/api/v1/ejercicios/{ejercicio.pk}/restaurar/", format="json"
        )
        self.assertEqual(restaurado.status_code, 200, restaurado.data)
        self.assertEqual(
            self.client.get(f"/api/v1/ejercicios/{ejercicio.pk}/").status_code, 200
        )

    def test_logout_all_revoca_todas_las_sesiones(self):
        primera = self.client.post(
            "/api/v1/login/",
            {"correo": self.operador.correo, "contrasena": "OtraClaveSegura123"},
            format="json",
        )
        segunda = self.client.post(
            "/api/v1/login/",
            {"correo": self.operador.correo, "contrasena": "OtraClaveSegura123"},
            format="json",
        )
        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {primera.data['token']}"
        )
        salida = self.client.post("/api/v1/logout/all/", format="json")
        self.assertEqual(salida.status_code, 200)
        self.assertGreaterEqual(salida.data["sesiones_revocadas"], 2)

        for respuesta in (primera, segunda):
            self.client.credentials(
                HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}"
            )
            self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)

    def test_login_esta_regulado_por_intentos(self):
        for _ in range(10):
            respuesta = self.client.post(
                "/api/v1/login/",
                {"correo": self.operador.correo, "contrasena": "ClaveIncorrecta123"},
                format="json",
            )
            self.assertEqual(respuesta.status_code, 401)

        regulado = self.client.post(
            "/api/v1/login/",
            {"correo": self.operador.correo, "contrasena": "ClaveIncorrecta123"},
            format="json",
        )
        self.assertEqual(regulado.status_code, 429)
        self.assertEqual(regulado.data["error"]["codigo"], 429)

    def test_cambios_de_permisos_de_rol_generan_auditoria(self):
        self.autenticar()
        rol = Rol.objects.create(gimnasio=gimnasio_principal(), nombre="rol-auditado")
        codigo = "roles:view"

        respuesta = self.client.put(
            f"/api/v1/roles/{rol.pk}/permisos/",
            {"permisos": [codigo]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)

        evento = EventoAuditoria.objects.filter(
            accion="actualizar-permisos", recurso="roles", objeto_id=str(rol.pk)
        ).first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.actor, self.operador)
        self.assertEqual(evento.detalles["permisos"], [codigo])


class CargarEnvTests(SimpleTestCase):
    """Comportamiento del cargador de backend/.env."""

    def _cargar(self, contenido, entorno=None):
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / ".env"
            ruta.write_text(contenido, encoding="utf-8")
            with patch.dict(os.environ, entorno or {}, clear=True):
                cargar_env(ruta)
                return dict(os.environ)

    def test_carga_claves_y_omite_lineas_invalidas(self):
        resultado = self._cargar(
            "\n".join(
                [
                    "# comentario",
                    'CLAVE=valor',
                    "",
                    "OTRA= con espacios ",
                    "export EXPORTADA=x",
                    'COMILLAS="doble"',
                    "linea sin igual",
                    "=sin-clave",
                    "1INVALIDA=x",
                ]
            )
        )

        self.assertEqual(resultado["CLAVE"], "valor")
        self.assertEqual(resultado["OTRA"], "con espacios")
        self.assertEqual(resultado["EXPORTADA"], "x")
        self.assertEqual(resultado["COMILLAS"], "doble")
        self.assertNotIn("linea sin igual", resultado)
        self.assertNotIn("", resultado)
        self.assertNotIn("1INVALIDA", resultado)

    def test_no_sobrescribe_variables_del_proceso(self):
        resultado = self._cargar("CLAVE=del-archivo\nNUEVA=del-archivo", {"CLAVE": "del-proceso"})

        self.assertEqual(resultado["CLAVE"], "del-proceso")
        self.assertEqual(resultado["NUEVA"], "del-archivo")

    def test_archivo_ausente_no_falla_ni_modifica_el_entorno(self):
        with TemporaryDirectory() as carpeta:
            faltante = Path(carpeta) / ".env"
            with patch.dict(os.environ, {"CLAVE": "del-proceso"}, clear=True):
                cargar_env(faltante)

                self.assertEqual(dict(os.environ), {"CLAVE": "del-proceso"})


class FinancieroApiTests(APITestCase):
    """Módulo financiero: pagos, gastos, membresías, alertas y dashboard."""

    CLAVE = "OtraClaveSegura123"

    def setUp(self):
        cache.clear()
        self.admin = self._crear_usuario(
            Rol.Nombre.ADMINISTRADOR, "Admin Finanzas", "finanzas@example.com"
        )
        usuario_cliente = self._crear_usuario(
            Rol.Nombre.CLIENTE, "Carla Ruiz", "carla@example.com"
        )
        self.cliente = Cliente.objects.create(
            usuario=usuario_cliente, tipo_documento="CC", numero_documento="900100"
        )
        self.metodo = MetodoPago.objects.create(
            nombre="Efectivo prueba", tipo=MetodoPago.Tipo.EFECTIVO
        )
        self.categoria = CategoriaGasto.objects.create(
            nombre="Arriendo prueba", tipo=CategoriaGasto.Tipo.ARRIENDO
        )
        self.hoy = timezone.localdate()
        self._autenticar(self.admin)

    def _crear_usuario(self, nombre_rol, nombre, correo):
        usuario = Usuario(
            rol=Rol.objects.get(nombre=nombre_rol), nombre=nombre, correo=correo
        )
        usuario.set_password(self.CLAVE)
        usuario.full_clean()
        usuario.save()
        return usuario

    def _autenticar(self, usuario):
        self.client.credentials()
        respuesta = self.client.post(
            "/api/v1/login/",
            {"correo": usuario.correo, "contrasena": self.CLAVE},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}"
        )

    def _membresia(self, fecha_fin, **extra):
        datos = {
            "cliente": self.cliente,
            "tipo": Membresia.Tipo.MENSUAL,
            "nombre": "Mensual estándar",
            "precio": Decimal("80000"),
            "fecha_inicio": fecha_fin - timedelta(days=30),
            "fecha_fin": fecha_fin,
            "registrado_por": self.admin,
        }
        datos.update(extra)
        return Membresia.objects.create(**datos)

    def _pago(self, valor, **extra):
        datos = {
            "cliente": self.cliente,
            "concepto": Pago.Concepto.MEMBRESIA,
            "valor": Decimal(valor),
            "metodo_pago": self.metodo,
            "registrado_por": self.admin,
        }
        datos.update(extra)
        return Pago.objects.create(**datos)

    def _gasto(self, valor, **extra):
        datos = {
            "descripcion": "Arriendo del mes",
            "categoria": self.categoria,
            "valor": Decimal(valor),
            "fecha": self.hoy,
            "metodo_pago": self.metodo,
            "registrado_por": self.admin,
        }
        datos.update(extra)
        return Gasto.objects.create(**datos)

    def test_rutas_financieras_requieren_autenticacion(self):
        self.client.credentials()
        for ruta in (
            "/api/v1/dashboard/",
            "/api/v1/pagos/",
            "/api/v1/gastos/",
            "/api/v1/membresias/",
            "/api/v1/alertas/",
            "/api/v1/metodos-pago/",
            "/api/v1/categorias-gasto/",
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 401)

    def test_administrador_registra_y_lista_un_pago(self):
        respuesta = self.client.post(
            "/api/v1/pagos/",
            {
                "cliente": self.cliente.pk,
                "concepto": Pago.Concepto.MEMBRESIA,
                "valor": "80000.00",
                "metodo_pago": self.metodo.pk,
                "registrado_por": self.admin.pk,
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data["estado"], Pago.Estado.COMPLETADO)

        listado = self.client.get("/api/v1/pagos/")
        self.assertEqual(listado.status_code, 200)
        self.assertEqual(listado.data["count"], 1)
        self.assertTrue(
            EventoAuditoria.objects.filter(recurso="pagos", accion="crear").exists()
        )

    def test_pago_rechaza_valor_no_positivo(self):
        respuesta = self.client.post(
            "/api/v1/pagos/",
            {
                "cliente": self.cliente.pk,
                "concepto": Pago.Concepto.OTRO,
                "valor": "0",
                "metodo_pago": self.metodo.pk,
                "registrado_por": self.admin.pk,
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(Pago.objects.count(), 0)

    def test_estadisticas_de_pagos_separan_completados_y_pendientes(self):
        self._pago("80000")
        self._pago("20000", concepto=Pago.Concepto.PRODUCTO)
        self._pago("50000", estado=Pago.Estado.PENDIENTE)

        respuesta = self.client.get("/api/v1/pagos/estadisticas/")

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(Decimal(respuesta.data["total_ingresos"]), Decimal("100000"))
        self.assertEqual(Decimal(respuesta.data["total_pendientes"]), Decimal("50000"))
        self.assertEqual(respuesta.data["count_completados"], 2)
        self.assertEqual(respuesta.data["count_pendientes"], 1)
        self.assertEqual(len(respuesta.data["por_concepto"]), 2)

    def test_estadisticas_de_gastos_agrupan_por_categoria(self):
        self._gasto("300000")
        self._gasto("50000", fecha=self.hoy - timedelta(days=90))

        respuesta = self.client.get("/api/v1/gastos/estadisticas/")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(Decimal(respuesta.data["total_gastos"]), Decimal("350000"))
        self.assertEqual(respuesta.data["count"], 2)
        self.assertEqual(
            respuesta.data["por_categoria"][0]["categoria__nombre"],
            self.categoria.nombre,
        )

        filtrado = self.client.get(
            "/api/v1/gastos/estadisticas/",
            {"fecha_desde": (self.hoy - timedelta(days=7)).isoformat()},
        )
        self.assertEqual(Decimal(filtrado.data["total_gastos"]), Decimal("300000"))

    def test_membresia_calcula_su_estado_al_crearse(self):
        self.assertEqual(
            self._membresia(self.hoy + timedelta(days=20)).estado,
            Membresia.Estado.ACTIVA,
        )
        self.assertEqual(
            self._membresia(self.hoy + timedelta(days=3)).estado,
            Membresia.Estado.POR_VENCER,
        )
        self.assertEqual(
            self._membresia(self.hoy - timedelta(days=1)).estado,
            Membresia.Estado.VENCIDA,
        )

    def test_sincronizar_estados_vence_membresias_con_el_paso_del_tiempo(self):
        activa = self._membresia(self.hoy + timedelta(days=20))
        congelada = self._membresia(self.hoy + timedelta(days=20))
        cancelada = self._membresia(self.hoy + timedelta(days=20))
        Membresia.objects.filter(pk=congelada.pk).update(
            estado=Membresia.Estado.CONGELADA
        )
        Membresia.objects.filter(pk=cancelada.pk).update(
            estado=Membresia.Estado.CANCELADA
        )

        cambios = Membresia.sincronizar_estados(hoy=self.hoy + timedelta(days=15))
        activa.refresh_from_db()
        congelada.refresh_from_db()
        self.assertEqual(activa.estado, Membresia.Estado.POR_VENCER)
        self.assertEqual(cambios["por_vencer"], 1)
        # Dentro de su vigencia, una congelada sigue congelada.
        self.assertEqual(congelada.estado, Membresia.Estado.CONGELADA)

        cambios = Membresia.sincronizar_estados(hoy=self.hoy + timedelta(days=40))
        activa.refresh_from_db()
        congelada.refresh_from_db()
        cancelada.refresh_from_db()
        self.assertEqual(activa.estado, Membresia.Estado.VENCIDA)
        # Pasada su fecha de fin, la congelada también vence.
        self.assertEqual(congelada.estado, Membresia.Estado.VENCIDA)
        self.assertEqual(cambios["vencidas"], 2)
        self.assertEqual(cancelada.estado, Membresia.Estado.CANCELADA)

    def test_comando_actualizar_membresias_sincroniza_estados(self):
        membresia = self._membresia(self.hoy + timedelta(days=20))
        Membresia.objects.filter(pk=membresia.pk).update(
            fecha_inicio=self.hoy - timedelta(days=60),
            fecha_fin=self.hoy - timedelta(days=2),
        )

        salida = StringIO()
        call_command("actualizar_membresias", stdout=salida)

        membresia.refresh_from_db()
        self.assertEqual(membresia.estado, Membresia.Estado.VENCIDA)
        self.assertIn("vencidas: 1", salida.getvalue())

    def test_renovar_extiende_la_vigencia_por_meses(self):
        fecha_fin = date(2026, 1, 31)
        membresia = self._membresia(fecha_fin)

        respuesta = self.client.post(
            f"/api/v1/membresias/{membresia.pk}/renovar/",
            {"meses": 1},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        membresia.refresh_from_db()
        # 31 de enero + 1 mes se ajusta al último día de febrero.
        self.assertEqual(membresia.fecha_fin, date(2026, 2, 28))
        self.assertEqual(membresia.fecha_ultima_renovacion, fecha_fin)

    def test_renovar_reactiva_una_membresia_vencida(self):
        membresia = self._membresia(self.hoy - timedelta(days=1))
        self.assertEqual(membresia.estado, Membresia.Estado.VENCIDA)

        respuesta = self.client.post(
            f"/api/v1/membresias/{membresia.pk}/renovar/",
            {"meses": 3, "tipo": Membresia.Tipo.TRIMESTRAL},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["estado"], Membresia.Estado.ACTIVA)
        self.assertEqual(respuesta.data["tipo"], Membresia.Tipo.TRIMESTRAL)

    def test_renovar_rechaza_meses_y_tipo_invalidos(self):
        membresia = self._membresia(self.hoy + timedelta(days=20))
        fecha_fin = membresia.fecha_fin

        for carga in ({"meses": "abc"}, {"meses": 0}, {"meses": -2}, {"tipo": "eterna"}):
            with self.subTest(carga=carga):
                respuesta = self.client.post(
                    f"/api/v1/membresias/{membresia.pk}/renovar/", carga, format="json"
                )
                self.assertEqual(respuesta.status_code, 400, respuesta.data)

        membresia.refresh_from_db()
        self.assertEqual(membresia.fecha_fin, fecha_fin)

    def test_congelar_y_activar_membresia(self):
        membresia = self._membresia(self.hoy + timedelta(days=20))

        congelada = self.client.post(
            f"/api/v1/membresias/{membresia.pk}/congelar/", {"dias": 5}, format="json"
        )
        self.assertEqual(congelada.status_code, 200, congelada.data)
        self.assertEqual(congelada.data["estado"], Membresia.Estado.CONGELADA)
        self.assertEqual(congelada.data["dias_congelados"], 5)
        # Los días congelados corren el vencimiento: no se pierden.
        self.assertEqual(
            congelada.data["fecha_fin"],
            (self.hoy + timedelta(days=25)).isoformat(),
        )

        repetida = self.client.post(
            f"/api/v1/membresias/{membresia.pk}/congelar/", {"dias": 5}, format="json"
        )
        self.assertEqual(repetida.status_code, 400)

        activa = self.client.post(f"/api/v1/membresias/{membresia.pk}/activar/")
        self.assertEqual(activa.status_code, 200, activa.data)
        self.assertEqual(activa.data["estado"], Membresia.Estado.ACTIVA)
        self.assertEqual(
            set(
                EventoAuditoria.objects.filter(recurso="membresias").values_list(
                    "accion", flat=True
                )
            ),
            {"congelar", "activar"},
        )

    def test_congelar_rechaza_dias_invalidos(self):
        membresia = self._membresia(self.hoy + timedelta(days=20))

        for dias in ("abc", -5, 0, 1000, None):
            with self.subTest(dias=dias):
                respuesta = self.client.post(
                    f"/api/v1/membresias/{membresia.pk}/congelar/",
                    {"dias": dias},
                    format="json",
                )
                self.assertEqual(respuesta.status_code, 400, respuesta.data)

        membresia.refresh_from_db()
        self.assertEqual(membresia.estado, Membresia.Estado.ACTIVA)
        self.assertEqual(membresia.dias_congelados, 0)

    def test_activar_una_congelada_ya_vencida_la_deja_vencida(self):
        membresia = self._membresia(self.hoy + timedelta(days=20))
        Membresia.objects.filter(pk=membresia.pk).update(
            estado=Membresia.Estado.CONGELADA,
            fecha_inicio=self.hoy - timedelta(days=60),
            fecha_fin=self.hoy - timedelta(days=3),
        )

        respuesta = self.client.post(f"/api/v1/membresias/{membresia.pk}/activar/")

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["estado"], Membresia.Estado.VENCIDA)

    def test_fechas_invalidas_en_filtros_devuelven_400(self):
        for ruta in (
            "/api/v1/pagos/estadisticas/?fecha_desde=xx",
            "/api/v1/gastos/estadisticas/?fecha_hasta=2026-13-40",
            "/api/v1/pagos/?fecha_desde=ayer",
            "/api/v1/gastos/?fecha_desde=2026-05-10&fecha_hasta=2026-05-01",
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 400)

    def test_listado_estadisticas_y_exportacion_comparten_el_filtro_de_fechas(self):
        self._pago("80000")
        self._pago("20000", fecha_pago=timezone.now() - timedelta(days=60))
        rango = {
            "fecha_desde": (self.hoy - timedelta(days=7)).isoformat(),
            "fecha_hasta": self.hoy.isoformat(),
        }

        listado = self.client.get("/api/v1/pagos/", rango)
        estadisticas = self.client.get("/api/v1/pagos/estadisticas/", rango)
        exportado = self.client.get("/api/v1/pagos/exportar/", rango)

        self.assertEqual(listado.data["count"], 1)
        self.assertEqual(Decimal(estadisticas.data["total_ingresos"]), Decimal("80000"))
        # Encabezado más una sola fila.
        self.assertEqual(len(exportado.content.decode().strip().splitlines()), 2)
        self.assertEqual(self.client.get("/api/v1/pagos/").data["count"], 2)

    def test_page_size_lo_decide_el_cliente_con_un_tope(self):
        for _ in range(3):
            self._gasto("1000")

        respuesta = self.client.get("/api/v1/gastos/", {"page_size": 2})

        self.assertEqual(respuesta.data["count"], 3)
        self.assertEqual(len(respuesta.data["results"]), 2)
        self.assertIsNotNone(respuesta.data["next"])

    def test_pago_toma_registrado_por_de_la_sesion(self):
        otro = self._crear_usuario(
            Rol.Nombre.RECEPCIONISTA, "Rosa Recepción", "rosa@example.com"
        )

        respuesta = self.client.post(
            "/api/v1/pagos/",
            {
                "cliente": self.cliente.pk,
                "concepto": Pago.Concepto.MATRICULA,
                "valor": "30000",
                "metodo_pago": self.metodo.pk,
                "registrado_por": otro.pk,
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data["registrado_por"], self.admin.pk)

    def test_pago_rechaza_membresia_de_otro_cliente(self):
        usuario = self._crear_usuario(Rol.Nombre.CLIENTE, "Luis Mora", "luis@example.com")
        otro_cliente = Cliente.objects.create(usuario=usuario)
        ajena = self._membresia(self.hoy + timedelta(days=20), cliente=otro_cliente)

        respuesta = self.client.post(
            "/api/v1/pagos/",
            {
                "cliente": self.cliente.pk,
                "membresia": ajena.pk,
                "concepto": Pago.Concepto.MEMBRESIA,
                "valor": "80000",
                "metodo_pago": self.metodo.pk,
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400, respuesta.data)
        self.assertIn("membresia", respuesta.data["error"]["detalles"])

    def test_gasto_registra_quien_lo_aprueba(self):
        otro = self._crear_usuario(
            Rol.Nombre.RECEPCIONISTA, "Rosa Recepción", "rosa@example.com"
        )
        creado = self.client.post(
            "/api/v1/gastos/",
            {
                "descripcion": "Mantenimiento de caminadoras",
                "categoria": self.categoria.pk,
                "valor": "120000",
                "fecha": self.hoy.isoformat(),
                "metodo_pago": self.metodo.pk,
                "aprobado_por": otro.pk,
            },
            format="json",
        )
        self.assertEqual(creado.status_code, 201, creado.data)
        self.assertEqual(creado.data["estado"], Gasto.Estado.REGISTRADO)
        self.assertEqual(creado.data["registrado_por"], self.admin.pk)
        self.assertIsNone(creado.data["aprobado_por"])

        aprobado = self.client.patch(
            f"/api/v1/gastos/{creado.data['id']}/",
            {"estado": Gasto.Estado.APROBADO, "aprobado_por": otro.pk},
            format="json",
        )
        self.assertEqual(aprobado.status_code, 200, aprobado.data)
        self.assertEqual(aprobado.data["aprobado_por"], self.admin.pk)
        self.assertIsNotNone(aprobado.data["fecha_aprobacion"])

    def test_exportacion_csv_neutraliza_formulas(self):
        self._pago("5000", notas='=HYPERLINK("http://example.com")')
        self._pago("7000", notas="-2 unidades devueltas")

        contenido = self.client.get("/api/v1/pagos/exportar/").content.decode()

        self.assertIn("'=HYPERLINK", contenido)
        self.assertIn("'-2 unidades devueltas", contenido)
        self.assertNotIn(",=HYPERLINK", contenido)
        # Los números no se tocan.
        self.assertIn("5000.00", contenido)
        self.assertNotIn("'5000.00", contenido)

    def test_alertas_se_ordenan_de_critica_a_baja(self):
        for prioridad in ("baja", "critica", "media", "alta"):
            Alerta.objects.create(
                tipo=Alerta.Tipo.GASTOS_ALTOS,
                prioridad=prioridad,
                titulo=f"Alerta {prioridad}",
                mensaje="Detalle.",
            )
        esperado = ["critica", "alta", "media", "baja"]

        listado = self.client.get("/api/v1/alertas/")
        dashboard = self.client.get("/api/v1/dashboard/")

        self.assertEqual([a["prioridad"] for a in listado.data["results"]], esperado)
        self.assertEqual(
            [a["prioridad"] for a in dashboard.data["alertas_recientes"]], esperado
        )

    def test_alertas_de_membresias_se_generan_una_sola_vez(self):
        por_vencer = self._membresia(self.hoy + timedelta(days=3))
        vencida = self._membresia(self.hoy - timedelta(days=2))
        self._membresia(self.hoy + timedelta(days=25))

        self.assertEqual(Alerta.generar_de_membresias(), 2)
        self.assertEqual(Alerta.generar_de_membresias(), 0)

        alerta_vencida = Alerta.objects.get(membresia=vencida)
        self.assertEqual(alerta_vencida.tipo, Alerta.Tipo.MEMBRESIA_VENCIDA)
        self.assertEqual(alerta_vencida.prioridad, Alerta.Prioridad.ALTA)
        self.assertEqual(alerta_vencida.cliente, self.cliente)
        self.assertEqual(
            Alerta.objects.get(membresia=por_vencer).tipo,
            Alerta.Tipo.MEMBRESIA_POR_VENCER,
        )

        # Tras renovar y volver a acercarse al vencimiento, avisa de nuevo.
        Membresia.objects.filter(pk=vencida.pk).update(
            fecha_fin=self.hoy + timedelta(days=5),
            estado=Membresia.Estado.POR_VENCER,
        )
        self.assertEqual(Alerta.generar_de_membresias(), 1)

    def test_graficas_del_dashboard_cubren_doce_meses_consecutivos(self):
        inicio_mes = timezone.localtime().replace(
            day=1, hour=12, minute=0, second=0, microsecond=0
        )
        mes_pasado = inicio_mes - timedelta(days=10)
        self._pago("40000", fecha_pago=mes_pasado)
        self._gasto("15000", fecha=mes_pasado.date())

        graficas = self.client.get("/api/v1/dashboard/").data["graficas"]

        esperados = []
        anio, mes = self.hoy.year, self.hoy.month
        for _ in range(12):
            esperados.append(f"{anio:04d}-{mes:02d}")
            anio, mes = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
        esperados.reverse()

        serie = graficas["ingresos_vs_gastos"]
        self.assertEqual([punto["mes"] for punto in serie], esperados)
        self.assertEqual(
            [punto["mes"] for punto in graficas["crecimiento_clientes"]], esperados
        )
        self.assertEqual(serie[-2]["ingresos"], 40000.0)
        self.assertEqual(serie[-2]["gastos"], 15000.0)
        self.assertEqual(graficas["crecimiento_clientes"][-1]["nuevos"], 1)

    def test_gasto_se_edita_y_anulado_no_suma(self):
        gasto = self._gasto("50000")
        self._gasto("20000", descripcion="Servicio de internet")

        respuesta = self.client.patch(
            f"/api/v1/gastos/{gasto.id}/", {"valor": "45000"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        respuesta = self.client.patch(
            f"/api/v1/gastos/{gasto.id}/", {"estado": "cancelado"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)

        stats = self.client.get("/api/v1/gastos/estadisticas/").data
        self.assertEqual(Decimal(str(stats["total_gastos"])), Decimal("20000"))
        self.assertEqual(stats["count_anulados"], 1)
        financieras = self.client.get("/api/v1/dashboard/").data["metricas_financieras"]
        self.assertEqual(financieras["gastos"]["mes"], 20000.0)

        busqueda = self.client.get("/api/v1/gastos/?search=internet").data
        self.assertEqual(busqueda["count"], 1)

    def test_dashboard_acepta_periodos_de_graficas(self):
        hace_cinco_meses = timezone.localtime() - timedelta(days=150)
        self._pago("70000", fecha_pago=hace_cinco_meses)

        respuesta = self.client.get("/api/v1/dashboard/?meses=6&dias=7")
        self.assertEqual(respuesta.status_code, 200)
        graficas = respuesta.data["graficas"]
        self.assertEqual(len(graficas["ingresos_vs_gastos"]), 6)
        self.assertEqual(len(graficas["ganancias_mensuales"]), 6)
        self.assertEqual(len(graficas["crecimiento_clientes"]), 6)
        self.assertEqual(len(graficas["asistencias_por_dia"]), 7)
        self.assertEqual(graficas["periodo"], {"meses": 6, "dias": 7})
        self.assertEqual(
            sum(punto["ingresos"] for punto in graficas["ingresos_vs_gastos"]), 70000.0
        )

        respuesta = self.client.get("/api/v1/dashboard/?meses=24&dias=90")
        self.assertEqual(len(respuesta.data["graficas"]["ingresos_vs_gastos"]), 24)
        self.assertEqual(len(respuesta.data["graficas"]["asistencias_por_dia"]), 90)

        for consulta in ("meses=5", "meses=abc", "dias=31", "dias=-7"):
            respuesta = self.client.get(f"/api/v1/dashboard/?{consulta}")
            self.assertEqual(respuesta.status_code, 400, consulta)

    def test_dashboard_resume_asistencias_por_dia_y_hora(self):
        ahora = timezone.localtime().replace(hour=7, minute=30, second=0, microsecond=0)
        for dias in (1, 1, 2):
            entrada = ahora - timedelta(days=dias)
            Asistencia.objects.create(
                cliente=self.cliente,
                entrada_at=entrada,
                salida_at=entrada + timedelta(hours=1),
            )

        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.client.get("/api/v1/dashboard/")

        asistencias = respuesta.data["metricas_asistencias"]
        self.assertEqual(asistencias["hora_pico"], "07:00")
        self.assertEqual(asistencias["promedio_diario"], 1.5)
        por_dia = {
            punto["fecha"]: punto["total"]
            for punto in respuesta.data["graficas"]["asistencias_por_dia"]
        }
        self.assertEqual(por_dia[(self.hoy - timedelta(days=1)).isoformat()], 2)
        self.assertEqual(por_dia[(self.hoy - timedelta(days=2)).isoformat()], 1)
        self.assertEqual(
            respuesta.data["graficas"]["horarios_asistencia"],
            [{"hora": "07:00", "total": 3}],
        )
        # Antes eran más de 100 consultas (una por mes y por día).
        self.assertLess(len(consultas), 60)

    def test_alertas_se_marcan_como_leidas(self):
        alerta = Alerta.objects.create(
            tipo=Alerta.Tipo.PAGOS_PENDIENTES,
            titulo="Pago pendiente",
            mensaje="Carla tiene un pago pendiente.",
            cliente=self.cliente,
        )
        Alerta.objects.create(
            tipo=Alerta.Tipo.GASTOS_ALTOS,
            prioridad=Alerta.Prioridad.ALTA,
            titulo="Gastos altos",
            mensaje="Los gastos superan los ingresos.",
        )

        estadisticas = self.client.get("/api/v1/alertas/estadisticas/")
        self.assertEqual(estadisticas.status_code, 200, estadisticas.data)
        self.assertEqual(estadisticas.data["no_leidas"], 2)

        una = self.client.post(f"/api/v1/alertas/{alerta.pk}/marcar-leida/")
        self.assertEqual(una.status_code, 200, una.data)
        alerta.refresh_from_db()
        self.assertTrue(alerta.leida)
        self.assertEqual(alerta.leida_por, self.admin)

        todas = self.client.post("/api/v1/alertas/marcar-todas-leidas/")
        self.assertEqual(todas.status_code, 200, todas.data)
        self.assertEqual(todas.data["cantidad"], 1)
        self.assertFalse(Alerta.objects.filter(leida=False).exists())
        self.assertFalse(Alerta.objects.exclude(leida_por=self.admin).exists())

    def test_dashboard_consolida_ingresos_gastos_y_membresias(self):
        self._pago("80000")
        self._pago("50000", estado=Pago.Estado.PENDIENTE)
        self._gasto("30000")
        self._membresia(self.hoy + timedelta(days=20))

        respuesta = self.client.get("/api/v1/dashboard/")

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        financieras = respuesta.data["metricas_financieras"]
        self.assertEqual(financieras["ingresos"]["mes"], 80000.0)
        self.assertEqual(financieras["ingresos"]["pendientes_mes"], 50000.0)
        self.assertEqual(financieras["gastos"]["mes"], 30000.0)
        self.assertEqual(financieras["ganancia_neta"]["mes"], 50000.0)

        clientes = respuesta.data["metricas_clientes"]
        self.assertEqual(clientes["total_registrados"], 1)
        self.assertEqual(clientes["activos"], 1)
        self.assertEqual(clientes["inactivos"], 0)
        self.assertEqual(respuesta.data["metricas_membresias"]["activas"], 1)

        graficas = respuesta.data["graficas"]
        self.assertEqual(len(graficas["ingresos_vs_gastos"]), 12)
        self.assertEqual(len(graficas["asistencias_por_dia"]), 30)
        mes_actual = graficas["ingresos_vs_gastos"][-1]
        self.assertEqual(mes_actual["mes"], self.hoy.strftime("%Y-%m"))
        self.assertEqual(mes_actual["ingresos"], 80000.0)
        self.assertEqual(mes_actual["gastos"], 30000.0)
        self.assertEqual(mes_actual["ganancia"], 50000.0)

    def test_dashboard_cuenta_membresias_vencidas_y_sin_renovar(self):
        # Se creó vigente y venció después, sin que nadie la volviera a guardar.
        membresia = self._membresia(self.hoy + timedelta(days=20))
        Membresia.objects.filter(pk=membresia.pk).update(
            fecha_inicio=self.hoy - timedelta(days=40),
            fecha_fin=self.hoy - timedelta(days=5),
        )

        respuesta = self.client.get("/api/v1/dashboard/")

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        clientes = respuesta.data["metricas_clientes"]
        self.assertEqual(clientes["membresias_vencidas"], 1)
        self.assertEqual(clientes["sin_renovar"], 1)
        self.assertEqual(clientes["activos"], 0)
        self.assertEqual(clientes["inactivos"], 1)
        self.assertEqual(respuesta.data["metricas_membresias"]["vencidas"], 1)

    def test_dashboard_no_cuenta_como_vencido_al_cliente_que_renovo(self):
        self._membresia(self.hoy - timedelta(days=5))
        self._membresia(self.hoy + timedelta(days=25))

        respuesta = self.client.get("/api/v1/dashboard/")

        clientes = respuesta.data["metricas_clientes"]
        self.assertEqual(clientes["membresias_vencidas"], 0)
        self.assertEqual(clientes["sin_renovar"], 0)
        self.assertEqual(clientes["activos"], 1)

    def test_cliente_no_accede_a_finanzas_del_gimnasio(self):
        self._gasto("30000")
        self._autenticar(self.cliente.usuario)

        self.assertEqual(self.client.get("/api/v1/dashboard/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/gastos/").status_code, 403)
        self.assertEqual(
            self.client.get("/api/v1/gastos/estadisticas/").status_code, 403
        )


class EscenarioDosGimnasios(APITestCase):
    """Dos gimnasios con datos propios; las pruebas actúan como admin de A.

    El gimnasio A es el principal que crea la migración; el B se crea en la
    prueba como lo haría el personal de la plataforma.
    """

    CLAVE = "ClaveSegura-2026"

    def setUp(self):
        cache.clear()
        self.gym_a = gimnasio_principal()
        self.gym_b = Gimnasio.objects.create(nombre="Gimnasio Norte", codigo="norte")
        rol_admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)
        rol_cliente = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)

        self.admin_a = self._usuario(self.gym_a, rol_admin, "admin.a@example.com")
        self.admin_b = self._usuario(self.gym_b, rol_admin, "admin.b@example.com")
        self.cliente_a = Cliente.objects.create(
            usuario=self._usuario(self.gym_a, rol_cliente, "cliente.a@example.com")
        )
        self.cliente_b = Cliente.objects.create(
            usuario=self._usuario(self.gym_b, rol_cliente, "cliente.b@example.com")
        )
        self.metodo_a = MetodoPago.objects.get(gimnasio=self.gym_a, nombre="Efectivo")
        self.metodo_b = MetodoPago.objects.get(gimnasio=self.gym_b, nombre="Efectivo")
        self.categoria_b = CategoriaGasto.objects.get(gimnasio=self.gym_b, nombre="Arriendo")
        hoy = timezone.localdate()

        self.pago_a = Pago.objects.create(
            cliente=self.cliente_a, concepto=Pago.Concepto.MATRICULA, valor=Decimal("10000"),
            metodo_pago=self.metodo_a, registrado_por=self.admin_a,
        )
        self.pago_b = Pago.objects.create(
            cliente=self.cliente_b, concepto=Pago.Concepto.MATRICULA, valor=Decimal("999000"),
            metodo_pago=self.metodo_b, registrado_por=self.admin_b,
        )
        self.gasto_b = Gasto.objects.create(
            descripcion="Arriendo secreto del Norte", categoria=self.categoria_b,
            valor=Decimal("777000"), fecha=hoy, metodo_pago=self.metodo_b,
            registrado_por=self.admin_b,
        )
        self.membresia_b = Membresia.objects.create(
            cliente=self.cliente_b, nombre="Mensual Norte", precio=Decimal("90000"),
            fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=30), registrado_por=self.admin_b,
        )
        self.asistencia_b = Asistencia.objects.create(
            cliente=self.cliente_b, entrada_at=timezone.now() - timedelta(hours=1)
        )
        self.alerta_b = Alerta.objects.create(
            tipo=Alerta.Tipo.GASTOS_ALTOS, titulo="Alerta del Norte", mensaje="Solo para B.",
            gasto=self.gasto_b,
        )
        self.ejercicio_b = Ejercicio.objects.create(gimnasio=self.gym_b, nombre="Sentadilla Norte")
        self._autenticar(self.admin_a)

    def _usuario(self, gimnasio, rol, correo):
        usuario = Usuario(gimnasio=gimnasio, rol=rol, nombre=correo.split("@")[0], correo=correo)
        usuario.set_password(self.CLAVE)
        usuario.save()
        return usuario

    def _autenticar(self, usuario):
        self.client.credentials()
        respuesta = self.client.post(
            "/api/v1/login/", {"correo": usuario.correo, "contrasena": self.CLAVE}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")
        return respuesta

    def _ids(self, ruta):
        respuesta = self.client.get(ruta, {"page_size": 200})
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        return {fila["id"] if "id" in fila else fila["usuario"] for fila in respuesta.data["results"]}


class AislamientoGimnasiosTests(EscenarioDosGimnasios):
    """Un gimnasio nunca ve ni modifica datos de otro (SaaS multi-tenant).

    Todas las solicitudes se hacen como administrador de A contra registros de B.
    """

    def test_cada_modelo_declara_como_se_aisla(self):
        from django.apps import apps

        from .tenancy import ruta_gimnasio

        for modelo in apps.get_app_config("gym").get_models():
            with self.subTest(modelo=modelo.__name__):
                ruta_gimnasio(modelo)

    def test_los_datos_heredan_el_gimnasio_de_su_cliente(self):
        self.assertEqual(self.pago_b.gimnasio, self.gym_b)
        self.assertEqual(self.membresia_b.gimnasio, self.gym_b)
        self.assertEqual(self.asistencia_b.gimnasio, self.gym_b)
        self.assertEqual(self.alerta_b.gimnasio, self.gym_b)

    def test_listados_solo_muestran_el_propio_gimnasio(self):
        casos = {
            "/api/v1/usuarios/": {self.admin_b.pk, self.cliente_b.pk},
            "/api/v1/clientes/": {self.cliente_b.pk},
            "/api/v1/pagos/": {self.pago_b.pk},
            "/api/v1/gastos/": {self.gasto_b.pk},
            "/api/v1/membresias/": {self.membresia_b.pk},
            "/api/v1/asistencias/": {self.asistencia_b.pk},
            "/api/v1/alertas/": {self.alerta_b.pk},
            "/api/v1/ejercicios/": {self.ejercicio_b.pk},
            "/api/v1/metodos-pago/": {self.metodo_b.pk},
            "/api/v1/categorias-gasto/": {self.categoria_b.pk},
        }
        for ruta, ajenos in casos.items():
            with self.subTest(ruta=ruta):
                visibles = self._ids(ruta)
                self.assertFalse(visibles & ajenos, f"{ruta} expone datos de otro gimnasio")
        self.assertIn(self.pago_a.pk, self._ids("/api/v1/pagos/"))

    def test_detalle_y_escritura_sobre_otro_gimnasio_responden_404(self):
        casos = [
            ("get", f"/api/v1/pagos/{self.pago_b.pk}/", None),
            ("get", f"/api/v1/gastos/{self.gasto_b.pk}/", None),
            ("get", f"/api/v1/membresias/{self.membresia_b.pk}/", None),
            ("get", f"/api/v1/clientes/{self.cliente_b.pk}/", None),
            ("get", f"/api/v1/usuarios/{self.admin_b.pk}/", None),
            ("get", f"/api/v1/asistencias/{self.asistencia_b.pk}/", None),
            ("patch", f"/api/v1/gastos/{self.gasto_b.pk}/", {"valor": "1"}),
            ("patch", f"/api/v1/usuarios/{self.admin_b.pk}/", {"nombre": "Hackeado"}),
            ("delete", f"/api/v1/pagos/{self.pago_b.pk}/", None),
            ("post", f"/api/v1/membresias/{self.membresia_b.pk}/renovar/", {"meses": 1}),
            ("post", f"/api/v1/membresias/{self.membresia_b.pk}/congelar/", {"dias": 5}),
            ("post", f"/api/v1/alertas/{self.alerta_b.pk}/marcar-leida/", {}),
        ]
        for metodo, ruta, datos in casos:
            with self.subTest(metodo=metodo, ruta=ruta):
                respuesta = getattr(self.client, metodo)(ruta, datos, format="json")
                self.assertEqual(respuesta.status_code, 404, respuesta.data)
        self.gasto_b.refresh_from_db()
        self.pago_b.refresh_from_db()
        self.assertEqual(self.gasto_b.valor, Decimal("777000"))
        self.assertIsNone(self.pago_b.deleted_at)
        self.assertEqual(Usuario.objects.get(pk=self.admin_b.pk).nombre, "admin.b")

    def test_restaurar_un_registro_de_otro_gimnasio_responde_404(self):
        self.gasto_b.soft_delete()
        respuesta = self.client.post(f"/api/v1/gastos/{self.gasto_b.pk}/restaurar/")
        self.assertEqual(respuesta.status_code, 404, respuesta.data)
        self.gasto_b.refresh_from_db()
        self.assertIsNotNone(self.gasto_b.deleted_at)

    def test_no_se_pueden_referenciar_registros_de_otro_gimnasio(self):
        hoy = timezone.localdate().isoformat()
        casos = [
            ("/api/v1/pagos/", {"cliente": self.cliente_b.pk, "concepto": "matricula", "valor": "5000", "metodo_pago": self.metodo_a.pk}, "cliente"),
            ("/api/v1/pagos/", {"cliente": self.cliente_a.pk, "concepto": "matricula", "valor": "5000", "metodo_pago": self.metodo_b.pk}, "metodo_pago"),
            ("/api/v1/pagos/", {"cliente": self.cliente_a.pk, "membresia": self.membresia_b.pk, "concepto": "membresia", "valor": "5000", "metodo_pago": self.metodo_a.pk}, "membresia"),
            ("/api/v1/gastos/", {"descripcion": "x", "categoria": self.categoria_b.pk, "valor": "5000", "fecha": hoy, "metodo_pago": self.metodo_a.pk}, "categoria"),
            ("/api/v1/membresias/", {"cliente": self.cliente_b.pk, "nombre": "x", "precio": "1", "fecha_inicio": hoy, "fecha_fin": hoy}, "cliente"),
            ("/api/v1/asistencias/", {"cliente": self.cliente_b.pk, "entrada_at": timezone.now().isoformat()}, "cliente"),
        ]
        antes = (Pago.objects.count(), Gasto.objects.count(), Membresia.objects.count(), Asistencia.objects.count())
        for ruta, datos, campo in casos:
            with self.subTest(ruta=ruta, campo=campo):
                respuesta = self.client.post(ruta, datos, format="json")
                self.assertEqual(respuesta.status_code, 400, respuesta.data)
                self.assertIn(campo, respuesta.data["error"]["detalles"])
        despues = (Pago.objects.count(), Gasto.objects.count(), Membresia.objects.count(), Asistencia.objects.count())
        self.assertEqual(antes, despues)

    def test_el_gimnasio_de_un_registro_nuevo_sale_de_la_sesion(self):
        respuesta = self.client.post(
            "/api/v1/gastos/",
            {
                "descripcion": "Intento de escribir en B",
                "categoria": CategoriaGasto.objects.get(gimnasio=self.gym_a, nombre="Arriendo").pk,
                "valor": "5000",
                "fecha": timezone.localdate().isoformat(),
                "metodo_pago": self.metodo_a.pk,
                "gimnasio": self.gym_b.pk,
                "gym_id": self.gym_b.pk,
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(Gasto.objects.get(pk=respuesta.data["id"]).gimnasio, self.gym_a)

        usuario = self.client.post(
            "/api/v1/usuarios/",
            {
                "rol": Rol.objects.get(nombre=Rol.Nombre.RECEPCIONISTA).pk,
                "nombre": "Nueva recepción",
                "correo": "recepcion.nueva@example.com",
                "contrasena": "UnaClaveSegura123",
                "gimnasio": self.gym_b.pk,
                "perfil": {},
            },
            format="json",
        )
        self.assertEqual(usuario.status_code, 201, usuario.data)
        self.assertEqual(Usuario.objects.get(pk=usuario.data["id"]).gimnasio, self.gym_a)

    def test_estadisticas_dashboard_y_exportacion_no_suman_otro_gimnasio(self):
        estadisticas = self.client.get("/api/v1/pagos/estadisticas/")
        self.assertEqual(Decimal(estadisticas.data["total_ingresos"]), Decimal("10000"))
        gastos = self.client.get("/api/v1/gastos/estadisticas/")
        self.assertEqual(Decimal(gastos.data["total_gastos"]), Decimal("0"))

        dashboard = self.client.get("/api/v1/dashboard/")
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        financieras = dashboard.data["metricas_financieras"]
        self.assertEqual(financieras["ingresos"]["mes"], 10000.0)
        self.assertEqual(financieras["gastos"]["mes"], 0.0)
        self.assertEqual(dashboard.data["metricas_clientes"]["total_registrados"], 1)
        self.assertNotIn(
            self.alerta_b.pk, [alerta["id"] for alerta in dashboard.data["alertas_recientes"]]
        )

        exportado = self.client.get("/api/v1/gastos/exportar/").content.decode()
        self.assertNotIn("Arriendo secreto del Norte", exportado)
        conteos = self.client.get("/api/v1/conteos/").data
        self.assertEqual(conteos.get("pagos"), 1)

    def test_auditoria_y_resumen_no_muestran_otro_gimnasio(self):
        self._autenticar(self.admin_b)
        self.client.patch(f"/api/v1/gastos/{self.gasto_b.pk}/", {"observaciones": "ok"}, format="json")
        self.assertTrue(EventoAuditoria.objects.filter(actor=self.admin_b).exists())

        self._autenticar(self.admin_a)
        eventos = self.client.get("/api/v1/auditoria/", {"page_size": 200}).data["results"]
        self.assertFalse([e for e in eventos if e.get("actor") == self.admin_b.pk])
        resumen = self.client.get("/api/v1/resumen/").data
        self.assertFalse(
            [e for e in resumen["actividad_reciente"] if e.get("actor") == self.admin_b.pk]
        )

    def test_la_matriz_de_permisos_es_de_cada_gimnasio(self):
        rol_cliente = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        antes_b = set(self.cliente_b.usuario.permisos_efectivos())

        respuesta = self.client.put(
            f"/api/v1/roles/{rol_cliente.pk}/permisos/",
            {"permisos": ["gastos:view"]},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertTrue(self.cliente_a.usuario.tiene_permiso("gastos:view"))
        self.assertFalse(self.cliente_b.usuario.tiene_permiso("gastos:view"))
        self.assertEqual(set(self.cliente_b.usuario.permisos_efectivos()), antes_b)
        # Aun con el permiso, el cliente de A no ve gastos de nadie (alcance).
        self.assertFalse(Gasto.objects.filter(gimnasio=self.gym_a).exists())

    def test_roles_personalizados_son_del_gimnasio_y_los_del_sistema_compartidos(self):
        creado = self.client.post("/api/v1/roles/", {"nombre": "caja-a"}, format="json")
        self.assertEqual(creado.status_code, 201, creado.data)
        self.assertFalse(creado.data["es_del_sistema"])
        self.assertEqual(Rol.objects.get(pk=creado.data["id"]).gimnasio, self.gym_a)

        rol_entrenador = Rol.objects.get(nombre=Rol.Nombre.ENTRENADOR)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/roles/{rol_entrenador.pk}/", {"is_active": False}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/roles/{rol_entrenador.pk}/").status_code, 403
        )
        rol_entrenador.refresh_from_db()
        self.assertTrue(rol_entrenador.is_active)

        self._autenticar(self.admin_b)
        self.assertEqual(self.client.get(f"/api/v1/roles/{creado.data['id']}/").status_code, 404)
        self.assertNotIn(creado.data["id"], self._ids("/api/v1/roles/"))
        asignar = self.client.post(
            "/api/v1/usuarios-roles/",
            {"usuario": self.cliente_b.pk, "rol": creado.data["id"]},
            format="json",
        )
        self.assertEqual(asignar.status_code, 400, asignar.data)

    def test_el_ultimo_administrador_se_cuenta_por_gimnasio(self):
        from .serializers import existe_otro_administrador_activo

        self.assertFalse(existe_otro_administrador_activo(self.admin_b))
        self._autenticar(self.admin_b)
        respuesta = self.client.put(
            f"/api/v1/usuarios/{self.admin_b.pk}/roles/",
            {"roles": [], "rol_principal": Rol.objects.get(nombre=Rol.Nombre.CLIENTE).pk},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 400, respuesta.data)

    def test_un_gimnasio_inactivo_no_inicia_sesion_y_pierde_sus_sesiones(self):
        respuesta_b = self._autenticar(self.admin_b)
        token_b = respuesta_b.data["token"]
        self.gym_b.is_active = False
        self.gym_b.save(update_fields=["is_active", "updated_at"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_b}")
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)
        self.client.credentials()
        login = self.client.post(
            "/api/v1/login/", {"correo": self.admin_b.correo, "contrasena": self.CLAVE}, format="json"
        )
        self.assertEqual(login.status_code, 401)

    def test_el_registro_publico_usa_el_codigo_del_gimnasio(self):
        self.client.credentials()
        datos = {"nombre": "Nueva Persona", "contrasena": "UnaClaveSegura123"}

        sin_codigo = self.client.post(
            "/api/v1/registro/", {**datos, "correo": "sin.codigo@example.com"}, format="json"
        )
        self.assertEqual(sin_codigo.status_code, 400, sin_codigo.data)
        self.assertIn("gimnasio", sin_codigo.data["error"]["detalles"])

        invalido = self.client.post(
            "/api/v1/registro/",
            {**datos, "correo": "invalido@example.com", "gimnasio": "no-existe"},
            format="json",
        )
        self.assertEqual(invalido.status_code, 400)

        creado = self.client.post(
            "/api/v1/registro/",
            {**datos, "correo": "norte.nuevo@example.com", "gimnasio": "NORTE"},
            format="json",
        )
        self.assertEqual(creado.status_code, 201, creado.data)
        self.assertEqual(creado.data["usuario"]["gimnasio"]["codigo"], "norte")
        self.assertEqual(Usuario.objects.get(correo="norte.nuevo@example.com").gimnasio, self.gym_b)

    def test_un_gimnasio_nuevo_queda_listo_para_operar(self):
        rol_admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)
        self.assertEqual(MetodoPago.objects.filter(gimnasio=self.gym_b).count(), 7)
        self.assertEqual(CategoriaGasto.objects.filter(gimnasio=self.gym_b).count(), 9)
        self.assertEqual(
            RolPermiso.objects.filter(rol=rol_admin, gimnasio=self.gym_b).count(),
            RolPermiso.objects.filter(rol=rol_admin, gimnasio=None).count(),
        )
        self.assertTrue(self.admin_b.tiene_permiso("gastos:create"))
        me = self._autenticar(self.admin_b).data["usuario"]
        self.assertEqual(me["gimnasio"]["nombre"], "Gimnasio Norte")

    def test_la_plataforma_ve_todos_los_gimnasios(self):
        plataforma = APIClient()
        get_user_model().objects.create_superuser(
            username="plataforma", email="plataforma@example.com", password="ClavePlataforma123"
        )
        self.assertTrue(plataforma.login(username="plataforma", password="ClavePlataforma123"))
        ids = {
            fila["id"]
            for fila in plataforma.get("/api/v1/pagos/", {"page_size": 200}).data["results"]
        }
        self.assertEqual(ids, {self.pago_a.pk, self.pago_b.pk})


class CentroAlertasYConfiguracionTests(APITestCase):
    """Configuración por gimnasio y reglas del centro de alertas."""

    CLAVE = "ClaveSegura-2026"

    def setUp(self):
        cache.clear()
        self.gimnasio = gimnasio_principal()
        self.otro = Gimnasio.objects.create(nombre="Otro Gimnasio", codigo="otro")
        self.admin = self._usuario(Rol.Nombre.ADMINISTRADOR, "admin.alertas@example.com")
        self.usuario_cliente = self._usuario(Rol.Nombre.CLIENTE, "cliente.alertas@example.com")
        self.cliente = Cliente.objects.create(usuario=self.usuario_cliente)
        self.metodo = MetodoPago.objects.get(gimnasio=self.gimnasio, nombre="Efectivo")
        self.categoria = CategoriaGasto.objects.get(gimnasio=self.gimnasio, nombre="Arriendo")
        self.hoy = timezone.localdate()
        self._autenticar(self.admin)

    def _usuario(self, rol, correo, gimnasio=None):
        usuario = Usuario(
            gimnasio=gimnasio or self.gimnasio,
            rol=Rol.objects.get(nombre=rol),
            nombre=correo.split("@")[0],
            correo=correo,
        )
        usuario.set_password(self.CLAVE)
        usuario.save()
        return usuario

    def _autenticar(self, usuario):
        self.client.credentials()
        respuesta = self.client.post(
            "/api/v1/login/", {"correo": usuario.correo, "contrasena": self.CLAVE}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")

    def _alertas(self, tipo):
        return Alerta.objects.filter(gimnasio=self.gimnasio, tipo=tipo)

    def test_configuracion_del_gimnasio_propio(self):
        respuesta = self.client.get("/api/v1/gimnasio/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["codigo"], "principal")

        cambio = self.client.patch(
            "/api/v1/gimnasio/",
            {
                "nombre": "Gym Centro",
                "dias_inactividad_alerta": 10,
                "limite_gastos_mensual": "2000000",
                "porcentaje_caida_ingresos": 25,
                "codigo": "robado",
                "is_active": False,
            },
            format="json",
        )
        self.assertEqual(cambio.status_code, 200, cambio.data)
        self.gimnasio.refresh_from_db()
        self.assertEqual(self.gimnasio.nombre, "Gym Centro")
        self.assertEqual(self.gimnasio.dias_inactividad_alerta, 10)
        self.assertEqual(self.gimnasio.codigo, "principal")
        self.assertTrue(self.gimnasio.is_active)
        self.otro.refresh_from_db()
        self.assertEqual(self.otro.nombre, "Otro Gimnasio")
        self.assertTrue(
            EventoAuditoria.objects.filter(recurso="gimnasio", accion="actualizar-configuracion").exists()
        )

        for datos in ({"dias_inactividad_alerta": 0}, {"porcentaje_caida_ingresos": 150}, {"limite_gastos_mensual": "-5"}):
            with self.subTest(datos=datos):
                self.assertEqual(self.client.patch("/api/v1/gimnasio/", datos, format="json").status_code, 400)

        self._autenticar(self.usuario_cliente)
        self.assertEqual(self.client.get("/api/v1/gimnasio/").status_code, 200)
        self.assertEqual(
            self.client.patch("/api/v1/gimnasio/", {"nombre": "x"}, format="json").status_code, 403
        )

    def test_alerta_de_cliente_que_dejo_de_asistir(self):
        from .alertas import generar_alertas

        Membresia.objects.create(
            cliente=self.cliente, nombre="Mensual", precio=Decimal("80000"),
            fecha_inicio=self.hoy - timedelta(days=5), fecha_fin=self.hoy + timedelta(days=25),
            registrado_por=self.admin,
        )
        entrada = timezone.now() - timedelta(days=20)
        Asistencia.objects.create(cliente=self.cliente, entrada_at=entrada, salida_at=entrada + timedelta(hours=1))

        self.assertEqual(generar_alertas(self.gimnasio)["clientes_inactivos"], 1)
        self.assertEqual(generar_alertas(self.gimnasio)["clientes_inactivos"], 0)
        alerta = self._alertas(Alerta.Tipo.CLIENTE_INACTIVO).get()
        self.assertEqual(alerta.cliente, self.cliente)

        # Con un umbral mayor que la ausencia no se alerta.
        Alerta.objects.all().delete()
        self.gimnasio.dias_inactividad_alerta = 30
        self.gimnasio.save()
        self.assertEqual(generar_alertas(self.gimnasio)["clientes_inactivos"], 0)

    def test_alerta_de_ingresos_bajos_frente_al_mes_anterior(self):
        from .alertas import generar_alertas

        inicio_mes = self.hoy.replace(day=1)
        mes_cerrado = (inicio_mes - timedelta(days=1)).replace(day=15)
        mes_previo = (mes_cerrado.replace(day=1) - timedelta(days=1)).replace(day=15)
        for fecha, valor in ((mes_previo, "1000000"), (mes_cerrado, "400000")):
            Pago.objects.create(
                cliente=self.cliente, concepto=Pago.Concepto.MEMBRESIA, valor=Decimal(valor),
                metodo_pago=self.metodo, registrado_por=self.admin,
                fecha_pago=timezone.make_aware(datetime.combine(fecha, time(10))),
            )

        self.assertEqual(generar_alertas(self.gimnasio)["ingresos_bajos"], 1)
        self.assertEqual(generar_alertas(self.gimnasio)["ingresos_bajos"], 0)
        alerta = self._alertas(Alerta.Tipo.INGRESOS_BAJOS).get()
        self.assertEqual(alerta.datos_adicionales["caida_porcentaje"], 60.0)
        self.assertIn("$ 400.000", alerta.mensaje)

    def test_alerta_de_gastos_sobre_el_limite_y_de_gasto_nuevo(self):
        self.gimnasio.limite_gastos_mensual = Decimal("500000")
        self.gimnasio.save()

        respuesta = self.client.post(
            "/api/v1/gastos/",
            {
                "descripcion": "Arriendo de noviembre",
                "categoria": self.categoria.pk,
                "valor": "600000",
                "fecha": self.hoy.isoformat(),
                "metodo_pago": self.metodo.pk,
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        nuevo = self._alertas(Alerta.Tipo.NUEVO_GASTO).get()
        self.assertEqual(nuevo.gasto_id, respuesta.data["id"])

        alertas = self.client.get("/api/v1/alertas/").data["results"]
        tipos = [alerta["tipo"] for alerta in alertas]
        self.assertIn(Alerta.Tipo.GASTOS_ALTOS, tipos)
        # La crítica va primero.
        self.assertEqual(alertas[0]["tipo"], Alerta.Tipo.GASTOS_ALTOS)
        self.client.get("/api/v1/alertas/")
        self.assertEqual(self._alertas(Alerta.Tipo.GASTOS_ALTOS).count(), 1)

    def test_alerta_de_pago_pendiente_se_cierra_al_completarlo(self):
        from .alertas import generar_alertas

        pago = Pago.objects.create(
            cliente=self.cliente, concepto=Pago.Concepto.MEMBRESIA, valor=Decimal("80000"),
            metodo_pago=self.metodo, registrado_por=self.admin, estado=Pago.Estado.PENDIENTE,
        )
        self.assertEqual(generar_alertas(self.gimnasio)["pagos_pendientes"], 1)
        self.assertEqual(generar_alertas(self.gimnasio)["pagos_pendientes"], 0)

        pago.estado = Pago.Estado.COMPLETADO
        pago.save()
        generar_alertas(self.gimnasio)
        self.assertTrue(self._alertas(Alerta.Tipo.PAGOS_PENDIENTES).get().leida)

    def test_las_alertas_se_generan_solo_para_el_propio_gimnasio(self):
        cliente_otro = Cliente.objects.create(
            usuario=self._usuario(Rol.Nombre.CLIENTE, "cliente.otro@example.com", gimnasio=self.otro)
        )
        Pago.objects.create(
            cliente=cliente_otro, concepto=Pago.Concepto.MATRICULA, valor=Decimal("1"),
            metodo_pago=MetodoPago.objects.get(gimnasio=self.otro, nombre="Efectivo"),
            registrado_por=self._usuario(Rol.Nombre.ADMINISTRADOR, "admin.otro@example.com", gimnasio=self.otro),
            estado=Pago.Estado.PENDIENTE,
        )
        self.client.get("/api/v1/alertas/")
        self.assertFalse(Alerta.objects.filter(gimnasio=self.otro).exists())

    def test_comando_generar_alertas_recorre_los_gimnasios(self):
        Pago.objects.create(
            cliente=self.cliente, concepto=Pago.Concepto.MEMBRESIA, valor=Decimal("1000"),
            metodo_pago=self.metodo, registrado_por=self.admin, estado=Pago.Estado.PENDIENTE,
        )
        salida = StringIO()
        call_command("generar_alertas", stdout=salida)
        self.assertIn("pagos_pendientes: 1", salida.getvalue())
        self.assertIn("Otro Gimnasio", salida.getvalue())


class ReportesTests(EscenarioDosGimnasios):
    """Reportes Excel/PDF con datos reales y aislados por gimnasio."""

    TIPOS = ("financiero", "ingresos", "gastos", "asistencia", "clientes", "membresias", "crecimiento")

    def setUp(self):
        super().setUp()
        hoy = timezone.localdate()
        self.rango = {"fecha_desde": hoy.replace(day=1).isoformat(), "fecha_hasta": hoy.isoformat()}
        categoria_a = CategoriaGasto.objects.get(gimnasio=self.gym_a, nombre="Arriendo")
        Gasto.objects.create(
            descripcion="Arriendo sede A", categoria=categoria_a, valor=Decimal("4000"),
            fecha=hoy, metodo_pago=self.metodo_a, registrado_por=self.admin_a,
        )
        Gasto.objects.create(
            descripcion="Gasto anulado A", categoria=categoria_a, valor=Decimal("500000"),
            fecha=hoy, metodo_pago=self.metodo_a, registrado_por=self.admin_a,
            estado=Gasto.Estado.CANCELADO,
        )
        Asistencia.objects.create(cliente=self.cliente_a, entrada_at=timezone.now() - timedelta(minutes=30))

    def _descargar(self, tipo, formato, **extra):
        return self.client.get(f"/api/v1/reportes/{tipo}/", {**self.rango, "formato": formato, **extra})

    def _libro(self, respuesta):
        from openpyxl import load_workbook

        return load_workbook(BytesIO(respuesta.content))

    def _textos(self, libro):
        return [
            str(celda)
            for hoja in libro.worksheets
            for fila in hoja.iter_rows(values_only=True)
            for celda in fila
            if celda is not None
        ]

    def test_todos_los_reportes_se_generan_en_excel_y_pdf(self):
        for tipo in self.TIPOS:
            excel = self._descargar(tipo, "xlsx")
            self.assertEqual(excel.status_code, 200, tipo)
            self.assertEqual(
                excel["Content-Type"],
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            self.assertIn(f"reporte_{tipo}_", excel["Content-Disposition"])
            self.assertGreater(len(self._libro(excel).worksheets), 1, tipo)

            pdf = self._descargar(tipo, "pdf")
            self.assertEqual(pdf.status_code, 200, tipo)
            self.assertEqual(pdf["Content-Type"], "application/pdf")
            self.assertTrue(pdf.content.startswith(b"%PDF"), tipo)
        self.assertEqual(
            EventoAuditoria.objects.filter(accion="exportar-reporte", actor=self.admin_a).count(),
            len(self.TIPOS) * 2,
        )

    def test_reporte_financiero_usa_cifras_reales_sin_anulados(self):
        libro = self._libro(self._descargar("financiero", "xlsx"))
        resumen = {
            fila[0]: fila[1]
            for fila in libro["Resumen"].iter_rows(min_row=8, values_only=True)
            if fila[0]
        }
        self.assertEqual(resumen["Ingresos completados"], 10000)
        self.assertEqual(resumen["Gastos"], 4000)
        self.assertEqual(resumen["Ganancia neta"], 6000)

    def test_reportes_no_incluyen_datos_de_otro_gimnasio(self):
        for tipo in self.TIPOS:
            textos = " ".join(self._textos(self._libro(self._descargar(tipo, "xlsx"))))
            self.assertNotIn("Gimnasio Norte", textos, tipo)
            self.assertNotIn("Arriendo secreto del Norte", textos, tipo)
            self.assertNotIn("cliente.b", textos, tipo)
            self.assertNotIn("999000", textos, tipo)
            self.assertNotIn("777000", textos, tipo)

    def test_el_gimnasio_no_se_elige_por_parametro(self):
        # Un administrador de A que pide el gimnasio B por parámetro sigue
        # recibiendo solo su propio gimnasio.
        textos = " ".join(self._textos(self._libro(self._descargar("ingresos", "xlsx", gimnasio="norte"))))
        self.assertIn(self.gym_a.nombre, textos)
        self.assertNotIn("Gimnasio Norte", textos)
        self.assertNotIn("999000", textos)

    def test_cliente_y_anonimo_no_descargan_reportes(self):
        self._autenticar(self.cliente_a.usuario)
        self.assertEqual(self._descargar("financiero", "xlsx").status_code, 403)
        self.client.credentials()
        self.assertEqual(self._descargar("financiero", "pdf").status_code, 401)

    def test_parametros_invalidos_responden_400_o_404(self):
        self.assertEqual(self._descargar("financiero", "docx").status_code, 400)
        self.assertEqual(self._descargar("inventado", "xlsx").status_code, 404)
        respuesta = self.client.get(
            "/api/v1/reportes/ingresos/",
            {"fecha_desde": "2026-05-10", "fecha_hasta": "2026-05-01"},
        )
        self.assertEqual(respuesta.status_code, 400)
        respuesta = self.client.get("/api/v1/reportes/ingresos/", {"fecha_desde": "10/05/2026"})
        self.assertEqual(respuesta.status_code, 400)


class ErroresPorCampoAltaUsuarioTests(EscenarioDosGimnasios):
    """El alta de usuarios devuelve cada error en su campo y en español."""

    def _alta(self, **cambios):
        datos = {
            "rol": Rol.objects.get(nombre="cliente").id,
            "nombre": "Angie Cantillo",
            "correo": "angie.nueva@example.com",
            "telefono": "3015478525",
            "contrasena": "Fuerte2026!",
            "is_active": True,
            "perfil": {
                "tipo_documento": "CC",
                "numero_documento": "1548652874",
                "fecha_nacimiento": "2008-01-26",
                "peso_kg": "52",
                "estatura_cm": "171",
            },
        }
        perfil = cambios.pop("perfil", None)
        datos.update(cambios)
        if perfil is not None:
            datos["perfil"] = perfil
        return self.client.post("/api/v1/usuarios/", datos, format="json")

    def test_alta_valida_crea_cliente(self):
        respuesta = self._alta()
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(Usuario.objects.get(correo="angie.nueva@example.com").gimnasio, self.gym_a)

    def test_contrasena_parecida_al_nombre_se_explica_en_su_campo(self):
        respuesta = self._alta(contrasena="angie123")
        self.assertEqual(respuesta.status_code, 400)
        mensajes = " ".join(respuesta.data["error"]["detalles"]["contrasena"])
        self.assertIn("al nombre", mensajes)
        self.assertNotIn("first_name", mensajes)

    def test_todos_los_errores_llegan_juntos(self):
        respuesta = self._alta(correo=self.admin_a.correo, contrasena="12345678")
        self.assertEqual(respuesta.status_code, 400)
        detalles = respuesta.data["error"]["detalles"]
        self.assertIn("correo", detalles)
        self.assertIn("contrasena", detalles)

    def test_correo_repetido_tiene_mensaje_claro(self):
        respuesta = self._alta(correo=self.admin_a.correo)
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(
            respuesta.data["error"]["detalles"]["correo"], ["Ya existe un usuario con este correo."]
        )

    def test_errores_del_perfil_quedan_en_su_campo(self):
        self.assertEqual(self._alta().status_code, 201)
        respuesta = self._alta(
            correo="otra@example.com",
            perfil={
                "tipo_documento": "cc",
                "numero_documento": "1548652874",
                "fecha_nacimiento": "2999-01-01",
                "peso_kg": "-5",
            },
        )
        self.assertEqual(respuesta.status_code, 400)
        perfil = respuesta.data["error"]["detalles"]["perfil"]
        self.assertIn("numero_documento", perfil)
        self.assertIn("fecha_nacimiento", perfil)
        self.assertIn("peso_kg", perfil)
        self.assertNotIn("uq_cliente_documento_lower", str(perfil))

    def test_administrador_elige_otro_rol_y_cliente_no_puede_crear(self):
        entrenador = Rol.objects.get(nombre="entrenador")
        respuesta = self._alta(correo="coach.nuevo@example.com", rol=entrenador.id, perfil={})
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(Usuario.objects.get(correo="coach.nuevo@example.com").rol, entrenador)

        self._autenticar(self.cliente_a.usuario)
        respuesta = self._alta(correo="intruso@example.com")
        self.assertIn(respuesta.status_code, (400, 403))
        self.assertFalse(Usuario.objects.filter(correo="intruso@example.com").exists())


class PlanesEntrenamientoConMusculosTests(EscenarioDosGimnasios):
    """Entrenador arma planes por día con músculos e imágenes; el cliente los ve."""

    def setUp(self):
        super().setUp()
        self._carpeta = TemporaryDirectory()
        self.addCleanup(self._carpeta.cleanup)
        ajustes = self.settings(PRIVATE_MEDIA_ROOT=self._carpeta.name)
        ajustes.enable()
        self.addCleanup(ajustes.disable)

        rol_entrenador = Rol.objects.get(nombre="entrenador")
        self.entrenador = Entrenador.objects.create(
            usuario=self._usuario(self.gym_a, rol_entrenador, "coach.a@example.com")
        )
        self.otro_entrenador = Entrenador.objects.create(
            usuario=self._usuario(self.gym_a, rol_entrenador, "coach.otro@example.com")
        )
        hoy = timezone.localdate()
        for entrenador in (self.entrenador, self.otro_entrenador):
            ClienteEntrenador.objects.create(
                cliente=self.cliente_a, entrenador=entrenador, fecha_inicio=hoy
            )

    def _png(self):
        buffer = BytesIO()
        Image.new("RGB", (8, 8), (40, 200, 90)).save(buffer, format="PNG")
        return SimpleUploadedFile("press.png", buffer.getvalue(), content_type="image/png")

    def _plan(self, **extra):
        datos = {
            "cliente": self.cliente_a.pk,
            "entrenador": self.entrenador.pk,
            "nombre": "Empuje-Tirón-Pierna",
            "objetivo": "Hipertrofia",
            "fecha_inicio": timezone.localdate().isoformat(),
            "rutina": {
                "lunes": {"titulo": "Empuje", "musculos": ["pecho", "hombros", "triceps"]},
                "miercoles": {"titulo": "Pierna", "musculos": ["cuadriceps", "gluteos"]},
            },
            **extra,
        }
        return self.client.post("/api/v1/planes-entrenamiento/", datos, format="json")

    def test_entrenador_crea_ejercicio_con_imagen_y_musculos(self):
        self._autenticar(self.entrenador.usuario)
        respuesta = self.client.post(
            "/api/v1/ejercicios/",
            {"nombre": "Press de banca", "grupo_muscular": "Pecho",
             "musculos": '["pecho", "triceps"]', "imagen": self._png()},
            format="multipart",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data["musculos"], ["pecho", "triceps"])
        self.assertTrue(respuesta.data["imagen_url"].endswith("/imagen/"))
        imagen = self.client.get(respuesta.data["imagen_url"])
        self.assertEqual(imagen.status_code, 200)
        self.assertEqual(imagen["Content-Type"], "image/png")
        imagen.close()  # FileResponse deja el archivo abierto; en Windows impide borrarlo.

        ejercicio = Ejercicio.objects.get(pk=respuesta.data["id"])
        self.assertEqual(ejercicio.gimnasio, self.gym_a)
        quitar = self.client.patch(
            f"/api/v1/ejercicios/{ejercicio.pk}/", {"quitar_imagen": True}, format="json"
        )
        self.assertEqual(quitar.status_code, 200, quitar.data)
        self.assertIsNone(quitar.data["imagen_url"])

    def test_quitar_imagen_responde_200_aunque_el_archivo_este_bloqueado(self):
        self._autenticar(self.entrenador.usuario)
        creado = self.client.post(
            "/api/v1/ejercicios/",
            {"nombre": "Remo", "imagen": self._png()},
            format="multipart",
        )
        self.assertEqual(creado.status_code, 201, creado.data)
        bloqueado = PermissionError(32, "El archivo está siendo utilizado por otro proceso")
        with patch("gym.storage.AlmacenamientoFotosPrivadas.delete", side_effect=bloqueado):
            quitar = self.client.patch(
                f"/api/v1/ejercicios/{creado.data['id']}/", {"quitar_imagen": True}, format="json"
            )
        self.assertEqual(quitar.status_code, 200, quitar.data)
        self.assertIsNone(quitar.data["imagen_url"])

    def test_musculos_y_rutina_invalidos_se_rechazan(self):
        self._autenticar(self.entrenador.usuario)
        respuesta = self.client.post(
            "/api/v1/ejercicios/", {"nombre": "Raro", "musculos": ["alas"]}, format="json"
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("musculos", respuesta.data["error"]["detalles"])
        respuesta = self._plan(rutina={"festivo": {"musculos": ["pecho"]}})
        self.assertEqual(respuesta.status_code, 400)
        respuesta = self._plan(rutina={"lunes": {"musculos": ["alas"]}})
        self.assertEqual(respuesta.status_code, 400)

    def test_entrenador_crea_plan_por_dia_solo_a_su_nombre(self):
        self._autenticar(self.entrenador.usuario)
        respuesta = self._plan()
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data["rutina"]["lunes"]["musculos"], ["pecho", "hombros", "triceps"])
        ajeno = self._plan(entrenador=self.otro_entrenador.pk, nombre="Otro")
        self.assertEqual(ajeno.status_code, 400)
        self.assertIn("entrenador", ajeno.data["error"]["detalles"])

    def test_plan_guarda_musculos_detallados_del_modelo_3d(self):
        """Los músculos individuales del modelo anatómico se guardan tal cual y
        los grupos antiguos siguen siendo válidos en la misma lista."""
        from .models import GRUPOS_MUSCULARES, MUSCULOS, MUSCULOS_DETALLADOS

        for codigo, (_nombre, grupo) in MUSCULOS_DETALLADOS.items():
            self.assertIn(grupo, GRUPOS_MUSCULARES, codigo)
            self.assertIn(codigo, MUSCULOS)
        self._autenticar(self.entrenador.usuario)
        musculos = ["pectoral_mayor", "deltoides_anterior", "triceps_braquial", "pecho"]
        respuesta = self._plan(rutina={"lunes": {"titulo": "Empuje", "musculos": musculos}})
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data["rutina"]["lunes"]["musculos"], musculos)
        respuesta = self.client.post(
            "/api/v1/ejercicios/",
            {"nombre": "Sentadilla frontal", "musculos": ["recto_femoral", "vasto_lateral", "gluteo_mayor"]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data["musculos"], ["recto_femoral", "vasto_lateral", "gluteo_mayor"])
        repetidos = self._plan(rutina={"lunes": {"musculos": ["soleo", "soleo"]}})
        self.assertEqual(repetidos.status_code, 400)

    def test_administrador_elige_entrenador_asignado(self):
        respuesta = self._plan(entrenador=self.otro_entrenador.pk)
        self.assertEqual(respuesta.status_code, 201, respuesta.data)

    def test_cliente_ve_su_plan_y_la_imagen_pero_no_puede_crearlo(self):
        ejercicio = Ejercicio.objects.create(
            gimnasio=self.gym_a, nombre="Press militar", musculos=["hombros"], imagen=self._png()
        )
        self._autenticar(self.entrenador.usuario)
        plan_id = self._plan().data["id"]
        fila = self.client.post(
            "/api/v1/planes-entrenamiento-ejercicios/",
            {"plan": plan_id, "ejercicio": ejercicio.pk, "dia_semana": "lunes", "orden": 1,
             "series": 4, "repeticiones": 10},
            format="json",
        )
        self.assertEqual(fila.status_code, 201, fila.data)

        self._autenticar(self.cliente_a.usuario)
        planes = self.client.get("/api/v1/planes-entrenamiento/").data["results"]
        self.assertEqual([plan["id"] for plan in planes], [plan_id])
        filas = self.client.get("/api/v1/planes-entrenamiento-ejercicios/", {"plan": plan_id}).data["results"]
        url = filas[0]["ejercicio_detalle"]["imagen_url"]
        self.assertIn("/planes-entrenamiento-ejercicios/", url)
        imagen = self.client.get(url)
        self.assertEqual(imagen.status_code, 200)
        imagen.close()  # Libera el archivo para que se pueda borrar el directorio temporal.
        self.assertEqual(self.client.get(f"/api/v1/ejercicios/{ejercicio.pk}/imagen/").status_code, 403)
        self.assertEqual(self._plan().status_code, 403)
