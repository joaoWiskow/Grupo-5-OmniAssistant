
import json
from time import perf_counter
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field
from google.genai import types

from src.core.config import MODEL, criar_cliente_gemini
from src.core.contracts import EvidenciaMultimodal
from src.tools.local import consultar_item, calcular_total, validar_codigo


class CodigoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    codigo: str = Field(description="Codigo do produto (ex: N101)")


class TotalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    quantidade: float = Field(
        ge=0.1, le=1000.0, description="Quantidade de itens"
    )
    preco_unitario: float = Field(
        ge=0.01, le=100000.0, description="Preco unitario em BRL"
    )


REGISTRO_TOOLS: dict[
    str, tuple[Callable[..., dict], type[BaseModel], str]
] = {
    "consultar_item": (
        consultar_item,
        CodigoArgs,
        "Consulta nome, preco e setor de um item por codigo no catalogo SQLite."
    ),
    "calcular_total": (
        calcular_total,
        TotalArgs,
        "Calcula o valor total em BRL a partir da quantidade e do preco unitario."
    ),
    "validar_codigo": (
        validar_codigo,
        CodigoArgs,
        "Valida o formato de um codigo de produto."
    ),
}


FERRAMENTAS_GEMINI = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name=nome,
            description=desc,
            parameters_json_schema=schema.model_json_schema(),
        )
        for nome, (_, schema, desc) in REGISTRO_TOOLS.items()
    ]
)


def despachar_tool(chamada: types.FunctionCall) -> dict:
    nome = chamada.name

    if nome not in REGISTRO_TOOLS:
        return {"erro": f"Ferramenta '{nome}' nao autorizada."}

    funcao, schema, _ = REGISTRO_TOOLS[nome]

    try:
        args = schema.model_validate(chamada.args or {}).model_dump()
        return funcao(**args)
    except Exception as e:
        return {
            "erro": f"Argumentos invalidos para {nome}: {type(e).__name__}"
        }


def executar_agente(
    pergunta: str,
    evidencias: list[EvidenciaMultimodal],
) -> dict:
    """Executa o agente multimodal com chamadas explicitas de ferramentas."""
    inicio = perf_counter()
    trace_ferramentas = []
    tokens_usados = 0
    resposta_final = "Limite de chamadas atingido."
    cliente = criar_cliente_gemini()

    payload_usuario = json.dumps(
        {
            "pergunta": pergunta,
            "evidencias_multimodais": [
                e.model_dump() for e in evidencias
            ],
        },
        ensure_ascii=False,
    )

    historico = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=payload_usuario)],
        )
    ]

    system_instruction = (
        "Voce e o especialista em triagem financeira e faturamento "
        "do OmniAssistant, responsavel por analisar prints de notas fiscais "
        "e comandos de voz de gestores. "
        "Extraia apenas fatos, numeros, valores, datas, CNPJs e rotulos "
        "presentes nas evidencias fornecidas. "
        "Identifique numero da nota, emitente, destinatario, vencimento, "
        "itens, quantidades, valores unitarios, impostos e total quando "
        "estiverem disponiveis. Interprete os comandos de voz preservando "
        "a intencao original. "
        "Nao invente informacoes ausentes. Sinalize dados ilegiveis, "
        "ambiguos ou divergentes e solicite confirmacao quando necessario. "
        "Use consultar_item para consultar o catalogo e validar_codigo "
        "para validar codigos. Use calcular_total somente quando a quantidade "
        "e o preco unitario estiverem confirmados. "
        "Se precisar de um preco cadastrado, consulte primeiro o item. "
        "Nao confunda dados do catalogo com dados extraidos de uma nota fiscal. "
        "Nao afirme que realizou pagamentos, aprovou faturas ou alterou registros. "
        "Responda em portugues brasileiro e informe a origem das informacoes."
    )

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.0,
        tools=[FERRAMENTAS_GEMINI],
        automatic_function_calling=(
            types.AutomaticFunctionCallingConfig(disable=True)
        ),
    )

    for turno in range(4):
        resposta = cliente.models.generate_content(
            model=MODEL,
            contents=historico,
            config=config,
        )

        if (
            resposta.usage_metadata
            and resposta.usage_metadata.total_token_count
        ):
            tokens_usados += resposta.usage_metadata.total_token_count

        candidato = (
            resposta.candidates[0].content
            if resposta.candidates
            else None
        )

        if not candidato:
            resposta_final = "Sem resposta do modelo."
            break

        historico.append(candidato)

        chamadas = [
            parte.function_call
            for parte in (candidato.parts or [])
            if parte.function_call is not None
        ]

        if not chamadas:
            resposta_final = resposta.text or "Resposta conclusiva emitida."
            break

        partes_resposta = []

        for chamada in chamadas:
            t0 = perf_counter()
            resultado = despachar_tool(chamada)
            duracao_ms = round((perf_counter() - t0) * 1000, 1)

            trace_ferramentas.append({
                "ferramenta": chamada.name,
                "argumentos": chamada.args,
                "resultado": resultado,
                "duracao_ms": duracao_ms,
            })

            # Devolve o resultado vinculado a chamada original.
            partes_resposta.append(
                types.Part.from_function_response(
                    name=chamada.name,
                    response={"resultado": resultado},
                )
            )

        # O SDK Gemini espera a resposta da ferramenta em uma mensagem USER.
        historico.append(
            types.Content(
                role="user",
                parts=partes_resposta,
            )
        )

    return {
        "resposta": resposta_final,
        "rastro_ferramentas": trace_ferramentas,
        "total_turnos": turno + 1,
        "tokens_estimados": tokens_usados,
        "tempo_total_ms": round(
            (perf_counter() - inicio) * 1000, 1
        ),
    }


if __name__ == "__main__":
    evidencia_teste = [
        EvidenciaMultimodal(
            origem="visao",
            resumo_informacao=(
                "Catalogo de demonstracao: item N101, "
                "preco unitario R$ 2500,00."
            ),
        ),
        EvidenciaMultimodal(
            origem="audio",
            resumo_informacao=(
                "Gestor solicita calcular o custo de 2 unidades do item N101."
            ),
        ),
    ]

    resultado = executar_agente(
        "Consulte o item N101 e calcule o custo total de 2 unidades.",
        evidencia_teste,
    )

    print(json.dumps(resultado, indent=2, ensure_ascii=False))