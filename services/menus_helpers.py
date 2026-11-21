"""
Helpers de dominio de menús y recetas: rangos de fechas, normalización de
ingredientes y lista de la compra. Puro: no toca ficheros ni la red.
"""

import re
import unicodedata
from datetime import datetime, timedelta

from . import ingredientes

# Paleta de colores para distinguir menús en el calendario
MENU_COLORS = ['#4e79a7', '#e15759', '#59a14f', '#f28e2b', '#b07aa1', '#76b7b2', '#edc948', '#ff9da7']

DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

# Utensilios que NO se permiten (el usuario solo tiene una cazuela, una sartén y un microondas con grill)
UTENSILIOS_PERMITIDOS = ('cazuela', 'sartén', 'sarten', 'microondas', 'cuchillo', 'varillas', 'tupper', 'recipiente', 'plato apto')


def utensilios_compatibles(receta_id, recetas_data):
    """True si la receta (y las subrecetas que enlaza) se puede hacer solo con
    cazuela, sartén y microondas con grill. Se miran las subrecetas porque los
    utensilios de una preparación base viven en ella, no en el plato."""
    ids, _ = expandir_receta(receta_id, recetas_data)
    for rid in ids:
        for u in recetas_data.get(rid, {}).get('utensilios', []):
            if not any(p in str(u).lower() for p in UTENSILIOS_PERMITIDOS):
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
                            # En cascada: un plato aporta sus ingredientes y los de las
                            # subrecetas enlazadas en sus pasos (una sola vez por plato,
                            # que es lo que se compra para ese plato).
                            ids, _ = expandir_receta(receta_id, recetas_data)
                            for rid in ids:
                                receta = recetas_data[rid]
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
    """'Pollo al curry (con arroz)' -> 'pollo_al_curry_con_arroz'.

    El id sale siempre en ASCII: los acentos y la eñe se deshacen (NFKD) y lo que
    no sea letra o número se convierte en guion bajo. El NOMBRE de la receta puede
    llevar cualquier carácter; el id, no (así las URLs de la API no dependen de la
    codificación)."""
    s = nombre.lower().strip().translate(SLUG_TRADE)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
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


# --- Subrecetas: un paso puede enlazar a otra receta ---
#
# Un paso puede ser (o contener) el marcador  [subreceta](id)  , que en la interfaz
# se pinta como un enlace y abre la receta enlazada en un modal. El marcador vive
# dentro del string del paso, así que no hace falta ningún cambio en los datos:
# recetas viejas y nuevas se guardan exactamente igual. Se guarda el ID (el nombre
# puede cambiar o repetirse); al escribir el nombre a mano se resuelve y se
# reescribe con el id canónico.

SUBRECETA_RE = re.compile(r'\[subreceta\]\(\s*([^)]*?)\s*\)')

# Red de seguridad para cadenas de subrecetas absurdamente largas (un bucle real
# se rechaza al guardar; aquí solo nos protegemos de datos corruptos).
SUBRECETA_MAX_NIVEL = 40


def nombres_de(recetas_data):
    """{id_receta: nombre} para resolver los enlaces de los pasos."""
    return {rid: r.get('nombre', rid) for rid, r in recetas_data.items()}


def resolver_subreceta(texto, catalogo_nombres):
    """Id de la receta enlazada. Devuelve (id, error).

    Acepta el id exacto, su slug o el nombre de la receta (sin acentos ni mayúsculas)."""
    t = str(texto or '').strip()
    if not t:
        return None, 'el enlace está vacío'
    if t in catalogo_nombres:
        return t, None

    sl = slugify(t)
    if sl in catalogo_nombres:
        return sl, None

    clave = _norm_palabra(t)
    gemelas = [rid for rid, nombre in catalogo_nombres.items() if _norm_palabra(nombre) == clave]
    if len(gemelas) == 1:
        return gemelas[0], None
    if len(gemelas) > 1:
        return None, f'varias recetas se llaman "{t}"; usa su id'
    return None, f'no existe ninguna receta para "{t}"'


def subrecetas_en_texto(texto):
    """Textos de los marcadores de un paso, tal como están escritos."""
    return [m.group(1) for m in SUBRECETA_RE.finditer(str(texto or ''))]


def normalizar_pasos(pasos, catalogo_nombres):
    """Reescribe los marcadores con el id canónico.

    Devuelve (pasos_limpios, errores) donde errores es una lista de frases
    legibles (enlace vacío, inexistente o ambiguo)."""
    limpios = []
    errores = []
    for paso in pasos or []:
        texto = str(paso)

        def sustituir(match):
            crudo = match.group(1)
            rid, error = resolver_subreceta(crudo, catalogo_nombres)
            if error:
                errores.append(f'paso «{_recortar(texto)}»: {error}')
                return match.group(0)
            return f'[subreceta]({rid})'

        limpios.append(SUBRECETA_RE.sub(sustituir, texto))
    return limpios, errores


def _recortar(texto, largo=40):
    t = ' '.join(str(texto).split())
    return t if len(t) <= largo else t[:largo - 1] + '…'


def subrecetas_de_receta(receta, catalogo_nombres):
    """Ids (sin duplicados, en orden) de las recetas que enlaza una receta."""
    ids = []
    for paso in receta.get('pasos', []) or []:
        for crudo in subrecetas_en_texto(paso):
            rid, _ = resolver_subreceta(crudo, catalogo_nombres)
            if rid and rid not in ids:
                ids.append(rid)
    return ids


def expandir_receta(receta_id, recetas_data):
    """(ids, rotos) de recorrer una receta en cascada.

    ids: la receta y todas las enlazadas, en profundidad, cada una una sola vez
    (los bucles no duplican y no cuelgan el recorrido).
    rotos: [{'receta', 'enlace'}] de los marcadores que ya no apuntan a nada."""
    catalogo_nombres = nombres_de(recetas_data)
    ids, rotos, vistos = [], [], set()
    pila = [(receta_id, 0)]
    while pila:
        rid, nivel = pila.pop()
        if rid in vistos or nivel > SUBRECETA_MAX_NIVEL:
            continue
        vistos.add(rid)
        receta = recetas_data.get(rid)
        if not receta:
            continue
        ids.append(rid)
        for crudo in subrecetas_en_texto('\n'.join(str(p) for p in receta.get('pasos', []) or [])):
            sub, error = resolver_subreceta(crudo, catalogo_nombres)
            if error:
                rotos.append({'receta': rid, 'enlace': crudo.strip()})
            elif sub not in vistos:
                pila.append((sub, nivel + 1))
    return ids, rotos


def aportes_subrecetas(receta_id, recetas_data):
    """Qué aportan las subrecetas de una receta, para enseñarlo en su ficha.

    Devuelve un dict con:
      'ingredientes': {clave: [nombres de subreceta que la aportan]}  (a cualquier nivel)
      'utensilios':   {utensilio: [nombres de subreceta que lo aportan]}
      'arbol':        [{'id', 'nombre', 'directa', 'ingredientes', 'utensilios'}, ...]
    La propia receta no se cuenta. Los enlaces rotos se ignoran y los bucles no
    duplican ni cuelgan el recorrido (usa expandir_receta)."""
    ids, _rotos = expandir_receta(receta_id, recetas_data)
    directas = set(subrecetas_de_receta(recetas_data.get(receta_id) or {},
                                        nombres_de(recetas_data)))
    aportes_ing, aportes_ut, arbol = {}, {}, []
    for sub_id in ids:
        if sub_id == receta_id:
            continue
        sub = recetas_data.get(sub_id)
        if not sub:
            continue
        nombre = str(sub.get('nombre') or sub_id)
        normalizada = normalize_receta(sub)   # las claves como las enseña la API
        ing = [str(k) for k in (normalizada.get('ingredientes') or {}).keys()]
        ut = [str(u) for u in (normalizada.get('utensilios') or []) if str(u).strip()]
        arbol.append({'id': sub_id, 'nombre': nombre, 'directa': sub_id in directas,
                      'ingredientes': sorted(ing), 'utensilios': ut})
        for clave in ing:
            lista = aportes_ing.setdefault(clave, [])
            if nombre not in lista:
                lista.append(nombre)
        for utensilio in ut:
            lista = aportes_ut.setdefault(utensilio, [])
            if nombre not in lista:
                lista.append(nombre)
    arbol.sort(key=lambda a: (not a['directa'], a['nombre']))
    return {'ingredientes': aportes_ing, 'utensilios': aportes_ut, 'arbol': arbol}


def subrecetas_usadas_por(recetas_data, receta_id):
    """Ids de las recetas que enlazan receta_id en alguno de sus pasos."""
    catalogo_nombres = nombres_de(recetas_data)
    usadas_por = {}
    for rid, receta in recetas_data.items():
        if rid == receta_id:
            continue
        if receta_id in subrecetas_de_receta(receta, catalogo_nombres):
            usadas_por[rid] = True
    return sorted(usadas_por)


def indice_usadas_por(recetas_data):
    """{id_receta: [ids de las recetas que la enlazan]} para listar y contar sin repetir recorridos."""
    catalogo_nombres = nombres_de(recetas_data)
    indice = {}
    for rid, receta in recetas_data.items():
        for sub in subrecetas_de_receta(receta, catalogo_nombres):
            if sub != rid:
                indice.setdefault(sub, []).append(rid)
    for lista in indice.values():
        lista.sort()
    return indice


def hay_ciclo_subrecetas(receta_id, receta, recetas_data):
    """True si lo que enlaza la receta crea bucle (se enlaza a sí misma, directa o indirectamente)."""
    catalogo_nombres = nombres_de(recetas_data)
    catalogo_nombres.setdefault(receta_id, receta.get('nombre', receta_id))

    def vecinas(rid):
        origen = receta if rid == receta_id else (recetas_data.get(rid) or {})
        return subrecetas_de_receta(origen, catalogo_nombres)

    en_camino = {receta_id}
    pila = [(receta_id, iter(vecinas(receta_id)))]
    while pila:
        nodo, vecinas_iter = pila[-1]
        avanzado = False
        for sub in vecinas_iter:
            if sub in en_camino:
                return True
            en_camino.add(sub)
            pila.append((sub, iter(vecinas(sub))))
            avanzado = True
            break
        if not avanzado:
            pila.pop()
            en_camino.discard(nodo)
    return False


def materializar_subreceta(padre, sub_id, recetas_data, catalogo_nombres=None):
    """Deshace el enlace de un padre: copia los pasos de la subreceta en el sitio del
    marcador y le suma los ingredientes y utensilios que aquella aportaba.

    Es lo que hace falta para poder borrar una subreceta sin que el plato pierda,
    por ejemplo, la pasta y la sal: la receta vuelve a ser autocontenida."""
    sub = recetas_data.get(sub_id) or {}
    catalogo_nombres = catalogo_nombres if catalogo_nombres is not None else nombres_de(recetas_data)

    pasos = []
    for paso in padre.get('pasos', []) or []:
        texto = str(paso)

        def sustituir(match):
            rid, _ = resolver_subreceta(match.group(1), catalogo_nombres)
            if rid != sub_id:
                return match.group(0)   # otros enlaces siguen apuntando a recetas vivas
            return ''

        sin_enlace = SUBRECETA_RE.sub(sustituir, texto)
        sin_enlace = ' '.join(sin_enlace.split())
        if sin_enlace != ' '.join(texto.split()):
            # Aquí había un enlace a la subreceta que se borra: sus pasos van en su sitio.
            if sin_enlace:
                pasos.append(sin_enlace)
            pasos.extend(str(p) for p in sub.get('pasos', []) or [])
        else:
            pasos.append(texto)

    nuevo = dict(padre)
    nuevo['pasos'] = pasos

    ingredientes = dict(nuevo.get('ingredientes', {}) or {})
    tienen = {ingredientes_canonico(clave) for clave in ingredientes}
    for clave, valor in (sub.get('ingredientes', {}) or {}).items():
        canonica = ingredientes_canonico(clave)
        if canonica not in tienen:
            ingredientes[clave] = valor
            tienen.add(canonica)
    nuevo['ingredientes'] = ingredientes

    utensilios = list(nuevo.get('utensilios', []) or [])
    tienen_u = {str(u).strip().lower() for u in utensilios}
    for u in sub.get('utensilios', []) or []:
        si_u = str(u).strip().lower()
        if si_u and si_u not in tienen_u:
            utensilios.append(u)
            tienen_u.add(si_u)
    nuevo['utensilios'] = utensilios
    return nuevo


def ingredientes_canonico(clave):
    """Clave de ingrediente en forma comparable (canónica, minúscula, sin espacios de más)."""
    return ingredientes.canonico(str(clave).strip())


def validar_receta(datos, catalogo_nombres=None):
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

    # Los enlaces [subreceta](...) se guardan con el id canónico; si apuntan a
    # algo que no existe se rechaza el guardado (la interfaz los elige de una lista).
    if catalogo_nombres is not None:
        pasos, errores = normalizar_pasos(pasos, catalogo_nombres)
        if errores:
            return None, 'Revisa los enlaces a subrecetas: ' + '; '.join(errores)

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
