import re
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from src.core.contracts import RegistroConversa
from src.integrations.email import enviar_email

NOME_SISTEMA = "OmniAssistant"
FUSO = ZoneInfo("America/Sao_Paulo")
ROTULO_RISCO = {
    "verde": ("🟢 Baixo", "#1e8e3e"),
    "amarelo": ("🟡 Atenção", "#b06000"),
    "vermelho": ("🔴 Alto", "#c5221f"),
}
RISCO_PADRAO = ("Não avaliado", "#5f6368")

_NEGRITO = re.compile(r"\*\*(.+?)\*\*")
_CODIGO = re.compile(r"`([^`]+)`")
_ITEM = re.compile(r"^\s*[*\-]\s+(.*)$")


def validar_registro(registro: RegistroConversa, exigir_email: bool = True) -> None:
    if exigir_email and not registro.destinatario_email:
        raise ValueError("Informe e confirme um destinatário de e-mail.")
    if registro.risco == "vermelho":
        raise ValueError("Operação bloqueada: a análise possui risco vermelho.")


def _inline_html(texto: str) -> str:
    t = escape(texto)
    t = _NEGRITO.sub(r"<b>\1</b>", t)
    t = _CODIGO.sub(r'<code style="background:#f1f3f4;padding:1px 4px;border-radius:3px">\1</code>', t)
    return t


def _markdown_para_html(texto: str) -> str:
    """Converte o Markdown simples do resumo (parágrafos, listas, negrito, código) em HTML."""
    blocos, paragrafo, itens = [], [], []

    def fechar_paragrafo():
        if paragrafo:
            blocos.append(f"<p>{_inline_html(' '.join(paragrafo))}</p>")
            paragrafo.clear()

    def fechar_lista():
        if itens:
            blocos.append("<ul>" + "".join(f"<li>{_inline_html(i)}</li>" for i in itens) + "</ul>")
            itens.clear()

    for linha in texto.splitlines():
        item = _ITEM.match(linha)
        if item:
            fechar_paragrafo()
            itens.append(item.group(1))
        elif not linha.strip():
            fechar_paragrafo()
            fechar_lista()
        else:
            fechar_lista()
            paragrafo.append(linha.strip())
    fechar_paragrafo()
    fechar_lista()
    return "\n".join(blocos)


def _markdown_para_texto(texto: str) -> str:
    t = _NEGRITO.sub(r"\1", texto)
    t = _CODIGO.sub(r"\1", t)
    return re.sub(r"^(\s*)\*\s+", r"\1- ", t, flags=re.M)


def montar_email(registro: RegistroConversa) -> dict:
    """Gera assunto, corpo em texto e corpo em HTML no formato padrão."""
    nota = str(registro.numero_nota) if registro.numero_nota else None
    operacao = str(registro.id_operacao)
    data = datetime.now(FUSO).strftime("%d/%m/%Y %H:%M")
    risco_txt, risco_cor = ROTULO_RISCO.get(registro.risco or "", RISCO_PADRAO)
    pendencias = list(registro.pendencias or [])
    resumo = (registro.resumo or "").strip()

    assunto = f"[{NOME_SISTEMA}] Análise {nota or operacao[:8]}"
    if pendencias:
        assunto += f" — {len(pendencias)} pendência(s)"

    # Texto puro (fallback)
    cabecalho = ([f"Nota       : {nota}"] if nota else []) + [
        f"Operação   : {operacao}",
        f"Data       : {data}",
        f"Risco      : {risco_txt}",
    ]
    linhas = [
        f"{NOME_SISTEMA} — Relatório de análise",
        "=" * 40,
        *cabecalho,
        "",
        "RESUMO",
        "-" * 40,
        _markdown_para_texto(resumo),
        "",
        "PENDÊNCIAS",
        "-" * 40,
        *([f"- {p}" for p in pendencias] or ["Nenhuma pendência."]),
        "",
        "—",
        f"Mensagem automática gerada pelo {NOME_SISTEMA}. Não responda este e-mail.",
    ]
    corpo = "\n".join(linhas)

    # HTML
    td = 'style="padding:2px 12px 2px 0"'
    linha_nota = f"<tr><td {td}><b>Nota</b></td><td>{escape(nota)}</td></tr>" if nota else ""
    pend_html = (
        "<ul>" + "".join(f"<li>{_inline_html(p)}</li>" for p in pendencias) + "</ul>"
        if pendencias
        else "<p style='color:#5f6368'>Nenhuma pendência.</p>"
    )
    html = f"""\
<html><body style="font-family:Arial,sans-serif;color:#202124;max-width:600px;line-height:1.5">
  <h2 style="margin-bottom:4px">{NOME_SISTEMA}</h2>
  <p style="margin-top:0;color:#5f6368">Relatório de análise</p>
  <table style="border-collapse:collapse;font-size:14px">
    {linha_nota}
    <tr><td {td}><b>Operação</b></td><td style="font-family:monospace;font-size:12px">{escape(operacao)}</td></tr>
    <tr><td {td}><b>Data</b></td><td>{data}</td></tr>
    <tr><td {td}><b>Risco</b></td><td style="color:{risco_cor};font-weight:bold">{risco_txt}</td></tr>
  </table>
  <h3>Resumo</h3>
  {_markdown_para_html(resumo)}
  <h3>Pendências</h3>
  {pend_html}
  <hr style="border:none;border-top:1px solid #dadce0">
  <p style="font-size:12px;color:#5f6368">Mensagem automática gerada pelo {NOME_SISTEMA}. Não responda este e-mail.</p>
</body></html>"""

    return {"assunto": assunto, "corpo": corpo, "html": html}


def finalizar_registro(
    registro: RegistroConversa,
    enviar: bool = True,
    email_sender=enviar_email,
) -> dict:
    validar_registro(registro, exigir_email=enviar)
    resultado = {"id_operacao": registro.id_operacao, "email": None}
    if enviar:
        email = montar_email(registro)
        resultado["email"] = email_sender(
            registro.destinatario_email or "",
            email["assunto"],
            email["corpo"],
            html=email["html"],
        )
    return resultado