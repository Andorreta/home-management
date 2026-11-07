"""
Estandarización de nombres de ingredientes.

El catálogo (ingredientes_catalogo.json) define, para cada ingrediente
canónico, sus alias: "atún en lata" -> "atún en conserva", "pimiento" ->
"pimiento rojo", "huevos" -> "huevo", etc.

Se usa para:
- guardar recetas con nombres canónicos y fusionar duplicados;
- agrupar la lista de la compra aunque las recetas antiguas usen alias;
- sugerir ingredientes en el alta/edición de recetas.
"""

import json
import os
import re
import unicodedata

_CATALOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'ingredientes_catalogo.json')


def _sin_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto)
                   if not unicodedata.combining(c))


def _norm(texto):
    """minúsculas, sin acentos, sin símbolos y con espacios simples."""
    s = _sin_acentos(str(texto or '').lower())
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def limpiar(nombre):
    """Quita espacios sobrantes sin cambiar mayúsculas/minúsculas."""
    return re.sub(r'\s+', ' ', str(nombre or '').strip())


def _cargar_catalogo():
    try:
        with open(_CATALOGO_PATH, 'r', encoding='utf-8') as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return []
    entradas = []
    for entrada in datos:
        if isinstance(entrada, str):
            entrada = {'nombre': entrada, 'alias': []}
        nombre = limpiar(entrada.get('nombre'))
        if not nombre:
            continue
        alias = [limpiar(a) for a in entrada.get('alias', []) if limpiar(a)]
        entradas.append({'nombre': nombre, 'alias': alias})
    return entradas


CATALOGO = _cargar_catalogo()

# alias normalizado -> nombre canónico
_CANONICO = {}
for _entrada in CATALOGO:
    _CANONICO[_norm(_entrada['nombre'])] = _entrada['nombre']
    for _alias in _entrada['alias']:
        _CANONICO.setdefault(_norm(_alias), _entrada['nombre'])


def _variantes_singular(key):
    """Prueba plurales simples: huevos -> huevo, champiñones -> champiñón."""
    variantes = []
    if key.endswith('s') and len(key) > 3:
        variantes.append(key[:-1])
        if key.endswith('es') and len(key) > 4:
            variantes.append(key[:-2])
    return variantes


def canonico(nombre):
    """Devuelve el nombre canónico de un ingrediente (o el nombre limpio)."""
    nombre = limpiar(nombre)
    if not nombre:
        return nombre
    key = _norm(nombre)
    if key in _CANONICO:
        return _CANONICO[key]
    for variante in _variantes_singular(key):
        if variante in _CANONICO:
            return _CANONICO[variante]
    return nombre


_UNIDADES = {
    'unidad': 'unidad', 'unidades': 'unidad', 'ud': 'unidad', 'uds': 'unidad',
    'g': 'g', 'gr': 'g', 'gramo': 'g', 'gramos': 'g',
    'kg': 'kg', 'kilo': 'kg', 'kilos': 'kg',
    'ml': 'ml', 'l': 'l', 'litro': 'l', 'litros': 'l',
    'cucharada': 'cucharada', 'cucharadas': 'cucharada',
    'cucharadita': 'cucharadita', 'cucharaditas': 'cucharadita',
}


def _clave_unidad(unit):
    u = _norm(unit)
    return _UNIDADES.get(u, u[:-1] if u.endswith('s') else u)


def _parse_cantidad(texto):
    """Devuelve (valor, unidad) o None. Acepta '1/2', '0.5', '50 ml'."""
    s = str(texto or '').strip().lower()
    if not s:
        return None
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*(.*)$', s)
    if m:
        try:
            val = float(m.group(1).replace(',', '.')) / float(m.group(2).replace(',', '.'))
        except (ValueError, ZeroDivisionError):
            return None
        return val, m.group(3).strip()
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s*(.*)$', s)
    if m:
        try:
            return float(m.group(1).replace(',', '.')), m.group(2).strip()
        except ValueError:
            return None
    return None


def _formatear_numero(val):
    if abs(val - round(val)) < 1e-9:
        return str(int(round(val)))
    return ('%.3f' % val).rstrip('0').rstrip('.')


def _fusionar_cantidades(a, b):
    a = limpiar(a)
    b = limpiar(b)
    if not a:
        return b
    if not b:
        return a
    pa, pb = _parse_cantidad(a), _parse_cantidad(b)
    if (pa and pb and pa[0] > 0 and pb[0] > 0 and
            _clave_unidad(pa[1]) == _clave_unidad(pb[1])):
        total = _formatear_numero(pa[0] + pb[0])
        return (total + ' ' + pb[1]).strip()
    return a + ' + ' + b


def _valor_a_texto(valor):
    if isinstance(valor, dict):
        if 'cantidad' in valor:
            return limpiar(valor.get('cantidad'))
        if 'val' in valor:
            unit = limpiar(valor.get('unit'))
            return (limpiar(_formatear_numero(float(valor.get('val') or 0))) +
                    (' ' + unit if unit else '')).strip()
    return limpiar(valor)


def _es_opcional(valor):
    if isinstance(valor, dict):
        return valor.get('opcional') in (True, 'yes', 'sí')
    return False


def fusionar_valores(a, b):
    """Fusiona dos cantidades del mismo ingrediente sin perder información."""
    cantidad = _fusionar_cantidades(_valor_a_texto(a), _valor_a_texto(b))
    if _es_opcional(a) and _es_opcional(b):
        return {'cantidad': cantidad, 'opcional': True}
    return cantidad


def canonicalizar(ingredientes):
    """
    Devuelve un diccionario con claves canónicas. Si dos alias apuntan al
    mismo ingrediente, fusiona sus cantidades.
    """
    resultado = {}
    for clave, valor in (ingredientes or {}).items():
        clave = canonico(clave)
        if not clave:
            continue
        if clave in resultado:
            resultado[clave] = fusionar_valores(resultado[clave], valor)
        else:
            resultado[clave] = valor
    return resultado


def sugerencias(recetas_data=None, consulta='', limite=10):
    """
    Sugerencias para el autocompletado. Combina el catálogo con los
    ingredientes realmente usados en las recetas (para que los nuevos
    ingredientes aparezcan sin tocar el catálogo).
    """
    q = _norm(consulta)

    usos = {}
    existentes = {}
    for receta in (recetas_data or {}).values():
        vistos = set()
        for clave in (receta.get('ingredientes') or {}):
            nombre = canonico(clave)
            key = _norm(nombre)
            if not key or key in vistos:
                continue
            vistos.add(key)
            usos[key] = usos.get(key, 0) + 1
            existentes[key] = nombre

    candidatos = {}
    for entrada in CATALOGO:
        nombre = entrada['nombre']
        key = _norm(nombre)
        candidatos.setdefault(key, {
            'nombre': nombre, 'alias': set(), 'usos': usos.get(key, 0),
        })
        candidatos[key]['alias'].update(entrada['alias'])
    for key, nombre in existentes.items():
        candidatos.setdefault(key, {'nombre': nombre, 'alias': set()})
        candidatos[key]['usos'] = usos.get(key, 0)

    resultados = []
    for key, item in candidatos.items():
        nombre = item['nombre']
        alias = item['alias']
        alias_coincidente = None

        if q:
            if _norm(nombre) == q:
                score = 0
            else:
                exactos = [a for a in alias if _norm(a) == q]
                if exactos:
                    score = 1
                    alias_coincidente = exactos[0]
                elif _norm(nombre).startswith(q) or any(_norm(a).startswith(q) for a in alias):
                    score = 2
                elif q in _norm(nombre) or any(q in _norm(a) for a in alias):
                    score = 3
                else:
                    continue
        else:
            score = 4

        resultados.append((score, -item['usos'], nombre, alias_coincidente))

    resultados.sort(key=lambda r: (r[0], r[1], r[2].lower()))
    return [
        {'nombre': nombre, 'alias': alias, 'usos': -neg_usos}
        for _, neg_usos, nombre, alias in resultados[:limite]
    ]
