import json
from pathlib import Path

import pytest

from src.core import colab_nlp
from src.core.contracts import EntradaUsuario
from src.core.ingestion import despachar_ingestao
from src.core.agent import executar_agente
from src.tools.local import consultar_item


def _colab_configurado() -> bool:
    try:
        colab_nlp._url_base()
        return True
    except RuntimeError:
        return False


@pytest.mark.skipif(
    not _colab_configurado(),
    reason="chat roda no Colab: defina COLAB_LLM_URL para o teste ponta a ponta",
)
def testar_pipeline_completo():
    print("Executando teste integrado de percepcao -> acao...")

    # 1. Simula as entradas do usuario
    entrada_txt = EntradaUsuario(
        tipo="texto", texto_comando="Identifique os itens e calcule o total"
    )
    evidencias = [despachar_ingestao(entrada_txt)]

    # Se houver imagem ou audio na pasta data/, adiciona ao lote
    if Path("data/amostra.png").is_file():
        evidencias.append(
            despachar_ingestao(
                EntradaUsuario(tipo="imagem", caminho_arquivo=Path("data/amostra.png"))
            )
        )
    if Path("data/comando.wav").is_file():
        evidencias.append(
            despachar_ingestao(
                EntradaUsuario(tipo="audio", caminho_arquivo=Path("data/comando.wav"))
            )
        )

    resultado = executar_agente(entrada_txt.texto_comando, evidencias)

    assert len(resultado["resposta"]) > 10, "A resposta do modelo veio vazia!"
    print("Resposta gerada:")
    print(resultado["resposta"])
    print("\nFerramentas disparadas:", len(resultado["rastro_ferramentas"]))
    print("Tempo de execucao:", resultado["tempo_total_ms"], "ms")


def testar_guardrail_sql():
    print("\nTestando resistencia contra SQL Injection...")
    codigo_malicioso = "A101'; DROP TABLE itens; --"
    resultado = consultar_item(codigo_malicioso)

    assert "erro" in resultado or resultado.get("encontrado") is False
    print(
        "PASS: Tentativa de SQL Injection barrada com sucesso pelo guardrail de validacao."
    )


if __name__ == "__main__":
    testar_pipeline_completo()
    testar_guardrail_sql()
