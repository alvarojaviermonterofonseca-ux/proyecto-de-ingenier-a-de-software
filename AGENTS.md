# AGENTS.md

## Project shape

- Django 6.1 + DRF API in `backend/`; canonical API is `/api/v1/`. The `/api/` mount is a compatibility alias that exposes the same router, so every route exists twice. Admin: `/admin/`; schema/docs: `/api/v1/schema/` and `/api/v1/docs/`.
- UI is an Angular 19 standalone SPA in `frontend/src/app/`, served by Django at `/app/` from `frontend/dist/gym-control-rbac/browser/` via `backend/config/frontend.py`. `/app/` returns 404 until `npm run build` has run.
- The legacy panel at `/panel/` (`frontend/panel.html` + `frontend/static/panel.js`/`rbac.js`) is separate from the SPA; Django templates load it because `TEMPLATES["DIRS"]` points at `frontend/`.
- SQLite is the fallback engine, but `DB_NAME` is required (`ImproperlyConfigured` otherwise); copy `backend/.env.example`. MySQL is selected with `DB_ENGINE=mysql` plus `DB_*`. `backend/.env` is untracked and machine-specific — never commit it, `*.sqlite3`, `frontend/dist/` or `media/`.
- `DJANGO_DEBUG` defaults to false; outside debug, `DJANGO_SECRET_KEY` is also required. `backend/.env.example` sets `DJANGO_DEBUG=true`; process env wins over `.env`.
- Root `package.json` is a leftover stub with no scripts; run npm from `frontend/`.
- `README.md` covers routes, roles/policies, demo seeding and env vars, but its 90/95 permission counts are stale; `IMPLEMENTATION_SUMMARY.md` (if present) is an outdated status snapshot. Migrations/tests are authoritative.

## Commands

From the repo root (Python 3.12+):

```powershell
python backend\manage.py migrate                             # 0019-0021 create "Gimnasio principal" (code `principal`) and assign all existing data to it
python backend\manage.py crear_gimnasio --nombre "Gym Norte" --codigo norte   # platform staff only; seeds catalogs + permission matrix
python backend\manage.py crear_administrador_gym --nombre "Administrador" --correo admin@example.com --gimnasio principal
python backend\manage.py sembrar_datos_demo --cantidad 100    # or --por-rol N
python backend\manage.py sembrar_datos_financiero             # catalogs only; demo seed has no payments/memberships
python backend\manage.py actualizar_membresias                # daily: membership states + alerts
python backend\manage.py generar_alertas                      # daily: all alert rules for every active gym
python backend\manage.py runserver
```

Frontend (Node 20+):

```powershell
cd frontend
npm install
npm start          # :4200; proxy.conf.json forwards /api to 127.0.0.1:8000
npm run build      # required before Django can serve /app/
```

Verification:

```powershell
python backend\manage.py test gym          # 137 tests
python backend\manage.py test gym.tests.GymApiTests.test_roles_iniciales_y_rutas_crud_requieren_autenticacion
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
cd frontend; npm run build
```

- Always pass the `gym` label: `python backend\manage.py test` from the repo root discovers 0 tests.
- `backend/manage.py` sets `TESTING=1` when the command is `test`, so the suite always runs on in-memory SQLite even if `.env` selects MySQL; `DB_NAME` is still required. Do not leave `TESTING` defined for `runserver`; it would switch the app to SQLite.
- `backend/gym/tests.py` is the only test module and calls `sembrar_datos_demo`, so that command must stay.
- No lint, formatter, typecheck or CI is configured. `npm test` (Karma) is broken: `karma-jasmine` is missing and there are no specs. `npm run build` is the frontend check.
- Production Angular uses `baseHref="/app/"`; the dev server uses `/`.

## Backend gotchas

- `gym.Usuario` is custom. Use `set_password()`/`check_password()` (Argon2id). API auth is a custom Bearer token and `Sesion` stores only its hash; Django admin sessions are accepted only for `is_staff`.
- A permission only counts with **both** rows: `tiene_permiso()` and `permisos_efectivos()` require a `RolPermiso` *and* a matching `RolRecurso` for the same role. `PUT /roles/{id}/permisos/` syncs both; creating `RolPermiso` directly grants nothing.
- The catalog has 125 permissions seeded by migrations, and `tests.py` asserts that number. Adding a resource means a migration for `Recurso`, `Permiso` and `RolPermiso`/`RolRecurso`, plus updating the test and the menu maps (`gym/resources.py`, `_RECURSOS_MENU_VIEWSETS` in `views.py`, `nav.config.ts`). Keep menu resources in `gym/resources.py` (it avoids a views/serializers import cycle).
- Every `ViewSet` declares `recurso_permiso`; `TienePermisoRecurso` maps GET→view, POST→create, PUT/PATCH→edit, DELETE→delete, with `accion_permiso`/`accion_permiso_por_accion` overrides (`exportar`→`export`). `None` allows any authenticated user.
- `ViewSetBase.filtrar_alcance()` applies the per-user data scope (`gym/scoping.py`); override it for any resource with per-user data. Out-of-scope detail returns 404, a missing permission returns 403.
- Scope: admin/Django staff see everything; a client sees only itself; trainer/therapist see their assigned clients; receptionist sees all clients but clinical fields in its edits are silently dropped. Effective roles are additive for both permissions and scope.
- `queryset_base()` hides soft-deleted rows; `?incluir_eliminados=1` only works for admins. DELETE is logical by default — use `politica_borrado = "fisico"` only for `UsuarioRol`, `RolPermiso` and `PlanEntrenamientoEjercicio`.
- Profiles (`Cliente`, `Entrenador`, `Terapeuta`, `Recepcionista`, `Administrador`) use `usuario` as a `OneToOneField(primary_key=True)`: the profile PK equals the user PK, which the scoping filters rely on.
- Cross-table rules live in model `clean()` (assignment overlap, one open attendance per client, plans need an active assigned trainer, meals must use the client's own plan). API writes validate via `ModeloValidadoSerializer`; plain `save()` skips it unless `save(validar=True)`.
- Permission changes are read from the DB on every request and do not revoke sessions; role changes revoke the target user's sessions except the caller's.
- `POST /api/v1/asistencias/registrar-entrada|salida/` are self-service for the authenticated client: they bypass `asistencias:create`, use server time, set `metodo_entrada=manual` and return the open attendance instead of duplicating it.
- Errors always use `{"error": {"codigo", "mensaje", "detalles"}}`; unhandled `IntegrityError` becomes 409.
- Food photos live under `PRIVATE_MEDIA_ROOT`, are never served from `/media/`, and are read through authenticated `GET /api/v1/registros-comida/{id}/foto/` (the SPA fetches a blob).
- `GET /api/v1/conteos/` instantiates each menu ViewSet and counts `get_queryset()`, so badges always equal the matching list `count`.
- Resource display names are file-backed, not a DB model: `gym/resource_aliases.py` writes `backend/resource_aliases.json` (the root `resource_aliases.json` is unused); `/api/v1/resource-aliases/` is readable by any authenticated user and PUT is admin-only. The SPA currently keeps aliases in `sessionStorage['gym_recursos_alias']` and does not call these endpoints.

## Multi-tenant (one gym per user)

- `Gimnasio` is the tenant. Every `Usuario` has a required `gimnasio` FK; there is no gym switcher. Django staff (`is_staff`, not a `Usuario`) is the platform: sees every gym, creates gyms in `/admin/` or with `crear_gimnasio`.
- The gym is always taken from the authenticated user (`tenancy.gimnasio_id_de`), never from request params. `gym/tenancy.py` `RUTA_GIMNASIO` declares how each model reaches its gym; `ViewSetBase.get_queryset` and serializer FK choices filter through it. A new model must be added there (a test fails otherwise).
- Login requires the gym code (`gimnasio` field); inactive gyms reject auth.
- RBAC matrix rows (`RolPermiso`/`RolRecurso`) carry `gimnasio`; rows with NULL gym are the template copied to new gyms. System roles (`Rol.gimnasio` NULL) are shared and read-only for gyms; custom roles belong to a gym. The `Permiso`/`Recurso` catalog is writable only by platform staff. A future permission migration must seed the template **and** every existing gym.
- Gym settings (`dias_inactividad_alerta`, `limite_gastos_mensual`, `porcentaje_caida_ingresos`) via `GET/PATCH /api/v1/gimnasio/` (PATCH admin-only) and `/financiero/configuracion` in the SPA.
- Known platform-wide uniques: client document number and role names.

## Financial module

- Endpoints: `/api/v1/dashboard/`, `/metodos-pago/`, `/categorias-gasto/`, `/pagos/`, `/gastos/`, `/membresias/` and `/alertas/`. Migration `0017` adds 30 permissions for the six resources and grants them only to `administrador`; other roles need explicit grants.
- `GET /dashboard/` is admin-only regardless of permissions and mutates state: it runs `alertas.generar_alertas_de(usuario)` (membership states + all alert rules for the gym) before responding. Accepts `?meses=3|6|12|24` and `?dias=7|14|30|90` for the chart windows (other values → 400). Its test caps the response at fewer than 60 SQL queries, so avoid per-day/per-month queries.
- Scope: `Pago`/`Membresia` follow `filtrar_clientes`; `Alerta` follows the client's assignments; `Gasto`/`MetodoPago`/`CategoriaGasto` return `.none()` for non-admins.
- `Membresia.save()` computes `estado` only on creation. Run `actualizar_membresias` daily (no scheduler is configured) or hit `/dashboard/` to refresh; `congelar` extends `fecha_fin`, `renovar` clamps month-end, and `activar` can leave it `vencida`.
- `pagos`/`gastos`/`membresias` list, `/estadisticas/` and `/exportar/` share `fecha_desde`/`fecha_hasta`; invalid dates return 400. `registrado_por` and approval `aprobado_por` come from the session, not the payload.
- Gastos with `estado=cancelado` are "anulados": listed, but excluded from totals, dashboard and reports.
- `GET /api/v1/reportes/<tipo>/?formato=xlsx|pdf&fecha_desde=&fecha_hasta=` (admin-only; tipos: financiero, ingresos, gastos, asistencia, clientes, membresias, crecimiento) builds real-data reports in `gym/reportes.py` with openpyxl/reportlab; each download is audited as `exportar-reporte`.
- Pagination accepts `?page_size=` up to 200; CSV exports prefix leading `= + - @` with an apostrophe to neutralize formulas.

## Frontend gotchas

- Guards: `authGuard`/`guestGuard` in `core/auth`, `permissionGuard` in `core/rbac`. Routes declare `data.permission` (string or array; arrays default to `any`, use `data.permissionMode: 'all'` for AND) and optional `data.adminOnly`. Financial nav items are `adminOnly`, but the `/financiero` parent and child routes only declare permission codes; financial screens live under `features/financial/` (`/dashboard`, `/financiero/{ingresos,gastos,membresias,alertas,reportes,configuracion}`) and use `financial.service.ts`.
- The Bearer token lives in `sessionStorage` (`TokenStorage`), never `localStorage`. `AuthService.refresh()` re-reads `/me/` after permission edits and when the window regains focus.
- `environment.apiBaseUrl` is the relative `/api/v1`, so the dev server only works with `proxy.conf.json`; production is same-origin behind Django.
- TypeScript runs with `strict`, `strictTemplates` and `noPropertyAccessFromIndexSignature`; use bracket access for index-signature fields, and template type errors fail `npm run build`.
