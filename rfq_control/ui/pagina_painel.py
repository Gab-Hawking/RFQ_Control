"""Painel com indicadores das RFQs."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..modelos import SITUACAO_ATRASADA, Idioma, StatusRFQ
from ..servicos.dias_uteis import dias_uteis_entre
from ..servicos.formatos import data_por_extenso
from ..servicos.rfq import calcular_indicadores
from . import acoes, estilo
from .componentes import (
    CartaoIndicador,
    Coluna,
    DelegadoMedidor,
    GraficoBarras,
    GraficoColunas,
    Tabela,
    cabecalho_pagina,
)

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal

ORDEM_SITUACOES = [
    SITUACAO_ATRASADA,
    StatusRFQ.ENVIADA.value,
    StatusRFQ.RASCUNHO.value,
    StatusRFQ.RESPONDIDA.value,
    StatusRFQ.SELECIONADA.value,
    StatusRFQ.NAO_SELECIONADA.value,
    StatusRFQ.DECLINADA.value,
]


def _cartao_secao(titulo: str, subtitulo: str = "") -> tuple[QFrame, QVBoxLayout]:
    cartao = QFrame()
    cartao.setObjectName("cartao")
    layout = QVBoxLayout(cartao)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)
    rotulo = QLabel(titulo)
    rotulo.setObjectName("tituloSecao")
    layout.addWidget(rotulo)
    if subtitulo:
        sub = QLabel(subtitulo)
        sub.setObjectName("dica")
        layout.addWidget(sub)
    return cartao, layout


class PaginaPainel(QWidget):
    def __init__(self, janela: JanelaPrincipal):
        super().__init__()
        self.setObjectName("pagina")
        self.janela = janela
        self.base = janela.base
        self._hoje = date.today()
        self._feriados: set[date] = set()

        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        externo.addWidget(rolagem)
        conteudo = QWidget()
        conteudo.setObjectName("pagina")
        rolagem.setWidget(conteudo)

        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        self.cabecalho = cabecalho_pagina("Painel", "")
        layout.addWidget(self.cabecalho)
        self.subtitulo = self.cabecalho.findChild(QLabel, "subtitulo")
        if self.subtitulo is None:
            self.subtitulo = QLabel()
            self.subtitulo.setObjectName("subtitulo")
            self.cabecalho.layout().addWidget(self.subtitulo)

        # ------------------------------------------------ indicadores
        linha = QHBoxLayout()
        linha.setSpacing(12)
        self.cartao_abertas = CartaoIndicador("Em aberto")
        self.cartao_atrasadas = CartaoIndicador("Atrasadas")
        self.cartao_vencendo = CartaoIndicador("Vencem até o próximo dia útil")
        self.cartao_taxa = CartaoIndicador("Taxa de resposta")
        self.cartao_tempo = CartaoIndicador("Tempo médio de resposta")
        for cartao in (self.cartao_abertas, self.cartao_atrasadas, self.cartao_vencendo, self.cartao_taxa,
                       self.cartao_tempo):
            cartao.setCursor(Qt.CursorShape.PointingHandCursor)
            linha.addWidget(cartao)
        self.cartao_abertas.clicado.connect(lambda: self.janela.mostrar_rfqs("Em aberto"))
        self.cartao_atrasadas.clicado.connect(lambda: self.janela.mostrar_rfqs(SITUACAO_ATRASADA))
        self.cartao_vencendo.clicado.connect(lambda: self.janela.mostrar_rfqs("Em aberto"))
        self.cartao_taxa.clicado.connect(lambda: self.janela.mostrar_rfqs(StatusRFQ.RESPONDIDA.value))
        self.cartao_tempo.clicado.connect(lambda: self.janela.mostrar_rfqs(StatusRFQ.RESPONDIDA.value))
        layout.addLayout(linha)

        # ------------------------------------------------ gráficos
        grade = QGridLayout()
        grade.setHorizontalSpacing(12)
        grade.setVerticalSpacing(12)
        cartao_mes, layout_mes = _cartao_secao("RFQs por mês", "Últimos 12 meses, pela data de envio")
        self.grafico_mes = GraficoColunas("RFQs")
        layout_mes.addWidget(self.grafico_mes, 1)
        cartao_situacao, layout_situacao = _cartao_secao("RFQs por situação", "Clique em uma barra para ver a lista")
        self.grafico_situacao = GraficoBarras()
        self.grafico_situacao.barra_clicada.connect(self.janela.mostrar_rfqs)
        layout_situacao.addWidget(self.grafico_situacao)
        layout_situacao.addStretch()
        grade.addWidget(cartao_mes, 0, 0)
        grade.addWidget(cartao_situacao, 0, 1)

        cartao_pendencias, layout_pendencias = _cartao_secao(
            "Aguardando resposta", "RFQs enviadas, ordenadas pelo prazo (duplo clique para abrir)"
        )
        self.pendencias = Tabela([
            Coluna("RFQ Nº", lambda r: r.numero, largura=115),
            Coluna("Fornecedor", self._fornecedor, largura=170),
            Coluna("Prazo", lambda r: r.prazo, largura=105),
            Coluna("Dias", self._dias, largura=55, alinhamento=Qt.AlignmentFlag.AlignRight,
                   formato=lambda v: "" if v is None else f"{v:+d}",
                   dica=lambda r: "Dias úteis até o prazo (negativo = atrasada)"),
            Coluna("Projeto", self._projeto, esticar=True),
        ])
        self.pendencias.setMinimumHeight(260)
        self.pendencias.ativada.connect(self._abrir_rfq)
        layout_pendencias.addWidget(self.pendencias)

        cartao_fornecedores, layout_fornecedores = _cartao_secao(
            "Fornecedores", "RFQs enviadas, respostas e tempo médio (dias úteis)"
        )
        self.fornecedores = Tabela([
            Coluna("Fornecedor", lambda f: f.nome, largura=170),
            Coluna("RFQs", lambda f: f.total, largura=70, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Respondidas", lambda f: f.respondidas, largura=115, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Taxa de resposta", lambda f: f.taxa_resposta, largura=160),
            Coluna("Tempo médio", lambda f: f.media_dias, alinhamento=Qt.AlignmentFlag.AlignRight, esticar=True,
                   formato=lambda v: "" if v is None else f"{v:.1f}".replace(".", ",")),
        ], selecao_multipla=False)
        self.fornecedores.setItemDelegateForColumn(3, DelegadoMedidor(self.fornecedores))
        self.fornecedores.setMinimumHeight(260)
        layout_fornecedores.addWidget(self.fornecedores)
        grade.addWidget(cartao_pendencias, 1, 0)
        grade.addWidget(cartao_fornecedores, 1, 1)
        grade.setColumnStretch(0, 1)
        grade.setColumnStretch(1, 1)
        layout.addLayout(grade)
        layout.addStretch()

    # ------------------------------------------------ valores
    def _fornecedor(self, rfq) -> str:
        fornecedor = self.base.fornecedores.obter(rfq.fornecedor_id)
        return fornecedor.nome if fornecedor else ""

    def _projeto(self, rfq) -> str:
        projeto = self.base.projeto_do_pacote(self.base.pacotes.obter(rfq.pacote_id))
        return projeto.nome if projeto else ""

    def _dias(self, rfq) -> int | None:
        if not rfq.prazo:
            return None
        return dias_uteis_entre(self._hoje, rfq.prazo, self._feriados)

    def _abrir_rfq(self, rfq) -> None:
        if acoes.abrir_rfq(self.janela, rfq):
            self.atualizar()

    # ------------------------------------------------ atualização
    def atualizar(self) -> None:
        self._hoje = date.today()
        self._feriados = self.base.datas_feriados()
        ind = calcular_indicadores(self.base, self._hoje)
        self.subtitulo.setText(
            f"{data_por_extenso(self._hoje, Idioma.PT).capitalize()} · {ind.total} RFQ(s) registradas"
        )
        self.cartao_abertas.definir(str(ind.em_aberto), "enviadas aguardando resposta")
        self.cartao_atrasadas.definir(
            str(ind.atrasadas), "prazo vencido sem resposta", estilo.CRITICO if ind.atrasadas else None
        )
        self.cartao_vencendo.definir(
            str(ind.vencendo), "cobrar em breve", estilo.ALERTA if ind.vencendo else None
        )
        self.cartao_taxa.definir(f"{ind.taxa_resposta:.0%}", f"{ind.respondidas} respondida(s)")
        media = "—" if ind.media_dias_resposta is None else f"{ind.media_dias_resposta:.1f}".replace(".", ",")
        self.cartao_tempo.definir(media, "dias úteis entre envio e resposta")

        self.grafico_mes.definir(ind.por_mes)
        barras = [
            (situacao, ind.por_situacao[situacao],
             estilo.CRITICO if situacao == SITUACAO_ATRASADA else estilo.DESTAQUE)
            for situacao in ORDEM_SITUACOES if ind.por_situacao.get(situacao)
        ]
        self.grafico_situacao.definir(barras)
        self.pendencias.definir(ind.pendencias)
        self.fornecedores.definir(ind.fornecedores)
        self.fornecedores.sortByColumn(1, Qt.SortOrder.DescendingOrder)

