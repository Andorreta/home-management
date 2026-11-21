#!/usr/bin/env python3
"""
Pasa a ASCII los ids de receta (y menú) que tengan acentos, eñes u otros caracteres.

Los nombres se dejan intactos: «Tortilla de champiñones» sigue igual, pero su id
pasa a tortilla_champinones. Ajusta también todo lo que apunta al id viejo:
los marcadores [subreceta](id) de otras recetas y los platos guardados en los
menús (id_comida / id_cena).

Por defecto solo enseña lo que haría. Para escribir:

    python migrar_ids_ascii.py --apply

Uso:
    python migrar_ids_ascii.py              # dry-run (no escribe)
    python migrar_ids_ascii.py --apply      # aplica (hace respaldo de la BD)
    python migrar_ids_ascii.py --apply --json-tambien
                                            # y los JSON viejos de data/recetas
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime

from models.factory import create_store
from services import menus_helpers as helpers
from settings import get_config


def nuevo_id(receta_id, receta, existentes):
    """Id ASCII para una receta: del nombre, y si no, del id viejo."""
    nombre = str(receta.get('nombre') or '')
    candidato = helpers.slugify(nombre) or helpers.slugify(receta_id) or 'receta'
    if candidato == 'sobras' or candidato in existentes or candidato == receta_id:
        candidato = helpers.receta_id_disponible(nombre or receta_id, existentes)
    return candidato


def plan_de_renombrados(recetas):
    """{id_viejo: id_nuevo} de las recetas cuyo id no cumple ID_RE."""
    plan = {}
    existentes = set(recetas)
    for receta_id, receta in recetas.items():
        if helpers.ID_RE.match(receta_id) and receta_id != 'sobras':
            continue
        nuevo = nuevo_id(receta_id, receta, existentes | set(plan.values()))
        plan[receta_id] = nuevo
    return plan


def reescribir_pasos(pasos, plan):
    """Cambia los [subreceta](id viejos) por su id nuevo. Devuelve (pasos, cambios)."""
    cambios = 0

    def sustituir(match):
        nonlocal cambios
        crudo = match.group(1).strip()
        if crudo in plan:
            cambios += 1
            return f'[subreceta]({plan[crudo]})'
        return match.group(0)

    nuevos = [re.sub(helpers.SUBRECETA_RE.pattern, sustituir, str(paso)) for paso in pasos or []]
    return nuevos, cambios


def reescribir_menu(menu, plan):
    """Cambia cualquier valor igual al id viejo (id_comida / id_cena y compañía)."""
    cambios = 0

    def andar(nodo):
        nonlocal cambios
        if isinstance(nodo, dict):
            for clave, valor in nodo.items():
                if isinstance(valor, str) and valor in plan:
                    nodo[clave] = plan[valor]
                    cambios += 1
                else:
                    andar(valor)
        elif isinstance(nodo, list):
            for i, valor in enumerate(nodo):
                if isinstance(valor, str) and valor in plan:
                    nodo[i] = plan[valor]
                    cambios += 1
                else:
                    andar(valor)

    andar(menu)
    return cambios


def comprobar(store):
    """Devuelve problemas: ids malos, platos de menú sin receta y enlaces rotos nuevos."""
    recetas = store.load_recetas()
    menus = store.load_menus()
    problemas = []
    for receta_id in recetas:
        if not helpers.ID_RE.match(receta_id):
            problemas.append(f'id de receta sigue sin ser ASCII: {receta_id!r}')
    catalogo = helpers.nombres_de(recetas)
    for menu_id, menu in menus.items():
        for dia in menu.get('dias', []) or []:
            for clave in ('id_comida', 'id_cena'):
                rid = dia.get(clave)
                if rid and rid != 'sobras' and rid not in recetas:
                    problemas.append(f'menú {menu_id} ({dia.get("dia")}): {clave}={rid!r} no existe')
        for viejo in [v for v in catalogo if not helpers.ID_RE.match(v)]:
            problemas.append(f'menú {menu_id} referencia el id no ASCII {viejo!r}')
    for receta_id, receta in recetas.items():
        for paso in receta.get('pasos', []) or []:
            for crudo in helpers.subrecetas_en_texto(str(paso)):
                _sub, error = helpers.resolver_subreceta(crudo, catalogo)
                if error:
                    problemas.append(f'receta {receta_id}: enlace roto {crudo!r}')
    return problemas


def migrar(store, apply_changes, etiquetas=''):
    recetas = store.load_recetas()
    plan = plan_de_renombrados(recetas)
    if not plan:
        print(f'{etiquetas}Todos los ids ya son ASCII ({len(recetas)} recetas). Nada que hacer.')
        return 0

    print(f'{etiquetas}{len(plan)} id(s) que cambiar de {len(recetas)} recetas:')
    for viejo, nuevo in sorted(plan.items()):
        print(f'  - {viejo!r} → {nuevo!r}   («{(recetas[viejo] or {}).get("nombre", "")}»)')

    menus = store.load_menus()
    tocados_menús = {m: reescribir_menu(menu, plan) for m, menu in menus.items()}
    tocados_menús = {m: n for m, n in tocados_menús.items() if n}
    for menu_id, n in sorted(tocados_menús.items()):
        print(f'    menú {menu_id}: {n} referencia(s) de plato')
    enlazadas = 0
    for receta in recetas.values():
        _p, n = reescribir_pasos(receta.get('pasos', []), plan)
        enlazadas += n
    print(f'    marcadores [subreceta](…) a reescribir: {enlazadas}')

    if not apply_changes:
        print('\ndry-run: no se ha escrito nada. Repite con --apply.')
        return 0

    # 1) recetas nuevas con el id ASCII (primero crear, luego borrar la vieja)
    existentes = set(recetas)
    for viejo, nuevo in sorted(plan.items()):
        receta = recetas[viejo]
        pasos, _n = reescribir_pasos(receta.get('pasos', []), plan)
        receta = dict(receta)
        receta['pasos'] = pasos
        store.save_receta(nuevo, receta)
        existentes.add(nuevo)
    for viejo in sorted(plan):
        store.delete_receta(viejo)

    # 2) el resto de recetas que apuntaban al id viejo en sus pasos
    recetas = store.load_recetas()
    for receta_id, receta in recetas.items():
        pasos, n = reescribir_pasos(receta.get('pasos', []), plan)
        if n:
            receta = dict(receta)
            receta['pasos'] = pasos
            store.save_receta(receta_id, receta)

    # 3) los menús
    for menu_id, menu in store.load_menus().items():
        n = reescribir_menu(menu, plan)
        if n:
            store.save_menu(menu_id, menu)

    problemas = comprobar(store)
    if problemas:
        print('ESCRITO, pero la comprobación final encuentra problemas:')
        for p in problemas[:20]:
            print('  -', p)
        return 2
    print(f'OK: {len(store.load_recetas())} recetas con id ASCII y '
          f'{len(store.load_menus())} menús apuntando a recetas que existen.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='escribir los cambios')
    parser.add_argument('--json-tambien', action='store_true',
                        help='aplicar lo mismo a los JSON viejos de data/recetas')
    args = parser.parse_args()

    config = get_config()
    store = create_store(config.STORE, {
        'db_path': config.MENUS_DB,
        'data_dir': config.DATA_DIR,
    })

    if args.apply and config.STORE == 'sqlite' and os.path.exists(config.MENUS_DB):
        respaldo = f'{config.MENUS_DB}.antes-ascii-{datetime.now().strftime("%Y%m%d%H%M")}.bak'
        shutil.copy2(config.MENUS_DB, respaldo)
        os.chmod(respaldo, 0o640)
        print(f'Respaldo de la BD en {respaldo}')

    codigo = migrar(store, args.apply, etiquetas=f'Almacén {config.STORE}: ')

    if args.json_tambien and config.STORE != 'json':
        from models.json_store import JsonStore
        json_store = JsonStore({'data_dir': config.DATA_DIR})
        if json_store.check_connection():
            codigo = max(codigo, migrar(json_store, args.apply, etiquetas='Almacén json (respaldo): '))
        else:
            print(f'No hay almacén JSON en {config.DATA_DIR}')

    return codigo


if __name__ == '__main__':
    sys.exit(main())
