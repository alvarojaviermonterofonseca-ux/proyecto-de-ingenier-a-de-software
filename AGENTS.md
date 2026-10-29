# AGENTS.md

## Project shape

- Django 6.1 + DRF API in `backend/`; canonical API is `/api/v1/` (`/api/` remains a compatibility alias). Admin is `/admin/`; schema/docs are `/api/v1/schema/` and `/api/v1/docs/`.
- The current UI is an Angular 19 standalone SPA in `frontend/src/app/`, served by Django at `/app/` from `frontend/dist/gym-control-rbac/browser/`. `backend/config/frontend.py` serves hashed assets and falls back to `index.html` for SPA routes. Build it before using `/app/`.
- The legacy Django-served panel at `/panel/` (`frontend/panel.html`, `frontend/static/panel.js`, `frontend/static/rbac.js`) remains intact and is not the new SPA.
- Default DB is `base de datos/db.sqlite3`, but `DB_NAME` is now **required**: there is no implicit fallback and settings raise `ImproperlyConfigured` if it is missing. Use `DB_ENGINE=mysql` plus `DB_*` for MySQL.
- Settings load `backend/.env` (template: `backend/.env.example`) through `config/env.py`. Real process env always wins, and `.env` stays untracked.
- Read root `README.md` for API routes, RBAC policy, roles, demo seeding, and env vars.

## Commands

Run from the repository root:

```powershell
python backend\manage.py migrate
python backend\manage.py crear_administrador_gym --nombre "Administrador" --correo admin@example.com --contrasena "UnaClaveSegura123"
python backend\manage.py sembrar_datos_demo --cantidad 100
python backend\manage.py runserver
```

Frontend:

```powershell
cd frontend
npm install
npm start          # dev server :4200, proxies /api to :8000
npm run build      # production build served by Django at /app/
```

Verification:

```powershell
python backend\manage.py test gym          # 57 tests
python backend\manage.py test gym.tests.GymApiTests.test_roles_iniciales_y_rutas_crud_requieren_autenticacion
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
cd frontend; npm run build
```

- `python backend\manage.py test` from the repo root discovers 0 tests. Always pass the `gym` label, or run `python manage.py test` with `backend/` as the working directory.
- There is no configured lint, formatter, or typecheck command.
- Frontend tests are not usable (`karma-jasmine` is missing and there are no specs).
- Production Angular uses `baseHref="/app/"`; the dev server still uses `/`.

## Backend gotchas

- `gym.Usuario` is a custom model, not Django's `auth.User`. Use `set_password()` / `check_password()`; passwords are Argon2id. API auth is the custom Bearer session (`Sesion` stores only a token hash). Django admin sessions are accepted only for `is_staff`.
- Every `ViewSet` must declare `recurso_permiso`. `TienePermisoRecurso` maps GET/POST/PUT-PATCH/DELETE to view/create/edit/delete. A `None` value allows any authenticated user. Authorization is resource-level only; querysets are not automatically scoped to the current user.
- The permission catalog is seeded by data migrations (95 permissions; `0007` added `clientes-terapeutas`). Adding a resource requires a new migration updating `Permiso`/`RolPermiso`; tests assert the catalog size.
- `ViewSetBase` hides soft-deleted rows. `DELETE` is logical by default; set `politica_borrado = "fisico"` only for bridge/composition tables (`UsuarioRol`, `RolPermiso`, `PlanEntrenamientoEjercicio`).
- Cross-table rules live in model `clean()` (assignment overlap, one open attendance per client, plans require an active assigned trainer, meal records must use the client's own plan). API writes validate through `ModeloValidadoSerializer`; direct ORM writes bypass validation unless `save(validar=True)`.
- API errors are always wrapped as `{"error": {"codigo", "mensaje", "detalles"}}`.
- Food photos are private: stored under `media/private` (`PRIVATE_MEDIA_ROOT`), never served from `/media/`. Use authenticated `GET /api/v1/registros-comida/{id}/foto/`. The Angular UI fetches it as a blob with the Bearer token and revokes object URLs on destroy.
- SPA routes are permission-driven: route `data.permission` accepts a code or array, and `data.adminOnly` restricts the route to the `administrador` role. Navigation is filtered through the same rules.
- The sidebar badges come from `GET /api/v1/conteos/` (`ConteoRecursosView`), which counts each resource through its own ViewSet, so a badge always equals the list `count`. Nav items declare `counts` in `frontend/src/app/layout/nav.config.ts`.
- `npm start` and production builds both use `sessionStorage` for the Bearer token, never `localStorage`.
