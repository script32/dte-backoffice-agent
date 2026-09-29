"""Línea de comandos: dte-agent procesar | pendientes | revisar | correo | api"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import cargar_config
from .domain.models import Decision, clp
from .service import Resultado, ServicioBackoffice

ICONOS = {
    "registrado": "✅",
    "pendiente_revision": "⏸️ ",
    "rechazado": "⛔",
    "duplicado": "♻️ ",
    "error_lectura": "❌",
}


def _imprimir(r: Resultado) -> None:
    icono = ICONOS.get(r.estado, "•")
    titulo = f"{r.emisor} folio {r.folio}" if r.folio else (r.archivo or "")
    monto = f" {clp(r.monto_total)}" if r.monto_total is not None else ""
    print(f"{icono} {r.estado.upper():<20} {titulo}{monto}")
    if r.asiento_id:
        print(f"     asiento {r.asiento_id} · cuenta {r.cuenta}")
    if r.estado == "pendiente_revision":
        print(f"     thread: {r.thread_id}")
        for motivo in r.motivos_revision:
            print(f"     - {motivo}")
    if r.error:
        print(f"     {r.error}")


def _archivos(rutas: list[str]) -> list[Path]:
    salida: list[Path] = []
    for ruta in map(Path, rutas):
        salida.extend(sorted(ruta.rglob("*.xml")) if ruta.is_dir() else [ruta])
    return salida


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="dte-agent", description=__doc__)
    parser.add_argument("--config", help="Ruta a config.yaml")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("procesar", help="Procesa archivos XML o carpetas")
    p.add_argument("rutas", nargs="+")

    sub.add_parser("pendientes", help="Lista documentos esperando aprobación")

    p = sub.add_parser("revisar", help="Aprueba o rechaza un documento pendiente")
    p.add_argument("thread_id")
    accion = p.add_mutually_exclusive_group(required=True)
    accion.add_argument("--aprobar", action="store_true")
    accion.add_argument("--rechazar", action="store_true")
    p.add_argument("--cuenta", help="Código de cuenta (por defecto, la sugerida)")
    p.add_argument("--comentario")
    p.add_argument("--revisor")

    sub.add_parser("correo", help="Procesa los XML no leídos de la casilla de intercambio")

    p = sub.add_parser("api", help="Levanta la API HTTP")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    settings = cargar_config(args.config)

    if args.comando == "api":
        import uvicorn

        from .api import crear_app

        uvicorn.run(crear_app(ServicioBackoffice(settings)), host=args.host, port=args.port)
        return 0

    servicio = ServicioBackoffice(settings)

    if args.comando == "procesar":
        for archivo in _archivos(args.rutas):
            for resultado in servicio.procesar_archivo(archivo):
                _imprimir(resultado)
    elif args.comando == "pendientes":
        pendientes = servicio.revisiones_pendientes()
        if not pendientes:
            print("No hay documentos pendientes de revisión.")
        for item in pendientes:
            print(json.dumps(item, ensure_ascii=False, indent=2))
    elif args.comando == "revisar":
        try:
            decision = Decision(
                accion="aprobar" if args.aprobar else "rechazar",
                cuenta=args.cuenta,
                comentario=args.comentario,
                revisor=args.revisor,
            )
            _imprimir(servicio.resolver_revision(args.thread_id, decision))
        except (ValueError, LookupError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    elif args.comando == "correo":
        from .ingesta.correo import procesar_casilla

        for resultado in procesar_casilla(servicio):
            _imprimir(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
