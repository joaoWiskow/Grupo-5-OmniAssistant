import sys
from pathlib import Path
from src.core.contracts import EntradaUsuario
from src.core.ingestion import despachar_ingestao

def testar_lazy_loading():
    # 1. Processar texto nao deve carregar o modulo de audio
    entrada_txt = EntradaUsuario(tipo="texto", texto_comando="Ola Omni")
    despachar_ingestao(entrada_txt)
    
    assert "src.audio.processor" not in sys.modules, "FALHA: Modulo de audio carregado indevidamente!"
    print("PASS: Lazy loading validado com sucesso. Texto puro nao consome memoria de audio.")

if __name__ == "__main__":
    testar_lazy_loading()