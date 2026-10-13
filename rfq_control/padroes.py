"""Conteúdo inicial criado na primeira execução (modelos de e-mail) e textos padrão."""

from __future__ import annotations

from dataclasses import dataclass

from .modelos import Idioma, ModeloEmail, StatusRFQ, TipoModelo

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

# A cobrança vai como resposta ao e-mail da RFQ, que aparece logo abaixo (por isso não repete as tabelas).
CORPO_COBRANCA_PT = """Caro {{contato}},

Ainda não recebemos a sua cotação referente à {{rfq}}, cujo prazo de retorno era {{prazo}}.

Por gentileza, envie a sua proposta o quanto antes ou nos informe caso não seja possível cotar os itens da solicitação abaixo.

Ficamos no aguardo."""

CORPO_COBRANCA_ES = """Estimado/a {{contato}}:

Aún no hemos recibido su cotización referente a la {{rfq}}, cuyo plazo de respuesta era el {{prazo}}.

Le pedimos que envíe su propuesta lo antes posible o nos informe si no le es posible cotizar los ítems de la solicitud a continuación.

Quedamos atentos a su respuesta."""

CORPO_COBRANCA_EN = """Dear {{contato}},

We have not yet received your quotation for {{rfq}}, which was due on {{prazo}}.

Please send your proposal as soon as possible, or let us know if you are unable to quote the items in the request below.

We look forward to hearing from you."""

ASSUNTOS_AGRADECIMENTO = {
    Idioma.PT: "{{rfqs}} / Customer: {{cliente}} / Project: {{projeto}} – Agradecimento",
    Idioma.ES: "{{rfqs}} / Customer: {{cliente}} / Project: {{projeto}} – Agradecimiento",
    Idioma.EN: "{{rfqs}} / Customer: {{cliente}} / Project: {{projeto}} – Thank you",
}

CORPO_AGRADECIMENTO_PT = """Caro {{contato}},

Agradecemos a sua participação no processo de cotação do projeto {{projeto}} (cliente {{cliente}}), referente à(s) {{rfqs}}.

{{motivo}}

Agradecemos o tempo e a dedicação da sua equipe neste processo e contamos com a sua parceria em futuras oportunidades."""

CORPO_AGRADECIMENTO_ES = """Estimado/a {{contato}}:

Agradecemos su participación en el proceso de cotización del proyecto {{projeto}} (cliente {{cliente}}), referente a la(s) {{rfqs}}.

{{motivo}}

Agradecemos el tiempo y la dedicación de su equipo en este proceso y contamos con su colaboración en futuras oportunidades."""

CORPO_AGRADECIMENTO_EN = """Dear {{contato}},

Thank you for taking part in the quotation process for the project {{projeto}} (customer {{cliente}}), regarding {{rfqs}}.

{{motivo}}

We appreciate the time and effort your team dedicated to this process and look forward to working with you on future opportunities."""


@dataclass(frozen=True)
class MotivoAgradecimento:
    """Situação do projeto informada no e-mail de agradecimento ({{motivo}}), em cada idioma."""

    chave: str
    rotulo: str
    textos: dict[Idioma, str]
    status_sugerido: StatusRFQ | None = None  # status aplicado às RFQs depois do envio (opcional)


MOTIVOS_AGRADECIMENTO = [
    MotivoAgradecimento(
        "declinado", "Projeto declinado — não vamos seguir",
        {
            Idioma.PT: "Informamos que o projeto foi declinado e, por isso, não daremos continuidade a esta cotação.",
            Idioma.ES: "Le informamos que el proyecto fue declinado y, por ello, no daremos continuidad a esta "
                       "cotización.",
            Idioma.EN: "Please note that the project has been declined and, therefore, we will not proceed with "
                       "this quotation.",
        },
        StatusRFQ.CANCELADA,
    ),
    MotivoAgradecimento(
        "suspenso", "Projeto suspenso / em espera",
        {
            Idioma.PT: "Informamos que o projeto está suspenso no momento. Caso seja retomado, entraremos em contato.",
            Idioma.ES: "Le informamos que el proyecto está suspendido en este momento. Si se retoma, nos pondremos "
                       "en contacto.",
            Idioma.EN: "Please note that the project is currently on hold. Should it resume, we will get back to you.",
        },
    ),
    MotivoAgradecimento(
        "outra_proposta", "Seguiremos com outra proposta",
        {
            Idioma.PT: "Informamos que, nesta oportunidade, seguiremos com outra proposta.",
            Idioma.ES: "Le informamos que, en esta ocasión, continuaremos con otra propuesta.",
            Idioma.EN: "Please note that, on this occasion, we will proceed with another proposal.",
        },
        StatusRFQ.NAO_SELECIONADA,
    ),
    MotivoAgradecimento(
        "concluido", "Processo de cotação concluído",
        {
            Idioma.PT: "Informamos que o processo de cotação deste projeto foi concluído.",
            Idioma.ES: "Le informamos que el proceso de cotización de este proyecto ha concluido.",
            Idioma.EN: "Please note that the quotation process for this project has been completed.",
        },
    ),
    MotivoAgradecimento("outro", "Outro (texto livre)", {}),
]

# Textos padrão de versões anteriores: modelos ainda iguais a eles são atualizados ao abrir a base.
CORPOS_PADRAO_ANTIGOS = {
    (TipoModelo.COBRANCA, Idioma.PT): """Caro {{contato}},

Ainda não recebemos a sua cotação referente à {{rfq}}, cujo prazo de retorno era {{prazo}}.

Por gentileza, envie a sua proposta o quanto antes ou nos informe caso não seja possível cotar os itens abaixo.

{{tabela_itens}}

{{tabela_projeto}}

Ficamos no aguardo.""",
    (TipoModelo.COBRANCA, Idioma.ES): """Estimado/a {{contato}}:

Aún no hemos recibido su cotización referente a la {{rfq}}, cuyo plazo de respuesta era el {{prazo}}.

Le pedimos que envíe su propuesta lo antes posible o nos informe si no le es posible cotizar los ítems a continuación.

{{tabela_itens}}

{{tabela_projeto}}

Quedamos atentos a su respuesta.""",
    (TipoModelo.COBRANCA, Idioma.EN): """Dear {{contato}},

We have not yet received your quotation for {{rfq}}, which was due on {{prazo}}.

Please send your proposal as soon as possible, or let us know if you are unable to quote the items below.

{{tabela_itens}}

{{tabela_projeto}}

We look forward to hearing from you.""",
}

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
    "commodity": "Commodity do pacote",
    "prazo": "Prazo de resposta por extenso, no idioma do e-mail",
    "tabela_itens": "Tabela com os itens (em uma linha separada)",
    "tabela_projeto": "Quadro com planta, projeto e cliente (em uma linha separada)",
    "rfqs": "Agradecimento: números das RFQs do fornecedor no projeto",
    "motivo": "Agradecimento: situação do projeto escolhida no envio (ex.: projeto declinado)",
}


def modelos_email_padrao() -> list[ModeloEmail]:
    return [
        ModeloEmail(tipo=TipoModelo.RFQ, idioma=Idioma.PT, assunto=ASSUNTO_RFQ, corpo=CORPO_RFQ_PT),
        ModeloEmail(tipo=TipoModelo.RFQ, idioma=Idioma.ES, assunto=ASSUNTO_RFQ, corpo=CORPO_RFQ_ES),
        ModeloEmail(tipo=TipoModelo.RFQ, idioma=Idioma.EN, assunto=ASSUNTO_RFQ, corpo=CORPO_RFQ_EN),
        ModeloEmail(tipo=TipoModelo.COBRANCA, idioma=Idioma.PT, assunto=ASSUNTO_COBRANCA, corpo=CORPO_COBRANCA_PT),
        ModeloEmail(tipo=TipoModelo.COBRANCA, idioma=Idioma.ES, assunto=ASSUNTO_COBRANCA, corpo=CORPO_COBRANCA_ES),
        ModeloEmail(tipo=TipoModelo.COBRANCA, idioma=Idioma.EN, assunto=ASSUNTO_COBRANCA, corpo=CORPO_COBRANCA_EN),
        ModeloEmail(tipo=TipoModelo.AGRADECIMENTO, idioma=Idioma.PT, assunto=ASSUNTOS_AGRADECIMENTO[Idioma.PT],
                    corpo=CORPO_AGRADECIMENTO_PT),
        ModeloEmail(tipo=TipoModelo.AGRADECIMENTO, idioma=Idioma.ES, assunto=ASSUNTOS_AGRADECIMENTO[Idioma.ES],
                    corpo=CORPO_AGRADECIMENTO_ES),
        ModeloEmail(tipo=TipoModelo.AGRADECIMENTO, idioma=Idioma.EN, assunto=ASSUNTOS_AGRADECIMENTO[Idioma.EN],
                    corpo=CORPO_AGRADECIMENTO_EN),
    ]
