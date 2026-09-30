from datetime import date

import pytest

from rfq_control.modelos import Idioma, Pacote, StatusRFQ
from rfq_control.servicos import rfq as srv
from rfq_control.servicos.dias_uteis import (
    dias_uteis_entre,
    domingo_de_pascoa,
    feriados_nacionais_brasil,
    somar_dias_uteis,
)
from rfq_control.servicos.formatos import data_por_extenso, ler_data, ler_numero, numero_br


# ---------------------------------------------------------------- dias úteis
def test_somar_dias_uteis_igual_ao_workday():
    # 30/09/2026 é quarta-feira: +4 dias úteis = terça 06/10 (sem feriados)
    assert somar_dias_uteis(date(2026, 9, 30), 4) == date(2026, 10, 6)
    # com o feriado de 12/10 (segunda)
    assert somar_dias_uteis(date(2026, 10, 9), 1, {date(2026, 10, 12)}) == date(2026, 10, 13)
    assert somar_dias_uteis(date(2026, 10, 3), 0) == date(2026, 10, 3)


def test_dias_uteis_entre():
    assert dias_uteis_entre(date(2026, 9, 30), date(2026, 10, 6)) == 4
    assert dias_uteis_entre(date(2026, 10, 6), date(2026, 9, 30)) == -4
    assert dias_uteis_entre(date(2026, 10, 6), date(2026, 10, 6)) == 0


def test_pascoa_e_feriados():
    assert domingo_de_pascoa(2026) == date(2026, 4, 5)
    assert domingo_de_pascoa(2027) == date(2027, 3, 28)
    feriados = dict(feriados_nacionais_brasil(2026))
    assert feriados[date(2026, 4, 3)] == "Sexta-feira Santa"
    assert feriados[date(2026, 2, 17)] == "Carnaval (terça-feira)"
    assert feriados[date(2026, 6, 4)] == "Corpus Christi"
    assert date(2026, 11, 20) in feriados
    sem_opcionais = dict(feriados_nacionais_brasil(2026, incluir_carnaval=False, incluir_corpus_christi=False))
    assert date(2026, 2, 17) not in sem_opcionais and date(2026, 6, 4) not in sem_opcionais


# ---------------------------------------------------------------- formatos
@pytest.mark.parametrize(
    "texto, esperado",
    [("1.464,76", 1464.76), ("1464,76", 1464.76), ("1,464.76", 1464.76), ("154000", 154000),
     ("154.000", 154000), ("1.5", 1.5), ("R$ 10", 10), ("", None), ("abc", None), (2, 2.0)],
)
def test_ler_numero(texto, esperado):
    assert ler_numero(texto) == esperado


def test_formatos_data_e_numero():
    assert data_por_extenso(date(2026, 10, 6), Idioma.PT) == "terça-feira, 6 de outubro de 2026"
    assert data_por_extenso(date(2026, 10, 6), Idioma.EN) == "Tuesday, October 6, 2026"
    assert ler_data("06/10/2026") == date(2026, 10, 6)
    assert ler_data("2026-10-06") == date(2026, 10, 6)
    assert numero_br(154000) == "154.000"
    assert numero_br(1464.76) == "1.464,76"


# ---------------------------------------------------------------- pacotes e RFQs
def test_numeracao_sequencial_por_ano(base_populada, pacote_exemplo):
    _, rfqs = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1", "f2"])
    ano = date.today().year
    assert [r.numero for r in rfqs] == [f"RFQ{ano}001", f"RFQ{ano}002"]
    assert srv.proximo_numero(base_populada) == f"RFQ{ano}003"
    assert srv.proximo_numero(base_populada, ano=ano + 1) == f"RFQ{ano + 1}001"


def test_criar_pacote_gera_uma_rfq_por_fornecedor(base_populada, pacote_exemplo):
    pacote, rfqs = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1", "f2"])
    assert len(pacote.itens) == 2  # item vazio descartado
    assert pacote.titulo == "Projeto Alfa — 28/09/2026"
    assert {r.fornecedor_id for r in rfqs} == {"f1", "f2"}
    assert rfqs[1].idioma == Idioma.EN  # idioma padrão do fornecedor
    assert all(r.status == StatusRFQ.RASCUNHO for r in rfqs)
    assert base_populada.rfqs_do_pacote(pacote.id) == sorted(rfqs, key=lambda r: r.numero)


def test_regras_ao_criar_pacote(base_populada, pacote_exemplo):
    with pytest.raises(srv.ErroNegocio, match="pelo menos um fornecedor"):
        srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, [])
    with pytest.raises(srv.ErroNegocio, match="pelo menos um item"):
        srv.criar_pacote_com_rfqs(base_populada, Pacote(projeto_id="prj1"), ["f1"])
    with pytest.raises(srv.ErroNegocio, match="projeto válido"):
        srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo.model_copy(update={"projeto_id": "x"}), ["f1"])
    pacote, _ = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1"])
    with pytest.raises(srv.ErroNegocio, match="já têm RFQ"):
        srv.adicionar_fornecedores(base_populada, pacote.id, ["f1"])
    novas = srv.adicionar_fornecedores(base_populada, pacote.id, ["f2"])
    assert len(novas) == 1 and len(base_populada.rfqs_do_pacote(pacote.id)) == 2


def test_status_e_resposta(base_populada, pacote_exemplo):
    _, rfqs = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1", "f2"])
    hoje = date(2026, 9, 30)
    enviada = srv.registrar_envio(base_populada, rfqs[0], Idioma.PT, "enviada", hoje)
    assert enviada.status == StatusRFQ.ENVIADA
    assert enviada.data_envio == hoje
    assert enviada.prazo == date(2026, 10, 6)
    assert enviada.atrasada(date(2026, 10, 7)) and enviada.situacao(date(2026, 10, 7)) == "Atrasada"
    assert not enviada.atrasada(date(2026, 10, 6))

    [respondida] = srv.alterar_status(base_populada, [enviada.id], StatusRFQ.RESPONDIDA, hoje=date(2026, 10, 2))
    assert respondida.data_resposta == date(2026, 10, 2)
    assert "Enviada para Respondida" in respondida.historico[-1].descricao


def test_selecionar_vencedora(base_populada, pacote_exemplo):
    _, rfqs = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1", "f2"])
    ids = [r.id for r in rfqs]
    srv.alterar_status(base_populada, ids, StatusRFQ.RESPONDIDA)
    srv.selecionar_vencedora(base_populada, ids[1])
    assert base_populada.rfqs.obter(ids[1]).status == StatusRFQ.SELECIONADA
    assert base_populada.rfqs.obter(ids[0]).status == StatusRFQ.NAO_SELECIONADA


def test_excluir_pacote_somente_sem_envio(base_populada, pacote_exemplo):
    pacote, rfqs = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1"])
    srv.registrar_envio(base_populada, rfqs[0], Idioma.PT, "enviada")
    with pytest.raises(srv.ErroNegocio, match="já tem RFQs enviadas"):
        srv.excluir_pacote(base_populada, pacote.id)
    rascunho, _ = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo.model_copy(update={"id": "p2"}), ["f2"])
    srv.excluir_pacote(base_populada, rascunho.id)
    assert base_populada.pacotes.obter(rascunho.id) is None
    assert not base_populada.rfqs_do_pacote(rascunho.id)


def test_duplicar_pacote_e_anexos(base_populada, pacote_exemplo, tmp_path):
    pacote, _ = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1"])
    arquivo = tmp_path / "CDC peça A.pdf"
    arquivo.write_bytes(b"%PDF-1.4 teste")
    pacote = srv.anexar_arquivos(base_populada, pacote.id, [arquivo])
    assert pacote.anexos == ["CDC peça A.pdf"]
    copia = srv.duplicar_pacote(base_populada, pacote.id)
    assert copia.id != pacote.id and copia.anexos == pacote.anexos
    assert (base_populada.pasta_anexos(copia.id) / "CDC peça A.pdf").exists()
    assert not base_populada.rfqs_do_pacote(copia.id)
    pacote = srv.remover_anexo(base_populada, pacote.id, "CDC peça A.pdf")
    assert pacote.anexos == []


def test_indicadores(base_populada, pacote_exemplo):
    _, rfqs = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1", "f2", "f3"])
    base_populada.rfqs.salvar(rfqs[2].model_copy(update={"data_criacao": date(2026, 9, 15)}))
    srv.registrar_envio(base_populada, rfqs[0], Idioma.PT, "ok", date(2026, 9, 1))
    srv.registrar_envio(base_populada, rfqs[1], Idioma.EN, "ok", date(2026, 9, 28))
    srv.alterar_status(base_populada, [rfqs[1].id], StatusRFQ.RESPONDIDA, hoje=date(2026, 9, 30))

    ind = srv.calcular_indicadores(base_populada, hoje=date(2026, 9, 30))
    assert ind.total == 3
    assert ind.rascunhos == 1
    assert ind.em_aberto == 1 and ind.atrasadas == 1
    assert ind.respondidas == 1
    assert ind.taxa_resposta == 0.5
    assert ind.media_dias_resposta == 2
    assert ind.por_mes[-1] == ("set/26", 3)
    assert ind.por_situacao == {"Atrasada": 1, "Respondida": 1, "Rascunho": 1}
    assert [p.numero for p in ind.pendencias] == [rfqs[0].numero]
