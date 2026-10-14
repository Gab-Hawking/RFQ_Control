"""Agradecimento / status do projeto: escolher o projeto, marcar as RFQs e avisar os fornecedores."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
)

from ..modelos import MetodoEmail, StatusRFQ
from ..padroes import MOTIVOS_AGRADECIMENTO
from ..servicos import agradecimento as servico
from ..servicos.formatos import data_curta
from .componentes import DelegadoBase, avisar, botao, confirmar, executar, mostrar_resultado

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal

NAO_ALTERAR = "Não alterar"
COL_MARCAR, COL_NUMERO, COL_FORNECEDOR, COL_SITUACAO, COL_ENVIO, COL_PACOTE, COL_IDIOMA = range(7)


class DialogoAgradecimento(QDialog):
    """Um e-mail por fornecedor, agradecendo e informando a situação do projeto (ex.: declinado)."""

    def __init__(self, janela: JanelaPrincipal, projeto_id: str | None = None, pai=None):
        super().__init__(pai or janela)
        self.janela = janela
        self.base = janela.base
        self.resultado = None
        self.setWindowTitle("Agradecimento / status do projeto")
        self.resize(1120, 700)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        titulo = QLabel("Agradecimento / status do projeto")
        titulo.setObjectName("tituloPagina")
        layout.addWidget(titulo)
        explicacao = QLabel(
            "Escolha o projeto e a situação; todas as RFQs enviadas para ele já vêm marcadas. Cada fornecedor "
            "recebe um e-mail no idioma da RFQ, agradecendo a participação e citando os números das RFQs dele."
        )
        explicacao.setObjectName("subtitulo")
        explicacao.setWordWrap(True)
        layout.addWidget(explicacao)

        formulario = QFormLayout()
        formulario.setSpacing(8)
        self.projeto = QComboBox()
        for projeto, total in servico.projetos_com_rfqs_enviadas(self.base):
            cliente = f" ({projeto.cliente})" if projeto.cliente else ""
            self.projeto.addItem(f"{projeto.nome}{cliente} — {total} RFQ(s) enviadas", projeto.id)
        self.projeto.setCurrentIndex(max(0, self.projeto.findData(projeto_id)))
        self.motivo = QComboBox()
        for motivo in MOTIVOS_AGRADECIMENTO:
            self.motivo.addItem(motivo.rotulo, motivo.chave)
        self.texto_livre = QLineEdit()
        self.texto_livre.setPlaceholderText("Mensagem sobre a situação do projeto (vai igual em todos os idiomas)")
        self.novo_status = QComboBox()
        self.novo_status.addItem(NAO_ALTERAR, None)
        for status in (StatusRFQ.CANCELADA, StatusRFQ.NAO_SELECIONADA, StatusRFQ.SELECIONADA):
            self.novo_status.addItem(status.value, status.value)
        self.novo_status.setToolTip("Status gravado nas RFQs dos e-mails abertos/enviados")
        formulario.addRow("Projeto", self.projeto)
        formulario.addRow("Situação do projeto", self.motivo)
        formulario.addRow("Texto (motivo 'Outro')", self.texto_livre)
        formulario.addRow("Depois, alterar o status para", self.novo_status)
        layout.addLayout(formulario)

        linha = QHBoxLayout()
        rotulo = QLabel("RFQs que recebem o e-mail")
        rotulo.setObjectName("tituloSecao")
        linha.addWidget(rotulo)
        linha.addStretch()
        linha.addWidget(botao("Marcar todas", lambda: self._marcar(True)))
        linha.addWidget(botao("Desmarcar", lambda: self._marcar(False)))
        linha.addWidget(botao("Pré-visualizar", self._pre_visualizar, dica="O e-mail do primeiro fornecedor marcado"))
        layout.addLayout(linha)
        self.tabela = QTableWidget(0, 7)
        self.tabela.setHorizontalHeaderLabels(["Enviar", "RFQ Nº", "Fornecedor", "Situação", "Envio", "Pacote", "Idioma"])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(32)
        self.tabela.setItemDelegate(DelegadoBase(self.tabela))
        self.tabela.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for coluna, largura in ((COL_MARCAR, 60), (COL_NUMERO, 125), (COL_FORNECEDOR, 220), (COL_SITUACAO, 130),
                                (COL_ENVIO, 95), (COL_IDIOMA, 90)):
            self.tabela.setColumnWidth(coluna, largura)
        self.tabela.horizontalHeader().setSectionResizeMode(COL_PACOTE, QHeaderView.ResizeMode.Stretch)
        self.tabela.itemChanged.connect(lambda _i: self._atualizar_botao())
        layout.addWidget(self.tabela, 1)

        opcoes = QHBoxLayout()
        self.revisar = QRadioButton("Abrir no Outlook para revisar antes de enviar")
        self.automatico = QRadioButton("Enviar automaticamente pelo Outlook")
        grupo = QButtonGroup(self)
        grupo.addButton(self.revisar)
        grupo.addButton(self.automatico)
        usa_outlook = self.base.configuracoes.metodo_email == MetodoEmail.OUTLOOK
        self.automatico.setEnabled(usa_outlook)
        self.revisar.setChecked(True)
        self.automatico.toggled.connect(lambda _v: self._atualizar_botao())
        opcoes.addWidget(self.revisar)
        opcoes.addWidget(self.automatico)
        opcoes.addStretch()
        layout.addLayout(opcoes)

        rodape = QHBoxLayout()
        self.resumo = QLabel()
        self.resumo.setObjectName("dica")
        rodape.addWidget(self.resumo, 1)
        rodape.addWidget(botao("Cancelar", self.reject))
        self.botao_enviar = botao("Abrir e-mails", self._enviar, primario=True)
        rodape.addWidget(self.botao_enviar)
        layout.addLayout(rodape)

        self.projeto.currentIndexChanged.connect(lambda _i: self._carregar_rfqs())
        self.motivo.currentIndexChanged.connect(lambda _i: self._motivo_mudou())
        self._motivo_mudou()
        self._carregar_rfqs()

    # ------------------------------------------------ dados
    def _motivo_mudou(self) -> None:
        motivo = servico.motivo(self.motivo.currentData())
        self.texto_livre.setEnabled(not motivo.textos)
        sugerido = motivo.status_sugerido.value if motivo.status_sugerido else None
        self.novo_status.setCurrentIndex(max(0, self.novo_status.findData(sugerido)))

    def _carregar_rfqs(self) -> None:
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(0)
        projeto_id = self.projeto.currentData()
        for rfq in servico.rfqs_enviadas_do_projeto(self.base, projeto_id) if projeto_id else []:
            linha = self.tabela.rowCount()
            self.tabela.insertRow(linha)
            caixa = QTableWidgetItem()
            caixa.setData(Qt.ItemDataRole.UserRole, rfq.id)
            caixa.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            # canceladas já foram encerradas; a vencedora (Selecionada) não recebe "não vamos seguir"
            marcada = rfq.status not in (StatusRFQ.CANCELADA, StatusRFQ.SELECIONADA)
            caixa.setCheckState(Qt.CheckState.Checked if marcada else Qt.CheckState.Unchecked)
            self.tabela.setItem(linha, COL_MARCAR, caixa)
            fornecedor = self.base.fornecedores.obter(rfq.fornecedor_id)
            pacote = self.base.pacotes.obter(rfq.pacote_id)
            valores = {
                COL_NUMERO: rfq.numero,
                COL_FORNECEDOR: fornecedor.nome if fornecedor else "?",
                COL_SITUACAO: rfq.situacao(),
                COL_ENVIO: data_curta(rfq.data_envio),
                COL_PACOTE: pacote.titulo if pacote else "",
                COL_IDIOMA: rfq.idioma.rotulo,
            }
            for coluna, texto in valores.items():
                self.tabela.setItem(linha, coluna, QTableWidgetItem(texto))
        self.tabela.blockSignals(False)
        self._atualizar_botao()

    def rfq_ids(self) -> list[str]:
        return [
            self.tabela.item(linha, COL_MARCAR).data(Qt.ItemDataRole.UserRole)
            for linha in range(self.tabela.rowCount())
            if self.tabela.item(linha, COL_MARCAR).checkState() == Qt.CheckState.Checked
        ]

    def _marcar(self, marcar: bool) -> None:
        self.tabela.blockSignals(True)
        for linha in range(self.tabela.rowCount()):
            self.tabela.item(linha, COL_MARCAR).setCheckState(
                Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked)
        self.tabela.blockSignals(False)
        self._atualizar_botao()

    def _fornecedores_marcados(self) -> int:
        ids = set(self.rfq_ids())
        return len({self.base.rfqs.obter(i).fornecedor_id for i in ids if self.base.rfqs.obter(i)})

    def _atualizar_botao(self) -> None:
        rfqs, fornecedores = len(self.rfq_ids()), self._fornecedores_marcados()
        acao = "Enviar" if self.automatico.isChecked() else "Abrir"
        self.botao_enviar.setText(f"{acao} {fornecedores} e-mail(s)" if fornecedores else f"{acao} e-mails")
        self.botao_enviar.setEnabled(bool(fornecedores))
        self.resumo.setText(f"{rfqs} RFQ(s) marcada(s) · {fornecedores} fornecedor(es) — um e-mail por fornecedor")

    # ------------------------------------------------ ações
    def _pre_visualizar(self) -> None:
        ok, email = executar(self, lambda: servico.pre_visualizar(
            self.base, self.rfq_ids(), self.motivo.currentData(), self.texto_livre.text()))
        if not ok:
            return
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Pré-visualização do agradecimento")
        dialogo.resize(860, 640)
        layout = QVBoxLayout(dialogo)
        navegador = QTextBrowser()
        cabecalho = (
            f"<p style='color:#52514e'><b>Para:</b> {html.escape('; '.join(email.para))}<br>"
            f"<b>Cc:</b> {html.escape('; '.join(email.copia)) or '—'}<br>"
            f"<b>Assunto:</b> {html.escape(email.assunto)}</p><hr>"
        )
        navegador.setHtml(cabecalho + email.html)
        layout.addWidget(navegador)
        linha = QHBoxLayout()
        linha.addStretch()
        linha.addWidget(botao("Fechar", dialogo.accept))
        layout.addLayout(linha)
        dialogo.exec()

    def _enviar(self) -> None:
        ids = self.rfq_ids()
        if not ids:
            avisar(self, "Marque pelo menos uma RFQ.")
            return
        automatico = self.automatico.isChecked()
        if automatico and not confirmar(
            self, f"Enviar agora {self._fornecedores_marcados()} e-mail(s) pelo Outlook, sem revisão?",
            "Enviar automaticamente", "Enviar agora",
        ):
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ok, resultado = executar(self, lambda: servico.enviar_agradecimento(
                self.base, ids, self.motivo.currentData(), self.texto_livre.text(), enviar=automatico,
                novo_status=self.novo_status.currentData(),
            ))
        finally:
            QApplication.restoreOverrideCursor()
        if not ok:
            return
        self.resultado = resultado
        resumo = resultado.resumo()
        detalhes = [
            f"{'✓' if i.ok else '✗'} {i.fornecedor} — {i.numero}" + (f" ({i.idioma.rotulo})" if i.idioma else "")
            + f": {i.mensagem}"
            for i in resultado.itens
        ] + resultado.avisos
        self.janela.mensagem(resumo)
        mostrar_resultado(self, "Agradecimento / status do projeto", resumo, "Fornecedores", detalhes)
        self.accept()
