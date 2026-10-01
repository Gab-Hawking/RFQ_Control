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
    assert "Confirma capacidade de 120%" in email.html
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

    rfq = resultado.rfq
    assert rfq.status == StatusRFQ.ENVIADA
    assert rfq.data_envio == HOJE and rfq.prazo == date(2026, 10, 6)
    assert "E-mail de RFQ aberto para revisão (arquivo .eml)" in rfq.historico[-1].descricao


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
    monkeypatch.setattr(envio_email, "abrir_no_outlook", lambda _: None)
    enviada = envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE).rfq
    cobranca = envio_email.gerar_email_rfq(
        base_populada, rfqs[0].id, tipo=TipoModelo.COBRANCA, hoje=date(2026, 10, 8)
    )
    assert cobranca.rfq.prazo == enviada.prazo
    assert "Ainda não recebemos" in cobranca.email.html
    assert "cobrança" in cobranca.rfq.historico[-1].descricao


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
    envio_email.gerar_email_rfq(base_populada, rfqs[0].id, hoje=HOJE)  # PT
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
