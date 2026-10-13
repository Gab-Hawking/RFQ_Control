"""Outlook de mentira para testar a automação (busca nos Itens Enviados, resposta, envio)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace


class Anexos(list):
    def Add(self, caminho):  # noqa: N802 - API do Outlook
        self.append(caminho)


class ItemFalso:
    def __init__(self, assunto: str = "", enviado: datetime | None = None,
                 corpo: str = "<html><body><div>Assinatura</div></body></html>"):
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
        self.exibido = True

    def Send(self):  # noqa: N802
        self.enviado_agora = True

    def ReplyAll(self):  # noqa: N802
        resposta = ItemFalso(f"RE: {self.Subject}", corpo=(
            "<html><body><div>Assinatura</div><div>De: eu · Assunto: " + self.Subject + "</div></body></html>"
        ))
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
    def __init__(self, enviados: list[ItemFalso] | None = None):
        self.enviados = Itens(enviados or [])
        self.criados: list[ItemFalso] = []

    def GetNamespace(self, _nome):  # noqa: N802
        return self

    def GetDefaultFolder(self, numero):  # noqa: N802
        assert numero == 5  # Itens Enviados
        return SimpleNamespace(Items=self.enviados)

    def CreateItem(self, _tipo):  # noqa: N802
        item = ItemFalso()
        self.criados.append(item)
        return item
