"""Modelos de dados do RFQ Control.

Cada coleção é gravada em um arquivo JSON próprio na pasta ``dados``
(equivalente às abas da planilha antiga). Os modelos validam os dados tanto
ao carregar os arquivos quanto ao salvar pelo aplicativo.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

_REGEX_EMAIL = re.compile(r"^[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+$")


def novo_id() -> str:
    return uuid.uuid4().hex[:12]


def agora() -> datetime:
    return datetime.now().replace(microsecond=0)


def email_valido(email: str) -> bool:
    return bool(_REGEX_EMAIL.match(email.strip()))


class Modelo(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore", use_enum_values=False)


class Registro(Modelo):
    id: str = Field(default_factory=novo_id)


def _obrigatorio(valor: str, campo: str) -> str:
    if not valor:
        raise ValueError(f"{campo} é obrigatório")
    return valor


class Idioma(str, Enum):
    PT = "PT"
    ES = "ES"
    EN = "EN"

    @property
    def rotulo(self) -> str:
        return {"PT": "Português", "ES": "Espanhol", "EN": "Inglês"}[self.value]

    @classmethod
    def de_texto(cls, texto: str | None) -> Idioma:
        """Aceita 'Português', 'Espanhol', 'Inglês', 'PT', 'es', 'English', 'Español'…"""
        chave = "".join(
            c for c in unicodedata.normalize("NFD", (texto or "").strip().casefold())
            if unicodedata.category(c) != "Mn"
        )
        for idioma, apelidos in _APELIDOS_IDIOMA.items():
            if chave in apelidos:
                return idioma
        raise ValueError(f"idioma inválido: '{texto}' (use Português, Espanhol ou Inglês)")


_APELIDOS_IDIOMA = {
    Idioma.PT: {"pt", "pt-br", "ptbr", "portugues", "portuguese", "port", "br", "brasil"},
    Idioma.ES: {"es", "espanhol", "espanol", "spanish", "castellano", "esp"},
    Idioma.EN: {"en", "ingles", "english", "eng", "ing", "en-us", "en-gb"},
}


class StatusRFQ(str, Enum):
    RASCUNHO = "Rascunho"
    ENVIADA = "Enviada"
    RESPONDIDA = "Respondida"
    DECLINADA = "Declinada"
    SELECIONADA = "Selecionada"
    NAO_SELECIONADA = "Não selecionada"
    CANCELADA = "Cancelada"


# Situação exibida quando uma RFQ enviada passa do prazo sem resposta.
SITUACAO_ATRASADA = "Atrasada"

# Status que contam como "o fornecedor respondeu".
STATUS_COM_RESPOSTA = {
    StatusRFQ.RESPONDIDA,
    StatusRFQ.DECLINADA,
    StatusRFQ.SELECIONADA,
    StatusRFQ.NAO_SELECIONADA,
}


# ---------------------------------------------------------------- cadastros


class Contato(Modelo):
    nome: str = ""
    email: str = ""
    copia: bool = False  # False = destinatário (Para); True = em cópia (Cc)
    telefone: str = ""

    @field_validator("email")
    @classmethod
    def _validar_email(cls, valor: str) -> str:
        if valor and not email_valido(valor):
            raise ValueError(f"e-mail inválido: {valor}")
        return valor.lower()


class Fornecedor(Registro):
    nome: str
    idioma: Idioma = Idioma.PT
    categoria: str = ""
    observacoes: str = ""
    ativo: bool = True
    contatos: list[Contato] = []

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        return _obrigatorio(valor, "Nome do fornecedor")

    def emails_para(self) -> list[str]:
        return [c.email for c in self.contatos if c.email and not c.copia]

    def emails_copia(self) -> list[str]:
        return [c.email for c in self.contatos if c.email and c.copia]

    def nome_contato(self) -> str:
        """Nome usado na saudação do e-mail (primeiro destinatário com nome)."""
        for contato in self.contatos:
            if not contato.copia and contato.nome:
                return contato.nome
        return ""


class Projeto(Registro):
    nome: str
    cliente: str = ""
    planta: str = ""
    sop: date | None = None
    lifetime_anos: int | None = Field(default=None, ge=0, le=50)
    ativo: bool = True

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        return _obrigatorio(valor, "Nome do projeto")


class Solicitante(Registro):
    nome: str
    email: str = ""
    ativo: bool = True

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        return _obrigatorio(valor, "Nome do solicitante")

    @field_validator("email")
    @classmethod
    def _validar_email(cls, valor: str) -> str:
        if valor and not email_valido(valor):
            raise ValueError(f"e-mail inválido: {valor}")
        return valor.lower()


class Feriado(Registro):
    data: date
    descricao: str = ""


class TipoModelo(str, Enum):
    RFQ = "Solicitação de cotação"
    COBRANCA = "Cobrança"


class ModeloEmail(Registro):
    tipo: TipoModelo = TipoModelo.RFQ
    idioma: Idioma = Idioma.PT
    assunto: str
    corpo: str

    @field_validator("assunto", "corpo")
    @classmethod
    def _validar_texto(cls, valor: str) -> str:
        return _obrigatorio(valor, "Assunto e corpo")


# ---------------------------------------------------------------- cotações


class Item(Modelo):
    ref_op: str = ""
    ref_cdc: str = ""
    descricao: str = ""
    unidade: str = ""
    quantidade: float | None = Field(default=None, ge=0)
    volume_anual: float | None = Field(default=None, ge=0)

    def vazio(self) -> bool:
        return not any(
            [self.ref_op, self.ref_cdc, self.descricao, self.unidade]
        ) and self.quantidade is None and self.volume_anual is None


class Pacote(Registro):
    """Pacote de cotação: o que se quer cotar (projeto + itens + anexos)."""

    titulo: str = ""
    projeto_id: str
    solicitante_id: str | None = None
    data: date = Field(default_factory=date.today)
    prazo_dias_uteis: int = Field(default=4, ge=0, le=60)
    observacoes: str = ""
    itens: list[Item] = []
    anexos: list[str] = []


class Evento(Modelo):
    data_hora: datetime = Field(default_factory=agora)
    descricao: str


class RFQ(Registro):
    """Um pacote enviado a um fornecedor."""

    numero: str
    pacote_id: str
    fornecedor_id: str
    idioma: Idioma = Idioma.PT
    status: StatusRFQ = StatusRFQ.RASCUNHO
    data_criacao: date = Field(default_factory=date.today)
    data_envio: date | None = None
    prazo: date | None = None
    data_resposta: date | None = None
    valor_total: float | None = Field(default=None, ge=0)
    moeda: str = "BRL"
    lead_time: str = ""
    observacoes: str = ""
    historico: list[Evento] = []

    def atrasada(self, hoje: date | None = None) -> bool:
        hoje = hoje or date.today()
        return self.status == StatusRFQ.ENVIADA and self.prazo is not None and self.prazo < hoje

    def situacao(self, hoje: date | None = None) -> str:
        return SITUACAO_ATRASADA if self.atrasada(hoje) else self.status.value

    def registrar(self, descricao: str) -> None:
        self.historico.append(Evento(descricao=descricao))


# ---------------------------------------------------------------- configurações


class MetodoEmail(str, Enum):
    OUTLOOK = "Outlook (abre o rascunho automaticamente)"
    EML = "Arquivo .eml (abre no programa de e-mail padrão)"


class Configuracoes(Modelo):
    empresa: str = ""
    prefixo_rfq: str = "RFQ"
    prazo_dias_uteis: int = Field(default=4, ge=0, le=60)
    metodo_email: MetodoEmail = MetodoEmail.OUTLOOK
    assinatura_html: str = ""
    copia_padrao: str = ""
    copiar_solicitante: bool = False
    incluir_colunas_fornecedor: bool = True
    moeda_padrao: str = "BRL"
    envio_automatico: bool = False  # True = envia direto pelo Outlook, sem abrir o rascunho

    @field_validator("prefixo_rfq")
    @classmethod
    def _validar_prefixo(cls, valor: str) -> str:
        if not re.fullmatch(r"[A-Za-z]{1,10}", valor or ""):
            raise ValueError("o prefixo deve ter de 1 a 10 letras (ex.: RFQ)")
        return valor.upper()

    def emails_copia_padrao(self) -> list[str]:
        return separar_emails(self.copia_padrao)


def separar_emails(texto: str) -> list[str]:
    """Separa uma lista de e-mails digitada com ';', ',' ou quebras de linha."""
    partes = re.split(r"[;,\s]+", texto or "")
    return [p.strip().lower() for p in partes if p.strip()]
