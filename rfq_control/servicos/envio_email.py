"""Entrega do e-mail montado: Outlook (rascunho para revisão ou envio direto) ou arquivo .eml.

- **Revisão** (padrão, como a macro antiga): o e-mail abre como rascunho e a RFQ fica
  "Aguardando envio". Ela só passa a Enviada quando o e-mail aparece nos Itens Enviados do
  Outlook (ou quando o usuário confirma o envio). Rascunho apagado sem enviar = RFQ em rascunho.
- **Envio direto**: o Outlook envia na hora e a RFQ é registrada como enviada.
- **Cobrança**: responde ao e-mail original da RFQ (mesma conversa). Sem o original, sai um
  e-mail "RE:" com a solicitação original citada abaixo.
"""

from __future__ import annotations

import html
import logging
import mimetypes
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import make_msgid
from pathlib import Path
from typing import Any

from ..armazenamento import BaseDados
from ..modelos import RFQ, Idioma, MetodoEmail, TipoModelo
from .email_rfq import FONTE, EmailMontado, montar_email
from .formatos import data_curta
from .rfq import ErroNegocio, confirmar_envio, pendentes_de_envio, registrar_envio, registrar_revisao

log = logging.getLogger(__name__)

PASTA_ITENS_ENVIADOS = 5  # olFolderSentMail
LIMITE_BUSCA = 200  # e-mails examinados por busca nos Itens Enviados
_PREFIXO_RESPOSTA = re.compile(r"^\s*(re|res|fw|fwd|enc|tr|aw|wg|rv)\s*:", re.IGNORECASE)


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
    resposta: bool = False  # cobrança aberta como resposta ao e-mail original no Outlook


def _nome_arquivo_seguro(texto: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", texto).strip("_") or "email"


def assinatura_em_html(texto: str) -> str:
    """A assinatura pode ser digitada como texto simples ou HTML."""
    if re.search(r"<[a-zA-Z][^>]*>", texto):
        return texto
    return "<br>".join(html.escape(linha) for linha in texto.splitlines())


def gerar_eml(
    email: EmailMontado, destino: Path, assinatura_html: str = "", message_id: str = "", em_resposta_a: str = ""
) -> Path:
    """Grava um .eml marcado como não enviado (abre como rascunho editável no Outlook)."""
    mensagem = EmailMessage(policy=SMTP)
    mensagem["To"] = ", ".join(email.para)
    if email.copia:
        mensagem["Cc"] = ", ".join(email.copia)
    mensagem["Subject"] = email.assunto
    mensagem["X-Unsent"] = "1"
    if message_id:
        mensagem["Message-ID"] = message_id
    if em_resposta_a:
        mensagem["In-Reply-To"] = em_resposta_a
        mensagem["References"] = em_resposta_a
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
    """Coloca o corpo logo após a tag <body> do e-mail (antes da assinatura e da mensagem citada)."""
    encontrado = re.search(r"<body[^>]*>", html_outlook, flags=re.IGNORECASE)
    if not encontrado:
        return corpo_html + html_outlook
    fim = encontrado.end()
    return html_outlook[:fim] + corpo_html + "<br>" + html_outlook[fim:]


# ---------------------------------------------------------------- Outlook


def _conectar_outlook(iniciar: bool = True) -> Any:
    """Outlook da área de trabalho. ``iniciar=False`` só usa um Outlook já aberto (não abre o programa)."""
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as erro:
        raise ErroOutlook("A automação do Outlook só está disponível no Windows.") from erro
    try:
        if iniciar:
            return win32com.client.Dispatch("Outlook.Application")
        return win32com.client.GetActiveObject("Outlook.Application")
    except Exception as erro:  # erros COM vêm como pywintypes.com_error
        raise ErroOutlook(f"Não foi possível conectar ao Outlook: {erro}") from erro


def _preencher_e_mostrar(mensagem: Any, email: EmailMontado, enviar: bool, destinatarios: bool = True) -> None:
    if enviar:
        mensagem.GetInspector  # noqa: B018 - carrega a assinatura padrão sem abrir a janela
    else:
        mensagem.Display()  # exibe primeiro para o Outlook inserir a assinatura padrão
    html_com_assinatura = mensagem.HTMLBody or ""
    if destinatarios:
        mensagem.To = "; ".join(email.para)
        mensagem.CC = "; ".join(email.copia)
        mensagem.Subject = email.assunto
    mensagem.HTMLBody = inserir_antes_da_assinatura(html_com_assinatura, email.html)
    for anexo in email.anexos:
        mensagem.Attachments.Add(str(anexo))
    if enviar:
        mensagem.Send()


def abrir_no_outlook(email: EmailMontado, enviar: bool = False) -> None:
    """Cria o e-mail no Outlook da área de trabalho, como a macro antiga.

    Com ``enviar=False`` o rascunho é exibido para revisão; com ``enviar=True`` é enviado na hora.
    Nos dois casos a assinatura padrão do Outlook é incluída.
    """
    outlook = _conectar_outlook()
    try:
        _preencher_e_mostrar(outlook.CreateItem(0), email, enviar)  # 0 = olMailItem
    except Exception as erro:
        acao = "enviar pelo" if enviar else "abrir o"
        raise ErroOutlook(f"Não foi possível {acao} Outlook: {erro}") from erro


def _data_hora(valor: Any) -> datetime | None:
    """Datas do Outlook (horário local) como datetime sem fuso."""
    if not isinstance(valor, datetime):
        return None
    return datetime(valor.year, valor.month, valor.day, valor.hour, valor.minute, valor.second)


def _padrao_numero(numero: str) -> re.Pattern:
    # RFQ2026001 não pode casar com RFQ20260011 nem com a parte RFQ2026001-2
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(numero)}(?![0-9]|-[0-9])", re.IGNORECASE)


def emails_enviados_com(outlook: Any, numero: str, desde: datetime | None = None) -> list[tuple[datetime | None, Any]]:
    """E-mails dos Itens Enviados com o número da RFQ no assunto, do mais recente ao mais antigo."""
    itens = outlook.GetNamespace("MAPI").GetDefaultFolder(PASTA_ITENS_ENVIADOS).Items
    try:
        itens = itens.Restrict(f"@SQL=\"urn:schemas:httpmail:subject\" LIKE '%{numero}%'")
    except Exception:  # noqa: BLE001 - algumas contas não aceitam o filtro: percorre os mais recentes
        log.info("Itens Enviados sem filtro por assunto; percorrendo os mais recentes.")
    try:
        itens.Sort("[SentOn]", True)
    except Exception:  # noqa: BLE001
        pass
    padrao = _padrao_numero(numero)
    encontrados = []
    for posicao, item in enumerate(itens):
        if posicao >= LIMITE_BUSCA:
            break
        if not padrao.search(str(getattr(item, "Subject", "") or "")):
            continue
        enviado = _data_hora(getattr(item, "SentOn", None))
        if desde and enviado and enviado < desde:
            continue
        encontrados.append((enviado, item))
    encontrados.sort(key=lambda par: par[0] or datetime.min, reverse=True)
    return encontrados


def _eh_resposta(item: Any) -> bool:
    return bool(_PREFIXO_RESPOSTA.match(str(getattr(item, "Subject", "") or "")))


def localizar_email_da_rfq(outlook: Any, numero: str) -> Any | None:
    """O e-mail de RFQ enviado mais recente (não uma resposta ou encaminhamento)."""
    encontrados = emails_enviados_com(outlook, numero)
    originais = [item for _quando, item in encontrados if not _eh_resposta(item)]
    return originais[0] if originais else None


def responder_no_outlook(original: Any, email: EmailMontado, enviar: bool = False) -> None:
    """Responde a todos no e-mail original, com o texto de ``email`` acima da mensagem citada."""
    try:
        resposta = original.ReplyAll()
        _preencher_e_mostrar(resposta, replace(email, anexos=[]), enviar, destinatarios=False)
    except Exception as erro:
        acao = "enviar" if enviar else "abrir"
        raise ErroOutlook(f"Não foi possível {acao} a resposta no Outlook: {erro}") from erro


def confirmar_envios_outlook(base: BaseDados, outlook: Any | None = None) -> list[RFQ]:
    """Passa para Enviada as RFQs aguardando envio cujo e-mail já está nos Itens Enviados.

    Só usa um Outlook já aberto (a conferência automática nunca abre o Outlook); sem ele não faz nada.
    """
    pendentes = pendentes_de_envio(base)
    if not pendentes:
        return []
    try:
        outlook = outlook or _conectar_outlook(iniciar=False)
    except ErroOutlook:
        return []
    confirmadas = []
    for rfq in pendentes:
        desde = rfq.aguardando_envio_desde - timedelta(minutes=5)
        try:
            encontrados = [(q, i) for q, i in emails_enviados_com(outlook, rfq.numero, desde) if not _eh_resposta(i)]
        except Exception as erro:  # noqa: BLE001 - uma falha não impede as demais
            log.warning("Falha ao procurar %s nos Itens Enviados: %s", rfq.numero, erro)
            continue
        if not encontrados:
            continue
        quando = encontrados[-1][0]  # o primeiro envio depois de abrir o e-mail
        texto = "Envio confirmado nos Itens Enviados do Outlook" + (f" ({data_curta(quando)})" if quando else "")
        confirmadas.append(confirmar_envio(base, rfq, quando.date() if quando else None, texto))
    return confirmadas


# ---------------------------------------------------------------- entrega


def entregar(
    base: BaseDados,
    email: EmailMontado,
    nome_arquivo: str,
    enviar: bool = False,
    abrir: bool = True,
    message_id: str = "",
    em_resposta_a: str = "",
) -> tuple[bool, Path | None, str]:
    """Abre (ou envia) o e-mail no Outlook; sem Outlook, gera o .eml. Devolve (via Outlook, .eml, aviso)."""
    config = base.configuracoes
    if enviar:
        if config.metodo_email != MetodoEmail.OUTLOOK:
            raise ErroNegocio("O envio automático usa o Outlook. Em Configurações, escolha abrir os e-mails via Outlook.")
        try:
            abrir_no_outlook(email, enviar=True)
        except ErroOutlook as erro:
            raise ErroNegocio(str(erro)) from erro
        return True, None, ""
    aviso = ""
    if config.metodo_email == MetodoEmail.OUTLOOK and abrir:
        try:
            abrir_no_outlook(email)
            return True, None, ""
        except ErroOutlook as erro:
            log.warning("Outlook indisponível, gerando .eml: %s", erro)
            aviso = f"{erro} O e-mail foi gerado como arquivo .eml."
    destino = base.pasta_emails / f"{_nome_arquivo_seguro(nome_arquivo)}.eml"
    arquivo = gerar_eml(email, destino, config.assinatura_html, message_id, em_resposta_a)
    if abrir:
        abrir_arquivo(arquivo)
    return False, arquivo, aviso


def _cabecalho_citacao(original: EmailMontado, rfq: RFQ) -> str:
    rotulos = {
        Idioma.PT: ("Mensagem original", "Enviado", "Para", "Assunto"),
        Idioma.ES: ("Mensaje original", "Enviado", "Para", "Asunto"),
        Idioma.EN: ("Original message", "Sent", "To", "Subject"),
    }[original.idioma]
    linhas = [f"<b>{rotulos[0]}</b>"]
    if rfq.data_envio:
        linhas.append(f"<b>{rotulos[1]}:</b> {data_curta(rfq.data_envio)}")
    linhas.append(f"<b>{rotulos[2]}:</b> {html.escape('; '.join(original.para))}")
    linhas.append(f"<b>{rotulos[3]}:</b> {html.escape(original.assunto)}")
    return (
        f'<div style="border-top:1px solid #B5B5B5;margin:18px 0 12px 0;padding-top:8px;font-family:{FONTE};'
        f'font-size:10pt;color:#444444;">' + "<br>".join(linhas) + "</div>"
    )


def cobranca_com_original(base: BaseDados, rfq: RFQ, cobranca: EmailMontado) -> EmailMontado:
    """Cobrança como e-mail "RE:" com a solicitação original citada abaixo (quando não dá para responder)."""
    original = montar_email(base, rfq, rfq.idioma, TipoModelo.RFQ)
    assunto = rfq.assunto_email or original.assunto
    return replace(
        cobranca,
        assunto=assunto if _PREFIXO_RESPOSTA.match(assunto) else f"RE: {assunto}",
        html=cobranca.html + _cabecalho_citacao(original, rfq) + original.html,
        texto=cobranca.texto + "\n\n----- " + assunto + " -----\n\n" + original.texto,
        anexos=[],
    )


def _gerar_cobranca(
    base: BaseDados, rfq: RFQ, email: EmailMontado, abrir: bool, enviar: bool
) -> ResultadoEmail:
    """Cobrança na mesma conversa: responde ao e-mail da RFQ nos Itens Enviados do Outlook.

    Sem o e-mail original (ou sem Outlook), sai um e-mail "RE:" com a solicitação original citada.
    """
    config = base.configuracoes
    aviso_busca = ""
    if config.metodo_email == MetodoEmail.OUTLOOK and (abrir or enviar):
        original = None
        try:
            original = localizar_email_da_rfq(_conectar_outlook(), rfq.numero)
            if original is None:
                aviso_busca = (f"O e-mail da {rfq.numero} não foi encontrado nos Itens Enviados do Outlook; a "
                               "cobrança foi aberta como e-mail novo (RE:) com a solicitação original abaixo.")
        except ErroOutlook as erro:
            if enviar:
                raise ErroNegocio(str(erro)) from erro
            log.warning("Cobrança sem Outlook: %s", erro)
        except Exception as erro:  # noqa: BLE001 - busca falhou: segue como e-mail novo
            log.warning("Falha ao procurar o e-mail da %s: %s", rfq.numero, erro)
        if original is not None:
            try:
                responder_no_outlook(original, email, enviar)
            except ErroOutlook as erro:
                if enviar:
                    raise ErroNegocio(str(erro)) from erro
                aviso_busca = f"{erro} A cobrança foi aberta como e-mail novo (RE:)."
            else:
                acao = "enviado" if enviar else "aberto para revisão"
                rfq = rfq.model_copy(deep=True)
                rfq.registrar(f"E-mail de cobrança {acao} no Outlook como resposta ao e-mail da RFQ — "
                              f"{email.idioma.rotulo}")
                return ResultadoEmail(base.rfqs.salvar(rfq), email, True, enviado=enviar, resposta=True)

    completo = cobranca_com_original(base, rfq, email)
    via_outlook, arquivo, aviso_entrega = entregar(
        base, completo, f"{rfq.numero}_cobranca", enviar, abrir, em_resposta_a=rfq.message_id
    )
    if enviar:
        acao = "enviado pelo Outlook (e-mail novo, RE:)"
    else:
        acao = "aberto para revisão (" + ("Outlook" if via_outlook else "arquivo .eml") + ")"
    rfq = rfq.model_copy(deep=True)
    rfq.registrar(f"E-mail de cobrança {acao} — {email.idioma.rotulo}")
    return ResultadoEmail(
        base.rfqs.salvar(rfq), completo, via_outlook, arquivo_eml=arquivo,
        aviso=" ".join(a for a in (aviso_busca, aviso_entrega) if a), enviado=enviar,
    )


def gerar_email_rfq(
    base: BaseDados,
    rfq_id: str,
    idioma: Idioma | None = None,
    tipo: TipoModelo = TipoModelo.RFQ,
    abrir: bool = True,
    hoje: date | None = None,
    enviar: bool = False,
) -> ResultadoEmail:
    """Monta o e-mail da RFQ e registra o que aconteceu na RFQ.

    ``enviar=False``: abre o rascunho para revisão (Outlook, ou .eml como alternativa); a RFQ fica
    "Aguardando envio" até o envio ser confirmado.
    ``enviar=True``: envia direto pelo Outlook e registra o envio; se o Outlook falhar, nada é registrado.
    """
    rfq = base.rfqs.obter(rfq_id)
    if not rfq:
        raise ErroNegocio("RFQ não encontrada.")
    tipo = TipoModelo(tipo)  # o Qt devolve o valor dos combos como texto
    email = montar_email(base, rfq, idioma, tipo, hoje)
    if tipo == TipoModelo.COBRANCA:
        return _gerar_cobranca(base, rfq, email, abrir, enviar)

    message_id = make_msgid(domain="rfq-control")
    via_outlook, arquivo, aviso = entregar(
        base, email, f"{rfq.numero}_{tipo.name.lower()}", enviar, abrir, message_id=message_id
    )
    if enviar:
        rfq = registrar_envio(
            base, rfq, email.idioma, f"E-mail de RFQ enviado pelo Outlook — {email.idioma.rotulo}", hoje,
            email.prazo, assunto=email.assunto,
        )
    else:
        meio = "Outlook" if via_outlook else "arquivo .eml"
        rfq = registrar_revisao(
            base, rfq, email.idioma,
            f"E-mail de RFQ aberto para revisão ({meio}) — {email.idioma.rotulo}. A RFQ passa a Enviada quando "
            "o e-mail aparecer nos Itens Enviados.",
            email.prazo, email.assunto, "" if via_outlook else message_id,
        )
    return ResultadoEmail(
        rfq=rfq, email=email, via_outlook=via_outlook, arquivo_eml=arquivo, aviso=aviso, enviado=enviar
    )
