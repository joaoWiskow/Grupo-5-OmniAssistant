import json
import math
import re
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path("data/catalogo.sqlite")

def inicializar_banco() -> None:
    """Cria a tabela e popula com registros sinteticos da demonstracao."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS itens (
                codigo TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                preco REAL NOT NULL,
                setor TEXT NOT NULL
            )
        """)
        # TODO: Adicione registros realistas adaptados ao caso da sua squad!
        dados = [
            ("N101", "Nota Fiscal de Servicos - Consultoria TI", 2500.00, "Servicos"),
            ("N202", "Nota Fiscal de Produtos - Equipamentos", 4750.50, "Produtos"),
            ("N303", "Fatura de Licenciamento de Software", 899.90, "Software"),
            ("N404", "Nota Fiscal de Manutencao de Hardware", 1250.00, "Manutencao"),
            ("N505", "Fatura de Servicos de Cloud", 680.75, "Infraestrutura"),
            ("N606", "Nota Fiscal de Material de Escritorio", 345.80, "Suprimentos"),
            ("N707", "Fatura de Telecomunicacoes", 219.99, "Telecomunicacoes"),
            ("N808", "Nota Fiscal de Consultoria Financeira", 1800.00, "Consultoria")
        ]
        conn.executemany("INSERT OR IGNORE INTO itens VALUES (?, ?, ?, ?)", dados)
        conn.commit()

def validar_codigo(codigo: str) -> dict:
    """Valida se o codigo segue o padrao [Letra Maiuscula][3 digitos] (ex: A101)."""
    valido = bool(re.fullmatch(r"[A-Z][0-9]{3}", codigo.strip()))
    return {"codigo": codigo, "valido": valido}

def consultar_item(codigo: str) -> dict:
    """Consulta informacoes tecnicas e preco de um item no banco relacional local."""
    codigo_limpo = codigo.strip().upper()
    if not validar_codigo(codigo_limpo)["valido"]:
        return {"erro": "Formato de codigo invalido. Padrao esperado: 1 letra e 3 numeros (ex: A101)."}
        
    if not DB_PATH.is_file():
        inicializar_banco()
        
    with closing(sqlite3.connect(f"{DB_PATH.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.execute("SELECT codigo, nome, preco, setor FROM itens WHERE codigo = ?", (codigo_limpo,))
        linha = cursor.fetchone()
        
    if not linha:
        return {"encontrado": False, "mensagem": f"Item {codigo_limpo} nao consta no catalogo."}
        
    return {
        "encontrado": True,
        "codigo": linha[0],
        "nome": linha[1],
        "preco": linha[2],
        "setor": linha[3]
    }

def calcular_total(quantidade: float, preco_unitario: float) -> dict:
    """Calcula o valor financeiro total de um lote com precisao monetaria."""
    if quantidade <= 0 or preco_unitario < 0:
        return {"erro": "Quantidade deve ser positiva e preco nao pode ser negativo."}
        
    total = round(quantidade * preco_unitario, 2)
    return {
        "quantidade": quantidade,
        "preco_unitario": preco_unitario,
        "total": total,
        "moeda": "BRL"
    }

if __name__ == "__main__":
    inicializar_banco()
    print("Banco inicializado:", DB_PATH)
    print("Teste consulta A101:", consultar_item("A101"))
    print("Teste calculo 4 x 25.0:", calcular_total(4, 25.0))