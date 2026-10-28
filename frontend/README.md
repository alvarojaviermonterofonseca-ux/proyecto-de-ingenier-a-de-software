# Gym Control Pro - Frontend Angular

SPA standalone de Angular 19 para operar Gym Control Pro contra la API real en
`/api/v1/`. Convive con el panel legado (`panel.html` y `static/`), que se
mantiene intacto en `/panel/`.

## Ejecutar en desarrollo

Requiere Node 20 o superior y el backend escuchando en `:8000`.

```powershell
cd frontend
npm install
npm start
```

Abre `http://localhost:4200`. El proxy de `proxy.conf.json` reenvía `/api` a
`http://127.0.0.1:8000` y el servidor de desarrollo usa `baseHref="/"`.

## Build servido por Django

```powershell
cd frontend
npm run build
```

El resultado queda en `frontend/dist/gym-control-rbac/browser/` y Django lo
publica en `http://127.0.0.1:8000/app/` mediante `backend/config/frontend.py`.
El build de producción usa `baseHref="/app/"`; las rutas profundas caen en
`index.html` y los assets se sirven con caché inmutable. Si `/app/` responde
404, falta ejecutar el build.

## Estructura

- `src/app/core/api/`: cliente HTTP tipado, DTOs, errores y estado de carga.
- `src/app/core/auth/`: sesión Bearer, guards e interceptores.
- `src/app/core/rbac/`: permisos, `permissionGuard` y directiva `*rbacCan`.
- `src/app/core/ui/`: toasts, confirmaciones y tema claro/oscuro.
- `src/app/shared/`: UI kit propio (iconos SVG, modal, badges, paginación...).
- `src/app/layout/`: shell autenticado, navegación y menú de usuario.
- `src/app/features/`: una carpeta por módulo funcional.

## Autenticación y permisos

- `AuthService` inicia sesión en `POST /api/v1/login/`, carga `/api/v1/me/` y
  guarda el token solo en `sessionStorage`. Nunca se usa `localStorage`.
- La UI decide con `permisos_efectivos`, no con nombres de rol. Los nombres de
  rol solo se usan para etiquetas visuales.
- Cada ruta declara `data.permission` (código o arreglo) y, si aplica,
  `data.adminOnly`; `permissionGuard` redirige a `/acceso-denegado`.
- Ocultar un botón no autoriza nada: el backend valida `recurso:accion` y el
  alcance por rol/propiedad en cada petición.

## Datos y archivos privados

- Los listados DRF paginados `{count,next,previous,results}` se recorren con
  `ApiClient.getAll()`.
- Las fotos de registros de comida no se sirven desde `/media/`. La pantalla
  solicita `GET /api/v1/registros-comida/{id}/foto/` como blob con el token y
  revoca los object URLs al destruir el componente.

## Verificación

No hay lint, formatter ni typecheck configurados. Las pruebas Karma no son
utilizables (falta `karma-jasmine` y no hay specs). La verificación actual es:

```powershell
npm run build
```

Desde la raíz del repositorio:

```powershell
python backend\manage.py test gym
python backend\manage.py check
```
