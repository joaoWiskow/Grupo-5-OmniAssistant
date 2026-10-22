import csv
import io


def _resultados_consulta(historico: list[dict]):
    """Percorre o rastro de ferramentas e devolve os resultados de consultas ao banco."""
    for mensagem in historico:
        if mensagem.get("papel") != "assistant":
            continue
        telemetria = mensagem.get("telemetria") or {}
        for passo in telemetria.get("rastro_ferramentas") or []:
            if passo.get("ferramenta") != "consultar_banco":
                continue
            resultado = passo.get("resultado") or {}
            colunas = resultado.get("colunas") or []
            linhas = resultado.get("linhas") or []
            if colunas and linhas:
                yield colunas, linhas


def montar_csv_financeiro(historico: list[dict]) -> str:
    """Exporta as linhas retornadas pelas consultas ao banco feitas nesta conversa."""
    resultados = list(_resultados_consulta(historico))
    if not resultados:
        return ""

    colunas = list(
        dict.fromkeys(coluna for cabecalho, _ in resultados for coluna in cabecalho)
    )
    vistos: set[tuple[str, ...]] = set()
    linhas: list[dict] = []

    for cabecalho, valores_linhas in resultados:
        for valores in valores_linhas:
            registro = dict(zip(cabecalho, valores))
            chave = tuple(str(registro.get(coluna, "")) for coluna in colunas)
            if chave in vistos:
                continue
            vistos.add(chave)
            linhas.append(registro)

    saida = io.StringIO(newline="")
    escritor = csv.DictWriter(saida, fieldnames=colunas, extrasaction="ignore")
    escritor.writeheader()
    for registro in linhas:
        escritor.writerow(
            {
                coluna: "" if registro.get(coluna) is None else registro.get(coluna)
                for coluna in colunas
            }
        )
    return "\ufeff" + saida.getvalue()
