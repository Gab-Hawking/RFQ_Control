"""Enviar e-mails: escolher a RFQ (pacote) e os fornecedores que vão receber."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..modelos import Idioma, MetodoEmail, StatusRFQ, TipoModelo
from ..servicos.disparo import Destinatario, ResultadoDisparo, disparar, situacao_fornecedores
from . import estilo
from .componentes import (
    CaixaBusca,
    Coluna,
    DelegadoBase,
    Tabela,
    avisar,
    botao,
    confirmar,
    executar,
    mostrar_resultado,
    sem_acentos,
)

SEM_COMMODITY = "__sem__"
# colunas da tabela de fornecedores
COL_ENVIAR, COL_FORNECEDOR, COL_COMMODITY, COL_IDIOMA, COL_EMAIL, COL_PACOTE = range(6)

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal


class DialogoEnvio(QDialog):
    """1) escolha a RFQ · 2) marque os fornecedores · 3) envie o e-mail padrão."""

    def __init__(
        self,
        janela: JanelaPrincipal,
        pacote_id: str | None = None,
        fornecedor_ids: list[str] | None = None,
        tipo: TipoModelo = TipoModelo.RFQ,
        pai=None,
    ):
        super().__init__(pai or janela)
        self.janela = janela
        self.base = janela.base
        self.resultado: ResultadoDisparo | None = None
        self._marcar_inicial = set(fornecedor_ids or [])
        self.setWindowTitle("Enviar e-mails de RFQ")
        self.resize(1340, 740)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        titulo = QLabel("Enviar e-mails de RFQ")
        titulo.setObjectName("tituloPagina")
        layout.addWidget(titulo)
        explicacao = QLabel(
            "Escolha a RFQ, marque os fornecedores e envie: cada um recebe o e-mail padrão no seu idioma, "
            "com a tabela de itens, os dados do projeto, o prazo e os anexos (Commodity Buyer em cópia). Quem "
            "ainda não tem RFQ neste pacote recebe um número novo automaticamente. E-mails abertos para revisão "
            "só contam como enviados quando aparecem nos Itens Enviados do Outlook."
        )
        explicacao.setObjectName("subtitulo")
        explicacao.setWordWrap(True)
        layout.addWidget(explicacao)

        divisor = QSplitter(Qt.Orientation.Horizontal)

        # ------------------------------------------------ 1. RFQ
        esquerda = QWidget()
        esquerda_layout = QVBoxLayout(esquerda)
        esquerda_layout.setContentsMargins(0, 0, 8, 0)
        passo1 = QLabel("1. Escolha a RFQ")
        passo1.setObjectName("tituloSecao")
        esquerda_layout.addWidget(passo1)
        self.busca_pacote = CaixaBusca("Buscar RFQ, projeto, cliente…")
        esquerda_layout.addWidget(self.busca_pacote)
        self.pacotes = Tabela([
            Coluna("RFQ / pacote", lambda p: p.titulo, largura=210, dica=lambda p: p.titulo),
            Coluna("Números", self._numeros, largura=160, dica=self._todos_numeros),
            Coluna("Commodity", lambda p: self.base.nomes_commodities(p.commodity_id), largura=120),
            Coluna("Itens", lambda p: len(p.itens), largura=50, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Data", lambda p: p.data, esticar=True),
        ], selecao_multipla=False)
        self.pacotes.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        self.busca_pacote.textChanged.connect(self.pacotes.filtro.definir_busca)
        self.pacotes.selectionModel().selectionChanged.connect(lambda *_: self._carregar_fornecedores())
        esquerda_layout.addWidget(self.pacotes, 1)
        divisor.addWidget(esquerda)

        # ------------------------------------------------ 2. fornecedores
        direita = QWidget()
        direita_layout = QVBoxLayout(direita)
        direita_layout.setContentsMargins(8, 0, 0, 0)
        passo2 = QLabel("2. Marque os fornecedores que vão receber")
        passo2.setObjectName("tituloSecao")
        direita_layout.addWidget(passo2)
        linha_busca = QHBoxLayout()
        self.busca_fornecedor = CaixaBusca("Buscar fornecedor, e-mail, commodity…")
        self.busca_fornecedor.textChanged.connect(lambda _t: self._filtrar_fornecedores())
        self.filtro_commodity = QComboBox()
        self.filtro_commodity.addItem("Todas as commodities", None)
        for commodity in sorted(self.base.commodities, key=lambda c: c.nome.casefold()):
            self.filtro_commodity.addItem(commodity.nome, commodity.id)
        self.filtro_commodity.addItem("Sem commodity", SEM_COMMODITY)
        self.filtro_commodity.currentIndexChanged.connect(lambda _i: self._filtrar_fornecedores())
        linha_busca.addWidget(self.busca_fornecedor, 1)
        linha_busca.addWidget(self.filtro_commodity)
        linha_busca.addWidget(botao("Marcar visíveis", lambda: self._marcar_todos(True)))
        linha_busca.addWidget(botao("Desmarcar", lambda: self._marcar_todos(False)))
        direita_layout.addLayout(linha_busca)
        self.fornecedores = QTableWidget(0, 6)
        self.fornecedores.setHorizontalHeaderLabels(
            ["Enviar", "Fornecedor", "Commodity", "Idioma", "E-mail (Para)", "Neste pacote"])
        self.fornecedores.verticalHeader().setVisible(False)
        self.fornecedores.verticalHeader().setDefaultSectionSize(34)
        self.fornecedores.setItemDelegate(DelegadoBase(self.fornecedores))
        self.fornecedores.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.fornecedores.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        cabecalho = self.fornecedores.horizontalHeader()
        for coluna, largura in ((COL_ENVIAR, 60), (COL_FORNECEDOR, 165), (COL_COMMODITY, 130), (COL_IDIOMA, 115),
                                (COL_EMAIL, 195)):
            self.fornecedores.setColumnWidth(coluna, largura)
        cabecalho.setSectionResizeMode(COL_PACOTE, QHeaderView.ResizeMode.Stretch)
        self.fornecedores.itemChanged.connect(lambda _: self._atualizar_botao())
        direita_layout.addWidget(self.fornecedores, 1)
        divisor.addWidget(direita)
        divisor.setSizes([520, 800])
        layout.addWidget(divisor, 1)

        # ------------------------------------------------ 3. como enviar
        passo3 = QLabel("3. Como enviar")
        passo3.setObjectName("tituloSecao")
        layout.addWidget(passo3)
        opcoes = QHBoxLayout()
        self.tipo = QComboBox()
        self.tipo.addItem("E-mail de solicitação de cotação", TipoModelo.RFQ)
        self.tipo.addItem("E-mail de cobrança (lembrete do prazo)", TipoModelo.COBRANCA)
        self.tipo.setCurrentIndex(self.tipo.findData(tipo))
        opcoes.addWidget(self.tipo)
        opcoes.addSpacing(16)
        self.revisar = QRadioButton("Abrir no Outlook para revisar antes de enviar")
        self.automatico = QRadioButton("Enviar automaticamente pelo Outlook")
        grupo = QButtonGroup(self)
        grupo.addButton(self.revisar)
        grupo.addButton(self.automatico)
        usa_outlook = self.base.configuracoes.metodo_email == MetodoEmail.OUTLOOK
        self.automatico.setEnabled(usa_outlook)
        if not usa_outlook:
            self.automatico.setToolTip("Disponível quando os e-mails são abertos via Outlook (Configurações).")
        (self.automatico if usa_outlook and self.base.configuracoes.envio_automatico else self.revisar).setChecked(True)
        self.automatico.toggled.connect(lambda _: self._atualizar_botao())
        opcoes.addWidget(self.revisar)
        opcoes.addWidget(self.automatico)
        opcoes.addStretch()
        layout.addLayout(opcoes)

        rodape = QHBoxLayout()
        self.resumo = QLabel()
        self.resumo.setObjectName("dica")
        rodape.addWidget(self.resumo, 1)
        rodape.addWidget(botao("Cancelar", self.reject))
        self.botao_enviar = botao("Enviar", self._enviar, primario=True)
        rodape.addWidget(self.botao_enviar)
        layout.addLayout(rodape)

        self._rfqs_por_pacote: dict[str, list] = {}
        self._carregar_pacotes(pacote_id)

    # ------------------------------------------------ dados
    def _numeros(self, pacote) -> str:
        numeros = sorted(r.numero for r in self._rfqs_por_pacote.get(pacote.id, []))
        if not numeros:
            return "—"
        if len(numeros) == 1:
            return numeros[0]
        return f"{numeros[0]} a {numeros[-1][-3:]}"

    def _todos_numeros(self, pacote) -> str:
        return ", ".join(sorted(r.numero for r in self._rfqs_por_pacote.get(pacote.id, [])))

    def _carregar_pacotes(self, selecionar: str | None) -> None:
        self._rfqs_por_pacote = {}
        for rfq in self.base.rfqs:
            if rfq.status != StatusRFQ.CANCELADA:
                self._rfqs_por_pacote.setdefault(rfq.pacote_id, []).append(rfq)
        self.pacotes.definir(self.base.pacotes.todos())
        visiveis = self.pacotes.visiveis()
        alvo = next((linha for linha, p in enumerate(visiveis) if p.id == selecionar), 0)
        if visiveis:
            self.pacotes.selectRow(alvo)
        self._carregar_fornecedores()

    def pacote_atual(self):
        return self.pacotes.atual()

    def _carregar_fornecedores(self) -> None:
        pacote = self.pacote_atual()
        self.fornecedores.blockSignals(True)
        self.fornecedores.setRowCount(0)
        if pacote is not None:
            for situacao in situacao_fornecedores(self.base, pacote.id):
                self._adicionar_fornecedor(situacao)
        self.fornecedores.blockSignals(False)
        self._marcar_inicial = set()
        self._filtrar_fornecedores()
        self._atualizar_botao()

    def _adicionar_fornecedor(self, situacao) -> None:
        linha = self.fornecedores.rowCount()
        self.fornecedores.insertRow(linha)
        fornecedor = situacao.fornecedor
        marcar = (
            fornecedor.id in self._marcar_inicial
            if self._marcar_inicial
            # rascunho ainda não aberto: os "Aguardando envio" já tiveram o e-mail aberto (evita duplicar)
            else situacao.rfq is not None and situacao.rfq.status == StatusRFQ.RASCUNHO
            and not situacao.rfq.aguardando_envio()
        )
        caixa = QTableWidgetItem()
        caixa.setData(Qt.ItemDataRole.UserRole, fornecedor.id)
        if situacao.tem_email:
            caixa.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            caixa.setCheckState(Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked)
        else:
            caixa.setFlags(Qt.ItemFlag.NoItemFlags)
            caixa.setToolTip("Sem e-mail (Para) cadastrado — complete na Base de dados.")
        caixa.setData(Qt.ItemDataRole.UserRole + 1, list(fornecedor.commodity_ids))
        self.fornecedores.setItem(linha, COL_ENVIAR, caixa)
        self.fornecedores.setItem(linha, COL_FORNECEDOR, QTableWidgetItem(fornecedor.nome))
        commodities = self.base.nomes_commodities(fornecedor.commodity_ids)
        celula_commodity = QTableWidgetItem(commodities or "—")
        celula_commodity.setToolTip(commodities)
        self.fornecedores.setItem(linha, COL_COMMODITY, celula_commodity)
        idioma = QComboBox()
        for opcao in Idioma:
            idioma.addItem(opcao.rotulo, opcao)
        idioma.setCurrentIndex(idioma.findData(situacao.idioma))
        idioma.setToolTip("Idioma do e-mail para este fornecedor")
        self.fornecedores.setCellWidget(linha, COL_IDIOMA, idioma)
        emails = "; ".join(fornecedor.emails_para()) or "⚠ sem e-mail cadastrado"
        self.fornecedores.setItem(linha, COL_EMAIL, QTableWidgetItem(emails))
        estado = QTableWidgetItem(situacao.descricao)
        estado.setToolTip(situacao.descricao)
        if situacao.rfq is None:
            estado.setForeground(QColor(estilo.TINTA_SUAVE))
        self.fornecedores.setItem(linha, COL_PACOTE, estado)
        if not situacao.tem_email:
            for coluna in (COL_FORNECEDOR, COL_COMMODITY, COL_EMAIL, COL_PACOTE):
                self.fornecedores.item(linha, coluna).setForeground(QColor(estilo.TINTA_SUAVE))

    def _filtrar_fornecedores(self) -> None:
        termos = sem_acentos(self.busca_fornecedor.text()).split()
        commodity = self.filtro_commodity.currentData()
        for linha in range(self.fornecedores.rowCount()):
            alvo = sem_acentos(" ".join(
                (self.fornecedores.item(linha, c).text() if self.fornecedores.item(linha, c) else "")
                for c in (COL_FORNECEDOR, COL_COMMODITY, COL_EMAIL, COL_PACOTE)
            ))
            ids = self.fornecedores.item(linha, COL_ENVIAR).data(Qt.ItemDataRole.UserRole + 1) or []
            visivel = all(t in alvo for t in termos) and (
                commodity is None or (commodity == SEM_COMMODITY and not ids) or commodity in ids
            )
            self.fornecedores.setRowHidden(linha, not visivel)

    def _marcar_todos(self, marcar: bool) -> None:
        self.fornecedores.blockSignals(True)
        for linha in range(self.fornecedores.rowCount()):
            item = self.fornecedores.item(linha, 0)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and (not marcar or not self.fornecedores.isRowHidden(linha)):
                item.setCheckState(Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked)
        self.fornecedores.blockSignals(False)
        self._atualizar_botao()

    def destinatarios(self) -> list[Destinatario]:
        lista = []
        for linha in range(self.fornecedores.rowCount()):
            item = self.fornecedores.item(linha, 0)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.checkState() == Qt.CheckState.Checked:
                idioma = Idioma(self.fornecedores.cellWidget(linha, COL_IDIOMA).currentData())
                lista.append(Destinatario(item.data(Qt.ItemDataRole.UserRole), idioma))
        return lista

    def marcar(self, fornecedor_ids: set[str]) -> None:
        for linha in range(self.fornecedores.rowCount()):
            item = self.fornecedores.item(linha, 0)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                marcado = item.data(Qt.ItemDataRole.UserRole) in fornecedor_ids
                item.setCheckState(Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked)

    def _atualizar_botao(self) -> None:
        total = len(self.destinatarios())
        acao = "Enviar" if self.automatico.isChecked() else "Abrir"
        self.botao_enviar.setText(f"{acao} e-mail para {total} fornecedor(es)" if total else f"{acao} e-mails")
        self.botao_enviar.setEnabled(bool(total))
        pacote = self.pacote_atual()
        self.resumo.setText(f"RFQ selecionada: {pacote.titulo}" if pacote else "Nenhuma RFQ cadastrada.")

    # ------------------------------------------------ envio
    def _enviar(self) -> None:
        pacote = self.pacote_atual()
        destinatarios = self.destinatarios()
        if pacote is None or not destinatarios:
            avisar(self, "Escolha a RFQ e marque pelo menos um fornecedor.")
            return
        automatico = self.automatico.isChecked()
        if automatico:
            nomes = [self.base.fornecedores.obter(d.fornecedor_id).nome for d in destinatarios]
            if not confirmar(
                self,
                f"Enviar agora {len(nomes)} e-mail(s) pelo Outlook, sem revisão?\n\n• " + "\n• ".join(nomes),
                "Enviar automaticamente",
                "Enviar agora",
            ):
                return
        if automatico != self.base.configuracoes.envio_automatico:
            executar(self, lambda: self.base.salvar_configuracoes(
                self.base.configuracoes.model_copy(update={"envio_automatico": automatico})))

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ok, resultado = executar(self, lambda: disparar(
                self.base, pacote.id, destinatarios, enviar=automatico, tipo=self.tipo.currentData()))
        finally:
            QApplication.restoreOverrideCursor()
        if not ok:
            return
        self.resultado = resultado
        resumo = resultado.resumo()
        if resultado.rfqs_criadas:
            resumo += "\nNovas RFQs: " + ", ".join(resultado.rfqs_criadas)
        detalhes = [
            f"{'✓' if i.ok else '✗'} {i.fornecedor}" + (f" — {i.numero}" if i.numero else "")
            + (f" ({i.idioma.rotulo})" if i.idioma else "") + f": {i.mensagem}"
            for i in resultado.itens
        ] + resultado.avisos
        self.janela.mensagem(resumo.replace("\n", " · "))
        if resultado.falhas or resultado.avisos or automatico:
            mostrar_resultado(self, "Envio de e-mails", resumo, "Fornecedores", detalhes)
        self.accept()
