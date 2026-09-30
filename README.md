# RFQ Control

Aplicativo desktop para controlar as RFQs (*Request for Quotation*) enviadas a fornecedores na fase
de cotação de novos projetos. Substitui por completo a planilha `RFQ_Controle.xlsm` — fórmulas e
macros — sem travar, com tudo registrado e com mais recursos.

## O que ele faz

- **Nova solicitação em um passo:** escolha o projeto, cole os itens do Excel (Ctrl+V), anexe CDC/desenhos,
  marque os fornecedores → o sistema cria **uma RFQ por fornecedor** com numeração automática
  (`RFQ2026001`, `RFQ2026002`…).
- **E-mail da RFQ em português ou inglês** (Ctrl+E / Ctrl+R, como na planilha): abre o rascunho no
  Outlook com destinatários, cópias, assunto, tabela de itens, dados do projeto, prazo em dias úteis
  (com feriados) e sua assinatura — pronto para revisar e enviar.
- **Acompanhamento:** situação de cada RFQ (Rascunho, Enviada, **Atrasada**, Respondida, Declinada,
  Selecionada…), prazo gravado, valor cotado, lead time, histórico completo e e-mail de cobrança.
- **Painel:** RFQs em aberto, atrasadas, vencendo, taxa e tempo médio de resposta, RFQs por mês e
  desempenho por fornecedor.
- **Pacotes de cotação:** o mesmo conjunto de itens enviado a vários fornecedores, com a comparação
  das respostas; enviar a mais fornecedores ou duplicar em um clique.
- **Cadastros editáveis no próprio app:** fornecedores (com vários contatos Para/Cópia e idioma),
  projetos, solicitantes, feriados (nacionais gerados automaticamente) e modelos de e-mail.
- **Importação da planilha antiga** (em menos de 1 segundo) e **exportação para Excel**.

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
2. Em **Fornecedores**, complete os e-mails dos contatos (Para e Cópia) — sem e-mail não há como gerar a RFQ.
3. Em **Configurações**, confira o método de e-mail (Outlook ou `.eml`), os e-mails sempre em cópia e o prazo padrão.
4. Use **+ Nova solicitação** (Ctrl+N) para criar pacotes e RFQs.

Atalhos: `Ctrl+N` nova solicitação · `Ctrl+E` / `Ctrl+R` e-mail PT / EN (lista de RFQs) · `Ctrl+F` buscar ·
`Enter` abrir · `F5` atualizar.

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
| `rfq_control/servicos/` | Regras: numeração, dias úteis, pacotes/RFQs, e-mail, importação, exportação |
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
