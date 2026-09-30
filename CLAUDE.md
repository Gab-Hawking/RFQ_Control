# CLAUDE.md

Contexto do projeto para sessões do Claude Code.

## Projeto

RFQ Control substitui a planilha `RFQ_Controle.xlsm` (controle de RFQs + macros VBA que geram
e-mails no Outlook) por uma aplicação completa. Antes de mexer no domínio, leia:

- `docs/01-analise-planilha-legado.md` — como a planilha funciona, regras de negócio (RN01–RN10) e bugs (B01–B14).
- `docs/02-proposta-sistema.md` — modelo de domínio, funcionalidades (F01–F07, N01–N13), arquitetura e roadmap.

## Conceitos de domínio

- **Pacote de cotação**: projeto + lista de itens + anexos. É o que se quer cotar.
- **Item**: referência OP (`ref_op`), referência do CDC — caderno de encargos (`ref_cdc`), descrição, unidade, quantidade, volume anual.
- **RFQ**: um pacote enviado a **um** fornecedor. Número `RFQ{AAAA}{NNN}` (ex.: `RFQ2026001`), sequencial por ano, gerado pelo sistema.
- **Prazo**: data de envio + 4 dias úteis (sem fins de semana e feriados).
- Na planilha, 1 linha = 1 item de uma RFQ; 225 RFQs equivalem a 63 pacotes (≈3,6 fornecedores por pacote).

## Convenções

- Idioma: interface, documentação e mensagens de commit em **português (PT-BR)**; e-mails para fornecedores em PT ou EN.
- Nunca versionar a planilha original nem dados reais extraídos dela (classificação C2). Use dados fictícios em seeds e testes.
- Segredos (SMTP, Graph, banco) apenas em variáveis de ambiente.
