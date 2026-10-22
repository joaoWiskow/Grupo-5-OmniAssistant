"""Dados de exemplo (clientes e notas) e consulta segura, somente leitura, ao SQLite."""
import os
import random
import re
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

from src.tools.local import DB_PATH
from src.tools.validacao import _dv_cnpj

LIMITE_LINHAS = 200
TEMPO_MAX_S = 3.0

# Codigos de acao do autorizador do SQLite: so leitura passa.
_SELECT, _READ, _FUNCTION, _RECURSIVE = 21, 20, 31, 33
_ACOES_PERMITIDAS = {_SELECT, _READ, _FUNCTION, _RECURSIVE}

DESCRICOES = {
    "clientes": (
        "Empresas parceiras do NAVI. 'segmento' é a categoria da empresa no NAVI; "
        "'estado' é a UF com 2 letras."
    ),
    "notas_fiscais": (
        "Notas fiscais emitidas. status: paga | pendente | vencida | cancelada. "
        "valor_total em BRL. Datas em AAAA-MM-DD."
    ),
    "notas_itens": (
        "Itens de cada nota (nota_id referencia notas_fiscais.id; "
        "codigo_item referencia itens.codigo)."
    ),
    "itens": "Catálogo de referência (codigo, nome, setor); 'preco' é o valor unitário em BRL.",
}

OBSERVACOES = [
    "Datas no formato AAAA-MM-DD; valores em BRL.",
    "Para faturamento, desconsidere notas com status 'cancelada'.",
    "Use strftime('%Y-%m', data_emissao) para agrupar por mês.",
    "Para saber o setor de um item vendido, junte notas_itens.codigo_item com itens.codigo.",
]


def caminho_banco() -> Path:
    """Mesmo arquivo do catalogo (DB_PATH do local.py). OMNI_DB sobrescreve, se definido."""
    env = os.getenv("OMNI_DB")
    return Path(env) if env else DB_PATH


def _conexao_leitura() -> sqlite3.Connection:
    caminho = caminho_banco()
    if not caminho.exists():
        raise FileNotFoundError("Banco de dados não encontrado.")
    return sqlite3.connect(f"{caminho.resolve().as_uri()}?mode=ro", uri=True)


# ---------------------------------------------------------------------------
# Carga de dados de exemplo
# ---------------------------------------------------------------------------
# Parceiros reais do NAVI (nome e categoria conforme o site).
# ATENCAO: cidade/UF sao provisorias (Porto Alegre/RS) porque o site nao as mostra;
# ajuste quando souber. A RAIES aparece sem categoria no site.
_CIDADE_PADRAO, _UF_PADRAO = "Porto Alegre", "RS"
_SEM_CATEGORIA = "Não informado"

_CLIENTES = [
    ("Green Thinking", _CIDADE_PADRAO, _UF_PADRAO, "Sustentabilidade, Energia e Meio Ambiente"),
    ("RAIES", _CIDADE_PADRAO, _UF_PADRAO, _SEM_CATEGORIA),
    ("Energia das Coisas", _CIDADE_PADRAO, _UF_PADRAO, "Sustentabilidade, Energia e Meio Ambiente"),
    ("GreenMotor", _CIDADE_PADRAO, _UF_PADRAO, "Agronegócio e AgTechs"),
    ("Instituto Ceos", _CIDADE_PADRAO, _UF_PADRAO, "Saúde, Biotecnologia e Ciências da Vida"),
    ("noharm.ai", _CIDADE_PADRAO, _UF_PADRAO, "Saúde, Biotecnologia e Ciências da Vida"),
    ("Vent", _CIDADE_PADRAO, _UF_PADRAO, "Tecnologia da Informação e Software"),
    ("GiroLend", _CIDADE_PADRAO, _UF_PADRAO, "Fintechs e Serviços Financeiros"),
    ("IBIAMA", _CIDADE_PADRAO, _UF_PADRAO, "Games, Mídia e Entretenimento"),
    ("SymCORE", _CIDADE_PADRAO, _UF_PADRAO, "Tecnologia da Informação e Software"),
    ("DGM Financeira", _CIDADE_PADRAO, _UF_PADRAO, "Fintechs e Serviços Financeiros"),
]

# Mesmos codigos, nomes e precos do catalogo (tabela 'itens' do local.py).
_ITENS = [
    ("N101", "Nota Fiscal de Servicos - Consultoria TI", 2500.00),
    ("N202", "Nota Fiscal de Produtos - Equipamentos", 4750.50),
    ("N303", "Fatura de Licenciamento de Software", 899.90),
    ("N404", "Nota Fiscal de Manutencao de Hardware", 1250.00),
    ("N505", "Fatura de Servicos de Cloud", 680.75),
    ("N606", "Nota Fiscal de Material de Escritorio", 345.80),
    ("N707", "Fatura de Telecomunicacoes", 219.99),
    ("N808", "Nota Fiscal de Consultoria Financeira", 1800.00),
    ("N901", "Nota Fiscal de Dados e Analytics", 3200.00),
    ("N902", "Serviços de Suporte Operacional", 1450.00),
    ("N903", "Licenciamento de Segurança Cibernética", 2100.00),
    ("N904", "Compra de Equipamentos de Redes", 860.00),
    ("N905", "Consultoria em Processos e Operações", 1750.00),
    ("N906", "Fatura de Hardware de Segurança", 990.00),
    ("N907", "Serviços de Infraestrutura e Backup", 1380.00),
    ("N908", "Equipamentos de Escritório", 420.00),
    ("N909", "Licenciamento de ERP", 2600.00),
    ("N910", "Fatura de Escritório Digital", 730.50),
]


def inicializar_dados(total_notas: int = 120) -> None:
    """Cria as tabelas e, se estiverem vazias, carrega clientes e notas de exemplo."""
    caminho_banco().parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho_banco())
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                cnpj TEXT NOT NULL UNIQUE,
                cidade TEXT,
                estado TEXT,
                segmento TEXT,
                data_cadastro TEXT
            );
            CREATE TABLE IF NOT EXISTS notas_fiscais (
                id INTEGER PRIMARY KEY,
                numero TEXT NOT NULL UNIQUE,
                cliente_id INTEGER REFERENCES clientes(id),
                data_emissao TEXT,
                data_vencimento TEXT,
                valor_total REAL,
                status TEXT CHECK (status IN ('paga','pendente','vencida','cancelada'))
            );
            CREATE TABLE IF NOT EXISTS notas_itens (
                id INTEGER PRIMARY KEY,
                nota_id INTEGER REFERENCES notas_fiscais(id),
                codigo_item TEXT,
                descricao TEXT,
                quantidade REAL,
                preco_unitario REAL
            );
            """
        )
        if con.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] > 0:
            return

        rng = random.Random(7)
        hoje = date.today()

        # CNPJs gerados apenas para a demonstracao (NAO sao os CNPJs reais dos parceiros).
        for i, (nome, cidade, uf, segmento) in enumerate(_CLIENTES, start=1):
            base = f"{10000000 + i * 1111111:08d}0001"
            cnpj = base + _dv_cnpj([int(c) for c in base])
            cadastro = hoje - timedelta(days=rng.randint(400, 1500))
            con.execute(
                "INSERT INTO clientes (id, nome, cnpj, cidade, estado, segmento, data_cadastro) "
                "VALUES (?,?,?,?,?,?,?)",
                (i, nome, cnpj, cidade, uf, segmento, cadastro.isoformat()),
            )

        pesos = [rng.randint(1, 5) for _ in _CLIENTES]
        datas = sorted(hoje - timedelta(days=rng.randint(1, 365)) for _ in range(total_notas))

        for n, emissao in enumerate(datas, start=1):
            cliente_id = rng.choices(range(1, len(_CLIENTES) + 1), weights=pesos)[0]
            itens = rng.sample(_ITENS, rng.randint(1, 5))
            linhas, total = [], 0.0
            for codigo, descricao, preco in itens:
                qtd = float(rng.randint(1, 8))
                linhas.append((codigo, descricao, qtd, preco))
                total += qtd * preco

            vencimento = emissao + timedelta(days=30)
            sorteio = rng.random()
            if sorteio < 0.06:
                status = "cancelada"
            elif vencimento < hoje:
                status = "paga" if rng.random() < 0.8 else "vencida"
            else:
                status = "pendente"

            cur = con.execute(
                "INSERT INTO notas_fiscais (numero, cliente_id, data_emissao, data_vencimento, valor_total, status) "
                "VALUES (?,?,?,?,?,?)",
                (f"NF-{emissao.year}{n:04d}", cliente_id, emissao.isoformat(),
                 vencimento.isoformat(), round(total, 2), status),
            )
            con.executemany(
                "INSERT INTO notas_itens (nota_id, codigo_item, descricao, quantidade, preco_unitario) "
                "VALUES (?,?,?,?,?)",
                [(cur.lastrowid, *linha) for linha in linhas],
            )
        con.commit()
    finally:
        con.close()


def reiniciar_dados() -> None:
    """Apaga SOMENTE as tabelas de exemplo (clientes e notas) e recarrega. O catalogo nao e tocado."""
    con = sqlite3.connect(caminho_banco())
    try:
        con.executescript(
            "DROP TABLE IF EXISTS notas_itens; DROP TABLE IF EXISTS notas_fiscais; DROP TABLE IF EXISTS clientes;"
        )
        con.commit()
    finally:
        con.close()
    inicializar_dados()


# ---------------------------------------------------------------------------
# Ferramentas do agente (somente leitura)
# ---------------------------------------------------------------------------
def descrever_banco(tabela: str = "") -> dict:
    """Lista tabelas, colunas, contagem e exemplos de linhas."""
    try:
        con = _conexao_leitura()
    except Exception as e:
        return {"erro": str(e)}
    try:
        nomes = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        if tabela:
            if tabela not in nomes:
                return {"erro": f"Tabela '{tabela}' não existe.", "tabelas_disponiveis": nomes}
            nomes = [tabela]

        resultado = []
        for nome in nomes:
            colunas = [{"nome": c[1], "tipo": c[2]} for c in con.execute(f'PRAGMA table_info("{nome}")')]
            total = con.execute(f'SELECT COUNT(*) FROM "{nome}"').fetchone()[0]
            cur = con.execute(f'SELECT * FROM "{nome}" LIMIT 2')
            amostra = [dict(zip([d[0] for d in cur.description], linha)) for linha in cur.fetchall()]
            resultado.append({
                "tabela": nome,
                "descricao": DESCRICOES.get(nome, ""),
                "linhas": total,
                "colunas": colunas,
                "amostra": amostra,
            })
        return {"tabelas": resultado, "observacoes": OBSERVACOES}
    finally:
        con.close()


def _autorizar(acao, *_):
    return 0 if acao in _ACOES_PERMITIDAS else 1  # 0 = OK, 1 = DENY


def _simples(valor):
    return valor if isinstance(valor, (int, float, str, type(None))) else str(valor)


def consultar_banco(sql: str) -> dict:
    """Executa UMA consulta SELECT, com conexão somente leitura, limite de tempo e de linhas."""
    texto = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", texto):
        return {"erro": "Somente consultas SELECT são permitidas."}

    try:
        con = _conexao_leitura()
    except Exception as e:
        return {"erro": str(e)}

    try:
        con.set_authorizer(_autorizar)
        limite_tempo = time.monotonic() + TEMPO_MAX_S
        con.set_progress_handler(lambda: 1 if time.monotonic() > limite_tempo else 0, 10000)

        cur = con.execute(texto)
        colunas = [d[0] for d in cur.description]
        linhas = cur.fetchmany(LIMITE_LINHAS + 1)
        truncado = len(linhas) > LIMITE_LINHAS
        linhas = [[_simples(v) for v in linha] for linha in linhas[:LIMITE_LINHAS]]
        return {
            "colunas": colunas,
            "linhas": linhas,
            "total_linhas": len(linhas),
            "truncado": truncado,
        }
    except Exception as e:
        return {"erro": f"Consulta inválida ou não permitida: {type(e).__name__}: {e}"}
    finally:
        con.close()


# Colunas de poucos valores: o modelo precisa ver a grafia exata (acentos, caixa).
_CATEGORICAS = {
    "clientes": ["estado", "segmento"],
    "notas_fiscais": ["status"],
}


def esquema_para_prompt() -> str:
    """Esquema compacto (tabelas, colunas, valores categóricos) para embutir no prompt."""
    info = descrever_banco()
    if "erro" in info:
        return ""

    linhas = []
    for t in info["tabelas"]:
        cols = ", ".join(f'{c["nome"]} {c["tipo"]}' for c in t["colunas"])
        linhas.append(f'- {t["tabela"]}({cols})')
        if t["descricao"]:
            linhas.append(f'  {t["descricao"]}')

    con = _conexao_leitura()
    try:
        for tabela, colunas in _CATEGORICAS.items():
            for col in colunas:
                try:
                    valores = [r[0] for r in con.execute(
                        f'SELECT DISTINCT "{col}" FROM "{tabela}" '
                        f'WHERE "{col}" IS NOT NULL ORDER BY 1'
                    )]
                except sqlite3.Error:
                    continue
                if valores:
                    # " | " porque os segmentos do NAVI já contêm vírgulas.
                    linhas.append(f"Valores de {tabela}.{col}: " + " | ".join(map(str, valores)))
    finally:
        con.close()

    linhas.extend(info.get("observacoes", []))
    return "\n".join(linhas)