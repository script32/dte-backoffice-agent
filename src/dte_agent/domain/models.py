"""Modelos de dominio."""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TIPOS_DTE: dict[int, str] = {
    33: "Factura electrónica",
    34: "Factura no afecta o exenta electrónica",
    56: "Nota de débito electrónica",
    61: "Nota de crédito electrónica",
}


def clp(monto: int | float) -> str:
    return "$" + f"{int(monto):,}".replace(",", ".")


class Severidad(StrEnum):
    ERROR = "error"
    ADVERTENCIA = "advertencia"


class LineaDetalle(BaseModel):
    numero: int
    nombre: str
    cantidad: float | None = None
    precio_unitario: float | None = None
    monto: int
    # IndExe del SII: 1 exento, 2 no facturable, 3 garantía por envases, etc. None = afecto
    indicador_exencion: int | None = None


class DescuentoRecargo(BaseModel):
    """Descuento o recargo global (<DscRcgGlobal>): modifica la base, no una línea."""

    numero: int
    tipo_movimiento: Literal["D", "R"]
    glosa: str | None = None
    tipo_valor: Literal["%", "$"]
    valor: float
    # IndExeDR: None = afecta ítems afectos, 1 = exentos, 2 = no facturables
    indicador_exencion: int | None = None


class Factura(BaseModel):
    tipo_dte: int
    folio: int
    fecha_emision: date
    fecha_vencimiento: date | None = None
    rut_emisor: str
    razon_social_emisor: str
    giro_emisor: str | None = None
    rut_receptor: str
    razon_social_receptor: str
    monto_neto: int = 0
    monto_exento: int = 0
    tasa_iva: float | None = None
    iva: int = 0
    otros_impuestos: int = 0
    credito_constructoras: int = 0  # <CredEC>: se resta del total
    garantia_envases: int = 0  # <GrntDep>: se suma al total
    monto_total: int
    lineas: list[LineaDetalle] = Field(default_factory=list)
    descuentos_recargos: list[DescuentoRecargo] = Field(default_factory=list)

    @property
    def tipo_nombre(self) -> str:
        return TIPOS_DTE.get(self.tipo_dte, f"DTE tipo {self.tipo_dte}")

    def resumen(self) -> dict:
        return {
            "tipo": self.tipo_nombre,
            "folio": self.folio,
            "fecha_emision": self.fecha_emision.isoformat(),
            "emisor": f"{self.razon_social_emisor} ({self.rut_emisor})",
            "monto_neto": self.monto_neto,
            "iva": self.iva,
            "monto_total": self.monto_total,
            "detalle": [linea.nombre for linea in self.lineas[:10]],
        }


class Hallazgo(BaseModel):
    codigo: str
    severidad: Severidad
    mensaje: str


class Cuenta(BaseModel):
    codigo: str
    nombre: str
    descripcion: str = ""


class SugerenciaCuenta(BaseModel):
    codigo: str | None
    nombre: str | None = None
    confianza: float = Field(ge=0, le=1)
    fuente: str
    justificacion: str


class Decision(BaseModel):
    accion: Literal["aprobar", "rechazar"]
    cuenta: str | None = None
    comentario: str | None = None
    revisor: str | None = None

    @model_validator(mode="after")
    def _rechazo_con_motivo(self) -> "Decision":
        if self.accion == "rechazar" and not self.comentario:
            raise ValueError("Un rechazo debe incluir un comentario con el motivo")
        return self
