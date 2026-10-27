"""Volumes por ano (EAU Y1…Yn pelo lifetime do projeto) — dados fictícios."""

from datetime import date

import pytest
from openpyxl import load_workbook

from rfq_control.modelos import CotacaoItem, Idioma, Item, Pacote, Projeto
from rfq_control.servicos import rfq as srv
from rfq_control.servicos.cotacao import comparar
from rfq_control.servicos.email_rfq import montar_email
from rfq_control.servicos.exportacao import exportar_rfqs


@pytest.fixture
def projeto(base_populada):
    """Projeto Beta (lifetime 6) com SOP em 2027."""
    beta = base_populada.projetos.obter("prj2")
    return base_populada.projetos.salvar(beta.model_copy(update={"sop": date(2027, 3, 1), "lifetime_anos": 3}))


def _pacote(base, volumes_por_ano=True, **item):
    pacote = Pacote(projeto_id="prj2", volumes_por_ano=volumes_por_ano, itens=[
        Item(ref_op="PECA A", unidade="PC", quantidade=1, **item)])
    return srv.criar_pacote_com_rfqs(base, pacote, ["f1", "f2"])


def test_rotulos_dos_anos():
    assert srv.rotulos_anos(Projeto(nome="P", sop=date(2027, 1, 1), lifetime_anos=3)) == ["2027", "2028", "2029"]
    assert srv.rotulos_anos(Projeto(nome="P", lifetime_anos=2)) == ["Y1", "Y2"]
    assert srv.rotulos_anos(Projeto(nome="P", sop=date(2027, 1, 1))) == []
    assert srv.rotulos_anos(None) == []


def test_pacote_com_volumes_por_ano(base_populada, projeto):
    pacote, _ = _pacote(base_populada, volumes=[1000, 2000, 3000, 4000, None])
    assert pacote.itens[0].volumes == [1000, 2000, 3000]  # só os anos do lifetime
    assert pacote.itens[0].volume_medio() == 2000 and pacote.itens[0].peso() == 2000
    desligado = srv.salvar_pacote(base_populada, pacote.model_copy(update={"volumes_por_ano": False}))
    assert desligado.itens[0].volumes == []  # sem a opção, os volumes por ano saem
    with pytest.raises(ValueError):
        Item(volumes=[-1])


def test_volumes_por_ano_exigem_lifetime(base_populada, projeto):
    base_populada.projetos.salvar(projeto.model_copy(update={"lifetime_anos": None}))
    with pytest.raises(srv.ErroNegocio, match="Lifetime"):
        _pacote(base_populada, volumes=[1000])


def test_email_com_uma_coluna_por_ano(base_populada, projeto):
    _, (um, dois) = _pacote(base_populada, volume_anual=999, volumes=[1000, None, 3000.5])
    email = montar_email(base_populada, um, hoje=date(2026, 9, 30))
    assert "EAU 2027" in email.html and "EAU 2028" in email.html and "EAU 2029" in email.html
    assert "Volume anual" not in email.html and "999" not in email.html
    assert "1.000" in email.html and "3.000,50" in email.html
    assert "EAU 2027 | EAU 2028 | EAU 2029" in email.texto
    assert "3,000.50" in montar_email(base_populada, dois, hoje=date(2026, 9, 30)).html  # inglês
    assert dois.idioma == Idioma.EN


def test_pacote_sem_a_opcao_mantem_o_volume_anual(base_populada, projeto):
    _, (um, _) = _pacote(base_populada, volumes_por_ano=False, volume_anual=154000)
    email = montar_email(base_populada, um, hoje=date(2026, 9, 30))
    assert "Volume anual" in email.html and "EAU" not in email.html


def test_comparativo_e_exportacao_usam_a_media(base_populada, projeto, tmp_path):
    pacote, rfqs = _pacote(base_populada, volumes=[1000, 2000, 3000])
    item = pacote.itens[0]
    for rfq, preco in zip(rfqs, (10, 12)):
        editada = rfq.model_copy(update={"cotacao": [CotacaoItem(item_id=item.id, preco=preco)]})
        srv.salvar_rfq(base_populada, editada, carregada=rfq)
    totais = {p.rfq.fornecedor_id: p.total_pecas for p in comparar(base_populada, pacote.id).propostas}
    assert totais == {"f1": 10 * 2000, "f2": 12 * 2000}
    livro = load_workbook(exportar_rfqs(base_populada, tmp_path / "rfqs.xlsx"))
    linha = next(livro["Itens"].iter_rows(min_row=2, values_only=True))
    assert linha[10] == 2000 and linha[-1] == "2027: 1000; 2028: 2000; 2029: 3000"
