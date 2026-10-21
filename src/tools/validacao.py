"""Ferramentas de conferencia: documentos (CNPJ/CPF) e soma dos itens da nota."""
import re
from decimal import Decimal, ROUND_HALF_UP

_CENTAVO = Decimal("0.01")


def _dv_cpf(digitos: list[int]) -> str:
    def calcular(ds: list[int]) -> int:
        resto = sum(d * p for d, p in zip(ds, range(len(ds) + 1, 1, -1))) % 11
        return 0 if resto < 2 else 11 - resto

    d1 = calcular(digitos)
    d2 = calcular(digitos + [d1])
    return f"{d1}{d2}"


def _dv_cnpj(digitos: list[int]) -> str:
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def calcular(ds: list[int], ps: list[int]) -> int:
        resto = sum(d * p for d, p in zip(ds, ps)) % 11
        return 0 if resto < 2 else 11 - resto

    d1 = calcular(digitos, pesos)
    d2 = calcular(digitos + [d1], [6] + pesos)
    return f"{d1}{d2}"


def _formatar(numeros: str, tipo: str) -> str:
    if tipo == "CPF":
        return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
    return f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"


def validar_cnpj_cpf(documento: str) -> dict:
    """Confere formato e digitos verificadores de um CPF (11) ou CNPJ (14)."""
    numeros = re.sub(r"\D", "", documento)

    if len(numeros) == 11:
        tipo = "CPF"
    elif len(numeros) == 14:
        tipo = "CNPJ"
    else:
        return {
            "tipo": "desconhecido",
            "documento": documento,
            "valido": False,
            "motivo": f"Quantidade de dígitos inválida ({len(numeros)}); esperado 11 (CPF) ou 14 (CNPJ).",
        }

    formatado = _formatar(numeros, tipo)

    if len(set(numeros)) == 1:
        return {
            "tipo": tipo,
            "documento": formatado,
            "valido": False,
            "motivo": "Todos os dígitos são iguais.",
        }

    base = [int(c) for c in numeros[:-2]]
    esperado = _dv_cpf(base) if tipo == "CPF" else _dv_cnpj(base)
    informado = numeros[-2:]

    if esperado == informado:
        return {"tipo": tipo, "documento": formatado, "valido": True, "motivo": "Dígitos verificadores corretos."}

    return {
        "tipo": tipo,
        "documento": formatado,
        "valido": False,
        "motivo": (
            f"Dígitos verificadores incorretos (informado {informado}, esperado {esperado}). "
            "Pode ser erro de leitura da imagem ou documento inválido."
        ),
        "digitos_esperados": esperado,
    }


def _dinheiro(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def conferir_soma(
    quantidades: list[float],
    precos_unitarios: list[float],
    total_declarado: float,
    ajustes: float = 0.0,
) -> dict:
    """Soma quantidade x preco de cada item e compara com o total da nota."""
    if len(quantidades) != len(precos_unitarios):
        return {"erro": "As listas de quantidades e preços unitários têm tamanhos diferentes."}

    subtotais = [
        _dinheiro(float(q) * float(p)) for q, p in zip(quantidades, precos_unitarios)
    ]
    soma_itens = sum(subtotais, Decimal("0.00"))
    esperado = soma_itens + _dinheiro(ajustes)
    declarado = _dinheiro(total_declarado)
    diferenca = declarado - esperado

    return {
        "subtotais": [float(s) for s in subtotais],
        "soma_itens": float(soma_itens),
        "ajustes": float(_dinheiro(ajustes)),
        "total_esperado": float(esperado),
        "total_declarado": float(declarado),
        "diferenca": float(diferenca),
        "confere": abs(diferenca) <= _CENTAVO,
        "observacao": (
            "Frete, impostos e descontos fora dos itens devem ser informados em 'ajustes'."
        ),
    }
