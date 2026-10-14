from datetime import date
from email import message_from_bytes, policy

import pytest

from rfq_control.modelos import Idioma, MetodoEmail, StatusRFQ, TipoModelo
from rfq_control.servicos import envio_email
from rfq_control.servicos import rfq as srv
from rfq_control.servicos.email_rfq import montar_email, renderizar

HOJE = date(2026, 9, 30)


@pytest.fixture
def rfqs(base_populada, pacote_exemplo):
    base_populada.salvar_configuracoes(
        base_populada.configuracoes.model_copy(update={"copia_padrao": "comprador@exemplo.com; copia@um.com"})
    )
    _, rfqs = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1", "f2", "f3"])
    return rfqs


def test_email_em_portugues(base_populada, rfqs):
    email = montar_email(base_populada, rfqs[0], hoje=HOJE)
    assert email.para == ["joao@um.com"]
    # Cc do fornecedor + cópia padrão, sem repetir (corrige o bug B01)
    assert email.copia == ["copia@um.com", "comprador@exemplo.com"]
    assert email.assunto == f"{rfqs[0].numero} / Customer: Cliente A / Project: Projeto Alfa"
    assert "Caro João," in email.html  # saudação com o nome do contato (B03)
    assert "Empresa Exemplo" in email.html
    assert "terça-feira, 6 de outubro de 2026" in email.html
    assert "<b>Prazo para retorno: terça-feira, 6 de outubro de 2026</b>" in email.html
    assert "Planta Sul" in email.html  # planta correta (B02)
    assert "154.000" in email.html  # volume anual incluído (B11)
    assert "Volume anual" in email.html and "2 PC" in email.html  # quantidade com a unidade
    assert "120%" not in email.html and "Cobertura" not in email.html  # sem colunas para o fornecedor preencher
    assert "{{" not in email.html and "{{" not in email.texto
    assert email.prazo == date(2026, 10, 6)


def test_email_em_ingles_usa_data_em_ingles(base_populada, rfqs):
    email = montar_email(base_populada, rfqs[1], hoje=HOJE)
    assert email.idioma == Idioma.EN
    assert "Dear Anna," in email.html
    assert "Tuesday, October 6, 2026" in email.html  # corrige o bug B07
    assert "terça" not in email.html
    assert "154,000" in email.html


def test_fornecedor_sem_email_gera_erro_claro(base_populada, rfqs):
    with pytest.raises(srv.ErroNegocio, match="Sem Email não tem e-mail"):
        montar_email(base_populada, rfqs[2], hoje=HOJE)


def test_renderizar_escapa_html_e_mantem_paragrafos():
    html, texto = renderizar(
        "Olá {{contato}},\nlinha 2\n\n**Negrito {{x}}**\n\n{{tabela_itens}}",
        {"contato": "A & B <ltda>", "x": "1"},
        {"tabela_itens": ("<table>T</table>", "T")},
    )
    assert "A &amp; B &lt;ltda&gt;" in html
    assert "Olá A &amp; B &lt;ltda&gt;,<br>linha 2" in html
    assert "<b>Negrito 1</b>" in html
    assert "<table>T</table>" in html
    assert texto == "Olá A & B <ltda>,\nlinha 2\n\nNegrito 1\n\nT"


def test_gerar_eml_e_registrar_envio(base_populada, rfqs, monkeypatch):
    base_populada.salvar_configuracoes(
        base_populada.configuracoes.model_copy(
            update={"metodo_email": MetodoEmail.EML, "assinatura_html": "<p>Maria — Compras</p>"}
        )
    )
    anexo = base_populada.pasta_anexos(rfqs[0].pacote_id)
    anexo.mkdir(parents=True)
    (anexo / "cdc.pdf").write_bytes(b"%PDF teste")
    pacote = base_populada.pacotes.obter(rfqs[0].pacote_id)
    base_populada.pacotes.salvar(pacote.model_copy(update={"anexos": ["cdc.pdf"]}))

    resultado = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, abrir=False, hoje=HOJE)
    assert not resultado.via_outlook
    mensagem = message_from_bytes(resultado.arquivo_eml.read_bytes(), policy=policy.default)
    assert mensagem["X-Unsent"] == "1"
    assert mensagem["To"] == "joao@um.com"
    assert "comprador@exemplo.com" in mensagem["Cc"]
    html = mensagem.get_body(("html",)).get_content()
    assert "Maria — Compras" in html
    assert [p.get_filename() for p in mensagem.iter_attachments()] == ["cdc.pdf"]

    assert mensagem["Message-ID"]

    rfq = resultado.rfq
    # aberto para revisão: ainda não foi enviado (se o rascunho for apagado, continua em rascunho)
    assert rfq.status == StatusRFQ.RASCUNHO and rfq.aguardando_envio() and rfq.data_envio is None
    assert rfq.prazo == date(2026, 10, 6)  # prazo escrito no e-mail, gravado quando o envio for confirmado
    assert rfq.message_id == mensagem["Message-ID"] and rfq.assunto_email == mensagem["Subject"]
    assert "E-mail de RFQ aberto para revisão (arquivo .eml)" in rfq.historico[-1].descricao

    confirmada = srv.confirmar_envio(base_populada, rfq, date(2026, 10, 1))
    assert confirmada.status == StatusRFQ.ENVIADA and not confirmada.aguardando_envio()
    assert confirmada.data_envio == date(2026, 10, 1) and confirmada.prazo == date(2026, 10, 6)


def test_outlook_indisponivel_cai_para_eml(base_populada, rfqs, monkeypatch):
    abertos = []
    monkeypatch.setattr(envio_email, "abrir_arquivo", abertos.append)

    def sem_outlook(_):
        raise envio_email.ErroOutlook("Outlook não encontrado.")

    monkeypatch.setattr(envio_email, "abrir_no_outlook", sem_outlook)
    resultado = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE)
    assert not resultado.via_outlook
    assert "Outlook não encontrado" in resultado.aviso
    assert abertos == [resultado.arquivo_eml]


def test_outlook_disponivel(base_populada, rfqs, monkeypatch):
    usados = []
    monkeypatch.setattr(envio_email, "abrir_no_outlook", usados.append)
    resultado = envio_email.gerar_email_rfq(base_populada, rfqs[1].id, hoje=HOJE)
    assert resultado.via_outlook and resultado.arquivo_eml is None
    assert usados[0].assunto.startswith(rfqs[1].numero)


def test_cobranca_nao_altera_prazo(base_populada, rfqs, monkeypatch):
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    enviada = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True).rfq
    assert enviada.status == StatusRFQ.ENVIADA and enviada.prazo == date(2026, 10, 6)
    cobranca = envio_email.gerar_email_rfq(
        base_populada, rfqs[0].id, tipo=TipoModelo.COBRANCA, hoje=date(2026, 10, 8)
    )
    assert cobranca.rfq.prazo == enviada.prazo
    # o e-mail cita o prazo que o fornecedor recebeu (não um recalculado a partir do dia da cobrança)
    assert "cujo prazo de retorno era terça-feira, 6 de outubro de 2026" in cobranca.email.html
    assert "Ainda não recebemos" in cobranca.email.html
    assert "cobrança" in cobranca.rfq.historico[-1].descricao


def test_cobranca_de_rfq_aguardando_envio_usa_o_prazo_do_email(base_populada, rfqs, monkeypatch):
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    aberta = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE).rfq  # prazo escrito: 06/10
    assert aberta.aguardando_envio() and aberta.prazo == date(2026, 10, 6)
    cobranca = montar_email(base_populada, aberta, tipo=TipoModelo.COBRANCA, hoje=date(2026, 10, 13))
    assert cobranca.prazo == date(2026, 10, 6) and "6 de outubro de 2026" in cobranca.html
    citada = envio_email.cobranca_com_original(base_populada, aberta, cobranca)
    assert "19 de outubro" not in citada.html and citada.html.count("6 de outubro de 2026") == 2
    # reabrir o e-mail da RFQ (novo envio) conta o prazo a partir do dia de novo
    assert montar_email(base_populada, aberta, hoje=date(2026, 10, 13)).prazo == date(2026, 10, 19)


def test_inserir_antes_da_assinatura():
    resultado = envio_email.inserir_antes_da_assinatura(
        '<html><body lang="PT-BR"><div>Assinatura</div></body></html>', "<p>Corpo</p>"
    )
    assert resultado.index("<p>Corpo</p>") < resultado.index("Assinatura")


def test_email_em_espanhol(base_populada, rfqs):
    fornecedor = base_populada.fornecedores.obter("f2")
    base_populada.fornecedores.salvar(fornecedor.model_copy(update={"idioma": Idioma.ES}))
    email = montar_email(base_populada, rfqs[1], hoje=HOJE)
    assert email.idioma == Idioma.ES  # RFQ em rascunho segue o idioma atual do fornecedor
    assert "Estimado/a Anna:" in email.html
    assert "Plazo de respuesta: martes, 6 de octubre de 2026" in email.html
    assert "Descripción" not in email.html  # coluna vazia não aparece
    assert "Volumen anual" in email.html and "154.000" in email.html
    assert "Proyecto" in email.html


def test_rfq_enviada_mantem_idioma_do_envio(base_populada, rfqs, monkeypatch):
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True)  # PT
    fornecedor = base_populada.fornecedores.obter("f1")
    base_populada.fornecedores.salvar(fornecedor.model_copy(update={"idioma": Idioma.EN}))
    rfq = base_populada.rfqs.obter(rfqs[0].id)
    assert montar_email(base_populada, rfq, hoje=HOJE).idioma == Idioma.PT
    assert montar_email(base_populada, rfq, Idioma.EN, hoje=HOJE).idioma == Idioma.EN


@pytest.mark.parametrize("texto, esperado", [
    ("Português", "PT"), ("portugues", "PT"), ("Espanhol", "ES"), ("Español", "ES"), ("spanish", "ES"),
    ("Inglês", "EN"), ("ENGLISH", "EN"), ("en", "EN"),
])
def test_idioma_de_texto(texto, esperado):
    assert Idioma.de_texto(texto).value == esperado


def test_idioma_invalido():
    with pytest.raises(ValueError, match="idioma inválido"):
        Idioma.de_texto("Francês")


def test_envio_direto_pelo_outlook(base_populada, rfqs, monkeypatch):
    chamadas = []
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda email, enviar=False: chamadas.append(enviar))
    resultado = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True)
    assert chamadas == [True] and resultado.enviado and resultado.via_outlook
    assert resultado.rfq.status == StatusRFQ.ENVIADA
    assert "enviado pelo Outlook" in resultado.rfq.historico[-1].descricao


def test_envio_direto_com_falha_nao_registra(base_populada, rfqs, monkeypatch):
    def falha(email, enviar=False):
        raise envio_email.ErroOutlook("Outlook fechado.")

    monkeypatch.setattr(envio_email, "abrir_no_outlook", falha)
    with pytest.raises(srv.ErroNegocio, match="Outlook fechado"):
        envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True)
    assert base_populada.rfqs.obter(rfqs[0].id).status == StatusRFQ.RASCUNHO


def test_envio_direto_exige_outlook(base_populada, rfqs):
    base_populada.salvar_configuracoes(
        base_populada.configuracoes.model_copy(update={"metodo_email": MetodoEmail.EML})
    )
    with pytest.raises(srv.ErroNegocio, match="usa o Outlook"):
        envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True)


def test_envio_direto_pelo_outlook_de_verdade(base_populada, rfqs, monkeypatch):
    from outlook_falso import OutlookFalso

    outlook = OutlookFalso()
    monkeypatch.setattr(envio_email, "_conectar_outlook", lambda iniciar=True: outlook)
    resultado = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True)
    [item] = outlook.criados
    assert item.enviado_agora and not item.exibido and item.To == "joao@um.com"
    assert resultado.enviado and resultado.rfq.status == StatusRFQ.ENVIADA


def test_outlook_recusa_o_envio_direto_e_o_email_fica_aberto(base_populada, rfqs, monkeypatch):
    from outlook_falso import OutlookFalso, erro_com

    outlook = OutlookFalso(erro_envio=erro_com(-2147467260, "Operação anulada"))
    monkeypatch.setattr(envio_email, "_conectar_outlook", lambda iniciar=True: outlook)
    resultado = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True)
    [item] = outlook.criados
    assert item.exibido and not item.enviado_agora and item.To == "joao@um.com"  # nada se perde
    assert not resultado.enviado and resultado.via_outlook
    assert "Operação anulada" in resultado.aviso and "bloqueou o envio" in resultado.aviso
    assert "clique em Enviar" in resultado.aviso
    rfq = base_populada.rfqs.obter(rfqs[0].id)
    assert rfq.aguardando_envio()  # vira Enviada quando aparecer nos Itens Enviados, como na revisão
    assert "não enviou automaticamente" in rfq.historico[-1].descricao


def test_outlook_recusa_envio_e_exibicao_nada_e_registrado(base_populada, rfqs, monkeypatch):
    from outlook_falso import OutlookFalso, erro_com

    outlook = OutlookFalso(erro_envio=erro_com(-2147467260, "Operação anulada"), erro_exibir=RuntimeError("x"))
    monkeypatch.setattr(envio_email, "_conectar_outlook", lambda iniciar=True: outlook)
    with pytest.raises(srv.ErroNegocio, match="não enviou o e-mail: Operação anulada"):
        envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True)
    rfq = base_populada.rfqs.obter(rfqs[0].id)
    assert rfq.status == StatusRFQ.RASCUNHO and not rfq.aguardando_envio()


def test_explicar_erro_outlook():
    from outlook_falso import ErroCOMFalso, erro_com

    explicar = envio_email.explicar_erro_outlook
    assert explicar(erro_com(-2147467260, "Operação anulada")).startswith("Operação anulada — o Outlook bloqueou")
    nomes = "O Outlook não reconhece um ou mais nomes."
    assert explicar(erro_com(-2147467259, nomes)) == nomes  # erro sem causa conhecida: o texto do Outlook
    servidor = explicar(ErroCOMFalso(-2146959355, "Falha na execução do servidor", None, None))
    assert servidor.startswith("Falha na execução do servidor — ") and "permissões diferentes" in servidor
    assert explicar(RuntimeError("Outlook fechado")) == "Outlook fechado"


# ---------------------------------------------------------------- visual, confirmação e cobrança em resposta


def test_paragrafo_todo_em_negrito_vira_quadro_e_vazio_some():
    html, texto = renderizar("Olá\n\n**Prazo: {{prazo}}**\n\n{{motivo}}\n\nFim", {"prazo": "amanhã", "motivo": ""}, {})
    assert html.count("<table") == 1 and "<b>Prazo: amanhã</b>" in html and "#FFF4D6" in html
    assert html.count("<p ") == 2  # o parágrafo só com {{motivo}} vazio não aparece
    assert texto == "Olá\n\nPrazo: amanhã\n\nFim"


def test_tabela_de_itens_organizada(base_populada, rfqs):
    email = montar_email(base_populada, rfqs[0], hoje=HOJE)
    assert "Itens para cotação (2)" in email.html and "Dados do projeto" in email.html
    assert "#2E2E2E" in email.html  # cabeçalho escuro
    assert "Itens para cotação (2)\n# | OP - Ref | CDC - Ref | Qtd. | Volume anual" in email.texto


def _rfq_aberta_para_revisao(base, rfq, monkeypatch):
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    return envio_email.gerar_email_rfq(base, rfq.id, hoje=HOJE).rfq


def test_envio_confirmado_pelos_itens_enviados(base_populada, rfqs, monkeypatch):
    from datetime import datetime, timedelta

    from outlook_falso import ItemFalso, OutlookFalso

    rfq = _rfq_aberta_para_revisao(base_populada, rfqs[0], monkeypatch)
    assert rfq.aguardando_envio()
    outlook = OutlookFalso([ItemFalso(f"{rfq.numero}2 / outra RFQ", datetime.now())])
    assert envio_email.confirmar_envios_outlook(base_populada, outlook) == []  # rascunho apagado: nada muda
    assert base_populada.rfqs.obter(rfq.id).situacao() == "Aguardando envio"

    ontem = rfq.aguardando_envio_desde - timedelta(days=1)
    enviado = rfq.aguardando_envio_desde + timedelta(minutes=3)
    outlook.enviados[:] = [
        ItemFalso(f"RE: {rfq.assunto_email}", enviado + timedelta(hours=1)),  # resposta não conta
        ItemFalso(rfq.assunto_email, enviado),
        ItemFalso(rfq.assunto_email, ontem),  # envio antigo, antes de abrir o e-mail
    ]
    [confirmada] = envio_email.confirmar_envios_outlook(base_populada, outlook)
    assert confirmada.status == StatusRFQ.ENVIADA and confirmada.data_envio == enviado.date()
    assert confirmada.prazo == date(2026, 10, 6)  # o prazo que estava no e-mail
    assert "Itens Enviados" in confirmada.historico[-1].descricao
    assert envio_email.confirmar_envios_outlook(base_populada, outlook) == []  # nada mais pendente


def test_alterar_status_confirma_envio_manual(base_populada, rfqs, monkeypatch):
    rfq = _rfq_aberta_para_revisao(base_populada, rfqs[0], monkeypatch)
    [enviada] = srv.alterar_status(base_populada, [rfq.id], StatusRFQ.ENVIADA, hoje=date(2026, 10, 1))
    assert enviada.data_envio == date(2026, 10, 1) and enviada.prazo == date(2026, 10, 6)
    assert not enviada.aguardando_envio()


def test_cobranca_responde_ao_email_da_rfq(base_populada, rfqs, monkeypatch):
    from datetime import datetime

    from outlook_falso import ItemFalso, OutlookFalso

    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    rfq = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True).rfq
    original = ItemFalso(rfq.assunto_email, datetime(2026, 9, 30, 10))
    # iscas mais recentes com o número da RFQ: resposta, agradecimento do app e lembrete da v0.2
    agradecimento = ItemFalso(f"{rfq.numero} / Customer: Cliente A / Project: Projeto Alfa – Agradecimento",
                              datetime(2026, 10, 5))
    lembrete = ItemFalso(f"Lembrete / Reminder: {rfq.numero} / Customer: Cliente A", datetime(2026, 10, 3))
    outlook = OutlookFalso([ItemFalso(f"RE: {rfq.assunto_email}", datetime(2026, 10, 2)), agradecimento, lembrete,
                            original])
    monkeypatch.setattr(envio_email, "_conectar_outlook", lambda iniciar=True: outlook)

    resultado = envio_email.gerar_email_rfq(base_populada, rfq.id, tipo=TipoModelo.COBRANCA, hoje=date(2026, 10, 8))
    assert resultado.resposta and resultado.via_outlook
    [resposta] = original.respostas  # respondeu ao e-mail original, não à resposta anterior
    assert agradecimento.respostas == [] and lembrete.respostas == []
    assert resposta.exibido and not resposta.enviado_agora
    corpo = resposta.HTMLBody
    assert corpo.index("Ainda não recebemos") < corpo.index("Assinatura") < corpo.index("De: eu")
    assert resposta.Attachments == [] and resposta.Subject.startswith("RE: ")
    assert "como resposta ao e-mail da RFQ" in resultado.rfq.historico[-1].descricao
    assert base_populada.rfqs.obter(rfq.id).status == StatusRFQ.ENVIADA


def test_cobranca_automatica_recusada_fica_aberta_como_resposta(base_populada, rfqs, monkeypatch):
    from datetime import datetime

    from outlook_falso import ItemFalso, OutlookFalso, erro_com

    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    rfq = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True).rfq
    recusa = erro_com(-2147467260, "Operação anulada")
    original = ItemFalso(rfq.assunto_email, datetime(2026, 9, 30, 10), erro_envio=recusa)
    monkeypatch.setattr(envio_email, "_conectar_outlook", lambda iniciar=True: OutlookFalso([original]))
    resultado = envio_email.gerar_email_rfq(
        base_populada, rfq.id, tipo=TipoModelo.COBRANCA, hoje=date(2026, 10, 8), enviar=True)
    [resposta] = original.respostas
    assert resposta.exibido and not resposta.enviado_agora
    assert resultado.resposta and not resultado.enviado and "clique em Enviar" in resultado.aviso
    assert "cobrança aberto para revisão" in resultado.rfq.historico[-1].descricao


def test_cobranca_sem_email_original_vai_como_re_com_a_solicitacao(base_populada, rfqs, monkeypatch):
    from outlook_falso import OutlookFalso

    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda *_a, **_k: None)
    rfq = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE, enviar=True).rfq
    abertos = []
    monkeypatch.setattr(envio_email, "_conectar_outlook", lambda iniciar=True: OutlookFalso([]))
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda email, enviar=False: abertos.append(email))
    resultado = envio_email.gerar_email_rfq(base_populada, rfq.id, tipo=TipoModelo.COBRANCA, hoje=date(2026, 10, 8))
    [email] = abertos
    assert not resultado.resposta and "não foi encontrado" in resultado.aviso
    assert email.assunto == f"RE: {rfq.assunto_email}"
    assert email.html.index("Ainda não recebemos") < email.html.index("Mensagem original") < email.html.index(
        "Itens para cotação")


def test_cobranca_em_eml_aponta_para_o_email_da_rfq(base_populada, rfqs, monkeypatch):
    base_populada.salvar_configuracoes(base_populada.configuracoes.model_copy(update={"metodo_email": MetodoEmail.EML}))
    rfq = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, abrir=False, hoje=HOJE).rfq
    rfq = srv.confirmar_envio(base_populada, rfq, HOJE)
    resultado = envio_email.gerar_email_rfq(
        base_populada, rfq.id, tipo=TipoModelo.COBRANCA, abrir=False, hoje=date(2026, 10, 8))
    mensagem = message_from_bytes(resultado.arquivo_eml.read_bytes(), policy=policy.default)
    assert mensagem["In-Reply-To"] == rfq.message_id and mensagem["Subject"] == f"RE: {rfq.assunto_email}"
    assert list(mensagem.iter_attachments()) == []


def test_paragrafo_em_negrito_com_varias_linhas():
    html, _ = renderizar("**Prazo: {{prazo}}\nEnviar para compras@exemplo.com**", {"prazo": "amanhã"}, {})
    assert "**" not in html
    assert "<b>Prazo: amanhã<br>Enviar para compras@exemplo.com</b>" in html and "#FFF4D6" in html


def test_agradecimento_sem_cliente_nao_deixa_parenteses_vazios(base_populada, pacote_exemplo):
    from rfq_control.servicos.email_rfq import montar_email_agradecimento

    projeto = base_populada.projetos.obter("prj1")
    base_populada.projetos.salvar(projeto.model_copy(update={"cliente": ""}))
    _, [rfq] = srv.criar_pacote_com_rfqs(base_populada, pacote_exemplo, ["f1"])
    rfq = srv.registrar_envio(base_populada, rfq, Idioma.PT, "enviada", HOJE)
    fornecedor = base_populada.fornecedores.obter("f1")
    for idioma in Idioma:
        email = montar_email_agradecimento(base_populada, fornecedor, [rfq], idioma, "texto")
        assert "( )" not in email.html and "(cliente )" not in email.html and "(customer )" not in email.html
        assert "Projeto Alfa," in email.html
