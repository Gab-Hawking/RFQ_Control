"""E-mail de agradecimento / status do projeto (dados fictícios)."""

from datetime import date

import pytest

from rfq_control.modelos import Idioma, StatusRFQ
from rfq_control.servicos import agradecimento, envio_email
from rfq_control.servicos import rfq as srv

ABRIR_NO_OUTLOOK = envio_email.abrir_no_outlook


@pytest.fixture
def projeto_enviado(base_populada, pacote_exemplo, monkeypatch):
    """Dois pacotes do Projeto Alfa: f1 recebeu os dois, f2 um; um rascunho fica de fora."""
    base = base_populada
    _, [a1, a2] = srv.criar_pacote_com_rfqs(base, pacote_exemplo, ["f1", "f2"])
    outro = pacote_exemplo.model_copy(update={"id": "p2", "titulo": "Segundo pacote"})
    _, [b1, rascunho] = srv.criar_pacote_com_rfqs(base, outro, ["f1", "f2"])
    for rfq in (a1, a2, b1):
        srv.registrar_envio(base, rfq, base.fornecedores.obter(rfq.fornecedor_id).idioma, "enviada", date(2026, 9, 1))
    abertos = []
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda email, enviar=False: abertos.append((email, enviar)))
    return base, abertos, [a1, a2, b1], rascunho


def test_lista_so_rfqs_enviadas_do_projeto(projeto_enviado):
    base, _, enviadas, rascunho = projeto_enviado
    ids = [r.id for r in agradecimento.rfqs_enviadas_do_projeto(base, "prj1")]
    assert sorted(ids) == sorted(r.id for r in enviadas) and rascunho.id not in ids
    assert [(p.nome, n) for p, n in agradecimento.projetos_com_rfqs_enviadas(base)] == [("Projeto Alfa", 3)]


def test_um_email_por_fornecedor_com_status(projeto_enviado):
    base, abertos, enviadas, _ = projeto_enviado
    resultado = agradecimento.enviar_agradecimento(
        base, [r.id for r in enviadas], "declinado", novo_status=StatusRFQ.CANCELADA)
    assert len(resultado.enviados) == 2 and not resultado.falhas
    (email_um, enviar), (email_dois, _) = abertos
    assert not enviar
    numeros_um = ", ".join(sorted(r.numero for r in enviadas if r.fornecedor_id == "f1"))
    assert numeros_um in email_um.assunto and numeros_um in email_um.html
    assert "Agradecemos a sua participação" in email_um.html and "foi declinado" in email_um.html
    assert email_dois.idioma == Idioma.EN and "has been declined" in email_dois.html
    assert email_um.anexos == []
    for rfq in enviadas:
        salva = base.rfqs.obter(rfq.id)
        assert salva.status == StatusRFQ.CANCELADA
        assert any("agradecimento" in e.descricao for e in salva.historico)


def test_motivo_outro_exige_texto_e_vai_igual_para_todos(projeto_enviado):
    base, abertos, enviadas, _ = projeto_enviado
    with pytest.raises(srv.ErroNegocio, match="Escreva a mensagem"):
        agradecimento.enviar_agradecimento(base, [enviadas[0].id], "outro")
    assert not abertos
    agradecimento.enviar_agradecimento(base, [enviadas[1].id], "outro", "O cliente adiou o projeto para 2028.")
    assert "adiou o projeto para 2028" in abertos[0][0].html
    assert base.rfqs.obter(enviadas[1].id).status == StatusRFQ.ENVIADA  # sem novo status: não muda


def test_rfqs_de_projetos_diferentes(projeto_enviado, pacote_exemplo):
    base, _, enviadas, _ = projeto_enviado
    beta = pacote_exemplo.model_copy(update={"id": "p3", "projeto_id": "prj2"})
    _, [outra] = srv.criar_pacote_com_rfqs(base, beta, ["f1"])
    with pytest.raises(srv.ErroNegocio, match="único projeto"):
        agradecimento.enviar_agradecimento(base, [enviadas[0].id, outra.id], "declinado")


def test_pre_visualizacao(projeto_enviado):
    base, abertos, enviadas, _ = projeto_enviado
    email = agradecimento.pre_visualizar(base, [r.id for r in enviadas], "outra_proposta")
    assert "outra proposta" in email.html and not abertos


def test_outra_proposta_nao_rebaixa_a_vencedora(projeto_enviado):
    base, abertos, enviadas, _ = projeto_enviado
    srv.alterar_status(base, [enviadas[0].id], StatusRFQ.SELECIONADA)
    agradecimento.enviar_agradecimento(
        base, [r.id for r in enviadas], "outra_proposta", novo_status=StatusRFQ.NAO_SELECIONADA)
    assert base.rfqs.obter(enviadas[0].id).status == StatusRFQ.SELECIONADA
    assert base.rfqs.obter(enviadas[1].id).status == StatusRFQ.NAO_SELECIONADA


def test_agradecimento_automatico_recusado_fica_aberto(projeto_enviado, monkeypatch):
    from outlook_falso import OutlookFalso, erro_com

    base, _, enviadas, _ = projeto_enviado
    monkeypatch.setattr(envio_email, "abrir_no_outlook", ABRIR_NO_OUTLOOK)  # o real, com o Outlook falso por baixo
    outlook = OutlookFalso(erro_envio=erro_com(-2147467260, "Operação anulada"))
    monkeypatch.setattr(envio_email, "_conectar_outlook", lambda iniciar=True: outlook)
    resultado = agradecimento.enviar_agradecimento(base, [r.id for r in enviadas], "declinado", enviar=True)
    assert [i.mensagem for i in resultado.itens] == ["aberto para revisão"] * 2 and len(outlook.criados) == 2
    assert all(item.exibido and not item.enviado_agora for item in outlook.criados)
    assert resultado.resumo() == "2 e-mail(s) aberto(s) para revisão" and "bloqueou o envio" in resultado.avisos[0]
    assert all("aberto para revisão" in base.rfqs.obter(r.id).historico[-1].descricao for r in enviadas)
