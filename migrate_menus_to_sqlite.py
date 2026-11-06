#!/usr/bin/env python3
"""
Migración de menús/recetas/preferencias de ficheros JSON a SQLite (data/menus.db).

Idempotente: se puede repetir, vuelca otra vez todos los ficheros (upsert).
NO borra los JSON: quedan como respaldo hasta confirmar la paridad.

Uso:
    python migrate_menus_to_sqlite.py            # migrar y verificar
    python migrate_menus_to_sqlite.py --dry-run  # solo contar, no escribir
"""

import argparse
import sys

from models.json_store import JsonStore
from models.sqlite_menus_store import SqliteMenusStore
from settings import get_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='no escribe nada')
    args = parser.parse_args()

    config = get_config()
    data_dir = config.DATA_DIR
    db_path = config.MENUS_DB

    origen = JsonStore({'data_dir': data_dir})
    if not origen.check_connection():
        print(f'No hay directorio de datos JSON en {data_dir}')
        return 1

    menus = origen.load_menus()
    recetas = origen.load_recetas()
    preferencias = origen.load_preferencias()
    print(f'Origen JSON ({data_dir}): {len(menus)} menús, {len(recetas)} recetas')

    if args.dry_run:
        print('dry-run: no se ha escrito nada')
        return 0

    destino = SqliteMenusStore({'db_path': db_path})
    if not destino.check_connection():
        print(f'No se pudo abrir la BD {db_path}')
        return 1
    destino.init_db()

    for menu_id, menu in menus.items():
        destino.save_menu(menu_id, menu)
    for receta_id, receta in recetas.items():
        destino.save_receta(receta_id, receta)
    destino.save_preferencias(preferencias)
    print(f'Migrado a {db_path}')

    # --- Verificación de paridad (comparación profunda, no solo conteos) ---
    mal = []
    destino_menus = destino.load_menus()
    if set(destino_menus) != set(menus):
        mal.append('menus: lista de ids distinta')
    for menu_id, menu in menus.items():
        if destino_menus.get(menu_id) != menu:
            mal.append(f'menú {menu_id}: contenido distinto')
    destino_recetas = destino.load_recetas()
    if set(destino_recetas) != set(recetas):
        mal.append('recetas: lista de ids distinta')
    for receta_id, receta in recetas.items():
        if destino_recetas.get(receta_id) != receta:
            mal.append(f'receta {receta_id}: contenido distinto')
    if destino.load_preferencias() != preferencias:
        mal.append('preferencias: contenido distinto')

    if mal:
        print('PARIDAD FALLIDA:')
        for problema in mal[:20]:
            print('  -', problema)
        return 2

    print(f'PARIDAD OK: {len(destino_menus)} menús y {len(destino_recetas)} recetas idénticos')
    print('Los JSON siguen en su sitio como respaldo; HM_STORE=sqlite usará ya la BD.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
