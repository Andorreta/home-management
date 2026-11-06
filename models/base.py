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
