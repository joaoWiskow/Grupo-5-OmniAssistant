"""Integração: persistência de usuários, blindagem SQL e token unificado UI/backend."""

import pytest

from src.core.auth import (
    contexto_backend,
    despachar_tool_autenticado,
    emitir_token_sessao,
    limpar_estado_auth,
    listar_usuarios,
)
from src.core.auth_ui import gerar_token_sessao
from src.core.contracts import ContextoAutenticacao, PapelUsuario, Usuario
from src.tools.dados import (
    consultar_banco,
    descrever_banco,
    esquema_para_prompt,
    inicializar_dados,
)
from src.tools.local import inicializar_banco


@pytest.fixture(autouse=True)
def banco_pronto():
    limpar_estado_auth()
    inicializar_banco()
    inicializar_dados()
    yield
    limpar_estado_auth()


def _contexto(papel: PapelUsuario) -> ContextoAutenticacao:
    usuario = Usuario(
        id=f"usr-teste-{papel.value.lower()}",
        nome="Usuário de Teste",
        email=f"{papel.value.lower()}@omni.ia",
        papel=papel,
    )
    return ContextoAutenticacao(
        usuario=usuario, token=emitir_token_sessao(usuario.id, papel)
    )


def test_usuarios_persistidos_no_sqlite():
    emails = {u.email for u in listar_usuarios()}
    assert {
        "admin@omni.ia",
        "gestor@omni.ia",
        "analista@omni.ia",
        "auditor@omni.ia",
    } <= emails


def test_tabela_usuarios_inacessivel_ate_para_admin():
    with contexto_backend(_contexto(PapelUsuario.ADMIN)):
        resultado = consultar_banco("SELECT * FROM usuarios")
        catalogo = consultar_banco("SELECT name FROM sqlite_master")
    assert "erro" in resultado
    assert "erro" in catalogo


def test_clientes_bloqueado_para_analista_e_liberado_para_gestor():
    with contexto_backend(_contexto(PapelUsuario.ANALISTA)):
        negado = consultar_banco("SELECT COUNT(*) FROM clientes")
    with contexto_backend(_contexto(PapelUsuario.GESTOR)):
        permitido = consultar_banco("SELECT COUNT(*) FROM clientes")

    assert "erro" in negado
    assert "erro" not in permitido


def test_esquema_nao_expoe_usuarios_e_oculta_clientes_do_analista():
    esquema = esquema_para_prompt(PapelUsuario.ANALISTA)
    descricao = descrever_banco(papel=PapelUsuario.ANALISTA)

    assert "usuarios" not in esquema
    assert "clientes" not in esquema
    assert all(t["tabela"] != "usuarios" for t in descricao["tabelas"])


def test_token_da_ui_aceito_pelo_backend():
    token = gerar_token_sessao("usr-gst-001", PapelUsuario.GESTOR)

    resultado = despachar_tool_autenticado(
        "consultar_item", {"codigo": "N101"}, token=token
    )

    assert resultado.get("status_code") != 401
    assert resultado.get("autorizado") is not False


def test_token_propaga_papel_para_blindagem_sql():
    gestor = emitir_token_sessao("usr-gst-002", PapelUsuario.GESTOR).token
    analista = emitir_token_sessao("usr-anl-003", PapelUsuario.ANALISTA).token

    assert "erro" not in despachar_tool_autenticado(
        "consultar_banco", {"sql": "SELECT COUNT(*) FROM clientes"}, token=gestor
    )
    assert "erro" in despachar_tool_autenticado(
        "consultar_banco", {"sql": "SELECT COUNT(*) FROM clientes"}, token=analista
    )
    assert "erro" in despachar_tool_autenticado(
        "consultar_banco", {"sql": "SELECT * FROM usuarios"}, token=gestor
    )


def _conversar_com_tool_call(*_args, **_kwargs):
    """Primeira chamada pede a ferramenta; a segunda encerra o loop."""
    if not _conversar_com_tool_call.chamou:
        _conversar_com_tool_call.chamou = True
        return {
            "tool_call": {"name": "consultar_item", "arguments": {"codigo": "N101"}}
        }
    return {"texto": "Concluído."}


def test_agente_bloqueia_ferramenta_sem_autenticacao(monkeypatch):
    import src.core.agent as agente

    _conversar_com_tool_call.chamou = False
    monkeypatch.setattr(agente, "conversar", _conversar_com_tool_call)

    resultado = agente.executar_agente("Consulte o item N101", [])

    assert resultado["rastro_ferramentas"][0]["resultado"]["status_code"] == 401


def test_agente_autoriza_ferramenta_com_token(monkeypatch):
    import src.core.agent as agente

    _conversar_com_tool_call.chamou = False
    monkeypatch.setattr(agente, "conversar", _conversar_com_tool_call)
    token = emitir_token_sessao("usr-gst-002", PapelUsuario.GESTOR).token

    resultado = agente.executar_agente("Consulte o item N101", [], token=token)

    ferramenta = resultado["rastro_ferramentas"][0]["resultado"]
    assert ferramenta.get("status_code") != 401
    assert "erro" not in ferramenta
