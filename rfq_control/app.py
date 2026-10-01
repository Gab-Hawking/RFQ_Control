"""Inicialização do RFQ Control."""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QLockFile, Qt, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from . import NOME_APP, __version__
from .armazenamento import BaseDados, ErroDados
from .caminhos import executando_como_exe, pasta_dados, pasta_recursos

log = logging.getLogger("rfq_control")


def configurar_log(pasta_logs: Path) -> None:
    pasta_logs.mkdir(parents=True, exist_ok=True)
    manipulador = RotatingFileHandler(pasta_logs / "rfq_control.log", maxBytes=1_000_000, backupCount=3,
                                      encoding="utf-8")
    manipulador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(manipulador)


def instalar_tratador_de_erros() -> None:
    """Erros não previstos viram mensagem e ficam no log, sem fechar o programa."""

    def tratar(tipo, valor, rastro):
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, rastro)
            return
        detalhes = "".join(traceback.format_exception(tipo, valor, rastro))
        log.error("Erro não tratado:\n%s", detalhes)
        QMessageBox.critical(
            None, NOME_APP,
            f"Ocorreu um erro inesperado:\n{valor}\n\nO programa continua aberto. Detalhes em dados/logs.",
        )

    sys.excepthook = tratar


def instalar_traducao(app: QApplication) -> None:
    """Botões e diálogos padrão do Qt (Sim/Não, calendário, copiar/colar) em português."""
    QLocale.setDefault(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
    pastas = [QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]
    if executando_como_exe():
        pastas.append(str(Path(getattr(sys, "_MEIPASS", "")) / "PySide6" / "Qt" / "translations"))
    tradutor = QTranslator(app)
    for pasta in pastas:
        if tradutor.load("qtbase_pt_BR", pasta):
            app.installTranslator(tradutor)
            return


class DialogoBoasVindas(QDialog):
    def __init__(self, pai=None):
        super().__init__(pai)
        self.setWindowTitle(f"Bem-vindo ao {NOME_APP}")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        titulo = QLabel(f"Bem-vindo ao {NOME_APP}")
        titulo.setObjectName("tituloPagina")
        layout.addWidget(titulo)
        texto = QLabel(
            "Os dados ficam na pasta 'dados', ao lado do programa — um arquivo para cada cadastro.\n\n"
            "Informe o nome da empresa que aparece nos e-mails para os fornecedores:"
        )
        texto.setWordWrap(True)
        layout.addWidget(texto)
        self.empresa = QLineEdit()
        self.empresa.setPlaceholderText("ex.: Minha Empresa Brasil")
        layout.addWidget(self.empresa)
        dica = QLabel("Você pode importar a planilha antiga (RFQ_Controle.xlsm) agora ou depois, em Configurações.")
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        layout.addWidget(dica)
        botoes = QDialogButtonBox()
        self.botao_importar = botoes.addButton("Importar planilha antiga…", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton("Começar do zero", QDialogButtonBox.ButtonRole.RejectRole)
        self.importar = False
        botoes.clicked.connect(lambda b: setattr(self, "importar", b is self.botao_importar))
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)


def verificar_instalacao(app: QApplication) -> int:
    """Autoteste usado no build: abre a base, monta todas as telas e encerra (código 0 = ok)."""
    from .ui.janela_principal import JanelaPrincipal

    base = BaseDados.abrir(pasta_dados())
    janela = JanelaPrincipal(base)
    for chave in ("painel", "rfqs", "pacotes", "controle", "fornecedores", "projetos", "solicitantes",
                  "feriados", "modelos", "configuracoes"):
        janela.ir_para(chave)
        app.processEvents()
    janela.close()
    print(f"{NOME_APP} {__version__}: verificação concluída ({base.pasta})")
    return 0


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(NOME_APP)
    app.setApplicationVersion(__version__)
    icone = pasta_recursos() / "icone.png"
    if icone.exists():
        app.setWindowIcon(QIcon(str(icone)))

    from .ui.estilo import aplicar_tema

    instalar_traducao(app)
    aplicar_tema(app)
    if "--verificar" in sys.argv:
        return verificar_instalacao(app)
    pasta = pasta_dados()
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except OSError as problema:
        QMessageBox.critical(None, NOME_APP, f"Não foi possível criar a pasta de dados:\n{pasta}\n\n{problema}")
        return 1

    trava = QLockFile(str(pasta / ".rfq_control.lock"))
    trava.setStaleLockTime(0)  # só considera abandonada se o processo dono não existir mais
    if not trava.tryLock(200):
        QMessageBox.warning(None, NOME_APP, f"O {NOME_APP} já está aberto usando a pasta:\n{pasta}")
        return 1

    configurar_log(pasta / "logs")
    instalar_tratador_de_erros()
    log.info("Iniciando %s %s — dados em %s", NOME_APP, __version__, pasta)
    try:
        base = BaseDados.abrir(pasta)
        base.backup_diario()
    except ErroDados as problema:
        log.error("Falha ao abrir os dados: %s", problema)
        QMessageBox.critical(None, NOME_APP, f"Não foi possível abrir os dados:\n\n{problema}")
        return 1

    from .ui.janela_principal import JanelaPrincipal

    janela = JanelaPrincipal(base)
    janela.showMaximized()

    if base.primeira_execucao:
        boas_vindas = DialogoBoasVindas(janela)
        boas_vindas.exec()
        empresa = boas_vindas.empresa.text().strip()
        if empresa:
            base.salvar_configuracoes(base.configuracoes.model_copy(update={"empresa": empresa}))
        if boas_vindas.importar:
            from .ui.pagina_configuracoes import importar_planilha_antiga

            importar_planilha_antiga(janela)
            janela.atualizar_pagina()

    codigo = app.exec()
    trava.unlock()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
