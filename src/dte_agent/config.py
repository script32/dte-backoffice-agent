"""Configuración por empresa. Todo lo específico de un cliente vive en config.yaml."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .domain import rut


class Empresa(BaseModel):
    rut: str
    razon_social: str

    @field_validator("rut")
    @classmethod
    def _rut_valido(cls, valor: str) -> str:
        if not rut.es_valido(valor):
            raise ValueError(f"RUT de empresa inválido: {valor}")
        return rut.normalizar(valor)


class Politicas(BaseModel):
    umbral_aprobacion: int = Field(default=1_000_000, ge=0)
    confianza_minima: float = Field(default=0.8, ge=0, le=1)
    revisar_proveedor_nuevo: bool = True
    dias_antiguedad_max: int = Field(default=60, ge=1)


class ReglaCuenta(BaseModel):
    cuenta: str
    rut_emisor: str | None = None
    palabra_clave: str | None = None

    @model_validator(mode="after")
    def _un_criterio(self) -> "ReglaCuenta":
        if bool(self.rut_emisor) == bool(self.palabra_clave):
            raise ValueError("Cada regla debe tener exactamente uno: rut_emisor o palabra_clave")
        if self.rut_emisor:
            self.rut_emisor = rut.normalizar(self.rut_emisor)
        return self


class Categorizacion(BaseModel):
    plan_de_cuentas: Path
    modelo_llm: str | None = None
    reglas: list[ReglaCuenta] = Field(default_factory=list)


class Almacenamiento(BaseModel):
    directorio: Path = Path(".data")


class Settings(BaseModel):
    empresa: Empresa
    politicas: Politicas = Field(default_factory=Politicas)
    categorizacion: Categorizacion
    almacenamiento: Almacenamiento = Field(default_factory=Almacenamiento)


def cargar_config(ruta: str | Path | None = None) -> Settings:
    ruta = Path(ruta or os.environ.get("DTE_AGENT_CONFIG", "config.yaml"))
    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe {ruta}. Copia config.example.yaml a config.yaml y completa tus datos."
        )
    with ruta.open(encoding="utf-8") as fh:
        return Settings.model_validate(yaml.safe_load(fh))
