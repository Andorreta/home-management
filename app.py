"""
home-management: aplicación Flask única con las secciones de menús (/menus),
gastos (/gastos) y un portal de entrada (/).

App factory al estilo ScholarCrawler: create_app() carga la configuración del
entorno (settings.py), crea el almacén de datos (models/factory.py) y registra
los blueprints.
"""

import os

from flask import Flask, redirect, request

from models.factory import create_store
from settings import get_config, load_llm_config


def create_app(config_class=None):
    app = Flask(__name__)

    # Config por entorno: HM_CONFIG=LocalConfig|ServerConfig (ver settings.py)
    config_class = config_class or get_config()
    app.config.from_object(config_class)

    # Almacén de datos (con fallback automático a JSON si el backend falla)
    app.store = create_store(app.config['STORE'], {'data_dir': app.config['DATA_DIR']})

    # Configuración del LLM (Strata) compartida por los blueprints
    app.llm_config = load_llm_config(config_class)

    # Crear directorios de datos si no existen
    os.makedirs(os.path.join(app.config['DATA_DIR'], 'menus'), exist_ok=True)
    os.makedirs(os.path.join(app.config['DATA_DIR'], 'recetas'), exist_ok=True)

    from blueprints import index as index_bp
    from blueprints import menus as menus_bp
    from blueprints import gastos as gastos_bp
    app.register_blueprint(index_bp.bp)
    app.register_blueprint(menus_bp.bp)
    app.register_blueprint(gastos_bp.bp)

    register_legacy_redirects(app)
    return app


# URLs antiguas de home-cooking siguen vivas: se redirigen a /menus/*
# (308 conserva el método, importante para el POST de /api/generar)
LEGACY_PAGES = {
    '/recetas': '/menus/recetas',
    '/generar': '/menus/generar',
}


def register_legacy_redirects(app):
    @app.before_request
    def _legacy_redirects():
        path = request.path
        if path == '/home-cooking':
            return redirect('/menus', code=308)
        if path.startswith('/home-cooking/'):
            return redirect('/menus/' + path[len('/home-cooking/'):], code=308)
        if path in LEGACY_PAGES:
            return redirect(LEGACY_PAGES[path], code=308)
        if path == '/api' or path.startswith('/api/'):
            return redirect('/menus' + path, code=308)


app = create_app()


if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', True), host='0.0.0.0', port=5000)
