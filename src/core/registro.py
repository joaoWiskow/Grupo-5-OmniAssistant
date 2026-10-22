import re
import uuid

from src.core.contracts import EvidenciaMultimodal, ItemRegistro, RegistroConversa

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
NOTA_RE = re.compile(r"\b(?:NF[- ]?)?\d{3,}\b", re.IGNORECASE)
VALOR_RE = re.compile(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:[.,]\d{2}))")


def extrair_registro(
    pergunta: str,
    resposta: str,
    evidencias: list[EvidenciaMultimodal],
    risco: dict | None = None,
) -> RegistroConversa:
    """Cria um rascunho editável; a confirmação humana é obrigatória antes de enviar."""
    texto = "\n".join([pergunta, resposta, *(e.resumo_informacao for e in evidencias)])
    email = next(iter(EMAIL_RE.findall(texto)), None)
    nota = next(iter(NOTA_RE.findall(texto)), None)
    valores = [_brl(v) for v in VALOR_RE.findall(texto)]
    total = valores[-1] if valores else None
    nivel = (risco or {}).get("nivel", "neutro")
    return RegistroConversa(
        id_operacao=uuid.uuid4().hex,
        destinatario_email=email,
        numero_nota=nota,
        total=total,
        risco=nivel if nivel in {"neutro", "verde", "amarelo", "vermelho"} else "neutro",
        resumo=resposta,
        pendencias=["Destinatário de e-mail não encontrado na conversa."] if not email else [],
    )


def _brl(valor: str) -> float:
    return float(valor.replace(".", "").replace(",", "."))
