from src.core.contracts import EntradaUsuario
from src.core.ingestion import despachar_ingestao

def testar_captura_de_erros_na_ui():
    # Valida que entradas inconsistentes disparam ValueError tratavel
    try:
        despachar_ingestao(EntradaUsuario(tipo="texto", texto_comando="   "))
        print("FALHA: Entrada vazia nao levantou erro!")
    except ValueError as e:
        print("PASS: Erro capturado perfeitamente na borda:", str(e))

if __name__ == "__main__":
    testar_captura_de_erros_na_ui()