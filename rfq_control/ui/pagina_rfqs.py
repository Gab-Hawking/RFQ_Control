"""Lista de RFQs (substitui a aba Controle da planilha)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..modelos import RFQ, SITUACAO_ATRASADA, Idioma, StatusRFQ, TipoModelo
from ..servicos.dias_uteis import dias_uteis_entre
from ..servicos.exportacao import exportar_rfqs
from ..servicos.envio_email import abrir_arquivo
from ..servicos.formatos import numero_br
from ..servicos.rfq import excluir_rfq
from . import acoes
from .componentes import (
    CaixaBusca,
    Coluna,
    DelegadoSituacao,
    Tabela,
    avisar,
    botao,
    cabecalho_pagina,
    confirmar,
    executar,
)

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal

FILTRO_TODAS = "Todas"
FILTRO_ABERTAS = "Em aberto (enviadas)"


class PaginaRFQs(QWidget):
    def __init__(self, janela: JanelaPrincipal):
        super().__init__()
        self.setObjectName("pagina")
        self.janela = janela
        self.base = janela.base
        self._hoje = date.today()
        self._feriados: set[date] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(cabecalho_pagina(
            "RFQs", "Todas as solicitações de cotação enviadas aos fornecedores (antiga aba Controle)."
        ))

        filtros = QHBoxLayout()
        self.busca = CaixaBusca("Buscar número, fornecedor, projeto, cliente…")
        self.situacao = QComboBox()
        self.situacao.addItems([FILTRO_TODAS, FILTRO_ABERTAS, SITUACAO_ATRASADA] + [s.value for s in StatusRFQ])
        self.projeto = QComboBox()
        self.fornecedor = QComboBox()
        self.ano = QComboBox()
        for combo, largura in ((self.situacao, 170), (self.projeto, 200), (self.fornecedor, 200), (self.ano, 90)):
            combo.setMinimumWidth(largura)
            combo.currentIndexChanged.connect(lambda _: self.atualizar(recarregar_filtros=False))
        filtros.addWidget(self.busca, 1)
        filtros.addWidget(QLabel("Situação"))
        filtros.addWidget(self.situacao)
        filtros.addWidget(self.projeto)
        filtros.addWidget(self.fornecedor)
        filtros.addWidget(self.ano)
        layout.addLayout(filtros)

        botoes = QHBoxLayout()
        botoes.addWidget(botao("+ Nova solicitação", self._nova, primario=True, dica="Ctrl+N"))
        botoes.addWidget(botao("Abrir", self._abrir, dica="Enter ou duplo clique"))
        botoes.addWidget(botao("E-mail PT", lambda: self._emails(Idioma.PT), dica="Ctrl+E"))
        botoes.addWidget(botao("E-mail EN", lambda: self._emails(Idioma.EN), dica="Ctrl+R"))
        botoes.addWidget(botao("Cobrança", lambda: self._emails(None, TipoModelo.COBRANCA),
                               dica="E-mail lembrando o prazo às RFQs selecionadas"))
        botoes.addWidget(botao("Alterar status", self._status))
        botoes.addStretch()
        botoes.addWidget(botao("Excluir rascunho", self._excluir, perigo=True))
        botoes.addWidget(botao("Exportar para Excel", self._exportar))
        layout.addLayout(botoes)

        colunas = [
            Coluna("RFQ Nº", lambda r: r.numero, largura=125),
            Coluna("Situação", lambda r: r.situacao(self._hoje), largura=150),
            Coluna("Envio", lambda r: r.data_envio, largura=95),
            Coluna("Prazo", lambda r: r.prazo, largura=95),
            Coluna("Dias", self._dias_restantes, largura=60, alinhamento=Qt.AlignmentFlag.AlignRight,
                   formato=lambda v: "" if v is None else f"{v:+d}",
                   dica=lambda r: "Dias úteis até o prazo (negativo = atrasada)"),
            Coluna("Fornecedor", self._fornecedor, largura=210),
            Coluna("Projeto", lambda r: self._projeto(r)[0], largura=190),
            Coluna("Cliente", lambda r: self._projeto(r)[1], largura=110),
            Coluna("Itens", self._itens, largura=55, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Solicitante", self._solicitante, largura=130),
            Coluna("Valor", lambda r: r.valor_total, largura=120, alinhamento=Qt.AlignmentFlag.AlignRight,
                   formato=lambda v: "" if v is None else numero_br(v, 2)),
            Coluna("Pacote", self._pacote, esticar=True),
        ]
        self.tabela = Tabela(colunas)
        self.tabela.setItemDelegateForColumn(1, DelegadoSituacao(self.tabela))
        self.tabela.ativada.connect(self._abrir_rfq)
        self.tabela.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        self.busca.textChanged.connect(self._buscar)
        layout.addWidget(self.tabela, 1)
        self.contador = QLabel()
        self.contador.setObjectName("dica")
        layout.addWidget(self.contador)

        QShortcut(QKeySequence("Ctrl+E"), self, activated=lambda: self._emails(Idioma.PT))
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self._emails(Idioma.EN))
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.busca.setFocus)

    # ------------------------------------------------ valores das colunas
    def _pacote_de(self, rfq: RFQ):
        return self.base.pacotes.obter(rfq.pacote_id)

    def _projeto(self, rfq: RFQ) -> tuple[str, str]:
        projeto = self.base.projeto_do_pacote(self._pacote_de(rfq))
        return (projeto.nome, projeto.cliente) if projeto else ("", "")

    def _fornecedor(self, rfq: RFQ) -> str:
        fornecedor = self.base.fornecedores.obter(rfq.fornecedor_id)
        return fornecedor.nome if fornecedor else ""

    def _itens(self, rfq: RFQ) -> int:
        pacote = self._pacote_de(rfq)
        return len(pacote.itens) if pacote else 0

    def _solicitante(self, rfq: RFQ) -> str:
        pacote = self._pacote_de(rfq)
        solicitante = self.base.solicitantes.obter(pacote.solicitante_id) if pacote else None
        return solicitante.nome if solicitante else ""

    def _pacote(self, rfq: RFQ) -> str:
        pacote = self._pacote_de(rfq)
        return pacote.titulo if pacote else ""

    def _dias_restantes(self, rfq: RFQ) -> int | None:
        if rfq.status != StatusRFQ.ENVIADA or not rfq.prazo:
            return None
        return dias_uteis_entre(self._hoje, rfq.prazo, self._feriados)

    # ------------------------------------------------ filtros
    def _recarregar_filtros(self) -> None:
        def preencher(combo: QComboBox, primeiro: str, opcoes: list[tuple[str, str]]) -> None:
            atual = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(primeiro, None)
            for texto, dado in opcoes:
                combo.addItem(texto, dado)
            combo.setCurrentIndex(max(0, combo.findData(atual)))
            combo.blockSignals(False)

        preencher(self.projeto, "Todos os projetos",
                  [(p.nome, p.id) for p in sorted(self.base.projetos, key=lambda p: p.nome.casefold())])
        preencher(self.fornecedor, "Todos os fornecedores",
                  [(f.nome, f.id) for f in sorted(self.base.fornecedores, key=lambda f: f.nome.casefold())])
        anos = sorted({(r.data_envio or r.data_criacao).year for r in self.base.rfqs}, reverse=True)
        preencher(self.ano, "Todos os anos", [(str(a), a) for a in anos])

    def filtrar_situacao(self, situacao: str) -> None:
        indice = self.situacao.findText(situacao)
        if situacao == "Em aberto":
            indice = self.situacao.findText(FILTRO_ABERTAS)
        self.situacao.setCurrentIndex(max(0, indice))

    def _aceita(self, rfq: RFQ) -> bool:
        situacao = self.situacao.currentText()
        if situacao == FILTRO_ABERTAS and rfq.status != StatusRFQ.ENVIADA:
            return False
        if situacao not in (FILTRO_TODAS, FILTRO_ABERTAS) and rfq.situacao(self._hoje) != situacao:
            return False
        if self.fornecedor.currentData() and rfq.fornecedor_id != self.fornecedor.currentData():
            return False
        if self.projeto.currentData():
            pacote = self._pacote_de(rfq)
            if not pacote or pacote.projeto_id != self.projeto.currentData():
                return False
        if self.ano.currentData() and (rfq.data_envio or rfq.data_criacao).year != self.ano.currentData():
            return False
        return True

    def atualizar(self, recarregar_filtros: bool = True) -> None:
        self._hoje = date.today()
        self._feriados = self.base.datas_feriados()
        if recarregar_filtros:
            self._recarregar_filtros()
        rfqs = [r for r in self.base.rfqs if self._aceita(r)]
        self.tabela.definir(rfqs)
        self._atualizar_contador()

    def _buscar(self, texto: str) -> None:
        self.tabela.filtro.definir_busca(texto)
        self._atualizar_contador()

    def _atualizar_contador(self) -> None:
        visiveis = self.tabela.visiveis()
        atrasadas = sum(1 for r in visiveis if r.atrasada(self._hoje))
        texto = f"{len(visiveis)} RFQ(s)"
        if atrasadas:
            texto += f" · {atrasadas} atrasada(s)"
        self.contador.setText(texto)

    # ------------------------------------------------ ações
    def _nova(self) -> None:
        if acoes.nova_solicitacao(self.janela):
            self.atualizar()

    def _abrir_rfq(self, rfq: RFQ) -> None:
        if acoes.abrir_rfq(self.janela, rfq):
            self.atualizar(recarregar_filtros=False)

    def _abrir(self) -> None:
        self._abrir_rfq(self.tabela.atual())

    def _emails(self, idioma: Idioma | None, tipo: TipoModelo = TipoModelo.RFQ) -> None:
        if acoes.gerar_emails(self.janela, self.tabela.selecionados(), idioma, tipo):
            self.atualizar(recarregar_filtros=False)

    def _status(self) -> None:
        if acoes.alterar_status(self.janela, self.tabela.selecionados()):
            self.atualizar(recarregar_filtros=False)

    def _excluir(self) -> None:
        selecionadas = self.tabela.selecionados()
        if not selecionadas:
            avisar(self, "Selecione as RFQs em rascunho que deseja excluir.")
            return
        numeros = ", ".join(r.numero for r in selecionadas)
        if not confirmar(self, f"Excluir {numeros}?", "Excluir", "Excluir"):
            return
        for rfq in selecionadas:
            ok, _ = executar(self, lambda r=rfq: excluir_rfq(self.base, r.id))
            if not ok:
                break
        self.atualizar(recarregar_filtros=False)

    def _exportar(self) -> None:
        sugestao = str(Path.home() / f"RFQs_{date.today():%Y-%m-%d}.xlsx")
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar RFQs", sugestao, "Planilha Excel (*.xlsx)")
        if not caminho:
            return
        ok, destino = executar(self, lambda: exportar_rfqs(self.base, Path(caminho), self.tabela.visiveis()))
        if ok:
            self.janela.mensagem(f"Exportado: {destino}")
            if confirmar(self, f"Arquivo gerado:\n{destino}\n\nAbrir agora?", "Exportação concluída", "Abrir"):
                executar(self, lambda: abrir_arquivo(destino))
