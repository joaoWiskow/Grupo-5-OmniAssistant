import sys
from io import BytesIO
from pathlib import Path
from PIL import Image
from google.genai import types
from pydantic import BaseModel, Field
from src.core.config import MODEL, criar_cliente_gemini
from src.core.contracts import EvidenciaMultimodal

class LeituraVisual(BaseModel):
    resumo_observado: str = Field(description="Sintese clara dos fatos observados na imagem")
    dados_chave: list[str] = Field(description="Codigos, metricas, valores ou nomes explicitamente visiveis")
    alertas_qualidade: list[str] = Field(default_factory=list, description="Problemas de nitidez ou campos duvidosos")

def processar_imagem(caminho: Path) -> EvidenciaMultimodal:
    """Valida a imagem localmente e extrai evidencias estruturadas via Gemini."""
    if not caminho.is_file() or caminho.stat().st_size > 5_000_000:
        raise ValueError("A imagem deve existir no disco e ter ate 5 MB.")
        
    dados = caminho.read_bytes()
    with Image.open(BytesIO(dados)) as img:
        img.verify()
    with Image.open(BytesIO(dados)) as img:
        formato = img.format
        if formato not in ("PNG", "JPEG"):
            raise ValueError(f"Formato {formato} invalido. Apenas PNG e JPEG sao aceitos.")
        largura, altura = img.size
        if largura * altura > 12_000_000:
            raise ValueError("Imagem excede 12 Megapixels.")
            
    mime_type = "image/png" if formato == "PNG" else "image/jpeg"
    
    # TODO: Personalize a system instruction com o contexto de negocio da sua squad!
    system_instruction = (
        "Voce e o especialista em percepcao visual do OmniAssistant. "
        "Extraia apenas fatos, numeros e rotulos que estejam inequivocamente legiveis na imagem. "
        "Nao presuma dados ausentes. Se houver corte ou ilegibilidade, registre em alertas_qualidade."
    )
    
    cliente = criar_cliente_gemini()
    resposta = cliente.models.generate_content(
        model=MODEL,
        contents=[
            "Extraia as evidencias visuais deste documento/tela.",
            types.Part.from_bytes(data=dados, mime_type=mime_type)
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=LeituraVisual
        )
    )
    
    leitura = LeituraVisual.model_validate_json(resposta.text or "{}")
    texto_consolidado = f"{leitura.resumo_observado}\nDados: {', '.join(leitura.dados_chave)}"
    if leitura.alertas_qualidade:
        texto_consolidado += f"\nAlertas: {'; '.join(leitura.alertas_qualidade)}"
        
    return EvidenciaMultimodal(
        origem="visao",
        resumo_informacao=texto_consolidado,
        confianca_declarada=0.7 if leitura.alertas_qualidade else 1.0
    )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m src.vision.processor data/amostra.png")
        sys.exit(1)
    evidencia = processar_imagem(Path(sys.argv[1]))
    print(evidencia.model_dump_json(indent=2))