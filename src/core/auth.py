"""Módulo Central de Autenticação, Autorização (RBAC) e Auditoria do Backend OmniAssistant."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Callable, Dict, Iterator, List, Optional

from dotenv import load_dotenv

from src.tools.local import DB_PATH

from src.core.contracts import (
    ContextoAutenticacao,
    CredenciaisLogin,
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
    TokenSessao,
    Usuario,
)

load_dotenv()


# ---------------------------------------------------------------------------
# Exceções Customizadas de Segurança
# ---------------------------------------------------------------------------
class AuthError(Exception):
    """Exceção base para falhas de autenticação e autorização."""

    status_code: int = 400


class TokenExpiradoError(AuthError):
    """Lançado quando o token de sessão ultrapassa seu limite de validade."""

    status_code: int = 401


class TokenInvalidoError(AuthError):
    """Lançado quando a assinatura do token é forjada, inválida ou malformada."""

    status_code: int = 401


class TokenNaoFornecidoError(AuthError):
    """Lançado quando uma operação restrita é chamada anonimamente."""

    status_code: int = 401


class TokenRevogadoError(AuthError):
    """Lançado quando o token foi invalidado explicitamente (logout/blacklisted)."""

    status_code: int = 401


class CredenciaisInvalidasError(AuthError):
    """Lançado em caso de identificador inexistente ou senha incorreta."""

    status_code: int = 401


class PermissaoNegadaError(AuthError):
    """Lançado quando o usuário autenticado não possui papel/permissão requerida."""

    status_code: int = 403


class ContaBloqueadaError(AuthError):
    """Lançado em caso de excesso de tentativas incorretas de autenticação."""

    status_code: int = 429


# ---------------------------------------------------------------------------
# Configuração de Assinatura e Mapeamentos RBAC
# ---------------------------------------------------------------------------
_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "omni-assistant-secret-key-auth-2026")
_DURACAO_PADRAO_SESSAO_S = 3600 * 8  # 8 horas
LIMITE_TENTATIVAS_LOGIN = 5
AUTH_ENFORCE = os.environ.get("AUTH_ENFORCE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

# Mapeamento estrito de ferramentas aos privilégios exigidos
PERMISSOES_FERRAMENTAS: dict[str, Permissao] = {
    "consultar_banco": Permissao.BANCO_CONSULTAR,
    "descrever_banco": Permissao.BANCO_CONSULTAR,
    "consultar_item": Permissao.TRIAGEM_EXECUTAR,
    "calcular_total": Permissao.TRIAGEM_EXECUTAR,
    "validar_codigo": Permissao.TRIAGEM_EXECUTAR,
    "validar_cnpj_cpf": Permissao.TRIAGEM_EXECUTAR,
    "conferir_soma": Permissao.TRIAGEM_EXECUTAR,
}

# ---------------------------------------------------------------------------
# Estado em Memória (Blacklist, Auditoria, Usuários e Tentativas)
# ---------------------------------------------------------------------------
_BLACKLIST_TOKENS: set[str] = set()
_TRILHA_AUDITORIA: list[dict[str, Any]] = []
_TENTATIVAS_FALHAS: dict[str, int] = {}


def limpar_estado_auth() -> None:
    """Limpa blacklist, histórico de auditoria e contadores de falhas."""
    _BLACKLIST_TOKENS.clear()
    _TRILHA_AUDITORIA.clear()
    _TENTATIVAS_FALHAS.clear()


# ---------------------------------------------------------------------------
# Hashing e Verificação de Senhas (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------
_ITERACOES_PBKDF2 = 200_000


def hashear_senha(senha: str, salt: str | None = None) -> tuple[str, str]:
    """Gera hash PBKDF2-HMAC-SHA256 com salt aleatório."""
    s = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), s.encode("utf-8"), _ITERACOES_PBKDF2
    ).hex()
    return h, s


def verificar_senha(senha: str, salt: str, hash_esperado: str) -> bool:
    """Validação de tempo constante para prevenir timing attacks."""
    h = hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), salt.encode("utf-8"), _ITERACOES_PBKDF2
    ).hex()
    return hmac.compare_digest(h, hash_esperado)


# ---------------------------------------------------------------------------
# Persistência de Usuários no SQLite (fonte da verdade)
# ---------------------------------------------------------------------------
def _caminho_banco() -> Path:
    env = os.getenv("OMNI_DB")
    return Path(env) if env else DB_PATH


_SEED_USUARIOS = [
    (
        "usr-adm-001",
        "Administrador Geral",
        "admin@omni.ia",
        PapelUsuario.ADMIN,
        "Admin@Master2026",
    ),
    (
        "usr-gst-002",
        "Gestora Financeira",
        "gestor@omni.ia",
        PapelUsuario.GESTOR,
        "Gestor@Master2026",
    ),
    (
        "usr-anl-003",
        "Analista de Triagem",
        "analista@omni.ia",
        PapelUsuario.ANALISTA,
        "Analista@Master2026",
    ),
    (
        "usr-aud-004",
        "Auditor Independente",
        "auditor@omni.ia",
        PapelUsuario.AUDITOR,
        "Auditor@Master2026",
    ),
]


def _conexao_usuarios() -> sqlite3.Connection:
    """Abre (e inicializa com seed) a tabela de usuários."""
    caminho = _caminho_banco()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            papel TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            senha_hash TEXT NOT NULL,
            salt TEXT NOT NULL
        )
        """
    )
    if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        linhas = []
        for uid, nome, email, papel, senha in _SEED_USUARIOS:
            h, s = hashear_senha(senha)
            linhas.append((uid, nome, email, papel.value, 1, h, s))
        con.executemany(
            "INSERT INTO usuarios (id, nome, email, papel, ativo, senha_hash, salt) "
            "VALUES (?,?,?,?,?,?,?)",
            linhas,
        )
        con.commit()
    return con


def listar_usuarios() -> list[Usuario]:
    """Retorna os usuários persistidos (sem hash/salt)."""
    con = _conexao_usuarios()
    try:
        linhas = con.execute(
            "SELECT id, nome, email, papel, ativo FROM usuarios ORDER BY id"
        ).fetchall()
    finally:
        con.close()
    return [
        Usuario(id=i, nome=n, email=e, papel=PapelUsuario(p), ativo=bool(a))
        for i, n, e, p, a in linhas
    ]


def _buscar_usuario(email: str) -> dict[str, Any] | None:
    con = _conexao_usuarios()
    try:
        linha = con.execute(
            "SELECT id, nome, email, papel, ativo, senha_hash, salt "
            "FROM usuarios WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        con.close()
    if not linha:
        return None
    uid, nome, mail, papel, ativo, senha_hash, salt = linha
    return {
        "usuario": Usuario(
            id=uid,
            nome=nome,
            email=mail,
            papel=PapelUsuario(papel),
            ativo=bool(ativo),
        ),
        "hash": senha_hash,
        "salt": salt,
    }


# ---------------------------------------------------------------------------
# Assinatura e Validação Criptográfica de Tokens de Sessão
# ---------------------------------------------------------------------------
def emitir_token_sessao(
    usuario_id: str,
    papel: PapelUsuario,
    duracao_segundos: int = _DURACAO_PADRAO_SESSAO_S,
) -> TokenSessao:
    """Emite um TokenSessao assinado com HMAC-SHA256 e timestamps UTC estritos."""
    agora_utc = datetime.now(timezone.utc)
    expira_utc = agora_utc + timedelta(seconds=duracao_segundos)

    ts_emissao = int(agora_utc.timestamp())
    ts_expiracao = int(expira_utc.timestamp())
    nonce = secrets.token_hex(8)

    corpo = f"{usuario_id}:{papel.value}:{ts_emissao}:{ts_expiracao}:{nonce}"
    assinatura = hmac.new(
        _SECRET_KEY.encode("utf-8"), corpo.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    token_string = f"omni_{corpo}:{assinatura}"

    return TokenSessao(
        token=token_string,
        usuario_id=usuario_id,
        papel=papel,
        emitido_em=agora_utc,
        expira_em=expira_utc,
    )


def validar_token_sessao(token: str | None) -> RespostaVerificacaoToken:
    """Valida integridade criptográfica, formato, expiração e status de revogação."""
    if not token or not isinstance(token, str):
        return RespostaVerificacaoToken(
            valido=False, expirado=False, mensagem="Token ausente ou inválido."
        )

    token_limpo = token.strip()
    if token_limpo.lower().startswith("bearer "):
        token_limpo = token_limpo[7:].strip()

    if not token_limpo.startswith("omni_"):
        return RespostaVerificacaoToken(
            valido=False, expirado=False, mensagem="Prefixo do token inválido."
        )

    # Checa revogação prévia
    if token_limpo in _BLACKLIST_TOKENS:
        return RespostaVerificacaoToken(
            valido=False, expirado=False, mensagem="Sessão revogada previamente."
        )

    try:
        conteudo = token_limpo[5:]
        corpo, assinatura_recebida = conteudo.rsplit(":", 1)
        partes = corpo.split(":")
        if len(partes) != 5:
            return RespostaVerificacaoToken(
                valido=False,
                expirado=False,
                mensagem="Segmentação interna do token inválida.",
            )

        uid, papel_str, ts_emit_str, ts_exp_str, _ = partes

        # Valida papel
        try:
            papel = PapelUsuario(papel_str)
        except ValueError:
            return RespostaVerificacaoToken(
                valido=False,
                expirado=False,
                mensagem=f"Papel desconhecido no token: {papel_str}.",
            )

        # Validação da assinatura criptográfica
        assinatura_esperada = hmac.new(
            _SECRET_KEY.encode("utf-8"), corpo.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(assinatura_recebida, assinatura_esperada):
            return RespostaVerificacaoToken(
                valido=False,
                expirado=False,
                mensagem="Assinatura forjada ou adulterada.",
            )

        # Checa expiração temporal UTC
        agora = datetime.now(timezone.utc).timestamp()
        ts_exp = float(ts_exp_str)
        if agora >= ts_exp:
            return RespostaVerificacaoToken(
                valido=False,
                usuario_id=uid,
                papel=papel,
                expirado=True,
                mensagem=f"Token expirado em {ts_exp_str}.",
            )

        return RespostaVerificacaoToken(
            valido=True,
            usuario_id=uid,
            papel=papel,
            expirado=False,
            mensagem="Token autêntico e sessão ativa.",
        )
    except Exception as e:
        return RespostaVerificacaoToken(
            valido=False, expirado=False, mensagem=f"Falha na validação do token: {e}"
        )


def revogar_token_sessao(
    requisicao: RequisicaoRevogacaoToken,
) -> RespostaRevogacaoToken:
    """Registra o token na blacklist e desativa sessões correlacionadas."""
    token = requisicao.token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    _BLACKLIST_TOKENS.add(token)
    registrar_auditoria_backend(
        usuario_id="sessao",
        acao="revogacao_token",
        recurso="auth:token",
        permitido=True,
        motivo=requisicao.motivo or "Logout voluntário.",
    )
    return RespostaRevogacaoToken(revogado=True, mensagem="Token revogado com sucesso.")


# ---------------------------------------------------------------------------
# Autenticação de Usuário (Login)
# ---------------------------------------------------------------------------
def autenticar_usuario_backend(requisicao: RequisicaoLogin) -> RespostaLogin:
    """Executa o ciclo completo de login com controle de força bruta e criação de contexto."""
    email = requisicao.identificador.strip().lower()

    # Checagem de bloqueio por força bruta
    falhas = _TENTATIVAS_FALHAS.get(email, 0)
    if falhas >= LIMITE_TENTATIVAS_LOGIN:
        registrar_auditoria_backend(
            usuario_id=email,
            acao="login",
            recurso="auth:login",
            permitido=False,
            motivo="Conta bloqueada por excesso de tentativas.",
        )
        raise ContaBloqueadaError(
            f"A conta '{email}' foi temporariamente bloqueada por excesso de tentativas falhas."
        )

    registro = _buscar_usuario(email)
    if not registro:
        _TENTATIVAS_FALHAS[email] = falhas + 1
        registrar_auditoria_backend(
            usuario_id=email,
            acao="login",
            recurso="auth:login",
            permitido=False,
            motivo="Usuário não cadastrado.",
        )
        raise CredenciaisInvalidasError("Credenciais inválidas.")

    usuario: Usuario = registro["usuario"]
    if not usuario.ativo:
        registrar_auditoria_backend(
            usuario_id=usuario.id,
            acao="login",
            recurso="auth:login",
            permitido=False,
            motivo="Usuário inativo.",
        )
        raise CredenciaisInvalidasError("Usuário desativado pelo administrador.")

    if not verificar_senha(requisicao.segredo, registro["salt"], registro["hash"]):
        _TENTATIVAS_FALHAS[email] = falhas + 1
        registrar_auditoria_backend(
            usuario_id=usuario.id,
            acao="login",
            recurso="auth:login",
            permitido=False,
            motivo="Senha incorreta.",
        )
        raise CredenciaisInvalidasError("Credenciais inválidas.")

    # Sucesso: limpa tentativas falhas
    _TENTATIVAS_FALHAS.pop(email, None)

    token = emitir_token_sessao(usuario.id, usuario.papel)
    contexto = ContextoAutenticacao(
        usuario=usuario,
        token=token,
        permissoes=PERMISSOES_PADRAO.get(usuario.papel, []).copy(),
    )

    registrar_auditoria_backend(
        usuario_id=usuario.id,
        acao="login",
        recurso="auth:login",
        permitido=True,
        motivo="Login efetuado com êxito.",
    )

    return RespostaLogin(
        sucesso=True,
        mensagem="Autenticação realizada com sucesso.",
        token=token,
        contexto=contexto,
    )


# ---------------------------------------------------------------------------
# Contexto de Autenticação em Thread / Backend
# ---------------------------------------------------------------------------
_CONTEXTO_THREAD: contextvars.ContextVar[Optional[ContextoAutenticacao]] = (
    contextvars.ContextVar("contexto_auth_thread", default=None)
)


def obter_contexto_ativo() -> Optional[ContextoAutenticacao]:
    return _CONTEXTO_THREAD.get()


@contextmanager
def contexto_backend(
    contexto: Optional[ContextoAutenticacao],
) -> Iterator[Optional[ContextoAutenticacao]]:
    anterior = _CONTEXTO_THREAD.get()
    try:
        _CONTEXTO_THREAD.set(contexto)
        yield contexto
    finally:
        _CONTEXTO_THREAD.set(anterior)


# ---------------------------------------------------------------------------
# Auditoria de Operações Backend
# ---------------------------------------------------------------------------
def registrar_auditoria_backend(
    usuario_id: str,
    acao: str,
    recurso: str,
    permitido: bool,
    motivo: str = "",
) -> dict[str, Any]:
    evento = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "usuario_id": usuario_id,
        "acao": acao,
        "recurso": recurso,
        "permitido": permitido,
        "motivo": motivo,
    }
    _TRILHA_AUDITORIA.append(evento)
    return evento


def obter_trilha_auditoria_backend() -> list[dict[str, Any]]:
    return list(_TRILHA_AUDITORIA)


# ---------------------------------------------------------------------------
# Despachante Seguro de Ferramentas com RBAC Estrito
# ---------------------------------------------------------------------------
def contexto_servico(papel: PapelUsuario = PapelUsuario.ADMIN) -> ContextoAutenticacao:
    """Contexto interno para scripts e testes que não passam pelo login."""
    usuario = Usuario(
        id="usr-servico",
        nome="Serviço Interno",
        email="servico@omni.ia",
        papel=papel,
    )
    return ContextoAutenticacao(
        usuario=usuario, token=emitir_token_sessao(usuario.id, papel)
    )


def contexto_de_token(token: str | None) -> Optional[ContextoAutenticacao]:
    """Reconstrói um contexto mínimo a partir de um token válido."""
    if not token:
        return None
    validacao = validar_token_sessao(token)
    if not validacao.valido:
        return None
    usr = Usuario(
        id=validacao.usuario_id or "usr-auth",
        nome="Usuário Autenticado",
        email=f"{validacao.usuario_id or 'usuario'}@omni.ia",
        papel=validacao.papel or PapelUsuario.ANALISTA,
    )
    tok = TokenSessao(
        token=token,
        usuario_id=usr.id,
        papel=usr.papel,
        expira_em=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    return ContextoAutenticacao(usuario=usr, token=tok)


def despachar_tool_autenticado(
    nome: str,
    argumentos: Optional[dict[str, Any]] = None,
    contexto: Optional[ContextoAutenticacao] = None,
    token: Optional[str] = None,
) -> dict[str, Any]:
    """Intercepta a execução da ferramenta validando token, permissões de papel e auditoria."""
    # 1. Determina o contexto de segurança
    ctx = contexto or obter_contexto_ativo()

    if ctx is None and token is not None:
        ctx = contexto_de_token(token)
        if ctx is None:
            validacao = validar_token_sessao(token)
            registrar_auditoria_backend(
                usuario_id=validacao.usuario_id or "desconhecido",
                acao=f"ferramenta:{nome}",
                recurso=nome,
                permitido=False,
                motivo=validacao.mensagem,
            )
            return {
                "erro": f"Token inválido: {validacao.mensagem}",
                "status_code": 401,
                "autorizado": False,
            }

    if ctx is None:
        registrar_auditoria_backend(
            usuario_id="anonimo",
            acao=f"ferramenta:{nome}",
            recurso=nome,
            permitido=False,
            motivo="Operação anônima não permitida.",
        )
        return {
            "erro": f"Acesso negado: a ferramenta '{nome}' exige autenticação prévia.",
            "status_code": 401,
            "autorizado": False,
        }

    # 2. Avaliação de RBAC
    permissao_exigida = PERMISSOES_FERRAMENTAS.get(nome)
    if permissao_exigida and not ctx.possui_permissao(permissao_exigida):
        motivo = (
            f"Papel '{ctx.usuario.papel.value}' não possui a permissão necessária "
            f"'{permissao_exigida.value}' para executar '{nome}'."
        )
        registrar_auditoria_backend(
            usuario_id=ctx.usuario.id,
            acao=f"ferramenta:{nome}",
            recurso=nome,
            permitido=False,
            motivo=motivo,
        )
        return {
            "erro": f"Acesso negado: {motivo}",
            "status_code": 403,
            "autorizado": False,
            "permissao_requerida": permissao_exigida.value,
        }

    # 3. Execução da ferramenta via despacho padrão
    from src.core.agent import despachar_tool

    with contexto_backend(ctx):
        resultado = despachar_tool(nome, argumentos)

    registrar_auditoria_backend(
        usuario_id=ctx.usuario.id,
        acao=f"ferramenta:{nome}",
        recurso=nome,
        permitido=True,
        motivo="Execução autorizada e bem-sucedida.",
    )
    return resultado
