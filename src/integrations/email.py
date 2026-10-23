import os
import re
import smtplib
from email.message import EmailMessage

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def enviar_email(destinatario: str, assunto: str, corpo: str, html: str | None = None) -> dict:
    """Envia e-mail via SMTP configurado; nunca retorna sucesso sem confirmação do servidor."""
    if not EMAIL_RE.fullmatch(destinatario.strip()):
        raise ValueError("Destinatário de e-mail inválido.")

    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    usuario = os.getenv("SMTP_USERNAME", "").strip()
    senha = os.getenv("SMTP_PASSWORD", "")
    remetente = os.getenv("SMTP_FROM", usuario).strip()
    try:
        porta = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as exc:
        raise ValueError("SMTP_PORT deve ser um número inteiro.") from exc
    if not usuario or not senha or not remetente:
        raise RuntimeError("SMTP do Google não configurado. Defina SMTP_USERNAME, SMTP_PASSWORD e SMTP_FROM.")

    mensagem = EmailMessage()
    mensagem["From"] = remetente
    mensagem["To"] = destinatario.strip()
    mensagem["Subject"] = assunto
    mensagem.set_content(corpo)
    if html:
        mensagem.add_alternative(html, subtype="html")

    with smtplib.SMTP(host, porta, timeout=30) as servidor:
        servidor.starttls()
        servidor.login(usuario, senha)
        servidor.send_message(mensagem)

    return {"enviado": True, "destinatario": destinatario.strip()}