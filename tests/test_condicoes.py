"""Condições (texto a mais no e-mail por commodity/região), região e sem solicitante — dados fictícios."""

import json
from datetime import date

import pytest

from rfq_control.armazenamento import BaseDados
from rfq_control.modelos import Commodity, Condicao, Idioma, Projeto, TipoModelo, normalizar_regiao
from rfq_control.padroes import CONDICOES_PADRAO
from rfq_control.servicos import abas, cadastros
from rfq_control.servicos import rfq as srv
from rfq_control.servicos.email_rfq import montar_email

HOJE = date(2026, 9, 30)
TEXTO_MOLDES = CONDICOES_PADRAO[0].textos
TEXTO_ARGENTINA = CONDICOES_PADRAO[1].textos


def _condicao(base, nome: str) -> Condicao:
    return next(c for c in base.condicoes if c.nome == nome)


@pytest.fixture
def molde(base_populada):
    """A condição padrão 'Moldes' fica ligada à commodity 'Molde' (criada na primeira abertura)."""
    return next(c for c in base_populada.commodities if c.nome == "Molde")


def _rfq(base, pacote, fornecedor_id: str, **alteracoes):
    _, [rfq] = srv.criar_pacote_com_rfqs(base, pacote.model_copy(update=alteracoes), [fornecedor_id])
    return rfq


# ---------------------------------------------------------------- condições padrão


def test_base_nova_tem_as_condicoes_padrao_com_os_tres_idiomas(base):
    moldes = _condicao(base, "Moldes")
    assert base.nomes_commodities(moldes.commodity_ids) == "Molde"
    argentina = _condicao(base, "Brasil → Argentina")
    assert (argentina.regiao_fornecedor, argentina.regiao_projeto, argentina.commodity_ids) == ("Brasil", "Argentina", [])
    textos = base.textos_da_condicao(moldes.id)
    assert {i: m.corpo for i, m in textos.items()} == TEXTO_MOLDES
    assert TEXTO_MOLDES[Idioma.PT] == "Favor enviar a cotação incluindo:\n\t- Moldflow;\n\t- Frete para TO;\n\t- Embalagem para TO"
    assert all(m.assunto == "" for m in textos.values())


def test_base_antiga_liga_a_condicao_a_commodity_de_moldes_que_ja_existe(base, pasta_dados):
    # base da versão 0.3: sem condicoes.json e com a commodity de moldes cadastrada com outro nome
    for condicao in base.condicoes:
        cadastros.excluir_registros(base, [condicao])
    for commodity in list(base.commodities):
        base.commodities.remover(commodity.id)
    injecao = base.commodities.salvar(Commodity(nome="Moldes de injeção", email="moldes@op.com"))
    sopro = base.commodities.salvar(Commodity(nome="Blow molds"))  # não começa com "mold"
    molds = base.commodities.salvar(Commodity(nome="Molds"))
    (pasta_dados / "condicoes.json").unlink()

    reaberta = BaseDados.abrir(pasta_dados)
    assert _condicao(reaberta, "Moldes").commodity_ids == [injecao.id, molds.id]
    assert {c.nome for c in reaberta.commodities} == {"Moldes de injeção", "Molds", sopro.nome}  # nada criado
    # reabrir de novo não recria condições apagadas pelo usuário
    cadastros.excluir_registros(reaberta, [_condicao(reaberta, "Moldes")])
    assert [c.nome for c in BaseDados.abrir(pasta_dados).condicoes] == ["Brasil → Argentina"]


# ---------------------------------------------------------------- e-mail


def test_commodity_molde_acrescenta_o_texto_no_fim_do_email(base_populada, pacote_exemplo, molde):
    rfq = _rfq(base_populada, pacote_exemplo, "f1", commodity_id=molde.id)
    email = montar_email(base_populada, rfq, hoje=HOJE)
    # o texto padrão continua igual e o da condição entra depois da nota de CBD/lead time
    assert email.texto.index("NOTA: Favor enviar") < email.texto.index("Favor enviar a cotação incluindo:")
    assert email.texto.endswith(TEXTO_MOLDES[Idioma.PT])
    assert "&nbsp;&nbsp;&nbsp;&nbsp;- Moldflow;<br>" in email.html  # o recuo do tab aparece no HTML
    assert "{{" not in email.html


def test_outra_commodity_mantem_o_email_padrao(base_populada, pacote_exemplo):
    outra = cadastros.salvar_commodity(base_populada, Commodity(nome="Usinagem"))
    rfq = _rfq(base_populada, pacote_exemplo, "f1", commodity_id=outra.id)
    email = montar_email(base_populada, rfq, hoje=HOJE)
    assert "Moldflow" not in email.html and "USD" not in email.html
    assert email.texto.rstrip().endswith("contemplando o CBD e lead time.")


def test_texto_da_condicao_no_idioma_do_fornecedor(base_populada, pacote_exemplo, molde):
    rfq = _rfq(base_populada, pacote_exemplo, "f2", commodity_id=molde.id)  # Supplier Two: inglês
    email = montar_email(base_populada, rfq, hoje=HOJE)
    assert email.texto.endswith(TEXTO_MOLDES[Idioma.EN])
    assert "Favor enviar a cotação" not in email.texto


def test_pacote_sem_commodity_usa_as_commodities_do_fornecedor(base_populada, pacote_exemplo, molde):
    fornecedor = base_populada.fornecedores.obter("f1")
    cadastros.salvar_fornecedor(base_populada, fornecedor.model_copy(update={"commodity_ids": [molde.id]}))
    rfq = _rfq(base_populada, pacote_exemplo, "f1")
    assert "Moldflow" in montar_email(base_populada, rfq, hoje=HOJE).texto


@pytest.mark.parametrize(
    ("regiao_fornecedor", "regiao_projeto", "esperado"),
    [("BR", "Argentina", True), ("Brasil", "Brasil", False), ("Argentina", "AR", False), ("", "Argentina", False)],
)
def test_fornecedor_do_brasil_em_projeto_na_argentina(
    base_populada, pacote_exemplo, regiao_fornecedor, regiao_projeto, esperado
):
    fornecedor = base_populada.fornecedores.obter("f1")
    base_populada.fornecedores.salvar(fornecedor.model_copy(update={"regiao": normalizar_regiao(regiao_fornecedor)}))
    projeto = base_populada.projetos.obter("prj1")
    cadastros.salvar_projeto(base_populada, Projeto.model_validate({**projeto.model_dump(), "regiao": regiao_projeto}))
    email = montar_email(base_populada, _rfq(base_populada, pacote_exemplo, "f1"), hoje=HOJE)
    assert (TEXTO_ARGENTINA[Idioma.PT] in email.texto) is esperado


def test_varias_condicoes_e_a_variavel_no_meio_do_texto(base_populada, pacote_exemplo, molde):
    base_populada.fornecedores.salvar(base_populada.fornecedores.obter("f1").model_copy(update={"regiao": "Brasil"}))
    base_populada.projetos.salvar(base_populada.projetos.obter("prj1").model_copy(update={"regiao": "Argentina"}))
    modelo = next(m for m in base_populada.modelos_email if m.tipo == TipoModelo.RFQ and m.idioma == Idioma.PT)
    base_populada.modelos_email.salvar(modelo.model_copy(update={"corpo": "Início\n\n{{condicoes}}\n\nFim"}))
    email = montar_email(base_populada, _rfq(base_populada, pacote_exemplo, "f1", commodity_id=molde.id), hoje=HOJE)
    # as duas valem (ordem alfabética do nome da condição) e entram onde está {{condicoes}}
    assert email.texto == "\n\n".join(["Início", TEXTO_ARGENTINA[Idioma.PT], TEXTO_MOLDES[Idioma.PT], "Fim"])


def test_condicao_inativa_ou_sem_texto_nao_entra(base_populada, pacote_exemplo, molde):
    moldes = _condicao(base_populada, "Moldes")
    rfq = _rfq(base_populada, pacote_exemplo, "f1", commodity_id=molde.id)
    cadastros.salvar_condicao(base_populada, moldes.model_copy(update={"ativo": False}))
    assert "Moldflow" not in montar_email(base_populada, rfq, hoje=HOJE).texto
    cadastros.salvar_condicao(base_populada, moldes.model_copy(update={"ativo": True}))
    texto_pt = base_populada.textos_da_condicao(moldes.id)[Idioma.PT]
    base_populada.modelos_email.salvar(texto_pt.model_copy(update={"corpo": ""}))  # texto ainda não escrito
    email = montar_email(base_populada, rfq, hoje=HOJE)
    assert "Moldflow" not in email.texto and email.texto.rstrip().endswith("lead time.")


def test_cobranca_nao_repete_o_texto_da_condicao(base_populada, pacote_exemplo, molde):
    rfq = _rfq(base_populada, pacote_exemplo, "f1", commodity_id=molde.id)
    srv.registrar_envio(base_populada, rfq, Idioma.PT, "enviada", date(2026, 9, 1))
    cobranca = montar_email(base_populada, base_populada.rfqs.obter(rfq.id), tipo=TipoModelo.COBRANCA, hoje=HOJE)
    assert "Moldflow" not in cobranca.texto


# ---------------------------------------------------------------- aba Condições


def test_aba_condicoes_grava_cria_textos_e_valida(base_populada):
    definicao = abas.ABA_CONDICOES
    with pytest.raises(srv.ErroNegocio, match="ao menos um critério"):
        definicao.gravar_linha(base_populada, {**definicao.linha_vazia(), "nome": "Sem critério"}, None)
    criadas: list[str] = []
    linha = {**definicao.linha_vazia(), "nome": "Chile", "commodities": "Fundição", "regiao_projeto": "cl"}
    chile = definicao.gravar_linha(base_populada, linha, None, criadas)
    assert criadas == ["Fundição"] and chile.regiao_projeto == "Chile" and chile.ativo
    assert set(base_populada.textos_da_condicao(chile.id)) == set(Idioma)  # um texto (vazio) por idioma
    assert "sem texto em Português, Espanhol, Inglês" in definicao.para_linha(base_populada, chile)["texto"]
    with pytest.raises(srv.ErroNegocio, match="Já existe uma condição"):
        definicao.gravar_linha(base_populada, {**linha, "nome": "CHILE"}, None)

    # commodity usada em condição não pode ser excluída; a condição sai com os seus textos
    fundicao = next(c for c in base_populada.commodities if c.nome == "Fundição")
    with pytest.raises(srv.ErroNegocio, match="1 condição"):
        cadastros.excluir_registros(base_populada, [fundicao])
    cadastros.excluir_registros(base_populada, [chile])
    assert base_populada.textos_da_condicao(chile.id) == {}
    assert cadastros.excluir_registros(base_populada, [fundicao]) == 1


def test_linha_da_aba_condicoes_mostra_o_texto_em_portugues(base_populada):
    linha = abas.ABA_CONDICOES.para_linha(base_populada, _condicao(base_populada, "Moldes"))
    assert linha["commodities"] == "Molde" and linha["ativo"] == "Sim"
    assert linha["texto"] == "Favor enviar a cotação incluindo: - Moldflow; - Frete para TO; - Embalagem para TO"


def test_texto_de_condicao_pode_ficar_vazio_e_dispensa_assunto(base_populada):
    texto = next(m for m in base_populada.modelos_email if m.tipo == TipoModelo.CONDICAO)
    salvo = base_populada.modelos_email.salvar(texto.model_copy(update={"corpo": ""}))
    assert salvo.corpo == "" and salvo.assunto == ""


# ---------------------------------------------------------------- região


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("BR", "Brasil"), (" brazil ", "Brasil"), ("ar", "Argentina"), ("México", "México"), ("mexico", "México"),
     ("EUA", "Estados Unidos"), ("Europa  Oriental", "Europa Oriental"), ("", "")],
)
def test_normalizar_regiao(texto, esperado):
    assert normalizar_regiao(texto) == esperado


def test_regiao_na_aba_fornecedores_e_projetos(base_populada):
    fornecedor = abas.ABA_FORNECEDORES.gravar_linha(
        base_populada, {"regiao": "argentina"}, base_populada.fornecedores.obter("f1"))
    assert fornecedor.regiao == "Argentina" and fornecedor.idioma == Idioma.PT  # região não muda o idioma
    projeto = abas.ABA_PROJETOS.gravar_linha(base_populada, {"regiao": "BR"}, base_populada.projetos.obter("prj1"))
    assert projeto.regiao == "Brasil"
    assert abas.ABA_PROJETOS.para_linha(base_populada, projeto)["regiao"] == "Brasil"
    assert "Argentina" in abas.regioes_sugeridas(base_populada)


# ---------------------------------------------------------------- modelos de importação


def test_modelos_tem_as_colunas_novas_e_nenhum_solicitante():
    titulos = {d.chave: [c.titulo for c in d.colunas_modelo] for d in abas.ABAS_CADASTRO}
    assert "E-mail Commodity Buyer (Cc)" in titulos["fornecedores"] and "Região" in titulos["fornecedores"]
    assert "Região" in titulos["projetos"]
    assert titulos["commodities"] == ["Commodity", "Commodity Buyer", "E-mail do Commodity Buyer"]
    assert titulos["condicoes"] == ["Condição", "Commodity", "Região do fornecedor", "Região do projeto", "Ativa"]
    assert "solicitantes" not in titulos
    assert "SOLICITANTE" not in abas.CABECALHO_CONTROLE


def test_importar_fornecedores_com_buyer_por_commodity(base, tmp_path):
    base.commodities.salvar(Commodity(nome="Pintura", email="pintura@op.com"))
    caminho = tmp_path / "fornecedores.csv"
    caminho.write_text(
        "Fornecedor;E-mail (Para);Commodity;E-mail Commodity Buyer (Cc);Região\n"
        'Acme;a@acme.com;"Usinagem; Solda";"usi@op.com; solda@op.com";BR\n'
        "Beta;b@beta.com;Pintura;outro@op.com;\n"
        'Gama;g@gama.com;"Fundição; Forjaria";fund@op.com;\n',
        encoding="utf-8",
    )
    resultado = abas.importar_arquivo(base, abas.ABA_FORNECEDORES, caminho)
    assert resultado.criados == 3 and resultado.erros == []
    emails = {c.nome: c.email for c in base.commodities}
    assert emails["Usinagem"] == "usi@op.com" and emails["Solda"] == "solda@op.com"
    assert emails["Pintura"] == "pintura@op.com"  # o buyer já cadastrado não muda
    assert emails["Fundição"] == "" and emails["Forjaria"] == ""  # um e-mail para duas commodities: ambíguo
    avisos = "\n".join(resultado.avisos)
    assert "Linha 3: a commodity Pintura já tem o buyer pintura@op.com" in avisos
    assert "Linha 4: informe um e-mail de Commodity Buyer por commodity" in avisos
    assert next(f for f in base.fornecedores if f.nome == "Acme").regiao == "Brasil"


# ---------------------------------------------------------------- sem solicitante


def test_dados_antigos_com_solicitante_continuam_abrindo(base, pasta_dados):
    pacote = {"id": "p1", "titulo": "Antigo", "projeto_id": "x", "solicitante_id": "sol1", "data": "2026-01-02",
              "itens": [{"ref_op": "A"}]}
    (pasta_dados / "pacotes.json").write_text(json.dumps({"registros": [pacote]}), encoding="utf-8")
    configuracoes = json.loads((pasta_dados / "configuracoes.json").read_text(encoding="utf-8"))
    configuracoes["copiar_solicitante"] = True
    (pasta_dados / "configuracoes.json").write_text(json.dumps(configuracoes), encoding="utf-8")
    reaberta = BaseDados.abrir(pasta_dados)
    assert reaberta.pacotes.obter("p1").titulo == "Antigo"
    assert not hasattr(reaberta, "solicitantes")
