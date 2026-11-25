# Registro de cambios

Todos los cambios importantes del proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Versionado Semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- Planes de entrenamiento: el entrenador y el administrador arman cada día agregando **varios
  ejercicios a la vez** desde un selector múltiple. Cada ejercicio tiene sus series y repeticiones
  editables (más peso, descanso e indicaciones opcionales), se puede reordenar o quitar, y el día
  completo (nombre, músculos y ejercicios) se guarda con un solo botón «Guardar plan».
- `PUT /api/v1/planes-entrenamiento/{id}/dias/{dia}/`: guarda el día completo en una transacción,
  reemplazando sus ejercicios en el orden recibido.

### Corregido

- Agregar ejercicios desde dos pestañas a la vez ya no choca con el orden duplicado (409): ahora el
  servidor asigna el orden.
- El entrenador ya puede quitar ejercicios de un día: antes el botón usaba `DELETE`, que su rol no
  tiene permitido.
- En pantallas medianas, el cuerpo 3D ya no tapa los botones del día.

## [1.1.0] - 2026-11-25

### Agregado

- Módulo financiero: pagos, gastos, membresías (renovar, congelar, activar), alertas y
  dashboard administrativo con gráficas.
- Multi-gimnasio: modelo `Gimnasio`, aislamiento de datos por gimnasio y comando
  `crear_gimnasio`. Las migraciones asignan los datos existentes al "Gimnasio principal".
- Reportes descargables en xlsx y pdf (`/api/v1/reportes/<tipo>/`).
- Registro de usuarios (`/api/v1/registro/`) con código de gimnasio.
- Músculos e imagen privada en ejercicios; rutina por día con modelo anatómico 3D.
- Integración continua con GitHub Actions: revisión de Django, migraciones, pruebas del
  backend y compilación del frontend en cada push y Pull Request a `main`.
- `CONTRIBUTING.md`, este `CHANGELOG.md` y `.gitattributes` para normalizar fines de línea.

### Corregido

- Quitar o reemplazar la imagen de un ejercicio ya no responde 500 cuando el archivo anterior
  está abierto por otro proceso (Windows); el aviso queda en el log.
- El listado, el detalle, las estadísticas y la exportación de membresías muestran el estado
  al día (vencida, por vencer) sin depender de `actualizar_membresias`.
- *Seguridad → Recursos*: los nombres de recursos se leen y guardan en el servidor en vez de
  `sessionStorage` (antes se perdían al cerrar la pestaña y el botón Guardar nunca se habilitaba).
  El menú lateral también los lee del servidor.
- `PUT /api/v1/resource-aliases/<recurso>/` con `nombre_actual` vacío elimina el alias en lugar
  de responder 400.
- Pruebas que dejaban abierta la imagen descargada y fallaban en Windows.

### Seguridad

- `sembrar_datos_demo` ya no asigna la contraseña pública `DemoGym2026!` fuera de
  `DJANGO_DEBUG=true`: si no se pasa `--contrasena`, genera una aleatoria.
- El mensaje de error por falta de `DB_NAME` usa una ruta de ejemplo genérica en lugar de una
  ruta personal.

### Cambiado

- README con resumen, tecnologías, requisitos, pasos completos de instalación y la cifra
  correcta de permisos (125).
- `AGENTS.md` corregido: el login solo recibe correo y contraseña; hay 155 pruebas.

### Eliminado

- `IMPLEMENTATION_SUMMARY.md` (obsoleto), `package.json`/`package-lock.json` vacíos de la raíz,
  `resource_aliases.json` de la raíz sin uso y `respaldo_gym.sql` vacío.
- Script `npm test` del frontend, que fallaba porque Karma nunca se instaló.

## [1.0.0] - 2026-11-04

### Agregado

- API REST con Django y Django REST Framework, versionada en `/api/v1/`, con autenticación
  Bearer y contraseñas Argon2id.
- RBAC por recurso con roles del sistema y roles personalizados.
- Clientes, entrenadores, terapeutas, recepcionistas y administradores; asignaciones,
  asistencia, planes de entrenamiento y alimentación, fotos privadas y notificaciones.
- SPA Angular servida por Django en `/app/`.

[Sin publicar]: https://github.com/alvarojaviermonterofonseca-ux/proyecto-de-ingenier-a-de-software/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/alvarojaviermonterofonseca-ux/proyecto-de-ingenier-a-de-software/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/alvarojaviermonterofonseca-ux/proyecto-de-ingenier-a-de-software/releases/tag/v1.0.0
