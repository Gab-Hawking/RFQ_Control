# Proposta do novo sistema — RFQ Control

> Baseada na análise da planilha legada ([`01-analise-planilha-legado.md`](01-analise-planilha-legado.md)).
> Arquitetura e decisões confirmadas estão na §6; o que ainda falta decidir está na §8.

## 1. Objetivo

Substituir **por completo** a planilha `RFQ_Controle.xlsm` (fórmulas e macros) por uma aplicação
visual, automática e robusta, que:

- não trava com o crescimento da base;
- elimina digitação repetida (um pacote de itens → várias RFQs, uma por fornecedor);
- gera os e-mails de RFQ sem depender de macros;
- registra tudo o que acontece com cada RFQ (envio, prazo, resposta, cobrança, decisão);
- oferece indicadores, comparação de propostas e acompanhamento de prazos.

## 2. Princípios de projeto

1. **Banco de dados relacional como fonte única da verdade** — nada de fórmulas copiadas por
   milhões de linhas; cliente, planta, prazo, numeração e status são calculados pelo sistema.
2. **Operações atômicas** — uma ação ou acontece inteira ou não acontece; nunca deixa dados "pela metade"
   (ao contrário da macro, que deixa a planilha desprotegida/filtrada quando falha).
3. **Validação na entrada** — campos obrigatórios, listas controladas, espaços removidos,
   unidade separada de quantidade, sem duplicidades.
4. **Auditoria** — toda alteração registra quem, quando e o quê.
5. **Integração com o Outlook sem depender dele** — o e-mail é gerado pelo sistema; o Outlook é
   apenas um dos canais de envio.

## 3. Modelo de domínio

A principal mudança conceitual: a linha da planilha (item repetido por fornecedor) vira três
entidades — **Pacote de cotação** (o que se quer cotar), **Item** (o que está no pacote) e
**RFQ** (o pacote enviado a um fornecedor específico).

```mermaid
erDiagram
    PLANTA ||--o{ PROJETO : possui
    CLIENTE ||--o{ PROJETO : possui
    PROJETO ||--o{ PACOTE : "tem"
    USUARIO ||--o{ PACOTE : solicita
    PACOTE ||--|{ ITEM : contem
    PACOTE ||--o{ ANEXO : "CDC, desenhos"
    PACOTE ||--|{ RFQ : "gera 1 por fornecedor"
    FORNECEDOR ||--o{ RFQ : recebe
    FORNECEDOR ||--|{ CONTATO : tem
    RFQ ||--o{ RESPOSTA_ITEM : "cotação recebida"
    ITEM ||--o{ RESPOSTA_ITEM : "cotado em"
    RFQ ||--o{ EVENTO : historico
    FERIADO }o--o| PLANTA : "aplica-se a"

    PLANTA {
        string nome
        string cidade
        string pais
    }
    CLIENTE {
        string nome
    }
    PROJETO {
        string codigo
        string nome
        date sop
        int lifetime_anos
        bool ativo
    }
    USUARIO {
        string nome
        string email
        string papel
        text assinatura_html
    }
    FORNECEDOR {
        string nome
        string idioma_padrao
        string categorias
        bool ativo
    }
    CONTATO {
        string nome
        string email
        string tipo_to_cc
        bool principal
    }
    PACOTE {
        string titulo
        date data_criacao
        int prazo_dias_uteis
        string status
    }
    ITEM {
        string ref_op
        string ref_cdc
        string descricao
        string unidade
        decimal quantidade
        decimal volume_anual
    }
    RFQ {
        string numero
        date data_envio
        date prazo
        string idioma
        string status
    }
    RESPOSTA_ITEM {
        decimal preco
        string moeda
        int lead_time_dias
        bool capacidade_120
        decimal cobertura_pct
    }
    EVENTO {
        datetime quando
        string tipo
        string usuario
        text detalhes
    }
    FERIADO {
        date data
        string descricao
        string escopo
    }
    TEMPLATE_EMAIL {
        string idioma
        string assunto
        text corpo
    }
```

### 3.1 Ciclo de vida da RFQ

```mermaid
stateDiagram-v2
    [*] --> Rascunho
    Rascunho --> Enviada: e-mail gerado/enviado (grava data e prazo)
    Enviada --> Atrasada: prazo vencido sem resposta (automático)
    Atrasada --> Enviada: cobrança enviada / prazo prorrogado
    Enviada --> Respondida: cotação registrada
    Atrasada --> Respondida: cotação registrada
    Enviada --> Declinada: fornecedor não vai cotar
    Respondida --> Selecionada: escolhida no comparativo
    Respondida --> NaoSelecionada: outra proposta escolhida
    Rascunho --> Cancelada
    Enviada --> Cancelada
    Selecionada --> [*]
    NaoSelecionada --> [*]
    Declinada --> [*]
    Cancelada --> [*]
```

## 4. Funcionalidades

### 4.1 Paridade com a planilha (MVP)

| ID | Funcionalidade | Substitui |
|---|---|---|
| F01 | Cadastros: Plantas, Clientes, Projetos (SOP, lifetime), Fornecedores com N contatos (To/Cc) e idioma padrão, Usuários, Feriados, Templates de e-mail | Abas de cadastro |
| F02 | Lista de RFQs com filtros, busca, ordenação, agrupamento e paginação no servidor | Aba `Controle` + autofiltro |
| F03 | Criar pacote de cotação: projeto, itens (digitados, **colados do Excel** ou importados), anexos; selecionar 1..N fornecedores → gera N RFQs com numeração automática `RFQ{AAAA}{NNN}` sem duplicidade | Digitação linha a linha + número manual |
| F04 | Gerar e-mail por RFQ (PT/EN, padrão pelo idioma do fornecedor): assunto, saudação com nome do contato, tabela de itens, dados do projeto, prazo calculado com feriados e **formatado no idioma do e-mail**, nota CBD/lead time, assinatura do usuário — com **pré-visualização** | Macros Ctrl+E / Ctrl+R |
| F05 | Entregar o e-mail: (a) arquivo `.eml` de rascunho que abre no Outlook para revisão e envio, com anexos; (b) envio direto via Microsoft Graph/SMTP (fase 4) | `Outlook.Application` via COM |
| F06 | Importar a planilha atual: 1.114 itens → 63 pacotes / 225 RFQs, cadastros e feriados, com relatório de inconsistências (espaços, projeto inexistente, UM/QTY misturado, duplicidades) | — (migração) |
| F07 | Exportar listas e comparativos para Excel | Uso da própria planilha |

### 4.2 Novas mecânicas

| ID | Funcionalidade |
|---|---|
| N01 | **Status e ciclo de vida** da RFQ (§3.1), com data de envio e prazo gravados |
| N02 | **Registro da cotação recebida** por item: preço, moeda, lead time, ferramental, confirmação de capacidade 120% (S/N), cobertura máxima %, validade, anexos (proposta, CBD) |
| N03 | **Comparativo de propostas** por pacote (equalização): tabela lado a lado, destaque de menor preço/lead time, gráfico, escolha do vencedor, exportação |
| N04 | **Follow-up automático**: alerta antes do prazo, marcação de atraso e e-mail de cobrança pronto (template próprio) |
| N05 | **Dashboard**: RFQs abertas/atrasadas/respondidas, taxa e tempo médio de resposta, volume por mês/cliente/projeto/fornecedor, funil de status |
| N06 | **Scorecard de fornecedores**: taxa de resposta, pontualidade, competitividade, RFQs vencidas |
| N07 | **Linha do tempo** de cada RFQ (auditoria completa) |
| N08 | **Anexos por pacote** (CDC, desenhos) incluídos automaticamente nos e-mails |
| N09 | **Feriados automáticos** (nacionais BR/AR via API pública) + feriados locais por planta |
| N10 | **Duplicar pacote** / enviar o mesmo pacote para um novo fornecedor em 1 clique |
| N11 | **Volumes por ano** (EAU Y1…Yn conforme lifetime do projeto) — a intenção original da macro, opcional por pacote |
| N12 | **Login e perfis** (comprador, solicitante, leitura, admin); login corporativo Microsoft na fase 4 |
| N13 | **Leitura da caixa de entrada** (Graph): marca a RFQ como respondida quando chega e-mail com o número dela no assunto (fase 4) |

### 4.3 Templates de e-mail atuais (a migrar)

Variáveis: `{{empresa}}`, `{{contato}}`, `{{fornecedor}}`, `{{rfq}}`, `{{cliente}}`, `{{projeto}}`,
`{{planta}}`, `{{solicitante}}`, `{{pacote}}`, `{{prazo}}`, `{{tabela_itens}}`, `{{tabela_projeto}}`.
A assinatura é incluída automaticamente (a padrão do Outlook, ou a configurada para `.eml`).

**Assunto (ambos os idiomas):** `{{rfq}} / Customer: {{cliente}} / Project: {{projeto}}`

**Português**

> Caro {{contato}},
>
> A {{empresa}} está atualmente participando de um processo de cotação junto ao cliente final
> para um novo projeto.
>
> Desta forma, solicitamos o envio da sua melhor proposta comercial para os itens abaixo, a fim de
> suportar a elaboração da nossa oferta ao cliente.
>
> Esta solicitação refere-se exclusivamente à fase de cotação do projeto e não representa uma
> definição de fornecimento ou processo de sourcing neste momento.
>
> {{tabela_itens}} {{tabela_projeto}}
>
> **Prazo para retorno {{prazo}}**
>
> NOTA: Favor enviar a cotação de acordo com as documentações enviadas, contemplando o CBD e lead time.
>
> *(assinatura)*

**Inglês**

> Dear {{contato}},
>
> {{empresa}} is currently participating in a quotation process with the final customer for a new
> project. Therefore, we kindly request the submission of your best commercial proposal for the
> items below, in order to support the preparation of our offer to the customer.
>
> This request refers exclusively to the project quotation phase and does not represent a supplier
> nomination or sourcing process at this stage.
>
> {{tabela_itens}} {{tabela_projeto}}
>
> **Due date {{prazo}}**
>
> Note: Please submit your quotation in accordance with the provided documentation, including the
> CBD and lead time.
>
> *(assinatura)*

Correções já embutidas em relação à macro: saudação com o nome real do contato, Cc do fornecedor
+ comprador, planta correta, prazo formatado no idioma do e-mail e gravado na RFQ, parágrafos
preservados, HTML válido, colunas de descrição/volume/capacidade incluídas quando preenchidas.

## 5. Requisitos não funcionais

| Tema | Requisito |
|---|---|
| Desempenho | Listas paginadas e filtradas no servidor com índices; resposta < 1 s com 100 mil itens |
| Robustez | Transações no banco, validação de esquema na entrada, tratamento de erros com mensagem clara, logs |
| Qualidade | Testes automatizados (unidade, integração e ponta a ponta) e CI no GitHub Actions |
| Dados | Migrações versionadas, backup automático, exportação a qualquer momento |
| Segurança | Autenticação, perfis de acesso, segredos em variáveis de ambiente (nunca no código), dados C2 fora do Git |
| Usabilidade | Interface em PT-BR (e-mails PT/EN), responsiva, atalhos de teclado, tema claro/escuro |
| Multiusuário | Acesso simultâneo sem conflito de arquivo |

## 6. Arquitetura adotada

Decisões confirmadas (30/09/2026): uso **local**, **um usuário**, **Python**, e-mail como
**rascunho no Outlook**, executável gerado **sempre com PyInstaller** e dados em uma pasta com
**um arquivo por "aba"**, editáveis pelo próprio aplicativo.

| Camada | Tecnologia |
|---|---|
| Interface | PySide6 (Qt 6 Widgets) — aplicativo desktop nativo, sem navegador nem servidor |
| Regras de negócio | Python 3.11+ (`rfq_control/servicos`), independentes da interface e testadas |
| Dados | Um arquivo JSON por coleção na pasta `dados`, validado com pydantic; gravação atômica e backup diário |
| E-mail | Outlook da área de trabalho via automação (pywin32), como a macro; alternativa `.eml` (rascunho) |
| Excel | Leitor próprio em streaming para importar a planilha antiga · openpyxl para exportar |
| Executável | PyInstaller (modo pasta) com as bibliotecas em `programa/` |
| Testes / CI | pytest (inclusive telas, com Qt offscreen) · GitHub Actions gera o `.exe` no Windows |

Estrutura instalada:

```
RFQ_Control\
├── RFQ_Control.exe
├── programa\            ← bibliotecas (PyInstaller, contents_directory)
└── dados\
    ├── configuracoes.json
    ├── fornecedores.json   (antiga aba CadastroContatos)
    ├── projetos.json       (antiga aba CadastroProjetos)
    ├── solicitantes.json
    ├── feriados.json       (antiga aba Feriados)
    ├── modelos_email.json  (antiga aba CorpoEmail)
    ├── pacotes.json        (pacotes de cotação e itens)
    ├── rfqs.json           (antiga aba Controle)
    ├── anexos\  emails\  backup\  logs\
```

```mermaid
flowchart LR
    U[Usuário] --> UI[Telas PySide6]
    UI --> SRV[Serviços<br/>regras de negócio]
    SRV --> DADOS[(dados/*.json<br/>um arquivo por aba)]
    SRV --> OL[Outlook<br/>rascunho para revisão]
    SRV -. alternativa .-> EML[arquivo .eml]
    SRV --> XLSX[Exportação Excel]
    XL[RFQ_Controle.xlsm] -- importação --> SRV
```

Por que JSON e não um banco único: cada coleção fica em um arquivo legível, fácil de copiar e de
restaurar, como as abas da planilha — e o volume (milhares de registros) é pequeno para isso. As
gravações são atômicas (arquivo temporário + substituição), então o arquivo nunca fica pela metade.

## 7. Roadmap

| Fase | Entregas | Situação |
|---|---|---|
| **0 — Fundação** | Estrutura do projeto, modelo de dados, importador da planilha com relatório, testes, CI, executável | ✅ v0.1.0 |
| **1 — Paridade** | Cadastros, lista de RFQs, pacote → N RFQs, e-mail PT/EN (Outlook/.eml), feriados, exportação Excel | ✅ v0.1.0 |
| **2 — Acompanhamento** | Status, resposta (valor, moeda, lead time), atrasos automáticos, cobrança, painel | ✅ v0.1.0 (resposta no nível da RFQ) |
| **2.5 — Base de dados e envio** | Tela com as antigas abas (edição tipo planilha), idioma Espanhol, cadastro em massa por Excel/CSV, RFQs novas a partir de planilha, envio de e-mails escolhendo RFQ e fornecedores (revisão ou envio automático) | ✅ v0.2.0 |
| **3 — Análise** | Cotação por item (N02), comparativo lado a lado (N03), scorecard detalhado, volumes por ano (N11) | Próxima |
| **4 — Integrações** | Leitura automática de respostas no Outlook (N13), lembretes automáticos | Futuro |

A planilha pode ser aposentada a partir da v0.1.0: importe o `.xlsm` em **Configurações →
Importar planilha antiga** e complete os e-mails dos fornecedores.

## 8. Decisões pendentes

1. **Resposta do fornecedor por item:** quais campos registrar na Fase 3 (preço unitário,
   ferramental, frete, validade, capacidade 120%, cobertura)?
2. **Feriados locais:** quais feriados municipais/estaduais das plantas devem ser cadastrados
   (os nacionais do Brasil são gerados automaticamente)?
