"""Reglas tributarias y de negocio. Deterministas y testeables, sin LLM."""

from datetime import date

from . import rut
from .models import TIPOS_DTE, Factura, Hallazgo, Severidad, clp

TOLERANCIA = 1  # diferencias de redondeo


def _redondear(valor: float) -> int:
    return int(valor + 0.5)


def validar(
    factura: Factura, rut_empresa: str, hoy: date, dias_antiguedad_max: int = 60
) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []

    def error(codigo: str, mensaje: str) -> None:
        hallazgos.append(Hallazgo(codigo=codigo, severidad=Severidad.ERROR, mensaje=mensaje))

    def advertencia(codigo: str, mensaje: str) -> None:
        hallazgos.append(Hallazgo(codigo=codigo, severidad=Severidad.ADVERTENCIA, mensaje=mensaje))

    f = factura
    if f.tipo_dte not in TIPOS_DTE:
        error("tipo_no_soportado", f"Tipo de DTE {f.tipo_dte} no soportado en compras")

    if not rut.es_valido(f.rut_emisor):
        error("rut_emisor_invalido", f"El RUT del emisor {f.rut_emisor} no es válido")

    if rut.normalizar(f.rut_receptor) != rut.normalizar(rut_empresa):
        error(
            "receptor_distinto",
            f"El documento está emitido a {f.rut_receptor} ({f.razon_social_receptor}), "
            f"no a la empresa ({rut.normalizar(rut_empresa)})",
        )

    if f.monto_neto > 0:
        tasa = f.tasa_iva if f.tasa_iva is not None else 19.0
        esperado = _redondear(f.monto_neto * tasa / 100)
        if abs(esperado - f.iva) > TOLERANCIA:
            error(
                "iva_incorrecto",
                f"IVA declarado {clp(f.iva)} no corresponde al {tasa:g}% de {clp(f.monto_neto)} "
                f"(esperado {clp(esperado)})",
            )

    total_calculado = f.monto_neto + f.monto_exento + f.iva + f.otros_impuestos
    if abs(total_calculado - f.monto_total) > TOLERANCIA:
        error(
            "total_incorrecto",
            f"Monto total {clp(f.monto_total)} no cuadra con neto + exento + impuestos "
            f"({clp(total_calculado)})",
        )

    if f.lineas:
        suma_lineas = sum(linea.monto for linea in f.lineas)
        base = f.monto_neto + f.monto_exento
        if abs(suma_lineas - base) > TOLERANCIA:
            advertencia(
                "detalle_no_cuadra",
                f"La suma del detalle ({clp(suma_lineas)}) difiere de neto + exento "
                f"({clp(base)}); puede deberse a descuentos o recargos globales",
            )

    if f.fecha_emision > hoy:
        error("fecha_futura", f"Fecha de emisión futura: {f.fecha_emision.isoformat()}")
    elif (hoy - f.fecha_emision).days > dias_antiguedad_max:
        advertencia(
            "documento_antiguo",
            f"Documento emitido hace {(hoy - f.fecha_emision).days} días "
            f"(máximo esperado: {dias_antiguedad_max})",
        )

    return hallazgos
