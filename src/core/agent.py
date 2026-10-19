import json
from time import perf_counter
from typing import Callable
from pydantic import BaseModel, ConfigDict, Field
from google.genai import types
from src.core.config import MODEL, criar_cliente_gemini
from src.core.contracts import EvidenciaMultimodal
from src.tools.local import consultar_item, calcular_total, validar_codigo

# Contratos estritos dos argumentos das ferramentas
class CodigoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    codigo: str = Field(description="Codigo do produto (ex: A101, B202)")

class TotalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    quantidade: float = Field(ge=0.1, le=1000.0, description="Quantidade de itens")
    preco_unitario: float = Field(ge=0.01, le=100000.0, description="Preco unitario em BRL")

REGISTRO_TOOLS: dict[str, tuple[Callable[..., dict], type[BaseModel], str]] = {
    "consultar_item": (consultar_item, CodigoArgs, "Consulta nome, preco e setor de um item por codigo no banco SQLite."),
    "calcular_total": (calcular_total, TotalArgs, "Calcula o valor total em BRL a partir de quantidade e preco."),
    "validar_codigo": (validar_codigo, CodigoArgs, "Valida o formato de um codigo de produto.")
}

FERRAMENTAS_GEMINI = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name=nome,
        description=desc,
        parameters_json_schema=schema.model_json_schema()
    )
    for nome, (_, schema, desc) in REGISTRO_TOOLS.items()
])

def despachar_tool(chamada: types.FunctionCall) -> dict:
    nome = chamada.name
    if nome not in REGISTRO_TOOLS:
        return {"erro": f"Ferramenta '{nome}' nao autorizada."}
        
    funcao, schema, _ = REGISTRO_TOOLS[nome]
    try:
        args = schema.model_validate(chamada.args or {}).model_dump()
        return funcao(**args)
    except Exception as e:
        return {"erro": f"Argumentos invalidos para {nome}: {type(e).__name__}"}

def executar_agente(pergunta: str, evidencias: list[EvidenciaMultimodal]) -> dict:
    """Executa o loop agentico multimodal em multiplos turnos com limite de passos."""
    inicio = perf_counter()
    trace_ferramentas = []
    
    contexto_evidencias = [e.model_dump() for e in evidencias]
    payload_usuario = json.dumps({
        "pergunta": pergunta,
        "evidencias_multimodais": contexto_evidencias
    }, ensure_ascii=False)
    
    historico = [types.Content(role="user", parts=[types.Part.from_text(text=payload_usuario)])]
    
    system_instruction = (
        "Voce e o orquestrador inteligente do OmniAssistant. "
        "Analise cuidadosamente as evidencias de visao e audio fornecidas. "
        "Quando precisar de precos ou dados cadastrais, acione consultar_item. "
        "Para contas matematicas, acione calcular_total. Nao chute valores! "
        "Na resposta final, cite explicitamente de onde veio cada informacao (ex: 'conforme observado na imagem')."
    )
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.0,
        tools=[FERRAMENTAS_GEMINI],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
    )
    
    resposta_final = "Limite de chamadas atingido."
    tokens_usados = 0
    cliente = criar_cliente_gemini()
    
    # Loop com trava de seguranca (max 4 turnos)
    for turno in range(4):
        resposta = cliente.models.generate_content(model=MODEL, contents=historico, config=config)
        if resposta.usage_metadata and resposta.usage_metadata.total_token_count:
            tokens_usados += resposta.usage_metadata.total_token_count
            
        candidato = resposta.candidates[0].content if resposta.candidates else None
        if not candidato:
            resposta_final = "Sem resposta do modelo."
            break
            
        historico.append(candidato)
        chamadas = [p.function_call for p in candidato.parts or [] if p.function_call is not None]
        
        # Se o modelo nao pediu mais ferramentas, ele concluiu a resposta!
        if not chamadas:
            resposta_final = resposta.text or "Resposta conclusiva emitida."
            break
            
        # Executa cada ferramenta solicitada e alimenta a observacao de volta
        partes_resposta = []
        for call in chamadas:
            t0 = perf_counter()
            resultado = despachar_tool(call)
            duracao_ms = round((perf_counter() - t0) * 1000, 1)
            
            trace_ferramentas.append({
                "ferramenta": call.name,
                "argumentos": call.args,
                "resultado": resultado,
                "duracao_ms": duracao_ms
            })
            partes_resposta.append(types.Part(
                function_response=types.FunctionResponse(name=call.name, response=resultado)
            ))
            
        historico.append(types.Content(role="tool", parts=partes_resposta))
        
    return {
        "resposta": resposta_final,
        "rastro_ferramentas": trace_ferramentas,
        "total_turnos": turno + 1,
        "tokens_estimados": tokens_usados,
        "tempo_total_ms": round((perf_counter() - inicio) * 1000, 1)
    }

if __name__ == "__main__":
    from src.core.contracts import EvidenciaMultimodal
    evidencia_teste = [
        EvidenciaMultimodal(origem="visao", resumo_informacao="Print de ordem de servico mostrando peca A101"),
        EvidenciaMultimodal(origem="audio", resumo_informacao="Cliente solicita a compra de 4 unidades deste item")
    ]
    resultado = executar_agente("Qual o custo total desta solicitacao?", evidencia_teste)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))