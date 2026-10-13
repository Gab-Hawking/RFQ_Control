"""Regras dos cadastros (nomes únicos e exclusão protegida)."""

from __future__ import annotations

from ..armazenamento import BaseDados, Colecao
from ..modelos import Commodity, Feriado, Fornecedor, Projeto, Solicitante, StatusRFQ
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
    # RFQs ainda não enviadas acompanham o idioma do fornecedor
    rascunhos = [
        r.model_copy(update={"idioma": salvo.idioma})
        for r in base.rfqs_do_fornecedor(salvo.id)
        if r.status == StatusRFQ.RASCUNHO and r.idioma != salvo.idioma
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


def salvar_solicitante(base: BaseDados, solicitante: Solicitante) -> Solicitante:
    _nome_unico(base.solicitantes, solicitante.nome, solicitante.id, "um solicitante")
    return base.solicitantes.salvar(solicitante)


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
    elif isinstance(registro, Solicitante):
        total = len(base.pacotes_do_solicitante(registro.id))
        if total:
            return f"O solicitante '{registro.nome}' está em {total} pacote(s). Desmarque 'Ativo' em vez de excluir."
    elif isinstance(registro, Commodity):
        fornecedores = len(base.fornecedores_da_commodity(registro.id))
        pacotes = len(base.pacotes_da_commodity(registro.id))
        if fornecedores or pacotes:
            return (f"A commodity '{registro.nome}' está em uso ({fornecedores} fornecedor(es), {pacotes} pacote(s)). "
                    "Retire-a dos fornecedores e pacotes antes de excluir.")
    return None


def colecao_de(base: BaseDados, registro) -> Colecao:
    mapa = {
        Fornecedor: base.fornecedores,
        Commodity: base.commodities,
        Projeto: base.projetos,
        Solicitante: base.solicitantes,
        Feriado: base.feriados,
    }
    return mapa[type(registro)]


def excluir_registros(base: BaseDados, registros: list) -> int:
    if not registros:
        return 0
    for registro in registros:
        motivo = motivo_bloqueio_exclusao(base, registro)
        if motivo:
            raise ErroNegocio(motivo)
    colecao_de(base, registros[0]).remover_varios([r.id for r in registros])
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
