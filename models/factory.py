"""
Factory de los distintos tipos de almacenes de datos.
Patrón calcado al models/factory.py del TFG ScholarCrawler: se crea el store
desde un nombre y una configuración, con fallback al store JSON si el backend
pedido no está disponible.
"""


def create_store(name, settings):
    """
    Crea un store de datos a partir de su nombre y su configuración.
    El diccionario `settings` tiene claves distintas para cada backend; ver
    cada store. En caso de no poder conectar, hace fallback al store JSON.
    """
    if name == 'sqlite':
        try:
            from . import sqlite_store
            store = sqlite_store.SqliteStore(settings)
            if store.check_connection():
                return store
        except Exception as e:
            print(f"Store sqlite no disponible ({e}); usando json.")
        name = 'json'

    if name == 'json':
        from . import json_store
        store = json_store.JsonStore(settings)
        if store.check_connection():
            return store
        raise ValueError('El almacén JSON no está disponible (falta data_dir).')

    raise ValueError('Unknown database.')


class Database(object):
    # Interfaz base de acceso a datos (ver models/base.py para el detalle)
    def check_connection(self):
        pass
