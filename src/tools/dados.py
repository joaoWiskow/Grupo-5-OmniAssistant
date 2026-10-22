"""Dados de exemplo (clientes e notas) e consulta segura, somente leitura, ao SQLite."""

import os
import random
import re
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

from src.core.auth import obter_contexto_ativo
from src.core.contracts import PapelUsuario
from src.tools.local import DB_PATH
from src.tools.validacao import _dv_cnpj

LIMITE_LINHAS = 200
TEMPO_MAX_S = 3.0

# Codigos de acao do autorizador do SQLite: so leitura passa.
_SELECT, _READ, _FUNCTION, _RECURSIVE = 21, 20, 31, 33
_ACOES_PERMITIDAS = {_SELECT, _READ, _FUNCTION, _RECURSIVE}

DESCRICOES = {
    "clientes": "Clientes cadastrados. 'estado' é a UF com 2 letras; 'segmento' é a área de atuação.",
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
_CLIENTES = [
    ("Comercial Pampa Ltda", "Porto Alegre", "RS", "Varejo"),
    ("Metalúrgica Gaúcha S.A.", "Caxias do Sul", "RS", "Indústria"),
    ("Tecnosul Sistemas", "Porto Alegre", "RS", "Tecnologia"),
    ("Distribuidora Lagoa", "Pelotas", "RS", "Varejo"),
    ("Agro Campos do Sul", "Santa Maria", "RS", "Agro"),
    ("Móveis Serra Azul", "Bento Gonçalves", "RS", "Indústria"),
    ("Clínica Vida Plena", "Canoas", "RS", "Serviços"),
    ("Logística Rio Guaíba", "Porto Alegre", "RS", "Serviços"),
    ("Panificadora Trigal", "Novo Hamburgo", "RS", "Varejo"),
    ("Cooperativa Vale Verde", "Passo Fundo", "RS", "Agro"),
    ("Grupo Paulista Alimentos", "São Paulo", "SP", "Indústria"),
    ("Inova Digital Ltda", "Campinas", "SP", "Tecnologia"),
    ("Atacado Bandeirantes", "Ribeirão Preto", "SP", "Varejo"),
    ("Construtora Horizonte", "São Paulo", "SP", "Serviços"),
    ("Têxtil Anhanguera", "Sorocaba", "SP", "Indústria"),
    ("Porto Norte Logística", "Itajaí", "SC", "Serviços"),
    ("Eletro Catarina", "Joinville", "SC", "Indústria"),
    ("Software Floripa", "Florianópolis", "SC", "Tecnologia"),
    ("Malharia Vale do Itajaí", "Blumenau", "SC", "Indústria"),
    ("Curitiba Distribuidora", "Curitiba", "PR", "Varejo"),
    ("Agroindustrial Paraná", "Londrina", "PR", "Agro"),
    ("Vidraçaria Maringá", "Maringá", "PR", "Indústria"),
    ("Minas Insumos", "Belo Horizonte", "MG", "Indústria"),
    ("Café Serra Mineira", "Uberlândia", "MG", "Agro"),
    ("Carioca Serviços Gerais", "Rio de Janeiro", "RJ", "Serviços"),
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
]


def inicializar_dados(total_notas: int = 80) -> None:
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
        datas = sorted(
            hoje - timedelta(days=rng.randint(1, 365)) for _ in range(total_notas)
        )

        for n, emissao in enumerate(datas, start=1):
            cliente_id = rng.choices(range(1, len(_CLIENTES) + 1), weights=pesos)[0]
            itens = rng.sample(_ITENS, rng.randint(1, 4))
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
                (
                    f"NF-{emissao.year}{n:04d}",
                    cliente_id,
                    emissao.isoformat(),
                    vencimento.isoformat(),
                    round(total, 2),
                    status,
                ),
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
def descrever_banco(tabela: str = "", papel: PapelUsuario | None = None) -> dict:
    """Lista tabelas, colunas, contagem e exemplos de linhas."""
    try:
        con = _conexao_leitura()
    except Exception as e:
        return {"erro": str(e)}
    try:
        nomes = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        nomes = [n for n in nomes if not _tabela_oculta(n, papel)]
        if tabela:
            if tabela not in nomes:
                return {
                    "erro": f"Tabela '{tabela}' não existe.",
                    "tabelas_disponiveis": nomes,
                }
            nomes = [tabela]

        resultado = []
        for nome in nomes:
            colunas = [
                {"nome": c[1], "tipo": c[2]}
                for c in con.execute(f'PRAGMA table_info("{nome}")')
            ]
            total = con.execute(f'SELECT COUNT(*) FROM "{nome}"').fetchone()[0]
            cur = con.execute(f'SELECT * FROM "{nome}" LIMIT 2')
            amostra = [
                dict(zip([d[0] for d in cur.description], linha))
                for linha in cur.fetchall()
            ]
            resultado.append(
                {
                    "tabela": nome,
                    "descricao": DESCRICOES.get(nome, ""),
                    "linhas": total,
                    "colunas": colunas,
                    "amostra": amostra,
                }
            )
        return {"tabelas": resultado, "observacoes": OBSERVACOES}
    finally:
        con.close()


_TABELAS_SEMPRE_OCULTAS = {"usuarios", "sqlite_master", "sqlite_schema"}


def _papel_ativo() -> PapelUsuario | None:
    ctx = obter_contexto_ativo()
    return ctx.usuario.papel if ctx else None


def _tabela_oculta(nome: str, papel: PapelUsuario | None = None) -> bool:
    if nome in _TABELAS_SEMPRE_OCULTAS:
        return True
    return nome == "clientes" and (papel or _papel_ativo()) in (
        PapelUsuario.ANALISTA,
        None,
    )


def _autorizar(acao, arg1=None, arg2=None, db=None, trigger=None):
    if acao not in _ACOES_PERMITIDAS:
        return 1  # 0 = OK, 1 = DENY
    if acao == _READ and arg1 and _tabela_oculta(arg1):
        return 1
    return 0


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
        con.set_progress_handler(
            lambda: 1 if time.monotonic() > limite_tempo else 0, 10000
        )

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


def esquema_para_prompt(papel: PapelUsuario | None = None) -> str:
    """Esquema compacto (tabelas, colunas, valores categóricos) para embutir no prompt."""
    info = descrever_banco(papel=papel)
    if "erro" in info:
        return ""

    linhas = []
    for t in info["tabelas"]:
        cols = ", ".join(f"{c['nome']} {c['tipo']}" for c in t["colunas"])
        linhas.append(f"- {t['tabela']}({cols})")
        if t["descricao"]:
            linhas.append(f"  {t['descricao']}")

    con = _conexao_leitura()
    try:
        for tabela, colunas in _CATEGORICAS.items():
            if _tabela_oculta(tabela, papel):
                continue
            for col in colunas:
                try:
                    valores = [
                        r[0]
                        for r in con.execute(
                            f'SELECT DISTINCT "{col}" FROM "{tabela}" '
                            f'WHERE "{col}" IS NOT NULL ORDER BY 1'
                        )
                    ]
                except sqlite3.Error:
                    continue
                if valores:
                    linhas.append(
                        f"Valores de {tabela}.{col}: " + ", ".join(map(str, valores))
                    )
    finally:
        con.close()

    linhas.extend(info.get("observacoes", []))
    return "\n".join(linhas)
