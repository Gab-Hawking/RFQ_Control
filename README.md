# RFQ Control

Sistema para controle de RFQs (*Request for Quotation*) enviadas a fornecedores na fase de
cotação de novos projetos. Substitui por completo a planilha `RFQ_Controle.xlsm` — suas fórmulas
e macros — por uma aplicação visual, automática e robusta.

## O que o sistema vai fazer

- Cadastros de plantas, clientes, projetos, fornecedores (com contatos), usuários, feriados e templates de e-mail.
- Criar um **pacote de cotação** (projeto + itens + anexos) e gerar automaticamente **uma RFQ por fornecedor**, com numeração sequencial.
- Gerar o e-mail de RFQ em português ou inglês (itens, dados do projeto, prazo em dias úteis com feriados, assinatura) e abri-lo no Outlook.
- Acompanhar o ciclo de vida de cada RFQ: envio, prazo, atraso, cobrança, resposta, decisão.
- Registrar as cotações recebidas, comparar propostas e acompanhar indicadores em um dashboard.

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/01-analise-planilha-legado.md`](docs/01-analise-planilha-legado.md) | Estrutura da planilha atual, fórmulas, macros VBA, regras de negócio, bugs e causas dos travamentos |
| [`docs/02-proposta-sistema.md`](docs/02-proposta-sistema.md) | Modelo de domínio, funcionalidades, arquitetura recomendada, roadmap e decisões em aberto |

## Status

Fase de contextualização concluída. Próximo passo: confirmar as decisões em aberto
([proposta §8](docs/02-proposta-sistema.md#8-decisões-em-aberto)) e iniciar a Fase 0 (fundação + importador da planilha).

## Confidencialidade

A planilha original é classificada como **C2 – Confidential – Internal distribution** e **não deve
ser versionada** neste repositório (arquivos Excel estão no `.gitignore`).
