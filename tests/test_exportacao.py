import csv
import io

from src.core.exportacao import montar_csv_financeiro


def ler_linhas(conteudo):
    return list(csv.DictReader(io.StringIO(conteudo.removeprefix("\ufeff"))))


def analise(*resultados):
    rastro = [
        {"ferramenta": "consultar_banco", "resultado": resultado}
        for resultado in resultados
    ]
    return {
        "papel": "assistant",
        "conteudo": "Resposta",
        "pergunta": "Pergunta",
        "telemetria": {"rastro_ferramentas": rastro},
    }


def test_exporta_linhas_da_consulta_da_conversa():
    historico = [
        {"papel": "user", "conteudo": "Quais notas venceram?"},
        analise(
            {
                "colunas": ["cliente", "numero", "valor_total", "status"],
                "linhas": [
                    ["Cliente A", "NF-1", 1234.5, "vencida"],
                    ["Cliente B", "NF-2", 500.0, "vencida"],
                ],
            }
        ),
    ]

    linhas = ler_linhas(montar_csv_financeiro(historico))

    assert len(linhas) == 2
    assert linhas[0]["cliente"] == "Cliente A"
    assert linhas[0]["numero"] == "NF-1"
    assert linhas[0]["valor_total"] == "1234.5"
    assert linhas[1]["status"] == "vencida"


def test_junta_colunas_de_varias_consultas():
    historico = [
        analise({"colunas": ["cliente", "total"], "linhas": [["Cliente A", 10.0]]}),
        analise({"colunas": ["mes", "faturamento"], "linhas": [["2026-01", 99.9]]}),
    ]

    linhas = ler_linhas(montar_csv_financeiro(historico))

    assert list(linhas[0].keys()) == ["cliente", "total", "mes", "faturamento"]
    assert linhas[0]["cliente"] == "Cliente A"
    assert linhas[0]["mes"] == ""
    assert linhas[1]["mes"] == "2026-01"
    assert linhas[1]["total"] == ""


def test_nao_duplica_linhas_repetidas():
    resultado = {"colunas": ["cliente", "total"], "linhas": [["Cliente A", 10.0]]}

    assert (
        len(ler_linhas(montar_csv_financeiro([analise(resultado), analise(resultado)])))
        == 1
    )


def test_ignora_ferramentas_que_nao_sao_consulta():
    historico = [
        {
            "papel": "assistant",
            "conteudo": "Resposta",
            "telemetria": {
                "rastro_ferramentas": [
                    {"ferramenta": "calcular_total", "resultado": {"total": 10.0}}
                ]
            },
        }
    ]

    assert montar_csv_financeiro(historico) == ""


def test_sem_pergunta_nao_gera_csv():
    assert montar_csv_financeiro([]) == ""
    assert montar_csv_financeiro([{"papel": "user", "conteudo": "Oi"}]) == ""
