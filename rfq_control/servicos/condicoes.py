"""Condições: textos adicionais do e-mail de RFQ conforme a commodity e as regiões.

Exemplos (criados na primeira abertura): commodity Molde → pedir Moldflow, frete e embalagem;
fornecedor do Brasil cotando um projeto na Argentina → cotação em USD com certificado de origem.
Uma condição vale quando todos os critérios preenchidos batem (critério vazio vale para qualquer valor).
"""

from __future__ import annotations

from ..armazenamento import BaseDados
from ..modelos import Condicao, Fornecedor, Idioma, Pacote, Projeto
from .formatos import normalizar_nome


def commodities_do_email(fornecedor: Fornecedor, pacote: Pacote | None) -> set[str]:
    """Mesma regra do Commodity Buyer em cópia: a commodity do pacote; sem ela, as do fornecedor."""
    if pacote is not None and pacote.commodity_id:
        return {pacote.commodity_id}
    return set(fornecedor.commodity_ids)


def condicao_vale(condicao: Condicao, fornecedor: Fornecedor, pacote: Pacote | None, projeto: Projeto | None) -> bool:
    if not condicao.ativo:
        return False
    if condicao.commodity_ids and not set(condicao.commodity_ids) & commodities_do_email(fornecedor, pacote):
        return False
    if condicao.regiao_fornecedor and normalizar_nome(condicao.regiao_fornecedor) != normalizar_nome(fornecedor.regiao):
        return False
    regiao_projeto = projeto.regiao if projeto else ""
    if condicao.regiao_projeto and normalizar_nome(condicao.regiao_projeto) != normalizar_nome(regiao_projeto):
        return False
    return True


def condicoes_aplicaveis(
    base: BaseDados, fornecedor: Fornecedor, pacote: Pacote | None, projeto: Projeto | None
) -> list[Condicao]:
    return sorted(
        (c for c in base.condicoes if condicao_vale(c, fornecedor, pacote, projeto)),
        key=lambda c: c.nome.casefold(),
    )


def texto_condicao(base: BaseDados, condicao: Condicao, idioma: Idioma) -> str:
    """Texto da condição no idioma do e-mail (vazio se ainda não foi escrito na aba Corpo do E-mail)."""
    modelo = base.textos_da_condicao(condicao.id).get(Idioma(idioma))
    return modelo.corpo if modelo else ""


def resumo_textos(base: BaseDados, condicao: Condicao) -> str:
    """Para a grade: o texto em português numa linha e os idiomas ainda sem texto."""
    textos = base.textos_da_condicao(condicao.id)
    faltando = [i.rotulo for i in Idioma if not (textos.get(i) and textos[i].corpo.strip())]
    principal = textos.get(Idioma.PT)
    resumo = " ".join(principal.corpo.split()) if principal and principal.corpo.strip() else ""
    if faltando:
        resumo += (" · " if resumo else "") + "sem texto em " + ", ".join(faltando)
    return resumo
