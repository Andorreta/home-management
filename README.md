# home-management

Aplicación web Flask para gestionar la casa: **menús semanales con recetas** (`/menus`)
y **gastos e ingresos** (`/gastos`), con un portal de entrada en `/`.

Nace de la fusión de home-cooking (gestión de menús y recetas) y home-expenses
(gestión de gastos de la casa). Corre en el servidor de casa (teléfono Android con
Termux: gunicorn + Caddy) y también en local.

## Características

- Portal de inicio con las secciones: Ver menús / Ver gastos
- Menús semanales con recetas, lista de la compra agrupada y visor de recetas
- Generación de menús con LLM local (Strata, API compatible OpenAI)
- Interfaz responsive con Flask + Bootstrap
- Datos en JSON (backend actual) con factory de almacenes para migrar a SQLite
  sin tocar las vistas (patrón inspirado en ScholarCrawler)

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
│   ├── llm.py              # Cliente Strata/OpenAI-compatible
│   └── menus_helpers.py    # Dominio: fechas, ingredientes, lista de la compra
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

- `config_local.json` (gitignoreado): `strata_url`, `strata_api_key`, `strata_model`
  para la generación de menús con LLM.
- Variables de entorno: `HM_CONFIG` (`LocalConfig`/`ServerConfig`), `HM_STORE`
  (`sqlite` por defecto con fallback a `json`, o `json`), `HM_MENUS_DB`, `HM_GASTOS_DB`,
  `STRATA_URL`, `STRATA_API_KEY`, `STRATA_MODEL`, `STRATA_VISION_MODEL`.
- Tras clonar en una máquina nueva: `python migrate_menus_to_sqlite.py` para volcar
  los JSON de `data/` a `data/menus.db` (sin Borrar los JSON; son el respaldo).

## URLs

- `/` portal · `/menus` · `/menus/recetas` · `/menus/generar` · `/gastos`
- API: `/menus/api/menus`, `/menus/api/menu/<id>`, `/menus/api/recetas`,
  `/menus/api/receta/<id>`, `/menus/api/preferencias`, `/menus/api/generar` (POST)
- Las URLs antiguas (`/home-cooking/*`, `/recetas`, `/generar`, `/api/*`)
  se redirigen automáticamente a su equivalents en `/menus`.

## Despliegue en el servidor de casa (192.168.1.4)

Flujo git: desarrollo local → push (usuario nemesis) → `git pull` en el teléfono →
`~/web-server/start_all.sh stop && start_all.sh start`. Los ficheros del teléfono
viven versionados en `deploy/phone/`.
