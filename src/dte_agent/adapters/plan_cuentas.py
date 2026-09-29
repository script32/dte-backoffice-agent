import csv
from pathlib import Path

from ..domain.models import Cuenta


def cargar_plan_de_cuentas(ruta: Path) -> list[Cuenta]:
    """Lee un CSV con columnas: codigo, nombre, descripcion."""
    with Path(ruta).open(encoding="utf-8-sig", newline="") as fh:
        cuentas = [
            Cuenta(
                codigo=fila["codigo"].strip(),
                nombre=fila["nombre"].strip(),
                descripcion=(fila.get("descripcion") or "").strip(),
            )
            for fila in csv.DictReader(fh)
            if fila.get("codigo")
        ]
    if not cuentas:
        raise ValueError(f"El plan de cuentas {ruta} está vacío")
    return cuentas
