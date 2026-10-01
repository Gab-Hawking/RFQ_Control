"""Ações usadas em várias telas (gerar e-mails, alterar status, abrir diálogos)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..modelos import RFQ, Idioma, StatusRFQ, TipoModelo
from ..servicos import rfq as srv
from ..servicos.envio_email import gerar_email_rfq
from .componentes import avisar, confirmar, executar, informar

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal


def gerar_emails(
    janela: JanelaPrincipal, rfqs: list[RFQ], idioma: Idioma | None = None, tipo: TipoModelo = TipoModelo.RFQ
) -> int:
    """Gera o e-mail de cada RFQ (abre no Outlook ou como .eml). Devolve quantos foram gerados."""
    if not rfqs:
        avisar(janela, "Selecione ao menos uma RFQ.")
        return 0
    canceladas = [r.numero for r in rfqs if r.status == StatusRFQ.CANCELADA]
    if canceladas:
        avisar(janela, "RFQs canceladas não geram e-mail: " + ", ".join(canceladas))
        rfqs = [r for r in rfqs if r.status != StatusRFQ.CANCELADA]
    if len(rfqs) > 3 and not confirmar(
        janela, f"Serão abertos {len(rfqs)} e-mails para revisão. Continuar?", "Gerar e-mails", "Gerar"
    ):
        return 0
    gerados, avisos = 0, []
    for rfq in rfqs:
        ok, resultado = executar(janela, lambda r=rfq: gerar_email_rfq(janela.base, r.id, idioma, tipo))
        if not ok:
            break
        gerados += 1
        if resultado.aviso and resultado.aviso not in avisos:
            avisos.append(resultado.aviso)
    if avisos:
        avisar(janela, "\n".join(avisos))
    if gerados:
        texto = "cobrança" if tipo == TipoModelo.COBRANCA else "RFQ"
        janela.mensagem(f"{gerados} e-mail(s) de {texto} gerado(s). Revise e clique em Enviar no Outlook.")
    return gerados


class DialogoStatus(QDialog):
    def __init__(self, quantidade: int, status_atual: StatusRFQ | None = None, pai=None):
        super().__init__(pai)
        self.setWindowTitle("Alterar status")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Alterar o status de {quantidade} RFQ(s) para:"))
        formulario = QFormLayout()
        self.status = QComboBox()
        for status in StatusRFQ:
            self.status.addItem(status.value, status)
        if status_atual:
            self.status.setCurrentIndex(self.status.findData(status_atual))
        self.observacao = QLineEdit()
        self.observacao.setPlaceholderText("Opcional — fica registrado no histórico")
        formulario.addRow("Novo status", self.status)
        formulario.addRow("Observação", self.observacao)
        layout.addLayout(formulario)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Alterar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)


def alterar_status(janela: JanelaPrincipal, rfqs: list[RFQ]) -> bool:
    if not rfqs:
        avisar(janela, "Selecione ao menos uma RFQ.")
        return False
    dialogo = DialogoStatus(len(rfqs), rfqs[0].status if len(rfqs) == 1 else None, janela)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return False
    ok, alteradas = executar(
        janela,
        lambda: srv.alterar_status(
            janela.base, [r.id for r in rfqs], dialogo.status.currentData(), dialogo.observacao.text().strip()
        ),
    )
    if ok:
        janela.mensagem(f"Status alterado em {len(alteradas)} RFQ(s).")
    return ok


def enviar_emails(
    janela: JanelaPrincipal,
    pacote_id: str | None = None,
    fornecedor_ids: list[str] | None = None,
    tipo: TipoModelo = TipoModelo.RFQ,
) -> bool:
    """Abre a tela de envio: escolher a RFQ e os fornecedores que vão receber o e-mail padrão."""
    from .dialogo_envio import DialogoEnvio

    if not len(janela.base.pacotes):
        informar(janela, "Ainda não há RFQs. Crie uma em '+ Nova solicitação' ou importe na Base de dados.")
        return False
    dialogo = DialogoEnvio(janela, pacote_id, fornecedor_ids, tipo)
    return dialogo.exec() == QDialog.DialogCode.Accepted


def nova_solicitacao(janela: JanelaPrincipal) -> bool:
    from .dialogo_pacote import DialogoPacote

    if not len(janela.base.projetos):
        informar(janela, "Cadastre ao menos um projeto antes (Base de dados → Cadastro de Projetos, ou botão '+' ao lado do projeto).")
    dialogo = DialogoPacote(janela)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return False
    rfqs = dialogo.rfqs_criadas
    janela.mensagem(f"Pacote criado com {len(rfqs)} RFQ(s): {', '.join(r.numero for r in rfqs)}")
    if rfqs:
        enviar_emails(janela, dialogo.original.id, [r.fornecedor_id for r in rfqs])
    return True


def abrir_pacote(janela: JanelaPrincipal, pacote_id: str, aba: str = "itens") -> bool:
    from .dialogo_pacote import DialogoPacote

    pacote = janela.base.pacotes.obter(pacote_id)
    if not pacote:
        avisar(janela, "Pacote não encontrado.")
        return False
    dialogo = DialogoPacote(janela, pacote, aba)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return False
    if dialogo.rfqs_criadas:
        enviar_emails(janela, pacote_id, [r.fornecedor_id for r in dialogo.rfqs_criadas])
    else:
        janela.mensagem("Pacote salvo.")
    return True


def abrir_rfq(janela: JanelaPrincipal, rfq: RFQ | None) -> bool:
    from .dialogo_rfq import DialogoRFQ

    if rfq is None:
        avisar(janela, "Selecione uma RFQ.")
        return False
    dialogo = DialogoRFQ(janela, janela.base.rfqs.obter(rfq.id) or rfq)
    dialogo.exec()
    return dialogo.alterou
