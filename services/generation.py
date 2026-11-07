"""
Generación de menús con el LLM (Strata) y fusión con los menús existentes.
Recibe el store por parámetro: no sabe si los datos viven en JSON o en SQLite.
"""

from datetime import datetime, timedelta

from . import llm
from . import menus_helpers as helpers


def parse_fechas(fecha_inicio, fecha_fin):
    """
    Valida el rango de fechas y devuelve (d_ini, d_fin, error).
    Se usa tanto para rechazar una petición inválida al instante como dentro
    de la generación en segundo plano.
    """
    try:
        d_ini = datetime.strptime(str(fecha_inicio or ''), '%Y-%m-%d')
        d_fin = datetime.strptime(str(fecha_fin or ''), '%Y-%m-%d')
    except (ValueError, TypeError):
        return None, None, 'Fechas inválidas (formato AAAA-MM-DD)'
    n_dias = (d_fin - d_ini).days + 1
    if not (1 <= n_dias <= 14):
        return None, None, 'El rango debe ser de 1 a 14 días'
    return d_ini, d_fin, None


def generar_menu(store, cfg, fecha_inicio, fecha_fin, feedback=''):
    """
    Valida fechas, pide un menú al LLM y lo guarda (creando o fusionando con
    los menús que solapen). `feedback` es un texto libre del usuario con el
    contexto del momento ("esta semana estoy flojo, hazlo simple").
    Devuelve (respuesta_dict, codigo_http).
    """
    d_ini, d_fin, error = parse_fechas(fecha_inicio, fecha_fin)
    if error:
        return {'error': error}, 400
    n_dias = (d_fin - d_ini).days + 1

    if not cfg['api_key'] or not cfg['model']:
        return {'error': 'Falta la configuración del LLM (config_local.json: strata_api_key/strata_model)'}, 500

    recetas_data = store.load_recetas()
    catalogo = {
        rid: r.get('nombre', rid)
        for rid, r in recetas_data.items()
        if helpers.utensilios_compatibles(r)
    }
    if len(catalogo) < n_dias:
        return {'error': f'No hay suficientes recetas compatibles con tus utensilios ({len(catalogo)})'}, 400

    prefs = store.load_preferencias()
    menus_data = store.load_menus()
    usados = helpers.get_recetas_usadas_recently(menus_data, fecha_inicio, prefs.get('evitar_repetir_de_semanas', 4))
    favoritas = set(prefs.get('favoritas', []))

    rango_dias = ', '.join(helpers.DIAS_SEMANA[(d_ini + timedelta(days=i)).weekday()] for i in range(n_dias))
    catalogo_txt = '\n'.join(f'{rid}: {nombre}' for rid, nombre in sorted(catalogo.items(), key=lambda x: x[1].lower()))
    habituales_txt = ', '.join(prefs.get('platos_habituales', [])) or '(sin lista)'
    usados_txt = ', '.join(
        f'{rid} ({catalogo.get(rid, "?")})' + (' ★favorita' if rid in favoritas else '')
        for rid in sorted(usados)
    ) or '(ninguna)'
    favoritas_txt = ', '.join(f'{rid} ({catalogo.get(rid, "?")})' for rid in sorted(favoritas) if rid in catalogo) or '(sin lista)'

    feedback_txt = str(feedback or '').strip()[:1000]
    bloque_feedback = ''
    if feedback_txt:
        bloque_feedback = f"""
CONTEXTO DE ESTA SEMANA (el usuario explica cómo está ahora mismo; ajusta el
menú a lo que pide —más simple, más ligero, reconfortante...— SIN romper nunca
las restricciones obligatorias ni las reglas de composición):
{feedback_txt}
"""

    system = ('Eres el planificador de comidas de un usuario con hipersensibilidad sensorial (autismo). '
              'Respetas estrictamente sus restricciones. Respondes SOLO con JSON válido, sin explicaciones ni cercas de código.')
    user_prompt = f"""Genera un menú de {n_dias} días, del {fecha_inicio} al {fecha_fin} (días: {rango_dias}).

RESTRICCIONES OBLIGATORIAS:
{chr(10).join('- ' + r for r in prefs.get('restricciones', []))}
{bloque_feedback}
CATÁLOGO DE RECETAS DISPONIBLES (ya filtradas por utensilios; elige SOLO ids exactos de esta lista; id: nombre):
{catalogo_txt}

RECETAS YA USADAS EN LAS ÚLTIMAS {prefs.get('evitar_repetir_de_semanas', 4)} SEMANAS (procura NO repetir estas, PERO las marcadas con ★favorita sí se pueden repetir aunque sean recientes: uno nunca se cansa de lo que le gusta):
{usados_txt}

RECETAS FAVORITAS (pueden repetirse siempre, incluso si ya salieron hace poco; si encajan, alguna puede aparecer en el menú):
{favoritas_txt}

PLATOS QUE SUELE COMER (referencia de sus gustos; si existe una receta parecida en el catálogo, priorízala; si un plato de esta lista incumple las restricciones, IGNÓRALO):
{habituales_txt}

REGLAS DE COMPOSICIÓN:
- {n_dias} elementos en "dias", en orden: {rango_dias}.
- Cada día: "comida" (plato principal) y "cena" (más ligero), con ids del catálogo.
- No repetir la misma receta en toda la semana.
- Variar el tipo de plato entre días (no pasta dos días seguidos, por ejemplo).

DEVUELVE EXACTAMENTE este JSON:
{{"titulo": "título corto y descriptivo del menú", "dias": [{{"comida": "<id>", "cena": "<id>"}}{', ...' if n_dias > 1 else ''}]}}"""

    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user_prompt}]

    error_anterior = None
    for intento in range(2):
        try:
            contenido = llm.call_llm(cfg, messages, max_tokens=cfg.get('max_tokens', 2500))
            generado = llm.parse_llm_json(contenido)
        except OSError as e:
            return {'error': f'No se pudo contactar con el LLM ({cfg["url"]}): {e}'}, 502
        except ValueError as e:
            error_anterior = f'JSON inválido: {e}'
            messages.append({'role': 'user', 'content': f'Error: {error_anterior}. Repite la respuesta SOLO con el JSON correcto.'})
            continue

        dias = generado.get('dias', [])
        problemas = []
        if len(dias) != n_dias:
            problemas.append(f'se esperaban {n_dias} días y vienen {len(dias)}')
        ids_del_menu = []
        for i, dia in enumerate(dias):
            for clave in ('comida', 'cena'):
                rid = str(dia.get(clave, ''))
                if rid not in catalogo:
                    problemas.append(f'día {i + 1}: id "{rid}" no está en el catálogo')
                else:
                    ids_del_menu.append(rid)
        if len(set(ids_del_menu)) != len(ids_del_menu):
            problemas.append('hay recetas repetidas en el menú')
        if problemas:
            error_anterior = '; '.join(problemas)
            messages.append({'role': 'user', 'content': 'Error en tu JSON: ' + error_anterior + '. Repite SOLO el JSON corrigiéndolo, usando ids exactos del catálogo.'})
            continue

        menu = {
            'titulo': generado.get('titulo') or f'Semana {d_ini.strftime("%d %b")} - {d_fin.strftime("%d %b %Y")}',
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'dias': [
                {
                    'dia': helpers.DIAS_SEMANA[(d_ini + timedelta(days=i)).weekday()],
                    'comida': catalogo[dia['comida']],
                    'id_comida': dia['comida'],
                    'cena': catalogo[dia['cena']],
                    'id_cena': dia['cena'],
                }
                for i, dia in enumerate(dias)
            ],
        }

        # --- Fusionar con los menús existentes que solapen el rango ---
        # (si no solapa ninguno, se crea un fichero nuevo)
        solapes = []
        for name, m in menus_data.items():
            m_ini, m_fin = helpers.get_menu_range(name, m)
            if m_ini and m_fin and m_ini <= d_fin and d_ini <= m_fin:
                solapes.append((name, m, m_ini, m_fin))

        nuevo_por_fecha = {
            d_ini + timedelta(days=i): {
                'dia': helpers.DIAS_SEMANA[(d_ini + timedelta(days=i)).weekday()],
                'comida': catalogo[dia['comida']],
                'id_comida': dia['comida'],
                'cena': catalogo[dia['cena']],
                'id_cena': dia['cena'],
            }
            for i, dia in enumerate(dias)
        }

        if not solapes:
            archivo = f'semana_{d_ini.strftime("%Y%m%d")}'
            existente = archivo in menus_data
            store.save_menu(archivo, menu)
            return {'ok': True, 'creado': archivo + '.json', 'sobrescrito': existente, 'menu': menu}, 200

        # 1) Contar cuántos días viejos sustituye cada menú del solape
        dias_por_fecha = {}   # nombre -> {fecha: entrada}
        sustituidos = {}
        for name, m, m_ini, m_fin in solapes:
            entradas = {}
            for i, entrada in enumerate(m.get('dias', [])):
                entradas[m_ini + timedelta(days=i)] = entrada
            dias_por_fecha[name] = entradas
            sustituidos[name] = sum(1 for f_ in nuevo_por_fecha if m_ini <= f_ <= m_fin)

        # 2) Asignar cada día nuevo: cada fecha exacta (día + mes) actualiza todos
        #    los menús que la cubren; los días sin cubrir van al menú con menos
        #    días sustituidos (a igualdad, el más cercano). Menús de otros meses
        #    con el mismo número de día nunca se tocan: todo compara fechas completas.
        asignados = {name: {} for name, _, _, _ in solapes}
        nombres = [name for name, _, _, _ in solapes]
        for fecha, entrada in nuevo_por_fecha.items():
            cubren = [name for name, m, m_ini, m_fin in solapes if m_ini <= fecha <= m_fin]
            if cubren:
                for n in cubren:
                    asignados[n][fecha] = entrada
            else:
                def distancia(n):
                    fs = sorted(dias_por_fecha[n])
                    if fecha < fs[0]:
                        return (fs[0] - fecha).days
                    if fecha > fs[-1]:
                        return (fecha - fs[-1]).days
                    return 0
                asignados[min(nombres, key=lambda n: (sustituidos[n], distancia(n)))][fecha] = entrada

        # 3) Reescribir cada menú afectado: sus días fuera del rango + los asignados
        tocados = []
        for name, m, m_ini, m_fin in solapes:
            entradas = dict(dias_por_fecha[name])
            for fecha, entrada in asignados[name].items():
                entradas[fecha] = entrada
            fechas = sorted(entradas)
            nuevo_menu = dict(m)
            nuevo_menu['fecha_inicio'] = fechas[0].strftime('%Y-%m-%d')
            nuevo_menu['fecha_fin'] = fechas[-1].strftime('%Y-%m-%d')
            nuevo_menu['dias'] = [entradas[f_] for f_ in fechas]
            store.save_menu(name, nuevo_menu)
            tocados.append(name)

        return {'ok': True, 'modificados': tocados, 'menu': menu}, 200

    return {'error': f'El modelo generó un menú inválido tras 2 intentos: {error_anterior}'}, 502
