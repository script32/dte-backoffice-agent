from datetime import date

from conftest import HOY

from dte_agent.domain.models import DescuentoRecargo, Factura, LineaDetalle
from dte_agent.domain.validation import validar

EMPRESA = "76543210-3"


def factura(**cambios) -> Factura:
    base = dict(
        tipo_dte=33,
        folio=1,
        fecha_emision=date(2026, 9, 20),
        rut_emisor="77111222-6",
        razon_social_emisor="Proveedor SpA",
        rut_receptor=EMPRESA,
        razon_social_receptor="Empresa",
        monto_neto=100000,
        tasa_iva=19,
        iva=19000,
        monto_total=119000,
        lineas=[LineaDetalle(numero=1, nombre="Servicio", monto=100000)],
    )
    return Factura(**{**base, **cambios})


def codigos(f: Factura) -> set[str]:
    return {h.codigo for h in validar(f, EMPRESA, HOY)}


def test_factura_correcta_sin_hallazgos():
    assert codigos(factura()) == set()


def test_iva_incorrecto():
    assert "iva_incorrecto" in codigos(factura(iva=18000, monto_total=118000))


def test_total_incorrecto():
    assert "total_incorrecto" in codigos(factura(monto_total=120000))


def test_receptor_distinto():
    assert "receptor_distinto" in codigos(factura(rut_receptor="11111111-1"))


def test_rut_emisor_invalido():
    assert "rut_emisor_invalido" in codigos(factura(rut_emisor="77111222-5"))


def test_fechas():
    assert "fecha_futura" in codigos(factura(fecha_emision=date(2026, 10, 30)))
    assert "documento_antiguo" in codigos(factura(fecha_emision=date(2026, 1, 1)))


def test_detalle_que_no_cuadra_es_advertencia():
    hallazgos = validar(
        factura(lineas=[LineaDetalle(numero=1, nombre="x", monto=90000)]), EMPRESA, HOY
    )
    assert [h.severidad for h in hallazgos] == ["advertencia"]


def test_credito_constructoras_se_resta_del_total():
    # Formato DTE SII, campo 124: el crédito 65% (IVA * 0,65) es el único que resta
    assert codigos(factura(credito_constructoras=12350, monto_total=106650)) == set()


def test_garantia_envases_se_suma_al_total_y_no_al_detalle():
    lineas = [
        LineaDetalle(numero=1, nombre="Cerveza", monto=100000),
        LineaDetalle(numero=2, nombre="Envases", monto=5000, indicador_exencion=3),
    ]
    f = factura(garantia_envases=5000, monto_total=124000, lineas=lineas)
    assert codigos(f) == set()


def test_descuento_global_porcentual_cuadra_el_detalle():
    f = factura(
        monto_neto=90000,
        iva=17100,
        monto_total=107100,
        descuentos_recargos=[
            DescuentoRecargo(numero=1, tipo_movimiento="D", tipo_valor="%", valor=10)
        ],
    )
    assert codigos(f) == set()


def test_recargo_global_en_pesos_sobre_exentos():
    lineas = [
        LineaDetalle(numero=1, nombre="Servicio", monto=100000),
        LineaDetalle(numero=2, nombre="Flete exento", monto=20000, indicador_exencion=1),
    ]
    recargo = DescuentoRecargo(
        numero=1, tipo_movimiento="R", tipo_valor="$", valor=5000, indicador_exencion=1
    )
    f = factura(
        monto_exento=25000, monto_total=144000, lineas=lineas, descuentos_recargos=[recargo]
    )
    assert codigos(f) == set()


def test_descuento_global_mal_aplicado_sigue_advirtiendo():
    f = factura(
        descuentos_recargos=[
            DescuentoRecargo(numero=1, tipo_movimiento="D", tipo_valor="$", valor=3000)
        ],
    )
    assert codigos(f) == {"detalle_no_cuadra"}
