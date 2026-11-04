from datetime import date, timedelta
from io import BytesIO
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
from rest_framework.test import APITestCase

from config.env import cargar_env

from .models import (
    Administrador,
    Asistencia,
    Cliente,
    ClienteEntrenador,
    ClienteTerapeuta,
    Comida,
    Ejercicio,
    Entrenador,
    Entrenamiento,
    EventoAuditoria,
    Notificacion,
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
        rol_gestor = Rol.objects.create(nombre="gestor-usuarios")
        for codigo in ("usuarios:view", "usuarios:create", "usuarios:edit"):
            RolPermiso.objects.create(
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
        rol_gestor = Rol.objects.create(nombre="gestor-estado-propio")
        for codigo in ("usuarios:view", "usuarios:edit"):
            RolPermiso.objects.create(
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
        rol_gestor = Rol.objects.create(nombre="gestor-contrasenas")
        for codigo in ("usuarios:view", "usuarios:edit"):
            RolPermiso.objects.create(
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
        self.assertEqual(Permiso.objects.count(), 95)
        admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)
        self.assertEqual(RolPermiso.objects.filter(rol=admin).count(), 95)
        self.assertEqual(
            Recurso.objects.count(),
            Permiso.objects.values("recurso").distinct().count(),
        )
        self.assertEqual(
            RolRecurso.objects.filter(rol=admin).count(),
            Recurso.objects.count(),
        )
        self.autenticar()
        rol_api = self.client.get(f"/api/roles/{admin.pk}/")
        self.assertEqual(rol_api.status_code, 200)
        self.assertIn("usuarios", rol_api.data["recursos"])
        cliente = Rol.objects.get(nombre=Rol.Nombre.CLIENTE)
        codigos = set(
            RolPermiso.objects.filter(rol=cliente).values_list("permiso__codigo", flat=True)
        )
        self.assertIn("clientes:view", codigos)
        self.assertIn("registros-comida:create", codigos)
        self.assertNotIn("usuarios:create", codigos)
        terapeuta = Rol.objects.get(nombre=Rol.Nombre.TERAPEUTA)
        self.assertTrue(
            RolPermiso.objects.filter(
                rol=terapeuta, permiso__codigo="clientes-terapeutas:view"
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
        self.assertEqual(RolPermiso.objects.filter(rol=cliente).count(), 2)
        self.assertTrue(
            RolRecurso.objects.filter(rol=cliente, recurso__nombre="clientes").exists()
        )

    def test_permiso_exige_puente_rol_recurso_activo(self):
        """No basta la concesión por acción: debe existir rol_has_recurso."""
        admin = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)
        puente = RolRecurso.objects.get(rol=admin, recurso__nombre="usuarios")

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

        rol_emisor = Rol.objects.create(nombre="emisor-notificaciones")
        for codigo in ("notificaciones:view", "notificaciones:create"):
            RolPermiso.objects.create(
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
        respuesta_permiso = self.client.delete(
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
        rol = Rol.objects.create(nombre="rol-auditado")
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
