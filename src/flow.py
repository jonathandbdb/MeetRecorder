# -*- coding: utf-8 -*-
"""
MeetRec — Flow: pipeline configurable post-extracción.

Permite enviar la respuesta de extracción a un endpoint HTTP
y opcionalmente procesar la respuesta (ej. agregarla como fuente
a NotebookLM).
"""
import json
import logging

import requests

from .config import FLOW_FILE

logger = logging.getLogger(__name__)

# Estructura por defecto del flujo
_DEFAULT_FLOW = {
    "enabled": False,
    "endpoint": {
        "url": "",
        "method": "POST",
        "headers": {},
        "timeout": 30,
    },
    "expect_response": False,
    "on_response": {
        "add_to_notebooklm": False,
    },
}


def load_flow_config() -> dict:
    """Carga la configuración del flujo desde disco."""
    if FLOW_FILE.exists():
        try:
            data = json.loads(FLOW_FILE.read_text(encoding="utf-8"))
            # Merge con defaults para garantizar todas las claves
            merged = json.loads(json.dumps(_DEFAULT_FLOW))
            merged.update(data)
            merged["endpoint"] = {**_DEFAULT_FLOW["endpoint"], **data.get("endpoint", {})}
            merged["on_response"] = {**_DEFAULT_FLOW["on_response"], **data.get("on_response", {})}
            return merged
        except (json.JSONDecodeError, ValueError):
            pass
    return json.loads(json.dumps(_DEFAULT_FLOW))


def save_flow_config(config: dict):
    """Persiste la configuración del flujo en disco."""
    FLOW_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def execute_flow(extraction_result: str, fmt: str, log_fn, nb_id: str | None = None):
    """
    Ejecuta el flujo post-extracción.

    Args:
        extraction_result: Texto o JSON devuelto por chat.ask.
        fmt: Formato de la respuesta ("text" o "json").
        log_fn: Función para loguear en la GUI.
        nb_id: ID del notebook actual (para agregar fuentes).
    """
    from .config import (
        ACCENT_BLUE,
        ACCENT_GREEN,
        ACCENT_LAVENDER,
        ACCENT_RED,
        ACCENT_YELLOW,
    )

    config = load_flow_config()
    if not config["enabled"]:
        return

    url = config["endpoint"].get("url", "").strip()
    if not url:
        log_fn("Flow: No hay URL configurada, omitiendo.", ACCENT_YELLOW)
        return

    method = config["endpoint"].get("method", "POST").upper()
    headers = dict(config["endpoint"].get("headers", {}))
    timeout = config["endpoint"].get("timeout", 30)

    # Construir el payload
    if fmt == "json":
        try:
            payload = json.loads(extraction_result)
        except (json.JSONDecodeError, ValueError):
            payload = {"response": extraction_result, "metadata": {}}
    else:
        payload = {"response": extraction_result, "metadata": {}}

    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    log_fn(f"Flow: Enviando a {url}...", ACCENT_BLUE)

    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        log_fn(f"Flow: Respuesta HTTP {resp.status_code}", ACCENT_BLUE)

        if not config["expect_response"]:
            log_fn("Flow: Completado (sin esperar respuesta).", ACCENT_GREEN)
            return

        # Procesar la respuesta
        resp_text = resp.text.strip()
        if not resp_text:
            log_fn("Flow: Respuesta vacía, nada que procesar.", ACCENT_YELLOW)
            return

        log_fn("─── Respuesta del endpoint ───", ACCENT_LAVENDER)
        for line in resp_text[:500].split("\n"):
            log_fn(f"  {line}", ACCENT_LAVENDER)
        if len(resp_text) > 500:
            log_fn("  ... (truncado)", ACCENT_LAVENDER)
        log_fn("──────────────────────────────", ACCENT_LAVENDER)

        # Agregar respuesta como fuente a NotebookLM
        if config["on_response"].get("add_to_notebooklm") and nb_id:
            _add_response_as_source(resp_text, nb_id, log_fn)

    except requests.exceptions.Timeout:
        log_fn(f"Flow: Timeout después de {timeout}s.", ACCENT_RED)
    except requests.exceptions.ConnectionError:
        log_fn(f"Flow: No se pudo conectar a {url}.", ACCENT_RED)
    except Exception as e:
        log_fn(f"Flow: Error — {e}", ACCENT_RED)


def _add_response_as_source(response_text: str, nb_id: str, log_fn):
    """Agrega la respuesta del endpoint como fuente de texto en NotebookLM."""
    import asyncio
    import datetime

    from .config import ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW, STORAGE_PATH

    log_fn("Flow: Agregando respuesta como fuente en NotebookLM...", ACCENT_YELLOW)

    async def _add():
        from notebooklm import NotebookLMClient

        async with await NotebookLMClient.from_storage(
            path=str(STORAGE_PATH),
        ) as client:
            source = await client.sources.add_text(nb_id, response_text)
            fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            titulo = f"Respuesta Flow {fecha}"
            await client.sources.rename(nb_id, source.id, titulo)
            return titulo

    try:
        titulo = asyncio.run(_add())
        log_fn(f"Flow: Fuente agregada: '{titulo}'", ACCENT_GREEN)
    except Exception as e:
        log_fn(f"Flow: Error al agregar fuente — {e}", ACCENT_RED)
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
