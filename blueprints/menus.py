"""
Blueprint de menús y recetas: la aplicación home-cooking de siempre, montada
bajo /menus. Todo el acceso a datos pasa por el store (models/factory).
"""

from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request

from services import generation
from services import ingredientes
from services import menus_helpers as helpers

bp = Blueprint('menus', __name__, url_prefix='/menus')


def store():
    return current_app.store


# --- Páginas ---

@bp.route('/')
def index():
    return render_template('menus/index.html')


@bp.route('/recetas')
def recetas():
    return render_template('menus/recetas.html')


@bp.route('/generar')
def generar():
    return render_template('menus/generar.html')


# --- API ---

@bp.route('/api/preferencias')
def api_preferencias():
    return jsonify(store().load_preferencias())


@bp.route('/api/preferencias', methods=['PUT'])
def api_guardar_preferencias():
    """Actualiza solo las claves permitidas (respeta el resto)."""
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos, dict):
        return jsonify({'error': 'El cuerpo debe ser un objeto JSON'}), 400

    lista_de_texto = 'Debe ser una lista de textos'
    prefs = store().load_preferencias()
    for clave in ('despensa_base', 'restricciones', 'platos_habituales', 'favoritas'):
        if clave in datos:
            v = datos[clave]
            if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
                return jsonify({'error': f'{clave}: {lista_de_texto}'}), 400
            prefs[clave] = [str(x).strip() for x in v]
    if 'evitar_repetir_de_semanas' in datos:
        try:
            n = int(datos['evitar_repetir_de_semanas'])
        except (TypeError, ValueError):
            return jsonify({'error': 'evitar_repetir_de_semanas debe ser un número'}), 400
        if not (0 <= n <= 12):
            return jsonify({'error': 'evitar_repetir_de_semanas debe estar entre 0 y 12'}), 400
        prefs['evitar_repetir_de_semanas'] = n

    store().save_preferencias(prefs)
    return jsonify({'ok': True, 'preferencias': prefs})


@bp.route('/api/menus')
def api_menus():
    menus_data = store().load_menus()
    resultado = []
    for i, name in enumerate(sorted(menus_data.keys())):
        menu = menus_data[name]
        d_ini, d_fin = helpers.get_menu_range(name, menu)
        resultado.append({
            'id': name,
            'titulo': menu.get('titulo', name),
            'fecha_inicio': d_ini.strftime('%Y-%m-%d') if d_ini else None,
            'fecha_fin': d_fin.strftime('%Y-%m-%d') if d_fin else None,
            'color': menu.get('color') or helpers.MENU_COLORS[i % len(helpers.MENU_COLORS)],
        })
    resultado.sort(key=lambda m: (m['fecha_inicio'] or '9999-99-99', m['id']))
    return jsonify(resultado)


@bp.route('/api/menu/<menu_name>')
def api_menu(menu_name):
    menus_data = store().load_menus()
    recetas_data = store().load_recetas()

    if menu_name in menus_data:
        menu = menus_data[menu_name]

        # Generar lista de la compra (sin la despensa básica del usuario)
        prefs = store().load_preferencias()
        despensa = prefs.get('despensa_base', [])
        mandatory_ingredients, optional_ingredients = helpers.get_shopping_list(
            {menu_name: menu}, recetas_data, exclusiones=despensa)

        # Avisos: pasos que enlazan una receta que ya no existe (enlaces rotos)
        avisos = []
        vistos_rotos = set()
        for dia in menu.get('dias', []) or []:
            for clave in ('id_comida', 'id_cena'):
                rid = dia.get(clave)
                if not rid or rid == 'sobras' or rid not in recetas_data:
                    continue
                _, rotos = helpers.expandir_receta(rid, recetas_data)
                for roto in rotos:
                    clave_avisos = (roto['receta'], roto['enlace'])
                    if clave_avisos in vistos_rotos:
                        continue
                    vistos_rotos.add(clave_avisos)
                    avisos.append({
                        'dia': dia.get('dia', ''),
                        'plato': dia.get('comida' if clave == 'id_comida' else 'cena', ''),
                        'receta': roto['receta'],
                        'receta_nombre': (recetas_data.get(roto['receta']) or {}).get('nombre', roto['receta']),
                        'enlace': roto['enlace'],
                    })

        # Preparar datos para la respuesta
        # Aportes de las subrecetas, solo de los platos de este menú (para su ficha)
        platos = []
        for dia in menu.get('dias', []) or []:
            for clave in ('id_comida', 'id_cena'):
                rid = dia.get(clave)
                if rid and rid != 'sobras' and rid in recetas_data and rid not in platos:
                    platos.append(rid)
        menu_data = {
            'menu': menu,
            'mandatory_ingredients': mandatory_ingredients,
            'optional_ingredients': optional_ingredients,
            'despensa_base': despensa,
            'recetas': recetas_data,
            'avisos': avisos,
            'aportes': {rid: helpers.aportes_subrecetas(rid, recetas_data) for rid in platos},
        }
        return jsonify(menu_data)
    else:
        return jsonify({'error': 'Menú no encontrado'}), 404


@bp.route('/api/receta/<receta_id>')
def api_receta(receta_id):
    recetas_data = store().load_recetas()

    if receta_id in recetas_data:
        if request.args.get('raw'):
            # Edición: tal cual está guardado, sin normalizar
            return jsonify(recetas_data[receta_id])
        # Normalizar receta antes de devolverla
        receta = helpers.normalize_receta(recetas_data[receta_id])
        # Qué aportan sus subrecetas (para marcarlo en la ficha)
        receta['aportes_subrecetas'] = helpers.aportes_subrecetas(receta_id, recetas_data)
        return jsonify(receta)
    else:
        return jsonify({'error': 'Receta no encontrada'}), 404


@bp.route('/api/recetas')
def api_recetas():
    recetas_data = store().load_recetas()
    usadas_por = helpers.indice_usadas_por(recetas_data)
    resultado = [
        {
            'id': key,
            'nombre': receta.get('nombre', key),
            'usada_por': usadas_por.get(key, []),
        }
        for key, receta in recetas_data.items()
    ]
    resultado.sort(key=lambda r: r['nombre'].lower())
    return jsonify(resultado)


@bp.route('/api/ingredientes')
def api_ingredientes():
    """Sugerencias de ingredientes canónicos para el autocompletado."""
    consulta = request.args.get('q', '')
    limite = request.args.get('limite', 10, type=int)
    limite = max(1, min(limite or 10, 20))
    return jsonify({
        'sugerencias': ingredientes.sugerencias(
            store().load_recetas(), consulta, limite),
    })


@bp.route('/api/generar', methods=['POST'])
def api_generar():
    """Lanza la generación en segundo plano y responde 202 al instante."""
    datos = request.get_json(silent=True) or {}
    fecha_inicio = str(datos.get('fecha_inicio') or '')
    fecha_fin = str(datos.get('fecha_fin') or '')
    feedback = str(datos.get('feedback') or '')

    _, _, error = generation.parse_fechas(fecha_inicio, fecha_fin)
    if error:
        return jsonify({'error': error}), 400

    cfg = current_app.llm_config
    if not cfg.get('api_key') or not cfg.get('model'):
        return jsonify({
            'error': 'Falta la configuración del LLM (config_local.json: strata_api_key/strata_model)'
        }), 500

    job = current_app.generation_jobs.crear(
        store(), cfg, fecha_inicio, fecha_fin, feedback=feedback)
    return jsonify({'ok': True, 'job': job}), 202


@bp.route('/api/generar/activos')
def api_generar_activos():
    """Trabajos pendientes o en proceso; la UI los usa como flag global."""
    return jsonify({'activos': current_app.generation_jobs.activos()})


@bp.route('/api/generar/<job_id>')
def api_generar_estado(job_id):
    job = current_app.generation_jobs.obtener(job_id)
    if not job:
        return jsonify({'error': 'Trabajo de generación no encontrado'}), 404
    return jsonify(job)


# --- CRUD de recetas (fase 5) ---

@bp.route('/api/recetas', methods=['POST'])
def apicrear_receta():
    datos = request.get_json(silent=True) or {}
    recetas_data = store().load_recetas()
    receta, error = helpers.validar_receta(datos, helpers.nombres_de(recetas_data))
    if error:
        return jsonify({'error': error}), 400

    receta_id = str(datos.get('id') or '').strip()
    if receta_id:
        if not helpers.ID_RE.match(receta_id) or receta_id == 'sobras':
            return jsonify({'error': 'Id inválido (letras minúsculas, números y _)'}), 400
        if receta_id in recetas_data:
            return jsonify({'error': f'Ya existe una receta con id "{receta_id}"'}), 409
    else:
        receta_id = helpers.receta_id_disponible(receta['nombre'], recetas_data)

    if helpers.hay_ciclo_subrecetas(receta_id, receta, recetas_data):
        return jsonify({'error': 'Hay un bucle de subrecetas: una receta no puede enlazarse a sí misma '
                                 '(ni directamente ni a través de otra).'}), 400

    store().save_receta(receta_id, receta)
    return jsonify({'ok': True, 'id': receta_id, 'receta': receta}), 201


@bp.route('/api/receta/<receta_id>', methods=['PUT'])
def api_actualizar_receta(receta_id):
    if not helpers.ID_RE.match(receta_id):
        return jsonify({'error': 'Id inválido'}), 400
    recetas_data = store().load_recetas()
    if receta_id not in recetas_data:
        return jsonify({'error': 'Receta no encontrada'}), 404

    receta, error = helpers.validar_receta(request.get_json(silent=True) or {},
                                           helpers.nombres_de(recetas_data))
    if error:
        return jsonify({'error': error}), 400

    if helpers.hay_ciclo_subrecetas(receta_id, receta, recetas_data):
        return jsonify({'error': 'Hay un bucle de subrecetas: una receta no puede enlazarse a sí misma '
                                 '(ni directamente ni a través de otra).'}), 400

    store().save_receta(receta_id, receta)
    return jsonify({'ok': True, 'id': receta_id, 'receta': receta})


@bp.route('/api/receta/<receta_id>', methods=['DELETE'])
def api_borrar_receta(receta_id):
    if not helpers.ID_RE.match(receta_id):
        return jsonify({'error': 'Id inválido'}), 400
    recetas_data = store().load_recetas()
    if receta_id not in recetas_data:
        return jsonify({'error': 'Receta no encontrada'}), 404

    en_uso = helpers.referencian_receta(store().load_menus(), receta_id)
    padres = helpers.subrecetas_usadas_por(recetas_data, receta_id)
    if (en_uso or padres) and not request.args.get('force'):
        mensaje = []
        if padres:
            mensaje.append(f'{len(padres)} ' + ('receta la usa' if len(padres) == 1
                                               else 'recetas la usan') + ' como subreceta')
        if en_uso:
            mensaje.append('aparece en ' + f'{len(en_uso)} ' +
                           ('menú guardado' if len(en_uso) == 1 else 'menús guardados'))
        return jsonify({
            'error': 'No se puede borrar: ' + ' y '.join(mensaje) + '.',
            'recetas_que_la_usan': padres,
            'n_recetas': len(padres),
            'menus': en_uso,
            'n_menus': len(en_uso),
        }), 409

    materializada_en = []
    if padres:
        # Al forzar, la subreceta se «materializa» antes de borrarla: sus pasos,
        # ingredientes y utensilios pasan a las recetas que la enlazaban, que vuelven
        # a ser autocontenidas y no pierden nada de la lista de la compra.
        catalogo_nombres = helpers.nombres_de(recetas_data)
        for pid in padres:
            nuevo_padre = helpers.materializar_subreceta(
                recetas_data[pid], receta_id, recetas_data, catalogo_nombres)
            store().save_receta(pid, nuevo_padre)
            materializada_en.append(pid)

    store().delete_receta(receta_id)
    return jsonify({'ok': True, 'materializada_en': materializada_en})


# --- CRUD de menús (fase 5) ---

@bp.route('/api/menu', methods=['POST'])
def api_crear_menu():
    datos = request.get_json(silent=True) or {}
    try:
        d_ini = datetime.strptime(str(datos.get('fecha_inicio') or ''), '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Fecha de inicio inválida (AAAA-MM-DD)'}), 400
    n_dias = int(datos.get('n_dias') or 7)
    if not (1 <= n_dias <= 14):
        return jsonify({'error': 'El menú debe tener entre 1 y 14 días'}), 400

    menus_data = store().load_menus()
    menu_id = f'semana_{d_ini.strftime("%Y%m%d")}'
    if menu_id in menus_data:
        return jsonify({'error': f'Ya existe el menú {menu_id}'}), 409

    menu = {
        'titulo': str(datos.get('titulo') or '').strip() or f'Semana del {d_ini.strftime("%d/%m/%Y")}',
        'fecha_inicio': d_ini.strftime('%Y-%m-%d'),
        'fecha_fin': (d_ini + timedelta(days=n_dias - 1)).strftime('%Y-%m-%d'),
        'dias': [
            {
                'dia': helpers.DIAS_SEMANA[(d_ini + timedelta(days=i)).weekday()],
                'comida': 'Sobras', 'id_comida': 'sobras',
                'cena': 'Sobras', 'id_cena': 'sobras',
            }
            for i in range(n_dias)
        ],
    }
    store().save_menu(menu_id, menu)
    return jsonify({'ok': True, 'id': menu_id, 'menu': menu}), 201


@bp.route('/api/menu/<menu_id>', methods=['PUT'])
def api_actualizar_menu(menu_id):
    if not helpers.ID_RE.match(menu_id):
        return jsonify({'error': 'Id inválido'}), 400
    menus_data = store().load_menus()
    if menu_id not in menus_data:
        return jsonify({'error': 'Menú no encontrado'}), 404

    catalogo_ids = set(store().load_recetas().keys())
    menu, error = helpers.validar_menu(request.get_json(silent=True) or {}, catalogo_ids)
    if error:
        return jsonify({'error': error}), 400

    anterior = menus_data[menu_id]
    guardado = dict(anterior)
    guardado.update(menu)
    d_ini, d_fin = helpers.get_menu_range(menu_id, anterior)
    if d_ini and d_fin:
        guardado['fecha_inicio'] = d_ini.strftime('%Y-%m-%d')
        guardado['fecha_fin'] = d_fin.strftime('%Y-%m-%d')
    store().save_menu(menu_id, guardado)
    return jsonify({'ok': True, 'id': menu_id, 'menu': guardado})


@bp.route('/api/menu/<menu_id>', methods=['DELETE'])
def api_borrar_menu(menu_id):
    if not helpers.ID_RE.match(menu_id):
        return jsonify({'error': 'Id inválido'}), 400
    if not store().delete_menu(menu_id):
        return jsonify({'error': 'Menú no encontrado'}), 404
    return jsonify({'ok': True})
