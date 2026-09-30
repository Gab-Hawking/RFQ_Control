from datetime import date

import pytest

from rfq_control.modelos import Feriado, Fornecedor, Projeto
from rfq_control.servicos import cadastros
from rfq_control.servicos import rfq as srv


def test_nome_unico_ignora_maiusculas_e_espacos(base_populada):
    with pytest.raises(srv.ErroNegocio, match="Já existe um fornecedor"):
        cadastros.salvar_fornecedor(base_populada, Fornecedor(nome="  fornecedor   um "))
    with pytest.raises(srv.ErroNegocio, match="Já existe um projeto"):
        cadastros.salvar_projeto(base_populada, Projeto(nome="PROJETO ALFA"))
    # editar o próprio registro é permitido
    existente = base_populada.fornecedores.obter("f1")
    cadastros.salvar_fornecedor(base_populada, existente.model_copy(update={"categoria": "Ferramentaria"}))
    assert base_populada.fornecedores.obter("f1").categoria == "Ferramentaria"


def test_exclusao_bloqueada_quando_em_uso(base_populada, pacote_exemplo):
    srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1"])
    with pytest.raises(srv.ErroNegocio, match="tem 1 RFQ"):
        cadastros.excluir_registros(base_populada, [base_populada.fornecedores.obter("f1")])
    with pytest.raises(srv.ErroNegocio, match="pacote"):
        cadastros.excluir_registros(base_populada, [base_populada.projetos.obter("prj1")])
    assert cadastros.excluir_registros(base_populada, [base_populada.fornecedores.obter("f3")]) == 1
    assert base_populada.fornecedores.obter("f3") is None


def test_feriados(base):
    total_antes = len(base.feriados)
    novos = cadastros.adicionar_feriados_nacionais(base, 2030)
    assert novos == 13 and len(base.feriados) == total_antes + 13
    assert cadastros.adicionar_feriados_nacionais(base, 2030) == 0
    with pytest.raises(srv.ErroNegocio, match="já está cadastrada"):
        cadastros.salvar_feriado(base, Feriado(data=date(2030, 12, 25)))
