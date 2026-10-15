# Gym Control Pro API

Backend REST construido con Django y Django REST Framework a partir de `gym_control_pro.sql`. Incluye los 17 recursos del esquema: identidad y perfiles, asistencia, entrenamiento, nutrición y notificaciones.

## Instalación y arranque

Requiere Python 3.12 o posterior.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py crear_administrador_gym --nombre "Administrador" --correo admin@example.com
python manage.py sembrar_datos_demo --cantidad 100
python manage.py runserver
```

El comando de administrador solicita la contraseña de forma oculta y crea la primera cuenta con acceso a la API.

`sembrar_datos_demo` crea 100 cuentas de demostración, 20 por cada rol, con todos los campos de sus perfiles y registros relacionados en asistencias, entrenamientos, planes, comidas, registros y notificaciones. No duplica los datos si se ejecuta otra vez. Las cuentas usan correos como `demo.usuario001@gymcontrol.local` y la contraseña predeterminada `DemoGym2026!` (puede cambiarse con `--contrasena`).

Para crear una base SQLite independiente con 100 cuentas para cada uno de los cinco roles (500 usuarios en total), ejecuta en PowerShell desde la raíz del proyecto:

```powershell
$env:DB_ENGINE = "sqlite"
$env:DB_NAME = "$PWD\gym_control_pro_100.sqlite3"
python manage.py migrate
python manage.py sembrar_datos_demo --por-rol 100
python manage.py runserver
```

Mantén las variables `DB_ENGINE` y `DB_NAME` definidas en la misma terminal donde ejecutas `runserver` para que Django use esa base. Puedes iniciar sesión con las cuentas demo usando la contraseña indicada por el comando (por defecto, `DemoGym2026!`). Esta contraseña compartida es solo para pruebas locales; no publiques la base ni uses las cuentas demo en producción. El archivo de base generado está excluido de Git.

La API queda disponible en `http://127.0.0.1:8000/api/` y responde únicamente JSON. La migración crea los cinco roles del esquema (`cliente`, `entrenador`, `terapeuta`, `recepcionista` y `administrador`).

## Panel web

Con el servidor iniciado, abre `http://127.0.0.1:8000/panel/`, inicia sesión con tu correo y contraseña, y selecciona una tabla para consultar sus datos. El panel envía automáticamente el token `Bearer` en todas las solicitudes protegidas; por ello, los endpoints como `/api/entrenadores/` ya no responden 401 por omitir el encabezado. El token se conserva solo en la sesión actual del navegador y se revoca al cerrar sesión.

## Inicio de sesión

Envía el correo y la contraseña a `POST /api/login/`. Si las credenciales son válidas y la cuenta y su rol están activos, la respuesta incluye los datos públicos del usuario y un token de sesión. Las contraseñas, sus hashes y el token en texto plano nunca se almacenan juntos en la base de datos.

```json
{
  "correo": "ana@example.com",
  "contrasena": "UnaClaveSegura123"
}
```

La respuesta contiene `token`, `tipo_token` (`Bearer`) y `expira_at`. Incluya el token en todos los endpoints protegidos:

```http
Authorization: Bearer <token>
```

Todos los recursos CRUD y `GET /api/me/` requieren una sesión válida. La sesión dura 8 horas por defecto; puede cambiarla con `AUTH_TOKEN_TTL_HOURS`. Para cerrar sesión y revocar el token actual use `POST /api/logout/` con el mismo encabezado.

## Endpoints

Todos los recursos ofrecen `GET` de lista/detalle, `POST`, `PUT`, `PATCH` y `DELETE`. Los `DELETE` de los recursos históricos son lógicos, por lo que el dato queda preservado y deja de aparecer en las consultas normales.

- `POST /api/login/` (público), `POST /api/logout/` y `GET /api/me/`

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

CORS está abierto mientras `DJANGO_DEBUG=true`, pensado para el frontend local. En producción use `DJANGO_DEBUG=false`, una `DJANGO_SECRET_KEY` segura, `DJANGO_ALLOWED_HOSTS` y `CORS_ALLOWED_ORIGINS` (orígenes separados por comas).
