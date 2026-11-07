"""
Cliente del LLM (Strata / API compatible OpenAI), independiente del dominio.
"""

import base64
import json
import re
import urllib.error
import urllib.request


def call_llm(cfg, messages, max_tokens=None, temperature=0.8):
    """Llamada a /v1/chat/completions (Strata/llama.cpp). Devuelve el content del asistente."""
    if max_tokens is None:
        max_tokens = cfg.get('max_tokens', 2500)
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
    # El timeout es configurable: una IA potente puede tardar varios minutos.
    with urllib.request.urlopen(req, timeout=cfg.get('timeout', 240)) as resp:
        data = json.load(resp)
    choice = (data.get('choices') or [{}])[0]
    content = (choice.get('message') or {}).get('content')
    if not content:
        raise ValueError("El modelo no devolvió contenido (¿max_tokens agotado por el razonamiento?)")
    return content


def call_llm_vision(cfg, prompt, image_bytes, mime='image/jpeg', max_tokens=700):
    """Igual que call_llm pero con una imagen adjunta (bloque vision de Strata, en CPU)."""
    body = json.dumps({
        'model': cfg['vision_model'],
        'max_tokens': max_tokens,
        'temperature': 0.1,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {
                'url': f'data:{mime};base64,' + base64.b64encode(image_bytes).decode()
            }},
        ]}],
    }).encode('utf-8')
    req = urllib.request.Request(
        cfg['url'].rstrip('/') + '/v1/chat/completions',
        data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f"Bearer {cfg['api_key']}"},
    )
    with urllib.request.urlopen(req, timeout=cfg.get('timeout', 240)) as resp:
        data = json.load(resp)
    choice = (data.get('choices') or [{}])[0]
    content = (choice.get('message') or {}).get('content')
    if not content:
        raise ValueError('El modelo de visión no devolvió contenido')
    return content


def parse_llm_json(text):
    """Extrae el JSON de la respuesta, tolerando cercas ```json ... ``` o texto alrededor."""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError('La respuesta no contiene JSON')
    return json.loads(match.group(0))
