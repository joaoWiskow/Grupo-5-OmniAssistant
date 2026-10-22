from src.core.contracts import RegistroConversa
from src.integrations.email import enviar_email


def validar_registro(registro: RegistroConversa, exigir_email: bool = True) -> None:
    if exigir_email and not registro.destinatario_email:
        raise ValueError("Informe e confirme um destinatário de e-mail.")
    if registro.risco == "vermelho":
        raise ValueError("Operação bloqueada: a análise possui risco vermelho.")


def finalizar_registro(
    registro: RegistroConversa,
    enviar: bool = True,
    email_sender=enviar_email,
) -> dict:
    validar_registro(registro, exigir_email=enviar)
    resultado = {"id_operacao": registro.id_operacao, "email": None}
    if enviar:
        assunto = f"OmniAssistant - análise {registro.numero_nota or registro.id_operacao}"
        corpo = registro.resumo
        if registro.pendencias:
            corpo += "\n\nPendências:\n- " + "\n- ".join(registro.pendencias)
        resultado["email"] = email_sender(registro.destinatario_email or "", assunto, corpo)
    return resultado
