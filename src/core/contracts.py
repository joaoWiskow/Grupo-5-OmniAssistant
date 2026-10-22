from pathlib import Path
from datetime import date
from typing import Literal, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ContratoBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

class EntradaUsuario(ContratoBase):
    tipo: Literal["imagem", "audio", "texto"]
    caminho_arquivo: Path | None = None
    texto_comando: str = ""

    @model_validator(mode="after")
    def validar_consistencia(self) -> Self:
        if self.tipo == "texto" and not self.texto_comando.strip():
            raise ValueError("Entrada do tipo texto nao pode estar vazia.")
        if self.tipo in ("imagem", "audio"):
            if self.caminho_arquivo is None or not self.caminho_arquivo.is_file():
                raise ValueError(f"Arquivo obrigatorio nao encontrado para entrada do tipo {self.tipo}.")
        return self

class SegmentoFala(ContratoBase):
    inicio_segundos: float = Field(ge=0.0)
    fim_segundos: float = Field(ge=0.0)
    texto_transcrito: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_ordem_cronologica(self) -> Self:
        if self.fim_segundos < self.inicio_segundos:
            raise ValueError("O timestamp final nao pode ser menor que o timestamp inicial.")
        return self

class EvidenciaMultimodal(ContratoBase):
    origem: Literal["visao", "audio", "texto", "banco_dados"]
    resumo_informacao: str = Field(min_length=1)
    segmentos_audio: list[SegmentoFala] = Field(default_factory=list)
    confianca_declarada: float = Field(default=1.0, ge=0.0, le=1.0)


class ItemRegistro(ContratoBase):
    codigo: str | None = None
    descricao: str | None = None
    quantidade: float | None = Field(default=None, ge=0)
    preco_unitario: float | None = Field(default=None, ge=0)
    total: float | None = Field(default=None, ge=0)


class RegistroConversa(ContratoBase):
    """Dados confirmáveis extraídos de uma análise, sem substituir a resposta textual."""

    id_operacao: str
    destinatario_email: str | None = None
    cliente: str | None = None
    documento: str | None = None
    numero_nota: str | None = None
    data_emissao: date | None = None
    data_vencimento: date | None = None
    itens: list[ItemRegistro] = Field(default_factory=list)
    total: float | None = Field(default=None, ge=0)
    status: str | None = None
    risco: Literal["neutro", "verde", "amarelo", "vermelho"] = "neutro"
    resumo: str
    pendencias: list[str] = Field(default_factory=list)
    origem: Literal["conversa"] = "conversa"

if __name__ == "__main__":
    entrada_valida = EntradaUsuario(tipo="texto", texto_comando="Auditar lote 502")
    print("Contrato EntradaUsuario validado:")
    print(entrada_valida.model_dump_json(indent=2))