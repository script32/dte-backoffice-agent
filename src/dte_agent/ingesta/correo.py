"""Ingesta desde la casilla de intercambio DTE (IMAP).

Los proveedores envían el XML de sus DTE por correo a la casilla de intercambio
registrada en el SII. Este módulo lee los correos no leídos, extrae los adjuntos XML
y los procesa. Los correos se marcan como leídos solo si se procesaron sin error.
"""

import email
import imaplib
import logging
import os
from email.message import Message

from ..service import Resultado, ServicioBackoffice

log = logging.getLogger(__name__)


def adjuntos_xml(mensaje: Message) -> list[tuple[str, bytes]]:
    adjuntos = []
    for parte in mensaje.walk():
        nombre = parte.get_filename() or ""
        es_xml = nombre.lower().endswith(".xml") or parte.get_content_type() in (
            "application/xml",
            "text/xml",
        )
        if es_xml and parte.get_content_disposition() in ("attachment", "inline"):
            contenido = parte.get_payload(decode=True)
            if contenido:
                adjuntos.append((nombre or "adjunto.xml", contenido))
    return adjuntos


def procesar_casilla(servicio: ServicioBackoffice) -> list[Resultado]:
    host = os.environ["IMAP_HOST"]
    usuario = os.environ["IMAP_USER"]
    clave = os.environ["IMAP_PASSWORD"]
    carpeta = os.environ.get("IMAP_FOLDER", "INBOX")

    resultados: list[Resultado] = []
    with imaplib.IMAP4_SSL(host) as imap:
        imap.login(usuario, clave)
        imap.select(carpeta)
        _, datos = imap.search(None, "UNSEEN")
        for num in datos[0].split():
            _, partes = imap.fetch(num, "(BODY.PEEK[])")
            mensaje = email.message_from_bytes(partes[0][1])
            try:
                for nombre, contenido in adjuntos_xml(mensaje):
                    resultados.extend(servicio.procesar_contenido(contenido, nombre))
            except Exception:
                log.exception("Error procesando correo %s; queda como no leído", num)
                continue
            imap.store(num, "+FLAGS", "\\Seen")
    return resultados
