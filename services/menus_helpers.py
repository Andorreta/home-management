"""
Helpers de dominio de menús y recetas: rangos de fechas, normalización de
ingredientes y lista de la compra. Puro: no toca ficheros ni la red.
"""

import re
from datetime import datetime, timedelta

from . import ingredientes

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
    """Parsea una cantidad de ingrediente.
    Conserva cualquier unidad ("latas", "tazas", "trozos"...), no solo las
    de una lista cerrada, para no perder información al mostrar la receta."""
    if not qty_str:
        return {"val": 0, "unit": ""}

    qty_str = str(qty_str).lower().strip()

    # Fracciones: "1/2 taza", "1 / 2"
    match = re.match(r'^(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*(.*)$', qty_str)
    if match:
        try:
            num = float(match.group(1).replace(',', '.'))
            den = float(match.group(2).replace(',', '.'))
            return {"val": num / den, "unit": match.group(3).strip()}
        except (ValueError, ZeroDivisionError):
            pass

    # Cantidades con unidades: "100 gr", "0.5 unidades", "1 lata"
    match = re.match(r'^(\d+(?:[.,]\d+)?)\s*(.*)$', qty_str)
    if match:
        try:
            return {"val": float(match.group(1).replace(',', '.')),
                    "unit": match.group(2).strip()}
        except ValueError:
            pass

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


# Unidades que no se pluralizan (gramos, mililitros, abreviaturas)
_UNIDADES_SIN_PLURAL = {'', 'g', 'gr', 'kg', 'ml', 'l', 'lt', 'lts', 'cm', 'mm',
                        'ud', 'uds', 'grs'}


def _unidad_singular(unit):
    """'latas' -> 'lata', 'unidades' -> 'unidad'; deja 'g'/'ml' igual."""
    u = str(unit or '').strip().lower()
    if not u or ' ' in u or u in _UNIDADES_SIN_PLURAL:
        return u
    if u.endswith('es') and len(u) > 3:
        return u[:-2]
    if u.endswith('s') and len(u) > 2:
        return u[:-1]
    return u


def _unidad_plural(base):
    """'lata' -> 'latas', 'unidad' -> 'unidades'; no toca 'g'/'ml'."""
    if not base or base in _UNIDADES_SIN_PLURAL:
        return base
    if base.endswith('z'):
        return base[:-1] + 'ces'
    if base[-1] in 'aeiouáéíóú':
        return base + 's'
    return base + 'es'


def _presentar_unidades(mapa):
    """Fusiona unidades equivalentes y elige singular/plural según la cantidad."""
    resultado = {}
    for ingrediente, unidades in mapa.items():
        nuevas = {}
        for unit, val in unidades.items():
            display = unit if val == 1 or not unit else _unidad_plural(unit)
            nuevas[display] = nuevas.get(display, 0) + val
        resultado[ingrediente] = nuevas
    return resultado


def process_ingredient(ingrediente, data, mandatory_map, optional_map):
    """Procesa un ingrediente para la lista de la compra"""
    # Normalizamos primero el ingrediente y su valor
    ingrediente, data = normalize_ingredient(ingrediente, data)
    ingrediente = ingredientes.canonico(ingrediente)

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

        unit_key = _unidad_singular(unit)
        current_val = target_map[ingrediente].get(unit_key, 0)
        target_map[ingrediente][unit_key] = current_val + val


_ACENTOS = str.maketrans({'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
                         'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u', 'ü': 'u'})


def _norm_palabra(texto):
    """minúsculas, sin acentos, sin símbolos: para comparar nombres de ingrediente."""
    s = str(texto).lower().translate(_ACENTOS)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def esta_excluido(nombre, exclusiones):
    """True si el ingrediente contiene una exclusión como palabra suelta
    ('sal' casa con 'sal' y 'sal gruesa' pero no con 'salmón'; plural simple incluido)."""
    n = _norm_palabra(nombre)
    if not n:
        return False
    for ex in exclusiones:
        e = _norm_palabra(ex)
        if not e:
            continue
        if n == e or re.search(r'(?<![a-z0-9])' + re.escape(e) + r's?(?![a-z0-9])', n):
            return True
    return False


def get_shopping_list(menus_data, recetas_data, exclusiones=None):
    """Genera la lista de la compra agrupada por ingredientes.
    `exclusiones` (despensa básica) quita los ingredientes que la contengan
    como palabra suelta: 'sal' excluye 'sal' y 'sal gruesa', no 'salmón'."""
    mandatory_ingredients, optional_ingredients = _shopping_raw(menus_data, recetas_data)
    if exclusiones:
        for mapa in (mandatory_ingredients, optional_ingredients):
            for clave in [k for k in mapa if esta_excluido(k, exclusiones)]:
                del mapa[clave]
    return _presentar_unidades(mandatory_ingredients), _presentar_unidades(optional_ingredients)


def _shopping_raw(menus_data, recetas_data):
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
    """Copia de la receta con los ingredientes normalizados y estandarizados."""
    receta = receta.copy()
    if 'ingredientes' in receta:
        new_ing = {}
        for k, v in receta['ingredientes'].items():
            nk, nv = normalize_ingredient(k, v)
            nk = ingredientes.canonico(nk)
            if nk in new_ing:
                new_ing[nk] = ingredientes.fusionar_valores(new_ing[nk], nv)
            else:
                new_ing[nk] = nv
        receta['ingredientes'] = new_ing
    return receta


# --- Soporte del CRUD (fase 5) ---

ID_RE = re.compile(r'^[a-z0-9][a-z0-9_]{0,59}$')

SLUG_TRADE = str.maketrans({
    'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
    'ñ': 'n', 'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
})


def slugify(nombre):
    """'Pollo al curry (con arroz)' -> 'pollo_al_curry_con_arroz'."""
    s = nombre.lower().strip().translate(SLUG_TRADE)
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')[:60]


def receta_id_disponible(nombre, existentes):
    """Id slug único para una receta nueva (huye de 'sobras' y colisiones)."""
    base = slugify(nombre) or 'receta'
    candidate = base
    n = 2
    while candidate == 'sobras' or candidate in existentes:
        candidate = f'{base}_{n}'
        n += 1
    return candidate


def validar_receta(datos):
    """Comprueba el cuerpo enviado por la web. Devuelve (receta_limpia, error)."""
    if not isinstance(datos, dict):
        return None, 'El cuerpo debe ser un objeto JSON'

    nombre = str(datos.get('nombre') or '').strip()
    if not nombre:
        return None, 'La receta necesita un nombre'

    ingredientes_datos = datos.get('ingredientes')
    if not isinstance(ingredientes_datos, dict) or not ingredientes_datos:
        return None, 'La receta necesita al menos un ingrediente'
    limpios = {}
    for clave, valor in ingredientes_datos.items():
        clave = str(clave).strip()
        if not clave:
            return None, 'Hay un ingrediente sin nombre'
        if isinstance(valor, dict):
            valor = {
                'cantidad': str(valor.get('cantidad', '')).strip(),
                'opcional': valor.get('opcional') in (True, 'yes', 'sí'),
            }
            if not valor['opcional']:
                del valor['opcional']
        elif isinstance(valor, bool):
            return None, f'Cantidad inválida en "{clave}"'
        elif isinstance(valor, (int, float)):
            valor = str(valor)
        elif isinstance(valor, str):
            valor = valor.strip()
        else:
            return None, f'Cantidad inválida en "{clave}"'

        canonica = ingredientes.canonico(clave)
        if canonica in limpios:
            # Dos alias del mismo ingrediente: se guardan como uno solo.
            limpios[canonica] = ingredientes.fusionar_valores(limpios[canonica], valor)
        else:
            limpios[canonica] = valor

    def lista_texto(clave):
        valores = datos.get(clave) or []
        if isinstance(valores, str):
            valores = [valores]
        if not isinstance(valores, list):
            return None, f'"{clave}" debe ser una lista'
        return [str(v).strip() for v in valores if str(v).strip()], None

    utensilios, err = lista_texto('utensilios')
    if err:
        return None, err
    pasos, err = lista_texto('pasos')
    if err:
        return None, err

    receta = {'nombre': nombre, 'utensilios': utensilios,
              'ingredientes': limpios, 'pasos': pasos}
    notas = str(datos.get('notas') or '').strip()
    if notas:
        receta['notas'] = notas
    return receta, None


def referencian_receta(menus_data, receta_id):
    """Ids de los menús que usan una receta en comida o cena."""
    return sorted(
        name for name, menu in menus_data.items()
        if any(dia.get('id_comida') == receta_id or dia.get('id_cena') == receta_id
               for dia in menu.get('dias', []))
    )


def validar_menu(menu, catalogo_ids):
    """Valida el payload de edición de un menú. Devuelve (menu_limpio, error)."""
    if not isinstance(menu, dict) or not isinstance(menu.get('dias'), list) or not menu['dias']:
        return None, 'El menú necesita días'
    dias = []
    for i, dia in enumerate(menu['dias'], start=1):
        if not isinstance(dia, dict):
            return None, f'Día {i} inválido'
        entrada = {'dia': str(dia.get('dia') or '').strip() or f'Día {i}'}
        for clave in ('comida', 'cena'):
            rid = str(dia.get(f'id_{clave}') or '').strip()
            nombre = str(dia.get(clave) or '').strip()
            if rid == 'sobras':
                entrada[clave] = nombre or 'Sobras'
                entrada[f'id_{clave}'] = 'sobras'
            elif rid in catalogo_ids:
                entrada[clave] = nombre or rid
                entrada[f'id_{clave}'] = rid
            else:
                return None, f'Día {i}: la {clave} no es una receta del catálogo ni sobras'
        dias.append(entrada)
    limpio = dict(menu)
    limpio['dias'] = dias
    if not str(limpio.get('titulo') or '').strip():
        limpio['titulo'] = 'Menú'
    return limpio, None
