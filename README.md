# Gym Control Pro API

Backend REST construido con Django y Django REST Framework a partir de `gym_control_pro.sql`. Incluye los 17 recursos del esquema: identidad y perfiles, asistencia, entrenamiento, nutrición y notificaciones.

## Instalación y arranque

Requiere Python 3.12 o posterior.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

La API queda disponible en `http://127.0.0.1:8000/api/` y responde únicamente JSON. La migración crea los cinco roles del esquema (`cliente`, `entrenador`, `terapeuta`, `recepcionista` y `administrador`).

## Inicio de sesión

Envía el correo y la contraseña a `POST /api/login/`. Si las credenciales son válidas y la cuenta y su rol están activos, la respuesta incluye los datos públicos del usuario y su perfil asociado. Las contraseñas y sus hashes nunca se devuelven.

```json
{
  "correo": "ana@example.com",
  "contrasena": "UnaClaveSegura123"
}
```

Este endpoint solo valida las credenciales; no genera una sesión ni un token. Los demás endpoints de la API permanecen abiertos, como está configurado actualmente.

## Endpoints

Todos los recursos ofrecen `GET` de lista/detalle, `POST`, `PUT`, `PATCH` y `DELETE`. Los `DELETE` de los recursos históricos son lógicos, por lo que el dato queda preservado y deja de aparecer en las consultas normales.

- `/api/roles/`, `/api/usuarios/`
- `/api/clientes/`, `/api/entrenadores/`, `/api/terapeutas/`, `/api/recepcionistas/`, `/api/administradores/`
- `/api/asignaciones-cliente-entrenador/`, `/api/asistencias/`, `/api/entrenamientos/`
- `/api/ejercicios/`, `/api/planes-entrenamiento/`, `/api/planes-entrenamiento-ejercicios/`
- `/api/planes-alimentacion/`, `/api/comidas/`, `/api/registros-comida/`, `/api/notificaciones/`

Al crear un usuario se debe incluir la contraseña temporalmente en `contrasena` (nunca se devuelve) y un objeto `perfil` del rol indicado. La operación es atómica: no se conservará el usuario si el perfil no cumple sus validaciones. La contraseña se almacena con Argon2id, nunca en texto plano.

```json
{
  "rol": 1,
  "nombre": "Ana Gómez",
  "correo": "ana@example.com",
  "contrasena": "UnaClaveSegura123",
  "perfil": {
    "tipo_documento": "CC",
    "numero_documento": "123456789",
    "objetivo": "Mejorar resistencia"
  }
}
```

## Base de datos y configuración

Por defecto se usa SQLite, para que el proyecto pueda ejecutarse de inmediato. Para usar MySQL 8 y mantener el motor del archivo SQL, cree la base de datos y defina estas variables antes de migrar:

```powershell
$env:DB_ENGINE = "mysql"
$env:DB_NAME = "gym_control_pro"
$env:DB_USER = "root"
$env:DB_PASSWORD = "su_clave"
$env:DB_HOST = "127.0.0.1"
python manage.py migrate
```

CORS está abierto mientras `DJANGO_DEBUG=true`, pensado para el frontend local. En producción use `DJANGO_DEBUG=false`, una `DJANGO_SECRET_KEY` segura, `DJANGO_ALLOWED_HOSTS` y `CORS_ALLOWED_ORIGINS` (orígenes separados por comas). La API inicial no incorpora autenticación/autorización porque el esquema aportado no define el flujo de inicio de sesión; antes de publicarla, configure una política DRF basada en los roles existentes.
