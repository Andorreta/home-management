"""
Cliente del LLM (Strata / API compatible OpenAI), independiente del dominio.
"""

import json
import re
import urllib.error
import urllib.request


def call_llm(cfg, messages, max_tokens=2500, temperature=0.8):
    """Llamada a /v1/chat/completions (Strata/llama.cpp). Devuelve el content del asistente."""
    body = json.dumps({
        'model': cfg['model'],
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }).encode('utf-8')
    req = urllib.request.Request(
        cfg['url'].rstrip('/') + '/v1/chat/completions',
        data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f"Bearer {cfg['api_key']}"},
    )
    with urllib.request.urlopen(req, timeout=240) as resp:
        data = json.load(resp)
    choice = (data.get('choices') or [{}])[0]
    content = (choice.get('message') or {}).get('content')
    if not content:
        raise ValueError("El modelo no devolvió contenido (¿max_tokens agotado por el razonamiento?)")
    return content


def parse_llm_json(text):
    """Extrae el JSON de la respuesta, tolerando cercas ```json ... ``` o texto alrededor."""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError('La respuesta no contiene JSON')
    return json.loads(match.group(0))
