from datetime import date
from pathlib import Path

import pytest
from conftest import MUESTRAS

from dte_agent.domain.dte_parser import ErrorDTE, parsear_documento, separar_documentos
from dte_agent.domain.validation import validar


def test_lee_envio_dte_con_namespace_y_latin1():
    docs = separar_documentos((MUESTRAS / "factura_nube_austral_hosting.xml").read_bytes())
    assert len(docs) == 1
    f = parsear_documento(docs[0])
    assert (f.tipo_dte, f.folio) == (33, 1520)
    assert f.rut_emisor == "77111222-6"
    assert f.monto_neto == 85000 and f.iva == 16150 and f.monto_total == 101150
    assert f.lineas[1].nombre == "Renovación dominio .cl"


def test_separa_varios_documentos():
    xml = (MUESTRAS / "factura_nube_austral_hosting.xml").read_text(encoding="iso-8859-1")
    inicio, fin = xml.index("<DTE "), xml.index("</DTE>") + len("</DTE>")
    doble = xml[:fin] + xml[inicio:fin] + xml[fin:]
    assert len(separar_documentos(doble.encode("iso-8859-1"))) == 2


def test_xml_invalido():
    with pytest.raises(ErrorDTE):
        separar_documentos(b"<no-es-xml")


def test_rechaza_entidades_externas():
    malicioso = b"""<?xml version="1.0"?>
<!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><Documento>&x;</Documento>"""
    with pytest.raises(ErrorDTE):
        separar_documentos(malicioso)


def test_documento_incompleto():
    with pytest.raises(ErrorDTE, match="Encabezado"):
        parsear_documento("<Documento><Detalle/></Documento>")


# Ejemplo oficial publicado por el SII (sii.cl, "Formato XML de Documentos Electrónicos")
EJEMPLO_SII = Path(__file__).parent / "fixtures" / "sii" / "F60T33-ejemplo.xml"


def test_lee_ejemplo_oficial_del_sii():
    docs = separar_documentos(EJEMPLO_SII.read_bytes())
    assert len(docs) == 1
    f = parsear_documento(docs[0])
    assert (f.tipo_dte, f.folio, f.rut_emisor) == (33, 60, "97975000-5")
    assert (f.monto_neto, f.iva, f.monto_total) == (100000, 19000, 119000)
    assert [linea.monto for linea in f.lineas] == [90000, 5000, 5000]
    assert validar(f, "77777777-7", date(2003, 10, 20)) == []


def documento(totales: str, detalle: str = "", extra: str = "") -> str:
    """DTE mínimo para probar secciones puntuales del formato."""
    return f"""<Documento><Encabezado>
      <IdDoc><TipoDTE>33</TipoDTE><Folio>7</Folio><FchEmis>2026-09-20</FchEmis></IdDoc>
      <Emisor><RUTEmisor>77111222-6</RUTEmisor><RznSoc>Proveedor SpA</RznSoc></Emisor>
      <Receptor><RUTRecep>76543210-3</RUTRecep><RznSocRecep>Empresa</RznSocRecep></Receptor>
      <Totales>{totales}</Totales></Encabezado>{detalle}{extra}</Documento>"""


def test_lee_credito_constructoras_y_garantia_envases():
    f = parsear_documento(
        documento(
            "<MntNeto>100</MntNeto><IVA>19</IVA><CredEC>12</CredEC><GrntDep>5</GrntDep>"
            "<MntTotal>112</MntTotal>"
        )
    )
    assert (f.credito_constructoras, f.garantia_envases) == (12, 5)


def test_lee_indicador_de_exencion_del_detalle():
    detalle = (
        "<Detalle><NroLinDet>1</NroLinDet><NmbItem>Bebida</NmbItem><MontoItem>100</MontoItem>"
        "</Detalle><Detalle><NroLinDet>2</NroLinDet><IndExe>3</IndExe><NmbItem>Envase</NmbItem>"
        "<MontoItem>5</MontoItem></Detalle>"
    )
    f = parsear_documento(documento("<MntTotal>0</MntTotal>", detalle))
    assert [linea.indicador_exencion for linea in f.lineas] == [None, 3]


def test_lee_descuentos_y_recargos_globales():
    extra = (
        "<DscRcgGlobal><NroLinDR>1</NroLinDR><TpoMov>D</TpoMov><GlosaDR>Pago contado</GlosaDR>"
        "<TpoValor>%</TpoValor><ValorDR>10.5</ValorDR></DscRcgGlobal>"
        "<DscRcgGlobal><NroLinDR>2</NroLinDR><TpoMov>R</TpoMov><TpoValor>$</TpoValor>"
        "<ValorDR>500</ValorDR><IndExeDR>1</IndExeDR></DscRcgGlobal>"
    )
    f = parsear_documento(documento("<MntTotal>0</MntTotal>", extra=extra))
    d, r = f.descuentos_recargos
    assert (d.tipo_movimiento, d.tipo_valor, d.valor, d.glosa) == ("D", "%", 10.5, "Pago contado")
    assert (r.tipo_movimiento, r.tipo_valor, r.valor, r.indicador_exencion) == ("R", "$", 500, 1)


def test_descuento_global_con_tipo_invalido():
    extra = (
        "<DscRcgGlobal><NroLinDR>1</NroLinDR><TpoMov>X</TpoMov><TpoValor>%</TpoValor>"
        "<ValorDR>10</ValorDR></DscRcgGlobal>"
    )
    with pytest.raises(ErrorDTE):
        parsear_documento(documento("<MntTotal>0</MntTotal>", extra=extra))
