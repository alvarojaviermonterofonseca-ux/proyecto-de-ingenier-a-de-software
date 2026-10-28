# Gym Control Pro API

Backend REST construido con Django y Django REST Framework a partir de `gym_control_pro.sql`. Incluye identidad y perfiles, asignaciones cliente-entrenador y cliente-terapeuta, asistencia, entrenamiento, nutrición y notificaciones.

## Instalación y arranque

Requiere Python 3.12 o posterior.

El código Django está en `backend/`, la SPA Angular y el panel legado en `frontend/`, el entorno virtual en `venv/` y las bases SQLite en `base de datos/`.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python backend\manage.py migrate
python backend\manage.py crear_administrador_gym --nombre "Administrador" --correo admin@example.com
python backend\manage.py sembrar_datos_demo --cantidad 100
python backend\manage.py runserver
```

El comando de administrador solicita la contraseña de forma oculta y crea la primera cuenta con acceso a la API.

`sembrar_datos_demo` crea 100 cuentas de demostración, 20 por cada rol, con todos los campos de sus perfiles y registros relacionados en asistencias, entrenamientos, planes, comidas, registros y notificaciones. No duplica los datos si se ejecuta otra vez. Las cuentas usan correos como `demo.usuario001@gymcontrol.local` y la contraseña predeterminada `DemoGym2026!` (puede cambiarse con `--contrasena`).

Para crear una base SQLite independiente con 100 cuentas para cada uno de los cinco roles (500 usuarios en total), ejecuta en PowerShell desde la raíz del proyecto:

```powershell
$env:DB_ENGINE = "sqlite"
$env:DB_NAME = Join-Path $PWD "base de datos\gym_control_pro_100.sqlite3"
python backend\manage.py migrate
python backend\manage.py sembrar_datos_demo --por-rol 100
python backend\manage.py runserver
```

Mantén las variables `DB_ENGINE` y `DB_NAME` definidas en la misma terminal donde ejecutas `runserver` para que Django use esa base. Puedes iniciar sesión con las cuentas demo usando la contraseña indicada por el comando (por defecto, `DemoGym2026!`). Esta contraseña compartida es solo para pruebas locales; no publiques la base ni uses las cuentas demo en producción. El archivo de base generado está excluido de Git.

La API queda disponible en `http://127.0.0.1:8000/api/v1/`; las respuestas de datos son JSON y el navegador de DRF solo se muestra cuando se solicita HTML. La migración crea los cinco roles del esquema (`cliente`, `entrenador`, `terapeuta`, `recepcionista` y `administrador`).

## Versionado, documentación y errores

- La versión canónica de la API es `/api/v1/`. La ruta `/api/` se mantiene como alias de compatibilidad para el panel y clientes antiguos.
- `GET /api/v1/schema/` expone el contrato OpenAPI 3 y `GET /api/v1/docs/` la interfaz Swagger UI. También están disponibles en `/api/schema/` y `/api/docs/`.
- Los errores conservan el sobre `{"error": {"codigo", "mensaje", "detalles"}}` para todas las respuestas, incluidas `429` (límite de intentos) y `500` (error interno).
- Los listados aceptan filtros por campo (`?campo=valor`), búsqueda (`?search=texto`) y ordenación (`?ordering=campo` o `-campo`) según los campos declarados por cada recurso.
- El `DELETE` responde `204` cuando se solicita JSON. Un administrador puede recuperar un registro borrado lógicamente con `POST /api/v1/{recurso}/{id}/restaurar/`.

## Frontend Angular

La interfaz principal es una SPA Angular 19 en `frontend/`. Consume `/api/v1/`, usa el token Bearer en `sessionStorage` y filtra rutas, navegación y acciones con los permisos efectivos de `/api/v1/me/`.

```powershell
cd frontend
npm install
npm run build
```

Con Django iniciado, abre `http://127.0.0.1:8000/app/`. Django sirve el build desde `frontend/dist/gym-control-rbac/browser/` con `baseHref="/app/"` y fallback a `index.html` para las rutas de la SPA. Para desarrollo con recarga y proxy a la API:

```powershell
cd frontend
npm start
```

Abre `http://localhost:4200`; `proxy.conf.json` reenvía `/api` a `http://127.0.0.1:8000`. Si `/app/` devuelve 404, falta ejecutar `npm run build`. Consulta `frontend/README.md` para la arquitectura del cliente.

## Panel web legado

El panel Django anterior sigue disponible en `http://127.0.0.1:8000/panel/`. Inicia sesión con tu correo y contraseña, y selecciona una tabla para consultar sus datos. El panel envía automáticamente el token `Bearer` en todas las solicitudes protegidas; por ello, los endpoints como `/api/v1/entrenadores/` ya no responden 401 por omitir el encabezado. El token se conserva solo en la sesión actual del navegador y se revoca al cerrar sesión.

### Roles y permisos en la interfaz

El RBAC es real y persistente en la base de datos: `Permiso` guarda códigos únicos `recurso:accion`, `RolPermiso` asigna permisos a roles y `UsuarioRol` permite varios roles por usuario con `activo` y `asignado_por`. `Usuario.rol` se conserva como rol principal para login y perfiles, mientras que `Usuario.roles` agrega roles adicionales M:N. Los roles personalizados están permitidos (el nombre ya no usa `choices`); solo los roles base `cliente`, `entrenador`, `terapeuta`, `recepcionista` y `administrador` tienen perfil asociado.

El panel consume `/api/v1/roles/` (cada rol incluye sus códigos de permiso), `/api/v1/me/` (roles y permisos efectivos) y las acciones `PUT /api/v1/roles/{id}/permisos/` y `PATCH /api/v1/usuarios/{id}/roles/`; ya no usa `localStorage`. Cada `ViewSet` declara su recurso y el servidor valida `recurso:accion` según el método HTTP en `backend/gym/permissions.py`, por lo que ocultar un botón no sustituye la autorización del backend.

El RBAC por recurso se complementa con alcance por rol y propiedad, de modo que un permiso concedido no permite consultar datos ajenos por cambiar el identificador de la URL:

- `administrador` y el personal de Django ven todos los recursos.
- `cliente` solo ve su propio usuario, perfil, asignaciones, asistencias, entrenamientos, planes y notificaciones.
- `entrenador` y `terapeuta` solo ven los clientes con una asignación activa y sus datos relacionados.
- `recepcionista` ve los clientes y sus datos operativos; los campos clínicos (`objetivo`, `peso_kg`, `estatura_cm`, `fecha_nacimiento`) no se exponen ni se aceptan en sus ediciones.
- Un usuario sin visibilidad sobre el registro recibe `404`; si carece del permiso de recurso recibe `403`. Nunca se filtra la existencia de datos ajenos.
- Las sesiones se revocan al cambiar contraseña, desactivar la cuenta, cambiar el rol principal, modificar roles adicionales o alterar los permisos de un rol. Cada cambio de roles/permisos queda registrado en `auditoria_eventos` y puede consultarse en `GET /api/v1/auditoria/` como administrador.

La migración `0005` siembra los 90 permisos iniciales (18 recursos × 5 acciones), asigna la política inicial de los cinco roles y rellena `usuario_rol` para los usuarios existentes. La migración `0007` agrega el recurso `clientes-terapeutas` y sus 5 permisos, por lo que el catálogo final tiene 95 permisos. Los roles personalizados se crean con `POST /api/v1/roles/` y no reciben permisos por defecto; asígnalos con `PUT /api/v1/roles/{id}/permisos/`.

La migración `0006` normaliza la identidad: `correo` y `username` se guardan en minúsculas, los campos opcionales vacíos pasan a `NULL` y los únicos de correo, username, documento de cliente y licencia profesional se validan sin distinguir mayúsculas. Al hacer borrado lógico, el correo, username, documento y licencia se reemplazan por valores tumba, de modo que una cuenta nueva puede reutilizar la identidad original sin chocar con el registro histórico.

La migración `0007` agrega `ClienteTerapeuta` y refuerza la integridad relacional: un cliente no puede tener dos asignaciones de entrenador activas ni periodos solapados; solo puede tener una asistencia abierta; los planes de entrenamiento y alimentación exigen que su entrenador o responsable esté asignado activamente al cliente; y un `RegistroComida` solo acepta comidas de un plan de alimentación del mismo cliente. Estas reglas se validan en los modelos y, por tanto, también en la API. Los entrenamientos con entrenador también exigen una asignación activa con el cliente.

Además, las asignaciones cliente-entrenador exigen que cliente y entrenador estén activos; el `revisado_por` de un registro de comida debe ser un entrenador activo asignado al cliente y con permiso `registros-comida:edit`; y las notificaciones solo admiten destinatarios activos, permitiendo al administrador, al propio usuario o a un profesional asignado al cliente. Cada regla se valida en el modelo y se vuelve a comprobar en la API antes de guardar. La validación del revisor solo se ejecuta al crear el registro o al cambiar su cliente o revisor, para no bloquear actualizaciones históricas; el rol base `entrenador` no incluye `registros-comida:edit`, así que un revisor necesita además un rol que conceda ese permiso.

Los serializers separan lectura, alta y edición de usuarios. `perfil` se valida con el serializer tipado del rol indicado, rechaza campos desconocidos o propios de otro rol y se comprueba antes de crear la cuenta; la creación sigue siendo atómica. En actualizaciones, el perfil no se modifica y su campo `usuario` es de solo lectura. Solo el rol `administrador` o el personal de Django puede cambiar `rol` o `is_active`; las asignaciones adicionales se gestionan exclusivamente con `PATCH /api/v1/usuarios/{id}/roles/`, y un no administrador no puede cambiar relaciones de un registro existente ni la contraseña de otra persona. Los campos internos (`id`, marcas de tiempo, `deleted_at` y `contrasena_hash`) nunca son asignables ni se devuelven. Las contraseñas pasan por `AUTH_PASSWORD_VALIDATORS` antes de almacenarse, y al cambiarlas o desactivar la cuenta se revocan todas sus sesiones.

Los listados de usuarios usan un DTO ligero con rol y perfil resumido; el detalle conserva roles y permisos. `/api/v1/me/` expone además `roles_efectivos` y `permisos_efectivos` para el frontend, manteniendo `roles_detalle` y `permisos` por compatibilidad.

## Inicio de sesión

Envía el correo y la contraseña a `POST /api/v1/login/`. Si las credenciales son válidas y la cuenta y su rol están activos, la respuesta incluye los datos públicos del usuario y un token de sesión. Las contraseñas, sus hashes y el token en texto plano nunca se almacenan juntos en la base de datos.

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

Todos los recursos CRUD y `GET /api/v1/me/` requieren una sesión válida. La sesión dura 8 horas por defecto; puede cambiarla con `AUTH_TOKEN_TTL_HOURS`. Para cerrar sesión y revocar el token actual use `POST /api/v1/logout/`; para revocar todas las sesiones de la cuenta use `POST /api/v1/logout/all/`. El login está limitado por IP (`LOGIN_THROTTLE_RATE`, por defecto `10/min`) y responde `429` al superar el límite.

## Endpoints

Todos los recursos ofrecen `GET` de lista/detalle, `POST`, `PUT`, `PATCH` y `DELETE`. Los `DELETE` de los recursos históricos son lógicos, por lo que el dato queda preservado y deja de aparecer en las consultas normales.

### Política de borrado y cascada

Cada `ViewSet` declara `politica_borrado`:

- **Lógico con `deleted_at`:** usuarios, perfiles, asignaciones, asistencias, entrenamientos, ejercicios, planes, comidas, registros de comida y notificaciones. El registro se marca inactivo, conserva su historial y se oculta de la API.
- **Lógico con `is_active`:** roles y permisos. No tienen `deleted_at` en el esquema; el `DELETE` los desactiva y los oculta del catálogo.
- **Físico:** `usuario_rol`, `rol_permiso` y las filas de `PlanEntrenamientoEjercicio`. Son tablas puente o filas de composición sin historial propio.

La restauración es una acción administrativa (`POST /api/v1/{recurso}/{id}/restaurar/`): limpia `deleted_at` y reactiva `is_active` del registro raíz. No se permite eliminar la propia cuenta ni al último administrador activo.

La cascada se ejecuta en una transacción y es idempotente:

- Al borrar un `Usuario` se borra su perfil, se desactivan sus asignaciones de rol, se desactivan sus notificaciones y se eliminan sus sesiones.
- Al borrar un `Cliente` se borra también su `Usuario` y sus asignaciones de entrenador/terapeuta, asistencias, entrenamientos, planes, comidas, registros de comida y notificaciones.
- Al borrar un `Entrenador` o un `Terapeuta` se desactivan sus asignaciones con clientes y su cuenta de usuario. Los planes históricos que ya tenía asignados se conservan.
- Al borrar un `Rol` se desactivan sus asignaciones de usuario; al borrar un `Permiso` deja de concederse aunque siga referenciado por un rol.
- Al borrar un `PlanEntrenamiento` se eliminan físicamente sus filas de ejercicios. Al borrar un `PlanAlimentacion` se desactivan sus comidas; los registros de comida se conservan como historial.

- `POST /api/v1/login/` (público), `POST /api/v1/logout/` y `GET /api/v1/me/`

- `/api/v1/roles/`, `/api/v1/permisos/`, `/api/v1/roles-permisos/`, `/api/v1/usuarios/`, `/api/v1/usuarios-roles/`
- `GET|PUT /api/v1/roles/{id}/permisos/` y `GET|PATCH /api/v1/usuarios/{id}/roles/`
- `/api/v1/clientes/`, `/api/v1/entrenadores/`, `/api/v1/terapeutas/`, `/api/v1/recepcionistas/`, `/api/v1/administradores/`
- `/api/v1/asignaciones-cliente-entrenador/`, `/api/v1/clientes-terapeutas/`, `/api/v1/asistencias/`, `/api/v1/entrenamientos/`
- `/api/v1/ejercicios/`, `/api/v1/planes-entrenamiento/`, `/api/v1/planes-entrenamiento-ejercicios/`
- `/api/v1/planes-alimentacion/`, `/api/v1/comidas/`, `/api/v1/registros-comida/`, `/api/v1/notificaciones/`
- `/api/v1/auditoria/` (solo lectura, administradores)
- `GET /api/v1/registros-comida/{id}/foto/` (foto privada autenticada)

Para consultar los clientes de un terapeuta use `GET /api/v1/clientes/?terapeuta={id}`. Las asignaciones también se pueden filtrar con `GET /api/v1/clientes-terapeutas/?terapeuta={id}&cliente={id}&activo=true`.

Acciones anidadas de solo lectura (respetan el alcance y el RBAC del recurso relacionado):

- `GET /api/v1/clientes/{id}/asistencias/`
- `GET /api/v1/clientes/{id}/planes-entrenamiento/`
- `GET /api/v1/entrenadores/{id}/clientes/`

La auditoría de cambios de identidad y permisos está en `GET /api/v1/auditoria/`, disponible solo para administradores y filtrable por `actor`, `accion`, `recurso` o búsqueda por `objeto_id`.

### Fotos privadas de registros de comida

`RegistroComida.foto` es un `ImageField` privado. Los archivos se guardan en `PRIVATE_MEDIA_ROOT` (por defecto `media/private`), no se publican en `/media/`, `/static/` ni en `MEDIA_URL`, y reciben un nombre opaco generado por el servidor.

- Súbalas con `POST` o `PATCH` en `multipart/form-data` usando el campo `foto`. Se aceptan JPEG, PNG y WebP, hasta 5 MB (`FOTO_REGISTRO_MAX_BYTES`) y 10000 px por lado (`FOTO_REGISTRO_MAX_DIMENSION`).
- El campo de entrada `foto_url` ya no acepta URLs externas. `foto_url` en las respuestas es un valor de solo lectura que apunta a `GET /api/v1/registros-comida/{id}/foto/`.
- Ese endpoint exige el token `Bearer` y el permiso `registros-comida:view`; responde con `Cache-Control: private, no-store` y `X-Content-Type-Options: nosniff`.
- Si una interfaz muestra la imagen con `<img>`, debe descargarla con `fetch` incluyendo el token y usar un `blob:` URL temporal; no incruste directamente la ruta en un atributo público.
- La migración `0008` reemplaza `foto_url` por `foto` y descarta las URLs externas existentes, que no se pueden convertir en archivos privados de forma segura. `Pillow` es una dependencia obligatoria para validar las imágenes.

Al crear un usuario se debe incluir la contraseña temporalmente en `contrasena` (nunca se devuelve) y, si el rol es uno de los cinco base, un objeto `perfil`. Los roles personalizados no requieren perfil. La operación es atómica: no se conservará el usuario si el perfil no cumple sus validaciones. En el alta se pueden enviar roles adicionales en `roles_asignados`; después solo se modifican con `PATCH /api/v1/usuarios/{id}/roles/`. La contraseña se almacena con Argon2id, nunca en texto plano.

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
python backend\manage.py migrate
```

Otras variables útiles: `API_PAGE_SIZE` (tamaño de página, por defecto `25`), `LOGIN_THROTTLE_RATE` (por defecto `10/min`), `AUTH_TOKEN_TTL_HOURS` y `PRIVATE_MEDIA_ROOT`.

CORS está abierto mientras `DJANGO_DEBUG=true`, pensado para el frontend local. En producción use `DJANGO_DEBUG=false`, una `DJANGO_SECRET_KEY` segura, `DJANGO_ALLOWED_HOSTS` y `CORS_ALLOWED_ORIGINS` (orígenes separados por comas).
