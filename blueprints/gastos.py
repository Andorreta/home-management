"""
Blueprint de gastos e ingresos (home-expenses).
Fase 1: esqueleto. La funcionalidad llega en la fase 2 (SQLite + gráficos).
"""

from flask import Blueprint, render_template

bp = Blueprint('gastos', __name__, url_prefix='/gastos')


@bp.route('/')
def index():
    return render_template('gastos/index.html')
