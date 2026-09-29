"""Pruebas de punta a punta del grafo: aprobación automática, interrupt y reanudación."""

import pytest
from conftest import MUESTRAS, CategorizadorFijo

from dte_agent.domain.models import Decision
from dte_agent.service import RevisionNoEncontrada


def procesar(servicio, nombre):
    [resultado] = servicio.procesar_archivo(MUESTRAS / nombre)
    return resultado


def test_factura_correcta_se_registra_sola(servicio_factory):
    r = procesar(servicio_factory(), "factura_nube_austral_hosting.xml")
    assert r.estado == "registrado"
    assert r.asiento_id and r.cuenta == "5104"


def test_reprocesar_es_idempotente(servicio_factory):
    categorizador = CategorizadorFijo()
    servicio = servicio_factory(categorizador)
    primero = procesar(servicio, "factura_nube_austral_hosting.xml")
    segundo = procesar(servicio, "factura_nube_austral_hosting.xml")
    assert primero.asiento_id == segundo.asiento_id
    assert categorizador.llamadas == 1


def test_monto_alto_pausa_y_se_aprueba_con_otra_cuenta(servicio_factory):
    servicio = servicio_factory()
    r = procesar(servicio, "factura_tecnosur_notebooks.xml")
    assert r.estado == "pendiente_revision"
    assert any("umbral" in m for m in r.motivos_revision)

    [pendiente] = servicio.revisiones_pendientes()
    assert pendiente["documento"]["folio"] == 88341

    final = servicio.resolver_revision(
        r.thread_id, Decision(accion="aprobar", cuenta="1301", revisor="contador")
    )
    assert final.estado == "registrado" and final.cuenta == "1301"
    assert servicio.revisiones_pendientes() == []
    asiento = servicio.dependencias.ledger.asientos()[0]
    assert asiento["aprobado_por"] == "contador"


def test_iva_erroneo_se_rechaza(servicio_factory):
    servicio = servicio_factory()
    r = procesar(servicio, "factura_imprenta_iva_erroneo.xml")
    assert r.estado == "pendiente_revision"
    assert any("IVA" in m for m in r.motivos_revision)

    final = servicio.resolver_revision(
        r.thread_id, Decision(accion="rechazar", comentario="Solicitar refacturación")
    )
    assert final.estado == "rechazado"
    assert servicio.dependencias.ledger.asientos() == []


def test_baja_confianza_requiere_revision(servicio_factory):
    servicio = servicio_factory(CategorizadorFijo(confianza=0.4))
    r = procesar(servicio, "factura_nube_austral_hosting.xml")
    assert r.estado == "pendiente_revision"
    assert any("Confianza" in m for m in r.motivos_revision)


def test_proveedor_nuevo_requiere_revision_y_luego_no(servicio_factory):
    servicio = servicio_factory(revisar_proveedor_nuevo=True)
    r = procesar(servicio, "factura_nube_austral_hosting.xml")
    assert any("Proveedor nuevo" in m for m in r.motivos_revision)
    servicio.resolver_revision(r.thread_id, Decision(accion="aprobar"))
    assert servicio.dependencias.ledger.proveedor_conocido("77111222-6")


def test_aprobar_sin_cuenta_valida_falla(servicio_factory):
    servicio = servicio_factory(CategorizadorFijo(codigo=None, confianza=0))
    r = procesar(servicio, "factura_nube_austral_hosting.xml")
    with pytest.raises(ValueError):
        servicio.resolver_revision(r.thread_id, Decision(accion="aprobar"))
    with pytest.raises(ValueError):
        servicio.resolver_revision(r.thread_id, Decision(accion="aprobar", cuenta="9999"))


def test_resolver_sin_pendiente(servicio_factory):
    with pytest.raises(RevisionNoEncontrada):
        servicio_factory().resolver_revision("dte-inexistente", Decision(accion="aprobar"))


def test_archivo_no_dte(servicio_factory):
    [r] = servicio_factory().procesar_contenido(b"<hola/>", "x.xml")
    assert r.estado == "error_lectura"
