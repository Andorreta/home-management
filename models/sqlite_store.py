"""
Backend SQLite para los gastos de la casa (home-expenses).
Una BD por módulo (data/expenses.db), tabla única de movimientos:
cada fila es un gasto o un ingreso, lo que permite el balance.
"""

import os
import sqlite3
from datetime import date

from .base import GastosStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS movimientos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT NOT NULL,                       -- AAAA-MM-DD
    tipo        TEXT NOT NULL CHECK (tipo IN ('gasto', 'ingreso')),
    importe     REAL NOT NULL CHECK (importe > 0),
    categoria   TEXT NOT NULL DEFAULT '',
    descripcion TEXT NOT NULL DEFAULT '',
    ticket_path TEXT,                                -- fase 3: ruta de la foto del ticket
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos (fecha);
"""


def _row_to_dict(row):
    return {
        'id': row['id'],
        'fecha': row['fecha'],
        'tipo': row['tipo'],
        'importe': row['importe'],
        'categoria': row['categoria'],
        'descripcion': row['descripcion'],
        'ticket_path': row['ticket_path'],
        'created_at': row['created_at'],
    }


class SqliteStore(GastosStore):
    """
    settings es un diccionario con:
      db_path: ruta del fichero de la base de datos (p. ej. data/expenses.db)
    """

    def __init__(self, settings):
        self.db_path = settings['db_path']

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def check_connection(self):
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with self._conn() as conn:
                conn.execute('SELECT 1')
            return True
        except Exception:
            return False

    def init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    # --- Validación común de un movimiento ---

    @staticmethod
    def _validate(fecha, tipo, importe, categoria, descripcion):
        if not fecha:
            raise ValueError('Falta la fecha')
        try:
            date.fromisoformat(fecha)
        except ValueError:
            raise ValueError('Fecha inválida (formato AAAA-MM-DD)')
        if tipo not in ('gasto', 'ingreso'):
            raise ValueError("El tipo debe ser 'gasto' o 'ingreso'")
        try:
            importe = float(importe)
        except (TypeError, ValueError):
            raise ValueError('Importe inválido')
        if importe <= 0:
            raise ValueError('El importe debe ser mayor que 0')
        return fecha, tipo, round(importe, 2), (categoria or '').strip(), (descripcion or '').strip()

    # --- Altas, modificaciones y bajas ---

    def add_movimiento(self, fecha, tipo, importe, categoria, descripcion):
        fecha, tipo, importe, categoria, descripcion = self._validate(
            fecha, tipo, importe, categoria, descripcion)
        with self._conn() as conn:
            cur = conn.execute(
                'INSERT INTO movimientos (fecha, tipo, importe, categoria, descripcion) '
                'VALUES (?, ?, ?, ?, ?)',
                (fecha, tipo, importe, categoria, descripcion),
            )
            row = conn.execute('SELECT * FROM movimientos WHERE id = ?', (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)

    def update_movimiento(self, mov_id, fecha, tipo, importe, categoria, descripcion):
        fecha, tipo, importe, categoria, descripcion = self._validate(
            fecha, tipo, importe, categoria, descripcion)
        with self._conn() as conn:
            cur = conn.execute(
                'UPDATE movimientos SET fecha = ?, tipo = ?, importe = ?, categoria = ?, descripcion = ? '
                'WHERE id = ?',
                (fecha, tipo, importe, categoria, descripcion, mov_id),
            )
            if not cur.rowcount:
                return None
            row = conn.execute('SELECT * FROM movimientos WHERE id = ?', (mov_id,)).fetchone()
        return _row_to_dict(row)

    def delete_movimiento(self, mov_id):
        with self._conn() as conn:
            cur = conn.execute('DELETE FROM movimientos WHERE id = ?', (mov_id,))
        return cur.rowcount > 0

    # --- Consultas ---

    def list_movimientos(self, limit=50, desde=None, hasta=None, tipo=None):
        sql = 'SELECT * FROM movimientos WHERE 1=1'
        params = []
        if desde:
            sql += ' AND fecha >= ?'
            params.append(desde)
        if hasta:
            sql += ' AND fecha <= ?'
            params.append(hasta)
        if tipo:
            sql += ' AND tipo = ?'
            params.append(tipo)
        sql += ' ORDER BY fecha DESC, id DESC LIMIT ?'
        params.append(int(limit))
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_resumen(self, meses=12):
        """Últimos `meses` meses calendario con totales y balance acumulado."""
        meses = max(1, min(int(meses), 60))
        hoy = date.today()
        # Primer mes de la ventana (YYYY-MM)
        anio, mes = hoy.year, hoy.month - (meses - 1)
        while mes <= 0:
            mes += 12
            anio -= 1
        primer_mes = f'{anio:04d}-{mes:02d}'

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT strftime('%Y-%m', fecha) AS mes, "
                "COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN importe END), 0) AS ingresos, "
                "COALESCE(SUM(CASE WHEN tipo = 'gasto' THEN importe END), 0) AS gastos "
                "FROM movimientos WHERE strftime('%Y-%m', fecha) >= ? "
                "GROUP BY mes ORDER BY mes",
                (primer_mes,),
            ).fetchall()
            # Saldo previo a la ventana, para que el acumulado sea real
            saldo_antes = conn.execute(
                "SELECT COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN importe ELSE -importe END), 0) "
                "FROM movimientos WHERE strftime('%Y-%m', fecha) < ?",
                (primer_mes,),
            ).fetchone()[0]

        por_mes = {r['mes']: r for r in rows}
        resultado = []
        acumulado = saldo_antes
        for i in range(meses):
            m = f'{anio:04d}-{mes:02d}'
            r = por_mes.get(m)
            ingresos = r['ingresos'] if r else 0
            gastos = r['gastos'] if r else 0
            balance = ingresos - gastos
            acumulado += balance
            resultado.append({
                'mes': m,
                'ingresos': round(ingresos, 2),
                'gastos': round(gastos, 2),
                'balance': round(balance, 2),
                'acumulado': round(acumulado, 2),
            })
            mes += 1
            if mes > 12:
                mes = 1
                anio += 1
        return resultado

    def list_categorias(self):
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT DISTINCT tipo, categoria FROM movimientos '
                "WHERE categoria != '' ORDER BY categoria"
            ).fetchall()
        resultado = {'gasto': [], 'ingreso': []}
        for r in rows:
            resultado[r['tipo']].append(r['categoria'])
        return resultado
