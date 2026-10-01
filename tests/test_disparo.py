"""Envio de e-mails: escolher a RFQ (pacote) e os fornecedores."""

from datetime import date

import pytest

from rfq_control.modelos import Idioma, MetodoEmail, StatusRFQ, TipoModelo
from rfq_control.servicos import envio_email
from rfq_control.servicos import rfq as srv
from rfq_control.servicos.disparo import Destinatario, disparar, situacao_fornecedores

HOJE = date(2026, 9, 30)


@pytest.fixture
def pacote(base_populada, pacote_exemplo):
    pacote, _ = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1"])
    return pacote


@pytest.fixture
def outlook(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        envio_email, "abrir_no_outlook", lambda email, enviar=False: chamadas.append((email.para[0], enviar))
    )
    return chamadas


def test_lista_de_fornecedores_do_envio(base_populada, pacote):
    situacoes = situacao_fornecedores(base_populada, pacote.id)
    assert [s.fornecedor.id for s in situacoes] == ["f1", "f3", "f2"]  # quem já tem RFQ vem primeiro
    um = situacoes[0]
    assert um.rfq is not None and um.descricao.endswith("Rascunho") and um.tem_email
    assert not situacoes[1].tem_email
    assert situacoes[2].idioma == Idioma.EN and situacoes[2].descricao == "ainda não recebeu"


def test_disparo_cria_rfq_para_novos_e_pula_quem_nao_tem_email(base_populada, pacote, outlook):
    resultado = disparar(
        base_populada, pacote.id,
        [Destinatario("f1"), Destinatario("f2", Idioma.ES), Destinatario("f3")],
        hoje=HOJE,
    )
    ano = date.today().year
    assert [(i.fornecedor, i.ok) for i in resultado.itens] == [
        ("Fornecedor Um", True), ("Supplier Two", True), ("Sem Email", False),
    ]
    assert "sem e-mail" in resultado.falhas[0].mensagem
    assert resultado.rfqs_criadas == [f"RFQ{ano}002"]  # só o fornecedor novo ganhou RFQ
    assert resultado.enviados[1].idioma == Idioma.ES  # idioma escolhido no envio
    assert outlook == [("joao@um.com", False), ("anna@two.com", False)]

    rfqs = {r.fornecedor_id: r for r in base_populada.rfqs}
    assert set(rfqs) == {"f1", "f2"}  # nenhuma RFQ para quem não tem e-mail
    assert all(r.status == StatusRFQ.ENVIADA and r.prazo == date(2026, 10, 6) for r in rfqs.values())
    assert rfqs["f2"].idioma == Idioma.ES


def test_envio_automatico(base_populada, pacote, outlook):
    resultado = disparar(base_populada, pacote.id, [Destinatario("f1")], enviar=True, hoje=HOJE)
    assert resultado.enviados[0].mensagem == "enviado"
    assert outlook == [("joao@um.com", True)]


def test_envio_automatico_exige_outlook(base_populada, pacote):
    base_populada.salvar_configuracoes(
        base_populada.configuracoes.model_copy(update={"metodo_email": MetodoEmail.EML})
    )
    with pytest.raises(srv.ErroNegocio, match="usa o Outlook"):
        disparar(base_populada, pacote.id, [Destinatario("f1")], enviar=True)


def test_falha_de_um_fornecedor_nao_interrompe_os_outros(base_populada, pacote, monkeypatch):
    def outlook_instavel(email, enviar=False):
        if email.para[0] == "joao@um.com":
            raise envio_email.ErroOutlook("Outlook recusou a mensagem.")

    monkeypatch.setattr(envio_email, "abrir_no_outlook", outlook_instavel)
    resultado = disparar(base_populada, pacote.id, [Destinatario("f1"), Destinatario("f2")], enviar=True)
    assert [i.ok for i in resultado.itens] == [False, True]
    assert "recusou" in resultado.falhas[0].mensagem
    assert base_populada.rfqs_do_pacote(pacote.id)[0].status == StatusRFQ.RASCUNHO


def test_cobranca_so_para_quem_tem_rfq(base_populada, pacote, outlook):
    disparar(base_populada, pacote.id, [Destinatario("f1")], hoje=HOJE)
    resultado = disparar(
        base_populada, pacote.id, [Destinatario("f1"), Destinatario("f2")], tipo=TipoModelo.COBRANCA, hoje=HOJE
    )
    assert [i.ok for i in resultado.itens] == [True, False]
    assert "não tem RFQ" in resultado.falhas[0].mensagem


def test_validacoes(base_populada, pacote):
    with pytest.raises(srv.ErroNegocio, match="Marque pelo menos um fornecedor"):
        disparar(base_populada, pacote.id, [])
    with pytest.raises(srv.ErroNegocio, match="Selecione a RFQ"):
        disparar(base_populada, "inexistente", [Destinatario("f1")])
