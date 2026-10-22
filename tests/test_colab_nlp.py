"""Testes do cliente do LLM no Colab. Nao usam rede."""

from src.core import colab_nlp

URL_TESTE = "https://teste.trycloudflare.com"
MENSAGENS = [{"role": "user", "content": "O que e juro composto?"}]


class RespostaFalsa:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def test_envia_mensagens_e_ferramentas(monkeypatch):
    capturado = {}
    ferramentas = [{"type": "function", "function": {"name": "consultar_item"}}]

    def post_falso(url, json, timeout):
        capturado.update(url=url, json=json, timeout=timeout)
        return RespostaFalsa(
            {"texto": "Juro composto incide sobre o capital corrigido."}
        )

    monkeypatch.setenv("COLAB_LLM_URL", URL_TESTE + "/")
    monkeypatch.setattr(colab_nlp.requests, "post", post_falso)

    saida = colab_nlp.conversar(MENSAGENS, ferramentas, max_new_tokens=128)

    assert "juro composto" in saida["texto"].lower()
    assert capturado["url"] == URL_TESTE + "/chat"
    assert capturado["json"] == {
        "mensagens": MENSAGENS,
        "ferramentas": ferramentas,
        "max_new_tokens": 128,
    }


def test_status_mostra_modelo_e_dispositivo(monkeypatch):
    capturado = {}

    def get_falso(url, timeout):
        capturado.update(url=url, timeout=timeout)
        return RespostaFalsa(
            {
                "ok": True,
                "modelo": "rwayz/tributario-llama-8b-v2",
                "dispositivo": "cuda",
            }
        )

    monkeypatch.setenv("COLAB_LLM_URL", URL_TESTE)
    monkeypatch.setattr(colab_nlp.requests, "get", get_falso)

    saida = colab_nlp.status_colab()

    assert saida["modelo"] == "rwayz/tributario-llama-8b-v2"
    assert capturado["url"] == URL_TESTE + "/health"


def test_colab_fora_do_ar_devolve_erro(monkeypatch):
    def post_falso(*args, **kwargs):
        raise colab_nlp.requests.ConnectionError("down")

    monkeypatch.setenv("COLAB_LLM_URL", URL_TESTE)
    monkeypatch.setattr(colab_nlp.requests, "post", post_falso)

    saida = colab_nlp.conversar(MENSAGENS)

    assert "erro" in saida
    assert "Colab indisponivel" in saida["erro"]


def test_sem_url_no_ambiente_devolve_erro(monkeypatch):
    monkeypatch.delenv("COLAB_LLM_URL", raising=False)
    monkeypatch.setattr(colab_nlp, "load_dotenv", lambda: None)

    saida = colab_nlp.conversar(MENSAGENS)

    assert "COLAB_LLM_URL ausente" in saida["erro"]
