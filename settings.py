"""
Configuración de home-management, al estilo de ScholarCrawler:
clases de config por entorno, seleccionables con la variable de entorno
HM_CONFIG (LocalConfig por defecto; ServerConfig en el teléfono).
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config(object):
    # Backend de datos de menús/recetas: 'sqlite' (data/menus.db, con fallback
    # automático a 'json' si la BD no existe o está vacía) o 'json' puro
    STORE = os.environ.get('HM_STORE', 'sqlite')
    MENUS_DB = os.environ.get('HM_MENUS_DB', os.path.join(BASE_DIR, 'data', 'menus.db'))

    # Directorio de datos relativo a la raíz del proyecto
    DATA_DIR = os.environ.get('HM_DATA_DIR', os.path.join(BASE_DIR, 'data'))

    # Almacén de gastos (nace sobre SQLite; una BD por módulo)
    GASTOS_STORE = os.environ.get('HM_GASTOS_STORE', 'sqlite')
    GASTOS_DB = os.environ.get('HM_GASTOS_DB', os.path.join(BASE_DIR, 'data', 'expenses.db'))

    # Config del LLM (Strata, API compatible OpenAI): config_local.json o variables de entorno
    STRATA_URL = os.environ.get('STRATA_URL', 'http://192.168.1.12:9931')
    STRATA_API_KEY = os.environ.get('STRATA_API_KEY', '')
    STRATA_MODEL = os.environ.get('STRATA_MODEL', '')
    # Modelo para visión (fotos de tickets); si va vacío, se usa STRATA_MODEL
    STRATA_VISION_MODEL = os.environ.get('STRATA_VISION_MODEL', '')
    # Una IA potente puede tardar varios minutos; la generación ya es en
    # segundo plano, así que aquí solo limita cuánto puede quedarse colgada.
    STRATA_TIMEOUT = int(os.environ.get('STRATA_TIMEOUT', '1800'))
    STRATA_MAX_TOKENS = int(os.environ.get('STRATA_MAX_TOKENS', '4000'))

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
        'vision_model': config_class.STRATA_VISION_MODEL,
        'timeout': config_class.STRATA_TIMEOUT,
        'max_tokens': config_class.STRATA_MAX_TOKENS,
    }
    path = os.path.join(BASE_DIR, 'config_local.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                local = json.load(f)
            cfg['url'] = local.get('strata_url', cfg['url'])
            cfg['api_key'] = local.get('strata_api_key', cfg['api_key'])
            cfg['model'] = local.get('strata_model', cfg['model'])
            cfg['vision_model'] = local.get('strata_vision_model', cfg['vision_model'])
            cfg['timeout'] = int(local.get('strata_timeout', cfg['timeout']))
            cfg['max_tokens'] = int(local.get('strata_max_tokens', cfg['max_tokens']))
        except Exception as e:
            print(f"Error leyendo config_local.json: {e}")
    if not cfg['vision_model']:
        cfg['vision_model'] = cfg['model']
    return cfg
