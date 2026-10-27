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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
        chave = _sem_acentos(texto or "")
        for idioma, apelidos in _APELIDOS_IDIOMA.items():
            if chave in apelidos:
                return idioma
        raise ValueError(f"idioma inválido: '{texto}' (use Português, Espanhol ou Inglês)")


_APELIDOS_IDIOMA = {
    Idioma.PT: {"pt", "pt-br", "ptbr", "portugues", "portuguese", "port", "br", "brasil"},
    Idioma.ES: {"es", "espanhol", "espanol", "spanish", "castellano", "esp"},
    Idioma.EN: {"en", "ingles", "english", "eng", "ing", "en-us", "en-gb"},
}


def _sem_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").strip().casefold()) if unicodedata.category(c) != "Mn"
    )


# Região (país) do fornecedor e do projeto, usada nas Condições. Siglas e nomes em PT/ES/EN viram o nome
# em português (ex.: "BR", "Brazil" → "Brasil"); outros textos ficam como foram digitados.
REGIOES = {
    "Brasil": {"br", "bra", "brasil", "brazil"},
    "Argentina": {"ar", "arg", "argentina"},
    "México": {"mx", "mex", "mexico"},
    "Chile": {"cl", "chi", "chile"},
    "Uruguai": {"uy", "uru", "uruguai", "uruguay"},
    "Paraguai": {"py", "par", "paraguai", "paraguay"},
    "Colômbia": {"co", "col", "colombia"},
    "Peru": {"pe", "per", "peru"},
    "Estados Unidos": {"us", "usa", "eua", "estados unidos", "united states", "estados unidos da america"},
    "Canadá": {"ca", "can", "canada"},
    "Alemanha": {"de", "ger", "alemanha", "germany", "alemania", "deutschland"},
    "Espanha": {"es", "esp", "espanha", "spain", "espana"},
    "Portugal": {"pt", "por", "portugal"},
    "Itália": {"it", "ita", "italia", "italy"},
    "França": {"fr", "fra", "franca", "france", "francia"},
    "China": {"cn", "chn", "china"},
    "Índia": {"in", "ind", "india"},
    "Japão": {"jp", "jpn", "japao", "japan", "japon"},
    "Coreia do Sul": {"kr", "kor", "coreia", "coreia do sul", "south korea", "korea", "corea", "corea del sur"},
}
_APELIDOS_REGIAO = {apelido: nome for nome, apelidos in REGIOES.items() for apelido in apelidos}


def normalizar_regiao(texto: str | None) -> str:
    """'BR', 'brazil', ' Brasil ' → 'Brasil'; região fora da lista fica como foi digitada (sem espaços extras)."""
    limpo = re.sub(r"\s+", " ", texto or "").strip()
    return _APELIDOS_REGIAO.get(_sem_acentos(limpo), limpo)


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
# Situação de uma RFQ em rascunho cujo e-mail foi aberto para revisão, mas ainda não apareceu
# nos Itens Enviados do Outlook (se o rascunho for apagado sem enviar, ela continua em rascunho).
SITUACAO_AGUARDANDO = "Aguardando envio"

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


class Commodity(Registro):
    """Família de itens comprados (ex.: Ferramentaria) e o comprador da OP responsável por ela."""

    nome: str
    comprador: str = ""  # Commodity Buyer: vai em cópia nos e-mails dos pacotes desta commodity
    email: str = ""

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        if re.search(r"[;\r\n]", valor or ""):
            raise ValueError("o nome da commodity não pode ter ';' nem quebra de linha (o ';' separa commodities)")
        return _obrigatorio(valor, "Nome da commodity")

    @field_validator("email")
    @classmethod
    def _validar_email(cls, valor: str) -> str:
        if valor and not email_valido(valor):
            raise ValueError(f"e-mail inválido: {valor}")
        return valor.lower()


class Fornecedor(Registro):
    nome: str
    idioma: Idioma = Idioma.PT
    regiao: str = ""  # país do fornecedor (diferente do idioma), usado nas Condições
    commodity_ids: list[str] = []
    categoria: str = ""  # versões até 0.2: texto livre, migrado para commodities ao abrir a base
    observacoes: str = ""
    ativo: bool = True
    contatos: list[Contato] = []

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        return _obrigatorio(valor, "Nome do fornecedor")

    @field_validator("regiao")
    @classmethod
    def _validar_regiao(cls, valor: str) -> str:
        return normalizar_regiao(valor)

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
    regiao: str = ""  # país da planta/cotação (ex.: Argentina), usado nas Condições
    sop: date | None = None
    lifetime_anos: int | None = Field(default=None, ge=0, le=50)
    ativo: bool = True

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        return _obrigatorio(valor, "Nome do projeto")

    @field_validator("regiao")
    @classmethod
    def _validar_regiao(cls, valor: str) -> str:
        return normalizar_regiao(valor)


class Feriado(Registro):
    data: date
    descricao: str = ""


class TipoModelo(str, Enum):
    RFQ = "Solicitação de cotação"
    COBRANCA = "Cobrança"
    AGRADECIMENTO = "Agradecimento / status do projeto"
    CONDICAO = "Texto da condição"  # texto adicional do e-mail de RFQ (aba Condições)


class ModeloEmail(Registro):
    tipo: TipoModelo = TipoModelo.RFQ
    idioma: Idioma = Idioma.PT
    assunto: str = ""
    corpo: str = ""
    condicao_id: str | None = None  # só nos textos de condição

    @model_validator(mode="after")
    def _validar_textos(self) -> ModeloEmail:
        if self.tipo == TipoModelo.CONDICAO:
            # o texto da condição não tem assunto e pode ficar vazio (nada é acrescentado nesse idioma)
            if not self.condicao_id:
                raise ValueError("o texto da condição precisa indicar a condição")
        elif not self.assunto or not self.corpo:
            raise ValueError("Assunto e corpo é obrigatório")
        return self


class Condicao(Registro):
    """Texto adicional do e-mail de RFQ quando a commodity e/ou as regiões batem.

    Todos os critérios preenchidos precisam bater; critério vazio vale para qualquer valor. Os textos
    (português, espanhol e inglês) ficam na aba Corpo do E-mail, como ``ModeloEmail`` do tipo CONDICAO.
    """

    nome: str
    commodity_ids: list[str] = []
    regiao_fornecedor: str = ""
    regiao_projeto: str = ""
    ativo: bool = True

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, valor: str) -> str:
        return _obrigatorio(valor, "Nome da condição")

    @field_validator("regiao_fornecedor", "regiao_projeto")
    @classmethod
    def _validar_regiao(cls, valor: str) -> str:
        return normalizar_regiao(valor)

    @model_validator(mode="after")
    def _validar_criterios(self) -> Condicao:
        if not (self.commodity_ids or self.regiao_fornecedor or self.regiao_projeto):
            raise ValueError("escolha ao menos um critério: commodity, região do fornecedor ou região do projeto")
        return self


# ---------------------------------------------------------------- cotações


class Item(Modelo):
    id: str = ""  # identifica o item no pacote (a cotação por item de cada RFQ aponta para ele)
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

    def peso(self) -> float:
        """Multiplicador do preço no comparativo: volume anual; sem ele, a quantidade; sem ela, 1."""
        if self.volume_anual is not None:
            return self.volume_anual
        return self.quantidade if self.quantidade is not None else 1.0


class Pacote(Registro):
    """Pacote de cotação: o que se quer cotar (projeto + itens + anexos)."""

    titulo: str = ""
    projeto_id: str
    commodity_id: str | None = None
    data: date = Field(default_factory=date.today)
    prazo_dias_uteis: int = Field(default=4, ge=0, le=60)
    observacoes: str = ""
    itens: list[Item] = []
    anexos: list[str] = []
    # comparativo de propostas: moeda (vazia = moeda padrão) e câmbio de cada outra moeda para ela
    moeda_comparativo: str = ""
    cambios: dict[str, float] = {}

    @model_validator(mode="after")
    def _identificar_itens(self) -> Pacote:
        """Itens sem id: de pacotes até a v0.4 (todos sem id) recebem i1, i2… pela posição — o mesmo id a
        cada leitura até o pacote ser gravado; itens novos num pacote que já tem ids recebem um id novo."""
        if not any(not i.id for i in self.itens):
            return self
        legado = all(not i.id for i in self.itens)
        for posicao, item in enumerate(self.itens, start=1):
            if not item.id:
                item.id = f"i{posicao}" if legado else novo_id()
        return self

    @field_validator("cambios")
    @classmethod
    def _validar_cambios(cls, valor: dict[str, float]) -> dict[str, float]:
        if any(taxa <= 0 for taxa in valor.values()):
            raise ValueError("o câmbio deve ser maior que zero")
        return {moeda.strip().upper(): taxa for moeda, taxa in valor.items() if moeda.strip()}


class Evento(Modelo):
    data_hora: datetime = Field(default_factory=agora)
    descricao: str


class CotacaoItem(Modelo):
    """Resposta do fornecedor para um item do pacote (valores unitários, na moeda da RFQ)."""

    item_id: str
    preco: float | None = Field(default=None, ge=0)  # preço unitário da peça
    ferramental: float | None = Field(default=None, ge=0)  # tooling (valor total do item)
    lead_time_dias: int | None = Field(default=None, ge=0)
    frete: float | None = Field(default=None, ge=0)  # por peça
    embalagem: float | None = Field(default=None, ge=0)  # por peça

    def vazia(self) -> bool:
        return all(v is None for v in (self.preco, self.ferramental, self.lead_time_dias, self.frete, self.embalagem))

    def custo_unitario(self) -> float | None:
        """Preço + frete + embalagem por peça (None se não houver preço)."""
        if self.preco is None:
            return None
        return self.preco + (self.frete or 0) + (self.embalagem or 0)


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
    validade: date | None = None  # validade da proposta
    cotacao: list[CotacaoItem] = []  # cotação por item (comparativo de propostas)
    observacoes: str = ""
    # E-mail aberto para revisão em: a RFQ só passa a Enviada quando o envio é confirmado.
    aguardando_envio_desde: datetime | None = None
    assunto_email: str = ""  # assunto do e-mail de RFQ (a cobrança responde a ele)
    message_id: str = ""  # Message-ID do .eml gerado (a cobrança em .eml aponta para ele)
    historico: list[Evento] = []

    def atrasada(self, hoje: date | None = None) -> bool:
        hoje = hoje or date.today()
        return self.status == StatusRFQ.ENVIADA and self.prazo is not None and self.prazo < hoje

    def aguardando_envio(self) -> bool:
        return self.status == StatusRFQ.RASCUNHO and self.aguardando_envio_desde is not None

    def situacao(self, hoje: date | None = None) -> str:
        if self.aguardando_envio():
            return SITUACAO_AGUARDANDO
        return SITUACAO_ATRASADA if self.atrasada(hoje) else self.status.value

    def registrar(self, descricao: str) -> None:
        self.historico.append(Evento(descricao=descricao))

    def cotacao_do_item(self, item_id: str) -> CotacaoItem | None:
        return next((c for c in self.cotacao if c.item_id == item_id), None)


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
