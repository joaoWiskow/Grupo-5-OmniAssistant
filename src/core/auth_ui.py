"""Módulo de Autenticação, Controle de Sessão e Guardrails de UI para OmniAssistant.

Suporta:
- Modelo de Usuário e Perfis de Acesso (RBAC).
- Ciclo de vida da sessão Streamlit: autenticado, usuario_atual, token_sessao.
- Telas de Login duplo modo: Credenciais formais ou Seletor Rápido de Perfis (Dev/Staging).
- Guardrails estritos de isolamento de interface (Sidebar, Inputs e Chat bloqueados).
- Badges dinâmicos de usuário, nível de acesso e encerramento seguro (Logout com purge).
"""

from __future__ import annotations

import hashlib
import html
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import streamlit as st

from pydantic import ValidationError

from src.core.auth import (
    ContaBloqueadaError,
    CredenciaisInvalidasError,
    autenticar_usuario_backend,
    emitir_token_sessao,
    revogar_token_sessao,
    validar_token_sessao as _validar_token_backend,
)
from src.core.contracts import (
    PERMISSOES_PADRAO,
    PapelUsuario,
    RequisicaoLogin,
    RequisicaoRevogacaoToken,
)

# Segredo legado só para hashes do seletor rápido (tokens usam AUTH_SECRET_KEY do backend).
_SECRET_KEY = "omni-assistant-secret-key-auth-2026"
SESSION_EXPIRATION_SECONDS = 3600 * 8  # 8 horas de sessão ativa


@dataclass
class Usuario:
    id: str
    login: str
    nome: str
    email: str
    papel: str  # 'Gestor' | 'Analista' | 'Auditor'
    badge_cor: str
    avatar: str
    permissoes: List[str] = field(default_factory=list)
    salt: str = ""
    senha_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("senha_hash", None)
        d.pop("salt", None)
        return d


def _hash_senha(senha: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{senha}:{_SECRET_KEY}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Base de Usuários e Perfis de Demonstração / Staging
# ---------------------------------------------------------------------------
_USUARIOS_MOCK: Dict[str, Usuario] = {
    "gestor": Usuario(
        id="usr-gst-001",
        login="helena.gestora",
        nome="Dra. Helena Vasconcelos",
        email="helena.vasconcelos@omni.ia",
        papel="Gestor",
        badge_cor="#FFB347",  # Âmbar corporativo
        avatar="👩‍💼",
        permissoes=[
            "leitura",
            "consultar_banco",
            "upload_arquivos",
            "audio_mic",
            "sintese_voz",
            "auditoria_completa",
            "exportar_dados",
        ],
        salt="salt_gst_819",
        senha_hash=_hash_senha("admin123", "salt_gst_819"),
    ),
    "analista": Usuario(
        id="usr-anl-002",
        login="carlos.analista",
        nome="Carlos Drummond",
        email="carlos.drummond@omni.ia",
        papel="Analista",
        badge_cor="#00E0FF",  # Ciano HUD
        avatar="👨‍💻",
        permissoes=[
            "leitura",
            "consultar_banco",
            "upload_arquivos",
            "audio_mic",
            "sintese_voz",
        ],
        salt="salt_anl_442",
        senha_hash=_hash_senha("analista123", "salt_anl_442"),
    ),
    "auditor": Usuario(
        id="usr-aud-003",
        login="mariana.auditora",
        nome="Mariana Rios",
        email="mariana.rios@omni.ia",
        papel="Auditor",
        badge_cor="#BA68C8",  # Roxo de auditoria
        avatar="🛡️",
        permissoes=["leitura", "consultar_banco", "auditoria_completa"],
        salt="salt_aud_993",
        senha_hash=_hash_senha("auditor123", "salt_aud_993"),
    ),
}


# ---------------------------------------------------------------------------
# Geração e Validação de Token de Sessão Criptográfico (mesmo formato do backend)
# ---------------------------------------------------------------------------
_PAPEL_POR_ROTULO = {
    "Administrador": PapelUsuario.ADMIN,
    "Gestor": PapelUsuario.GESTOR,
    "Analista": PapelUsuario.ANALISTA,
    "Auditor": PapelUsuario.AUDITOR,
}

_APARENCIA_POR_PAPEL = {
    PapelUsuario.ADMIN: ("Administrador", "#FF6B6B", "🛡️"),
    PapelUsuario.GESTOR: ("Gestor", "#FFB347", "👩‍💼"),
    PapelUsuario.ANALISTA: ("Analista", "#00E0FF", "👨‍💻"),
    PapelUsuario.AUDITOR: ("Auditor", "#BA68C8", "🕵️"),
}


def gerar_token_sessao(
    usuario_id: str, papel: PapelUsuario = PapelUsuario.ANALISTA
) -> str:
    """Emite um token no formato assinado do backend (aceito por despachar_tool_autenticado)."""
    return emitir_token_sessao(usuario_id, papel, SESSION_EXPIRATION_SECONDS).token


def validar_token_sessao(token: Optional[str]) -> bool:
    """Valida expiração pelo relógio local e assinatura criptográfica do backend."""
    if not token or not isinstance(token, str) or not token.startswith("omni_"):
        return False
    try:
        corpo = token[5:].rsplit(":", 1)[0]
        partes = corpo.split(":")
        if len(partes) != 5:
            return False
        if time.time() >= float(partes[3]):
            return False
    except (ValueError, IndexError):
        return False
    return _validar_token_backend(token).valido


def usuario_ui_de_backend(usuario) -> "Usuario":
    """Converte o Usuario do backend no perfil de exibição da UI (sem expor hash/salt)."""
    rotulo, cor, avatar = _APARENCIA_POR_PAPEL[usuario.papel]
    return Usuario(
        id=usuario.id,
        login=usuario.email,
        nome=usuario.nome,
        email=usuario.email,
        papel=rotulo,
        badge_cor=cor,
        avatar=avatar,
        permissoes=PERMISSOES_PADRAO.get(usuario.papel, []).copy(),
    )


# ---------------------------------------------------------------------------
# Gerenciamento de Estado no Streamlit
# ---------------------------------------------------------------------------
def inicializar_estado_auth() -> None:
    """Garante a existência das chaves padronizadas de autenticação no session_state."""
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
    if "usuario_atual" not in st.session_state:
        st.session_state["usuario_atual"] = None
    if "token_sessao" not in st.session_state:
        st.session_state["token_sessao"] = None
    if "login_timestamp" not in st.session_state:
        st.session_state["login_timestamp"] = None


def executar_login(usuario: Usuario) -> None:
    """Registra o usuário, cria token compatível com o backend e redireciona."""
    papel = _PAPEL_POR_ROTULO.get(usuario.papel, PapelUsuario.ANALISTA)
    st.session_state["autenticado"] = True
    st.session_state["usuario_atual"] = usuario.to_dict()
    st.session_state["token_sessao"] = gerar_token_sessao(usuario.id, papel)
    st.session_state["login_timestamp"] = time.time()
    st.rerun()


def executar_logout() -> None:
    """Revoga o token no backend, purga a sessão e retorna ao login."""
    token = st.session_state.get("token_sessao")
    if token:
        try:
            revogar_token_sessao(
                RequisicaoRevogacaoToken(
                    token=token, motivo="Logout voluntário na UI."
                )
            )
        except Exception:
            pass

    chaves_para_limpar = list(st.session_state.keys())
    for k in chaves_para_limpar:
        del st.session_state[k]

    # Re-inicializa padrões seguros
    inicializar_estado_auth()
    st.session_state["historico_mensagens"] = []
    st.session_state["evidencias_ativas"] = []
    st.session_state["splash_visto"] = True  # Evita repetir o splash no logout
    st.rerun()


def usuario_possui_permissao(permissao: str) -> bool:
    """Verifica se o usuário atualmente autenticado possui a permissão requerida."""
    usuario = st.session_state.get("usuario_atual")
    if not usuario:
        return False
    return permissao in usuario.get("permissoes", [])


# ---------------------------------------------------------------------------
# UI: Indicadores de Usuário & Barra Lateral
# ---------------------------------------------------------------------------
def renderizar_painel_usuario_sidebar(tema_hud: bool = False) -> None:
    """Renderiza na sidebar o perfil do usuário logado, badge de papel e botão de logout."""
    usuario = st.session_state.get("usuario_atual")
    if not usuario:
        return

    nome = html.escape(usuario.get("nome", "Usuário"))
    papel = html.escape(usuario.get("papel", "Convidado"))
    cor = usuario.get("badge_cor", "#00E0FF" if tema_hud else "#4FD1C5")
    avatar = usuario.get("avatar", "👤")
    token = st.session_state.get("token_sessao", "")
    token_curto = f"{token[:12]}..." if token else "N/A"

    if tema_hud:
        html_bloco = f"""
        <div style="
            background: rgba(0, 224, 255, 0.05);
            border: 1px solid rgba(0, 224, 255, 0.25);
            padding: 0.9rem;
            margin-bottom: 1.2rem;
            clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
        ">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.4rem;">
                <span style="font-size: 1.3rem;">{avatar}</span>
                <span style="
                    font-family: 'Share Tech Mono', monospace;
                    font-size: 0.72rem;
                    letter-spacing: 0.12em;
                    color: {cor};
                    background: rgba(0, 224, 255, 0.12);
                    padding: 0.15rem 0.5rem;
                    border: 1px solid {cor};
                    text-transform: uppercase;
                ">CLEARANCE: {papel}</span>
            </div>
            <div style="font-family: 'Orbitron', sans-serif; font-size: 0.92rem; font-weight: 600; color: #BFEFFA; margin-bottom: 0.2rem;">
                {nome}
            </div>
            <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.75rem; color: #6FA3B3;">
                SESSÃO: <code style="color:{cor}; background:transparent;">{token_curto}</code>
            </div>
        </div>
        """
    else:
        html_bloco = f"""
        <div style="
            background: #0C2029;
            border: 1px solid #1B3744;
            border-radius: 12px;
            padding: 0.85rem;
            margin-bottom: 1.2rem;
        ">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.4rem;">
                <span style="font-size: 1.2rem;">{avatar}</span>
                <span style="
                    font-size: 0.75rem;
                    font-weight: 500;
                    color: {cor};
                    background: rgba(255, 255, 255, 0.05);
                    padding: 0.2rem 0.6rem;
                    border-radius: 999px;
                    border: 1px solid {cor};
                ">{papel}</span>
            </div>
            <div style="font-weight: 500; font-size: 0.95rem; color: #E6F1F2;">{nome}</div>
            <div style="font-size: 0.75rem; color: #7F9AA3; margin-top: 0.2rem;">
                Token: <code>{token_curto}</code>
            </div>
        </div>
        """

    st.sidebar.markdown(html_bloco, unsafe_allow_html=True)
    if st.sidebar.button("Encerrar Sessão", key="btn_auth_logout", type="secondary"):
        executar_logout()


# ---------------------------------------------------------------------------
# GUARDRAIL PRINCIPAL: Bloqueia Renderização e Interações Não Autenticadas
# ---------------------------------------------------------------------------
def checar_guardrails_auth(tema_hud: bool = False) -> None:
    """Verifica se o usuário está autenticado e com token válido.

    Se não estiver, oculta totalmente os controles da sidebar via CSS,
    renderiza a tela de login (Dual Mode: Credenciais ou Perfis Dev)
    e chama `st.stop()` para garantir que nenhum input ou agente seja executado.
    """
    inicializar_estado_auth()

    # Valida sessão existente
    if st.session_state.get("autenticado"):
        token = st.session_state.get("token_sessao")
        if validar_token_sessao(token):
            return  # Sessão válida! Prossegue com a aplicação.
        else:
            # Token expirado ou forjado -> reset imediato
            st.warning("Sua sessão expirou ou é inválida. Por favor, autentique-se novamente.")
            executar_logout()
            st.stop()

    # BLOQUEIO ABSOLUTO DA BARRA LATERAL QUANDO NÃO AUTENTICADO
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
            visibility: hidden !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # RENDERIZAÇÃO DA TELA DE LOGIN
    _renderizar_tela_login(tema_hud=tema_hud)

    # Interrompe a execução aqui: nenhum chat_input, file_uploader ou agente roda!
    st.stop()


def _renderizar_tela_login(tema_hud: bool = False) -> None:
    """Interface elegante de login adaptada ao tema estético da aplicação."""
    col_centro_l, col_centro, col_centro_r = st.columns([1, 2.2, 1])

    with col_centro:
        if tema_hud:
            st.markdown(
                """
                <div style="text-align: center; margin-top: 2rem; margin-bottom: 1.5rem;">
                    <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.85rem; color: #00E0FF; letter-spacing: 0.2em;">
                        ACESSO RESTRITO // SECURITY GATEWAY
                    </div>
                    <h1 style="font-family: 'Orbitron', sans-serif; font-size: 2.2rem; color: #00E0FF; margin: 0.4rem 0;">
                        OMNIASSISTANT
                    </h1>
                    <p style="color: #6FA3B3; font-size: 0.95rem;">
                        Autenticação multifatorial corporativa e controle de permissões
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div style="text-align: center; margin-top: 2rem; margin-bottom: 1.5rem;">
                    <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#FFB347; box-shadow:0 0 14px #FFB347;"></span>
                    <h1 style="font-size: 2.1rem; margin: 0.4rem 0;">OmniAssistant</h1>
                    <p style="color: #7F9AA3; font-size: 1rem;">
                        Controle de Acesso e Identidade Corporativa
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        aba_perfis, aba_credenciais = st.tabs(
            ["⚡ Seletor Rápido (Dev / Staging)", "🔒 Credenciais Corporativas"]
        )

        with aba_perfis:
            st.caption(
                "Simule instantaneamente a navegação sob diferentes papéis de responsabilidade:"
            )

            col1, col2 = st.columns(2)
            perfis = list(_USUARIOS_MOCK.values())

            for i, usuario in enumerate(perfis):
                col_alvo = col1 if i % 2 == 0 else col2
                with col_alvo:
                    st.markdown(
                        f"""
                        <div style="
                            padding: 0.75rem;
                            border: 1px solid {usuario.badge_cor};
                            border-radius: 8px;
                            margin-bottom: 0.6rem;
                            background: rgba(255,255,255,0.02);
                        ">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <b>{usuario.avatar} {usuario.papel}</b>
                                <span style="font-size:0.75rem; color:{usuario.badge_cor};">{usuario.login}</span>
                            </div>
                            <div style="font-size:0.85rem; color:#A0B0B8; margin-top:0.2rem;">{usuario.nome}</div>
                            <div style="font-size:0.75rem; color:#6FA3B3; margin-top:0.3rem;">
                                Permissões: {len(usuario.permissoes)} recursos
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        f"Entrar como {usuario.papel}",
                        key=f"btn_quick_{usuario.id}",
                        type="primary" if usuario.papel == "Gestor" else "secondary",
                        use_container_width=True,
                    ):
                        executar_login(usuario)

        with aba_credenciais:
            st.caption("Acesso via contas corporativas registradas no banco:")
            with st.form("form_login_credenciais"):
                input_usuario = st.text_input(
                    "E-mail corporativo", placeholder="ex: gestor@omni.ia"
                )
                input_senha = st.text_input(
                    "Senha", type="password", placeholder="••••••••"
                )
                submit = st.form_submit_button(
                    "Entrar no Sistema", type="primary", use_container_width=True
                )

                if submit:
                    try:
                        resposta = autenticar_usuario_backend(
                            RequisicaoLogin(
                                identificador=input_usuario.strip(),
                                segredo=input_senha,
                            )
                        )
                    except ValidationError:
                        st.error(
                            "Informe e-mail corporativo e senha válidos "
                            "(senha com pelo menos 6 caracteres)."
                        )
                    except (CredenciaisInvalidasError, ContaBloqueadaError) as exc:
                        st.error(str(exc))
                    else:
                        st.success(
                            f"Bem-vindo(a), {resposta.contexto.usuario.nome}!"
                        )
                        time.sleep(0.3)
                        executar_login(usuario_ui_de_backend(resposta.contexto.usuario))
