"""Janela principal: menu lateral + páginas."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
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
from ..servicos import envio_email
from ..servicos.rfq import pendentes_de_envio
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

log = logging.getLogger(__name__)
INTERVALO_VERIFICACAO = 10  # segundos entre duas consultas aos Itens Enviados do Outlook
REPETIR_VERIFICACAO_MS = 30_000  # enquanto houver e-mails aguardando envio, confere de novo
SEGUNDA_TENTATIVA_MS = 8_000  # ao voltar ao app o e-mail pode ainda estar na Caixa de Saída

# Abas da Base de dados que também podem ser abertas diretamente (ex.: ir_para("fornecedores")).
ABAS_BASE = {"controle", "fornecedores", "commodities", "projetos", "solicitantes", "feriados", "modelos"}


class JanelaPrincipal(QMainWindow):
    envios_confirmados = Signal(list)  # números das RFQs confirmadas pelo Outlook

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
                       dica="Escolher a RFQ e os fornecedores que vão receber o e-mail (Ctrl+R na lista de RFQs)")
        enviar.setObjectName("botaoLateral")
        lateral_layout.addWidget(enviar)
        self.botao_base = botao("Base de dados", lambda: self.ir_para("base"),
                                dica="As antigas abas da planilha: Controle, Fornecedores, Commodities, "
                                     "Projetos, Solicitantes, Feriados e Corpo do E-mail (Ctrl+B)")
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
        QShortcut(QKeySequence("F5"), self, activated=self._f5)
        self.ir_para("painel")

        # E-mails abertos para revisão: confere nos Itens Enviados ao abrir o app e ao voltar para ele
        # (ex.: depois de clicar em Enviar no Outlook).
        self._ultima_verificacao = 0.0
        aplicacao = QApplication.instance()
        if aplicacao is not None:
            aplicacao.applicationStateChanged.connect(self._estado_do_app)
        QTimer.singleShot(1500, self, self.verificar_envios)  # com contexto: cancelado se a janela sumir
        self._repeticao = QTimer(self)
        self._repeticao.setInterval(REPETIR_VERIFICACAO_MS)
        self._repeticao.timeout.connect(lambda: self.verificar_envios(forcar=True))
        self._repeticao.start()

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

    def _estado_do_app(self, estado) -> None:
        if estado == Qt.ApplicationState.ApplicationActive:
            self.verificar_envios()
            if pendentes_de_envio(self.base):
                QTimer.singleShot(SEGUNDA_TENTATIVA_MS, self, lambda: self.verificar_envios(forcar=True))

    def _f5(self) -> None:
        self.verificar_envios(forcar=True)
        self.atualizar_pagina()

    def verificar_envios(self, forcar: bool = False) -> list:
        """Passa para Enviada as RFQs aguardando envio cujo e-mail já está nos Itens Enviados."""
        if not forcar and time.monotonic() - self._ultima_verificacao < INTERVALO_VERIFICACAO:
            return []
        self._ultima_verificacao = time.monotonic()
        if not pendentes_de_envio(self.base):
            return []
        try:
            confirmadas = envio_email.confirmar_envios_outlook(self.base)
        except Exception:  # noqa: BLE001 - conferência automática: nunca atrapalha o uso
            log.exception("Falha ao conferir os Itens Enviados do Outlook")
            return []
        if confirmadas:
            numeros = [r.numero for r in confirmadas]
            self.mensagem("Envio confirmado no Outlook: " + ", ".join(numeros))
            self.atualizar_pagina()
            self.envios_confirmados.emit(numeros)
        return confirmadas

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
