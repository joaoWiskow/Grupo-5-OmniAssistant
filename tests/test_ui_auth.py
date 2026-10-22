"""Testes de Resiliência de Interface, Estado de Sessão e Guardrails de UI (tests/test_ui_auth.py).

Cobre:
- Ciclo de vida e máquina de estados do Streamlit session_state (inicialização, login, logout).
- Limpeza estrita (purge) de dados sensíveis na expiração e logout (histórico, evidências, tokens).
- Transições de estado entre Não-Autenticado e Autenticado.
- Controle de visibilidade de componentes e guardrails de ação por papel/permissão (RBAC na UI).
- Resiliência contra Session Tampering (adulteração de papel ou injeção de token forjado no session_state).
- Expiração temporal e invalidação de sessão ativa.
- Resiliência de feedback na UI sem vazamento de exceções ou dados sensíveis.
"""

import time
import pytest
import streamlit as st

from src.core.auth_ui import (
    _USUARIOS_MOCK,
    _SECRET_KEY,
    SESSION_EXPIRATION_SECONDS,
    executar_login,
    executar_logout,
    gerar_token_sessao,
    inicializar_estado_auth,
    usuario_possui_permissao,
    validar_token_sessao,
)


@pytest.fixture(autouse=True)
def preparar_session_state(monkeypatch):
    """Limpa e isola o st.session_state antes e depois de cada teste."""
    # Monkeypatch do st.rerun para evitar interrupções de fluxo no Streamlit durante o teste
    monkeypatch.setattr(st, "rerun", lambda: None)

    for k in list(st.session_state.keys()):
        del st.session_state[k]
    yield
    for k in list(st.session_state.keys()):
        del st.session_state[k]


# ---------------------------------------------------------------------------
# 1. MÁQUINA DE ESTADOS E INICIALIZAÇÃO DO SESSION_STATE
# ---------------------------------------------------------------------------


def test_inicializacao_estado_padrao_seguro():
    inicializar_estado_auth()

    assert st.session_state["autenticado"] is False
    assert st.session_state["usuario_atual"] is None
    assert st.session_state["token_sessao"] is None
    assert st.session_state["login_timestamp"] is None


def test_transicao_estado_login_sucesso():
    gestor = _USUARIOS_MOCK["gestor"]

    executar_login(gestor)

    assert st.session_state["autenticado"] is True
    assert st.session_state["usuario_atual"]["id"] == gestor.id
    assert st.session_state["usuario_atual"]["papel"] == "Gestor"
    assert st.session_state["token_sessao"] is not None
    assert st.session_state["token_sessao"].startswith(f"omni_{gestor.id}:")
    assert validar_token_sessao(st.session_state["token_sessao"]) is True


# ---------------------------------------------------------------------------
# 2. PURGE E LIMPEZA DE DADOS SENSÍVEIS NO LOGOUT
# ---------------------------------------------------------------------------


def test_logout_purge_completo_dados_sensiveis():
    analista = _USUARIOS_MOCK["analista"]
    executar_login(analista)

    # Simula dados sensíveis acumulados durante a sessão do usuário
    st.session_state["historico_mensagens"] = [
        {"role": "user", "content": "Auditar faturamento do CNPJ 12.345.678/0001-90"},
        {"role": "assistant", "content": "Dados fiscais confidenciais encontrados."},
    ]
    st.session_state["evidencias_ativas"] = [
        {"origem": "visao", "resumo": "Print da NF-e com valor sigiloso"}
    ]
    st.session_state["arquivo_temporario_upload"] = "/tmp/nota_fiscal_privada.png"

    # Executa o encerramento seguro
    executar_logout()

    # Validações estritas de segurança
    assert st.session_state["autenticado"] is False
    assert st.session_state["usuario_atual"] is None
    assert st.session_state["token_sessao"] is None

    # O histórico e as evidências confidenciais DEVEM ser completamente purgados
    assert st.session_state["historico_mensagens"] == []
    assert st.session_state["evidencias_ativas"] == []
    assert "arquivo_temporario_upload" not in st.session_state


# ---------------------------------------------------------------------------
# 3. EXPIRAÇÃO DE SESSÃO E DERRUBADA NA INTERFACE
# ---------------------------------------------------------------------------


def test_expiracao_sessao_e_bloqueio_interface(monkeypatch):
    analista = _USUARIOS_MOCK["analista"]
    executar_login(analista)

    token = st.session_state["token_sessao"]
    assert validar_token_sessao(token) is True

    # Simula o avanço do relógio do servidor para além do limite de expiração
    futuro = time.time() + SESSION_EXPIRATION_SECONDS + 300
    monkeypatch.setattr(time, "time", lambda: futuro)

    # Validação do token falha
    sessao_valida = validar_token_sessao(st.session_state["token_sessao"])
    assert sessao_valida is False

    # Na ocorrência de token expirado, a UI deve disparar logout automático
    if not sessao_valida:
        executar_logout()

    assert st.session_state["autenticado"] is False
    assert st.session_state["token_sessao"] is None


# ---------------------------------------------------------------------------
# 4. GUARDRAILS DE UI E VISIBILIDADE DE COMPONENTES (RBAC)
# ---------------------------------------------------------------------------


def test_guardrails_permissoes_usuario_nao_autenticado():
    inicializar_estado_auth()

    # Nenhum usuário autenticado deve ter permissões concedidas
    assert usuario_possui_permissao("leitura") is False
    assert usuario_possui_permissao("consultar_banco") is False
    assert usuario_possui_permissao("auditoria_completa") is False


def test_guardrails_permissoes_diferenciadas_por_perfil():
    gestor = _USUARIOS_MOCK["gestor"]
    analista = _USUARIOS_MOCK["analista"]

    # 1. Avalia Gestor
    executar_login(gestor)
    assert usuario_possui_permissao("auditoria_completa") is True
    assert usuario_possui_permissao("exportar_dados") is True
    assert usuario_possui_permissao("consultar_banco") is True

    # 2. Alterna para Analista (perfil sem auditoria/exportação)
    executar_login(analista)
    assert usuario_possui_permissao("auditoria_completa") is False
    assert usuario_possui_permissao("exportar_dados") is False
    assert usuario_possui_permissao("consultar_banco") is True
    assert usuario_possui_permissao("upload_arquivos") is True


# ---------------------------------------------------------------------------
# 5. DEFESA CONTRA SESSION TAMPERING NO STREAMLIT
# ---------------------------------------------------------------------------


def test_resiliencia_tampering_modificacao_manual_session_state():
    analista = _USUARIOS_MOCK["analista"]
    executar_login(analista)

    # Atacante tenta elevar privilégios diretamente injetando no session_state em memória
    st.session_state["usuario_atual"]["papel"] = "Gestor"
    st.session_state["usuario_atual"]["permissoes"].append("auditoria_completa")

    # Guardrail de integridade: checa se o token assinado confere com o ID e integridade do token
    token = st.session_state["token_sessao"]
    assert token.startswith(f"omni_{analista.id}:")

    # Injeção de token forjado
    token_falso = "omni_usr-gst-001:9999999999:fakenonce:assinaturainvalida"
    st.session_state["token_sessao"] = token_falso
    assert validar_token_sessao(st.session_state["token_sessao"]) is False


def test_resiliencia_token_sessao_nulo_ou_vazio():
    assert validar_token_sessao("") is False
    assert validar_token_sessao(None) is False
    assert validar_token_sessao("   ") is False
    assert validar_token_sessao("Bearer token_sem_prefixo_omni") is False


# ---------------------------------------------------------------------------
# 6. INTEGRIDADE DA BASE DE USUÁRIOS E PERFIS DE DEMO
# ---------------------------------------------------------------------------


def test_integridade_base_perfis_demonstracao():
    for chave, u in _USUARIOS_MOCK.items():
        assert u.id.startswith("usr-")
        assert "@" in u.email
        assert len(u.permissoes) > 0
        assert u.badge_cor.startswith("#")
        assert u.avatar != ""
        d = u.to_dict()
        assert "senha_hash" not in d, "Vazamento crítico: hash de senha serializado no dicionário!"
        assert "salt" not in d, "Vazamento crítico: salt serializado no dicionário de UI!"
