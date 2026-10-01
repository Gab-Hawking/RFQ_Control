"""Envio dos e-mails de RFQ: o usuário escolhe a RFQ (pacote) e os fornecedores.

Para cada fornecedor marcado, usa a RFQ que ele já tem no pacote ou cria uma nova (com número
próprio) e envia o e-mail padrão no idioma do fornecedor — como a macro da planilha, mas para
vários fornecedores de uma vez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..armazenamento import BaseDados
from ..modelos import RFQ, Fornecedor, Idioma, MetodoEmail, StatusRFQ, TipoModelo
from .email_rfq import idioma_padrao
from .envio_email import gerar_email_rfq
from .rfq import ErroNegocio, adicionar_fornecedores


@dataclass
class Destinatario:
    fornecedor_id: str
    idioma: Idioma | None = None  # None = idioma do fornecedor


@dataclass
class SituacaoFornecedor:
    """Um fornecedor na lista de envio, com a RFQ que ele já tem no pacote (se tiver)."""

    fornecedor: Fornecedor
    rfq: RFQ | None

    @property
    def tem_email(self) -> bool:
        return bool(self.fornecedor.emails_para())

    @property
    def idioma(self) -> Idioma:
        return idioma_padrao(self.rfq, self.fornecedor) if self.rfq else self.fornecedor.idioma

    @property
    def descricao(self) -> str:
        if not self.rfq:
            return "ainda não recebeu"
        texto = f"{self.rfq.numero} · {self.rfq.situacao()}"
        if self.rfq.data_envio:
            texto += f" em {self.rfq.data_envio:%d/%m/%Y}"
        return texto


def situacao_fornecedores(base: BaseDados, pacote_id: str) -> list[SituacaoFornecedor]:
    """Fornecedores ativos (e os que já estão no pacote), primeiro os que já têm RFQ."""
    rfqs = {r.fornecedor_id: r for r in base.rfqs_do_pacote(pacote_id) if r.status != StatusRFQ.CANCELADA}
    lista = [
        SituacaoFornecedor(f, rfqs.get(f.id))
        for f in base.fornecedores
        if f.ativo or f.id in rfqs
    ]
    return sorted(lista, key=lambda s: (s.rfq is None, s.fornecedor.nome.casefold()))


@dataclass
class ItemDisparo:
    fornecedor: str
    numero: str
    idioma: Idioma | None
    ok: bool
    mensagem: str


@dataclass
class ResultadoDisparo:
    itens: list[ItemDisparo] = field(default_factory=list)
    rfqs_criadas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def enviados(self) -> list[ItemDisparo]:
        return [i for i in self.itens if i.ok]

    @property
    def falhas(self) -> list[ItemDisparo]:
        return [i for i in self.itens if not i.ok]


def disparar(
    base: BaseDados,
    pacote_id: str,
    destinatarios: list[Destinatario],
    enviar: bool = False,
    abrir: bool = True,
    tipo: TipoModelo = TipoModelo.RFQ,
    hoje: date | None = None,
) -> ResultadoDisparo:
    """Envia (``enviar=True``) ou abre para revisão o e-mail padrão para cada fornecedor escolhido.

    Um fornecedor com problema (sem e-mail, Outlook recusou…) não interrompe os demais.
    """
    pacote = base.pacotes.obter(pacote_id)
    if not pacote:
        raise ErroNegocio("Selecione a RFQ (pacote de cotação) que será enviada.")
    if not destinatarios:
        raise ErroNegocio("Marque pelo menos um fornecedor.")
    if enviar and base.configuracoes.metodo_email != MetodoEmail.OUTLOOK:
        raise ErroNegocio("O envio automático usa o Outlook. Em Configurações, escolha abrir os e-mails via Outlook.")

    resultado = ResultadoDisparo()
    existentes = {r.fornecedor_id: r for r in base.rfqs_do_pacote(pacote_id) if r.status != StatusRFQ.CANCELADA}
    for destino in destinatarios:
        fornecedor = base.fornecedores.obter(destino.fornecedor_id)
        if not fornecedor:
            resultado.itens.append(ItemDisparo("?", "", None, False, "fornecedor não encontrado"))
            continue
        rfq = existentes.get(fornecedor.id)
        if not fornecedor.emails_para():
            # não cria RFQ para quem não pode receber o e-mail
            resultado.itens.append(ItemDisparo(
                fornecedor.nome, rfq.numero if rfq else "", destino.idioma, False,
                "sem e-mail (Para) cadastrado na Base de dados",
            ))
            continue
        if tipo == TipoModelo.COBRANCA and rfq is None:
            resultado.itens.append(ItemDisparo(fornecedor.nome, "", destino.idioma, False, "não tem RFQ neste pacote"))
            continue
        if rfq is None:
            [rfq] = adicionar_fornecedores(base, pacote_id, [fornecedor.id])
            existentes[fornecedor.id] = rfq
            resultado.rfqs_criadas.append(rfq.numero)
        try:
            enviado = gerar_email_rfq(base, rfq.id, destino.idioma, tipo, abrir, hoje, enviar)
        except ErroNegocio as erro:
            resultado.itens.append(ItemDisparo(fornecedor.nome, rfq.numero, destino.idioma, False, str(erro)))
            continue
        if enviado.aviso and enviado.aviso not in resultado.avisos:
            resultado.avisos.append(enviado.aviso)
        acao = "enviado" if enviar else "aberto para revisão"
        resultado.itens.append(ItemDisparo(fornecedor.nome, rfq.numero, enviado.email.idioma, True, acao))
    return resultado
