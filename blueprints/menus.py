"""
Blueprint de menús y recetas: la aplicación home-cooking de siempre, montada
bajo /menus. Todo el acceso a datos pasa por el store (models/factory).
"""

from flask import Blueprint, current_app, jsonify, render_template, request

from services import generation
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

        # Generar lista de la compra
        mandatory_ingredients, optional_ingredients = helpers.get_shopping_list({menu_name: menu}, recetas_data)

        # Preparar datos para la respuesta
        menu_data = {
            'menu': menu,
            'mandatory_ingredients': mandatory_ingredients,
            'optional_ingredients': optional_ingredients,
            'recetas': recetas_data
        }
        return jsonify(menu_data)
    else:
        return jsonify({'error': 'Menú no encontrado'}), 404


@bp.route('/api/receta/<receta_id>')
def api_receta(receta_id):
    recetas_data = store().load_recetas()

    if receta_id in recetas_data:
        # Normalizar receta antes de devolverla
        return jsonify(helpers.normalize_receta(recetas_data[receta_id]))
    else:
        return jsonify({'error': 'Receta no encontrada'}), 404


@bp.route('/api/recetas')
def api_recetas():
    recetas_data = store().load_recetas()
    resultado = [
        {'id': key, 'nombre': receta.get('nombre', key)}
        for key, receta in recetas_data.items()
    ]
    resultado.sort(key=lambda r: r['nombre'].lower())
    return jsonify(resultado)


@bp.route('/api/generar', methods=['POST'])
def api_generar():
    datos = request.get_json(silent=True) or {}
    respuesta, status = generation.generar_menu(
        store(),
        current_app.llm_config,
        datos.get('fecha_inicio', ''),
        datos.get('fecha_fin', ''),
    )
    return jsonify(respuesta), status
