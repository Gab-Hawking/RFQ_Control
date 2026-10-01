# RFQ Control

Aplicativo desktop para controlar as RFQs (*Request for Quotation*) enviadas a fornecedores na fase
de cotação de novos projetos. Substitui por completo a planilha `RFQ_Controle.xlsm` — fórmulas e
macros — sem travar, com tudo registrado e com mais recursos.

## O que ele faz

- **Base de dados com as antigas abas da planilha** (botão *Base de dados* no menu lateral): Controle,
  Cadastro de Fornecedores, Cadastro de Projetos, Solicitantes, Feriados e Corpo do E-mail — abas embaixo,
  como no Excel. Edite direto nas células (cada linha é salva sozinha), cole várias linhas do Excel com
  Ctrl+V, copie com Ctrl+C.
- **Idioma por fornecedor:** coluna *Idioma* no cadastro de fornecedores — **Português, Espanhol ou Inglês**.
  O e-mail de cada fornecedor sai no idioma dele (texto, datas e tabela).
- **Cadastro em massa:** em cada aba, *Importar Excel/CSV* cria ou atualiza os registros a partir de uma
  planilha (reconhece também os cabeçalhos da planilha antiga). *Baixar modelo* gera a planilha no
  formato certo, com a lista de idiomas. Na aba Controle, a importação aceita a planilha antiga e o modelo
  de RFQs — linhas **sem número de RFQ viram RFQs novas**, numeradas automaticamente.
- **Enviar e-mails** (botão no menu lateral): escolha a RFQ, marque os fornecedores que vão receber e envie —
  cada um recebe o e-mail padrão no seu idioma, com itens, dados do projeto, prazo e anexos. Quem ainda não
  tem RFQ naquele pacote ganha um número novo na hora. Dá para **abrir no Outlook para revisar** (como a
  macro) ou **enviar automaticamente pelo Outlook**.
- **Nova solicitação em um passo:** escolha o projeto, cole os itens do Excel, anexe CDC/desenhos, marque os
  fornecedores → uma RFQ por fornecedor (`RFQ2026001`, `RFQ2026002`…) e a tela de envio já aberta.
- **Acompanhamento:** situação de cada RFQ (Rascunho, Enviada, **Atrasada**, Respondida, Declinada,
  Selecionada…), prazo gravado, valor cotado, lead time, histórico completo e e-mail de cobrança.
- **Painel:** RFQs em aberto, atrasadas, vencendo, taxa e tempo médio de resposta, RFQs por mês e
  desempenho por fornecedor.
- **Importação da planilha antiga** (menos de 1 segundo) e **exportação para Excel**.

## Estrutura

```
RFQ_Control\
├── RFQ_Control.exe        ← abra este
├── programa\              ← bibliotecas (não mexa)
└── dados\                 ← base de dados: um arquivo por "aba"
    ├── fornecedores.json  projetos.json  solicitantes.json  feriados.json
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
2. Em **Base de dados → Cadastro de Fornecedores**, complete os e-mails (Para e Cc) e o **Idioma** de cada
   fornecedor — direto na tabela ou importando uma planilha (*Baixar modelo* mostra o formato).
3. Em **Configurações**, confira o método de e-mail (Outlook ou `.eml`), os e-mails sempre em cópia e o prazo padrão.
4. Crie RFQs em **+ Nova solicitação** (Ctrl+N) e dispare em **Enviar e-mails**.

Atalhos: `Ctrl+N` nova solicitação · `Ctrl+B` Base de dados · na lista de RFQs: `Ctrl+R` enviar e-mails
(escolher fornecedores) e `Ctrl+E` gerar o e-mail das RFQs selecionadas · `Ctrl+F` buscar · `Enter` abrir ·
`F5` atualizar.

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
