"""Fachada de aplicación: la usan la API, la CLI y la ingesta por correo."""

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from .adapters.ledger import LedgerPort, SQLiteLedger
from .adapters.plan_cuentas import cargar_plan_de_cuentas
from .adapters.revisiones import ColaRevision
from .categorization import (
    Categorizador,
    CategorizadorEnCadena,
    CategorizadorHistorial,
    CategorizadorLLM,
    CategorizadorReglas,
)
from .config import Settings
from .domain.dte_parser import ErrorDTE, separar_documentos
from .domain.models import Decision
from .graph.builder import Dependencias, construir_grafo


class Resultado(BaseModel):
    thread_id: str | None
    archivo: str | None
    estado: str
    tipo_dte: int | None = None
    folio: int | None = None
    emisor: str | None = None
    monto_total: int | None = None
    cuenta: str | None = None
    asiento_id: str | None = None
    motivos_revision: list[str] = []
    error: str | None = None


class RevisionNoEncontrada(LookupError):
    pass


def crear_dependencias(
    settings: Settings,
    ledger: LedgerPort | None = None,
    categorizador: Categorizador | None = None,
    hoy: Callable[[], date] = date.today,
) -> Dependencias:
    directorio = settings.almacenamiento.directorio
    directorio.mkdir(parents=True, exist_ok=True)
    ledger = ledger or SQLiteLedger(directorio / "libro_compras.db")
    cuentas = cargar_plan_de_cuentas(settings.categorizacion.plan_de_cuentas)
    if categorizador is None:
        cadena: list[Categorizador] = [
            CategorizadorHistorial(ledger),
            CategorizadorReglas(settings.categorizacion.reglas),
        ]
        if settings.categorizacion.modelo_llm:
            cadena.append(CategorizadorLLM(settings.categorizacion.modelo_llm))
        categorizador = CategorizadorEnCadena(cadena)
    return Dependencias(settings, ledger, categorizador, cuentas, hoy)


class ServicioBackoffice:
    def __init__(
        self,
        settings: Settings,
        *,
        ledger: LedgerPort | None = None,
        categorizador: Categorizador | None = None,
        checkpointer=None,
        hoy: Callable[[], date] = date.today,
    ):
        self.dependencias = crear_dependencias(settings, ledger, categorizador, hoy)
        directorio = settings.almacenamiento.directorio
        if checkpointer is None:
            conn = sqlite3.connect(str(directorio / "checkpoints.db"), check_same_thread=False)
            checkpointer = SqliteSaver(conn)
        self.cola = ColaRevision(directorio / "revisiones.db")
        self.grafo = construir_grafo(self.dependencias, checkpointer=checkpointer)

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def procesar_archivo(self, ruta: Path) -> list[Resultado]:
        return self.procesar_contenido(Path(ruta).read_bytes(), Path(ruta).name)

    def procesar_contenido(self, contenido: bytes, origen: str) -> list[Resultado]:
        try:
            documentos = separar_documentos(contenido)
        except ErrorDTE as exc:
            return [
                Resultado(thread_id=None, archivo=origen, estado="error_lectura", error=str(exc))
            ]
        return [self._procesar_documento(xml, origen) for xml in documentos]

    def _procesar_documento(self, xml: str, origen: str) -> Resultado:
        # thread_id derivado del contenido: reprocesar el mismo XML es idempotente
        thread_id = "dte-" + hashlib.sha256(xml.encode()).hexdigest()[:16]
        config = self._config(thread_id)
        if not self.grafo.get_state(config).values:
            self.grafo.invoke({"archivo": origen, "xml": xml}, config)
        return self._resultado(thread_id)

    def _resultado(self, thread_id: str) -> Resultado:
        snapshot = self.grafo.get_state(self._config(thread_id))
        valores = snapshot.values
        factura = valores.get("factura") or {}
        pendiente = bool(snapshot.next)
        if pendiente:
            solicitud = next((i.value for tarea in snapshot.tasks for i in tarea.interrupts), {})
            self.cola.agregar(thread_id, valores.get("archivo"), solicitud)
        decision = valores.get("decision") or {}
        sugerencia = valores.get("sugerencia") or {}
        return Resultado(
            thread_id=thread_id,
            archivo=valores.get("archivo"),
            estado="pendiente_revision" if pendiente else valores.get("estado", "desconocido"),
            tipo_dte=factura.get("tipo_dte"),
            folio=factura.get("folio"),
            emisor=factura.get("razon_social_emisor"),
            monto_total=factura.get("monto_total"),
            cuenta=decision.get("cuenta") or sugerencia.get("codigo"),
            asiento_id=valores.get("asiento_id"),
            motivos_revision=valores.get("motivos_revision", []),
            error=valores.get("error"),
        )

    def revisiones_pendientes(self) -> list[dict]:
        return self.cola.pendientes()

    def resolver_revision(self, thread_id: str, decision: Decision) -> Resultado:
        config = self._config(thread_id)
        snapshot = self.grafo.get_state(config)
        if not snapshot.next:
            raise RevisionNoEncontrada(f"No hay una revisión pendiente para {thread_id}")
        if decision.accion == "aprobar":
            cuenta = decision.cuenta or snapshot.values["sugerencia"].get("codigo")
            codigos = {c.codigo for c in self.dependencias.cuentas}
            if cuenta not in codigos:
                raise ValueError("Para aprobar debes indicar una cuenta válida del plan de cuentas")
            decision = decision.model_copy(update={"cuenta": cuenta})
        self.grafo.invoke(Command(resume=decision.model_dump(mode="json")), config)
        resultado = self._resultado(thread_id)
        self.cola.cerrar(thread_id, resultado.estado)
        return resultado
