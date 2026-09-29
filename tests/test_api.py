from conftest import MUESTRAS
from fastapi.testclient import TestClient

from dte_agent.api import crear_app


def test_flujo_por_api(servicio_factory, monkeypatch):
    monkeypatch.setenv("DTE_AGENT_API_KEY", "secreto")
    cliente = TestClient(crear_app(servicio_factory()))
    headers = {"X-API-Key": "secreto"}

    assert cliente.get("/revisiones").status_code == 401

    archivo = (MUESTRAS / "factura_tecnosur_notebooks.xml").read_bytes()
    resp = cliente.post("/documentos", files={"archivo": ("f.xml", archivo)}, headers=headers)
    assert resp.status_code == 200
    thread_id = resp.json()[0]["thread_id"]

    assert len(cliente.get("/revisiones", headers=headers).json()) == 1

    resp = cliente.post(
        f"/revisiones/{thread_id}", json={"accion": "aprobar", "cuenta": "1301"}, headers=headers
    )
    assert resp.json()["estado"] == "registrado"
    assert (
        cliente.post(
            f"/revisiones/{thread_id}", json={"accion": "aprobar"}, headers=headers
        ).status_code
        == 404
    )
