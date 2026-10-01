"""Entrega do e-mail montado: rascunho no Outlook ou arquivo .eml.

O e-mail nunca é enviado automaticamente — assim como na macro antiga, ele é
aberto para revisão e o usuário clica em "Enviar".
"""

from __future__ import annotations

import html
import logging
import mimetypes
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path

from ..armazenamento import BaseDados
from ..modelos import RFQ, Idioma, MetodoEmail, TipoModelo
from .email_rfq import EmailMontado, montar_email
from .rfq import ErroNegocio, registrar_envio

log = logging.getLogger(__name__)


class ErroOutlook(Exception):
    """O Outlook não pôde ser usado (não instalado, fechado com erro, etc.)."""


@dataclass
class ResultadoEmail:
    rfq: RFQ
    email: EmailMontado
    via_outlook: bool
    arquivo_eml: Path | None = None
    aviso: str = ""
    enviado: bool = False  # True = enviado direto; False = aberto para revisão


def _nome_arquivo_seguro(texto: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", texto).strip("_") or "email"


def assinatura_em_html(texto: str) -> str:
    """A assinatura pode ser digitada como texto simples ou HTML."""
    if re.search(r"<[a-zA-Z][^>]*>", texto):
        return texto
    return "<br>".join(html.escape(linha) for linha in texto.splitlines())


def gerar_eml(email: EmailMontado, destino: Path, assinatura_html: str = "") -> Path:
    """Grava um .eml marcado como não enviado (abre como rascunho editável no Outlook)."""
    mensagem = EmailMessage(policy=SMTP)
    mensagem["To"] = ", ".join(email.para)
    if email.copia:
        mensagem["Cc"] = ", ".join(email.copia)
    mensagem["Subject"] = email.assunto
    mensagem["X-Unsent"] = "1"
    texto = email.texto
    corpo_html = email.html
    if assinatura_html.strip():
        assinatura = assinatura_em_html(assinatura_html.strip())
        corpo_html += "<br>" + assinatura
        texto += "\n\n" + html.unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", assinatura)))
    mensagem.set_content(texto)
    mensagem.add_alternative(
        f'<html><head><meta charset="utf-8"></head><body>{corpo_html}</body></html>', subtype="html"
    )
    for anexo in email.anexos:
        tipo, _ = mimetypes.guess_type(anexo.name)
        principal, secundario = (tipo or "application/octet-stream").split("/", 1)
        mensagem.add_attachment(anexo.read_bytes(), maintype=principal, subtype=secundario, filename=anexo.name)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(bytes(mensagem))
    return destino


def abrir_arquivo(caminho: Path) -> None:
    """Abre um arquivo ou pasta com o programa padrão do sistema."""
    if sys.platform.startswith("win"):
        os.startfile(str(caminho))  # noqa: S606 - arquivo local gerado pelo próprio app
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(caminho)])
    else:
        subprocess.Popen(["xdg-open", str(caminho)])


def inserir_antes_da_assinatura(html_outlook: str, corpo_html: str) -> str:
    """Coloca o corpo logo após a tag <body> do e-mail em branco (que já traz a assinatura)."""
    encontrado = re.search(r"<body[^>]*>", html_outlook, flags=re.IGNORECASE)
    if not encontrado:
        return corpo_html + html_outlook
    fim = encontrado.end()
    return html_outlook[:fim] + corpo_html + "<br>" + html_outlook[fim:]


def abrir_no_outlook(email: EmailMontado, enviar: bool = False) -> None:
    """Cria o e-mail no Outlook da área de trabalho, como a macro antiga.

    Com ``enviar=False`` o rascunho é exibido para revisão; com ``enviar=True`` é enviado na hora.
    Nos dois casos a assinatura padrão do Outlook é incluída.
    """
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as erro:
        raise ErroOutlook("A automação do Outlook só está disponível no Windows.") from erro
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mensagem = outlook.CreateItem(0)  # 0 = olMailItem
        if enviar:
            mensagem.GetInspector  # noqa: B018 - carrega a assinatura padrão sem abrir a janela
        else:
            mensagem.Display()  # exibe primeiro para o Outlook inserir a assinatura padrão
        html_com_assinatura = mensagem.HTMLBody or ""
        mensagem.To = "; ".join(email.para)
        mensagem.CC = "; ".join(email.copia)
        mensagem.Subject = email.assunto
        mensagem.HTMLBody = inserir_antes_da_assinatura(html_com_assinatura, email.html)
        for anexo in email.anexos:
            mensagem.Attachments.Add(str(anexo))
        if enviar:
            mensagem.Send()
    except Exception as erro:  # erros COM vêm como pywintypes.com_error
        acao = "enviar pelo" if enviar else "abrir o"
        raise ErroOutlook(f"Não foi possível {acao} Outlook: {erro}") from erro


def gerar_email_rfq(
    base: BaseDados,
    rfq_id: str,
    idioma: Idioma | None = None,
    tipo: TipoModelo = TipoModelo.RFQ,
    abrir: bool = True,
    hoje: date | None = None,
    enviar: bool = False,
) -> ResultadoEmail:
    """Monta o e-mail da RFQ e registra o envio na RFQ.

    ``enviar=False``: abre o rascunho para revisão (Outlook, ou .eml como alternativa).
    ``enviar=True``: envia direto pelo Outlook; se o Outlook falhar, nada é registrado.
    """
    rfq = base.rfqs.obter(rfq_id)
    if not rfq:
        raise ErroNegocio("RFQ não encontrada.")
    email = montar_email(base, rfq, idioma, tipo, hoje)
    config = base.configuracoes

    via_outlook, arquivo, aviso = False, None, ""
    if enviar:
        if config.metodo_email != MetodoEmail.OUTLOOK:
            raise ErroNegocio("O envio automático usa o Outlook. Em Configurações, escolha abrir os e-mails via Outlook.")
        try:
            abrir_no_outlook(email, enviar=True)
        except ErroOutlook as erro:
            raise ErroNegocio(str(erro)) from erro
        via_outlook = True
    elif config.metodo_email == MetodoEmail.OUTLOOK and abrir:
        try:
            abrir_no_outlook(email)
            via_outlook = True
        except ErroOutlook as erro:
            log.warning("Outlook indisponível, gerando .eml: %s", erro)
            aviso = f"{erro} O e-mail foi gerado como arquivo .eml."
    if not via_outlook:
        destino = base.pasta_emails / f"{_nome_arquivo_seguro(rfq.numero)}_{tipo.name.lower()}.eml"
        arquivo = gerar_eml(email, destino, config.assinatura_html)
        if abrir:
            abrir_arquivo(arquivo)

    if enviar:
        acao = "enviado pelo Outlook"
    else:
        acao = "aberto para revisão (" + ("Outlook" if via_outlook else "arquivo .eml") + ")"
    if tipo == TipoModelo.COBRANCA:
        rfq = rfq.model_copy(deep=True)
        rfq.registrar(f"E-mail de cobrança {acao} — {email.idioma.rotulo}")
        rfq = base.rfqs.salvar(rfq)
    else:
        rfq = registrar_envio(
            base, rfq, email.idioma, f"E-mail de RFQ {acao} — {email.idioma.rotulo}", hoje, email.prazo
        )
    return ResultadoEmail(
        rfq=rfq, email=email, via_outlook=via_outlook, arquivo_eml=arquivo, aviso=aviso, enviado=enviar
    )
