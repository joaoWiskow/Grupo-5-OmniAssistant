import argparse
import json
from pathlib import Path
from src.core.contracts import EntradaUsuario, EvidenciaMultimodal

def despachar_ingestao(entrada: EntradaUsuario) -> EvidenciaMultimodal:
    """Roteia a entrada para o processador especialista sob demanda (Lazy Loading)."""
    if entrada.tipo == "texto":
        return EvidenciaMultimodal(
            origem="texto",
            resumo_informacao=entrada.texto_comando.strip()
        )
    elif entrada.tipo == "imagem":
        # Importacao sob demanda: nao carrega Pillow/Gemini se nao precisar
        from src.vision.processor import processar_imagem
        assert entrada.caminho_arquivo is not None
        return processar_imagem(entrada.caminho_arquivo)
    elif entrada.tipo == "audio":
        # Importacao sob demanda: nao carrega Whisper na memoria se for apenas imagem/texto
        from src.audio.processor import processar_audio
        assert entrada.caminho_arquivo is not None
        return processar_audio(entrada.caminho_arquivo)
    else:
        raise ValueError(f"Tipo de entrada desconhecido: {entrada.tipo}")

def auditar_conflito_evidencias(evidencia_visao: EvidenciaMultimodal, evidencia_audio: EvidenciaMultimodal) -> dict:
    """Verifica se ha palavras ou numeros de alta relevancia divergentes entre imagem e audio."""
    # TODO: Implemente a logica que detecta contradicoes entre o texto da visao e o texto do audio
    conflito_detectado = False
    motivo = "Fontes consistentes ou complementares."
    
    # Exemplo simples: se ambos citam valores monetarios diferentes
    return {
        "visao": evidencia_visao.resumo_informacao,
        "audio": evidencia_audio.resumo_informacao,
        "divergencia_identificada": conflito_detectado,
        "parecer_auditoria": motivo
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Despachante Multimodal OmniAssistant")
    parser.add_argument("tipo", choices=["imagem", "audio", "texto"])
    parser.add_argument("--caminho", type=Path)
    parser.add_argument("--texto", default="")
    args = parser.parse_args()
    
    cmd = EntradaUsuario(tipo=args.tipo, caminho_arquivo=args.caminho, texto_comando=args.texto)
    resultado = despachar_ingestao(cmd)
    print(resultado.model_dump_json(indent=2))