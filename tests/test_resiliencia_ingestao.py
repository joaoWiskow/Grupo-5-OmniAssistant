import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def testar_lazy_loading():
    # Processo limpo: isola de outros testes que ja carregaram src.audio.processor
    codigo = (
        "import sys;"
        "from src.core.contracts import EntradaUsuario;"
        "from src.core.ingestion import despachar_ingestao;"
        "despachar_ingestao(EntradaUsuario(tipo='texto', texto_comando='Ola Omni'));"
        "sys.exit('src.audio.processor' in sys.modules)"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True
    )
    assert resultado.returncode == 0, (
        "FALHA: Modulo de audio carregado indevidamente!\n" + resultado.stderr
    )


if __name__ == "__main__":
    testar_lazy_loading()
