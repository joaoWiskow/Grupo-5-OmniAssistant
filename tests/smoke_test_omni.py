import argparse
import json
from src.core.config import MODEL, TIMEOUT_MS, criar_cliente_gemini
from src.core.contracts import EntradaUsuario, EvidenciaMultimodal, SegmentoFala

def executar_smoke_test(testar_api: bool = False) -> dict:
    print("Iniciando Smoke Test do OmniAssistant...")
    
    # 1. Validacao dos contratos
    cmd = EntradaUsuario(tipo="texto", texto_comando="Ping de teste da arquitetura")
    evidencia = EvidenciaMultimodal(
        origem="texto",
        resumo_informacao=cmd.texto_comando,
        segmentos_audio=[SegmentoFala(inicio_segundos=0.0, fim_segundos=1.5, texto_transcrito="Ping")]
    )
    
    # Valida serializacao e desserializacao JSON
    evidencia_recuperada = EvidenciaMultimodal.model_validate_json(evidencia.model_dump_json())
    assert evidencia_recuperada == evidencia, "Falha na integridade dos contratos Pydantic!"
    
    resultado = {
        "status_contratos": "PASS",
        "modelo_ativo": MODEL,
        "timeout_ms": TIMEOUT_MS,
        "conexao_api": "NAO_SOLICITADA"
    }
    
    # 2. Teste opcional de conectividade com a API
    if testar_api:
        try:
            cliente = criar_cliente_gemini()
            resposta = cliente.models.generate_content(
                model=MODEL,
                contents="Responda apenas com a palavra: OPERACIONAL"
            )
            resultado["conexao_api"] = "CONECTADO_COM_SUCESSO" if resposta.text else "RESPOSTA_VAZIA"
        except Exception as e:
            resultado["conexao_api"] = f"ERRO_DE_CONEXAO: {type(e).__name__}"
            
    return resultado

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", action="store_true", help="Dispara chamada real de validacao no Gemini")
    args = parser.parse_args()
    
    relatorio = executar_smoke_test(testar_api=args.api)
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))