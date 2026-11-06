"""
Blueprint de gastos e ingresos (home-expenses).
Datos sobre SQLite a través del store (models/factory.create_gastos_store).
"""

from flask import Blueprint, current_app, jsonify, render_template, request

bp = Blueprint('gastos', __name__, url_prefix='/gastos')


def store():
    return current_app.gastos_store


# --- Página ---

@bp.route('/')
def index():
    return render_template('gastos/index.html')


# --- API ---

@bp.route('/api/movimientos')
def api_movimientos():
    try:
        limit = min(int(request.args.get('limit', 50)), 500)
    except ValueError:
        limit = 50
    movimientos = store().list_movimientos(
        limit=limit,
        desde=request.args.get('desde') or None,
        hasta=request.args.get('hasta') or None,
        tipo=request.args.get('tipo') or None,
    )
    return jsonify(movimientos)


@bp.route('/api/movimientos', methods=['POST'])
def api_alta_movimiento():
    datos = request.get_json(silent=True) or {}
    try:
        mov = store().add_movimiento(
            datos.get('fecha', ''),
            datos.get('tipo', ''),
            datos.get('importe', ''),
            datos.get('categoria', ''),
            datos.get('descripcion', ''),
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(mov), 201


@bp.route('/api/movimiento/<int:mov_id>', methods=['PUT'])
def api_editar_movimiento(mov_id):
    datos = request.get_json(silent=True) or {}
    try:
        mov = store().update_movimiento(
            mov_id,
            datos.get('fecha', ''),
            datos.get('tipo', ''),
            datos.get('importe', ''),
            datos.get('categoria', ''),
            datos.get('descripcion', ''),
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    if mov is None:
        return jsonify({'error': 'Movimiento no encontrado'}), 404
    return jsonify(mov)


@bp.route('/api/movimiento/<int:mov_id>', methods=['DELETE'])
def api_borrar_movimiento(mov_id):
    if not store().delete_movimiento(mov_id):
        return jsonify({'error': 'Movimiento no encontrado'}), 404
    return jsonify({'ok': True})


@bp.route('/api/resumen')
def api_resumen():
    try:
        meses = int(request.args.get('meses', 12))
    except ValueError:
        meses = 12
    return jsonify(store().get_resumen(meses))


@bp.route('/api/comparativa')
def api_comparativa():
    try:
        meses = int(request.args.get('meses', 12))
    except ValueError:
        meses = 12
    return jsonify(store().get_resumen_comparativo(meses))


@bp.route('/api/categorias')
def api_categorias():
    return jsonify(store().list_categorias())
