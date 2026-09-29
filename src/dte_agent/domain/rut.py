"""Utilidades para el RUT chileno (validación con módulo 11)."""

import re


def limpiar(rut: str) -> str:
    return re.sub(r"[^0-9kK]", "", rut or "").upper()


def calcular_dv(cuerpo: str) -> str:
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


def es_valido(rut: str) -> bool:
    r = limpiar(rut)
    if len(r) < 2 or not r[:-1].isdigit():
        return False
    return calcular_dv(r[:-1]) == r[-1]


def normalizar(rut: str) -> str:
    """Devuelve el RUT en formato canónico '76543210-3'."""
    r = limpiar(rut)
    if len(r) < 2 or not r[:-1].isdigit():
        return r
    return f"{int(r[:-1])}-{r[-1]}"
