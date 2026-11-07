# home-management

Aplicación web Flask para gestionar la casa: **menús semanales con recetas** (`/menus`)
y **gastos e ingresos** (`/gastos`), con un portal de entrada en `/`.

Nace de la fusión de home-cooking (gestión de menús y recetas) y home-expenses
(gestión de gastos de la casa). Corre en el servidor de casa (teléfono Android con
Termux: gunicorn + Caddy) y también en local.

## Características

- Portal de inicio con las secciones: Ver menús / Ver gastos
- Menús semanales con recetas, lista de la compra agrupada y visor de recetas
- CRUD de recetas (crear/editar/borrar con aviso si están en menús) y editor de
  menús (cambar plato por día, crear menús vacíos, borrar semanas)
- **Ingredientes estandarizados**: al crear o editar una receta se sugieren
  nombres canónicos y se unifican alias (`atún en lata` → `atún en conserva`,
  `pimiento` → `pimiento rojo`, `huevos` → `huevo`). La lista de la compra
  agrupa los alias aunque las recetas antiguas los usen.
- Generación de menús con LLM local (Strata, API compatible OpenAI) y campo de
  feedback libre del momento ("esta semana hazlo simple") inyectado en el prompt.
  La generación es **asíncrona**: el botón crea un trabajo en segundo plano y la
  UI consulta su estado, así una IA lenta no bloquea la página ni provoca timeouts.
- Interfaz responsive con Flask + Bootstrap
- Datos en SQLite (`data/menus.db` y `data/expenses.db`) con factory de almacenes;
  los menús caen automáticamente al respaldo JSON si la BD está sin migrar
  (patrón inspirado en ScholarCrawler)

## Estructura del Proyecto

```
.
├── app.py                  # App factory: create_app() registra blueprints y el store
├── settings.py             # Config por entorno (HM_CONFIG=LocalConfig|ServerConfig)
├── migrate_menus_to_sqlite.py  # Migración idempotente JSON → data/menus.db (con verificación)
├── blueprints/
│   ├── index.py            # Portal (/)
│   ├── menus.py            # Menús/recetas/generar bajo /menus
│   └── gastos.py           # Gastos (/gastos): movimientos, resumen, tickets
├── models/
│   ├── factory.py          # create_store / create_gastos_store con fallback
│   ├── base.py             # Interfaces de almacén
│   ├── json_store.py       # Backend JSON (respaldo de menús/recetas)
│   ├── sqlite_store.py     # Gastos: tabla movimientos en data/expenses.db
│   └── sqlite_menus_store.py  # Menús/recetas: documental en data/menus.db
├── services/
│   ├── generation.py       # Generación de menús LLM + fusión con existentes
│   ├── generation_jobs.py  # Trabajos asíncronos persistidos en data/generacion/
│   ├── llm.py              # Cliente Strata/OpenAI-compatible (texto y visión)
│   ├── ingredientes.py     # Estandarización, alias y sugerencias de ingredientes
│   ├── ingredientes_catalogo.json  # Catálogo canónico + alias (editable)
│   ├── menus_helpers.py    # Dominio: fechas, ingredientes, validación CRUD
│   └── tickets.py          # Análisis de fotos de tickets con visión
├── templates/              # base.html compartido + portal + menus/ + gastos/
├── static/css/custom.css   # y static/vendor/ (flatpickr)
├── data/                   # gitignoreado: menus/, recetas/, preferencias.json
├── deploy/phone/           # Caddyfile y start_all.sh del servidor de casa
└── run.sh                  # start/stop/install (agnóstico Termux/Linux)
```

## Requisitos

- Python 3.6+ (en el servidor: Termux con Python y Gunicorn)
- Flask

## Instalación y ejecución

```bash
./run.sh install   # crea venv e instala dependencias
./run.sh           # arranca (gunicorn en segundo plano si está disponible)
./run.sh stop
```

En local: `python app.py` (servidor de desarrollo en el puerto 5000).

## Configuración

- `config_local.json` (gitignoreado): `strata_url`, `strata_api_key`, `strata_model`,
  y opcionales `strata_timeout` (segundos, 1800 por defecto) y `strata_max_tokens`
  (4000 por defecto) para la generación de menús con LLM.
- Variables de entorno: `HM_CONFIG` (`LocalConfig`/`ServerConfig`), `HM_STORE`
  (`sqlite` por defecto con fallback a `json`, o `json`), `HM_MENUS_DB`, `HM_GASTOS_DB`,
  `STRATA_URL`, `STRATA_API_KEY`, `STRATA_MODEL`, `STRATA_VISION_MODEL`,
  `STRATA_TIMEOUT`, `STRATA_MAX_TOKENS`.
- Tras clonar en una máquina nueva: `python migrate_menus_to_sqlite.py` para volcar
  los JSON de `data/` a `data/menus.db` (sin borrar los JSON; son el respaldo).

## URLs

- `/` portal · `/menus` · `/menus/recetas` · `/menus/generar` · `/gastos`
- API: `/menus/api/menus`, `/menus/api/menu/<id>`, `/menus/api/recetas`,
  `/menus/api/receta/<id>`, `/menus/api/preferencias`,
  `/menus/api/ingredientes?q=<texto>` (sugerencias canónicas y alias)
- Generación asíncrona: `POST /menus/api/generar` responde `202` con un `job`;
  `GET /menus/api/generar/<job_id>` devuelve su estado (`pendiente`, `en_proceso`,
  `terminado` o `error`) y `GET /menus/api/generar/activos` lista los trabajos
  en curso para el flag global de la UI.
- Las URLs antiguas (`/home-cooking/*`, `/recetas`, `/generar`, `/api/*`)
  se redirigen automáticamente a su equivalents en `/menus`.

## Despliegue en el servidor de casa (192.168.1.4)

Flujo git: desarrollo local → push (usuario nemesis) → `git pull` en el teléfono →
`~/web-server/start_all.sh stop && start_all.sh start`. Los ficheros del teléfono
viven versionados en `deploy/phone/`.
