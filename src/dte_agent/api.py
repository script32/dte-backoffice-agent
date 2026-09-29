"""API HTTP. Pensada para integrarse con n8n, un ERP o un portal interno."""

import os

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from . import __version__
from .config import cargar_config
from .domain.models import Decision
from .service import Resultado, RevisionNoEncontrada, ServicioBackoffice

TAMANO_MAXIMO = 5 * 1024 * 1024


def _verificar_api_key(x_api_key: str | None = Header(default=None)) -> None:
    esperada = os.environ.get("DTE_AGENT_API_KEY")
    if esperada and x_api_key != esperada:
        raise HTTPException(status_code=401, detail="API key inválida")


def crear_app(servicio: ServicioBackoffice | None = None) -> FastAPI:
    svc = servicio or ServicioBackoffice(cargar_config())
    app = FastAPI(title="DTE Backoffice Agent", version=__version__)
    protegido = [Depends(_verificar_api_key)]

    @app.get("/salud")
    def salud() -> dict:
        return {"estado": "ok", "version": __version__}

    @app.post("/documentos", response_model=list[Resultado], dependencies=protegido)
    async def subir_documento(archivo: UploadFile) -> list[Resultado]:
        contenido = await archivo.read(TAMANO_MAXIMO + 1)
        if len(contenido) > TAMANO_MAXIMO:
            raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx. 5 MB)")
        return await run_in_threadpool(
            svc.procesar_contenido, contenido, archivo.filename or "sin_nombre.xml"
        )

    @app.get("/revisiones", dependencies=protegido)
    def revisiones() -> list[dict]:
        return svc.revisiones_pendientes()

    @app.post("/revisiones/{thread_id}", response_model=Resultado, dependencies=protegido)
    def resolver(thread_id: str, decision: Decision) -> Resultado:
        try:
            return svc.resolver_revision(thread_id, decision)
        except RevisionNoEncontrada as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app
