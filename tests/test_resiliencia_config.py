import os
from unittest.mock import patch
from src.core.config import criar_cliente_gemini

def testar_falha_sem_chave():
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        try:
            criar_cliente_gemini()
            print("FALHA: O cliente foi criado sem chave de API!")
        except ValueError as e:
            print("PASS: Sistema levantou ValueError educativo:", str(e))

if __name__ == "__main__":
    testar_falha_sem_chave()