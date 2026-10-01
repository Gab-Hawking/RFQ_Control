"""Pacotes de cotação e comparação das RFQs de cada pacote."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from ..modelos import STATUS_COM_RESPOSTA, Pacote, StatusRFQ
from ..servicos import rfq as srv
from ..servicos.formatos import numero_br
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


class PaginaPacotes(QWidget):
    def __init__(self, janela: JanelaPrincipal):
        super().__init__()
        self.setObjectName("pagina")
        self.janela = janela
        self.base = janela.base
        self._rfqs_por_pacote: dict[str, list] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(cabecalho_pagina(
            "Pacotes de cotação",
            "Cada pacote reúne projeto, itens e anexos, e pode ser enviado a vários fornecedores (uma RFQ por fornecedor).",
        ))

        barra = QHBoxLayout()
        self.busca = CaixaBusca("Buscar pacote, projeto, cliente…")
        barra.addWidget(self.busca, 1)
        barra.addWidget(botao("+ Nova solicitação", self._nova, primario=True))
        barra.addWidget(botao("Abrir / editar", self._editar))
        barra.addWidget(botao("Enviar e-mails…", self._enviar,
                              dica="Escolher os fornecedores que vão receber esta RFQ"))
        barra.addWidget(botao("Duplicar", self._duplicar, dica="Cria um novo pacote com os mesmos itens e anexos"))
        barra.addWidget(botao("Excluir", self._excluir, perigo=True))
        layout.addLayout(barra)

        divisor = QSplitter(Qt.Orientation.Vertical)
        self.tabela = Tabela([
            Coluna("Pacote", lambda p: p.titulo, largura=280),
            Coluna("Projeto", lambda p: self._projeto(p)[0], largura=170),
            Coluna("Cliente", lambda p: self._projeto(p)[1], largura=110),
            Coluna("Data", lambda p: p.data, largura=95),
            Coluna("Itens", lambda p: len(p.itens), largura=65, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("RFQs", lambda p: self._contagem(p)[0], largura=65, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Respondidas", lambda p: self._contagem(p)[1], largura=115, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Em aberto", lambda p: self._contagem(p)[2], largura=100, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Anexos", lambda p: len(p.anexos), largura=80, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Solicitante", self._solicitante, esticar=True),
        ], selecao_multipla=False)
        self.tabela.ativada.connect(lambda p: self._abrir(p))
        self.tabela.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        self.tabela.selectionModel().selectionChanged.connect(lambda *_: self._mostrar_rfqs())
        self.busca.textChanged.connect(self.tabela.filtro.definir_busca)
        divisor.addWidget(self.tabela)

        detalhe = QWidget()
        detalhe_layout = QVBoxLayout(detalhe)
        detalhe_layout.setContentsMargins(0, 8, 0, 0)
        self.titulo_rfqs = QLabel("RFQs do pacote")
        self.titulo_rfqs.setObjectName("tituloSecao")
        detalhe_layout.addWidget(self.titulo_rfqs)
        self.rfqs = Tabela([
            Coluna("RFQ Nº", lambda r: r.numero, largura=125),
            Coluna("Fornecedor", self._fornecedor, largura=240),
            Coluna("Situação", lambda r: r.situacao(), largura=150),
            Coluna("Envio", lambda r: r.data_envio, largura=95),
            Coluna("Prazo", lambda r: r.prazo, largura=95),
            Coluna("Resposta", lambda r: r.data_resposta, largura=95),
            Coluna("Valor", lambda r: r.valor_total, largura=130, alinhamento=Qt.AlignmentFlag.AlignRight,
                   formato=lambda v: "" if v is None else numero_br(v, 2)),
            Coluna("Moeda", lambda r: r.moeda if r.valor_total is not None else "", largura=65),
            Coluna("Lead time", lambda r: r.lead_time, esticar=True),
        ])
        self.rfqs.setItemDelegateForColumn(2, DelegadoSituacao(self.rfqs))
        self.rfqs.ativada.connect(self._abrir_rfq)
        detalhe_layout.addWidget(self.rfqs)
        divisor.addWidget(detalhe)
        divisor.setSizes([420, 260])
        layout.addWidget(divisor, 1)

    # ------------------------------------------------ valores
    def _projeto(self, pacote: Pacote) -> tuple[str, str]:
        projeto = self.base.projeto_do_pacote(pacote)
        return (projeto.nome, projeto.cliente) if projeto else ("", "")

    def _solicitante(self, pacote: Pacote) -> str:
        solicitante = self.base.solicitantes.obter(pacote.solicitante_id)
        return solicitante.nome if solicitante else ""

    def _contagem(self, pacote: Pacote) -> tuple[int, int, int]:
        rfqs = [r for r in self._rfqs_por_pacote.get(pacote.id, []) if r.status != StatusRFQ.CANCELADA]
        respondidas = sum(1 for r in rfqs if r.status in STATUS_COM_RESPOSTA)
        abertas = sum(1 for r in rfqs if r.status == StatusRFQ.ENVIADA)
        return len(rfqs), respondidas, abertas

    def _fornecedor(self, rfq) -> str:
        fornecedor = self.base.fornecedores.obter(rfq.fornecedor_id)
        return fornecedor.nome if fornecedor else ""

    # ------------------------------------------------ atualização
    def atualizar(self) -> None:
        self._rfqs_por_pacote = {}
        for rfq in self.base.rfqs:
            self._rfqs_por_pacote.setdefault(rfq.pacote_id, []).append(rfq)
        self.tabela.definir(self.base.pacotes.todos())
        if not self.tabela.selecionados() and self.tabela.filtro.rowCount():
            self.tabela.selectRow(0)
        self._mostrar_rfqs()

    def _mostrar_rfqs(self) -> None:
        pacote = self.tabela.atual()
        if not pacote:
            self.titulo_rfqs.setText("RFQs do pacote — selecione um pacote acima")
            self.rfqs.definir([])
            return
        rfqs = self.base.rfqs_do_pacote(pacote.id)
        self.titulo_rfqs.setText(f"RFQs do pacote “{pacote.titulo}” ({len(rfqs)})")
        self.rfqs.definir(rfqs)

    # ------------------------------------------------ ações
    def _nova(self) -> None:
        if acoes.nova_solicitacao(self.janela):
            self.atualizar()

    def _abrir(self, pacote: Pacote | None, aba: str = "itens") -> None:
        if pacote is None:
            avisar(self, "Selecione um pacote.")
            return
        if acoes.abrir_pacote(self.janela, pacote.id, aba):
            self.atualizar()

    def _editar(self) -> None:
        self._abrir(self.tabela.atual())

    def _enviar(self) -> None:
        pacote = self.tabela.atual()
        if acoes.enviar_emails(self.janela, pacote.id if pacote else None):
            self.atualizar()

    def _abrir_rfq(self, rfq) -> None:
        if acoes.abrir_rfq(self.janela, rfq):
            self.atualizar()

    def _duplicar(self) -> None:
        pacote = self.tabela.atual()
        if not pacote:
            avisar(self, "Selecione um pacote.")
            return
        ok, copia = executar(self, lambda: srv.duplicar_pacote(self.base, pacote.id))
        if ok:
            self.janela.mensagem(f"Pacote duplicado: {copia.titulo}")
            self.atualizar()
            self._abrir(copia, "fornecedores")

    def _excluir(self) -> None:
        pacote = self.tabela.atual()
        if not pacote:
            avisar(self, "Selecione um pacote.")
            return
        if not confirmar(self, f"Excluir o pacote '{pacote.titulo}' e suas RFQs em rascunho?", "Excluir", "Excluir"):
            return
        ok, _ = executar(self, lambda: srv.excluir_pacote(self.base, pacote.id))
        if ok:
            self.janela.mensagem("Pacote excluído.")
            self.atualizar()
