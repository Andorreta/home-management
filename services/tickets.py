"""
Análisis de fotos de tickets con el modelo de visión (Strata).
Devuelve una sugerencia de movimiento para precargar el formulario;
el usuario confirma o corrige antes de guardar nada.
"""

import re
from datetime import date, datetime, timedelta

from . import llm

PROMPT = (
    'Analiza la foto de este ticket/comprobante de compra español y extrae los datos.\n'
    'Responde SOLO con JSON válido, sin explicaciones ni cercas de código, con este formato exacto:\n'
    '{"fecha": "AAAA-MM-DD", "tienda": "nombre del establecimiento", '
    '"total": 0.00, "categoria": "una de: compra, restaurante, transporte, gasolina, '
    'farmacia, suministros, ropa, ocio, recibos, otros", '
    '"articulos": [{"descripcion": "...", "importe": 0.00}]}\n'
    'Reglas: "total" es el importe TOTAL pagado (el de la línea TOTAL, impuestos incluidos). '
    'Si el ticket está en pesetas o tiene importes parciales, usa solo el total final. '
    'La fecha en formato AAAA-MM-DD (año actual si el ticket no lo indica). '
    '"articulos" con los productos, vacía si no se distinguen. Si la foto no es un ticket, '
    'responde {"error": "no es un ticket"}.'
)

FECHAS_RELATIVAS = {
    'hoy': 0, 'ayer': -1, 'anteayer': -2,
}


def _normaliza_fecha(valor):
    """Aceita AAAA-MM-DD, DD/MM/AA, DD/MM/AAAA, 'hoy'... Devuelve ISO o ''."""
    valor = (valor or '').strip()
    if not valor:
        return ''
    hoy = date.today()
    if valor.lower() in FECHAS_RELATIVAS:
        return (hoy + timedelta(days=FECHAS_RELATIVAS[valor.lower()])).isoformat()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y'):
        try:
            return datetime.strptime(valor, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})', valor)
    if m:
        d, mes, anio = m.groups()
        anio = int(anio)
        if anio < 100:
            anio += 2000
        try:
            return date(anio, int(mes), int(d)).isoformat()
        except ValueError:
            pass
    return ''


def _normaliza_importe(valor):
    """'1.234,56', '9,45', 9.45, '9.45 EUR' -> float o None."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r'[^\d,.-]', '', str(valor))
    if not s:
        return None
    if ',' in s and '.' in s:
        # formato español: miles con punto, decimales con coma
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def analizar_ticket(cfg, image_bytes, mime='image/jpeg'):
    """Devuelve la sugerencia normalizada: {fecha, tienda, total, categoria, articulos}.
    Lanza ValueError si el modelo no produce algo util."""
    if not cfg['api_key']:
        raise ValueError('Falta la configuración del LLM (config_local.json)')

    contenido = llm.call_llm_vision(cfg, PROMPT, image_bytes, mime)
    try:
        datos = llm.parse_llm_json(contenido)
    except ValueError:
        raise ValueError('El análisis no devolvió un JSON interpretable')

    if datos.get('error'):
        raise ValueError(f'El modelo no pudo leer el ticket: {datos["error"]}')

    articulos = []
    for a in datos.get('articulos') or []:
        if not isinstance(a, dict):
            continue
        imp = _normaliza_importe(a.get('importe'))
        if imp and a.get('descripcion'):
            articulos.append({'descripcion': str(a['descripcion']).strip(), 'importe': round(imp, 2)})

    total = _normaliza_importe(datos.get('total'))
    if total is None and articulos:
        total = round(sum(a['importe'] for a in articulos), 2)

    tienda = str(datos.get('tienda') or '').strip()
    categoria = str(datos.get('categoria') or '').strip().lower()
    if categoria not in ('compra', 'restaurante', 'transporte', 'gasolina', 'farmacia',
                         'suministros', 'ropa', 'ocio', 'recibos', 'otros'):
        categoria = 'compra' if categoria in ('supermercado', '') else categoria or 'otros'

    return {
        'fecha': _normaliza_fecha(datos.get('fecha')),
        'tienda': tienda,
        'total': round(total, 2) if total is not None else None,
        'categoria': categoria,
        'articulos': articulos,
    }
