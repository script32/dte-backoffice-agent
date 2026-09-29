"""Grafo LangGraph que procesa un documento DTE de punta a punta.

leer -> validar -> categorizar -> evaluar_politicas -> [revision_humana] -> registrar | rechazar

Ningún nodo anterior a `revision_humana` tiene efectos secundarios: al reanudar un
interrupt, LangGraph re-ejecuta el nodo desde el inicio, así que las escrituras
solo ocurren en `registrar`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ..adapters.ledger import DocumentoDuplicado, LedgerPort
from ..categorization import Categorizador
from ..config import Settings
from ..domain.dte_parser import ErrorDTE, parsear_documento
from ..domain.models import Cuenta, Decision, Factura, SugerenciaCuenta, clp
from ..domain.validation import validar
from .state import EstadoDocumento


@dataclass
class Dependencias:
    settings: Settings
    ledger: LedgerPort
    categorizador: Categorizador
    cuentas: list[Cuenta]
    hoy: Callable[[], date] = field(default=date.today)


def construir_grafo(dep: Dependencias, checkpointer=None):
    politicas = dep.settings.politicas

    def leer(state: EstadoDocumento) -> dict:
        try:
            factura = parsear_documento(state["xml"])
        except ErrorDTE as exc:
            return {"estado": "error_lectura", "error": str(exc)}
        return {"factura": factura.model_dump(mode="json")}

    def validar_documento(state: EstadoDocumento) -> dict:
        factura = Factura.model_validate(state["factura"])
        if dep.ledger.existe_documento(factura):
            return {"estado": "duplicado"}
        hallazgos = validar(
            factura,
            rut_empresa=dep.settings.empresa.rut,
            hoy=dep.hoy(),
            dias_antiguedad_max=politicas.dias_antiguedad_max,
        )
        return {"hallazgos": [h.model_dump(mode="json") for h in hallazgos]}

    def categorizar(state: EstadoDocumento) -> dict:
        factura = Factura.model_validate(state["factura"])
        sugerencia = dep.categorizador.sugerir(factura, dep.cuentas)
        return {"sugerencia": sugerencia.model_dump(mode="json")}

    def evaluar_politicas(state: EstadoDocumento) -> dict:
        factura = Factura.model_validate(state["factura"])
        sugerencia = SugerenciaCuenta.model_validate(state["sugerencia"])
        motivos = [f"[{h['severidad'].upper()}] {h['mensaje']}" for h in state.get("hallazgos", [])]
        if factura.monto_total > politicas.umbral_aprobacion:
            motivos.append(
                f"Monto {clp(factura.monto_total)} supera el umbral de aprobación automática "
                f"({clp(politicas.umbral_aprobacion)})"
            )
        if not sugerencia.codigo:
            motivos.append(f"No se pudo determinar la cuenta contable: {sugerencia.justificacion}")
        elif sugerencia.confianza < politicas.confianza_minima:
            motivos.append(
                f"Confianza de categorización baja ({sugerencia.confianza:.0%}; "
                f"mínimo {politicas.confianza_minima:.0%})"
            )
        if politicas.revisar_proveedor_nuevo and not dep.ledger.proveedor_conocido(
            factura.rut_emisor
        ):
            motivos.append(f"Proveedor nuevo: {factura.razon_social_emisor} ({factura.rut_emisor})")
        return {"motivos_revision": motivos}

    def revision_humana(state: EstadoDocumento) -> dict:
        factura = Factura.model_validate(state["factura"])
        respuesta = interrupt(
            {
                "tipo": "aprobacion_documento",
                "documento": factura.resumen(),
                "motivos": state["motivos_revision"],
                "sugerencia": state["sugerencia"],
                "cuentas_disponibles": [f"{c.codigo} - {c.nombre}" for c in dep.cuentas],
            }
        )
        decision = Decision.model_validate(respuesta)
        return {"decision": decision.model_dump(mode="json")}

    def registrar(state: EstadoDocumento) -> dict:
        factura = Factura.model_validate(state["factura"])
        decision = state.get("decision") or {}
        cuenta = decision.get("cuenta") or state["sugerencia"]["codigo"]
        metadatos = {
            "aprobado_por": decision.get("revisor") or ("humano" if decision else "automatico"),
            "comentario": decision.get("comentario"),
        }
        try:
            asiento_id = dep.ledger.registrar(factura, cuenta, metadatos)
        except DocumentoDuplicado:
            return {"estado": "duplicado"}
        return {"estado": "registrado", "asiento_id": asiento_id}

    def rechazar(state: EstadoDocumento) -> dict:
        return {"estado": "rechazado"}

    g = StateGraph(EstadoDocumento)
    g.add_node("leer", leer)
    g.add_node("validar", validar_documento)
    g.add_node("categorizar", categorizar)
    g.add_node("evaluar_politicas", evaluar_politicas)
    g.add_node("revision_humana", revision_humana)
    g.add_node("registrar", registrar)
    g.add_node("rechazar", rechazar)

    g.add_edge(START, "leer")
    g.add_conditional_edges(
        "leer", lambda s: END if s.get("estado") else "validar", ["validar", END]
    )
    g.add_conditional_edges(
        "validar", lambda s: END if s.get("estado") else "categorizar", ["categorizar", END]
    )
    g.add_edge("categorizar", "evaluar_politicas")
    g.add_conditional_edges(
        "evaluar_politicas",
        lambda s: "revision_humana" if s["motivos_revision"] else "registrar",
        ["revision_humana", "registrar"],
    )
    g.add_conditional_edges(
        "revision_humana",
        lambda s: "registrar" if s["decision"]["accion"] == "aprobar" else "rechazar",
        ["registrar", "rechazar"],
    )
    g.add_edge("registrar", END)
    g.add_edge("rechazar", END)
    return g.compile(checkpointer=checkpointer)
