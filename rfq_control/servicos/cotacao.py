"""Comparativo de propostas de um pacote (equalização) e competitividade dos fornecedores.

Cada RFQ guarda a cotação por item (preço, ferramental, lead time, frete e embalagem) na moeda da RFQ.
O comparativo converte tudo para a moeda do pacote (câmbio informado na tela) e aponta os melhores
valores: custo unitário (preço + frete + embalagem) e lead time por item; custo das peças (custo unitário ×
volume anual — ou quantidade), ferramental e maior lead time por proposta.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..armazenamento import BaseDados
from ..modelos import RFQ, CotacaoItem, Item, Pacote, StatusRFQ
from .rfq import ErroNegocio

STATUS_FORA = {StatusRFQ.CANCELADA, StatusRFQ.DECLINADA}  # não entram no comparativo
_TOLERANCIA = 1e-9


@dataclass
class Proposta:
    rfq: RFQ
    fornecedor: str
    taxa: float | None  # câmbio da moeda da RFQ para a do comparativo (None: falta informar)
    total_pecas: float | None = None  # Σ custo unitário × peso do item, na moeda do comparativo
    ferramental: float | None = None
    lead_time: int | None = None  # o maior lead time entre os itens (dias)
    itens_cotados: int = 0
    completa: bool = False  # todos os itens do pacote com preço

    @property
    def moeda(self) -> str:
        return self.rfq.moeda.upper()

    def converter(self, valor: float | None) -> float | None:
        return None if valor is None or self.taxa is None else valor * self.taxa

    def item(self, item_id: str) -> CotacaoItem | None:
        return self.rfq.cotacao_do_item(item_id)


@dataclass
class Comparativo:
    pacote: Pacote
    moeda: str
    itens: list[Item]
    propostas: list[Proposta]
    sem_cotacao: list[RFQ] = field(default_factory=list)  # RFQs do pacote ainda sem cotação por item
    moedas_sem_cambio: list[str] = field(default_factory=list)
    # (item_id, "custo" | "ferramental" | "lead_time") → RFQs com o melhor valor daquele item
    melhores_itens: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    melhor_total: set[str] = field(default_factory=set)
    melhor_ferramental: set[str] = field(default_factory=set)
    melhor_lead_time: set[str] = field(default_factory=set)

    def melhor(self, item_id: str, campo: str, rfq_id: str) -> bool:
        return rfq_id in self.melhores_itens.get((item_id, campo), set())


def _menores(valores: dict[str, float | None]) -> set[str]:
    """RFQs com o menor valor — só quando há ao menos duas propostas para comparar."""
    validos = {k: v for k, v in valores.items() if v is not None}
    if len(validos) < 2:
        return set()
    menor = min(validos.values())
    return {k for k, v in validos.items() if v - menor <= _TOLERANCIA}


def _proposta(base: BaseDados, rfq: RFQ, pacote: Pacote, moeda: str) -> Proposta:
    fornecedor = base.fornecedores.obter(rfq.fornecedor_id)
    taxa = 1.0 if rfq.moeda.upper() == moeda else pacote.cambios.get(rfq.moeda.upper())
    proposta = Proposta(rfq, fornecedor.nome if fornecedor else "(excluído)", taxa)
    total = ferramental = 0.0
    tem_ferramental = False
    leads = []
    for item in pacote.itens:
        cotacao = rfq.cotacao_do_item(item.id)
        if cotacao is None:
            continue
        custo = cotacao.custo_unitario()
        if custo is not None:
            proposta.itens_cotados += 1
            total += custo * item.peso()
        if cotacao.ferramental is not None:
            tem_ferramental = True
            ferramental += cotacao.ferramental
        if cotacao.lead_time_dias is not None:
            leads.append(cotacao.lead_time_dias)
    proposta.completa = bool(pacote.itens) and proposta.itens_cotados == len(pacote.itens)
    proposta.total_pecas = proposta.converter(total) if proposta.itens_cotados else None
    proposta.ferramental = proposta.converter(ferramental) if tem_ferramental else None
    proposta.lead_time = max(leads) if leads else None
    return proposta


def comparar(base: BaseDados, pacote_id: str, rfqs: list[RFQ] | None = None) -> Comparativo:
    """Comparativo das propostas do pacote (``rfqs``: as RFQs do pacote, se já estiverem à mão)."""
    pacote = base.pacotes.obter(pacote_id)
    if not pacote:
        raise ErroNegocio("Pacote não encontrado.")
    moeda = (pacote.moeda_comparativo or base.configuracoes.moeda_padrao).upper()
    rfqs = [r for r in (rfqs if rfqs is not None else base.rfqs_do_pacote(pacote_id)) if r.status not in STATUS_FORA]
    com_cotacao = [r for r in rfqs if any(not c.vazia() for c in r.cotacao)]
    ids_com_cotacao = {r.id for r in com_cotacao}
    comparativo = Comparativo(
        pacote=pacote,
        moeda=moeda,
        itens=list(pacote.itens),
        propostas=[_proposta(base, r, pacote, moeda) for r in com_cotacao],
        sem_cotacao=[r for r in rfqs if r.id not in ids_com_cotacao],
    )
    comparativo.moedas_sem_cambio = sorted({p.moeda for p in comparativo.propostas if p.taxa is None})
    convertidas = [p for p in comparativo.propostas if p.taxa is not None]
    for item in pacote.itens:
        custos: dict[str, float | None] = {}
        ferramentais: dict[str, float | None] = {}
        leads: dict[str, float | None] = {}
        for proposta in convertidas:
            cotacao = proposta.item(item.id)
            if cotacao is not None:
                custos[proposta.rfq.id] = proposta.converter(cotacao.custo_unitario())
                ferramentais[proposta.rfq.id] = proposta.converter(cotacao.ferramental)
                leads[proposta.rfq.id] = cotacao.lead_time_dias
        comparativo.melhores_itens[(item.id, "custo")] = _menores(custos)
        comparativo.melhores_itens[(item.id, "ferramental")] = _menores(ferramentais)
        comparativo.melhores_itens[(item.id, "lead_time")] = _menores(leads)
    completas = [p for p in convertidas if p.completa]
    comparativo.melhor_total = _menores({p.rfq.id: p.total_pecas for p in completas})
    comparativo.melhor_ferramental = _menores({p.rfq.id: p.ferramental for p in completas})
    comparativo.melhor_lead_time = _menores({p.rfq.id: p.lead_time for p in completas})
    return comparativo


def definir_cambio(base: BaseDados, pacote_id: str, moeda: str, cambios: dict[str, float]) -> Pacote:
    """Grava a moeda do comparativo e o câmbio de cada outra moeda para ela (taxa vazia ou zero = sem câmbio)."""
    pacote = base.pacotes.obter(pacote_id)
    if not pacote:
        raise ErroNegocio("Pacote não encontrado.")
    moeda = moeda.strip().upper()
    if not moeda:
        raise ErroNegocio("Informe a moeda do comparativo.")
    cambios = {m.strip().upper(): t for m, t in cambios.items() if t and m.strip() and m.strip().upper() != moeda}
    return base.pacotes.salvar(pacote.model_copy(update={"moeda_comparativo": moeda, "cambios": cambios}))


def competitividade(base: BaseDados) -> dict[str, tuple[int, int]]:
    """Por fornecedor: (vezes com o menor custo das peças, pacotes em que concorreu com proposta completa)."""
    por_pacote: dict[str, list[RFQ]] = defaultdict(list)
    for rfq in base.rfqs:
        por_pacote[rfq.pacote_id].append(rfq)
    melhores: dict[str, int] = defaultdict(int)
    concorrencias: dict[str, int] = defaultdict(int)
    for pacote_id, rfqs in por_pacote.items():
        if not base.pacotes.obter(pacote_id) or not any(r.cotacao for r in rfqs):
            continue
        comparativo = comparar(base, pacote_id, rfqs)
        candidatas = [p for p in comparativo.propostas if p.completa and p.taxa is not None]
        if len(candidatas) < 2:
            continue
        for proposta in candidatas:
            concorrencias[proposta.rfq.fornecedor_id] += 1
            if proposta.rfq.id in comparativo.melhor_total:
                melhores[proposta.rfq.fornecedor_id] += 1
    return {f: (melhores[f], total) for f, total in concorrencias.items()}
