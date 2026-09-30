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
from .componentes import botao
from .pagina_cadastros import pagina_feriados, pagina_fornecedores, pagina_projetos, pagina_solicitantes
from .pagina_configuracoes import PaginaConfiguracoes
from .pagina_modelos import PaginaModelos
from .pagina_pacotes import PaginaPacotes
from .pagina_painel import PaginaPainel
from .pagina_rfqs import PaginaRFQs

MENU = [
    ("COTAÇÕES", None),
    ("Painel", "painel"),
    ("RFQs", "rfqs"),
    ("Pacotes de cotação", "pacotes"),
    ("CADASTROS", None),
    ("Fornecedores", "fornecedores"),
    ("Projetos", "projetos"),
    ("Solicitantes", "solicitantes"),
    ("Feriados", "feriados"),
    ("Modelos de e-mail", "modelos"),
    ("SISTEMA", None),
    ("Configurações", "configuracoes"),
]


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
            "fornecedores": pagina_fornecedores(self),
            "projetos": pagina_projetos(self),
            "solicitantes": pagina_solicitantes(self),
            "feriados": pagina_feriados(self),
            "modelos": PaginaModelos(self),
            "configuracoes": PaginaConfiguracoes(self),
        }
        for pagina in self._paginas.values():
            self.paginas.addWidget(pagina)

        self.statusBar().showMessage(f"Dados em {base.pasta}")
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.nova_solicitacao)
        QShortcut(QKeySequence("F5"), self, activated=self.atualizar_pagina)
        self.ir_para("painel")

    # ------------------------------------------------ navegação
    def _mudar_pagina(self, item: QListWidgetItem | None, _anterior=None) -> None:
        if item is None:
            return
        chave = item.data(Qt.ItemDataRole.UserRole)
        pagina = self._paginas.get(chave)
        if pagina is None:
            return
        self.paginas.setCurrentWidget(pagina)
        pagina.atualizar()

    def ir_para(self, chave: str):
        for linha in range(self.menu.count()):
            if self.menu.item(linha).data(Qt.ItemDataRole.UserRole) == chave:
                if self.menu.currentRow() == linha:
                    self._paginas[chave].atualizar()
                else:
                    self.menu.setCurrentRow(linha)
                break
        return self._paginas[chave]

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
