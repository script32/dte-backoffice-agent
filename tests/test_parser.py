import pytest
from conftest import MUESTRAS

from dte_agent.domain.dte_parser import ErrorDTE, parsear_documento, separar_documentos


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
