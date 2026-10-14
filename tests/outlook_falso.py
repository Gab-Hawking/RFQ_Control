"""Outlook de mentira para testar a automação (busca nos Itens Enviados, resposta, envio)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace


class ErroCOMFalso(Exception):
    """Como o pywintypes.com_error: args = (hresult, texto, excepinfo, argumento)."""


def erro_com(scode: int, descricao: str) -> ErroCOMFalso:
    """Erro que o Outlook devolve num método (DISP_E_EXCEPTION, com o motivo em excepinfo)."""
    return ErroCOMFalso(-2147352567, "Exceção.", (4096, "Microsoft Outlook", descricao, None, 0, scode), None)


class Anexos(list):
    def Add(self, caminho):  # noqa: N802 - API do Outlook
        self.append(caminho)


class ItemFalso:
    def __init__(self, assunto: str = "", enviado: datetime | None = None,
                 corpo: str = "<html><body><div>Assinatura</div></body></html>",
                 erro_envio: Exception | None = None, erro_exibir: Exception | None = None):
        self.erro_envio, self.erro_exibir = erro_envio, erro_exibir  # o Outlook recusa Send() / Display()
        self.Subject = assunto
        self.SentOn = enviado
        self.HTMLBody = corpo
        self.To = self.CC = ""
        self.Attachments = Anexos()
        self.respostas: list[ItemFalso] = []
        self.exibido = self.enviado_agora = False

    @property
    def GetInspector(self):  # noqa: N802
        return None

    def Display(self):  # noqa: N802
        if self.erro_exibir:
            raise self.erro_exibir
        self.exibido = True

    def Send(self):  # noqa: N802
        if self.erro_envio:
            raise self.erro_envio
        self.enviado_agora = True

    def ReplyAll(self):  # noqa: N802
        resposta = ItemFalso(f"RE: {self.Subject}", corpo=(
            "<html><body><div>Assinatura</div><div>De: eu · Assunto: " + self.Subject + "</div></body></html>"
        ), erro_envio=self.erro_envio, erro_exibir=self.erro_exibir)
        self.respostas.append(resposta)
        return resposta


class Itens(list):
    filtro = ""

    def Restrict(self, filtro):  # noqa: N802
        self.filtro = filtro
        return Itens(self)  # o filtro real é do Outlook; o app confere o número de novo

    def Sort(self, campo, decrescente):  # noqa: N802
        pass


class OutlookFalso:
    def __init__(self, enviados: list[ItemFalso] | None = None, **erros):
        self.enviados = Itens(enviados or [])
        self.criados: list[ItemFalso] = []
        self.erros = erros  # erro_envio / erro_exibir dos e-mails criados

    def GetNamespace(self, _nome):  # noqa: N802
        return self

    def GetDefaultFolder(self, numero):  # noqa: N802
        assert numero == 5  # Itens Enviados
        return SimpleNamespace(Items=self.enviados)

    def CreateItem(self, _tipo):  # noqa: N802
        item = ItemFalso(**self.erros)
        self.criados.append(item)
        return item
