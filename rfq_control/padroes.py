"""Conteúdo inicial criado na primeira execução (modelos de e-mail)."""

from __future__ import annotations

from .modelos import Idioma, ModeloEmail, TipoModelo

ASSUNTO_RFQ = "{{rfq}} / Customer: {{cliente}} / Project: {{projeto}}"

CORPO_RFQ_PT = """Caro {{contato}},

A {{empresa}} está atualmente participando de um processo de cotação junto ao cliente final para um novo projeto.

Desta forma, solicitamos o envio da sua melhor proposta comercial para os itens abaixo, a fim de suportar a elaboração da nossa oferta ao cliente.

Esta solicitação refere-se exclusivamente à fase de cotação do projeto e não representa uma definição de fornecimento ou processo de sourcing neste momento.

{{tabela_itens}}

{{tabela_projeto}}

**Prazo para retorno: {{prazo}}**

NOTA: Favor enviar a cotação de acordo com as documentações enviadas, contemplando o CBD e lead time."""

CORPO_RFQ_ES = """Estimado/a {{contato}}:

{{empresa}} está participando actualmente en un proceso de cotización con el cliente final para un nuevo proyecto.

Por ello, solicitamos el envío de su mejor propuesta comercial para los ítems a continuación, con el fin de respaldar la elaboración de nuestra oferta al cliente.

Esta solicitud se refiere exclusivamente a la fase de cotización del proyecto y no representa una nominación de proveedor ni un proceso de sourcing en este momento.

{{tabela_itens}}

{{tabela_projeto}}

**Plazo de respuesta: {{prazo}}**

NOTA: Por favor, envíe la cotización de acuerdo con la documentación enviada, incluyendo el CBD y el lead time."""

CORPO_RFQ_EN = """Dear {{contato}},

{{empresa}} is currently participating in a quotation process with the final customer for a new project.

Therefore, we kindly request the submission of your best commercial proposal for the items below, in order to support the preparation of our offer to the customer.

This request refers exclusively to the project quotation phase and does not represent a supplier nomination or sourcing process at this stage.

{{tabela_itens}}

{{tabela_projeto}}

**Due date: {{prazo}}**

Note: Please submit your quotation in accordance with the provided documentation, including the CBD and lead time."""

ASSUNTO_COBRANCA = "Lembrete / Reminder: {{rfq}} / Customer: {{cliente}} / Project: {{projeto}}"

CORPO_COBRANCA_PT = """Caro {{contato}},

Ainda não recebemos a sua cotação referente à {{rfq}}, cujo prazo de retorno era {{prazo}}.

Por gentileza, envie a sua proposta o quanto antes ou nos informe caso não seja possível cotar os itens abaixo.

{{tabela_itens}}

{{tabela_projeto}}

Ficamos no aguardo."""

CORPO_COBRANCA_ES = """Estimado/a {{contato}}:

Aún no hemos recibido su cotización referente a la {{rfq}}, cuyo plazo de respuesta era el {{prazo}}.

Le pedimos que envíe su propuesta lo antes posible o nos informe si no le es posible cotizar los ítems a continuación.

{{tabela_itens}}

{{tabela_projeto}}

Quedamos atentos a su respuesta."""

CORPO_COBRANCA_EN = """Dear {{contato}},

We have not yet received your quotation for {{rfq}}, which was due on {{prazo}}.

Please send your proposal as soon as possible, or let us know if you are unable to quote the items below.

{{tabela_itens}}

{{tabela_projeto}}

We look forward to hearing from you."""

VARIAVEIS_MODELO = {
    "contato": "Nome do contato do fornecedor (ou \"fornecedor\"/\"supplier\")",
    "fornecedor": "Nome do fornecedor",
    "empresa": "Nome da empresa (Configurações)",
    "rfq": "Número da RFQ",
    "projeto": "Nome do projeto",
    "cliente": "Cliente do projeto",
    "planta": "Planta do projeto",
    "solicitante": "Nome do solicitante",
    "pacote": "Título do pacote de cotação",
    "prazo": "Prazo de resposta por extenso, no idioma do e-mail",
    "tabela_itens": "Tabela com os itens (em uma linha separada)",
    "tabela_projeto": "Tabela com planta, projeto e cliente (em uma linha separada)",
}


def modelos_email_padrao() -> list[ModeloEmail]:
    return [
        ModeloEmail(tipo=TipoModelo.RFQ, idioma=Idioma.PT, assunto=ASSUNTO_RFQ, corpo=CORPO_RFQ_PT),
        ModeloEmail(tipo=TipoModelo.RFQ, idioma=Idioma.ES, assunto=ASSUNTO_RFQ, corpo=CORPO_RFQ_ES),
        ModeloEmail(tipo=TipoModelo.RFQ, idioma=Idioma.EN, assunto=ASSUNTO_RFQ, corpo=CORPO_RFQ_EN),
        ModeloEmail(tipo=TipoModelo.COBRANCA, idioma=Idioma.PT, assunto=ASSUNTO_COBRANCA, corpo=CORPO_COBRANCA_PT),
        ModeloEmail(tipo=TipoModelo.COBRANCA, idioma=Idioma.ES, assunto=ASSUNTO_COBRANCA, corpo=CORPO_COBRANCA_ES),
        ModeloEmail(tipo=TipoModelo.COBRANCA, idioma=Idioma.EN, assunto=ASSUNTO_COBRANCA, corpo=CORPO_COBRANCA_EN),
    ]
