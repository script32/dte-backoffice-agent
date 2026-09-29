# Conectar tu sistema contable

El grafo no conoce el ERP: habla con un puerto (`LedgerPort`). Para integrar Bsale, Nubox,
Defontana, SAP u otro, implementa estas cuatro operaciones:

```python
from dte_agent.adapters.ledger import DocumentoDuplicado
from dte_agent.domain.models import Factura


class MiERPLedger:
    def __init__(self, cliente_api):
        self.api = cliente_api

    def existe_documento(self, factura: Factura) -> bool:
        # Buscar por RUT emisor + tipo DTE + folio en las compras del ERP
        ...

    def proveedor_conocido(self, rut_emisor: str) -> bool:
        # ¿Existe el proveedor en el maestro del ERP?
        ...

    def ultima_cuenta_proveedor(self, rut_emisor: str) -> str | None:
        # Cuenta contable usada en la última compra a este proveedor (alimenta el historial)
        ...

    def registrar(self, factura: Factura, cuenta: str, metadatos: dict) -> str:
        # Crear el documento de compra / asiento. Devolver su ID en el ERP.
        # Si el ERP responde "ya existe", lanzar DocumentoDuplicado.
        ...
```

Luego pásalo al servicio:

```python
from dte_agent.config import cargar_config
from dte_agent.service import ServicioBackoffice

servicio = ServicioBackoffice(cargar_config(), ledger=MiERPLedger(cliente))
```

Reglas para que la integración sea segura:

- `registrar` es la única operación con efectos: debe ser idempotente o lanzar
  `DocumentoDuplicado` si el documento ya existe.
- Las tres primeras operaciones son de solo lectura y se pueden llamar varias veces
  (LangGraph re-ejecuta nodos al reanudar una revisión humana).
