from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from src.core.contracts import (
    ContratoBase,
    CredenciaisLogin,
    ContextoAutenticacao,
    EntradaUsuario,
    EvidenciaMultimodal,
    PapelUsuario,
    Permissao,
    PERMISSOES_PADRAO,
    RequisicaoLogin,
    RequisicaoRevogacaoToken,
    RequisicaoValidacaoPermissao,
    RequisicaoVerificacaoToken,
    RespostaLogin,
    RespostaRevogacaoToken,
    RespostaValidacaoPermissao,
    RespostaVerificacaoToken,
    SegmentoFala,
    TokenSessao,
    Usuario,
)


# ---------------------------------------------------------------------------
# TESTES: PAPEL E PERMISSÕES RBAC
# ---------------------------------------------------------------------------


def test_papeis_usuario_valores():
    assert PapelUsuario.ADMIN == "ADMIN"
    assert PapelUsuario.GESTOR == "GESTOR"
    assert PapelUsuario.ANALISTA == "ANALISTA"
    assert PapelUsuario.AUDITOR == "AUDITOR"
    assert set(p.value for p in PapelUsuario) == {"ADMIN", "GESTOR", "ANALISTA", "AUDITOR"}


def test_permissoes_padrao_por_papel():
    admin_perms = PERMISSOES_PADRAO[PapelUsuario.ADMIN]
    gestor_perms = PERMISSOES_PADRAO[PapelUsuario.GESTOR]
    analista_perms = PERMISSOES_PADRAO[PapelUsuario.ANALISTA]
    auditor_perms = PERMISSOES_PADRAO[PapelUsuario.AUDITOR]

    assert Permissao.USUARIOS_GERENCIAR.value in admin_perms
    assert Permissao.CONFIGURACAO_EDITAR.value in admin_perms
    assert Permissao.TRIAGEM_APROVAR.value in gestor_perms
    assert Permissao.USUARIOS_GERENCIAR.value not in gestor_perms
    assert Permissao.TRIAGEM_EXECUTAR.value in analista_perms
    assert Permissao.TRIAGEM_APROVAR.value not in analista_perms
    assert Permissao.AUDITORIA_VISUALIZAR.value in auditor_perms
    assert Permissao.TRIAGEM_EXECUTAR.value not in auditor_perms


# ---------------------------------------------------------------------------
# TESTES: ENTIDADE USUARIO
# ---------------------------------------------------------------------------


def test_usuario_valido():
    u = Usuario(
        id="usr-01",
        nome="  Maria Souza  ",
        email="Maria.Souza@Empresa.COM  ",
        papel=PapelUsuario.ANALISTA,
        ativo=True,
    )
    assert u.id == "usr-01"
    assert u.nome == "Maria Souza"
    assert u.email == "maria.souza@empresa.com"
    assert u.papel == PapelUsuario.ANALISTA
    assert u.ativo is True


def test_usuario_email_invalido():
    with pytest.raises(ValidationError):
        Usuario(
            id="usr-01",
            nome="Maria Souza",
            email="email_invalido_sem_arroba",
            papel=PapelUsuario.ANALISTA,
        )


def test_usuario_nome_vazio_ou_espacos():
    with pytest.raises(ValidationError):
        Usuario(
            id="usr-01",
            nome="    ",
            email="maria@empresa.com",
            papel=PapelUsuario.ANALISTA,
        )


def test_usuario_rejeita_campos_extras():
    with pytest.raises(ValidationError) as exc:
        Usuario(
            id="usr-01",
            nome="Maria Souza",
            email="maria@empresa.com",
            papel=PapelUsuario.ANALISTA,
            campo_injetado="hacker",
        )
    assert "extra_forbidden" in str(exc.value) or "Extra inputs are not permitted" in str(exc.value)


# ---------------------------------------------------------------------------
# TESTES: CREDENCIAIS LOGIN
# ---------------------------------------------------------------------------


def test_credenciais_login_validas():
    cred = CredenciaisLogin(identificador="  maria@empresa.com  ", segredo="SenhaForte123!")
    assert cred.identificador == "maria@empresa.com"
    assert cred.segredo == "SenhaForte123!"


def test_credenciais_login_segredo_invalido():
    with pytest.raises(ValidationError):
        CredenciaisLogin(identificador="maria", segredo="123")  # min 6 chars

    with pytest.raises(ValidationError):
        CredenciaisLogin(identificador="maria", segredo="      ")  # whitespace only


# ---------------------------------------------------------------------------
# TESTES: TOKEN DE SESSAO
# ---------------------------------------------------------------------------


def test_token_sessao_valido():
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(hours=2)
    tok = TokenSessao(
        token="token_criptografico_seguro_12345",
        usuario_id="usr-01",
        papel=PapelUsuario.GESTOR,
        expira_em=expira,
        emitido_em=agora,
    )
    assert tok.usuario_id == "usr-01"
    assert tok.papel == PapelUsuario.GESTOR
    assert not tok.esta_expirado()
    assert tok.segundos_restantes() > 7000


def test_token_sessao_expiracao_cronologica_invalida():
    agora = datetime.now(timezone.utc)
    with pytest.raises(ValidationError) as exc:
        TokenSessao(
            token="token_criptografico_seguro_12345",
            usuario_id="usr-01",
            papel=PapelUsuario.GESTOR,
            expira_em=agora - timedelta(minutes=10),
            emitido_em=agora,
        )
    assert "expiração deve ser estritamente posterior" in str(exc.value)


def test_token_sessao_normalizacao_naive_datetime():
    # Passando datetimes sem tzinfo (naive) deve forçar UTC
    naive_emitido = datetime(2026, 10, 22, 10, 0, 0)
    naive_expira = datetime(2026, 10, 22, 12, 0, 0)
    tok = TokenSessao(
        token="token_criptografico_seguro_12345",
        usuario_id="usr-01",
        papel=PapelUsuario.GESTOR,
        emitido_em=naive_emitido,
        expira_em=naive_expira,
    )
    assert tok.emitido_em.tzinfo == timezone.utc
    assert tok.expira_em.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# TESTES: CONTEXTO DE AUTENTICACAO
# ---------------------------------------------------------------------------


def test_contexto_autenticacao_sucesso_auto_permissoes():
    agora = datetime.now(timezone.utc)
    u = Usuario(
        id="usr-auditor",
        nome="Lucas Auditor",
        email="lucas@auditoria.com",
        papel=PapelUsuario.AUDITOR,
    )
    t = TokenSessao(
        token="token_super_seguro_auditor_999",
        usuario_id="usr-auditor",
        papel=PapelUsuario.AUDITOR,
        expira_em=agora + timedelta(hours=1),
    )
    ctx = ContextoAutenticacao(usuario=u, token=t)

    assert ctx.possui_permissao(Permissao.AUDITORIA_VISUALIZAR) is True
    assert ctx.possui_permissao("banco:consultar") is True
    assert ctx.possui_permissao(Permissao.TRIAGEM_APROVAR) is False
    assert ctx.possui_papel(PapelUsuario.AUDITOR) is True
    assert ctx.possui_papel(PapelUsuario.ADMIN) is False


def test_contexto_autenticacao_divergencia_usuario_id():
    agora = datetime.now(timezone.utc)
    u = Usuario(
        id="usr-01",
        nome="Carlos",
        email="carlos@empresa.com",
        papel=PapelUsuario.ANALISTA,
    )
    t = TokenSessao(
        token="token_super_seguro_123456",
        usuario_id="usr-99_divergente",
        papel=PapelUsuario.ANALISTA,
        expira_em=agora + timedelta(hours=1),
    )
    with pytest.raises(ValidationError) as exc:
        ContextoAutenticacao(usuario=u, token=t)
    assert "usuario_id inconsistente" in str(exc.value)


def test_contexto_autenticacao_divergencia_papel():
    agora = datetime.now(timezone.utc)
    u = Usuario(
        id="usr-01",
        nome="Carlos",
        email="carlos@empresa.com",
        papel=PapelUsuario.ANALISTA,
    )
    t = TokenSessao(
        token="token_super_seguro_123456",
        usuario_id="usr-01",
        papel=PapelUsuario.ADMIN,
        expira_em=agora + timedelta(hours=1),
    )
    with pytest.raises(ValidationError) as exc:
        ContextoAutenticacao(usuario=u, token=t)
    assert "Papel inconsistente" in str(exc.value)


def test_contexto_autenticacao_usuario_inativo():
    agora = datetime.now(timezone.utc)
    u = Usuario(
        id="usr-01",
        nome="Carlos",
        email="carlos@empresa.com",
        papel=PapelUsuario.ANALISTA,
        ativo=False,
    )
    t = TokenSessao(
        token="token_super_seguro_123456",
        usuario_id="usr-01",
        papel=PapelUsuario.ANALISTA,
        expira_em=agora + timedelta(hours=1),
    )
    with pytest.raises(ValidationError) as exc:
        ContextoAutenticacao(usuario=u, token=t)
    assert "Usuário desativado não pode compor contexto" in str(exc.value)


# ---------------------------------------------------------------------------
# TESTES: ESQUEMAS DE API (REQUEST / RESPONSE)
# ---------------------------------------------------------------------------


def test_ciclo_api_login():
    req = RequisicaoLogin(identificador="admin@omni.ia", segredo="SenhaAdminMaster#1")
    assert req.identificador == "admin@omni.ia"

    u = Usuario(
        id="adm-1",
        nome="Root Admin",
        email="admin@omni.ia",
        papel=PapelUsuario.ADMIN,
    )
    tok = TokenSessao(
        token="jwt_simulado_super_seguro_token",
        usuario_id="adm-1",
        papel=PapelUsuario.ADMIN,
        expira_em=datetime.now(timezone.utc) + timedelta(hours=8),
    )
    ctx = ContextoAutenticacao(usuario=u, token=tok)

    resp = RespostaLogin(sucesso=True, mensagem="Login autorizado.", token=tok, contexto=ctx)
    json_str = resp.model_dump_json()

    # Desserializacao estrita de volta
    restaurado = RespostaLogin.model_validate_json(json_str)
    assert restaurado.sucesso is True
    assert restaurado.contexto.usuario.papel == PapelUsuario.ADMIN


def test_api_verificacao_token():
    req = RequisicaoVerificacaoToken(token="jwt_simulado_super_seguro_token")
    resp_ok = RespostaVerificacaoToken(
        valido=True,
        usuario_id="usr-01",
        papel=PapelUsuario.ANALISTA,
        expirado=False,
        mensagem="Sessao ativa",
    )
    assert resp_ok.valido is True

    resp_expirado = RespostaVerificacaoToken(
        valido=False,
        expirado=True,
        mensagem="Sessao expirada",
    )
    assert resp_expirado.valido is False
    assert resp_expirado.expirado is True


def test_api_validacao_permissao():
    req = RequisicaoValidacaoPermissao(
        token="token_valido_gestor_123",
        permissao_requerida="triagem:aprovar",
        recurso_alvo="lote_502",
    )
    resp = RespostaValidacaoPermissao(
        autorizado=True,
        usuario_id="gest-01",
        papel=PapelUsuario.GESTOR,
        permissao="triagem:aprovar",
        motivo="Permissao inerente ao papel GESTOR",
    )
    assert resp.autorizado is True
    assert resp.permissao == "triagem:aprovar"


def test_api_revogacao_token():
    req = RequisicaoRevogacaoToken(
        token="token_valido_gestor_123", motivo="Logout solicitado pelo usuario"
    )
    resp = RespostaRevogacaoToken(revogado=True, mensagem="Sessao revogada com sucesso.")
    assert resp.revogado is True


# ---------------------------------------------------------------------------
# TESTES: COMPATIBILIDADE RETROATIVA DOS CONTRATOS MULTIMODAIS
# ---------------------------------------------------------------------------


def test_retrocompatibilidade_entrada_usuario():
    # Chamada legado (sem usuario_id)
    e1 = EntradaUsuario(tipo="texto", texto_comando="Auditar nota 101")
    assert e1.usuario_id is None
    assert e1.tipo == "texto"

    # Chamada moderna (com usuario_id de auditoria)
    e2 = EntradaUsuario(tipo="texto", texto_comando="Auditar nota 101", usuario_id="usr-42")
    assert e2.usuario_id == "usr-42"


def test_retrocompatibilidade_evidencia_multimodal():
    # Chamada legado (sem autor_usuario_id)
    ev1 = EvidenciaMultimodal(origem="texto", resumo_informacao="Nota emitida em SP")
    assert ev1.autor_usuario_id is None

    # Chamada moderna com autor
    ev2 = EvidenciaMultimodal(
        origem="texto",
        resumo_informacao="Nota emitida em SP",
        autor_usuario_id="usr-42",
    )
    assert ev2.autor_usuario_id == "usr-42"


# ---------------------------------------------------------------------------
# TESTES: VALIDAÇÃO CRIPTOGRÁFICA, TAMPERING E EXPIRAÇÃO DE TOKENS
# ---------------------------------------------------------------------------


def test_token_sessao_expiracao_metodos_avaliacao():
    agora = datetime.now(timezone.utc)
    exp = agora + timedelta(seconds=120)
    tok = TokenSessao(
        token="token_para_teste_temporal_12345",
        usuario_id="usr-temp",
        papel=PapelUsuario.ANALISTA,
        emitido_em=agora,
        expira_em=exp,
    )
    # Antes de expirar
    assert tok.esta_expirado(agora + timedelta(seconds=60)) is False
    assert tok.segundos_restantes(agora + timedelta(seconds=60)) == pytest.approx(60.0, 1.0)

    # Exatamente no momento de expiração
    assert tok.esta_expirado(exp) is True
    assert tok.segundos_restantes(exp) == 0.0

    # Após expirar
    assert tok.esta_expirado(agora + timedelta(seconds=300)) is True
    assert tok.segundos_restantes(agora + timedelta(seconds=300)) == 0.0


def test_contexto_autenticacao_metodos_permissao():
    u = Usuario(
        id="usr-gst",
        nome="Gestor Teste",
        email="gestor@empresa.com",
        papel=PapelUsuario.GESTOR,
    )
    t = TokenSessao(
        token="token_gestor_metodos_12345",
        usuario_id="usr-gst",
        papel=PapelUsuario.GESTOR,
        expira_em=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    ctx = ContextoAutenticacao(usuario=u, token=t)

    # possui_todas_permissoes
    assert ctx.possui_todas_permissoes(Permissao.TRIAGEM_EXECUTAR, Permissao.TRIAGEM_APROVAR) is True
    assert ctx.possui_todas_permissoes(Permissao.TRIAGEM_EXECUTAR, Permissao.USUARIOS_GERENCIAR) is False

    # possui_qualquer_permissao
    assert ctx.possui_qualquer_permissao(Permissao.USUARIOS_GERENCIAR, Permissao.TRIAGEM_APROVAR) is True
    assert ctx.possui_qualquer_permissao("permissao:inexistente", "outra:falsa") is False


def test_validacao_token_criptografico_integridade_e_tampering():
    from src.core.auth import emitir_token_sessao, validar_token_sessao

    tok = emitir_token_sessao("usr-anl-003", PapelUsuario.ANALISTA, duracao_segundos=1800)
    assert tok.token.startswith("omni_")

    # 1. Validação com token autêntico
    val = validar_token_sessao(tok.token)
    assert val.valido is True
    assert val.usuario_id == "usr-anl-003"
    assert val.papel == PapelUsuario.ANALISTA
    assert val.expirado is False

    # 2. Tampering: adulteração da assinatura final
    token_forjado = tok.token[:-5] + "99999"
    val_forjado = validar_token_sessao(token_forjado)
    assert val_forjado.valido is False
    assert "Assinatura forjada" in val_forjado.mensagem

    # 3. Tampering: alteração do papel no corpo (elevação de privilégio para ADMIN)
    prefixo, rest = tok.token.split(":", 1)
    corpo, sig = tok.token[5:].rsplit(":", 1)
    partes = corpo.split(":")
    partes[1] = PapelUsuario.ADMIN.value
    corpo_adulterado = ":".join(partes)
    token_papel_adulterado = f"omni_{corpo_adulterado}:{sig}"
    val_papel = validar_token_sessao(token_papel_adulterado)
    assert val_papel.valido is False
    assert "Assinatura forjada" in val_papel.mensagem

    # 4. Token com prefixo inválido ou ausente
    assert validar_token_sessao("jwt.invalido.sem_prefixo").valido is False
    assert validar_token_sessao(None).valido is False
    assert validar_token_sessao("").valido is False


def test_validacao_token_expirado_temporalmente(monkeypatch):
    from src.core.auth import emitir_token_sessao, validar_token_sessao

    # Emite um token válido por 1 segundo
    tok = emitir_token_sessao("usr-exp-01", PapelUsuario.GESTOR, duracao_segundos=1)
    
    # Simula passagem de tempo para o futuro além da expiração
    futuro_utc = datetime.now(timezone.utc) + timedelta(seconds=100)
    
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return futuro_utc

    monkeypatch.setattr("src.core.auth.datetime", FakeDatetime)
    val = validar_token_sessao(tok.token)
    assert val.valido is False
    assert val.expirado is True
    assert "Token expirado" in val.mensagem


def test_revogacao_e_blacklist_token():
    from src.core.auth import emitir_token_sessao, validar_token_sessao, revogar_token_sessao

    tok = emitir_token_sessao("usr-rev-01", PapelUsuario.AUDITOR, duracao_segundos=3600)
    assert validar_token_sessao(tok.token).valido is True

    # Revoga
    resp = revogar_token_sessao(RequisicaoRevogacaoToken(token=tok.token, motivo="Sessao encerrada"))
    assert resp.revogado is True

    # Tenta reutilizar token revogado
    val_pos_revogacao = validar_token_sessao(tok.token)
    assert val_pos_revogacao.valido is False
    assert "revogada" in val_pos_revogacao.mensagem.lower()


def test_hash_senha_e_prevencao_timing():
    from src.core.auth import hashear_senha, verificar_senha

    h1, s1 = hashear_senha("MinhaSenhaForte2026")
    h2, s2 = hashear_senha("MinhaSenhaForte2026")

    # Salting aleatório garante hashes diferentes para senhas iguais
    assert s1 != s2
    assert h1 != h2

    # Verificação de senha
    assert verificar_senha("MinhaSenhaForte2026", s1, h1) is True
    assert verificar_senha("SenhaIncorreta", s1, h1) is False

