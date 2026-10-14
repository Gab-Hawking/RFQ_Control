# CLAUDE.md

Contexto do projeto para sessões do Claude Code.

## Projeto

RFQ Control substitui a planilha `RFQ_Controle.xlsm` (controle de RFQs + macros VBA que geram
e-mails no Outlook) por um aplicativo desktop. Antes de mexer no domínio, leia:

- `docs/01-analise-planilha-legado.md` — como a planilha funciona, regras de negócio (RN01–RN10) e bugs (B01–B14).
- `docs/02-proposta-sistema.md` — modelo de domínio, funcionalidades (F01–F07, N01–N13), arquitetura adotada e roadmap.

## Decisões do usuário (não reabrir sem pedido)

- Uso **local**, por **uma pessoa**; linguagem **Python**; interface **PySide6**.
- Dados em uma pasta `dados/` com **um arquivo por coleção** (como as abas da planilha), editáveis pelo app.
- Distribuição: `RFQ_Control.exe` + `programa/` + `dados/`, gerada **sempre com PyInstaller** (`python build.py`).
- E-mail: rascunho aberto no Outlook para revisão (automação COM, como a macro), com `.eml` como alternativa.

## Comandos

```bash
pip install -r requirements-dev.txt
python main.py                          # roda o app (dados em ./dados)
QT_QPA_PLATFORM=offscreen pytest -q     # todos os testes, inclusive as telas
python build.py                         # PyInstaller + autoteste do executável (--verificar)
```

O CI (`.github/workflows/build.yml`) roda os testes no Linux e no Windows e publica o artefato
`RFQ_Control-windows` com o `.exe`.

## Arquitetura

- `rfq_control/modelos.py` — modelos pydantic. Enums de status/idioma são `str`: o Qt devolve
  `currentData()` como texto simples, então sempre passe valores de combos por `model_validate`
  (ou `StatusRFQ(...)`/`Idioma(...)`) — nunca por `model_copy(update=...)`.
- `rfq_control/armazenamento.py` — `BaseDados` com uma `Colecao` por arquivo JSON; gravação atômica,
  validação ao carregar, backup diário em `dados/backup`.
- `rfq_control/servicos/` — regras sem interface (testáveis): `rfq.py` (numeração, pacotes, status,
  envio/revisão/confirmação, indicadores), `email_rfq.py` (montagem e visual do e-mail, destinatários com
  Commodity Buyer), `envio_email.py` (Outlook/.eml, revisão ou envio direto — se o Outlook recusar o `Send()`, o e-mail
  fica aberto e a RFQ segue como na revisão (`EnvioNaoAutomatico`); erros COM explicados em
  `explicar_erro_outlook` —, busca nos Itens Enviados, cobrança como resposta), `disparo.py` (escolher RFQ + fornecedores e enviar), `agradecimento.py`
  (e-mail de agradecimento / status do projeto, um por fornecedor), `abas.py` (colunas das abas da Base de dados,
  conversão linha ↔ registro, importação em massa Excel/CSV, modelos), `importacao_legado.py` (aba Controle;
  linhas sem número viram RFQs novas), `leitor_xlsx.py` (streaming), `exportacao.py`, `cadastros.py`,
  `dias_uteis.py`, `formatos.py`.
- `rfq_control/ui/` — telas; erros de negócio viram mensagem via `componentes.executar`. A tela
  `pagina_base_dados.py` mostra as antigas abas da planilha; as de cadastro usam a grade editável de
  `grade.py`, guiada pelas definições de `servicos/abas.py` (para mudar colunas, mude lá; colunas
  `somente_leitura` são calculadas e `multilista` abre uma lista para marcar). O tema fica em `estilo.py`
  (fundo cinza `#7A7A7A`, escuro `#2E2E2E`, azul de destaque); editores de célula usam o nome `editorCelula`.
- Testes da automação do Outlook usam `tests/outlook_falso.py` (substitui `envio_email._conectar_outlook`).

## Conceitos de domínio

- **Pacote de cotação**: projeto + lista de itens + anexos. É o que se quer cotar.
- **Item**: referência OP (`ref_op`), referência do CDC — caderno de encargos (`ref_cdc`), descrição, unidade, quantidade, volume anual.
- **RFQ**: um pacote enviado a **um** fornecedor. Número `RFQ{AAAA}{NNN}` (ex.: `RFQ2026001`), sequencial por ano, gerado pelo sistema.
- **Prazo**: data de envio + 4 dias úteis (sem fins de semana e feriados); vai escrito no e-mail e fica gravado na RFQ quando o envio é confirmado.
- **Atrasada** não é status gravado: é a situação calculada de uma RFQ `Enviada` com prazo vencido.
- **Aguardando envio** também é situação calculada: RFQ em `Rascunho` cujo e-mail foi aberto para revisão
  (`aguardando_envio_desde`). Só vira `Enviada` quando o e-mail aparece nos Itens Enviados do Outlook ou o
  usuário confirma; se o rascunho do e-mail for apagado, nada vira Enviada e o usuário a devolve para
  `Rascunho` ("E-mail não enviado" / Alterar status → Rascunho, que limpa o prazo proposto). Não pode ser
  excluída enquanto estiver aguardando. Cobrança/agradecimento usam o prazo e o idioma gravados.
- **Commodity**: família de itens com um **Commodity Buyer** (comprador da OP), que vai em cópia nos e-mails.
  Fornecedor tem várias commodities; pacote tem uma (opcional). Cc = Supplier Cc + buyer + cópia padrão.
- **Idioma** (Português, Espanhol, Inglês) é do fornecedor; RFQs em rascunho acompanham o idioma dele,
  RFQs já enviadas guardam o idioma em que foram enviadas.

## Convenções

- Idioma: código de domínio, interface, documentação e mensagens de commit em **português (PT-BR)**; e-mails para fornecedores em PT, ES ou EN.
- Nunca versionar a planilha original nem dados reais extraídos dela (classificação C2). Use dados fictícios em seeds e testes.
- Segredos, se um dia existirem, apenas em variáveis de ambiente.
