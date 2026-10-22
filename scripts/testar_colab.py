"""Prova ponta a ponta que o LLM do Colab esta no ar e ligado ao agente.

Uso: .venv/bin/python scripts/testar_colab.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.agent import executar_agente
from src.core.auth import contexto_servico
from src.core.colab_nlp import conversar, status_colab

PERGUNTA = "Explique em uma frase o que e juro composto."
falhas = []


def checar(nome: str, resultado: dict, campo: str | None = None) -> None:
    ok = "erro" not in resultado
    if ok and campo:
        ok = bool(resultado.get(campo)) and "Nao consegui falar" not in str(
            resultado.get(campo)
        )
    print(
        f"{'OK   ' if ok else 'FALHA'} {nome}: {json.dumps(resultado, ensure_ascii=False)}"
    )
    if not ok:
        falhas.append(nome)


checar("1. tunel + modelo (/health)", status_colab())
checar(
    "2. resposta direta (POST /chat)",
    conversar([{"role": "user", "content": PERGUNTA}], max_new_tokens=64),
    campo="texto",
)
checar(
    "3. agente completo",
    executar_agente(PERGUNTA, [], contexto=contexto_servico()),
)

sys.exit(1 if falhas else 0)
