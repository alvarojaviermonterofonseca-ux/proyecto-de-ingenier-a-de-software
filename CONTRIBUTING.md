# Cómo contribuir a Gym Control Pro

## Flujo de trabajo

Usamos **GitHub Flow**: `main` siempre está estable y todo cambio entra por Pull Request.

1. Crea o elige un issue que describa el cambio.
2. Actualiza `main`: `git switch main; git pull`.
3. Crea una rama desde `main` con el formato de abajo.
4. Haz commits pequeños siguiendo la convención de commits.
5. Sube la rama (`git push -u origin <rama>`) y abre un Pull Request hacia `main`.
6. Espera a que el CI esté en verde y a la aprobación de otro integrante.
7. Integra con **"Create a merge commit"** (así los commits quedan visibles en `main`) y borra la rama.

## Nombres de ramas

`tipo/descripcion-corta-en-kebab-case`

| Prefijo | Uso | Ejemplo |
|---|---|---|
| `feature/` | Funcionalidad nueva | `feature/exportar-asistencias` |
| `fix/` | Corrección de un error | `fix/imagen-ejercicio-bloqueada` |
| `docs/` | Solo documentación | `docs/actualizar-readme` |
| `refactor/` | Reestructurar sin cambiar el comportamiento | `refactor/dividir-views` |
| `chore/` | Mantenimiento, dependencias, configuración | `chore/actualizar-angular` |

## Convención de commits

[Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/) en español:

```
tipo(alcance opcional): descripción en imperativo y minúscula
```

Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`, `perf`, `style`.
Un cambio incompatible lleva `!` (`feat(api)!: ...`) y una nota `BREAKING CHANGE:` en el cuerpo del commit.

- ✅ `fix: evitar error 500 al quitar la imagen de un ejercicio en uso`
- ✅ `feat(finanzas): agregar filtro por método de pago`
- ❌ `cambios`, `final`, `arreglo`, `ahora-si`, `Actualización de Gym Control Pro`

## Pull Requests

Cada PR debe incluir:

- **Descripción**: qué cambia y por qué.
- **Issue relacionado**: `Closes #N`, para que se cierre al integrar.
- **Explicación del cambio**: archivos o decisiones principales.
- **Cómo verificarlo**: comandos o pasos concretos.
- **Evidencia**: capturas o salida de pruebas, cuando aplique.

Antes de pedir revisión, ejecuta desde la raíz del repositorio:

```powershell
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py test gym
cd frontend; npm run build
```

## Reglas básicas

- Nunca hagas commit directo a `main`.
- No subas secretos ni datos locales: `backend/.env`, `*.sqlite3`, `media/`, `frontend/dist/`, `backend/resource_aliases.json`.
- Todo bug corregido lleva una prueba que lo reproduzca.
- Un permiso o recurso nuevo exige una migración que siembre la plantilla **y** cada gimnasio existente, y actualizar el conteo de permisos en `backend/gym/tests.py` (ver `AGENTS.md`).
- Si el cambio se nota para el usuario, anótalo en `CHANGELOG.md`, en la sección "Sin publicar".
- Versionado [SemVer](https://semver.org/lang/es/): MAJOR rompe compatibilidad, MINOR agrega funcionalidad compatible y PATCH corrige errores. Cada versión lleva un tag anotado (`git tag -a vX.Y.Z`).
