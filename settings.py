"""
Configuración de home-management, al estilo de ScholarCrawler:
clases de config por entorno, seleccionables con la variable de entorno
HM_CONFIG (LocalConfig por defecto; ServerConfig en el teléfono).
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config(object):
    # Backend de datos: 'json' (ficheros en DATA_DIR) o 'sqlite' (llegará en fases posteriores)
    STORE = os.environ.get('HM_STORE', 'json')

    # Directorio de datos relativo a la raíz del proyecto
    DATA_DIR = os.environ.get('HM_DATA_DIR', os.path.join(BASE_DIR, 'data'))

    # Almacén de gastos (nace sobre SQLite; una BD por módulo)
    GASTOS_STORE = os.environ.get('HM_GASTOS_STORE', 'sqlite')
    GASTOS_DB = os.environ.get('HM_GASTOS_DB', os.path.join(BASE_DIR, 'data', 'expenses.db'))

    # Config del LLM (Strata, API compatible OpenAI): config_local.json o variables de entorno
    STRATA_URL = os.environ.get('STRATA_URL', 'http://192.168.1.12:9931')
    STRATA_API_KEY = os.environ.get('STRATA_API_KEY', '')
    STRATA_MODEL = os.environ.get('STRATA_MODEL', '')

    SECRET_KEY = os.environ.get('HM_SECRET_KEY', 'home-management-dev')


class LocalConfig(Config):
    """Desarrollo en el PC."""
    DEBUG = True


class ServerConfig(Config):
    """Producción en el servidor de casa (teléfono Termux)."""
    DEBUG = False


def get_config():
    name = os.environ.get('HM_CONFIG', 'LocalConfig')
    return {'LocalConfig': LocalConfig, 'ServerConfig': ServerConfig}.get(name, LocalConfig)


def load_llm_config(config_class):
    """Devuelve la config del LLM, permitiendo sobreescribir con config_local.json (gitignoreado)."""
    cfg = {
        'url': config_class.STRATA_URL,
        'api_key': config_class.STRATA_API_KEY,
        'model': config_class.STRATA_MODEL,
    }
    path = os.path.join(BASE_DIR, 'config_local.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                local = json.load(f)
            cfg['url'] = local.get('strata_url', cfg['url'])
            cfg['api_key'] = local.get('strata_api_key', cfg['api_key'])
            cfg['model'] = local.get('strata_model', cfg['model'])
        except Exception as e:
            print(f"Error leyendo config_local.json: {e}")
    return cfg
