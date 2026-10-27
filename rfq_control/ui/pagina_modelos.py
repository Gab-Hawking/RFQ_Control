"""Edição dos modelos de e-mail (antiga aba CorpoEmail) e dos textos das Condições."""

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
from ..padroes import ASSUNTO_RFQ, MOTIVOS_AGRADECIMENTO, VARIAVEIS_MODELO, modelos_email_padrao
from ..servicos.email_rfq import renderizar, tabela_itens, tabela_projeto
from ..servicos.formatos import data_por_extenso
from .componentes import botao, cabecalho_pagina, confirmar, executar

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal


def pre_visualizar_html(modelo: ModeloEmail, empresa: str) -> str:
    """Renderiza o modelo com dados de exemplo."""
    idioma = modelo.idioma
    motivo = next((m for m in MOTIVOS_AGRADECIMENTO if m.textos), None)
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
        "rfqs": f"RFQ{date.today().year}001, RFQ{date.today().year}004",
        "commodity": "Ferramentaria",
        "motivo": motivo.textos[idioma] if motivo else "",
        "projeto": projeto.nome,
        "cliente": projeto.cliente,
        "projeto_cliente": f"{projeto.nome} ({'customer' if idioma == Idioma.EN else 'cliente'} {projeto.cliente})",
        "planta": projeto.planta,
        "pacote": "Pacote de exemplo",
        "prazo": data_por_extenso(date.today(), idioma),
    }
    blocos = {
        "tabela_itens": tabela_itens(itens, idioma),
        "tabela_projeto": tabela_projeto(projeto, idioma),
    }
    corpo, _ = renderizar(modelo.corpo, variaveis, blocos)
    if modelo.tipo == TipoModelo.CONDICAO:
        return ("<p style='color:#52514e'><i>Texto a mais no e-mail de RFQ quando a condição vale para o "
                "fornecedor (no fim do e-mail, ou onde estiver a variável condicoes):</i></p><hr>" + corpo)
    assunto, _ = renderizar(modelo.assunto, variaveis, {})
    if modelo.tipo == TipoModelo.COBRANCA:
        assunto = "RE: " + renderizar(ASSUNTO_RFQ, variaveis, {})[0] + " <i>(resposta ao e-mail da RFQ)</i>"
    return f"<p style='color:#52514e'><b>Assunto:</b> {assunto}</p><hr>{corpo}"


class PaginaModelos(QWidget):
    """Modelos de e-mail; ``embutida=True`` é a aba "Corpo do E-mail" da Base de dados."""

    def __init__(self, janela: JanelaPrincipal, embutida: bool = False):
        super().__init__()
        self.setObjectName("pagina")
        self.janela = janela
        self.base = janela.base
        self.atual: ModeloEmail | None = None

        layout = QVBoxLayout(self)
        explicacao = (
            "Textos padrão dos e-mails de RFQ, cobrança e agradecimento, em português, espanhol e inglês — o "
            "idioma usado é o do fornecedor. Separe parágrafos com uma linha em branco; use **texto** para negrito "
            "(um parágrafo inteiro em negrito vira um quadro de destaque) e as variáveis da lista para os dados. "
            "A cobrança sai como resposta ao e-mail da RFQ, com o mesmo assunto. Os textos de condição entram no "
            "fim do e-mail de RFQ quando a condição (aba Condições) vale para o fornecedor."
        )
        if embutida:
            layout.setContentsMargins(12, 12, 12, 8)
            layout.setSpacing(8)
            dica = QLabel(explicacao)
            dica.setObjectName("dica")
            dica.setWordWrap(True)
            layout.addWidget(dica)
        else:
            layout.setContentsMargins(24, 20, 24, 20)
            layout.setSpacing(12)
            layout.addWidget(cabecalho_pagina("Modelos de e-mail", explicacao))

        divisor = QSplitter(Qt.Orientation.Horizontal)
        self.lista = QListWidget()
        self.lista.setMaximumWidth(360)
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
        self.corpo.setTabStopDistance(self.corpo.fontMetrics().horizontalAdvance(" ") * 4)  # recuo de listas
        editor_layout.addWidget(self.corpo, 1)
        botoes = QHBoxLayout()
        self.botao_restaurar = botao("Restaurar texto padrão", self._restaurar)
        botoes.addWidget(self.botao_restaurar)
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
        divisor.setSizes([300, 620, 260])
        layout.addWidget(divisor, 1)

    def atualizar(self) -> None:
        atual_id = self.atual.id if self.atual else None
        self.lista.blockSignals(True)
        self.lista.clear()
        ordem_tipos = list(TipoModelo)
        ordem_idiomas = list(Idioma)
        modelos = sorted(
            self.base.modelos_email,
            key=lambda m: (ordem_tipos.index(m.tipo), self._nome_condicao(m).casefold(), ordem_idiomas.index(m.idioma)),
        )
        for modelo in modelos:
            if modelo.tipo == TipoModelo.CONDICAO:
                texto = f"Condição: {self._nome_condicao(modelo)} — {modelo.idioma.rotulo}"
                if not modelo.corpo.strip():
                    texto += " (vazio)"
            else:
                texto = f"{modelo.tipo.value} — {modelo.idioma.rotulo}"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, modelo.id)
            self.lista.addItem(item)
        self.lista.blockSignals(False)
        linha = next((i for i in range(self.lista.count())
                      if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == atual_id), 0)
        self.lista.setCurrentRow(linha)
        self._selecionar(self.lista.currentItem(), None)

    def _nome_condicao(self, modelo: ModeloEmail) -> str:
        condicao = self.base.condicoes.obter(modelo.condicao_id)
        return condicao.nome if condicao else ""

    def selecionar_condicao(self, condicao_id: str, idioma: Idioma = Idioma.PT) -> None:
        """Mostra o texto da condição (usado pelo botão 'Editar textos…' da aba Condições)."""
        self.atualizar()
        alvo = next((m.id for m in self.base.modelos_email
                     if m.tipo == TipoModelo.CONDICAO and m.condicao_id == condicao_id and m.idioma == idioma), None)
        for linha in range(self.lista.count()):
            if self.lista.item(linha).data(Qt.ItemDataRole.UserRole) == alvo:
                self.lista.setCurrentRow(linha)
                return

    def _selecionar(self, item, _anterior) -> None:
        self.atual = self.base.modelos_email.obter(item.data(Qt.ItemDataRole.UserRole)) if item else None
        condicao = self.atual is not None and self.atual.tipo == TipoModelo.CONDICAO
        self.assunto.setText(self.atual.assunto if self.atual else "")
        self.assunto.setEnabled(not condicao)
        self.assunto.setPlaceholderText("Não se aplica: o texto entra no e-mail de RFQ" if condicao else "")
        self.corpo.setPlainText(self.atual.corpo if self.atual else "")
        self.botao_restaurar.setEnabled(not condicao)

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
            if salvo.tipo == TipoModelo.CONDICAO:
                self.atualizar()  # a lista mostra "(vazio)" nos textos de condição sem texto

    def _restaurar(self) -> None:
        if not self.atual:
            return
        padrao = next((m for m in modelos_email_padrao()
                       if m.tipo == self.atual.tipo and m.idioma == self.atual.idioma), None)
        if padrao and confirmar(self.window(), "Substituir o texto no editor pelo texto padrão?", "Restaurar", "Restaurar"):
            self.assunto.setText(padrao.assunto)
            self.corpo.setPlainText(padrao.corpo)

    def _pre_visualizar(self) -> None:
        modelo = self._editado()
        if modelo is None:
            return
        config = self.base.configuracoes
        ok, html = executar(self, lambda: pre_visualizar_html(modelo, config.empresa))
        if not ok:
            return
        dialogo = QDialog(self.window())
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

