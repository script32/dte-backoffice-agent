"""Lectura de XML DTE del SII (DTE suelto, EnvioDTE o SetDTE con varios documentos).

La lectura es determinista: un XML estructurado no necesita un LLM.
Se usa defusedxml porque los XML llegan de terceros (protección contra XXE y 'billion laughs').
"""

from datetime import date
from xml.etree.ElementTree import Element, tostring

from defusedxml.ElementTree import fromstring
from pydantic import ValidationError

from .models import DescuentoRecargo, Factura, LineaDetalle
from .rut import normalizar


class ErrorDTE(ValueError):
    """El contenido no es un DTE legible."""


def _sin_namespaces(raiz: Element) -> Element:
    for el in raiz.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return raiz


def _parse(contenido: bytes | str) -> Element:
    try:
        return _sin_namespaces(fromstring(contenido))
    except Exception as exc:  # defusedxml y expat lanzan varios tipos
        raise ErrorDTE(f"XML inválido: {exc}") from exc


def _txt(el: Element, ruta: str, requerido: bool = True) -> str | None:
    nodo = el.find(ruta)
    valor = nodo.text.strip() if nodo is not None and nodo.text else None
    if requerido and not valor:
        raise ErrorDTE(f"Falta el campo obligatorio <{ruta}>")
    return valor


def _int(el: Element, ruta: str, default: int = 0) -> int:
    valor = _txt(el, ruta, requerido=False)
    return int(round(float(valor))) if valor else default


def _float(el: Element, ruta: str) -> float | None:
    valor = _txt(el, ruta, requerido=False)
    return float(valor) if valor else None


def _int_opcional(el: Element, ruta: str) -> int | None:
    valor = _txt(el, ruta, requerido=False)
    return int(valor) if valor else None


def _seccion(padre: Element, nombre: str) -> Element:
    nodo = padre.find(nombre)
    if nodo is None:
        raise ErrorDTE(f"Falta la sección <{nombre}>")
    return nodo


def separar_documentos(contenido: bytes) -> list[str]:
    """Devuelve cada <Documento> del archivo como XML independiente."""
    raiz = _parse(contenido)
    documentos = [raiz] if raiz.tag == "Documento" else list(raiz.iter("Documento"))
    if not documentos:
        raise ErrorDTE("El archivo no contiene documentos DTE (<Documento>)")
    return [tostring(doc, encoding="unicode") for doc in documentos]


def parsear_documento(xml: str) -> Factura:
    doc = _parse(xml)
    enc = _seccion(doc, "Encabezado")
    iddoc = _seccion(enc, "IdDoc")
    emisor = _seccion(enc, "Emisor")
    receptor = _seccion(enc, "Receptor")
    totales = _seccion(enc, "Totales")

    try:
        vencimiento = _txt(iddoc, "FchVenc", requerido=False)
        return Factura(
            tipo_dte=_int(iddoc, "TipoDTE"),
            folio=_int(iddoc, "Folio"),
            fecha_emision=date.fromisoformat(_txt(iddoc, "FchEmis")),
            fecha_vencimiento=date.fromisoformat(vencimiento) if vencimiento else None,
            rut_emisor=normalizar(_txt(emisor, "RUTEmisor")),
            razon_social_emisor=_txt(emisor, "RznSoc"),
            giro_emisor=_txt(emisor, "GiroEmis", requerido=False),
            rut_receptor=normalizar(_txt(receptor, "RUTRecep")),
            razon_social_receptor=_txt(receptor, "RznSocRecep"),
            monto_neto=_int(totales, "MntNeto"),
            monto_exento=_int(totales, "MntExe"),
            tasa_iva=_float(totales, "TasaIVA"),
            iva=_int(totales, "IVA"),
            otros_impuestos=sum(_int(i, "MontoImp") for i in totales.findall("ImptoReten")),
            credito_constructoras=_int(totales, "CredEC"),
            garantia_envases=_int(totales, "GrntDep"),
            monto_total=_int(totales, "MntTotal"),
            lineas=[
                LineaDetalle(
                    numero=_int(d, "NroLinDet"),
                    nombre=_txt(d, "NmbItem"),
                    cantidad=_float(d, "QtyItem"),
                    precio_unitario=_float(d, "PrcItem"),
                    monto=_int(d, "MontoItem"),
                    indicador_exencion=_int_opcional(d, "IndExe"),
                )
                for d in doc.findall("Detalle")
            ],
            descuentos_recargos=[
                DescuentoRecargo(
                    numero=_int(dr, "NroLinDR"),
                    tipo_movimiento=_txt(dr, "TpoMov"),
                    glosa=_txt(dr, "GlosaDR", requerido=False),
                    tipo_valor=_txt(dr, "TpoValor"),
                    valor=_float(dr, "ValorDR") or 0,
                    indicador_exencion=_int_opcional(dr, "IndExeDR"),
                )
                for dr in doc.findall("DscRcgGlobal")
            ],
        )
    except ErrorDTE:
        raise
    except (ValidationError, ValueError) as exc:
        raise ErrorDTE(f"Datos del DTE inválidos: {exc}") from exc
