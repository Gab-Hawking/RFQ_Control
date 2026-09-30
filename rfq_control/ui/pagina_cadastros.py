"""Telas de cadastro: fornecedores, projetos, solicitantes e feriados."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
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
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..modelos import Contato, Feriado, Fornecedor, Idioma, Projeto, Solicitante
from ..servicos import cadastros
from .componentes import (
    CaixaBusca,
    Coluna,
    Tabela,
    avisar,
    botao,
    cabecalho_pagina,
    confirmar,
    executar,
    informar,
)
from .formularios import Campo, DialogoFormulario

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal


class PaginaCadastro(QWidget):
    """Lista com busca + botões Novo / Editar / Excluir."""

    def __init__(
        self,
        janela: JanelaPrincipal,
        titulo: str,
        subtitulo: str,
        registros: Callable[[], list[Any]],
        colunas: list[Coluna],
        editar: Callable[[Any | None], bool],
        nome_singular: str,
    ):
        super().__init__()
        self.setObjectName("pagina")
        self.janela = janela
        self._registros = registros
        self._editar = editar
        self.nome_singular = nome_singular

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(cabecalho_pagina(titulo, subtitulo))

        barra = QHBoxLayout()
        self.busca = CaixaBusca(f"Buscar {nome_singular}…")
        barra.addWidget(self.busca)
        self.somente_ativos = QCheckBox("Somente ativos")
        self.somente_ativos.toggled.connect(lambda _: self.atualizar())
        barra.addWidget(self.somente_ativos)
        self.somente_ativos.setVisible(False)
        barra.addStretch()
        self.barra_botoes = barra
        self.botao_excluir = botao("Excluir", self.excluir, perigo=True)
        self.botao_editar = botao("Editar", self.editar_selecionado)
        self.botao_novo = botao(f"Novo {nome_singular}", self.novo, primario=True)
        for b in (self.botao_excluir, self.botao_editar, self.botao_novo):
            barra.addWidget(b)
        layout.addLayout(barra)

        self.tabela = Tabela(colunas)
        self.tabela.ativada.connect(self._editar_registro)
        self.busca.textChanged.connect(self.tabela.filtro.definir_busca)
        layout.addWidget(self.tabela, 1)
        self.contador = QLabel()
        self.contador.setObjectName("dica")
        layout.addWidget(self.contador)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.busca.setFocus)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.tabela, activated=self.excluir)

    def adicionar_botao(self, *botoes) -> None:
        for b in botoes:
            self.barra_botoes.insertWidget(self.barra_botoes.count() - 3, b)

    def usar_filtro_ativos(self) -> None:
        self.somente_ativos.setVisible(True)

    def atualizar(self) -> None:
        registros = self._registros()
        if self.somente_ativos.isVisible() and self.somente_ativos.isChecked():
            registros = [r for r in registros if getattr(r, "ativo", True)]
        self.tabela.definir(registros)
        self.contador.setText(f"{len(registros)} registro(s)")

    def novo(self) -> None:
        if self._editar(None):
            self.atualizar()

    def _editar_registro(self, registro) -> None:
        if registro is not None and self._editar(registro):
            self.atualizar()

    def editar_selecionado(self) -> None:
        registro = self.tabela.atual()
        if registro is None:
            avisar(self, f"Selecione um {self.nome_singular} na lista.")
            return
        self._editar_registro(registro)

    def excluir(self) -> None:
        selecionados = self.tabela.selecionados()
        if not selecionados:
            avisar(self, f"Selecione ao menos um {self.nome_singular} para excluir.")
            return
        texto = (
            f"Excluir {len(selecionados)} registro(s) selecionado(s)?"
            if len(selecionados) > 1 else f"Excluir '{_descricao(selecionados[0])}'?"
        )
        if not confirmar(self, texto, "Excluir", "Excluir"):
            return
        ok, total = executar(self, lambda: cadastros.excluir_registros(self.janela.base, selecionados))
        if ok:
            self.janela.mensagem(f"{total} registro(s) excluído(s).")
            self.atualizar()


def _descricao(registro) -> str:
    if isinstance(registro, Feriado):
        return f"{registro.data:%d/%m/%Y} {registro.descricao}"
    return getattr(registro, "nome", str(registro))


# ---------------------------------------------------------------- fornecedores


class DialogoFornecedor(QDialog):
    def __init__(self, janela: JanelaPrincipal, fornecedor: Fornecedor | None = None, pai=None):
        super().__init__(pai or janela)
        self.janela = janela
        self.original = fornecedor
        self.resultado: Fornecedor | None = None
        self.setWindowTitle("Editar fornecedor" if fornecedor else "Novo fornecedor")
        self.resize(760, 560)
        fornecedor = fornecedor or Fornecedor.model_construct(
            nome="", idioma=Idioma.PT, categoria="", observacoes="", ativo=True, contatos=[]
        )

        layout = QVBoxLayout(self)
        formulario = QFormLayout()
        self.nome = QLineEdit(fornecedor.nome)
        self.idioma = QComboBox()
        for idioma in Idioma:
            self.idioma.addItem(idioma.rotulo, idioma)
        self.idioma.setCurrentIndex(self.idioma.findData(fornecedor.idioma))
        self.idioma.setToolTip("Idioma padrão dos e-mails de RFQ para este fornecedor")
        self.categoria = QComboBox()
        self.categoria.setEditable(True)
        categorias = sorted({f.categoria for f in janela.base.fornecedores if f.categoria})
        self.categoria.addItems(categorias)
        self.categoria.setCurrentText(fornecedor.categoria)
        self.ativo = QCheckBox("Fornecedor ativo (aparece na seleção de novas RFQs)")
        self.ativo.setChecked(fornecedor.ativo)
        self.observacoes = QPlainTextEdit(fornecedor.observacoes)
        self.observacoes.setFixedHeight(60)
        formulario.addRow("Nome *", self.nome)
        formulario.addRow("Idioma dos e-mails", self.idioma)
        formulario.addRow("Categoria", self.categoria)
        formulario.addRow("", self.ativo)
        formulario.addRow("Observações", self.observacoes)
        layout.addLayout(formulario)

        titulo = QLabel("Contatos")
        titulo.setObjectName("tituloSecao")
        dica = QLabel("Destinatários (Para) recebem o e-mail; contatos em Cópia (Cc) são copiados. "
                      "O nome do primeiro destinatário é usado na saudação.")
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        layout.addWidget(titulo)
        layout.addWidget(dica)
        self.contatos = QTableWidget(0, 4)
        self.contatos.setHorizontalHeaderLabels(["Nome", "E-mail", "Tipo", "Telefone"])
        self.contatos.verticalHeader().setVisible(False)
        self.contatos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        cabecalho = self.contatos.horizontalHeader()
        cabecalho.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.contatos.setColumnWidth(0, 180)
        self.contatos.setColumnWidth(2, 110)
        self.contatos.setColumnWidth(3, 130)
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
        self.contatos.setItem(linha, 0, QTableWidgetItem(contato.nome if contato else ""))
        self.contatos.setItem(linha, 1, QTableWidgetItem(contato.email if contato else ""))
        tipo = QComboBox()
        tipo.addItem("Para", False)
        tipo.addItem("Cópia (Cc)", True)
        tipo.setCurrentIndex(1 if contato and contato.copia else 0)
        self.contatos.setCellWidget(linha, 2, tipo)
        self.contatos.setItem(linha, 3, QTableWidgetItem(contato.telefone if contato else ""))

    def _remover_contato(self) -> None:
        for linha in sorted({i.row() for i in self.contatos.selectedIndexes()}, reverse=True):
            self.contatos.removeRow(linha)

    def _texto(self, linha: int, coluna: int) -> str:
        item = self.contatos.item(linha, coluna)
        return item.text().strip() if item else ""

    def _salvar(self) -> None:
        contatos = []
        for linha in range(self.contatos.rowCount()):
            nome, email, telefone = self._texto(linha, 0), self._texto(linha, 1), self._texto(linha, 3)
            if not (nome or email or telefone):
                continue
            copia = self.contatos.cellWidget(linha, 2).currentData()
            contatos.append({"nome": nome, "email": email, "copia": copia, "telefone": telefone})
        dados = {
            "nome": self.nome.text(),
            "idioma": self.idioma.currentData(),
            "categoria": self.categoria.currentText(),
            "ativo": self.ativo.isChecked(),
            "observacoes": self.observacoes.toPlainText(),
            "contatos": contatos,
        }
        if self.original:
            dados["id"] = self.original.id

        def salvar():
            return cadastros.salvar_fornecedor(self.janela.base, Fornecedor.model_validate(dados))

        ok, resultado = executar(self, salvar)
        if ok:
            if not resultado.emails_para():
                avisar(self, "Fornecedor salvo, mas sem e-mail de destinatário (Para). "
                             "Não será possível gerar o e-mail de RFQ até cadastrar um.")
            self.resultado = resultado
            self.accept()


def pagina_fornecedores(janela: JanelaPrincipal) -> PaginaCadastro:
    base = janela.base

    def editar(fornecedor):
        dialogo = DialogoFornecedor(janela, fornecedor)
        return dialogo.exec() == QDialog.DialogCode.Accepted

    def contagem(f: Fornecedor) -> int:
        return len(base.rfqs_do_fornecedor(f.id))

    colunas = [
        Coluna("Fornecedor", lambda f: f.nome, largura=260),
        Coluna("Contato principal", lambda f: f.nome_contato(), largura=160),
        Coluna("E-mail (Para)", lambda f: "; ".join(f.emails_para()), esticar=True,
               dica=lambda f: "Cópia: " + "; ".join(f.emails_copia()) if f.emails_copia() else ""),
        Coluna("Idioma", lambda f: f.idioma.rotulo, largura=90),
        Coluna("Categoria", lambda f: f.categoria, largura=140),
        Coluna("RFQs", contagem, largura=60, alinhamento=Qt.AlignmentFlag.AlignRight),
        Coluna("Ativo", lambda f: f.ativo, largura=60),
    ]
    pagina = PaginaCadastro(
        janela, "Fornecedores", "Cadastro de fornecedores e contatos (antiga aba CadastroContatos).",
        lambda: sorted(base.fornecedores, key=lambda f: f.nome.casefold()), colunas, editar, "fornecedor",
    )
    pagina.usar_filtro_ativos()
    return pagina


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


def pagina_projetos(janela: JanelaPrincipal) -> PaginaCadastro:
    base = janela.base
    colunas = [
        Coluna("Projeto", lambda p: p.nome, largura=260),
        Coluna("Cliente", lambda p: p.cliente, largura=160),
        Coluna("Planta", lambda p: p.planta, largura=180),
        Coluna("SOP", lambda p: p.sop, largura=100),
        Coluna("Lifetime", lambda p: p.lifetime_anos, largura=80, alinhamento=Qt.AlignmentFlag.AlignRight),
        Coluna("Pacotes", lambda p: len(base.pacotes_do_projeto(p.id)), largura=80,
               alinhamento=Qt.AlignmentFlag.AlignRight),
        Coluna("Ativo", lambda p: p.ativo, esticar=True),
    ]
    pagina = PaginaCadastro(
        janela, "Projetos", "Projetos, clientes e plantas (antiga aba CadastroProjetos).",
        lambda: sorted(base.projetos, key=lambda p: p.nome.casefold()), colunas,
        lambda projeto: editar_projeto(janela, projeto) is not None, "projeto",
    )
    pagina.usar_filtro_ativos()
    return pagina


# ---------------------------------------------------------------- solicitantes


def pagina_solicitantes(janela: JanelaPrincipal) -> PaginaCadastro:
    base = janela.base

    def editar(solicitante: Solicitante | None) -> bool:
        campos = [
            Campo("nome", "Nome", obrigatorio=True),
            Campo("email", "E-mail", dica="Usado em cópia quando ativado em Configurações"),
            Campo("ativo", "Ativo", "booleano"),
        ]
        valores = solicitante.model_dump() if solicitante else {"ativo": True}

        def salvar(dados):
            return cadastros.salvar_solicitante(base, Solicitante.model_validate({**valores, **dados}))

        dialogo = DialogoFormulario(
            "Editar solicitante" if solicitante else "Novo solicitante", campos, valores, salvar, janela
        )
        return dialogo.exec() == QDialog.DialogCode.Accepted

    colunas = [
        Coluna("Nome", lambda s: s.nome, largura=260),
        Coluna("E-mail", lambda s: s.email, largura=260),
        Coluna("Pacotes", lambda s: len(base.pacotes_do_solicitante(s.id)), largura=80,
               alinhamento=Qt.AlignmentFlag.AlignRight),
        Coluna("Ativo", lambda s: s.ativo, esticar=True),
    ]
    return PaginaCadastro(
        janela, "Solicitantes", "Pessoas que solicitam as cotações (antiga tabela Requester).",
        lambda: sorted(base.solicitantes, key=lambda s: s.nome.casefold()), colunas, editar, "solicitante",
    )


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


def pagina_feriados(janela: JanelaPrincipal) -> PaginaCadastro:
    base = janela.base
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

    def editar(feriado: Feriado | None) -> bool:
        campos = [Campo("data", "Data", "data", obrigatorio=True), Campo("descricao", "Descrição")]
        valores = feriado.model_dump() if feriado else {"data": date.today()}

        def salvar(dados):
            return cadastros.salvar_feriado(base, Feriado.model_validate({**valores, **dados}))

        dialogo = DialogoFormulario("Editar feriado" if feriado else "Novo feriado", campos, valores, salvar, janela)
        return dialogo.exec() == QDialog.DialogCode.Accepted

    colunas = [
        Coluna("Data", lambda f: f.data, largura=110),
        Coluna("Dia da semana", lambda f: dias[f.data.weekday()], largura=120),
        Coluna("Descrição", lambda f: f.descricao, esticar=True),
    ]
    pagina = PaginaCadastro(
        janela, "Feriados", "Datas desconsideradas no cálculo do prazo em dias úteis.",
        lambda: sorted(base.feriados, key=lambda f: f.data, reverse=True), colunas, editar, "feriado",
    )

    def nacionais():
        dialogo = DialogoFeriadosNacionais(janela)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        ok, total = executar(janela, lambda: cadastros.adicionar_feriados_nacionais(
            base, dialogo.ano.value(), dialogo.carnaval.isChecked(), dialogo.corpus.isChecked()))
        if ok:
            informar(janela, f"{total} feriado(s) adicionado(s) para {dialogo.ano.value()}.")
            pagina.atualizar()

    pagina.adicionar_botao(botao("Feriados nacionais…", nacionais,
                                 dica="Gera os feriados nacionais do Brasil de um ano"))
    return pagina
