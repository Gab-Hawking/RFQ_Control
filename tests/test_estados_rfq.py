"""Transições de estado da RFQ: revisão, confirmação, volta a rascunho e gravação concorrente."""

from datetime import date

import pytest

from rfq_control.modelos import Idioma, StatusRFQ
from rfq_control.servicos import cadastros, envio_email
from rfq_control.servicos import rfq as srv

HOJE = date(2026, 9, 30)


@pytest.fixture
def aberta(base_populada, pacote_exemplo, monkeypatch):
    """RFQ de f1 com o e-mail aberto para revisão em 30/09 (prazo escrito: 06/10)."""
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    _, [rfq] = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1"])
    return envio_email.gerar_email_rfq(base_populada, rfq.id, hoje=HOJE).rfq


def test_salvar_tela_desatualizada_nao_desfaz_envio_confirmado(base_populada, aberta):
    carregada = aberta.model_copy(deep=True)  # o que a tela da RFQ tinha aberto
    srv.confirmar_envio(base_populada, aberta, date(2026, 10, 1), "Envio confirmado nos Itens Enviados")
    formulario = carregada.model_copy(update={"observacoes": "pediu desconto"})
    salva = srv.salvar_rfq(base_populada, formulario, carregada=carregada)
    assert salva.status == StatusRFQ.ENVIADA and salva.data_envio == date(2026, 10, 1)
    assert salva.observacoes == "pediu desconto"
    assert any("Itens Enviados" in e.descricao for e in salva.historico)
    # confirmar de novo (botão de uma tela antiga) não muda nada
    assert srv.confirmar_envio(base_populada, carregada).data_envio == date(2026, 10, 1)


def test_status_enviada_com_data_digitada_conta_o_prazo_dessa_data(base_populada, pacote_exemplo):
    _, [rfq] = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1"])
    formulario = rfq.model_copy(update={"status": StatusRFQ.ENVIADA, "data_envio": date(2026, 9, 1)})
    salva = srv.salvar_rfq(base_populada, formulario, carregada=rfq)
    # 4 dias úteis depois de 01/09 (terça), pulando o feriado de 7/9: 08/09
    assert salva.data_envio == date(2026, 9, 1) and salva.prazo == date(2026, 9, 8)


def test_confirmacao_grava_a_data_real_do_envio(base_populada, aberta, monkeypatch):
    # RFQ que já tinha sido enviada antes, voltou a rascunho e foi reaberta: vale a data do novo envio
    rfq = base_populada.rfqs.salvar(aberta.model_copy(update={"data_envio": date(2026, 9, 1)}))
    rfq = envio_email.gerar_email_rfq(base_populada, rfq.id, hoje=HOJE).rfq
    assert rfq.data_envio is None  # aberto para revisão: ainda não saiu
    confirmada = srv.confirmar_envio(base_populada, rfq, date(2026, 10, 2))
    assert confirmada.data_envio == date(2026, 10, 2) and confirmada.prazo == date(2026, 10, 6)


def test_email_nao_enviado_volta_para_rascunho(base_populada, aberta):
    [rascunho] = srv.alterar_status(base_populada, [aberta.id], StatusRFQ.RASCUNHO)
    assert rascunho.status == StatusRFQ.RASCUNHO and not rascunho.aguardando_envio()
    assert rascunho.prazo is None and rascunho.situacao() == "Rascunho"
    assert "E-mail não enviado" in rascunho.historico[-1].descricao
    assert srv.alterar_status(base_populada, [aberta.id], StatusRFQ.RASCUNHO) == []  # já é rascunho


def test_rfq_aguardando_envio_nao_pode_ser_excluida(base_populada, aberta):
    with pytest.raises(srv.ErroNegocio, match="já foi aberto para envio"):
        srv.excluir_rfq(base_populada, aberta.id)
    srv.alterar_status(base_populada, [aberta.id], StatusRFQ.RASCUNHO)
    srv.excluir_rfq(base_populada, aberta.id)
    assert base_populada.rfqs.obter(aberta.id) is None


def test_reabrir_email_de_rfq_enviada_registra_reenvio(base_populada, aberta, monkeypatch):
    enviada = srv.confirmar_envio(base_populada, aberta, date(2026, 10, 1))
    reaberta = envio_email.gerar_email_rfq(base_populada, enviada.id, hoje=date(2026, 10, 5)).rfq
    assert reaberta.status == StatusRFQ.ENVIADA and reaberta.prazo == enviada.prazo
    assert "reaberto para revisão" in reaberta.historico[-1].descricao
    assert "passa a Enviada" not in reaberta.historico[-1].descricao


def test_rfq_aguardando_envio_mantem_o_idioma_do_email(base_populada, aberta):
    fornecedor = base_populada.fornecedores.obter("f1")
    cadastros.salvar_fornecedor(base_populada, fornecedor.model_copy(update={"idioma": Idioma.EN}))
    assert base_populada.rfqs.obter(aberta.id).idioma == Idioma.PT  # o e-mail aberto foi em português
