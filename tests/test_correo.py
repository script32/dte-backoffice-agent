from email.message import EmailMessage

from dte_agent.ingesta.correo import adjuntos_xml


def test_extrae_solo_adjuntos_xml():
    msg = EmailMessage()
    msg.set_content("Adjuntamos DTE")
    msg.add_attachment(b"<EnvioDTE/>", maintype="application", subtype="xml", filename="dte.xml")
    msg.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename="dte.pdf")
    assert adjuntos_xml(msg) == [("dte.xml", b"<EnvioDTE/>")]
