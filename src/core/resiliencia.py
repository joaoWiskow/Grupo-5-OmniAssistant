"""Resiliência para chamadas à API: limite de concorrência e retry com espera progressiva."""
import logging
import threading
import time
from functools import wraps

LIMITE_CONCORRENCIA = 8
ESPERAS = (1, 2, 4)              # segundos entre tentativas
STATUS_REPETIVEIS = {429, 503}

# O módulo é importado uma vez por processo, então o semáforo é
# compartilhado por todas as sessões do Streamlit e por todas as threads.
_semaforo = threading.BoundedSemaphore(LIMITE_CONCORRENCIA)
log = logging.getLogger(__name__)


def _status_http(exc: Exception) -> int | None:
    """Extrai o status HTTP de exceções de SDKs comuns (google-genai, openai, anthropic, requests, httpx)."""
    for attr in ("status_code", "code", "http_status", "status"):
        valor = getattr(exc, attr, None)
        if isinstance(valor, int):
            return valor
    valor = getattr(getattr(exc, "response", None), "status_code", None)
    return valor if isinstance(valor, int) else None


def com_resiliencia(func=None, *, esperas=ESPERAS):
    """Limita a concorrência e repete em 429/503 com espera progressiva.

    Uso:
        @com_resiliencia
        def f(...): ...

        @com_resiliencia(esperas=(1,))
        def g(...): ...
    """
    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            for tentativa in range(len(esperas) + 1):
                try:
                    # O semáforo só segura a vaga durante a chamada,
                    # não durante a espera do retry.
                    with _semaforo:
                        return f(*args, **kwargs)
                except Exception as exc:
                    status = _status_http(exc)
                    if status not in STATUS_REPETIVEIS or tentativa == len(esperas):
                        raise
                    espera = esperas[tentativa]
                    log.warning(
                        "%s: HTTP %s, tentativa %d/%d, nova tentativa em %ss",
                        f.__name__, status, tentativa + 1, len(esperas) + 1, espera,
                    )
                    time.sleep(espera)
        return wrapper
    return decorador(func) if func else decorador


@com_resiliencia
def gerar_conteudo(cliente, **kwargs):
    """cliente.models.generate_content com semáforo e retry em 429/503."""
    return cliente.models.generate_content(**kwargs)