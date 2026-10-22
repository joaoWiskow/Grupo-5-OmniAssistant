import sys
from pathlib import Path
from src.core.contracts import EntradaUsuario
from src.core.ingestion import despachar_ingestao

def testar_lazy_loading():
    # Processar texto nao deve carregar o modulo de audio nesta chamada.
    audio_carregado_antes = "src.audio.processor" in sys.modules
    entrada_txt = EntradaUsuario(tipo="texto", texto_comando="Ola Omni")
    despachar_ingestao(entrada_txt)

    audio_carregado_depois = "src.audio.processor" in sys.modules
    assert audio_carregado_depois == audio_carregado_antes, (
        "FALHA: Processar texto carregou o modulo de audio indevidamente!"
    )
    print("PASS: Lazy loading validado com sucesso. Texto puro nao consome memoria de audio.")

if __name__ == "__main__":
    testar_lazy_loading()