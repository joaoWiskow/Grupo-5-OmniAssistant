from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Self
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Expressão regular RFC 5322 simplificada para validação de e-mails corporativos
REGEX_EMAIL = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


class ContratoBase(BaseModel):
    """Contrato base imutável e estrito contra atributos desconhecidos."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# DOMÍNIO: RBAC E CONTROLE DE ACESSO
# ---------------------------------------------------------------------------


class PapelUsuario(str, Enum):
    """Papéis hierárquicos para controle de acesso baseado em função (RBAC)."""

    ADMIN = "ADMIN"
    GESTOR = "GESTOR"
    ANALISTA = "ANALISTA"
    AUDITOR = "AUDITOR"


class Permissao(str, Enum):
    """Permissões granulares de operação no ecossistema OmniAssistant."""

    USUARIOS_GERENCIAR = "usuarios:gerenciar"
    TRIAGEM_EXECUTAR = "triagem:executar"
    TRIAGEM_APROVAR = "triagem:aprovar"
    BANCO_CONSULTAR = "banco:consultar"
    AUDITORIA_VISUALIZAR = "auditoria:visualizar"
    CONFIGURACAO_EDITAR = "configuracao:editar"


PERMISSOES_PADRAO: dict[PapelUsuario, list[str]] = {
    PapelUsuario.ADMIN: [p.value for p in Permissao],
    PapelUsuario.GESTOR: [
        Permissao.TRIAGEM_EXECUTAR.value,
        Permissao.TRIAGEM_APROVAR.value,
        Permissao.BANCO_CONSULTAR.value,
        Permissao.AUDITORIA_VISUALIZAR.value,
    ],
    PapelUsuario.ANALISTA: [
        Permissao.TRIAGEM_EXECUTAR.value,
        Permissao.BANCO_CONSULTAR.value,
    ],
    PapelUsuario.AUDITOR: [
        Permissao.BANCO_CONSULTAR.value,
        Permissao.AUDITORIA_VISUALIZAR.value,
    ],
}


class Usuario(ContratoBase):
    """Entidade de usuário registrada no OmniAssistant."""

    id: str = Field(
        min_length=1,
        max_length=64,
        description="Identificador único universal do usuário (UUID ou chave de banco)",
    )
    nome: str = Field(
        min_length=2,
        max_length=120,
        description="Nome completo ou de exibição do usuário",
    )
    email: str = Field(
        pattern=REGEX_EMAIL,
        description="Endereço de e-mail institucional normalizado",
    )
    papel: PapelUsuario = Field(
        description="Papel atribuído no controle de acesso baseado em função",
    )
    ativo: bool = Field(
        default=True,
        description="Indica se o usuário está habilitado para autenticação",
    )

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 2:
            raise ValueError("Nome não pode conter apenas espaços em branco.")
        return s

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class CredenciaisLogin(ContratoBase):
    """Par de identificador e segredo para autenticação de usuário."""

    identificador: str = Field(
        min_length=3,
        max_length=255,
        description="E-mail corporativo ou nome de usuário",
    )
    segredo: str = Field(
        min_length=6,
        max_length=128,
        description="Senha ou chave de autenticação em texto pleno",
    )

    @field_validator("identificador")
    @classmethod
    def sanitizar_identificador(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Identificador de login não pode ser vazio.")
        return s

    @field_validator("segredo")
    @classmethod
    def validar_segredo(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Segredo não pode ser composto apenas de espaços.")
        return v


class TokenSessao(ContratoBase):
    """Token de sessão com metadados temporais UTC e amarração de papel."""

    token: str = Field(
        min_length=16,
        description="Token de autenticação ou sessão criptográfica (JWT ou Bearer opaco)",
    )
    usuario_id: str = Field(
        min_length=1,
        max_length=64,
        description="ID do usuário proprietário da sessão",
    )
    papel: PapelUsuario = Field(
        description="Papel do usuário capturado no momento da emissão da sessão",
    )
    expira_em: datetime = Field(
        description="Timestamp UTC de expiração do token de sessão",
    )
    emitido_em: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp UTC de emissão da sessão",
    )

    @field_validator("expira_em", "emitido_em", mode="after")
    @classmethod
    def assegurar_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validar_cronologia(self) -> Self:
        if self.expira_em <= self.emitido_em:
            raise ValueError("A data de expiração deve ser estritamente posterior à emissão.")
        return self

    def esta_expirado(self, momento: datetime | None = None) -> bool:
        """Verifica se o token já expirou em relação a um momento UTC de referência."""
        agora = momento or datetime.now(timezone.utc)
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=timezone.utc)
        else:
            agora = agora.astimezone(timezone.utc)
        return agora >= self.expira_em

    def segundos_restantes(self, momento: datetime | None = None) -> float:
        """Retorna o tempo restante de vida da sessão em segundos."""
        agora = momento or datetime.now(timezone.utc)
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=timezone.utc)
        else:
            agora = agora.astimezone(timezone.utc)
        delta = (self.expira_em - agora).total_seconds()
        return max(0.0, delta)


class ContextoAutenticacao(ContratoBase):
    """Contexto de segurança injetado na sessão com usuário, token e permissões ativas."""

    usuario: Usuario = Field(
        description="Entidade do usuário autenticado",
    )
    token: TokenSessao = Field(
        description="Token de sessão vinculado",
    )
    permissoes: list[str] = Field(
        default_factory=list,
        description="Lista de permissões ativas concedidas ao usuário na sessão",
    )

    @model_validator(mode="after")
    def validar_consistencia_seguranca(self) -> Self:
        if self.usuario.id != self.token.usuario_id:
            raise ValueError(
                f"usuario_id inconsistente: usuario.id='{self.usuario.id}' != token.usuario_id='{self.token.usuario_id}'."
            )
        if self.usuario.papel != self.token.papel:
            raise ValueError(
                f"Papel inconsistente: usuario.papel='{self.usuario.papel}' != token.papel='{self.token.papel}'."
            )
        if not self.usuario.ativo:
            raise ValueError("Usuário desativado não pode compor contexto de autenticação ativo.")
        if not self.permissoes:
            self.permissoes = PERMISSOES_PADRAO.get(self.usuario.papel, []).copy()
        return self

    def possui_permissao(self, permissao: Permissao | str) -> bool:
        """Verifica se a permissão solicitada está ativa no contexto."""
        valor = permissao.value if isinstance(permissao, Permissao) else permissao
        return valor in self.permissoes

    def possui_todas_permissoes(self, *permissoes: Permissao | str) -> bool:
        """Verifica se todas as permissões informadas constam no contexto."""
        return all(self.possui_permissao(p) for p in permissoes)

    def possui_qualquer_permissao(self, *permissoes: Permissao | str) -> bool:
        """Verifica se ao menos uma das permissões informadas consta no contexto."""
        return any(self.possui_permissao(p) for p in permissoes)

    def possui_papel(self, *papeis: PapelUsuario) -> bool:
        """Verifica se o usuário possui um dos papéis informados."""
        return self.usuario.papel in papeis


# ---------------------------------------------------------------------------
# ESQUEMAS DE API (REQUEST / RESPONSE)
# ---------------------------------------------------------------------------


class RequisicaoLogin(ContratoBase):
    """Payload de entrada para o endpoint de autenticação."""

    identificador: str = Field(
        min_length=3,
        max_length=255,
        description="E-mail corporativo ou identificador de acesso",
    )
    segredo: str = Field(
        min_length=6,
        max_length=128,
        description="Senha de acesso em texto plano",
    )


class RespostaLogin(ContratoBase):
    """Payload de saída do endpoint de autenticação."""

    sucesso: bool = Field(
        default=True,
        description="Indica se a autenticação foi concluída com êxito",
    )
    mensagem: str = Field(
        default="Login efetuado com sucesso.",
        description="Mensagem informativa",
    )
    token: TokenSessao | None = Field(
        default=None,
        description="Token de sessão gerado em caso de sucesso",
    )
    contexto: ContextoAutenticacao | None = Field(
        default=None,
        description="Contexto completo de segurança se autenticado",
    )


class RequisicaoVerificacaoToken(ContratoBase):
    """Payload de consulta para validação de integridade de token."""

    token: str = Field(
        min_length=16,
        description="Token de sessão a ser verificado",
    )


class RespostaVerificacaoToken(ContratoBase):
    """Resultado da verificação de sessão."""

    valido: bool = Field(
        description="Indica se o token é autêntico e a sessão permanece ativa",
    )
    usuario_id: str | None = Field(
        default=None,
        description="ID do usuário se a validação for positiva",
    )
    papel: PapelUsuario | None = Field(
        default=None,
        description="Papel do usuário se a validação for positiva",
    )
    expirado: bool = Field(
        default=False,
        description="Indica se o token é conhecido, porém expirado temporalmente",
    )
    mensagem: str = Field(
        default="",
        description="Detalhe textual do resultado da verificação",
    )
    contexto: ContextoAutenticacao | None = Field(
        default=None,
        description="Contexto de autenticação reconstituído se válido",
    )


class RequisicaoValidacaoPermissao(ContratoBase):
    """Payload para autorização de ação baseada em permissão."""

    token: str = Field(
        min_length=16,
        description="Token da sessão do solicitante",
    )
    permissao_requerida: str = Field(
        min_length=1,
        description="Código da permissão requerida (ex: 'triagem:executar')",
    )
    recurso_alvo: str | None = Field(
        default=None,
        description="Identificador opcional de recurso alvo (ex: 'lote_502')",
    )


class RespostaValidacaoPermissao(ContratoBase):
    """Resultado da autorização de ação."""

    autorizado: bool = Field(
        description="Indica se a permissão foi concedida ao solicitante",
    )
    usuario_id: str | None = Field(
        default=None,
        description="ID do usuário autenticado associado ao token",
    )
    papel: PapelUsuario | None = Field(
        default=None,
        description="Papel do usuário no momento da avaliação",
    )
    permissao: str = Field(
        description="Permissão examinada",
    )
    motivo: str = Field(
        default="",
        description="Justificativa da decisão de autorização ou motivo da recusa",
    )


class RequisicaoRevogacaoToken(ContratoBase):
    """Payload para término/revogação voluntária de sessão (logout)."""

    token: str = Field(
        min_length=16,
        description="Token de sessão a ser invalidado",
    )
    motivo: str | None = Field(
        default=None,
        description="Motivo do encerramento da sessão",
    )


class RespostaRevogacaoToken(ContratoBase):
    """Resultado da revogação de sessão."""

    revogado: bool = Field(
        description="Indica se a revogação foi registrada com sucesso",
    )
    mensagem: str = Field(
        default="Sessão finalizada com sucesso.",
        description="Mensagem informativa da revogação",
    )


# ---------------------------------------------------------------------------
# CONTRATOS MULTIMODAIS EXISTENTES (COM COMPATIBILIDADE RETROATIVA TOTAL)
# ---------------------------------------------------------------------------


class EntradaUsuario(ContratoBase):
    """Representa a entrada bruta submetida pelo usuário ao pipeline multimodal."""

    tipo: Literal["imagem", "audio", "texto"]
    caminho_arquivo: Path | None = None
    texto_comando: str = ""
    usuario_id: str | None = None

    @model_validator(mode="after")
    def validar_consistencia(self) -> Self:
        if self.tipo == "texto" and not self.texto_comando.strip():
            raise ValueError("Entrada do tipo texto nao pode estar vazia.")
        if self.tipo in ("imagem", "audio"):
            if self.caminho_arquivo is None or not self.caminho_arquivo.is_file():
                raise ValueError(f"Arquivo obrigatorio nao encontrado para entrada do tipo {self.tipo}.")
        return self


class SegmentoFala(ContratoBase):
    """Segmento temporal transcrito com timestamp e texto correspondente."""

    inicio_segundos: float = Field(ge=0.0)
    fim_segundos: float = Field(ge=0.0)
    texto_transcrito: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_ordem_cronologica(self) -> Self:
        if self.fim_segundos < self.inicio_segundos:
            raise ValueError("O timestamp final nao pode ser menor que o timestamp inicial.")
        return self


class EvidenciaMultimodal(ContratoBase):
    """Evidência processada para consumo pelo agente decisor financeiro."""

    origem: Literal["visao", "audio", "texto", "banco_dados"]
    resumo_informacao: str = Field(min_length=1)
    segmentos_audio: list[SegmentoFala] = Field(default_factory=list)
    confianca_declarada: float = Field(default=1.0, ge=0.0, le=1.0)
    autor_usuario_id: str | None = None


__all__ = [
    "ContratoBase",
    "PapelUsuario",
    "Permissao",
    "PERMISSOES_PADRAO",
    "Usuario",
    "CredenciaisLogin",
    "TokenSessao",
    "ContextoAutenticacao",
    "RequisicaoLogin",
    "RespostaLogin",
    "RequisicaoVerificacaoToken",
    "RespostaVerificacaoToken",
    "RequisicaoValidacaoPermissao",
    "RespostaValidacaoPermissao",
    "RequisicaoRevogacaoToken",
    "RespostaRevogacaoToken",
    "EntradaUsuario",
    "SegmentoFala",
    "EvidenciaMultimodal",
]


if __name__ == "__main__":
    entrada_valida = EntradaUsuario(tipo="texto", texto_comando="Auditar lote 502")
    print("Contrato EntradaUsuario validado:")
    print(entrada_valida.model_dump_json(indent=2))
