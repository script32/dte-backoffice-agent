import pytest

from dte_agent.domain import rut


@pytest.mark.parametrize("valor", ["76.543.210-3", "765432103", "78222333-k", "11.111.111-1"])
def test_ruts_validos(valor):
    assert rut.es_valido(valor)


@pytest.mark.parametrize("valor", ["76.543.210-4", "", "abc", "1"])
def test_ruts_invalidos(valor):
    assert not rut.es_valido(valor)


def test_normalizar():
    assert rut.normalizar("076.543.210-3") == "76543210-3"
    assert rut.normalizar("78222333k") == "78222333-K"
