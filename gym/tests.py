from rest_framework.test import APITestCase

from .models import Cliente, Rol, Usuario


class GymApiTests(APITestCase):
    def crear_cliente(self):
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

    def test_roles_iniciales_y_rutas_crud_disponibles(self):
        self.assertEqual(Rol.objects.count(), 5)
        for ruta in ("roles", "usuarios", "clientes", "asistencias", "planes-entrenamiento", "notificaciones"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(f"/api/{ruta}/").status_code, 200)

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
