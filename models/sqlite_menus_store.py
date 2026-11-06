"""
Backend SQLite para menús y recetas (migración de la fase 4).
Modelo documental: cada menú/receta guarda su JSON completo en `data`, con
columnas extraídas (fechas, nombre) para consultar sin parsear todo.
Una BD por módulo: data/menus.db (los gastos viven en expenses.db).
"""

import json
import os
import sqlite3

from .base import DEFAULT_PREFERENCIAS, MenusStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS menus (
    id           TEXT PRIMARY KEY,          -- p. ej. semana_20261102
    titulo       TEXT NOT NULL DEFAULT '',
    fecha_inicio TEXT,
    fecha_fin    TEXT,
    data         TEXT NOT NULL              -- JSON completo del menú
);
CREATE INDEX IF NOT EXISTS idx_menus_fecha ON menus (fecha_inicio);
CREATE TABLE IF NOT EXISTS recetas (
    id     TEXT PRIMARY KEY,
    nombre TEXT NOT NULL DEFAULT '',
    data   TEXT NOT NULL                    -- JSON completo de la receta
);
CREATE TABLE IF NOT EXISTS preferencias (
    id   INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);
"""


class SqliteMenusStore(MenusStore):
    """
    settings es un diccionario con:
      db_path: ruta del fichero de la base de datos (p. ej. data/menus.db)
    """

    def __init__(self, settings):
        self.db_path = settings['db_path']

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def check_connection(self):
        try:
            os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)
            with self._conn() as conn:
                conn.execute('SELECT 1')
            return True
        except Exception:
            return False

    def init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def is_empty(self):
        """True si no hay ni menús ni recetas (probablemente falta la migración)."""
        with self._conn() as conn:
            n = conn.execute('SELECT COUNT(*) AS c FROM menus').fetchone()['c']
            m = conn.execute('SELECT COUNT(*) AS c FROM recetas').fetchone()['c']
        return n == 0 and m == 0

    # --- Preferencias ---

    def load_preferencias(self):
        preferencias = dict(DEFAULT_PREFERENCIAS)
        with self._conn() as conn:
            row = conn.execute('SELECT data FROM preferencias WHERE id = 1').fetchone()
        if row:
            preferencias.update(json.loads(row['data']))
        return preferencias

    def save_preferencias(self, preferencias):
        with self._conn() as conn:
            conn.execute(
                'INSERT INTO preferencias (id, data) VALUES (1, ?) '
                'ON CONFLICT(id) DO UPDATE SET data = excluded.data',
                (json.dumps(preferencias, ensure_ascii=False),),
            )

    # --- Menús ---

    def load_menus(self):
        with self._conn() as conn:
            rows = conn.execute('SELECT id, data FROM menus').fetchall()
        return {r['id']: json.loads(r['data']) for r in rows}

    def save_menu(self, menu_id, menu):
        with self._conn() as conn:
            conn.execute(
                'INSERT INTO menus (id, titulo, fecha_inicio, fecha_fin, data) VALUES (?, ?, ?, ?, ?) '
                'ON CONFLICT(id) DO UPDATE SET titulo = excluded.titulo, '
                'fecha_inicio = excluded.fecha_inicio, fecha_fin = excluded.fecha_fin, '
                'data = excluded.data',
                (menu_id, menu.get('titulo', ''), menu.get('fecha_inicio'),
                 menu.get('fecha_fin'), json.dumps(menu, ensure_ascii=False)),
            )

    # --- Recetas ---

    def load_recetas(self):
        with self._conn() as conn:
            rows = conn.execute('SELECT id, data FROM recetas').fetchall()
        return {r['id']: json.loads(r['data']) for r in rows}

    def save_receta(self, receta_id, receta):
        with self._conn() as conn:
            conn.execute(
                'INSERT INTO recetas (id, nombre, data) VALUES (?, ?, ?) '
                'ON CONFLICT(id) DO UPDATE SET nombre = excluded.nombre, data = excluded.data',
                (receta_id, receta.get('nombre', receta_id), json.dumps(receta, ensure_ascii=False)),
            )

    def delete_receta(self, receta_id):
        with self._conn() as conn:
            cur = conn.execute('DELETE FROM recetas WHERE id = ?', (receta_id,))
        return cur.rowcount > 0
