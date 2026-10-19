import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

MODEL = "gemini-3.8-flash"
TIMEOUT_MS = 30_000

def criar_cliente_gemini() -> genai.Client:
    """Carrega as variaveis de ambiente e instancia o cliente oficial com timeout estrito."""
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Chave GEMINI_API_KEY ausente! Crie o arquivo .env ou configure no ambiente.")
        
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=TIMEOUT_MS)
    )

def obter_status_configuracao(nome_squad: str) -> str:
    # TODO: Retorne uma string identificando a squad e os parametros ativos (sem vazar a chave!)
    return f"Squad '{nome_squad}' | Modelo: {MODEL} | Timeout: {TIMEOUT_MS}ms"

if __name__ == "__main__":
    print(obter_status_configuracao("Squad 5"))
    print("Configuracao centralizada carregada com sucesso!")