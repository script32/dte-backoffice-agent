from typing import TypedDict


class EstadoDocumento(TypedDict, total=False):
    """Estado de un documento a lo largo del grafo. Solo tipos serializables (JSON)."""

    archivo: str
    xml: str
    factura: dict
    hallazgos: list[dict]
    sugerencia: dict
    motivos_revision: list[str]
    decision: dict
    estado: str  # error_lectura | duplicado | registrado | rechazado
    asiento_id: str
    error: str
