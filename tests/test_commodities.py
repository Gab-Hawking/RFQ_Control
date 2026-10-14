"""Commodities, Commodity Buyer em cópia e migração da antiga 'Categoria' (dados fictícios)."""

import json
from datetime import date

import pytest

from rfq_control.armazenamento import BaseDados
from rfq_control.modelos import Commodity, Fornecedor, TipoModelo
from rfq_control.servicos import abas, cadastros
from rfq_control.servicos import rfq as srv
from rfq_control.servicos.email_rfq import montar_email

HOJE = date(2026, 9, 30)


@pytest.fixture
def commodities(base_populada):
    base_populada.commodities.salvar_varios([
        Commodity(id="c1", nome="Ferramentaria", comprador="Bia Buyer", email="bia@op.com"),
        Commodity(id="c2", nome="Dispositivos", comprador="Caio Buyer", email="caio@op.com"),
    ])
    fornecedor = base_populada.fornecedores.obter("f1")
    cadastros.salvar_fornecedor(base_populada, fornecedor.model_copy(update={"commodity_ids": ["c1", "c2"]}))
    return base_populada


def test_cc_do_commodity_buyer_do_pacote(commodities, pacote_exemplo):
    pacote = pacote_exemplo.model_copy(update={"commodity_id": "c2"})
    _, [rfq] = srv.criar_pacote_com_rfqs(commodities, pacote, ["f1"])
    email = montar_email(commodities, rfq, hoje=HOJE)
    # Supplier Cc + buyer da commodity do pacote (só a do pacote, não todas do fornecedor)
    assert email.copia == ["copia@um.com", "caio@op.com"]


def test_pacote_sem_commodity_copia_os_buyers_do_fornecedor(commodities, pacote_exemplo):
    _, [rfq] = srv.criar_pacote_com_rfqs(commodities, pacote_exemplo, ["f1"])
    assert montar_email(commodities, rfq, hoje=HOJE).copia == ["copia@um.com", "bia@op.com", "caio@op.com"]


def test_grade_de_fornecedores_mostra_commodities_e_buyers(commodities):
    linha = abas.ABA_FORNECEDORES.para_linha(commodities, commodities.fornecedores.obter("f1"))
    assert linha["commodities"] == "Ferramentaria; Dispositivos"
    assert linha["email_buyer"] == "bia@op.com; caio@op.com"
    assert linha["email_cc"] == "copia@um.com"
    assert set(linha) == {"nome", "email_para", "email_cc", "commodities", "email_buyer", "idioma"}


def test_grade_aceita_varias_commodities_e_recusa_desconhecida(commodities):
    definicao = abas.ABA_FORNECEDORES
    fornecedor = commodities.fornecedores.obter("f2")
    salvo = definicao.gravar_linha(commodities, {"commodities": "dispositivos;  FERRAMENTARIA"}, fornecedor)
    assert salvo.commodity_ids == ["c2", "c1"]
    with pytest.raises(srv.ErroNegocio, match="Commodity não cadastrada: Pintura"):
        definicao.gravar_linha(commodities, {"commodities": "Ferramentaria; Pintura"}, fornecedor)
    # a coluna calculada (e-mail do buyer) nunca chega à conversão nem muda a commodity
    recebidas = []
    original = definicao.de_linha
    try:
        definicao.de_linha = lambda base, linha, existente: recebidas.append(dict(linha)) or original(base, linha, existente)
        salvo = definicao.gravar_linha(commodities, {"email_buyer": "x@y.com", "idioma": "Inglês"}, salvo)
    finally:
        definicao.de_linha = original
    assert recebidas == [{"idioma": "Inglês"}]
    assert salvo.commodity_ids == ["c2", "c1"]
    assert commodities.commodities.obter("c1").email == "bia@op.com"
    assert commodities.commodities.obter("c2").email == "caio@op.com"


def test_aba_commodities(commodities):
    definicao = abas.ABA_COMMODITIES
    nova = definicao.gravar_linha(commodities, {"nome": "Pintura", "comprador": "Dani", "email": "DANI@OP.COM"}, None)
    assert nova.email == "dani@op.com"
    assert definicao.para_linha(commodities, commodities.commodities.obter("c1"))["fornecedores"] == "Fornecedor Um"
    with pytest.raises(srv.ErroNegocio, match="e-mail inválido"):
        definicao.gravar_linha(commodities, {"email": "dani(arroba)op"}, nova)
    with pytest.raises(srv.ErroNegocio, match="Já existe uma commodity"):
        definicao.gravar_linha(commodities, {"nome": "pintura"}, None)


def test_commodity_em_uso_nao_pode_ser_excluida(commodities):
    with pytest.raises(srv.ErroNegocio, match="em uso"):
        cadastros.excluir_registros(commodities, [commodities.commodities.obter("c1")])
    livre = cadastros.salvar_commodity(commodities, Commodity(nome="Sem uso"))
    assert cadastros.excluir_registros(commodities, [livre]) == 1


def test_categoria_antiga_vira_commodity(base, pasta_dados):
    # base da versão 0.2: fornecedor com 'categoria' em texto
    base.fornecedores.salvar(Fornecedor(id="a", nome="Antigo", categoria="Ferramentaria, Moldes"))
    base.fornecedores.salvar(Fornecedor(id="b", nome="Outro", categoria="ferramentaria"))
    reaberta = BaseDados.abrir(pasta_dados)
    assert sorted(c.nome for c in reaberta.commodities) == ["Ferramentaria", "Moldes"]
    assert reaberta.nomes_commodities(reaberta.fornecedores.obter("a").commodity_ids) == "Ferramentaria, Moldes"
    assert reaberta.nomes_commodities(reaberta.fornecedores.obter("b").commodity_ids) == "Ferramentaria"
    assert all(not f.categoria for f in reaberta.fornecedores)
    assert (pasta_dados / "commodities.json").exists()


def test_feriados_do_ano_novo_sao_gerados(base):
    for feriado in [f for f in base.feriados if f.data.year == 2031]:
        base.feriados.remover(feriado.id)
    base._completar_feriados(hoje=date(2031, 1, 2))
    datas = base.datas_feriados()
    assert date(2031, 12, 25) in datas and date(2032, 1, 1) in datas
    total = len(base.feriados)
    base._completar_feriados(hoje=date(2031, 6, 1))  # o ano já tem feriados: nada muda
    assert len(base.feriados) == total


def test_modelo_de_cobranca_antigo_e_atualizado_e_o_editado_nao(base, pasta_dados):
    from rfq_control.padroes import CORPOS_PADRAO_ANTIGOS

    cobrancas = {m.idioma.value: m for m in base.modelos_email if m.tipo == TipoModelo.COBRANCA}
    base.modelos_email.salvar(cobrancas["PT"].model_copy(
        update={"corpo": CORPOS_PADRAO_ANTIGOS[(TipoModelo.COBRANCA, cobrancas["PT"].idioma)]}))
    base.modelos_email.salvar(cobrancas["EN"].model_copy(update={"corpo": "Texto meu {{tabela_itens}}"}))
    reaberta = BaseDados.abrir(pasta_dados)
    assert "{{tabela_itens}}" not in reaberta.modelos_email.obter(cobrancas["PT"].id).corpo
    assert reaberta.modelos_email.obter(cobrancas["EN"].id).corpo == "Texto meu {{tabela_itens}}"


def test_arquivo_de_fornecedores_antigo_continua_valido(base, pasta_dados):
    conteudo = {"registros": [{"id": "x", "nome": "Velho", "categoria": "", "ativo": True, "observacoes": "",
                               "contatos": [{"nome": "Ana", "email": "ana@velho.com", "copia": False}]}]}
    (pasta_dados / "fornecedores.json").write_text(json.dumps(conteudo), encoding="utf-8")
    assert BaseDados.abrir(pasta_dados).fornecedores.obter("x").commodity_ids == []


# ---------------------------------------------------------------- correções da revisão


def test_importacao_com_virgula_usa_as_commodities_existentes(commodities, tmp_path):
    caminho = tmp_path / "f.csv"
    caminho.write_text("Fornecedor;E-mail (Para);Commodity\nAcme;a@acme.com;Ferramentaria, Dispositivos\n",
                       encoding="utf-8")
    resultado = abas.importar_arquivo(commodities, abas.ABA_FORNECEDORES, caminho)
    assert resultado.criados == 1 and resultado.opcoes_criadas == []
    acme = next(f for f in commodities.fornecedores if f.nome == "Acme")
    assert acme.commodity_ids == ["c1", "c2"]


def test_duas_colunas_de_commodity_no_arquivo(commodities, tmp_path):
    caminho = tmp_path / "f.csv"
    caminho.write_text("Fornecedor;E-mail (Para);Commodity;Categoria\nBeta;b@beta.com;Ferramentaria;Pintura\n",
                       encoding="utf-8")
    resultado = abas.importar_arquivo(commodities, abas.ABA_FORNECEDORES, caminho)
    assert resultado.erros == [] and resultado.opcoes_criadas == ["Pintura"]
    beta = next(f for f in commodities.fornecedores if f.nome == "Beta")
    assert commodities.nomes_commodities(beta.commodity_ids) == "Ferramentaria, Pintura"


def test_nome_de_commodity_nao_aceita_ponto_e_virgula(base):
    with pytest.raises(srv.ErroNegocio, match="não pode ter ';'"):
        abas.ABA_COMMODITIES.gravar_linha(base, {"nome": "Usinagem; Solda"}, None)
    with pytest.raises(ValueError):
        Commodity(nome="Usinagem\nSolda")


def test_migracao_nao_separa_barra_e_faz_backup(base, pasta_dados):
    base.fornecedores.salvar(Fornecedor(id="a", nome="Antigo", categoria="Usinagem/Solda"))
    reaberta = BaseDados.abrir(pasta_dados)
    assert [c.nome for c in reaberta.commodities] == ["Usinagem/Solda"]
    assert any(p.name.startswith("antes_migracao_commodities") for p in reaberta.pasta_backup.iterdir())


def test_buyers_por_pacote_e_commodity_sem_repetir(commodities, pacote_exemplo):
    from rfq_control.servicos.email_rfq import emails_commodity_buyer, montar_email_agradecimento

    com_c2 = pacote_exemplo.model_copy(update={"id": "pa", "commodity_id": "c2"})
    sem = pacote_exemplo.model_copy(update={"id": "pb"})
    outro_c2 = pacote_exemplo.model_copy(update={"id": "pc", "commodity_id": "c2"})
    fornecedor = commodities.fornecedores.obter("f1")  # commodities c1 e c2
    # pacote sem commodity leva os buyers do fornecedor; o com commodity, só o dela
    assert emails_commodity_buyer(commodities, fornecedor, [com_c2, sem]) == ["caio@op.com", "bia@op.com"]
    pacotes = []
    for pacote in (com_c2, outro_c2):
        p, [rfq] = srv.criar_pacote_com_rfqs(commodities, pacote, ["f1"])
        pacotes.append(srv.registrar_envio(commodities, rfq, rfq.idioma, "enviada"))
    email = montar_email_agradecimento(commodities, fornecedor, pacotes, fornecedor.idioma, "texto")
    assert commodities.nomes_commodities(["c2", "c2"]) == "Dispositivos"
    assert email.copia.count("caio@op.com") == 1


def test_feriados_nacionais_mesmo_com_feriado_local_no_ano(base):
    from rfq_control.modelos import Feriado

    base.feriados.salvar(Feriado(data=date(2032, 1, 25), descricao="Aniversário da cidade"))
    base._completar_feriados(hoje=date(2032, 1, 3))
    datas = base.datas_feriados()
    assert date(2032, 4, 21) in datas and date(2032, 12, 25) in datas and date(2032, 1, 25) in datas
    # um nacional apagado de propósito não volta
    natal = next(f for f in base.feriados if f.data == date(2032, 12, 25))
    base.feriados.remover(natal.id)
    base._completar_feriados(hoje=date(2032, 1, 3))
    assert date(2032, 12, 25) not in base.datas_feriados()
