"""
Blueprint de gastos e ingresos (home-expenses).
Datos sobre SQLite a través del store (models/factory.create_gastos_store).
"""

import os
import uuid
from datetime import date

from flask import (Blueprint, current_app, jsonify, render_template,
                   request, send_file)

from services import tickets as tickets_service

bp = Blueprint('gastos', __name__, url_prefix='/gastos')

MIMES_TICKET = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
TAMANHO_MAX_FOTO = 6 * 1024 * 1024  # el navegador ya comprime a ~1280px


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
            datos.get('ticket_path'),
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


# --- Tickets (fase 3: foto + análisis con visión de Strata) ---

@bp.route('/api/tickets', methods=['POST'])
def api_analizar_ticket():
    foto = request.files.get('foto')
    if not foto:
        return jsonify({'error': 'No llegó la foto (campo "foto")'}), 400
    mime = foto.mimetype
    if mime not in MIMES_TICKET:
        return jsonify({'error': 'Formato no soportado (jpg, png o webp)'}), 400
    imagen = foto.read()
    if len(imagen) > TAMANHO_MAX_FOTO:
        return jsonify({'error': 'La foto es demasiado grande (>6 MB)'}), 400

    # Guardar la foto aunque luego falle el análisis: se puede reintentar o guardar a mano
    data_dir = current_app.config['DATA_DIR']
    subcarpeta = date.today().strftime('%Y-%m')
    ruta_rel = os.path.join('tickets', subcarpeta, uuid.uuid4().hex + MIMES_TICKET[mime])
    os.makedirs(os.path.join(data_dir, 'tickets', subcarpeta), exist_ok=True)
    with open(os.path.join(data_dir, ruta_rel), 'wb') as f:
        f.write(imagen)

    try:
        sugerencia = tickets_service.analizar_ticket(current_app.llm_config, imagen, mime)
    except (ValueError, OSError) as e:
        return jsonify({'ticket_path': ruta_rel, 'error': str(e)}), 502
    return jsonify({'ticket_path': ruta_rel, 'sugerencia': sugerencia})


@bp.route('/ticket/<int:mov_id>')
def ver_ticket(mov_id):
    mov = store().get_movimiento(mov_id)
    if not mov or not mov['ticket_path']:
        return 'Sin ticket', 404
    ruta = os.path.normpath(os.path.join(current_app.config['DATA_DIR'], mov['ticket_path']))
    if not ruta.startswith(os.path.normpath(current_app.config['DATA_DIR']) + os.sep) or not os.path.isfile(ruta):
        return 'Ticket no encontrado', 404
    return send_file(ruta)
