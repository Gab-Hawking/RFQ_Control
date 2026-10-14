"""E-mail de agradecimento / status do projeto para os fornecedores das RFQs de um projeto.

Exemplo: o projeto foi declinado — escolha o projeto, marque as RFQs enviadas e cada fornecedor
recebe um e-mail (no idioma da RFQ) agradecendo a participação e informando a situação.
"""

from __future__ import annotations

from collections import OrderedDict

from ..armazenamento import BaseDados
from ..modelos import RFQ, Idioma, MetodoEmail, Projeto, StatusRFQ
from ..padroes import MOTIVOS_AGRADECIMENTO, MotivoAgradecimento
from .disparo import ItemDisparo, ResultadoDisparo
from .email_rfq import EmailMontado, montar_email_agradecimento
from .envio_email import entregar
from .rfq import ErroNegocio, alterar_status


def motivo(chave: str) -> MotivoAgradecimento:
    for opcao in MOTIVOS_AGRADECIMENTO:
        if opcao.chave == chave:
            return opcao
    raise ErroNegocio(f"Motivo desconhecido: {chave}")


def texto_motivo(opcao: MotivoAgradecimento, idioma: Idioma, texto_livre: str = "") -> str:
    if not opcao.textos:
        if not texto_livre.strip():
            raise ErroNegocio("Escreva a mensagem sobre a situação do projeto (motivo 'Outro').")
        return texto_livre.strip()
    return opcao.textos[Idioma(idioma)]


def rfqs_enviadas_do_projeto(base: BaseDados, projeto_id: str) -> list[RFQ]:
    """RFQs que já saíram para os fornecedores (rascunhos não recebem agradecimento)."""
    return [r for r in base.rfqs_do_projeto(projeto_id) if r.status != StatusRFQ.RASCUNHO]


def projetos_com_rfqs_enviadas(base: BaseDados) -> list[tuple[Projeto, int]]:
    projetos = []
    for projeto in sorted(base.projetos, key=lambda p: p.nome.casefold()):
        total = len(rfqs_enviadas_do_projeto(base, projeto.id))
        if total:
            projetos.append((projeto, total))
    return projetos


def _agrupar(base: BaseDados, rfq_ids: list[str]) -> OrderedDict[str, list[RFQ]]:
    rfqs = [r for r in (base.rfqs.obter(i) for i in rfq_ids) if r]
    if not rfqs:
        raise ErroNegocio("Marque pelo menos uma RFQ.")
    projetos = {getattr(base.pacotes.obter(r.pacote_id), "projeto_id", None) for r in rfqs}
    if len(projetos) > 1:
        raise ErroNegocio("Marque RFQs de um único projeto.")
    grupos: OrderedDict[str, list[RFQ]] = OrderedDict()
    for rfq in sorted(rfqs, key=lambda r: r.numero):
        grupos.setdefault(rfq.fornecedor_id, []).append(rfq)
    return grupos


def pre_visualizar(base: BaseDados, rfq_ids: list[str], chave_motivo: str, texto_livre: str = "") -> EmailMontado:
    """O e-mail do primeiro fornecedor marcado, como ele vai sair."""
    fornecedor_id, rfqs = next(iter(_agrupar(base, rfq_ids).items()))
    fornecedor = base.fornecedores.obter(fornecedor_id)
    if fornecedor is None:
        raise ErroNegocio("Fornecedor não encontrado.")
    opcao = motivo(chave_motivo)
    return montar_email_agradecimento(
        base, fornecedor, rfqs, rfqs[0].idioma, texto_motivo(opcao, rfqs[0].idioma, texto_livre)
    )


def enviar_agradecimento(
    base: BaseDados,
    rfq_ids: list[str],
    chave_motivo: str,
    texto_livre: str = "",
    enviar: bool = False,
    abrir: bool = True,
    novo_status: StatusRFQ | None = None,
) -> ResultadoDisparo:
    """Um e-mail por fornecedor (com todas as RFQs dele no projeto), no idioma em que a RFQ foi enviada.

    ``novo_status``: status aplicado às RFQs dos e-mails abertos/enviados (ex.: Cancelada). Um
    fornecedor com problema (sem e-mail, Outlook recusou…) não interrompe os demais.
    """
    opcao = motivo(chave_motivo)
    texto_motivo(opcao, Idioma.PT, texto_livre)  # valida o texto livre antes de abrir qualquer e-mail
    grupos = _agrupar(base, rfq_ids)
    if enviar and base.configuracoes.metodo_email != MetodoEmail.OUTLOOK:
        raise ErroNegocio("O envio automático usa o Outlook. Em Configurações, escolha abrir os e-mails via Outlook.")
    resultado = ResultadoDisparo()
    concluidas: list[str] = []
    acao = "enviado" if enviar else "aberto para revisão"
    for fornecedor_id, rfqs in grupos.items():
        numeros = ", ".join(r.numero for r in rfqs)
        fornecedor = base.fornecedores.obter(fornecedor_id)
        if fornecedor is None:
            resultado.itens.append(ItemDisparo("?", numeros, None, False, "fornecedor não encontrado"))
            continue
        idioma = rfqs[0].idioma
        try:
            email = montar_email_agradecimento(base, fornecedor, rfqs, idioma, texto_motivo(opcao, idioma, texto_livre))
            _via, _arquivo, aviso = entregar(
                base, email, f"agradecimento_{rfqs[0].numero}_{fornecedor.nome}", enviar, abrir
            )
        except ErroNegocio as erro:
            resultado.itens.append(ItemDisparo(fornecedor.nome, numeros, idioma, False, str(erro)))
            continue
        if aviso and aviso not in resultado.avisos:
            resultado.avisos.append(aviso)
        registradas = []
        for rfq in rfqs:
            copia = rfq.model_copy(deep=True)
            copia.registrar(f"E-mail de agradecimento / status ({opcao.rotulo}) {acao} — {idioma.rotulo}")
            registradas.append(copia)
        base.rfqs.salvar_varios(registradas)
        concluidas += [r.id for r in rfqs]
        resultado.itens.append(ItemDisparo(fornecedor.nome, numeros, idioma, True, acao))
    if novo_status and concluidas:
        novo_status = StatusRFQ(novo_status)
        if novo_status == StatusRFQ.NAO_SELECIONADA:
            # a vencedora nunca é rebaixada por um agradecimento de "outra proposta"
            concluidas = [i for i in concluidas if base.rfqs.obter(i).status != StatusRFQ.SELECIONADA]
        alterar_status(base, concluidas, novo_status, f"e-mail de agradecimento: {opcao.rotulo}")
    return resultado
