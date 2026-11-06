"""
Helpers de dominio de menús y recetas: rangos de fechas, normalización de
ingredientes y lista de la compra. Puro: no toca ficheros ni la red.
"""

import re
from datetime import datetime, timedelta

# Paleta de colores para distinguir menús en el calendario
MENU_COLORS = ['#4e79a7', '#e15759', '#59a14f', '#f28e2b', '#b07aa1', '#76b7b2', '#edc948', '#ff9da7']

DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

# Utensilios que NO se permiten (el usuario solo tiene una cazuela, una sartén y un microondas con grill)
UTENSILIOS_PERMITIDOS = ('cazuela', 'sartén', 'sarten', 'microondas', 'cuchillo', 'varillas', 'tupper', 'recipiente', 'plato apto')


def utensilios_compatibles(receta):
    """True si la receta se puede hacer solo con cazuela, sartén y microondas con grill."""
    for u in receta.get('utensilios', []):
        u_low = u.lower()
        if not any(p in u_low for p in UTENSILIOS_PERMITIDOS):
            return False
    return True


def get_recetas_usadas_recently(menus_data, fecha_inicio, semanas):
    """Ids de recetas usadas en menús que empezaron dentro de las últimas `semanas`."""
    usados = set()
    try:
        limite = datetime.strptime(fecha_inicio, '%Y-%m-%d') - timedelta(weeks=semanas)
    except ValueError:
        return usados
    for name, menu in menus_data.items():
        d_ini, d_fin = get_menu_range(name, menu)
        if d_ini and limite <= d_ini < datetime.strptime(fecha_inicio, '%Y-%m-%d'):
            for dia in menu.get('dias', []):
                for clave in ('id_comida', 'id_cena'):
                    rid = dia.get(clave)
                    if rid and rid != 'sobras':
                        usados.add(rid)
    return usados


def get_menu_range(menu_name, menu):
    """Devuelve (fecha_inicio, fecha_fin) del menú.
    Usa los campos explícitos del JSON y, si no existen, los deriva
    del nombre del archivo (semana_YYYYMMDD) y del número de días."""
    ini = menu.get('fecha_inicio')
    if ini:
        try:
            d_ini = datetime.strptime(ini, '%Y-%m-%d')
            fin = menu.get('fecha_fin')
            if fin:
                d_fin = datetime.strptime(fin, '%Y-%m-%d')
            else:
                d_fin = d_ini + timedelta(days=max(len(menu.get('dias', [])), 1) - 1)
            return d_ini, d_fin
        except ValueError:
            pass
    match = re.match(r'^semana_(\d{8})$', menu_name)
    if not match:
        return None, None
    d_ini = datetime.strptime(match.group(1), '%Y%m%d')
    d_fin = d_ini + timedelta(days=max(len(menu.get('dias', [])), 1) - 1)
    return d_ini, d_fin


def parse_quantity(qty_str):
    """Parsea una cantidad de ingrediente"""
    if not qty_str:
        return {"val": 0, "unit": ""}

    qty_str = str(qty_str).lower().strip()

    # Manejar fracciones
    if '/' in qty_str:
        parts = qty_str.split('/')
        if len(parts) == 2:
            try:
                num = float(parts[0])
                den = float(parts[1])
                val = num / den
                unit = qty_str.replace(f"{num}/{den}", "").strip()
                return {"val": val, "unit": unit}
            except:
                pass

    # Manejar cantidades con unidades (g, ml, etc.)
    match = re.match(r'^([\d.]+)\s*(.*)$', qty_str)
    if match:
        val = float(match.group(1))
        unit = match.group(2).strip()
        # Si la unidad está en la parte final y es g o ml, usarla
        if unit.endswith(('g', 'ml', 'kg', 'l', 'unidad', 'unidades', 'pizca', 'cucharada', 'cucharadita')):
            return {"val": val, "unit": unit}
        else:
            return {"val": val, "unit": ""}

    return {"val": 0, "unit": qty_str}


def normalize_ingredient(key, value):
    """
    Normaliza un ingrediente:
    - "aceite_de_oliva_ml": 10 -> "aceite de oliva": {"val": 10, "unit": "ml"}
    - "Pasta fresca": "100 gr" -> "Pasta fresca": {"val": 100, "unit": "gr"}
    """
    # 1. Caso: llave con sufijo de unidad (ej: aceite_de_oliva_ml)
    match = re.match(r'^(.*)_([a-z]+)$', key)
    if match:
        new_key = match.group(1).replace('_', ' ')
        unit_from_key = match.group(2)

        if isinstance(value, (int, float)):
            return new_key, {"val": float(value), "unit": unit_from_key}

        if isinstance(value, str):
            parsed = parse_quantity(value)
            # Si el string tiene su propia unidad, la priorizamos, si no, usamos la de la llave
            return new_key, {"val": parsed['val'], "unit": parsed['unit'] if parsed['unit'] else unit_from_key}

        if isinstance(value, dict):
            qty_str = value.get('cantidad', '')
            parsed = parse_quantity(qty_str)
            new_val = {"val": parsed['val'], "unit": parsed['unit']}
            if value.get('opcional') in [True, "yes", "sí"]:
                new_val['opcional'] = True
            return new_key, new_val

    # 2. Caso: valor es string tipo "100 gr"
    if isinstance(value, str):
        parsed = parse_quantity(value)
        if parsed['val'] > 0:
            return key, parsed

    # 3. Caso: valor es un diccionario (formato antiguo)
    if isinstance(value, dict):
        qty_str = value.get('cantidad', '')
        if qty_str:
            parsed = parse_quantity(qty_str)
            new_val = {"val": parsed['val'], "unit": parsed['unit']}
            if value.get('opcional') in [True, "yes", "sí"]:
                new_val['opcional'] = True
            return key, new_val

    return key, value


def process_ingredient(ingrediente, data, mandatory_map, optional_map):
    """Procesa un ingrediente para la lista de la compra"""
    # Normalizamos primero el ingrediente y su valor
    ingrediente, data = normalize_ingredient(ingrediente, data)

    if not ingrediente:
        return

    is_optional = False
    val = 0
    unit = ""

    if isinstance(data, dict):
        val = data.get('val', 0)
        unit = data.get('unit', '')
        is_optional = data.get('opcional', False)
    elif isinstance(data, (int, float)):
        val = float(data)
    elif isinstance(data, str):
        parsed = parse_quantity(data)
        val = parsed['val']
        unit = parsed['unit']

    target_map = optional_map if is_optional else mandatory_map

    if val > 0:
        if ingrediente not in target_map:
            target_map[ingrediente] = {}

        unit_key = unit or ''
        current_val = target_map[ingrediente].get(unit_key, 0)
        target_map[ingrediente][unit_key] = current_val + val


def get_shopping_list(menus_data, recetas_data):
    """Genera la lista de la compra agrupada por ingredientes"""
    mandatory_ingredients = {}
    optional_ingredients = {}

    for menu_name, menu in menus_data.items():
        if 'dias' in menu:
            for day in menu['dias']:
                # Procesar comida y cena
                for meal_type in ['comida', 'cena']:
                    if f'id_{meal_type}' in day and day[f'id_{meal_type}'] and day[f'id_{meal_type}'] != "sobras":
                        receta_id = day[f'id_{meal_type}']
                        if receta_id in recetas_data:
                            receta = recetas_data[receta_id]
                            if 'ingredientes' in receta:
                                for ingrediente, data in receta['ingredientes'].items():
                                    process_ingredient(ingrediente, data, mandatory_ingredients, optional_ingredients)

    return mandatory_ingredients, optional_ingredients


def normalize_receta(receta):
    """Copia de la receta con los ingredientes normalizados para su presentación."""
    receta = receta.copy()
    if 'ingredientes' in receta:
        new_ing = {}
        for k, v in receta['ingredientes'].items():
            nk, nv = normalize_ingredient(k, v)
            new_ing[nk] = nv
        receta['ingredientes'] = new_ing
    return receta
