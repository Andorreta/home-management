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
- **Subrecetas**: un paso puede enlazar otra receta, así lo que se repite siempre
  (cocer la pasta, el arroz, un sofrito) se define una sola vez. En el editor se
  enlaza escribiendo el nombre en el buscador —lo que se guarda es un paso normal
  con el enlace dentro— y el panel avisa si un ingrediente lo aporta ya la
  subreceta para no contarlo dos veces. Los ingredientes de la subreceta **no se
  duplican** en la receta padre: la lista de la compra los suma en cascada, aunque
  el enlace esté a varios niveles, y los utensilios también cuentan. En el plan
  semanal y en la ficha el enlace se ve como una etiqueta que abre la subreceta en
  un modal, con breadcrumb para volver de donde se viene. Si la receta enlazada ya
  no existe, no se rompe nada: se avisa en la página y en la API. Borrar una receta
  que otras enlazan pide confirmación diciendo **cuántas recetas la usan**; al
  confirmar, sus pasos, ingredientes y utensilios se copian en ellas
  (`DELETE /menus/api/receta/<id>?force=1`) y siguen siendo recetas completas.
- Generación de menús con LLM local (Strata, API compatible OpenAI) y campo de
  feedback libre del momento ("esta semana hazlo simple") inyectado en el prompt.
  La generación es **asíncrona**: el botón crea un trabajo en segundo plano y la
  UI consulta su estado, así una IA lenta no bloquea la página ni provoca timeouts.
- **Gastos por mes y categoría**: la vista de gastos muestra todos los
  movimientos del mes elegido (gastos e ingresos), permite filtrar por categoría
  y resume gastos, ingresos y balance del filtro. La gráfica representa los
  ingresos en positivo y los gastos en negativo, con el balance acumulado como
  línea.
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
│   ├── menus_helpers.py    # Dominio: fechas, ingredientes, validación CRUD, subrecetas
│   └── tickets.py          # Análisis de fotos de tickets con visión
├── templates/              # base.html compartido + portal + menus/ + gastos/
├── static/css/custom.css   # y static/vendor/ (flatpickr)
├── static/js/subrecetas.js # Pinta los enlaces a subreceta y abre su modal (lo usan
│                           # el plan semanal y la ficha de receta)
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
- Gastos: `GET /gastos/api/movimientos?desde=AAAA-MM-DD&hasta=AAAA-MM-DD&categoria=Casa&tipo=gasto&limit=500`,
  más `/gastos/api/resumen`, `/gastos/api/comparativa`, `/gastos/api/categorias`.
- API: `/menus/api/menus`, `/menus/api/menu/<id>` (devuelve `avisos` con los enlaces
  a subreceta que ya no existen), `/menus/api/recetas` (cada receta con `usada_por`:
  las recetas que la enlazan), `/menus/api/receta/<id>`, `/menus/api/preferencias`,
  `/menus/api/ingredientes?q=<texto>` (sugerencias canónicas y alias)
- Subrecetas: un paso enlaza otra receta con `[subreceta](id)` dentro de `pasos`
  (sin columnas nuevas: es texto de un paso). `DELETE /menus/api/receta/<id>`
  devuelve `409` con `recetas_que_la_usan` y `n_recetas` si otras recetas la
  enlazan; con `?force=1` sus pasos, ingredientes y utensilios se materializan
  primero en cada una (`materializada_en`). Un ciclo de enlaces se rechaza al
  guardar (`400`).
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
