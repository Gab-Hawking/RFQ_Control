"""Comparativo de propostas de um pacote: fornecedores lado a lado, melhores valores e escolha da vencedora."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..servicos import rfq as srv
from ..servicos.cotacao import Comparativo, Proposta, comparar, definir_cambio
from ..servicos.exportacao import exportar_comparativo
from ..servicos.formatos import data_curta, numero_br, valor_monetario
from . import estilo
from .componentes import MOEDAS, DelegadoBase, avisar, botao, confirmar, executar

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal

FUNDO_MELHOR = QColor("#d6f0d6")
LEGENDA = (
    "Valores na moeda do comparativo. Custo unitário = preço + frete + embalagem; custo das peças = custo "
    "unitário × volume anual (ou quantidade). Verde: melhor valor — por item, entre as propostas com câmbio; "
    "no resumo, entre as propostas completas (todos os itens com preço)."
)


def _celula(texto: str, alinhar_direita: bool = False, melhor: bool = False, dica: str = "") -> QTableWidgetItem:
    celula = QTableWidgetItem(texto)
    celula.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    if alinhar_direita:
        celula.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if melhor:
        celula.setBackground(FUNDO_MELHOR)
        fonte = QFont()
        fonte.setBold(True)
        celula.setFont(fonte)
    if dica:
        celula.setToolTip(dica)
    return celula


def _abreviar(nome: str, limite: int = 18) -> str:
    return nome if len(nome) <= limite else nome[: limite - 1].rstrip() + "…"


def _tabela(colunas: list[str]) -> QTableWidget:
    tabela = QTableWidget(0, len(colunas))
    tabela.setHorizontalHeaderLabels(colunas)
    tabela.verticalHeader().setVisible(False)
    tabela.verticalHeader().setDefaultSectionSize(30)
    tabela.setItemDelegate(DelegadoBase(tabela))
    tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    return tabela


class DialogoComparativo(QDialog):
    def __init__(self, janela: JanelaPrincipal, pacote_id: str, pai=None):
        super().__init__(pai or janela)
        self.janela = janela
        self.base = janela.base
        self.pacote_id = pacote_id
        self.alterou = False
        self.comparativo: Comparativo | None = None
        self.resize(1200, 760)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.titulo = QLabel()
        self.titulo.setObjectName("tituloPagina")
        layout.addWidget(self.titulo)
        self.subtitulo = QLabel()
        self.subtitulo.setObjectName("dica")
        layout.addWidget(self.subtitulo)

        # ------------------------------------------------ moeda e câmbio
        linha_cambio = QHBoxLayout()
        formulario = QFormLayout()
        self.moeda = QComboBox()
        self.moeda.setEditable(True)
        self.moeda.addItems(MOEDAS)
        formulario.addRow("Moeda do comparativo", self.moeda)
        linha_cambio.addLayout(formulario)
        self.area_cambios = QWidget()
        self.layout_cambios = QHBoxLayout(self.area_cambios)
        self.layout_cambios.setContentsMargins(12, 0, 0, 0)
        linha_cambio.addWidget(self.area_cambios)
        linha_cambio.addWidget(botao("Aplicar câmbio", self._aplicar_cambio,
                                     dica="Grava a moeda e o câmbio neste pacote e recalcula o comparativo"))
        linha_cambio.addStretch()
        layout.addLayout(linha_cambio)
        self.campos_cambio: dict[str, QDoubleSpinBox] = {}

        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet(f"color:{estilo.TEXTO_FUNDO}; background:{estilo.SERIO}; border-radius:6px; "
                                 "padding:6px 10px;")
        layout.addWidget(self.aviso)

        # ------------------------------------------------ resumo por proposta
        rotulo = QLabel("Propostas")
        rotulo.setObjectName("tituloSecao")
        layout.addWidget(rotulo)
        self.resumo = _tabela([
            "RFQ Nº", "Fornecedor", "Situação", "Moeda", "Validade", "Itens com preço", "Custo das peças",
            "Ferramental", "Maior lead time (dias)",
        ])
        self.resumo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.resumo.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.resumo.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for coluna, largura in enumerate([115, 200, 130, 70, 95, 150, 150, 130, 160]):
            if coluna != 1:
                self.resumo.setColumnWidth(coluna, largura)
        self.resumo.setMaximumHeight(210)
        self.resumo.cellDoubleClicked.connect(lambda *_: self._abrir_rfq())
        layout.addWidget(self.resumo)

        # ------------------------------------------------ itens lado a lado
        rotulo = QLabel("Itens lado a lado")
        rotulo.setObjectName("tituloSecao")
        layout.addWidget(rotulo)
        self.itens = _tabela([])
        layout.addWidget(self.itens, 1)
        legenda = QLabel(LEGENDA)
        legenda.setObjectName("dica")
        legenda.setWordWrap(True)
        layout.addWidget(legenda)

        botoes = QHBoxLayout()
        botoes.addWidget(botao("Abrir RFQ", self._abrir_rfq, dica="Abre a RFQ da proposta selecionada (duplo clique)"))
        botoes.addWidget(botao("Selecionar vencedora", self._vencedora,
                               dica="Marca a proposta selecionada como Selecionada e as outras respondidas como "
                                    "Não selecionada"))
        botoes.addWidget(botao("Exportar para Excel", self._exportar))
        botoes.addStretch()
        botoes.addWidget(botao("Fechar", self.accept, primario=True))
        layout.addLayout(botoes)
        self.atualizar()

    # ------------------------------------------------ exibição
    def atualizar(self) -> None:
        ok, comparativo = executar(self, lambda: comparar(self.base, self.pacote_id))
        if not ok:
            return
        self.comparativo = comparativo
        pacote = comparativo.pacote
        projeto = self.base.projeto_do_pacote(pacote)
        self.setWindowTitle(f"Comparativo — {pacote.titulo}")
        self.titulo.setText(f"Comparativo — {pacote.titulo}")
        self.subtitulo.setText(
            " · ".join(p for p in (projeto.nome if projeto else "", projeto.cliente if projeto else "") if p)
            + f" · {len(comparativo.itens)} item(ns) · {len(comparativo.propostas)} proposta(s) com cotação"
        )
        self.moeda.setCurrentText(comparativo.moeda)
        self._montar_cambios(comparativo)
        avisos = []
        if comparativo.moedas_sem_cambio:
            avisos.append("Informe o câmbio de " + ", ".join(comparativo.moedas_sem_cambio)
                          + f" para {comparativo.moeda}: essas propostas ficam fora dos destaques.")
        if comparativo.sem_cotacao:
            avisos.append("Ainda sem cotação por item: " + ", ".join(
                f"{r.numero} ({self._nome_fornecedor(r.fornecedor_id)})" for r in comparativo.sem_cotacao)
                + " — registre na aba Cotação da RFQ.")
        self.aviso.setText("\n".join(avisos))
        self.aviso.setVisible(bool(avisos))
        self._montar_resumo(comparativo)
        self._montar_itens(comparativo)

    def _nome_fornecedor(self, fornecedor_id: str) -> str:
        fornecedor = self.base.fornecedores.obter(fornecedor_id)
        return fornecedor.nome if fornecedor else "?"

    def _montar_cambios(self, comparativo: Comparativo) -> None:
        while self.layout_cambios.count():
            item = self.layout_cambios.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.campos_cambio = {}
        moedas = sorted({p.moeda for p in comparativo.propostas if p.moeda != comparativo.moeda})
        for moeda in moedas:
            campo = QDoubleSpinBox()
            campo.setDecimals(4)
            campo.setRange(0, 1e6)
            campo.setSpecialValueText("—")
            campo.setValue(comparativo.pacote.cambios.get(moeda, 0))
            campo.setToolTip(f"Quanto vale 1 {moeda} em {comparativo.moeda}")
            self.layout_cambios.addWidget(QLabel(f"1 {moeda} ="))
            self.layout_cambios.addWidget(campo)
            self.layout_cambios.addWidget(QLabel(comparativo.moeda))
            self.layout_cambios.addSpacing(12)
            self.campos_cambio[moeda] = campo

    def _montar_resumo(self, comparativo: Comparativo) -> None:
        total_itens = len(comparativo.itens)
        self.resumo.setRowCount(len(comparativo.propostas))
        for linha, proposta in enumerate(comparativo.propostas):
            rfq = proposta.rfq
            completa = "" if proposta.completa else " (incompleta)"
            valores = [
                _celula(rfq.numero), _celula(proposta.fornecedor), _celula(rfq.situacao()), _celula(proposta.moeda),
                _celula(data_curta(rfq.validade)),
                _celula(f"{proposta.itens_cotados}/{total_itens}{completa}", True),
                _celula(valor_monetario(proposta.total_pecas), True, rfq.id in comparativo.melhor_total,
                        self._dica_conversao(proposta) if proposta.completa else
                        "Proposta incompleta: o custo não inclui os itens sem preço (fora da comparação)"),
                _celula(valor_monetario(proposta.ferramental), True, rfq.id in comparativo.melhor_ferramental,
                        self._dica_conversao(proposta)),
                _celula("" if proposta.lead_time is None else str(proposta.lead_time), True,
                        rfq.id in comparativo.melhor_lead_time),
            ]
            if not proposta.completa:  # totais de proposta incompleta não são comparáveis
                for celula in valores[6:]:
                    celula.setForeground(QColor(estilo.TINTA_SUAVE))
            for coluna, celula in enumerate(valores):
                celula.setData(Qt.ItemDataRole.UserRole, rfq.id)
                self.resumo.setItem(linha, coluna, celula)

    def _dica_conversao(self, proposta: Proposta) -> str:
        if proposta.taxa is None:
            return f"Sem câmbio de {proposta.moeda}: valor fora do comparativo"
        if proposta.moeda != self.comparativo.moeda:
            return f"Convertido de {proposta.moeda} (1 {proposta.moeda} = {proposta.taxa:g} {self.comparativo.moeda})"
        return ""

    def _montar_itens(self, comparativo: Comparativo) -> None:
        fixas = ["#", "OP - Ref", "CDC - Ref", "Volume anual"]
        self.itens.clear()
        self.itens.setColumnCount(len(fixas) + 3 * len(comparativo.propostas))
        self.itens.setHorizontalHeaderLabels(fixas)
        for indice, proposta in enumerate(comparativo.propostas):
            nome = _abreviar(proposta.fornecedor)
            for passo, rotulo in enumerate(("Custo unit.", "Ferramental", "Lead time")):
                cabecalho = QTableWidgetItem(f"{nome}\n{rotulo}")
                cabecalho.setToolTip(f"{proposta.fornecedor} ({proposta.rfq.numero}) — {rotulo}")
                self.itens.setHorizontalHeaderItem(len(fixas) + 3 * indice + passo, cabecalho)
        self.itens.setRowCount(len(comparativo.itens))
        for coluna, largura in enumerate([40, 150, 190, 105]):
            self.itens.setColumnWidth(coluna, largura)
        for coluna in range(len(fixas), self.itens.columnCount()):
            self.itens.setColumnWidth(coluna, 135)
        for linha, item in enumerate(comparativo.itens):
            fixos = [str(linha + 1), item.ref_op, item.ref_cdc, numero_br(item.volume_anual)]
            for coluna, texto in enumerate(fixos):
                self.itens.setItem(linha, coluna, _celula(texto, coluna in (0, 3)))
            coluna = len(fixas)
            for proposta in comparativo.propostas:
                cotacao = proposta.item(item.id)
                if cotacao is None:
                    for _ in range(3):
                        self.itens.setItem(linha, coluna, _celula("—", True, dica="Item sem cotação"))
                        coluna += 1
                    continue
                detalhe = (f"Preço {valor_monetario(cotacao.preco) or '—'} + frete {valor_monetario(cotacao.frete) or '0'}"
                           f" + embalagem {valor_monetario(cotacao.embalagem) or '0'} ({proposta.moeda})")
                celulas = [
                    _celula(valor_monetario(proposta.converter(cotacao.custo_unitario())), True,
                            comparativo.melhor(item.id, "custo", proposta.rfq.id), detalhe),
                    _celula(valor_monetario(proposta.converter(cotacao.ferramental)), True,
                            comparativo.melhor(item.id, "ferramental", proposta.rfq.id), self._dica_conversao(proposta)),
                    _celula("" if cotacao.lead_time_dias is None else str(cotacao.lead_time_dias), True,
                            comparativo.melhor(item.id, "lead_time", proposta.rfq.id)),
                ]
                for celula in celulas:
                    self.itens.setItem(linha, coluna, celula)
                    coluna += 1
        self.itens.horizontalHeader().setMinimumHeight(46)

    # ------------------------------------------------ ações
    def proposta_selecionada(self) -> Proposta | None:
        linha = self.resumo.currentRow()
        if self.comparativo is None or linha < 0 or linha >= len(self.comparativo.propostas):
            return None
        return self.comparativo.propostas[linha]

    def _aplicar_cambio(self) -> None:
        cambios = {moeda: campo.value() for moeda, campo in self.campos_cambio.items()}
        ok, _ = executar(self, lambda: definir_cambio(self.base, self.pacote_id, self.moeda.currentText(), cambios))
        if ok:
            self.alterou = True
            self.atualizar()

    def _abrir_rfq(self) -> None:
        from . import acoes

        proposta = self.proposta_selecionada()
        if proposta is None:
            avisar(self, "Selecione uma proposta na tabela.")
            return
        if acoes.abrir_rfq(self.janela, proposta.rfq):
            self.alterou = True
            self.atualizar()

    def _vencedora(self) -> None:
        proposta = self.proposta_selecionada()
        if proposta is None:
            avisar(self, "Selecione a proposta vencedora na tabela.")
            return
        if not confirmar(self, f"Selecionar a proposta de {proposta.fornecedor} ({proposta.rfq.numero})? As demais "
                               "RFQs respondidas do pacote ficam como 'Não selecionada'.",
                         "Selecionar vencedora", "Selecionar"):
            return
        ok, _ = executar(self, lambda: srv.selecionar_vencedora(self.base, proposta.rfq.id))
        if ok:
            self.alterou = True
            self.janela.mensagem(f"{proposta.rfq.numero} ({proposta.fornecedor}) selecionada.")
            self.atualizar()

    def _exportar(self) -> None:
        nome = f"Comparativo {self.comparativo.pacote.titulo if self.comparativo else ''} {date.today():%Y-%m-%d}.xlsx"
        nome = "".join(c for c in nome if c not in '\\/:*?"<>|')
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar comparativo", str(Path.home() / nome),
                                                 "Planilha Excel (*.xlsx)")
        if not caminho:
            return
        ok, destino = executar(self, lambda: exportar_comparativo(self.base, self.pacote_id, Path(caminho)))
        if ok:
            from .pagina_base_dados import _oferecer_abrir

            _oferecer_abrir(self.janela, destino, "Comparativo exportado")
