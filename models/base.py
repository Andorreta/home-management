"""
Interfaces de los almacenes de datos (factory al estilo ScholarCrawler).
Los blueprints solo hablan con estas interfaces; nunca con ficheros ni SQL.
"""


class Store(object):
    """Interfaz común a todos los backends de datos."""

    def check_connection(self):
        """True si el backend está disponible (el factory hace fallback si no)."""
        raise NotImplementedError

    # --- Preferencias ---

    def load_preferencias(self):
        raise NotImplementedError

    # --- Menús ---

    def load_menus(self):
        """{nombre_menú: datos} como clave los ids de menú."""
        raise NotImplementedError

    def save_menu(self, menu_id, menu):
        raise NotImplementedError


class MenusStore(Store):
    """El store de menús también sirve el catálogo de recetas."""

    def load_recetas(self):
        """{id_receta: datos}"""
        raise NotImplementedError


class GastosStore(Store):
    """Almacén de movimientos (gastos e ingresos) de la casa."""

    def add_movimiento(self, fecha, tipo, importe, categoria, descripcion):
        """Valida e inserta. Devuelve el movimiento creado (dict). Lanza ValueError si es inválido."""
        raise NotImplementedError

    def update_movimiento(self, mov_id, fecha, tipo, importe, categoria, descripcion):
        """Devuelve el movimiento actualizado (dict) o None si no existe."""
        raise NotImplementedError

    def delete_movimiento(self, mov_id):
        """True si existía y se borró."""
        raise NotImplementedError

    def list_movimientos(self, limit=50, desde=None, hasta=None, tipo=None):
        """Movimientos más recientes primero."""
        raise NotImplementedError

    def get_resumen(self, meses=12):
        """Lista cronológica de los últimos `meses` meses calendario:
        [{mes, ingresos, gastos, balance, acumulado}] (acumulado incluye meses anteriores)."""
        raise NotImplementedError

    def list_categorias(self):
        """{'gasto': [...], 'ingreso': [...]} usadas hasta ahora."""
        raise NotImplementedError
