"""Testes da interface (Qt em modo offscreen), com dados fictícios."""

from datetime import date

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QModelIndex, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
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
    j.pagina("base").descartar_pendentes()  # senão o fechamento pergunta sobre linhas não salvas
    j.close()


def test_todas_as_paginas_abrem(janela, app, mensagens):
    for chave in ("painel", "rfqs", "pacotes", "base", "configuracoes"):
        pagina = janela.ir_para(chave)
        app.processEvents()
        assert janela.paginas.currentWidget() is pagina
        assert janela.botao_base.isChecked() == (chave == "base")
        assert not janela.grab().isNull()
    base = janela.pagina("base")
    for indice in range(base.abas.count()):
        base.abas.setCurrentIndex(indice)
        app.processEvents()
    assert [base.abas.tabText(i) for i in range(base.abas.count())] == [
        "Controle", "Fornecedores", "Commodities", "Projetos", "Feriados", "Condições", "Corpo do E-mail",
    ]
    assert base.abas.tabPosition() == base.abas.TabPosition.North  # abas em cima, abaixo da descrição
    assert janela.ir_para("feriados") is base and base.abas.currentWidget() is base.feriados
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
    # abertos para revisão: só viram Enviada quando o envio é confirmado
    assert all(base.rfqs.obter(r.id).aguardando_envio() for r in rfqs)

    pagina = janela.ir_para("rfqs")
    pagina.filtrar_situacao("Aguardando envio")
    assert len(pagina.tabela.visiveis()) == 2
    srv.alterar_status(base, [rfqs[0].id], StatusRFQ.ENVIADA)
    pagina.atualizar()
    pagina.filtrar_situacao("Em aberto")
    assert [r.id for r in pagina.tabela.visiveis()] == [rfqs[0].id]


def test_email_de_fornecedor_sem_contato_avisa(janela, pacote_exemplo, mensagens):
    from rfq_control.ui import acoes

    _, [rfq] = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f3"])
    assert acoes.gerar_emails(janela, [rfq]) == 0
    assert "não tem e-mail de destinatário" in mensagens[-1][1]
    assert janela.base.rfqs.obter(rfq.id).status == StatusRFQ.RASCUNHO


def test_fornecedor_com_email_invalido(janela, mensagens):
    from rfq_control.ui.dialogos_cadastro import DialogoFornecedor

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
        html = pre_visualizar_html(modelo, "Empresa Exemplo")
        assert "{{" not in html
        if modelo.tipo.name == "RFQ":
            assert "<table" in html


# ---------------------------------------------------------------- Base de dados


def _indice(grade, linha, chave):
    coluna = [c.chave for c in grade.definicao.colunas].index(chave)
    return grade.filtro.mapFromSource(grade.modelo.index(linha, coluna))


def test_grade_edita_e_salva_cada_linha(janela, app):
    base = janela.ir_para("fornecedores")
    grade = base.fornecedores.grade
    total = len(janela.base.fornecedores)
    base.fornecedores.nova_linha()
    linha = len(grade.modelo.linhas) - 1
    grade.model().setData(_indice(grade, linha, "email_para"), "nova@empresa.com")
    assert grade.modelo.linhas[linha].registro is None  # falta o nome (obrigatório)
    assert "Fornecedor" in grade.modelo.linhas[linha].erro
    grade.model().setData(_indice(grade, linha, "nome"), "Nova Empresa")
    grade.model().setData(_indice(grade, linha, "idioma"), "Espanhol")
    salvo = janela.base.fornecedores.obter(grade.modelo.linhas[linha].id)
    assert len(janela.base.fornecedores) == total + 1
    assert salvo.nome == "Nova Empresa" and salvo.idioma == Idioma.ES and salvo.emails_para() == ["nova@empresa.com"]

    grade.model().setData(_indice(grade, linha, "email_para"), "invalido")
    assert "E-mail inválido" in grade.modelo.linhas[linha].erro
    assert janela.base.fornecedores.obter(salvo.id).emails_para() == ["nova@empresa.com"]  # não gravou


def test_grade_cola_varias_linhas_do_excel(janela, app):
    base = janela.ir_para("projetos")
    grade = base.projetos.grade
    grade.setCurrentIndex(QModelIndex())
    grade.colar("Planta A\tCliente X\tProjeto Colado 1\t01/06/2027\t5\n"
                "Planta B\tCliente Y\tProjeto Colado 2\t\t\n"
                "Planta C\tCliente Z\t\t\t\n")
    nomes = {p.nome for p in janela.base.projetos}
    assert {"Projeto Colado 1", "Projeto Colado 2"} <= nomes
    colado = next(p for p in janela.base.projetos if p.nome == "Projeto Colado 1")
    assert colado.sop == date(2027, 6, 1) and colado.lifetime_anos == 5
    assert len(grade.modelo.pendentes()) == 1  # a linha sem nome do projeto ficou pendente


def test_sair_da_base_com_linha_pendente_pergunta(janela, app, monkeypatch):
    from rfq_control.ui import janela_principal

    base = janela.ir_para("condicoes")
    base.condicoes.nova_linha()
    grade = base.condicoes.grade
    grade.model().setData(_indice(grade, len(grade.modelo.linhas) - 1, "regiao_projeto"), "Chile")
    respostas = []
    monkeypatch.setattr(janela_principal, "confirmar", lambda *a, **k: respostas.append(a) or False)
    assert janela.ir_para("painel") is base  # ficou na Base de dados
    monkeypatch.setattr(janela_principal, "confirmar", lambda *a, **k: True)
    assert janela.ir_para("painel") is janela.pagina("painel")
    assert respostas and base.pendentes() == 0


def test_excluir_linha_em_uso_e_bloqueado(janela, pacote_exemplo, mensagens, monkeypatch):
    from rfq_control.ui import pagina_base_dados

    srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1"])
    base = janela.ir_para("fornecedores")
    grade = base.fornecedores.grade
    linha = next(i for i, l in enumerate(grade.modelo.linhas) if l.id == "f1")
    monkeypatch.setattr(pagina_base_dados, "confirmar", lambda *a, **k: True)
    grade.setCurrentIndex(_indice(grade, linha, "nome"))
    grade.selectionModel().select(_indice(grade, linha, "nome"), grade.selectionModel().SelectionFlag.Select)
    base.fornecedores.excluir()
    assert "tem 1 RFQ" in mensagens[-1][1]
    assert janela.base.fornecedores.obter("f1") is not None


def test_aba_controle_mostra_uma_linha_por_item(janela, pacote_exemplo):
    srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1", "f2"])
    base = janela.ir_para("controle")
    assert len(base.controle.tabela.visiveis()) == 4  # 2 RFQs x 2 itens


def test_delete_com_linha_inteira_exclui_na_grade(janela, app, monkeypatch):
    from rfq_control.ui import pagina_base_dados

    perguntas = []
    monkeypatch.setattr(pagina_base_dados, "confirmar", lambda _p, texto, *a, **k: perguntas.append(texto) or True)
    janela.show()
    janela.activateWindow()
    base = janela.ir_para("fornecedores")
    base.fornecedores.busca.setFocus()
    grade = base.fornecedores.grade
    linha = _indice(grade, next(i for i, l in enumerate(grade.modelo.linhas) if l.id == "f3"), "nome").row()
    cabecalho = grade.verticalHeader()  # clique no número da linha: seleciona a linha inteira e dá o foco à grade
    meio = cabecalho.sectionViewportPosition(linha) + cabecalho.sectionSize(linha) // 2
    QTest.mouseClick(cabecalho.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(10, meio))
    app.processEvents()
    assert app.focusWidget() is grade and grade.linhas_inteiras()
    QTest.keyClick(grade, Qt.Key.Key_Delete)
    assert perguntas == ["Excluir 1 linha(s)?"]
    assert janela.base.fornecedores.obter("f3") is None
    assert all(l.id != "f3" for l in grade.modelo.linhas)


def test_delete_em_celula_so_limpa_a_celula(janela, monkeypatch):
    from rfq_control.ui import pagina_base_dados

    monkeypatch.setattr(pagina_base_dados, "confirmar", lambda *a, **k: pytest.fail("não deveria excluir"))
    base = janela.ir_para("fornecedores")
    grade = base.fornecedores.grade
    linha = next(i for i, l in enumerate(grade.modelo.linhas) if l.id == "f1")
    grade.setFocus()
    grade.setCurrentIndex(_indice(grade, linha, "email_cc"))
    QTest.keyClick(grade, Qt.Key.Key_Delete)
    fornecedor = janela.base.fornecedores.obter("f1")
    assert fornecedor is not None and not [c for c in fornecedor.contatos if c.copia]


def test_delete_na_aba_controle_exclui_a_rfq(janela, pacote_exemplo, monkeypatch):
    from rfq_control.ui import acoes

    _, rfqs = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1", "f2"])
    perguntas = []
    monkeypatch.setattr(acoes, "confirmar", lambda _p, texto, *a, **k: perguntas.append(texto) or True)
    base = janela.ir_para("controle")
    tabela = base.controle.tabela
    linha = next(r for r in range(tabela.filtro.rowCount())
                 if tabela.filtro.index(r, 0).data() == rfqs[0].numero)
    tabela.setFocus()
    tabela.selectRow(linha)
    QTest.keyClick(tabela, Qt.Key.Key_Delete)
    assert perguntas[0].startswith(f"Excluir {rfqs[0].numero}?") and "todas as linhas" in perguntas[0]
    assert janela.base.rfqs.obter(rfqs[0].id) is None and janela.base.rfqs.obter(rfqs[1].id) is not None
    assert len(tabela.visiveis()) == 2  # as 2 linhas de item da RFQ excluída saíram


def test_delete_na_lista_de_rfqs(janela, pacote_exemplo, monkeypatch, mensagens):
    from rfq_control.ui import acoes

    _, rfqs = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1", "f2", "f3"])
    rascunho, enviada, aguardando = rfqs
    srv.registrar_envio(janela.base, enviada, Idioma.PT, "enviada")
    srv.registrar_revisao(janela.base, aguardando, Idioma.PT, "aberta para revisão", None)
    perguntas = []
    monkeypatch.setattr(acoes, "confirmar", lambda _p, texto, *a, **k: perguntas.append(texto) or True)
    pagina = janela.ir_para("rfqs")
    pagina.tabela.setFocus()
    pagina.tabela.selectAll()
    QTest.keyClick(pagina.tabela, Qt.Key.Key_Delete)
    assert perguntas[0] == f"Excluir {rascunho.numero}?"
    assert "Marcar como Cancelada" in perguntas[1] and enviada.numero in perguntas[1]
    assert any(aguardando.numero in texto for _tipo, texto in mensagens)
    assert janela.base.rfqs.obter(rascunho.id) is None
    assert janela.base.rfqs.obter(enviada.id).status == StatusRFQ.CANCELADA  # o número fica guardado
    assert janela.base.rfqs.obter(aguardando.id).aguardando_envio()
    assert len(pagina.tabela.visiveis()) == 2


# ---------------------------------------------------------------- envio de e-mails


def test_dialogo_de_envio(janela, pacote_exemplo, monkeypatch, mensagens):
    from rfq_control.ui.dialogo_envio import DialogoEnvio

    usados = []
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda email, enviar=False: usados.append((email, enviar)))
    pacote, _ = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1"])
    dialogo = DialogoEnvio(janela, pacote.id)
    assert dialogo.pacote_atual().id == pacote.id
    # f1 tem RFQ em rascunho: já vem marcado; f3 não tem e-mail: não pode ser marcado
    assert [d.fornecedor_id for d in dialogo.destinatarios()] == ["f1"]
    dialogo.marcar({"f1", "f2", "f3"})
    assert [d.fornecedor_id for d in dialogo.destinatarios()] == ["f1", "f2"]
    assert dialogo.botao_enviar.text() == "Abrir e-mail para 2 fornecedor(es)"
    dialogo._enviar()

    assert dialogo.resultado and len(dialogo.resultado.enviados) == 2
    assert [enviar for _e, enviar in usados] == [False, False]
    assert {r.fornecedor_id for r in janela.base.rfqs_do_pacote(pacote.id)} == {"f1", "f2"}
    assert all(r.situacao() == "Aguardando envio" for r in janela.base.rfqs_do_pacote(pacote.id))
    assert usados[1][0].idioma == Idioma.EN  # idioma do fornecedor f2


# ---------------------------------------------------------------- commodities, filtros, agradecimento


@pytest.fixture
def com_commodities(janela):
    from rfq_control.modelos import Commodity
    from rfq_control.servicos import cadastros

    base = janela.base
    base.commodities.salvar_varios([
        Commodity(id="c1", nome="Ferramentaria", comprador="Bia", email="bia@op.com"),
        Commodity(id="c2", nome="Dispositivos", comprador="Caio", email="caio@op.com"),
    ])
    cadastros.salvar_fornecedor(base, base.fornecedores.obter("f1").model_copy(update={"commodity_ids": ["c1"]}))
    cadastros.salvar_fornecedor(base, base.fornecedores.obter("f2").model_copy(update={"commodity_ids": ["c2"]}))
    return janela


def test_grade_de_fornecedores_com_commodity(com_commodities, app):
    from rfq_control.ui.grade import EditorMultiplo

    pagina = com_commodities.ir_para("fornecedores")
    grade = pagina.fornecedores.grade
    titulos = [c.titulo for c in grade.definicao.colunas]
    assert titulos == ["Fornecedor", "E-mail (Para)", "E-mails Supplier (Cc)", "Commodity",
                       "E-mail Commodity Buyer (Cc)", "Idioma", "Região"]
    linha = next(i for i, l in enumerate(grade.modelo.linhas) if l.id == "f3")
    buyer = _indice(grade, linha, "email_buyer")
    assert not grade.model().flags(buyer) & Qt.ItemFlag.ItemIsEditable  # coluna calculada

    indice = _indice(grade, linha, "commodities")
    grade.setCurrentIndex(indice)
    grade.edit(indice)
    app.processEvents()
    editor = grade.indexWidget(indice) or next(
        w for w in grade.viewport().findChildren(EditorMultiplo) if w.isVisible())
    # "Molde": commodity da condição padrão Moldes
    assert [editor.item(i).text() for i in range(editor.count())] == ["Dispositivos", "Ferramentaria", "Molde"]
    editor._alternar(editor.item(0))
    editor._alternar(editor.item(1))
    grade.itemDelegate().setModelData(editor, grade.model(), indice)
    assert com_commodities.base.fornecedores.obter("f3").commodity_ids == ["c2", "c1"]
    assert grade.modelo.linhas[linha].valores["email_buyer"] == "caio@op.com; bia@op.com"


def test_nova_solicitacao_filtra_por_commodity(com_commodities, app):
    from rfq_control.ui.dialogo_pacote import DialogoPacote

    dialogo = DialogoPacote(com_commodities)
    lista = dialogo.fornecedores

    def visiveis():
        return [lista.lista.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(lista.lista.count()) if not lista.lista.item(i).isHidden()]

    assert visiveis() == ["f1", "f3", "f2"]
    dialogo.commodity.setCurrentIndex(dialogo.commodity.findData("c2"))  # commodity do pacote filtra a lista
    assert visiveis() == ["f2"]
    lista.commodity.setCurrentIndex(lista.commodity.findData("__sem__"))
    assert visiveis() == ["f3"]
    lista.commodity.setCurrentIndex(0)
    lista.idioma.setCurrentIndex(lista.idioma.findData("EN"))
    assert visiveis() == ["f2"]
    lista.idioma.setCurrentIndex(0)
    lista._marcar_visiveis(True)
    lista.so_marcados.setChecked(True)
    assert visiveis() == ["f1", "f3", "f2"] and len(lista.selecionados()) == 3
    lista._marcar_visiveis(False, todos=True)
    assert visiveis() == [] and "0 marcado" in lista.contador.text()

    dialogo.projeto.setCurrentIndex(dialogo.projeto.findData("prj1"))
    dialogo.tabela_itens.item(0, 0).setText("PEÇA 1")
    lista.so_marcados.setChecked(False)
    for i in range(lista.lista.count()):
        if lista.lista.item(i).data(Qt.ItemDataRole.UserRole) == "f2":
            lista.lista.item(i).setCheckState(Qt.CheckState.Checked)
    dialogo._salvar()
    assert com_commodities.base.pacotes.obter(dialogo.original.id).commodity_id == "c2"


def test_excluir_rascunhos_oferece_excluir_pacote_vazio(janela, pacote_exemplo, monkeypatch):
    from rfq_control.ui import acoes

    pacote, rfqs = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1", "f2"])
    pagina = janela.ir_para("rfqs")
    pagina.tabela.selectAll()
    perguntas = []
    monkeypatch.setattr(acoes, "confirmar", lambda _p, texto, *a, **k: perguntas.append(texto) or True)
    pagina._excluir()
    assert len(perguntas) == 2 and pacote.titulo in perguntas[1]
    assert not len(janela.base.rfqs) and janela.base.pacotes.obter(pacote.id) is None


def test_agradecimento_pelo_dialogo(com_commodities, pacote_exemplo, monkeypatch, mensagens):
    from rfq_control.ui import dialogo_agradecimento
    from rfq_control.ui.dialogo_agradecimento import DialogoAgradecimento

    base = com_commodities.base
    _, rfqs = srv.criar_pacote_com_rfqs(base, pacote_exemplo, ["f1", "f2"])
    for rfq in rfqs:
        srv.registrar_envio(base, rfq, base.fornecedores.obter(rfq.fornecedor_id).idioma, "enviada")
    abertos = []
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda email, enviar=False: abertos.append(email))
    monkeypatch.setattr(dialogo_agradecimento, "mostrar_resultado", lambda *a, **k: None)
    dialogo = DialogoAgradecimento(com_commodities, "prj1")
    assert dialogo.tabela.rowCount() == 2 and len(dialogo.rfq_ids()) == 2
    assert dialogo.novo_status.currentData() == StatusRFQ.CANCELADA.value  # sugerido para "declinado"
    assert dialogo.botao_enviar.text() == "Abrir 2 e-mail(s)"
    dialogo._enviar()
    assert len(abertos) == 2 and "foi declinado" in abertos[0].html
    assert "bia@op.com" in abertos[0].copia  # Commodity Buyer em cópia
    assert all(base.rfqs.obter(r.id).status == StatusRFQ.CANCELADA for r in rfqs)
    assert not [m for m in mensagens if m[0] == "critical"]


def test_janela_confirma_envio_pelos_itens_enviados(janela, pacote_exemplo, monkeypatch):
    from datetime import timedelta

    from outlook_falso import ItemFalso, OutlookFalso

    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    _, [rfq] = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1"])
    rfq = envio_email.gerar_email_rfq(janela.base, rfq.id).rfq
    outlook = OutlookFalso([ItemFalso(rfq.assunto_email, rfq.aguardando_envio_desde + timedelta(minutes=1))])
    conexoes = []
    monkeypatch.setattr(envio_email, "_conectar_outlook", lambda iniciar=True: conexoes.append(iniciar) or outlook)
    [confirmada] = janela.verificar_envios(forcar=True)
    assert conexoes == [False]  # a conferência automática só usa um Outlook já aberto
    assert confirmada.status == StatusRFQ.ENVIADA
    assert "Envio confirmado" in janela.statusBar().currentMessage()
    assert janela.verificar_envios(forcar=True) == []  # nada pendente: nem consulta o Outlook
    assert conexoes == [False]


# ---------------------------------------------------------------- correções da revisão


def test_detalhes_do_fornecedor_nao_perde_telefone(janela, mensagens):
    from rfq_control.modelos import Contato
    from rfq_control.ui.dialogos_cadastro import DialogoFornecedor

    base = janela.base
    fornecedor = base.fornecedores.obter("f1").model_copy(update={"contatos": [
        Contato(nome="João Compras", telefone="(11) 4000-1234"),
        Contato(telefone="(11) 9999-0000"),
        Contato(nome="Ana", email="ana@um.com", telefone="(11) 5555-0000"),
    ]})
    base.fornecedores.salvar(fornecedor)
    dialogo = DialogoFornecedor(janela, base.fornecedores.obter("f1"))
    dialogo.contatos.item(2, 1).setText("ana@um.com.br")  # corrigir o e-mail não apaga o telefone
    dialogo._salvar()
    assert [(c.nome, c.email, c.telefone) for c in base.fornecedores.obter("f1").contatos] == [
        ("João Compras", "", "(11) 4000-1234"), ("", "", "(11) 9999-0000"), ("Ana", "ana@um.com.br", "(11) 5555-0000"),
    ]


def test_editor_de_commodity_distingue_acentos(app):
    from rfq_control.ui.grade import EditorMultiplo

    editor = EditorMultiplo(("Fundicao", "Fundição"))
    editor.definir(["Fundição"])
    assert editor.valores() == ["Fundição"]


def test_envio_nao_pre_marca_rfq_aguardando_envio(janela, pacote_exemplo, monkeypatch):
    from rfq_control.ui.dialogo_envio import DialogoEnvio

    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    pacote, [um, dois] = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1", "f2"])
    envio_email.gerar_email_rfq(janela.base, um.id)  # f1: e-mail já aberto
    dialogo = DialogoEnvio(janela, pacote.id)
    assert [d.fornecedor_id for d in dialogo.destinatarios()] == ["f2"]


def test_colar_segue_as_colunas_do_modelo(janela, app):
    pagina = janela.ir_para("fornecedores")
    grade = pagina.fornecedores.grade
    grade.setCurrentIndex(QModelIndex())
    # linha no formato da planilha de 'Baixar modelo' (o e-mail do buyer é ignorado na grade)
    grade.colar("Proveedor Uno\tventas@uno.com\t\t\tbuyer@op.com\tEspanhol\tAR\n")
    uno = next(f for f in janela.base.fornecedores if f.nome == "Proveedor Uno")
    assert uno.idioma == Idioma.ES and uno.emails_para() == ["ventas@uno.com"] and uno.regiao == "Argentina"


def test_grade_com_linha_pendente_atualiza_as_outras(com_commodities, app):
    from rfq_control.servicos import cadastros

    pagina = com_commodities.ir_para("fornecedores")
    pagina.fornecedores.nova_linha()
    grade = pagina.fornecedores.grade
    grade.model().setData(_indice(grade, len(grade.modelo.linhas) - 1, "email_para"), "so@email.com")
    assert len(grade.modelo.pendentes()) == 1
    commodity = com_commodities.base.commodities.obter("c1")
    cadastros.salvar_commodity(com_commodities.base, commodity.model_copy(update={"nome": "Ferramentaria e Moldes"}))
    pagina.atualizar()
    linha_um = next(l for l in grade.modelo.linhas if l.id == "f1")
    assert linha_um.valores["commodities"] == "Ferramentaria e Moldes"
    assert len(grade.modelo.pendentes()) == 1  # a linha pendente continua lá
    grade.model().setData(_indice(grade, grade.modelo.linhas.index(linha_um), "email_cc"), "cc@um.com")
    assert not linha_um.erro and "cc@um.com" in com_commodities.base.fornecedores.obter("f1").emails_copia()
    pagina.descartar_pendentes()


def test_fornecedor_marcado_nao_some_pelo_filtro(com_commodities, app):
    from rfq_control.ui.dialogo_pacote import DialogoPacote

    dialogo = DialogoPacote(com_commodities)
    lista = dialogo.fornecedores
    for i in range(lista.lista.count()):
        if lista.lista.item(i).data(Qt.ItemDataRole.UserRole) == "f2":
            lista.lista.item(i).setCheckState(Qt.CheckState.Checked)
    dialogo.commodity.setCurrentIndex(dialogo.commodity.findData("c1"))
    visiveis = [lista.lista.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(lista.lista.count()) if not lista.lista.item(i).isHidden()]
    assert visiveis == ["f1", "f2"]  # f2 é de outra commodity, mas está marcado e vai receber


def test_agradecimento_nao_marca_a_vencedora(com_commodities, pacote_exemplo):
    from rfq_control.ui.dialogo_agradecimento import DialogoAgradecimento

    base = com_commodities.base
    _, rfqs = srv.criar_pacote_com_rfqs(base, pacote_exemplo, ["f1", "f2"])
    for rfq in rfqs:
        srv.registrar_envio(base, rfq, base.fornecedores.obter(rfq.fornecedor_id).idioma, "enviada")
    srv.alterar_status(base, [rfqs[0].id], StatusRFQ.SELECIONADA)
    dialogo = DialogoAgradecimento(com_commodities, "prj1")
    assert dialogo.rfq_ids() == [rfqs[1].id]


def test_dialogo_da_rfq_volta_a_rascunho_e_acompanha_a_confirmacao(janela, pacote_exemplo, monkeypatch):
    from rfq_control.ui.dialogo_rfq import DialogoRFQ

    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    _, [rfq] = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1"])
    rfq = envio_email.gerar_email_rfq(janela.base, rfq.id).rfq
    dialogo = DialogoRFQ(janela, rfq)
    assert not dialogo.botao_nao_enviado.isHidden()
    dialogo._nao_enviado()
    assert dialogo.rfq.situacao() == "Rascunho" and dialogo.botao_nao_enviado.isHidden()
    # e-mail reaberto e confirmado pelo Outlook com a tela aberta: a tela recarrega e salvar não desfaz
    envio_email.gerar_email_rfq(janela.base, rfq.id)
    dialogo._carregar()
    srv.confirmar_envio(janela.base, rfq, None, "Envio confirmado nos Itens Enviados do Outlook")
    janela.envios_confirmados.emit([rfq.numero])
    assert dialogo.status.currentData() == StatusRFQ.ENVIADA
    dialogo.lead_time.setText("8 semanas")
    dialogo._salvar()
    salva = janela.base.rfqs.obter(rfq.id)
    assert salva.status == StatusRFQ.ENVIADA and salva.lead_time == "8 semanas"


def test_conferencia_periodica_e_f5(janela, monkeypatch):
    from rfq_control.ui import janela_principal

    assert janela._repeticao.isActive() and janela._repeticao.interval() == janela_principal.REPETIR_VERIFICACAO_MS
    chamadas = []
    monkeypatch.setattr(janela, "verificar_envios", lambda forcar=False: chamadas.append(forcar) or [])
    janela._f5()
    assert chamadas == [True]


def test_mensagens_abrem_na_janela_e_nao_na_aba(janela):
    from rfq_control.ui.componentes import janela_de

    aba = janela.ir_para("fornecedores").fornecedores
    assert janela_de(aba) is janela and janela_de(None) is None


# ---------------------------------------------------------------- condições, região e sem solicitante


def test_aba_condicoes_abre_os_textos_no_corpo_do_email(janela, app, mensagens):
    from rfq_control.modelos import TipoModelo

    pagina = janela.ir_para("condicoes")
    grade = pagina.condicoes.grade
    linha = next(i for i, l in enumerate(grade.modelo.linhas) if l.registro.nome == "Moldes")
    grade.setCurrentIndex(_indice(grade, linha, "nome"))
    pagina._textos_condicao()
    modelos = pagina.modelos
    assert pagina.abas.currentWidget() is modelos
    assert modelos.atual.tipo == TipoModelo.CONDICAO and modelos.atual.idioma == Idioma.PT
    assert modelos.corpo.toPlainText().startswith("Favor enviar a cotação incluindo:")
    assert not modelos.assunto.isEnabled() and not modelos.botao_restaurar.isEnabled()
    assert modelos.lista.currentItem().text() == "Condição: Moldes — Português"
    # texto vazio é aceito (nada é acrescentado nesse idioma) e a lista avisa
    modelos.corpo.setPlainText("")
    modelos._salvar()
    assert not [m for m in mensagens if m[0] == "critical"]
    assert modelos.lista.currentItem().text() == "Condição: Moldes — Português (vazio)"
    pagina.condicoes.atualizar()
    moldes = next(l for l in grade.modelo.linhas if l.registro.nome == "Moldes")
    assert moldes.valores["texto"] == "sem texto em Português"


def test_regiao_na_grade_aceita_valor_digitado(janela, app):
    from PySide6.QtWidgets import QComboBox

    pagina = janela.ir_para("fornecedores")
    grade = pagina.fornecedores.grade
    linha = next(i for i, l in enumerate(grade.modelo.linhas) if l.id == "f1")
    indice = _indice(grade, linha, "regiao")
    grade.setCurrentIndex(indice)
    grade.edit(indice)
    app.processEvents()
    editor = grade.viewport().findChildren(QComboBox)[-1]  # editor aberto na célula
    assert editor.isEditable() and editor.findText("Argentina") >= 0
    editor.setCurrentText("uruguay")
    grade.itemDelegate().setModelData(editor, grade.model(), indice)
    assert janela.base.fornecedores.obter("f1").regiao == "Uruguai"


def test_dialogos_tem_regiao_e_nao_tem_solicitante(janela, pacote_exemplo, mensagens):
    from rfq_control.ui.dialogo_pacote import DialogoPacote
    from rfq_control.ui.dialogo_rfq import DialogoRFQ
    from rfq_control.ui.dialogos_cadastro import DialogoFornecedor

    dialogo = DialogoFornecedor(janela, janela.base.fornecedores.obter("f1"))
    dialogo.regiao.setCurrentText("BR")
    dialogo._salvar()
    assert janela.base.fornecedores.obter("f1").regiao == "Brasil"

    janela.base.projetos.salvar(janela.base.projetos.obter("prj1").model_copy(update={"regiao": "Argentina"}))
    nova = DialogoPacote(janela)
    assert not hasattr(nova, "solicitante")
    nova.projeto.setCurrentIndex(nova.projeto.findData("prj1"))
    assert "Região: Argentina" in nova.info_projeto.text()

    _, [rfq] = srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1"])
    detalhe = DialogoRFQ(janela, rfq)
    textos = [detalhe.info.itemAt(i).widget().text() for i in range(detalhe.info.count())
              if detalhe.info.itemAt(i).widget()]
    assert "Solicitante" not in textos and "Condições" in textos
    assert "Brasil → Argentina" in textos


def test_controle_e_listas_sem_solicitante(janela, pacote_exemplo):
    srv.criar_pacote_com_rfqs(janela.base, pacote_exemplo, ["f1"])
    controle = janela.ir_para("controle").controle
    rfqs = janela.ir_para("rfqs")
    pacotes = janela.ir_para("pacotes")
    for tabela in (controle.tabela, rfqs.tabela, pacotes.tabela):
        titulos = [tabela.model().headerData(i, Qt.Orientation.Horizontal) for i in range(tabela.model().columnCount())]
        assert "Solicitante" not in titulos
    assert controle.tabela.itemDelegateForColumn(10).__class__.__name__ == "DelegadoSituacao"


def test_excluir_commodity_avisa_que_sai_dos_fornecedores(com_commodities, app, monkeypatch):
    from rfq_control.ui import pagina_base_dados

    pagina = com_commodities.ir_para("commodities")
    grade = pagina.commodities.grade
    linha = next(i for i, l in enumerate(grade.modelo.linhas) if l.id == "c1")
    grade.setCurrentIndex(_indice(grade, linha, "nome"))
    perguntas = []
    monkeypatch.setattr(pagina_base_dados, "confirmar", lambda _p, texto, *a, **k: perguntas.append(texto) or True)
    pagina.commodities.excluir()
    assert "sai de 1 fornecedor" in perguntas[0]
    assert com_commodities.base.commodities.obter("c1") is None
    assert com_commodities.base.fornecedores.obter("f1").commodity_ids == []
