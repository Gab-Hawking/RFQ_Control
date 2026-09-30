"""Edição dos modelos de e-mail (antiga aba CorpoEmail)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..modelos import Idioma, Item, ModeloEmail, Projeto, TipoModelo
from ..padroes import VARIAVEIS_MODELO, modelos_email_padrao
from ..servicos.email_rfq import renderizar, tabela_itens, tabela_projeto
from ..servicos.formatos import data_por_extenso
from .componentes import botao, cabecalho_pagina, confirmar, executar

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal


def pre_visualizar_html(modelo: ModeloEmail, empresa: str, colunas_fornecedor: bool) -> str:
    """Renderiza o modelo com dados de exemplo."""
    idioma = modelo.idioma
    itens = [
        Item(ref_op="PEÇA EXEMPLO 1", ref_cdc="CDC-EXEMPLO-001", unidade="PC", quantidade=2),
        Item(ref_op="PEÇA EXEMPLO 2", ref_cdc="CDC-EXEMPLO-002", unidade="PC", quantidade=1, volume_anual=150000),
    ]
    projeto = Projeto(nome="Projeto Exemplo", cliente="Cliente Exemplo", planta="Planta Exemplo")
    variaveis = {
        "contato": "Maria Silva",
        "fornecedor": "Fornecedor Exemplo Ltda.",
        "empresa": empresa or "nossa empresa",
        "rfq": f"RFQ{date.today().year}001",
        "projeto": projeto.nome,
        "cliente": projeto.cliente,
        "planta": projeto.planta,
        "solicitante": "Solicitante Exemplo",
        "pacote": "Pacote de exemplo",
        "prazo": data_por_extenso(date.today(), idioma),
    }
    blocos = {
        "tabela_itens": tabela_itens(itens, idioma, colunas_fornecedor),
        "tabela_projeto": tabela_projeto(projeto, idioma),
    }
    corpo, _ = renderizar(modelo.corpo, variaveis, blocos)
    assunto, _ = renderizar(modelo.assunto, variaveis, {})
    return f"<p style='color:#52514e'><b>Assunto:</b> {assunto}</p><hr>{corpo}"


class PaginaModelos(QWidget):
    def __init__(self, janela: JanelaPrincipal):
        super().__init__()
        self.setObjectName("pagina")
        self.janela = janela
        self.base = janela.base
        self.atual: ModeloEmail | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(cabecalho_pagina(
            "Modelos de e-mail",
            "Textos usados nos e-mails de RFQ e de cobrança. Separe parágrafos com uma linha em branco; "
            "use **texto** para negrito e as variáveis da lista para dados da RFQ.",
        ))

        divisor = QSplitter(Qt.Orientation.Horizontal)
        self.lista = QListWidget()
        self.lista.setMaximumWidth(280)
        self.lista.currentItemChanged.connect(self._selecionar)
        divisor.addWidget(self.lista)

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(12, 0, 0, 0)
        editor_layout.addWidget(QLabel("Assunto"))
        self.assunto = QLineEdit()
        editor_layout.addWidget(self.assunto)
        editor_layout.addWidget(QLabel("Corpo"))
        self.corpo = QPlainTextEdit()
        editor_layout.addWidget(self.corpo, 1)
        botoes = QHBoxLayout()
        botoes.addWidget(botao("Restaurar texto padrão", self._restaurar))
        botoes.addStretch()
        botoes.addWidget(botao("Pré-visualizar", self._pre_visualizar))
        botoes.addWidget(botao("Salvar modelo", self._salvar, primario=True))
        editor_layout.addLayout(botoes)
        divisor.addWidget(editor)

        variaveis = QWidget()
        variaveis_layout = QVBoxLayout(variaveis)
        variaveis_layout.setContentsMargins(12, 0, 0, 0)
        titulo = QLabel("Variáveis (duplo clique para inserir)")
        titulo.setObjectName("tituloSecao")
        variaveis_layout.addWidget(titulo)
        self.variaveis = QListWidget()
        for nome, descricao in VARIAVEIS_MODELO.items():
            item = QListWidgetItem(f"{{{{{nome}}}}}")
            item.setToolTip(descricao)
            item.setData(Qt.ItemDataRole.UserRole, nome)
            self.variaveis.addItem(item)
        self.variaveis.itemDoubleClicked.connect(self._inserir_variavel)
        variaveis_layout.addWidget(self.variaveis, 1)
        self.descricao_variavel = QLabel()
        self.descricao_variavel.setObjectName("dica")
        self.descricao_variavel.setWordWrap(True)
        self.variaveis.currentItemChanged.connect(
            lambda item, _: self.descricao_variavel.setText(item.toolTip() if item else "")
        )
        variaveis_layout.addWidget(self.descricao_variavel)
        divisor.addWidget(variaveis)
        divisor.setSizes([240, 640, 260])
        layout.addWidget(divisor, 1)

    def atualizar(self) -> None:
        atual_id = self.atual.id if self.atual else None
        self.lista.blockSignals(True)
        self.lista.clear()
        modelos = sorted(
            self.base.modelos_email,
            key=lambda m: (m.tipo != TipoModelo.RFQ, m.tipo.value, m.idioma != Idioma.PT),
        )
        for modelo in modelos:
            item = QListWidgetItem(f"{modelo.tipo.value} — {modelo.idioma.rotulo}")
            item.setData(Qt.ItemDataRole.UserRole, modelo.id)
            self.lista.addItem(item)
        self.lista.blockSignals(False)
        linha = next((i for i in range(self.lista.count())
                      if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == atual_id), 0)
        self.lista.setCurrentRow(linha)
        self._selecionar(self.lista.currentItem(), None)

    def _selecionar(self, item, _anterior) -> None:
        self.atual = self.base.modelos_email.obter(item.data(Qt.ItemDataRole.UserRole)) if item else None
        self.assunto.setText(self.atual.assunto if self.atual else "")
        self.corpo.setPlainText(self.atual.corpo if self.atual else "")

    def _inserir_variavel(self, item: QListWidgetItem) -> None:
        self.corpo.insertPlainText(f"{{{{{item.data(Qt.ItemDataRole.UserRole)}}}}}")
        self.corpo.setFocus()

    def _editado(self) -> ModeloEmail | None:
        if not self.atual:
            return None
        return self.atual.model_copy(update={"assunto": self.assunto.text().strip(),
                                             "corpo": self.corpo.toPlainText().strip()})

    def _salvar(self) -> None:
        modelo = self._editado()
        if modelo is None:
            return
        ok, salvo = executar(self, lambda: self.base.modelos_email.salvar(modelo))
        if ok:
            self.atual = salvo
            self.janela.mensagem("Modelo de e-mail salvo.")

    def _restaurar(self) -> None:
        if not self.atual:
            return
        padrao = next((m for m in modelos_email_padrao()
                       if m.tipo == self.atual.tipo and m.idioma == self.atual.idioma), None)
        if padrao and confirmar(self, "Substituir o texto no editor pelo texto padrão?", "Restaurar", "Restaurar"):
            self.assunto.setText(padrao.assunto)
            self.corpo.setPlainText(padrao.corpo)

    def _pre_visualizar(self) -> None:
        modelo = self._editado()
        if modelo is None:
            return
        config = self.base.configuracoes
        ok, html = executar(self, lambda: pre_visualizar_html(modelo, config.empresa, config.incluir_colunas_fornecedor))
        if not ok:
            return
        dialogo = QDialog(self)
        dialogo.setWindowTitle(f"Pré-visualização — {modelo.tipo.value} ({modelo.idioma.rotulo})")
        dialogo.resize(820, 640)
        layout = QVBoxLayout(dialogo)
        navegador = QTextBrowser()
        navegador.setHtml(html)
        layout.addWidget(navegador)
        linha = QHBoxLayout()
        linha.addStretch()
        linha.addWidget(botao("Fechar", dialogo.accept))
        layout.addLayout(linha)
        dialogo.exec()

