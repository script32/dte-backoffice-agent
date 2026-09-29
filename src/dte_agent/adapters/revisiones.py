"""Índice de documentos a la espera de aprobación humana."""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path


class ColaRevision:
    def __init__(self, ruta: Path | str):
        self._conn = sqlite3.connect(str(ruta), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS revisiones (
                    thread_id TEXT PRIMARY KEY,
                    archivo TEXT,
                    solicitud TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'pendiente',
                    creado_en TEXT NOT NULL,
                    resuelto_en TEXT
                )
                """
            )

    def agregar(self, thread_id: str, archivo: str | None, solicitud: dict) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO revisiones (thread_id, archivo, solicitud, creado_en) "
                "VALUES (?,?,?,?)",
                (thread_id, archivo, json.dumps(solicitud), datetime.now(UTC).isoformat()),
            )

    def pendientes(self) -> list[dict]:
        with self._lock:
            filas = self._conn.execute(
                "SELECT * FROM revisiones WHERE estado='pendiente' ORDER BY creado_en"
            ).fetchall()
        return [
            {
                "thread_id": f["thread_id"],
                "archivo": f["archivo"],
                "creado_en": f["creado_en"],
                **json.loads(f["solicitud"]),
            }
            for f in filas
        ]

    def cerrar(self, thread_id: str, estado: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE revisiones SET estado=?, resuelto_en=? WHERE thread_id=?",
                (estado, datetime.now(UTC).isoformat(), thread_id),
            )
