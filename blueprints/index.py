"""
Blueprint del portal: pantalla de índice con las secciones de home-management.
"""

from flask import Blueprint, render_template

bp = Blueprint('index', __name__)


@bp.route('/')
def portal():
    return render_template('portal.html')
