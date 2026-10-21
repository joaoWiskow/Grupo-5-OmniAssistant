import json
from time import perf_counter
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field
from google.genai import types

from src.core.config import MODEL, criar_cliente_gemini
from src.core.contracts import EvidenciaMultimodal
from src.tools.local import consultar_item, calcular_total, validar_codigo
from src.tools.validacao import validar_cnpj_cpf, conferir_soma
from src.tools.dados import consultar_banco, descrever_banco


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


class DocumentoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    documento: str = Field(
        description="CNPJ (14 digitos) ou CPF (11 digitos), com ou sem pontuacao"
    )


class TabelaArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tabela: str = Field(
        default="",
        description="Nome da tabela a detalhar. Deixe vazio para listar todas as tabelas do banco.",
    )


class ConsultaArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sql: str = Field(
        min_length=6, max_length=2000,
        description="UMA consulta SELECT em SQLite (pode usar WITH, JOIN, GROUP BY). Somente leitura.",
    )


class SomaArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    quantidades: list[float] = Field(
        min_length=1, max_length=200,
        description="Quantidade de cada item da nota, na ordem em que aparecem",
    )
    precos_unitarios: list[float] = Field(
        min_length=1, max_length=200,
        description="Preco unitario em BRL de cada item, na MESMA ordem das quantidades",
    )
    total_declarado: float = Field(
        ge=0.0, description="Valor total da nota em BRL, como impresso na nota"
    )
    ajustes: float = Field(
        default=0.0,
        description="Frete + impostos fora dos itens - descontos, em BRL. Zero se nao houver.",
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
    "validar_cnpj_cpf": (
        validar_cnpj_cpf,
        DocumentoArgs,
        "Confere os digitos verificadores de um CNPJ ou CPF extraido da nota."
    ),
    "conferir_soma": (
        conferir_soma,
        SomaArgs,
        "Confere se a soma de quantidade x preco unitario dos itens bate com o total da nota."
    ),
    "descrever_banco": (
        descrever_banco,
        TabelaArgs,
        "Mostra as tabelas do banco de dados da empresa (clientes, notas, itens e catalogo) com colunas e exemplos."
    ),
    "consultar_banco": (
        consultar_banco,
        ConsultaArgs,
        "Executa uma consulta SELECT (somente leitura) no banco da empresa para responder perguntas sobre clientes, notas e faturamento."
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


def avaliar_risco(rastro: list[dict]) -> dict:
    """Semaforo calculado so a partir dos resultados das ferramentas (nao do modelo).

    vermelho: alguma conferencia reprovou | amarelo: alguma nao pode ser feita |
    verde: conferencias feitas e todas aprovadas | neutro: nenhuma conferencia usada.
    """
    vermelho, amarelo, aprovadas = [], [], 0

    for passo in rastro:
        nome = passo["ferramenta"]
        res = passo.get("resultado") or {}

        if nome not in ("validar_cnpj_cpf", "conferir_soma"):
            continue
        if "erro" in res:
            amarelo.append(f"Não foi possível executar {nome}.")
            continue

        if nome == "validar_cnpj_cpf":
            if res.get("valido"):
                aprovadas += 1
            else:
                vermelho.append(f"{res.get('tipo', 'Documento')} {res.get('documento')}: {res.get('motivo')}")
        else:
            if res.get("confere"):
                aprovadas += 1
            else:
                vermelho.append(
                    f"Soma dos itens diverge do total em R$ {abs(res.get('diferenca', 0)):.2f}."
                )

    if vermelho:
        return {"nivel": "vermelho", "rotulo": "DIVERGÊNCIA", "motivos": vermelho + amarelo}
    if amarelo:
        return {"nivel": "amarelo", "rotulo": "ATENÇÃO", "motivos": amarelo}
    if aprovadas:
        plural = "conferência aprovada" if aprovadas == 1 else "conferências aprovadas"
        return {"nivel": "verde", "rotulo": "CONFERIDO", "motivos": [f"{aprovadas} {plural}."]}
    return {"nivel": "neutro", "rotulo": "SEM CONFERÊNCIA", "motivos": []}


def executar_agente(
    pergunta: str,
    evidencias: list[EvidenciaMultimodal],
    ao_evento: Callable[[dict], None] | None = None,
) -> dict:
    """Executa o agente multimodal com chamadas explicitas de ferramentas.

    ao_evento (opcional): funcao chamada a cada passo, para a interface
    mostrar o raciocinio ao vivo. Eventos emitidos:
      {"tipo": "turno", "n": 1}
      {"tipo": "ferramenta", "nome": ..., "argumentos": ...,
       "resultado": ..., "duracao_ms": ...}
    Se for None, o comportamento e identico ao anterior.
    """

    def emitir(**evento) -> None:
        if ao_evento is None:
            return
        try:
            ao_evento(evento)
        except Exception:
            # Falha na interface nunca deve derrubar o agente.
            pass

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
        "Responda em portugues brasileiro e informe a origem das informacoes. "
        "Escreva respostas completas e bem explicadas, nunca telegraficas: "
        "comece respondendo diretamente a pergunta e depois acrescente o "
        "contexto relevante das evidencias, como os demais dados da nota que "
        "ajudem a conferir a resposta, o que foi consultado no catalogo e o "
        "resultado de cada calculo. Termine com alertas e pendencias quando "
        "houver (dados ilegiveis, divergencias, confirmacoes necessarias). "
        "Seja completo, mas continue sem inventar dados ausentes: se um campo "
        "nao estiver nas evidencias, diga que nao foi encontrado. "
        "Sempre que as evidencias trouxerem CNPJ ou CPF, use validar_cnpj_cpf "
        "para cada documento. Quando a nota trouxer itens com quantidades e "
        "valores unitarios junto com um total, use conferir_soma (frete, "
        "impostos e descontos que estejam na nota entram em 'ajustes'). "
        "Relate na resposta o resultado de cada conferencia e nunca ignore "
        "uma divergencia. "
        "Perguntas sobre clientes, notas cadastradas, faturamento, status de "
        "cobranca ou outros dados da empresa NAO dependem das evidencias "
        "enviadas: responda consultando o banco. Se ainda nao conhecer o "
        "esquema, use descrever_banco primeiro; depois use consultar_banco com "
        "uma unica consulta SELECT, usando agregacoes (COUNT, SUM, GROUP BY) em "
        "vez de listar linhas quando a pergunta pedir totais ou rankings. Se a "
        "consulta falhar, corrija-a e tente de novo. Responda apenas com o que "
        "a consulta retornou, informe quais tabelas usou e avise se o resultado "
        "foi truncado. Voce so le o banco: nunca diga que inseriu, alterou ou "
        "apagou registros. Nao misture dados do banco com os da nota enviada."
    )

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.0,
        tools=[FERRAMENTAS_GEMINI],
        automatic_function_calling=(
            types.AutomaticFunctionCallingConfig(disable=True)
        ),
    )

    for turno in range(6):
        emitir(tipo="turno", n=turno + 1)

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

            emitir(
                tipo="ferramenta",
                nome=chamada.name,
                argumentos=dict(chamada.args or {}),
                resultado=resultado,
                duracao_ms=duracao_ms,
            )

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
        "risco": avaliar_risco(trace_ferramentas),
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
        ao_evento=print,
    )

    print(json.dumps(resultado, indent=2, ensure_ascii=False))