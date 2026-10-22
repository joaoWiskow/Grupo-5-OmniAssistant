import pytest

from src.core.contracts import RegistroConversa
from src.core.finalizacao import finalizar_registro


def registro(**kwargs):
    valores = {
        "id_operacao": "op-1",
        "destinatario_email": "financeiro@example.com",
        "resumo": "Resumo da análise.",
    }
    valores.update(kwargs)
    return RegistroConversa(
        **valores,
    )


def test_finalizacao_executa_email():
    chamadas = []
    def email_sender(destinatario, assunto, corpo):
        chamadas.append(("email", destinatario))
        return {"enviado": True}

    resultado = finalizar_registro(
        registro(),
        email_sender=email_sender,
    )

    assert resultado["email"] == {"enviado": True}
    assert chamadas == [("email", "financeiro@example.com")]


def test_finalizacao_bloqueia_risco_vermelho():
    with pytest.raises(ValueError, match="risco vermelho"):
        finalizar_registro(registro(risco="vermelho"))


def test_finalizacao_exige_email_quando_enviando():
    with pytest.raises(ValueError, match="destinatário"):
        finalizar_registro(registro(destinatario_email=None))
