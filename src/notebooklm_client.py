# -*- coding: utf-8 -*-
"""
MeetRec — NotebookLM client helpers (create/select notebooks, upload audio).
"""
import asyncio
import datetime
from pathlib import Path

from .config import (
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_YELLOW,
    MAX_SOURCES,
    MUTED_COLOR,
    NOTEBOOK_PREFIX,
    STORAGE_PATH,
)
from .state import load_state, save_state


async def _get_or_create_notebook(client, log_fn) -> str:
    from notebooklm import RPCError

    state = load_state()
    nb_id = state.get("notebook_id")

    if nb_id:
        try:
            sources = await client.sources.list(nb_id)
            count = len(sources)
            log_fn(f"Notebook activo: {count}/{MAX_SOURCES} fuentes", MUTED_COLOR)
            if count < MAX_SOURCES:
                return nb_id
            else:
                log_fn("Notebook lleno. Creando uno nuevo...", ACCENT_YELLOW)
        except (RPCError, Exception):
            log_fn("Notebook previo no encontrado. Creando uno nuevo...", ACCENT_YELLOW)

    fecha = datetime.datetime.now().strftime("%Y-%m")
    titulo = f"{NOTEBOOK_PREFIX} {fecha}"
    nb = await client.notebooks.create(titulo)
    log_fn(f"Notebook creado: '{titulo}'", ACCENT_GREEN)
    save_state({"notebook_id": nb.id, "title": titulo})
    return nb.id


async def _subir_a_notebooklm(file_path: str, log_fn, progress_callback=None):
    from notebooklm import NotebookLMClient

    log_fn("Conectando con NotebookLM...", ACCENT_YELLOW)
    if progress_callback:
        progress_callback(10)

    async with await NotebookLMClient.from_storage(
        path=str(STORAGE_PATH),
    ) as client:
        nb_id = await _get_or_create_notebook(client, log_fn)

        if progress_callback:
            progress_callback(30)

        log_fn("Subiendo audio al notebook...", ACCENT_YELLOW)
        if progress_callback:
            progress_callback(50)

        source = await client.sources.add_file(nb_id, Path(file_path))

        if progress_callback:
            progress_callback(80)

        log_fn(f"Fuente agregada: {source.title}", ACCENT_GREEN)

        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        nuevo_titulo = f"Reunión {fecha}"
        await client.sources.rename(nb_id, source.id, nuevo_titulo)
        log_fn(f"Renombrada a: '{nuevo_titulo}'", MUTED_COLOR)
        log_fn("Audio subido a NotebookLM!", ACCENT_GREEN)
        log_fn("Abrí NotebookLM para ver la transcripción.", ACCENT_BLUE)

        if progress_callback:
            progress_callback(100)


def subir_audio(file_path: str, log_fn, progress_callback=None):
    asyncio.run(_subir_a_notebooklm(file_path, log_fn, progress_callback))


def listar_notebooks_con_fuentes():
    async def _fetch():
        from notebooklm import NotebookLMClient
        async with await NotebookLMClient.from_storage(
            path=str(STORAGE_PATH),
        ) as client:
            notebooks = await client.notebooks.list()
            result = []
            for nb in notebooks:
                try:
                    sources = await client.sources.list(nb.id)
                    count = len(sources)
                except Exception:
                    count = -1
                result.append({
                    "id": nb.id,
                    "title": nb.title or "(Sin título)",
                    "source_count": count,
                })
            return result
    return asyncio.run(_fetch())
