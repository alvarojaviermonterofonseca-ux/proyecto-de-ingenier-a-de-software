from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APITestCase

from .models import (
    Administrador,
    Asistencia,
    Cliente,
    ClienteEntrenador,
    Comida,
    Ejercicio,
    Entrenador,
    Entrenamiento,
    Notificacion,
    PlanAlimentacion,
    PlanEntrenamiento,
    PlanEntrenamientoEjercicio,
    Recepcionista,
    RegistroComida,
    Rol,
    Terapeuta,
    Usuario,
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
        rol = Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR)
        self.operador = Usuario(rol=rol, nombre="Operador", correo="operador@example.com")
        self.operador.set_password("OtraClaveSegura123")
        self.operador.full_clean()
        self.operador.save()

    def autenticar(self):
        respuesta = self.client.post(
            "/api/login/",
            {"correo": self.operador.correo, "contrasena": "OtraClaveSegura123"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")
        return respuesta.data["token"]

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
