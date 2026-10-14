"""Diálogos de cadastro usados pela Base de dados e pela nova solicitação."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..modelos import Contato, Fornecedor, Idioma, Projeto
from ..servicos import cadastros
from .componentes import DelegadoBase, avisar, botao, executar
from .formularios import Campo, DialogoFormulario

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal


# ---------------------------------------------------------------- fornecedores


class DialogoFornecedor(QDialog):
    def __init__(self, janela: JanelaPrincipal, fornecedor: Fornecedor | None = None, pai=None):
        super().__init__(pai or janela)
        self.janela = janela
        self.original = fornecedor
        self.resultado: Fornecedor | None = None
        self.setWindowTitle("Detalhes do fornecedor" if fornecedor else "Novo fornecedor")
        self.resize(760, 620)
        fornecedor = fornecedor or Fornecedor.model_construct(
            nome="", idioma=Idioma.PT, commodity_ids=[], categoria="", observacoes="", ativo=True, contatos=[]
        )

        layout = QVBoxLayout(self)
        formulario = QFormLayout()
        self.nome = QLineEdit(fornecedor.nome)
        self.idioma = QComboBox()
        for idioma in Idioma:
            self.idioma.addItem(idioma.rotulo, idioma)
        self.idioma.setCurrentIndex(self.idioma.findData(fornecedor.idioma))
        self.idioma.setToolTip("Idioma padrão dos e-mails de RFQ para este fornecedor")
        self.commodities = QListWidget()
        self.commodities.setFixedHeight(104)
        for commodity in sorted(janela.base.commodities, key=lambda c: c.nome.casefold()):
            item = QListWidgetItem(commodity.nome + (f"   (buyer: {commodity.comprador})" if commodity.comprador else ""))
            item.setData(Qt.ItemDataRole.UserRole, commodity.id)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            marcado = commodity.id in fornecedor.commodity_ids
            item.setCheckState(Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked)
            self.commodities.addItem(item)
        if not self.commodities.count():
            vazio = QListWidgetItem("Nenhuma commodity cadastrada (Base de dados → Commodities)")
            vazio.setFlags(Qt.ItemFlag.NoItemFlags)
            self.commodities.addItem(vazio)
        self.ativo = QCheckBox("Fornecedor ativo (aparece na seleção de novas RFQs)")
        self.ativo.setChecked(fornecedor.ativo)
        self.observacoes = QPlainTextEdit(fornecedor.observacoes)
        self.observacoes.setFixedHeight(60)
        formulario.addRow("Nome *", self.nome)
        formulario.addRow("Idioma dos e-mails", self.idioma)
        formulario.addRow("Commodities", self.commodities)
        formulario.addRow("", self.ativo)
        formulario.addRow("Observações", self.observacoes)
        layout.addLayout(formulario)

        titulo = QLabel("Contatos")
        titulo.setObjectName("tituloSecao")
        dica = QLabel("Destinatários (Para) recebem o e-mail com o escopo; os contatos Supplier (Cc) vão em "
                      "cópia. O nome do primeiro destinatário é usado na saudação (\"Caro …\"). O Commodity Buyer "
                      "vem da commodity e entra em cópia automaticamente.")
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        layout.addWidget(titulo)
        layout.addWidget(dica)
        self.contatos = QTableWidget(0, 3)
        self.contatos.setHorizontalHeaderLabels(["Nome", "E-mail", "Tipo"])
        self.contatos.verticalHeader().setVisible(False)
        self.contatos.verticalHeader().setDefaultSectionSize(34)
        self.contatos.setItemDelegate(DelegadoBase(self.contatos))
        self.contatos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        cabecalho = self.contatos.horizontalHeader()
        cabecalho.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.contatos.setColumnWidth(0, 200)
        self.contatos.setColumnWidth(2, 170)
        for contato in fornecedor.contatos:
            self._adicionar_contato(contato)
        layout.addWidget(self.contatos, 1)
        linha = QHBoxLayout()
        linha.addWidget(botao("+ Adicionar contato", lambda: self._adicionar_contato(None)))
        linha.addWidget(botao("Remover contato", self._remover_contato))
        linha.addStretch()
        if self.original:
            total = len(janela.base.rfqs_do_fornecedor(self.original.id))
            info = QLabel(f"{total} RFQ(s) enviadas a este fornecedor")
            info.setObjectName("dica")
            linha.addWidget(info)
        layout.addLayout(linha)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Save).setText("Salvar")
        botoes.button(QDialogButtonBox.StandardButton.Save).setProperty("primario", True)
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        if not fornecedor.contatos:
            self._adicionar_contato(None)

    def _adicionar_contato(self, contato: Contato | None) -> None:
        linha = self.contatos.rowCount()
        self.contatos.insertRow(linha)
        nome = QTableWidgetItem(contato.nome if contato else "")
        # o telefone saiu da tela, mas fica guardado na linha para não se perder ao salvar
        nome.setData(Qt.ItemDataRole.UserRole, contato.telefone if contato else "")
        self.contatos.setItem(linha, 0, nome)
        self.contatos.setItem(linha, 1, QTableWidgetItem(contato.email if contato else ""))
        tipo = QComboBox()
        tipo.addItem("Para", False)
        tipo.addItem("Supplier (Cc)", True)
        tipo.setCurrentIndex(1 if contato and contato.copia else 0)
        self.contatos.setCellWidget(linha, 2, tipo)

    def _remover_contato(self) -> None:
        for linha in sorted({i.row() for i in self.contatos.selectedIndexes()}, reverse=True):
            self.contatos.removeRow(linha)

    def _texto(self, linha: int, coluna: int) -> str:
        item = self.contatos.item(linha, coluna)
        return item.text().strip() if item else ""

    def _salvar(self) -> None:
        contatos = []
        for linha in range(self.contatos.rowCount()):
            nome, email = self._texto(linha, 0), self._texto(linha, 1)
            item_nome = self.contatos.item(linha, 0)
            telefone = (item_nome.data(Qt.ItemDataRole.UserRole) or "") if item_nome else ""
            if not (nome or email or telefone):
                continue
            copia = self.contatos.cellWidget(linha, 2).currentData()
            contatos.append({"nome": nome, "email": email, "copia": copia, "telefone": telefone})
        commodities = [
            self.commodities.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.commodities.count())
            if self.commodities.item(i).checkState() == Qt.CheckState.Checked
        ]
        dados = {
            "nome": self.nome.text(),
            "idioma": self.idioma.currentData(),
            "commodity_ids": commodities,
            "ativo": self.ativo.isChecked(),
            "observacoes": self.observacoes.toPlainText(),
            "contatos": contatos,
        }
        if self.original:
            dados = {**self.original.model_dump(), **dados}

        def salvar():
            return cadastros.salvar_fornecedor(self.janela.base, Fornecedor.model_validate(dados))

        ok, resultado = executar(self, salvar)
        if ok:
            if not resultado.emails_para():
                avisar(self, "Fornecedor salvo, mas sem e-mail de destinatário (Para). "
                             "Não será possível gerar o e-mail de RFQ até cadastrar um.")
            self.resultado = resultado
            self.accept()


# ---------------------------------------------------------------- projetos


def editar_projeto(janela: JanelaPrincipal, projeto: Projeto | None, pai=None) -> Projeto | None:
    base = janela.base
    clientes = sorted({p.cliente for p in base.projetos if p.cliente})
    plantas = sorted({p.planta for p in base.projetos if p.planta})
    campos = [
        Campo("nome", "Projeto", obrigatorio=True),
        Campo("cliente", "Cliente", "sugestoes", opcoes=[(c, c) for c in clientes]),
        Campo("planta", "Planta", "sugestoes", opcoes=[(p, p) for p in plantas]),
        Campo("sop", "SOP", "data", dica="Start of production"),
        Campo("lifetime_anos", "Lifetime (anos)", "inteiro", maximo=50),
        Campo("ativo", "Ativo", "booleano"),
    ]
    valores = projeto.model_dump() if projeto else {"ativo": True}

    def salvar(dados):
        registro = Projeto.model_validate({**valores, **dados})
        return cadastros.salvar_projeto(base, registro)

    dialogo = DialogoFormulario("Editar projeto" if projeto else "Novo projeto", campos, valores, salvar, pai or janela)
    return dialogo.resultado if dialogo.exec() == QDialog.DialogCode.Accepted else None


# ---------------------------------------------------------------- feriados


class DialogoFeriadosNacionais(QDialog):
    def __init__(self, pai=None):
        super().__init__(pai)
        self.setWindowTitle("Adicionar feriados nacionais")
        layout = QVBoxLayout(self)
        formulario = QFormLayout()
        self.ano = QSpinBox()
        self.ano.setRange(2000, 2100)
        self.ano.setValue(date.today().year)
        self.carnaval = QCheckBox("Incluir Carnaval (segunda e terça-feira)")
        self.carnaval.setChecked(True)
        self.corpus = QCheckBox("Incluir Corpus Christi")
        self.corpus.setChecked(True)
        formulario.addRow("Ano", self.ano)
        formulario.addRow("", self.carnaval)
        formulario.addRow("", self.corpus)
        layout.addLayout(formulario)
        dica = QLabel("Feriados estaduais e municipais devem ser cadastrados manualmente.")
        dica.setObjectName("dica")
        layout.addWidget(dica)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Adicionar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
