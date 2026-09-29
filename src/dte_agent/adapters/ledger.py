"""Puerto hacia el sistema contable de la empresa y un adaptador SQLite incluido.

Para conectar un ERP real (Bsale, Nubox, Defontana, SAP, etc.) basta con implementar
`LedgerPort` y pasarlo al servicio. El grafo no conoce el sistema contable.
"""

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ..domain.models import Factura


class LedgerPort(Protocol):
    def existe_documento(self, factura: Factura) -> bool: ...
    def proveedor_conocido(self, rut_emisor: str) -> bool: ...
    def ultima_cuenta_proveedor(self, rut_emisor: str) -> str | None: ...
    def registrar(self, factura: Factura, cuenta: str, metadatos: dict) -> str: ...


class DocumentoDuplicado(Exception):
    pass


class SQLiteLedger:
    """Libro de compras local. Útil para operar sin ERP o como respaldo auditable."""

    def __init__(self, ruta: Path | str):
        self._conn = sqlite3.connect(str(ruta), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS asientos (
                    id TEXT PRIMARY KEY,
                    rut_emisor TEXT NOT NULL,
                    razon_social TEXT NOT NULL,
                    tipo_dte INTEGER NOT NULL,
                    folio INTEGER NOT NULL,
                    fecha_emision TEXT NOT NULL,
                    monto_neto INTEGER NOT NULL,
                    monto_exento INTEGER NOT NULL,
                    iva INTEGER NOT NULL,
                    monto_total INTEGER NOT NULL,
                    cuenta TEXT NOT NULL,
                    aprobado_por TEXT NOT NULL,
                    comentario TEXT,
                    registrado_en TEXT NOT NULL,
                    UNIQUE (rut_emisor, tipo_dte, folio)
                )
                """
            )

    def _uno(self, sql: str, params: tuple) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def existe_documento(self, factura: Factura) -> bool:
        return (
            self._uno(
                "SELECT 1 FROM asientos WHERE rut_emisor=? AND tipo_dte=? AND folio=?",
                (factura.rut_emisor, factura.tipo_dte, factura.folio),
            )
            is not None
        )

    def proveedor_conocido(self, rut_emisor: str) -> bool:
        return self._uno("SELECT 1 FROM asientos WHERE rut_emisor=?", (rut_emisor,)) is not None

    def ultima_cuenta_proveedor(self, rut_emisor: str) -> str | None:
        fila = self._uno(
            "SELECT cuenta FROM asientos WHERE rut_emisor=? ORDER BY registrado_en DESC LIMIT 1",
            (rut_emisor,),
        )
        return fila["cuenta"] if fila else None

    def registrar(self, factura: Factura, cuenta: str, metadatos: dict) -> str:
        asiento_id = f"AS-{uuid.uuid4().hex[:10].upper()}"
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT INTO asientos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        asiento_id,
                        factura.rut_emisor,
                        factura.razon_social_emisor,
                        factura.tipo_dte,
                        factura.folio,
                        factura.fecha_emision.isoformat(),
                        factura.monto_neto,
                        factura.monto_exento,
                        factura.iva,
                        factura.monto_total,
                        cuenta,
                        metadatos.get("aprobado_por", "automatico"),
                        metadatos.get("comentario"),
                        datetime.now(UTC).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DocumentoDuplicado(str(exc)) from exc
        return asiento_id

    def asientos(self) -> list[dict]:
        with self._lock:
            filas = self._conn.execute("SELECT * FROM asientos ORDER BY registrado_en").fetchall()
        return [dict(f) for f in filas]
