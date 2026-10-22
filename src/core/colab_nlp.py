"""Cliente do modelo tributario que roda no Colab (notebooks/OmniFinance_Tributario.ipynb)."""

import os

import requests
from dotenv import load_dotenv

TIMEOUT_S = 180  # 8B em 4-bit na T4 gera poucos tokens por segundo


def _url_base() -> str:
    load_dotenv()
    url = os.environ.get("COLAB_LLM_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError(
            "COLAB_LLM_URL ausente. Rode notebooks/OmniFinance_Tributario.ipynb "
            "e copie a URL impressa para o .env."
        )
    return url


def _cabecalhos_auth(token: str | None = None) -> dict[str, str]:
    """Token explicito > COLAB_AUTH_TOKEN > contexto ativo, com rastreio do usuario."""
    headers: dict[str, str] = {}
    chave = (token or os.environ.get("COLAB_AUTH_TOKEN", "")).strip()

    ctx = None
    try:
        from src.core.auth import obter_contexto_ativo

        ctx = obter_contexto_ativo()
    except Exception:
        pass

    if not chave and ctx:
        chave = ctx.token.token
    if chave:
        headers["Authorization"] = f"Bearer {chave}"
    if ctx:
        headers["X-Omni-User-ID"] = ctx.usuario.id
        headers["X-Omni-Role"] = ctx.usuario.papel.value
    return headers


def status_colab(timeout: float = 5.0) -> dict:
    """Consulta /health para provar qual modelo esta carregado no Colab."""
    try:
        url = _url_base()
    except RuntimeError as exc:
        return {"erro": str(exc)}

    try:
        resposta = requests.get(f"{url}/health", timeout=timeout)
        resposta.raise_for_status()
        return resposta.json()
    except Exception as exc:
        return {"erro": f"Colab indisponivel ({type(exc).__name__})."}


def conversar(
    mensagens: list[dict],
    ferramentas: list[dict] | None = None,
    max_new_tokens: int = 512,
    token: str | None = None,
) -> dict:
    """Envia o historico no formato do chat template do Llama e devolve a resposta.

    Retorna {"texto", "tool_call", "modelo", "dispositivo"} ou {"erro": ...}.
    Falha de rede vira {"erro": ...} para o agente encerrar a resposta sem quebrar.
    """
    try:
        url = _url_base()
    except RuntimeError as exc:
        return {"erro": str(exc)}

    headers = _cabecalhos_auth(token)

    kwargs = {"timeout": TIMEOUT_S}
    if headers:
        kwargs["headers"] = headers

    try:
        resposta = requests.post(
            f"{url}/chat",
            json={
                "mensagens": mensagens,
                "ferramentas": ferramentas,
                "max_new_tokens": max_new_tokens,
            },
            **kwargs,
        )
        resposta.raise_for_status()
        return resposta.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        corpo = exc.response.text[:400] if exc.response is not None else ""
        return {"erro": f"Colab respondeu HTTP {status}: {corpo}"}
    except Exception as exc:  # fronteira de rede: nunca derruba o chat
        return {
            "erro": f"Colab indisponivel ({type(exc).__name__}). "
            "Rode o notebook OmniFinance_Tributario e atualize COLAB_LLM_URL."
        }
