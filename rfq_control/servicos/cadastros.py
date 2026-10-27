"""Regras dos cadastros (nomes únicos e exclusão protegida)."""

from __future__ import annotations

from ..armazenamento import BaseDados, Colecao
from ..modelos import Commodity, Condicao, Feriado, Fornecedor, Projeto, StatusRFQ
from .dias_uteis import feriados_nacionais_brasil
from .formatos import normalizar_nome
from .rfq import ErroNegocio


def _nome_unico(colecao: Colecao, nome: str, identificador: str, tipo: str) -> None:
    chave = normalizar_nome(nome)
    for registro in colecao:
        if registro.id != identificador and normalizar_nome(registro.nome) == chave:
            raise ErroNegocio(f"Já existe {tipo} com o nome '{registro.nome}'.")


def salvar_fornecedor(base: BaseDados, fornecedor: Fornecedor) -> Fornecedor:
    _nome_unico(base.fornecedores, fornecedor.nome, fornecedor.id, "um fornecedor")
    if any(base.commodities.obter(i) is None for i in fornecedor.commodity_ids):
        raise ErroNegocio("Uma das commodities do fornecedor não existe mais. Revise a coluna Commodity.")
    ids = list(dict.fromkeys(fornecedor.commodity_ids))  # sem repetidas, na ordem escolhida
    if ids != fornecedor.commodity_ids:
        fornecedor = fornecedor.model_copy(update={"commodity_ids": ids})
    salvo = base.fornecedores.salvar(fornecedor)
    # RFQs ainda não enviadas acompanham o idioma do fornecedor (as com e-mail aberto já têm idioma)
    rascunhos = [
        r.model_copy(update={"idioma": salvo.idioma})
        for r in base.rfqs_do_fornecedor(salvo.id)
        if r.status == StatusRFQ.RASCUNHO and not r.aguardando_envio() and r.idioma != salvo.idioma
    ]
    if rascunhos:
        base.rfqs.salvar_varios(rascunhos)
    return salvo


def salvar_commodity(base: BaseDados, commodity: Commodity) -> Commodity:
    _nome_unico(base.commodities, commodity.nome, commodity.id, "uma commodity")
    return base.commodities.salvar(commodity)


def salvar_projeto(base: BaseDados, projeto: Projeto) -> Projeto:
    _nome_unico(base.projetos, projeto.nome, projeto.id, "um projeto")
    return base.projetos.salvar(projeto)


def salvar_condicao(base: BaseDados, condicao: Condicao) -> Condicao:
    """Grava a condição e cria os textos (vazios) que faltarem na aba Corpo do E-mail."""
    _nome_unico(base.condicoes, condicao.nome, condicao.id, "uma condição")
    if any(base.commodities.obter(i) is None for i in condicao.commodity_ids):
        raise ErroNegocio("Uma das commodities da condição não existe mais. Revise a coluna Commodity.")
    ids = list(dict.fromkeys(condicao.commodity_ids))
    if ids != condicao.commodity_ids:
        condicao = condicao.model_copy(update={"commodity_ids": ids})
    salva = base.condicoes.salvar(condicao)
    faltando = base.textos_faltando([salva])
    if faltando:
        base.modelos_email.salvar_varios(faltando)
    return salva


def salvar_feriado(base: BaseDados, feriado: Feriado) -> Feriado:
    for existente in base.feriados:
        if existente.id != feriado.id and existente.data == feriado.data:
            raise ErroNegocio(f"A data {feriado.data:%d/%m/%Y} já está cadastrada ({existente.descricao}).")
    return base.feriados.salvar(feriado)


def motivo_bloqueio_exclusao(base: BaseDados, registro) -> str | None:
    """Explica por que o registro não pode ser excluído (ou None se pode)."""
    if isinstance(registro, Fornecedor):
        total = len(base.rfqs_do_fornecedor(registro.id))
        if total:
            return (f"O fornecedor '{registro.nome}' tem {total} RFQ(s) e não pode ser excluído. Para tirá-lo das "
                    "listas de envio, desmarque 'Fornecedor ativo' em 'Detalhes do fornecedor…'.")
    elif isinstance(registro, Projeto):
        total = len(base.pacotes_do_projeto(registro.id))
        if total:
            return f"O projeto '{registro.nome}' tem {total} pacote(s) de cotação. Desmarque 'Ativo' em vez de excluir."
    elif isinstance(registro, Commodity):
        # a commodity não depende de fornecedor (sai deles ao excluir); só pacotes e condições a prendem
        pacotes = len(base.pacotes_da_commodity(registro.id))
        condicoes = len(base.condicoes_da_commodity(registro.id))
        if pacotes or condicoes:
            return (f"A commodity '{registro.nome}' está em uso ({pacotes} pacote(s), {condicoes} condição(ões)). "
                    "Retire-a dos pacotes e das condições antes de excluir.")
    return None


def colecao_de(base: BaseDados, registro) -> Colecao:
    mapa = {
        Fornecedor: base.fornecedores,
        Commodity: base.commodities,
        Projeto: base.projetos,
        Feriado: base.feriados,
        Condicao: base.condicoes,
    }
    return mapa[type(registro)]


def aviso_exclusao(base: BaseDados, registros: list) -> str:
    """O que mais muda ao excluir (ex.: fornecedores que perdem a commodity), para a confirmação."""
    commodities = {r.id for r in registros if isinstance(r, Commodity)}
    fornecedores = [f for f in base.fornecedores if commodities & set(f.commodity_ids)]
    if fornecedores:
        return f"A commodity também sai de {len(fornecedores)} fornecedor(es)."
    return ""


def excluir_registros(base: BaseDados, registros: list) -> int:
    if not registros:
        return 0
    for registro in registros:
        motivo = motivo_bloqueio_exclusao(base, registro)
        if motivo:
            raise ErroNegocio(motivo)
    ids = {r.id for r in registros}
    if isinstance(registros[0], Commodity):
        fornecedores = [
            f.model_copy(update={"commodity_ids": [i for i in f.commodity_ids if i not in ids]})
            for f in base.fornecedores if ids & set(f.commodity_ids)
        ]
        if fornecedores:
            base.fornecedores.salvar_varios(fornecedores)
    colecao_de(base, registros[0]).remover_varios(ids)
    if isinstance(registros[0], Condicao):
        base.modelos_email.remover_varios([m.id for m in base.modelos_email if m.condicao_id in ids])
    return len(registros)


def adicionar_feriados_nacionais(
    base: BaseDados, ano: int, incluir_carnaval: bool = True, incluir_corpus_christi: bool = True
) -> int:
    existentes = base.datas_feriados()
    novos = [
        Feriado(data=dia, descricao=nome)
        for dia, nome in feriados_nacionais_brasil(ano, incluir_carnaval, incluir_corpus_christi)
        if dia not in existentes
    ]
    if novos:
        base.feriados.salvar_varios(novos)
    return len(novos)
