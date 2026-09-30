"""Testes da interface (Qt em modo offscreen), com dados fictícios."""

from datetime import date

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from rfq_control.modelos import Idioma, MetodoEmail, StatusRFQ  # noqa: E402
from rfq_control.servicos import envio_email  # noqa: E402
from rfq_control.servicos import rfq as srv  # noqa: E402


@pytest.fixture(scope="session")
def app():
    from rfq_control.ui.estilo import aplicar_tema

    aplicacao = QApplication.instance() or QApplication([])
    aplicar_tema(aplicacao)
    return aplicacao


@pytest.fixture
def mensagens(monkeypatch):
    """Captura as caixas de mensagem em vez de abri-las."""
    registro = []
    for nome in ("warning", "information", "critical"):
        monkeypatch.setattr(
            QMessageBox, nome, staticmethod(lambda _pai, _titulo, texto, *a, _n=nome: registro.append((_n, texto)))
        )
    return registro


@pytest.fixture
def janela(app, base_populada, mensagens):
    from rfq_control.ui.janela_principal import JanelaPrincipal

    j = JanelaPrincipal(base_populada)
    yield j
    j.close()


def test_todas_as_paginas_abrem(janela, app, mensagens):
    for chave in ("painel", "rfqs", "pacotes", "fornecedores", "projetos", "solicitantes", "feriados",
                  "modelos", "configuracoes"):
        pagina = janela.ir_para(chave)
        app.processEvents()
        assert janela.paginas.currentWidget() is pagina
        assert not janela.grab().isNull()
    assert not [m for m in mensagens if m[0] == "critical"]


def test_nova_solicitacao_cria_rfqs(janela, app, mensagens):
    from rfq_control.ui.dialogo_pacote import DialogoPacote

    dialogo = DialogoPacote(janela)
    dialogo.projeto.setCurrentIndex(dialogo.projeto.findData("prj1"))
    tabela = dialogo.tabela_itens
    tabela.item(0, 0).setText("PEÇA 1")
    tabela.item(0, 1).setText("CDC PEÇA 1")
    tabela.item(0, 4).setText("2")
    tabela.item(1, 0).setText("PEÇA 2")
    tabela.item(1, 5).setText("154.000")
    lista = dialogo.fornecedores.lista
    for linha in range(lista.count()):
        item = lista.item(linha)
        if item.data(Qt.ItemDataRole.UserRole) in ("f1", "f2"):
            item.setCheckState(Qt.CheckState.Checked)
    assert dialogo.botao_salvar.text() == "Criar 2 RFQ(s)"
    dialogo._salvar()

    assert not mensagens
    assert len(dialogo.rfqs_criadas) == 2
    pacote = janela.base.pacotes.obter(dialogo.original.id)
    assert [(i.ref_op, i.quantidade, i.volume_anual) for i in pacote.itens] == [
        ("PEÇA 1", 2.0, None), ("PEÇA 2", None, 154000.0)
    ]
    ano = date.today().year
    assert sorted(r.numero for r in janela.base.rfqs) == [f"RFQ{ano}001", f"RFQ{ano}002"]


def test_nova_solicitacao_sem_fornecedor_avisa(janela, mensagens):
    from rfq_control.ui.dialogo_pacote import DialogoPacote

    dialogo = DialogoPacote(janela)
    dialogo.projeto.setCurrentIndex(dialogo.projeto.findData("prj1"))
    dialogo.tabela_itens.item(0, 0).setText("PEÇA 1")
    dialogo._salvar()
    assert mensagens and "pelo menos um fornecedor" in mensagens[0][1]
    assert not len(janela.base.pacotes)


def test_colar_do_excel(app, janela):
    from rfq_control.ui.dialogo_pacote import TabelaItens

    tabela = TabelaItens()
    tabela.adicionar_linha()
    tabela.setCurrentCell(0, 0)
    QGuiApplication.clipboard().setText("A\tCDC A\t\tPC\t2\r\nB\tCDC B\tdesc B\tEA\t1.464,5\t154.000\r\n")
    assert tabela.colar() == 2
    itens = tabela.itens()
    assert [(i.ref_op, i.unidade, i.quantidade, i.volume_anual, i.descricao) for i in itens] == [
        ("A", "PC", 2.0, None, ""), ("B", "EA", 1464.5, 154000.0, "desc B")
    ]
    tabela.item(0, 4).setText("abc")
    with pytest.raises(srv.ErroNegocio, match="não é um número"):
        tabela.itens()


def test_dialogo_rfq_registra_resposta(janela, pacote_exemplo, mensagens):
    from rfq_control.ui.dialogo_rfq import DialogoRFQ

    _, [rfq] = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1"])
    dialogo = DialogoRFQ(janela, rfq)
    dialogo.status.setCurrentIndex(dialogo.status.findData(StatusRFQ.RESPONDIDA))
    dialogo.valor.setValue(12500.5)
    dialogo.lead_time.setText("10 semanas")
    dialogo._salvar()
    salva = janela.base.rfqs.obter(rfq.id)
    assert salva.status == StatusRFQ.RESPONDIDA
    assert salva.valor_total == 12500.5 and salva.lead_time == "10 semanas"
    assert salva.data_resposta == date.today()
    assert any("Rascunho para Respondida" in e.descricao for e in salva.historico)


def test_gerar_email_pela_lista(janela, pacote_exemplo, monkeypatch, mensagens):
    from rfq_control.ui import acoes

    base = janela.base
    base.salvar_configuracoes(base.configuracoes.model_copy(update={"metodo_email": MetodoEmail.EML}))
    abertos = []
    monkeypatch.setattr(envio_email, "abrir_arquivo", abertos.append)
    _, rfqs = srv.criar_pacote_com_rfqs(base, pacote_exemplo, ["f1", "f2"])
    assert acoes.gerar_emails(janela, rfqs, Idioma.EN) == 2
    assert len(abertos) == 2 and all(p.suffix == ".eml" for p in abertos)
    assert all(base.rfqs.obter(r.id).status == StatusRFQ.ENVIADA for r in rfqs)

    pagina = janela.ir_para("rfqs")
    pagina.filtrar_situacao("Em aberto")
    assert len(pagina.tabela.visiveis()) == 2
    pagina.filtrar_situacao(StatusRFQ.RASCUNHO.value)
    assert pagina.tabela.visiveis() == []


def test_email_de_fornecedor_sem_contato_avisa(janela, pacote_exemplo, mensagens):
    from rfq_control.ui import acoes

    _, [rfq] = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f3"])
    assert acoes.gerar_emails(janela, [rfq]) == 0
    assert "não tem e-mail de destinatário" in mensagens[-1][1]
    assert janela.base.rfqs.obter(rfq.id).status == StatusRFQ.RASCUNHO


def test_fornecedor_com_email_invalido(janela, mensagens):
    from rfq_control.ui.pagina_cadastros import DialogoFornecedor

    dialogo = DialogoFornecedor(janela)
    dialogo.nome.setText("Novo Fornecedor")
    dialogo.contatos.item(0, 0).setText("Ana")
    dialogo.contatos.item(0, 1).setText("ana(arroba)teste")
    dialogo._salvar()
    assert "e-mail inválido" in mensagens[-1][1]
    dialogo.contatos.item(0, 1).setText("ana@teste.com")
    dialogo._salvar()
    assert dialogo.resultado.emails_para() == ["ana@teste.com"]


def test_pre_visualizacao_do_modelo(base):
    from rfq_control.ui.pagina_modelos import pre_visualizar_html

    for modelo in base.modelos_email:
        html = pre_visualizar_html(modelo, "Empresa Exemplo", True)
        assert "{{" not in html and "<table" in html
