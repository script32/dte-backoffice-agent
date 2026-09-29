from datetime import date
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from dte_agent.config import Settings
from dte_agent.domain.models import Cuenta, Factura, SugerenciaCuenta
from dte_agent.service import ServicioBackoffice

RAIZ = Path(__file__).resolve().parent.parent
MUESTRAS = RAIZ / "data" / "samples"
HOY = date(2026, 9, 29)


class CategorizadorFijo:
    """Reemplaza al LLM en tests: determinista y sin red."""

    def __init__(self, codigo: str | None = "5104", confianza: float = 0.9):
        self.codigo, self.confianza, self.llamadas = codigo, confianza, 0

    def sugerir(self, factura: Factura, cuentas: list[Cuenta]) -> SugerenciaCuenta:
        self.llamadas += 1
        return SugerenciaCuenta(
            codigo=self.codigo, confianza=self.confianza, fuente="test", justificacion="fijo"
        )


def crear_settings(tmp_path: Path, **politicas) -> Settings:
    return Settings.model_validate(
        {
            "empresa": {"rut": "76.543.210-3", "razon_social": "Comercial Los Lagos SpA"},
            "politicas": {"revisar_proveedor_nuevo": False, **politicas},
            "categorizacion": {"plan_de_cuentas": RAIZ / "data/plan_de_cuentas.example.csv"},
            "almacenamiento": {"directorio": tmp_path},
        }
    )


@pytest.fixture
def servicio_factory(tmp_path):
    def _crear(categorizador=None, **politicas) -> ServicioBackoffice:
        return ServicioBackoffice(
            crear_settings(tmp_path, **politicas),
            categorizador=categorizador or CategorizadorFijo(),
            checkpointer=InMemorySaver(),
            hoy=lambda: HOY,
        )

    return _crear
