"""Janela principal: menu lateral + páginas."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import NOME_APP, __version__
from ..armazenamento import BaseDados
from . import acoes
from .componentes import botao, confirmar
from .pagina_base_dados import PaginaBaseDados
from .pagina_configuracoes import PaginaConfiguracoes
from .pagina_pacotes import PaginaPacotes
from .pagina_painel import PaginaPainel
from .pagina_rfqs import PaginaRFQs

MENU = [
    ("COTAÇÕES", None),
    ("Painel", "painel"),
    ("RFQs", "rfqs"),
    ("Pacotes de cotação", "pacotes"),
    ("SISTEMA", None),
    ("Configurações", "configuracoes"),
]

# Abas da Base de dados que também podem ser abertas diretamente (ex.: ir_para("fornecedores")).
ABAS_BASE = {"controle", "fornecedores", "projetos", "solicitantes", "feriados", "modelos"}


class JanelaPrincipal(QMainWindow):
    def __init__(self, base: BaseDados):
        super().__init__()
        self.base = base
        self.setWindowTitle(f"{NOME_APP} — {base.pasta}")
        self.resize(1400, 860)
        self.setMinimumSize(QSize(1100, 680))

        central = QWidget()
        central.setObjectName("conteudo")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)

        # ------------------------------------------------ menu lateral
        lateral = QWidget()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(230)
        lateral_layout = QVBoxLayout(lateral)
        lateral_layout.setContentsMargins(12, 18, 12, 14)
        lateral_layout.setSpacing(8)
        marca = QLabel(NOME_APP)
        marca.setObjectName("marca")
        versao = QLabel(f"versão {__version__}")
        versao.setObjectName("versao")
        lateral_layout.addWidget(marca)
        lateral_layout.addWidget(versao)
        lateral_layout.addSpacing(10)
        nova = botao("+  Nova solicitação", self.nova_solicitacao, dica="Ctrl+N")
        nova.setObjectName("novaSolicitacao")
        lateral_layout.addWidget(nova)
        enviar = botao("Enviar e-mails", self.enviar_emails,
                       dica="Escolher a RFQ e os fornecedores que vão receber o e-mail (Ctrl+E)")
        enviar.setObjectName("botaoLateral")
        lateral_layout.addWidget(enviar)
        self.botao_base = botao("Base de dados", lambda: self.ir_para("base"),
                                dica="As antigas abas da planilha: Controle, Fornecedores, Projetos, "
                                     "Solicitantes, Feriados e Corpo do E-mail")
        self.botao_base.setObjectName("botaoLateral")
        self.botao_base.setCheckable(True)
        lateral_layout.addWidget(self.botao_base)
        lateral_layout.addSpacing(4)

        self.menu = QListWidget()
        self.menu.setObjectName("menu")
        self.menu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for texto, chave in MENU:
            item = QListWidgetItem(texto)
            if chave is None:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
            else:
                item.setData(Qt.ItemDataRole.UserRole, chave)
            self.menu.addItem(item)
        self.menu.currentItemChanged.connect(self._mudar_pagina)
        lateral_layout.addWidget(self.menu, 1)
        layout.addWidget(lateral)

        # ------------------------------------------------ páginas
        self.paginas = QStackedWidget()
        self.paginas.setObjectName("conteudo")
        layout.addWidget(self.paginas, 1)
        self._paginas = {
            "painel": PaginaPainel(self),
            "rfqs": PaginaRFQs(self),
            "pacotes": PaginaPacotes(self),
            "base": PaginaBaseDados(self),
            "configuracoes": PaginaConfiguracoes(self),
        }
        for pagina in self._paginas.values():
            self.paginas.addWidget(pagina)

        self.statusBar().showMessage(f"Dados em {base.pasta}")
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.nova_solicitacao)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=lambda: self.ir_para("base"))
        QShortcut(QKeySequence("F5"), self, activated=self.atualizar_pagina)
        self.ir_para("painel")

    # ------------------------------------------------ navegação
    def _mudar_pagina(self, item: QListWidgetItem | None, _anterior=None) -> None:
        if item is not None and item.data(Qt.ItemDataRole.UserRole):
            self.ir_para(item.data(Qt.ItemDataRole.UserRole))

    def _pode_sair_da_base(self) -> bool:
        base: PaginaBaseDados = self._paginas["base"]
        pendentes = base.pendentes()
        if self.paginas.currentWidget() is not base or not pendentes:
            return True
        if confirmar(self, f"{pendentes} linha(s) da Base de dados não foram salvas (estão destacadas, com o "
                           "motivo ao passar o mouse).\n\nSair mesmo assim e descartar essas linhas?",
                     "Linhas não salvas", "Descartar"):
            base.descartar_pendentes()
            return True
        return False

    def ir_para(self, chave: str):
        aba = None
        if chave in ABAS_BASE:
            chave, aba = "base", chave
        pagina = self._paginas[chave]
        if pagina is not self.paginas.currentWidget() and not self._pode_sair_da_base():
            chave = "base"
            pagina = self._paginas["base"]
        self.paginas.setCurrentWidget(pagina)
        self.botao_base.setChecked(chave == "base")
        self.menu.blockSignals(True)
        self.menu.setCurrentRow(-1)
        for linha in range(self.menu.count()):
            if self.menu.item(linha).data(Qt.ItemDataRole.UserRole) == chave:
                self.menu.setCurrentRow(linha)
        self.menu.blockSignals(False)
        if aba:
            pagina.mostrar(aba)
        else:
            pagina.atualizar()
        return pagina

    def pagina(self, chave: str):
        return self._paginas[chave]

    def atualizar_pagina(self) -> None:
        atual = self.paginas.currentWidget()
        if hasattr(atual, "atualizar"):
            atual.atualizar()

    def mostrar_rfqs(self, situacao: str) -> None:
        pagina: PaginaRFQs = self.ir_para("rfqs")
        pagina.filtrar_situacao(situacao)

    def mensagem(self, texto: str) -> None:
        self.statusBar().showMessage(texto, 8000)

    def nova_solicitacao(self) -> None:
        if acoes.nova_solicitacao(self):
            self.atualizar_pagina()

    def enviar_emails(self) -> None:
        if acoes.enviar_emails(self):
            self.atualizar_pagina()

    def closeEvent(self, evento):  # noqa: N802
        if self._pode_sair_da_base():
            evento.accept()
        else:
            evento.ignore()
