# RFQ Control

Aplicativo desktop para controlar as RFQs (*Request for Quotation*) enviadas a fornecedores na fase
de cotação de novos projetos. Substitui por completo a planilha `RFQ_Controle.xlsm` — fórmulas e
macros — sem travar, com tudo registrado e com mais recursos.

## O que ele faz

- **Base de dados com as antigas abas da planilha** (botão *Base de dados* no menu lateral): Controle,
  Fornecedores, Commodities, Projetos, Feriados, Condições e Corpo do E-mail — abas em cima, logo abaixo
  da descrição. Edite direto nas células (cada linha é salva sozinha; a linha atual fica destacada e a célula
  em edição ganha moldura azul), cole várias linhas do Excel com Ctrl+V, copie com Ctrl+C.
- **Excluir com o botão ou com a tecla Delete:** nas abas de cadastro, selecione as linhas pelo número à
  esquerda e tecle Delete (ou *Excluir linhas*) — com só algumas células selecionadas, Delete limpa as células,
  como no Excel. Na lista de **RFQs** e na aba **Controle**, selecione a linha e tecle Delete (ou *Excluir* /
  *Excluir RFQ*). Só RFQs em rascunho são apagadas; as já enviadas não podem ser excluídas (o número e o
  histórico do envio ficam guardados) e o app oferece marcá-las como **Cancelada**.
- **Commodities:** cada commodity tem o seu **Commodity Buyer** (nome e e-mail). Um fornecedor pode ter
  várias commodities. Nos e-mails, o buyer da commodity do pacote (ou das commodities do fornecedor) vai em
  cópia, junto com os **E-mails Supplier (Cc)** do fornecedor. A commodity **não depende de fornecedor**:
  cadastre na aba Commodities ou digite/cole o nome na aba Fornecedores (a que não existir é criada). Excluir
  uma commodity a retira dos fornecedores; só as usadas em pacotes ou condições ficam protegidas.
- **Idioma e região por fornecedor:** colunas *Idioma* (**Português, Espanhol ou Inglês** — o e-mail sai no
  idioma dele: texto, datas e tabela) e *Região* (país, ex.: Brasil). O projeto também tem *Região* (país da
  planta/cotação, ex.: Argentina). Siglas e nomes em PT/ES/EN viram o nome em português (BR, Brazil → Brasil).
- **Condições** (aba *Condições*): textos a mais no e-mail de RFQ conforme a commodity e as regiões. Quando
  todos os critérios preenchidos batem, o texto entra no fim do e-mail (depois do texto padrão, ou onde estiver
  `{{condicoes}}`), no idioma do fornecedor; nos outros casos o e-mail fica igual. Os textos em português,
  espanhol e inglês ficam na aba **Corpo do E-mail** (*Editar textos…*). Já vêm cadastradas:
  - **Moldes** — commodity Molde: pede Moldflow, frete para TO e embalagem para TO;
  - **Brasil → Argentina** — fornecedor do Brasil cotando projeto na Argentina: cotação em USD com
    certificado de origem.
- **Cadastro em massa:** em cada aba, *Importar Excel/CSV* cria ou atualiza os registros a partir de uma
  planilha (reconhece também os cabeçalhos da planilha antiga). *Baixar modelo* gera a planilha no
  formato certo, com a lista de idiomas e as sugestões de região. O modelo de fornecedores traz o
  **E-mail Commodity Buyer**, que preenche o e-mail das commodities que ainda não têm (um por commodity, na
  mesma ordem). Na aba Controle, a importação aceita a planilha antiga e o modelo de RFQs (as colunas são
  achadas pelo cabeçalho) — linhas **sem número de RFQ viram RFQs novas**, numeradas automaticamente.
- **Enviar e-mails** (botão no menu lateral): escolha a RFQ, marque os fornecedores que vão receber e envie —
  cada um recebe o e-mail padrão no seu idioma, com tabela de itens (com volume anual), quadro do projeto,
  prazo em destaque e anexos. Quem ainda não tem RFQ naquele pacote ganha um número novo na hora. Dá para
  **abrir no Outlook para revisar** (como a macro) ou **enviar automaticamente pelo Outlook**. Se o Outlook
  recusar o envio automático (proteção do Outlook ou política da empresa para programas que enviam e-mails),
  o e-mail fica aberto nele para você clicar em Enviar — a mensagem do app diz o motivo e a RFQ segue como na
  revisão (*Aguardando envio*).
- **Envio confirmado de verdade:** e-mail aberto para revisão deixa a RFQ em **Aguardando envio**; ela só
  passa a **Enviada** quando o e-mail aparece nos **Itens Enviados** do Outlook (o app confere ao abrir e ao
  voltar para ele e a cada 30 s enquanto houver pendentes) ou com *Confirmar envio*. Se o rascunho for
  apagado sem enviar, nada é registrado como enviado: use *E-mail não enviado* (ou Alterar status →
  Rascunho) para a RFQ voltar a rascunho.
- **Nova solicitação em um passo:** escolha o projeto e a commodity, cole os itens do Excel, anexe
  CDC/desenhos, marque os fornecedores (filtros por commodity, idioma e só marcados) → uma RFQ por fornecedor
  (`RFQ2026001`, `RFQ2026002`…) e a tela de envio já aberta.
- **Acompanhamento:** situação de cada RFQ (Rascunho, Aguardando envio, Enviada, **Atrasada**, Respondida,
  Declinada, Selecionada…), prazo gravado, valor cotado, lead time e histórico completo.
- **Cotação por item** (aba *Cotação* da RFQ): moeda e validade da proposta e, para cada item do pacote,
  **preço unitário, ferramental, lead time** (dias — ou "6 semanas"), **frete e embalagem por peça** — digitados
  ou colados do Excel (Ctrl+V). A primeira cotação de uma RFQ enviada a passa para **Respondida**.
- **Comparativo de propostas** (*Pacotes de cotação → Comparar propostas…*, ou na RFQ): fornecedores lado a
  lado, convertidos para a moeda do comparativo (câmbio informado na tela e guardado no pacote). Destaca em
  verde o menor custo unitário (preço + frete + embalagem), ferramental e lead time de cada item e, entre as
  propostas completas, o menor **custo das peças** (custo unitário × volume anual — ou quantidade), ferramental
  e lead time. Dali se escolhe a **vencedora** e se exporta o comparativo para Excel.
- **Cobrança na mesma conversa:** a cobrança **responde ao e-mail da RFQ** nos Itens Enviados do Outlook
  (sem o original, sai um "RE:" com a solicitação original citada).
- **Agradecimento / status do projeto:** escolha o projeto (ex.: declinado), todas as RFQs enviadas já vêm
  marcadas e cada fornecedor recebe um e-mail no seu idioma agradecendo e informando a situação — com opção
  de mudar o status das RFQs (ex.: Cancelada).
- **Painel:** RFQs em aberto, atrasadas, vencendo, taxa e tempo médio de resposta, RFQs por mês e o
  **scorecard dos fornecedores** — taxa de resposta, tempo médio, **pontualidade** (respostas até o prazo),
  **menor preço** (vezes com o menor custo das peças nos comparativos) e RFQs selecionadas.
- **Importação da planilha antiga** (menos de 1 segundo) e **exportação para Excel** (com a cotação por item).

## Estrutura

```
RFQ_Control\
├── RFQ_Control.exe        ← abra este
├── programa\              ← bibliotecas (não mexa)
└── dados\                 ← base de dados: um arquivo por "aba"
    ├── fornecedores.json  commodities.json  projetos.json  feriados.json  condicoes.json
    ├── modelos_email.json pacotes.json   rfqs.json          configuracoes.json
    └── anexos\  emails\  backup\  logs\
```

- Uma cópia de segurança de todos os arquivos é feita automaticamente **uma vez por dia** em `dados\backup`.
- Para **atualizar** o programa, substitua apenas `RFQ_Control.exe` e a pasta `programa`. **Nunca apague a pasta `dados`.**

## Como obter o executável

**Pelo GitHub (sem instalar nada):** a cada envio de código, o GitHub Actions roda os testes e gera o
executável no Windows. Em **Actions → Testes e executável → (última execução) → Artifacts**, baixe
`RFQ_Control-windows`, extraia para uma pasta (ex.: `Documentos\RFQ_Control`) e abra o `RFQ_Control.exe`.

**No seu computador** (requer [Python 3.11+](https://www.python.org/downloads/)): dê dois cliques em
`build.bat`. Ele cria o ambiente, instala as dependências e roda o PyInstaller; o resultado fica em
`dist\RFQ_Control\`. Rodar o build de novo **preserva** a pasta `dados` que estiver ali.

## Primeiros passos

1. Na primeira abertura, informe o nome da empresa (usado nos e-mails) e, se quiser, importe a planilha antiga.
2. Em **Base de dados → Commodities**, cadastre as commodities e o Commodity Buyer de cada uma.
3. Em **Base de dados → Fornecedores**, complete os e-mails (Para e Supplier Cc), as **commodities** e o
   **Idioma** de cada fornecedor — direto na tabela ou importando uma planilha (*Baixar modelo* mostra o formato).
4. Em **Configurações**, confira o método de e-mail (Outlook ou `.eml`), os e-mails sempre em cópia e o prazo padrão.
5. Crie RFQs em **+ Nova solicitação** (Ctrl+N) e dispare em **Enviar e-mails**.

Atalhos: `Ctrl+N` nova solicitação · `Ctrl+B` Base de dados · na lista de RFQs: `Ctrl+R` enviar e-mails
(escolher fornecedores) e `Ctrl+E` gerar o e-mail das RFQs selecionadas · `Ctrl+F` buscar · `Enter` abrir ·
`Delete` excluir as linhas selecionadas · `F5` atualizar.

## Desenvolvimento

```bash
pip install -r requirements-dev.txt
python main.py                        # executa o app (dados em ./dados, ignorada pelo Git)
QT_QPA_PLATFORM=offscreen pytest -q   # testes (regras, arquivos, importação, e-mail e telas)
python build.py                       # gera dist/RFQ_Control com PyInstaller + autoteste do .exe
```

| Pasta | Conteúdo |
|---|---|
| `rfq_control/modelos.py` | Modelos de dados (pydantic) |
| `rfq_control/armazenamento.py` | Arquivos JSON por coleção, gravação atômica, backup |
| `rfq_control/servicos/` | Regras: numeração, dias úteis, pacotes/RFQs, e-mail, envio, abas e cadastro em massa, importação, exportação |
| `rfq_control/ui/` | Telas (PySide6) |
| `tests/` | Testes automatizados (somente dados fictícios) |
| `docs/` | Análise da planilha legada e proposta do sistema |

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/01-analise-planilha-legado.md`](docs/01-analise-planilha-legado.md) | Estrutura da planilha antiga, fórmulas, macros VBA, regras de negócio, bugs e causas dos travamentos |
| [`docs/02-proposta-sistema.md`](docs/02-proposta-sistema.md) | Modelo de domínio, funcionalidades, arquitetura adotada e roadmap |

## Confidencialidade

A planilha original é classificada como **C2 – Confidential – Internal distribution**. Nem ela nem a
pasta `dados` são versionadas (estão no `.gitignore`); os testes usam apenas dados fictícios.
