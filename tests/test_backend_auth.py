"""Testes de Integração de Autenticação e RBAC no Backend OmniAssistant.

Cobre:
- Propagação de contexto de segurança nas threads/chamadas do backend.
- Bloqueio estrito de chamadas anônimas em ferramentas do sistema.
- Controle de acesso baseado em função (RBAC) em nível de ferramenta (consultar_banco, consultar_item).
- Rejeição de tokens expirados, forjados e revogados.
- Propagação de cabeçalho de autorização para o cliente Colab NLP.
- Defesa em profundidade: Bloqueio na autenticação antes de guardrails SQL.
- Registro completo da trilha de auditoria para operações permitidas e negadas.
- Ciclo de login com proteção contra ataques de força bruta.
"""

from datetime import datetime, timedelta, timezone
import pytest

from src.core import colab_nlp
from src.core.auth import (
    ContaBloqueadaError,
    CredenciaisInvalidasError,
    PERMISSOES_FERRAMENTAS,
    autenticar_usuario_backend,
    contexto_backend,
    despachar_tool_autenticado,
    emitir_token_sessao,
    limpar_estado_auth,
    obter_contexto_ativo,
    obter_trilha_auditoria_backend,
    revogar_token_sessao,
)
from src.core.contracts import (
    ContextoAutenticacao,
    PapelUsuario,
    Permissao,
    PERMISSOES_PADRAO,
    RequisicaoLogin,
    RequisicaoRevogacaoToken,
    TokenSessao,
    Usuario,
)


@pytest.fixture(autouse=True)
def resetar_ambiente_auth():
    """Garante isolamento de estado para cada teste."""
    limpar_estado_auth()
    yield
    limpar_estado_auth()


# ---------------------------------------------------------------------------
# 1. PROPAGAÇÃO DE CONTEXTO BACKEND
# ---------------------------------------------------------------------------


def test_contexto_backend_propagacao_e_ciclo_de_vida():
    assert obter_contexto_ativo() is None

    u = Usuario(
        id="usr-anl-01",
        nome="Analista Teste",
        email="analista@empresa.com",
        papel=PapelUsuario.ANALISTA,
    )
    tok = emitir_token_sessao(u.id, u.papel)
    ctx = ContextoAutenticacao(usuario=u, token=tok)

    with contexto_backend(ctx):
        ativo = obter_contexto_ativo()
        assert ativo is not None
        assert ativo.usuario.id == "usr-anl-01"
        assert ativo.possui_permissao(Permissao.TRIAGEM_EXECUTAR) is True

    # Ao sair do bloco de contexto, o estado anterior é restaurado
    assert obter_contexto_ativo() is None


# ---------------------------------------------------------------------------
# 2. BLOQUEIO DE CHAMADAS ANÔNIMAS E TOKENS INVÁLIDOS
# ---------------------------------------------------------------------------


def test_despacho_ferramenta_sem_autenticacao_rejeitado():
    # Nenhuma credencial ou contexto informado
    res = despachar_tool_autenticado("consultar_banco", {"sql": "SELECT 1"})
    assert res.get("autorizado") is False
    assert res.get("status_code") == 401
    assert "exige autenticação prévia" in res.get("erro", "")

    # Tentativa com ferramenta de catálogo
    res_item = despachar_tool_autenticado("consultar_item", {"codigo": "N101"})
    assert res_item.get("autorizado") is False
    assert res_item.get("status_code") == 401


def test_despacho_ferramenta_com_token_forjado():
    token_forjado = "omni_usr-hacker:ADMIN:1700000000:1800000000:nonce:assinatura_falsa_999"
    res = despachar_tool_autenticado(
        "consultar_banco", {"sql": "SELECT 1"}, token=token_forjado
    )
    assert res.get("autorizado") is False
    assert res.get("status_code") == 401
    assert "Assinatura forjada" in res.get("erro", "")


def test_despacho_ferramenta_com_token_revogado():
    tok = emitir_token_sessao("usr-anl-01", PapelUsuario.ANALISTA)
    revogar_token_sessao(RequisicaoRevogacaoToken(token=tok.token))

    res = despachar_tool_autenticado(
        "consultar_item", {"codigo": "N101"}, token=tok.token
    )
    assert res.get("autorizado") is False
    assert res.get("status_code") == 401
    assert "revogada" in res.get("erro", "").lower()


# ---------------------------------------------------------------------------
# 3. RBAC EM NÍVEL DE FERRAMENTA
# ---------------------------------------------------------------------------


def test_rbac_banco_consultar_permitido_para_gestor_e_admin():
    from src.tools.local import inicializar_banco
    inicializar_banco()

    # Gestor possui permissão 'banco:consultar'
    u_gestor = Usuario(
        id="usr-gst-01",
        nome="Gestora",
        email="gestora@omni.ia",
        papel=PapelUsuario.GESTOR,
    )
    tok_gestor = emitir_token_sessao(u_gestor.id, u_gestor.papel)
    ctx_gestor = ContextoAutenticacao(usuario=u_gestor, token=tok_gestor)

    res = despachar_tool_autenticado(
        "consultar_banco",
        {"sql": "SELECT COUNT(*) as total FROM itens"},
        contexto=ctx_gestor,
    )
    assert "colunas" in res or "linhas" in res or res.get("total_linhas") is not None
    assert "erro" not in res


def test_rbac_triagem_executar_bloqueado_para_auditor():
    # Auditor possui 'banco:consultar' e 'auditoria:visualizar', mas NÃO 'triagem:executar'
    u_auditor = Usuario(
        id="usr-aud-01",
        nome="Auditor Externo",
        email="auditor@omni.ia",
        papel=PapelUsuario.AUDITOR,
    )
    tok_auditor = emitir_token_sessao(u_auditor.id, u_auditor.papel)
    ctx_auditor = ContextoAutenticacao(usuario=u_auditor, token=tok_auditor)

    res = despachar_tool_autenticado(
        "consultar_item", {"codigo": "N101"}, contexto=ctx_auditor
    )
    assert res.get("autorizado") is False
    assert res.get("status_code") == 403
    assert res.get("permissao_requerida") == "triagem:executar"
    assert "não possui a permissão necessária" in res.get("erro", "")


def test_rbac_triagem_executar_permitido_para_analista():
    from src.tools.local import inicializar_banco
    inicializar_banco()

    u_analista = Usuario(
        id="usr-anl-02",
        nome="Analista Jr",
        email="analista@omni.ia",
        papel=PapelUsuario.ANALISTA,
    )
    tok_analista = emitir_token_sessao(u_analista.id, u_analista.papel)
    ctx_analista = ContextoAutenticacao(usuario=u_analista, token=tok_analista)

    res = despachar_tool_autenticado(
        "consultar_item", {"codigo": "N101"}, contexto=ctx_analista
    )
    assert res.get("encontrado") is True or "nome" in res
    assert "status_code" not in res


# ---------------------------------------------------------------------------
# 4. PROPAGAÇÃO DE TOKEN PARA CLIENTES EXTERNOS (COLAB NLP)
# ---------------------------------------------------------------------------


def test_colab_nlp_propagacao_token_cabecalho(monkeypatch):
    capturado = {}

    class RespostaFalsa:
        def raise_for_status(self):
            pass

        def json(self):
            return {"texto": "Resposta autenticada do modelo tributario."}

    def post_com_headers(url, json=None, headers=None, timeout=None):
        capturado.update(url=url, json=json, headers=headers, timeout=timeout)
        return RespostaFalsa()

    monkeypatch.setenv("COLAB_LLM_URL", "https://colab-teste.trycloudflare.com")
    monkeypatch.setattr(colab_nlp.requests, "post", post_com_headers)

    token_teste = "omni_usr-test:ANALISTA:17000:18000:nonce:sig"
    resp = colab_nlp.conversar(
        [{"role": "user", "content": "Calcular imposto"}],
        token=token_teste,
    )

    assert "texto" in resp
    assert capturado.get("headers") is not None
    assert capturado["headers"]["Authorization"] == f"Bearer {token_teste}"


def test_colab_nlp_tratamento_erro_401(monkeypatch):
    class Resposta401:
        status_code = 401
        text = "Unauthorized: Token de autorizacao invalido ou expirado no backend"

    def post_com_falha(*args, **kwargs):
        raise colab_nlp.requests.HTTPError(response=Resposta401())

    monkeypatch.setenv("COLAB_LLM_URL", "https://colab-teste.trycloudflare.com")
    monkeypatch.setattr(colab_nlp.requests, "post", post_com_falha)

    resp = colab_nlp.conversar(
        [{"role": "user", "content": "Verificar faturamento"}],
        token="token_invalido",
    )
    assert "erro" in resp
    assert "Colab respondeu HTTP 401" in resp["erro"]


# ---------------------------------------------------------------------------
# 5. DEFESA EM PROFUNDIDADE: SQL INJECTION + AUTORIZAÇÃO
# ---------------------------------------------------------------------------


def test_bloqueio_sql_injection_antes_do_banco_para_nao_autenticado():
    codigo_malicioso = "A101'; DROP TABLE itens; --"

    # 1. Sem autenticação: a tentativa é barrada na borda de auth (401), sem tocar o SQLite
    res_sem_auth = despachar_tool_autenticado("consultar_item", {"codigo": codigo_malicioso})
    assert res_sem_auth.get("status_code") == 401
    assert res_sem_auth.get("autorizado") is False

    # 2. Com autenticação válida: a consulta passa pelo auth mas é barrada pelo guardrail de input
    u_analista = Usuario(
        id="usr-anl-sec",
        nome="Analista",
        email="analista@empresa.com",
        papel=PapelUsuario.ANALISTA,
    )
    tok = emitir_token_sessao(u_analista.id, u_analista.papel)
    ctx = ContextoAutenticacao(usuario=u_analista, token=tok)

    res_com_auth = despachar_tool_autenticado(
        "consultar_item", {"codigo": codigo_malicioso}, contexto=ctx
    )
    # Deve ser sanitizado/rejeitado pelo guardrail da ferramenta
    assert res_com_auth.get("encontrado") is False or "erro" in res_com_auth


# ---------------------------------------------------------------------------
# 6. TRILHA DE AUDITORIA DE SEGURANÇA
# ---------------------------------------------------------------------------


def test_trilha_auditoria_backend_registro_operacoes():
    limpar_estado_auth()

    # Executa operação não autorizada
    despachar_tool_autenticado("consultar_banco", {"sql": "SELECT 1"})

    # Executa operação autorizada
    u = Usuario(
        id="usr-adm-aud",
        nome="Admin Auditor",
        email="admin@omni.ia",
        papel=PapelUsuario.ADMIN,
    )
    tok = emitir_token_sessao(u.id, u.papel)
    ctx = ContextoAutenticacao(usuario=u, token=tok)
    despachar_tool_autenticado("consultar_item", {"codigo": "N101"}, contexto=ctx)

    trilha = obter_trilha_auditoria_backend()
    assert len(trilha) >= 2

    # Evento de bloqueio
    evento_bloqueado = trilha[0]
    assert evento_bloqueado["permitido"] is False
    assert evento_bloqueado["usuario_id"] == "anonimo"

    # Evento de sucesso
    evento_permitido = trilha[1]
    assert evento_permitido["permitido"] is True
    assert evento_permitido["usuario_id"] == "usr-adm-aud"


# ---------------------------------------------------------------------------
# 7. CICLO DE LOGIN E PROTEÇÃO CONTRA FORÇA BRUTA NO BACKEND
# ---------------------------------------------------------------------------


def test_autenticacao_login_backend_sucesso():
    req = RequisicaoLogin(
        identificador="gestor@omni.ia", segredo="Gestor@Master2026"
    )
    resp = autenticar_usuario_backend(req)
    assert resp.sucesso is True
    assert resp.token is not None
    assert resp.contexto.usuario.papel == PapelUsuario.GESTOR


def test_autenticacao_login_bloqueio_forca_bruta():
    email = "gestor@omni.ia"

    # 4 falhas seguidas
    for _ in range(4):
        with pytest.raises(CredenciaisInvalidasError):
            autenticar_usuario_backend(
                RequisicaoLogin(identificador=email, segredo="SenhaErrada123")
            )

    # 5ª falha bloqueia a conta
    with pytest.raises(CredenciaisInvalidasError):
        autenticar_usuario_backend(
            RequisicaoLogin(identificador=email, segredo="SenhaErrada123")
        )

    # 6ª tentativa dispara ContaBloqueadaError, mesmo com a senha correta
    with pytest.raises(ContaBloqueadaError) as exc:
        autenticar_usuario_backend(
            RequisicaoLogin(identificador=email, segredo="Gestor@Master2026")
        )
    assert "bloqueada por excesso de tentativas" in str(exc.value)
