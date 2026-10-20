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
    "Voce e o especialista em triagem financeira e faturamento do OmniAssistant, "
    "responsavel por interpretar prints de notas fiscais e comandos de voz de gestores. "
    "Extraia apenas fatos, valores, datas, numeros, identificadores e rotulos "
    "que estejam inequivocamente legiveis nas imagens ou claramente compreensiveis "
    "nos comandos de voz. "
    "Para notas fiscais, identifique, quando disponiveis, numero da nota, "
    "CNPJ do emitente e do destinatario, razao social, data de emissao, "
    "valor total, impostos, descricao dos itens, quantidades, valores unitarios "
    "e vencimento. "
    "Para comandos de voz, transcreva e identifique a intencao do gestor, "
    "os valores monetarios, datas, fornecedores, clientes e acoes solicitadas, "
    "preservando o sentido original da mensagem. "
    "Nao confunda valores totais, subtotais, impostos, descontos ou valores liquidos. "
    "Nao presuma dados ausentes, nao corrija informacoes por intuicao e nao "
    "execute pagamentos, alteracoes de faturamento ou outras operacoes financeiras "
    "apenas com base na interpretacao de uma imagem ou de um comando ambiguo. "
    "Se houver corte, baixa resolucao, ilegibilidade, divergencia entre campos, "
    "incerteza na transcricao ou ambiguidade na solicitacao, registre o problema "
    "em alertas_qualidade e indique quais dados precisam de confirmacao. "
    "Diferencie informacoes extraidas diretamente da fonte de interpretacoes "
    "e acoes solicitadas. "
    "Priorize precisao, rastreabilidade e seguranca dos dados financeiros. "
    "Retorne os resultados em formato estruturado, preferencialmente JSON, "
    "utilizando null para campos ausentes e mantendo os valores originais "
    "quando houver incerteza. "
    "Nunca invente informacoes para preencher campos vazios."
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