"""
Backend JSON: envuelve exactamente el comportamiento actual de home-cooking
(ficheros en data/menus, data/recetas y data/preferencias.json).
"""

import json
import os

from .base import DEFAULT_PREFERENCIAS, MenusStore


class JsonStore(MenusStore):
    """
    settings es un diccionario con:
      data_dir: directorio raíz de datos (contiene menus/, recetas/ y preferencias.json)
    """

    def __init__(self, settings):
        self.data_dir = settings['data_dir']

    def check_connection(self):
        return os.path.isdir(self.data_dir)

    def _load_json_files(self, directory):
        """Carga todos los archivos JSON de un directorio"""
        data = {}
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                if filename.endswith('.json'):
                    filepath = os.path.join(directory, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            key = filename.replace('.json', '')
                            data[key] = json.load(f)
                    except Exception as e:
                        print(f"Error cargando {filename}: {e}")
        return data

    # --- Preferencias ---

    def load_preferencias(self):
        defaults = dict(DEFAULT_PREFERENCIAS)
        path = os.path.join(self.data_dir, 'preferencias.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    prefs = json.load(f)
                defaults.update(prefs)
            except Exception as e:
                print(f"Error leyendo preferencias.json: {e}")
        return defaults

    # --- Menús ---

    def load_menus(self):
        return self._load_json_files(os.path.join(self.data_dir, 'menus'))

    def save_menu(self, menu_id, menu):
        directory = os.path.join(self.data_dir, 'menus')
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, menu_id + '.json'), 'w', encoding='utf-8') as f:
            json.dump(menu, f, ensure_ascii=False, indent=2)
            f.write('\n')

    # --- Recetas ---

    def load_recetas(self):
        return self._load_json_files(os.path.join(self.data_dir, 'recetas'))
