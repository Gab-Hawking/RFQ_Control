"""Configurações, importação da planilha antiga e manutenção dos dados."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEventLoop, QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressDialog,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import NOME_APP, __version__
from ..modelos import Configuracoes, MetodoEmail, email_valido, separar_emails
from ..servicos.envio_email import abrir_arquivo
from ..servicos.exportacao import exportar_rfqs
from ..servicos.importacao_legado import RelatorioImportacao, importar_planilha
from .componentes import botao, cabecalho_pagina, confirmar, erro, executar, informar

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal


# ---------------------------------------------------------------- importação


class _TrabalhoImportacao(QObject):
    progresso = Signal(str)
    concluido = Signal(object)
    falhou = Signal(str)

    def __init__(self, base, caminho: Path):
        super().__init__()
        self.base = base
        self.caminho = caminho

    def executar(self) -> None:
        try:
            relatorio = importar_planilha(self.base, self.caminho, self.progresso.emit)
        except Exception as problema:  # noqa: BLE001 - devolvido à interface como mensagem
            self.falhou.emit(str(problema))
        else:
            self.concluido.emit(relatorio)


def importar_planilha_antiga(janela: JanelaPrincipal) -> bool:
    caminho, _ = QFileDialog.getOpenFileName(
        janela, "Selecionar a planilha RFQ_Controle", str(Path.home()), "Planilhas Excel (*.xlsm *.xlsx)"
    )
    if not caminho:
        return False
    if not confirmar(
        janela,
        "Os dados da planilha serão adicionados à base atual (RFQs já existentes são ignoradas). "
        "Uma cópia de segurança é feita antes.\n\nContinuar?",
        "Importar planilha",
        "Importar",
    ):
        return False

    progresso = QProgressDialog("Preparando importação…", None, 0, 0, janela)
    progresso.setWindowTitle("Importando planilha")
    progresso.setWindowModality(Qt.WindowModality.ApplicationModal)
    progresso.setMinimumDuration(0)
    progresso.setMinimumWidth(420)

    thread = QThread(janela)
    trabalho = _TrabalhoImportacao(janela.base, Path(caminho))
    trabalho.moveToThread(thread)
    resultado: dict = {}
    trabalho.progresso.connect(progresso.setLabelText)
    trabalho.concluido.connect(lambda r: resultado.update(relatorio=r))
    trabalho.falhou.connect(lambda m: resultado.update(erro=m))
    trabalho.concluido.connect(thread.quit)
    trabalho.falhou.connect(thread.quit)
    thread.started.connect(trabalho.executar)
    # O sinal 'finished' chega pela fila de eventos, então não se perde mesmo se a
    # importação terminar antes de o laço começar.
    laco = QEventLoop()
    thread.finished.connect(laco.quit)
    progresso.show()
    thread.start()
    laco.exec()
    thread.wait()
    progresso.close()

    if "erro" in resultado:
        erro(janela, f"A importação não foi concluída:\n{resultado['erro']}")
        return False
    relatorio = resultado.get("relatorio")
    if relatorio:
        mostrar_relatorio(janela, relatorio)
        janela.mensagem(f"Importação concluída: {relatorio.rfqs_importadas} RFQ(s).")
    return True


def mostrar_relatorio(janela: JanelaPrincipal, relatorio: RelatorioImportacao) -> None:
    dialogo = QDialog(janela)
    dialogo.setWindowTitle("Resultado da importação")
    dialogo.resize(720, 520)
    layout = QVBoxLayout(dialogo)
    titulo = QLabel("Importação concluída")
    titulo.setObjectName("tituloPagina")
    layout.addWidget(titulo)
    layout.addWidget(QLabel(relatorio.resumo()))
    if relatorio.pasta_backup:
        dica = QLabel(f"Cópia de segurança anterior à importação: {relatorio.pasta_backup}")
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        layout.addWidget(dica)
    rotulo = QLabel(f"Avisos ({len(relatorio.avisos)})")
    rotulo.setObjectName("tituloSecao")
    layout.addWidget(rotulo)
    avisos = QPlainTextEdit("\n".join(f"• {a}" for a in relatorio.avisos) or "Nenhum aviso.")
    avisos.setReadOnly(True)
    layout.addWidget(avisos, 1)
    linha = QHBoxLayout()
    linha.addStretch()
    linha.addWidget(botao("Fechar", dialogo.accept, primario=True))
    layout.addLayout(linha)
    dialogo.exec()


# ---------------------------------------------------------------- página


class PaginaConfiguracoes(QWidget):
    def __init__(self, janela: JanelaPrincipal):
        super().__init__()
        self.setObjectName("pagina")
        self.janela = janela
        self.base = janela.base

        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        externo.addWidget(rolagem)
        conteudo = QWidget()
        conteudo.setObjectName("pagina")
        rolagem.setWidget(conteudo)
        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(cabecalho_pagina("Configurações", "Preferências de e-mail, numeração e manutenção dos dados."))

        # ------------------------------------------------ e-mail
        grupo_email = QGroupBox("E-mails")
        form_email = QFormLayout(grupo_email)
        form_email.setSpacing(10)
        self.empresa = QLineEdit()
        self.empresa.setPlaceholderText("ex.: Minha Empresa Brasil")
        self.metodo = QComboBox()
        for metodo in MetodoEmail:
            self.metodo.addItem(metodo.value, metodo)
        self.copia_padrao = QLineEdit()
        self.copia_padrao.setPlaceholderText("e-mails separados por ; — ex.: seu.email@empresa.com")
        self.copiar_solicitante = QCheckBox("Copiar o solicitante do pacote nos e-mails de RFQ")
        self.colunas_fornecedor = QCheckBox(
            "Incluir na tabela as colunas para o fornecedor confirmar capacidade de 120% e cobertura máxima"
        )
        self.assinatura = QPlainTextEdit()
        self.assinatura.setFixedHeight(110)
        self.assinatura.setPlaceholderText(
            "Usada apenas no método .eml (no Outlook a assinatura padrão entra automaticamente). "
            "Texto simples ou HTML."
        )
        form_email.addRow("Nome da empresa", self.empresa)
        form_email.addRow("Abrir e-mails via", self.metodo)
        form_email.addRow("Sempre em cópia (Cc)", self.copia_padrao)
        form_email.addRow("", self.copiar_solicitante)
        form_email.addRow("", self.colunas_fornecedor)
        form_email.addRow("Assinatura (.eml)", self.assinatura)
        layout.addWidget(grupo_email)

        # ------------------------------------------------ RFQs
        grupo_rfq = QGroupBox("RFQs")
        form_rfq = QFormLayout(grupo_rfq)
        form_rfq.setSpacing(10)
        self.prefixo = QLineEdit()
        self.prefixo.setMaxLength(10)
        self.exemplo_numero = QLabel()
        self.exemplo_numero.setObjectName("dica")
        self.prefixo.textChanged.connect(
            lambda t: self.exemplo_numero.setText(f"Próximos números: {t.upper() or 'RFQ'}{date.today().year}001, …")
        )
        self.prazo = QSpinBox()
        self.prazo.setRange(0, 60)
        self.prazo.setSuffix(" dias úteis")
        self.moeda = QComboBox()
        self.moeda.setEditable(True)
        self.moeda.addItems(["BRL", "USD", "EUR", "ARS"])
        form_rfq.addRow("Prefixo do número", self.prefixo)
        form_rfq.addRow("", self.exemplo_numero)
        form_rfq.addRow("Prazo padrão de resposta", self.prazo)
        form_rfq.addRow("Moeda padrão", self.moeda)
        layout.addWidget(grupo_rfq)

        salvar = QHBoxLayout()
        salvar.addStretch()
        salvar.addWidget(botao("Salvar configurações", self._salvar, primario=True))
        layout.addLayout(salvar)

        # ------------------------------------------------ dados
        grupo_dados = QGroupBox("Dados")
        dados_layout = QVBoxLayout(grupo_dados)
        self.caminho = QLabel()
        self.caminho.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.caminho.setWordWrap(True)
        dados_layout.addWidget(self.caminho)
        explicacao = QLabel(
            "Cada cadastro fica em um arquivo próprio (fornecedores.json, projetos.json, rfqs.json…). "
            "Uma cópia de segurança diária é feita automaticamente na pasta 'backup'."
        )
        explicacao.setObjectName("dica")
        explicacao.setWordWrap(True)
        dados_layout.addWidget(explicacao)
        linha = QHBoxLayout()
        linha.addWidget(botao("Abrir pasta de dados", lambda: executar(self, lambda: abrir_arquivo(self.base.pasta))))
        linha.addWidget(botao("Fazer backup agora", self._backup))
        linha.addWidget(botao("Exportar tudo para Excel", self._exportar))
        linha.addWidget(botao("Importar planilha antiga (.xlsm)…", self._importar))
        linha.addStretch()
        dados_layout.addLayout(linha)
        layout.addWidget(grupo_dados)

        sobre = QLabel(f"{NOME_APP} {__version__}")
        sobre.setObjectName("dica")
        layout.addWidget(sobre)
        layout.addStretch()

    def atualizar(self) -> None:
        config = self.base.configuracoes
        self.empresa.setText(config.empresa)
        self.metodo.setCurrentIndex(max(0, self.metodo.findData(config.metodo_email)))
        self.copia_padrao.setText(config.copia_padrao)
        self.copiar_solicitante.setChecked(config.copiar_solicitante)
        self.colunas_fornecedor.setChecked(config.incluir_colunas_fornecedor)
        self.assinatura.setPlainText(config.assinatura_html)
        self.prefixo.setText(config.prefixo_rfq)
        self.prazo.setValue(config.prazo_dias_uteis)
        self.moeda.setCurrentText(config.moeda_padrao)
        self.caminho.setText(f"Pasta de dados: {self.base.pasta}")

    def _salvar(self) -> None:
        invalidos = [e for e in separar_emails(self.copia_padrao.text()) if not email_valido(e)]
        if invalidos:
            erro(self, "E-mail(s) inválido(s) em 'Sempre em cópia': " + ", ".join(invalidos))
            return
        dados = self.base.configuracoes.model_dump()
        dados.update(
            empresa=self.empresa.text().strip(),
            metodo_email=self.metodo.currentData(),
            copia_padrao="; ".join(separar_emails(self.copia_padrao.text())),
            copiar_solicitante=self.copiar_solicitante.isChecked(),
            incluir_colunas_fornecedor=self.colunas_fornecedor.isChecked(),
            assinatura_html=self.assinatura.toPlainText().strip(),
            prefixo_rfq=self.prefixo.text().strip() or "RFQ",
            prazo_dias_uteis=self.prazo.value(),
            moeda_padrao=self.moeda.currentText().strip().upper() or "BRL",
        )
        ok, _ = executar(self, lambda: self.base.salvar_configuracoes(Configuracoes.model_validate(dados)))
        if ok:
            self.atualizar()
            self.janela.mensagem("Configurações salvas.")

    def _backup(self) -> None:
        ok, destino = executar(self, self.base.backup)
        if ok:
            informar(self, f"Cópia de segurança criada em:\n{destino}")

    def _exportar(self) -> None:
        sugestao = str(Path.home() / f"RFQ_Control_{date.today():%Y-%m-%d}.xlsx")
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar para Excel", sugestao, "Planilha Excel (*.xlsx)")
        if caminho:
            ok, destino = executar(self, lambda: exportar_rfqs(self.base, Path(caminho)))
            if ok:
                self.janela.mensagem(f"Exportado: {destino}")

    def _importar(self) -> None:
        if importar_planilha_antiga(self.janela):
            self.atualizar()
