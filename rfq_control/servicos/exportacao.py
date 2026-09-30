"""Exportação das RFQs para Excel (.xlsx)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..armazenamento import BaseDados
from ..modelos import RFQ

_CABECALHO = Font(bold=True, color="FFFFFF")
_FUNDO = PatternFill("solid", fgColor="1F4E79")


def _formatar_aba(aba, larguras: list[int]) -> None:
    for celula in aba[1]:
        celula.font = _CABECALHO
        celula.fill = _FUNDO
        celula.alignment = Alignment(vertical="center", wrap_text=True)
    for indice, largura in enumerate(larguras, start=1):
        aba.column_dimensions[get_column_letter(indice)].width = largura
    aba.freeze_panes = "A2"
    if aba.max_row > 1:
        aba.auto_filter.ref = aba.dimensions


def exportar_rfqs(base: BaseDados, destino: Path, rfqs: list[RFQ] | None = None, hoje: date | None = None) -> Path:
    rfqs = sorted(rfqs if rfqs is not None else base.rfqs.todos(), key=lambda r: r.numero)
    livro = Workbook()
    aba_rfqs = livro.active
    aba_rfqs.title = "RFQs"
    aba_rfqs.append([
        "RFQ Nº", "Situação", "Data de envio", "Prazo", "Data da resposta", "Projeto", "Cliente", "Planta",
        "Fornecedor", "Idioma", "Solicitante", "Pacote", "Nº de itens", "Valor total", "Moeda", "Lead time",
        "Observações",
    ])
    aba_itens = livro.create_sheet("Itens")
    aba_itens.append([
        "RFQ Nº", "Data de envio", "Solicitante", "Cliente", "Projeto", "Fornecedor", "OP - Ref", "CDC - Ref",
        "Descrição", "Unidade", "Quantidade", "Volume anual", "Situação",
    ])

    for rfq in rfqs:
        pacote = base.pacotes.obter(rfq.pacote_id)
        projeto = base.projeto_do_pacote(pacote)
        fornecedor = base.fornecedores.obter(rfq.fornecedor_id)
        solicitante = base.solicitantes.obter(pacote.solicitante_id) if pacote else None
        situacao = rfq.situacao(hoje)
        nome_projeto = projeto.nome if projeto else ""
        cliente = projeto.cliente if projeto else ""
        nome_fornecedor = fornecedor.nome if fornecedor else ""
        nome_solicitante = solicitante.nome if solicitante else ""
        aba_rfqs.append([
            rfq.numero, situacao, rfq.data_envio, rfq.prazo, rfq.data_resposta, nome_projeto, cliente,
            projeto.planta if projeto else "", nome_fornecedor, rfq.idioma.value, nome_solicitante,
            pacote.titulo if pacote else "", len(pacote.itens) if pacote else 0, rfq.valor_total, rfq.moeda,
            rfq.lead_time, rfq.observacoes,
        ])
        for item in pacote.itens if pacote else []:
            aba_itens.append([
                rfq.numero, rfq.data_envio, nome_solicitante, cliente, nome_projeto, nome_fornecedor,
                item.ref_op, item.ref_cdc, item.descricao, item.unidade, item.quantidade, item.volume_anual,
                situacao,
            ])

    for aba, colunas in ((aba_rfqs, "CDE"), (aba_itens, "B")):
        for coluna in colunas:
            for celula in aba[coluna][1:]:
                celula.number_format = "DD/MM/YYYY"
    for celula in aba_rfqs["N"][1:]:
        celula.number_format = "#,##0.00"
    for coluna in "KL":
        for celula in aba_itens[coluna][1:]:
            celula.number_format = "#,##0.##"

    _formatar_aba(aba_rfqs, [14, 15, 13, 13, 13, 28, 16, 18, 30, 8, 18, 34, 10, 14, 8, 14, 40])
    _formatar_aba(aba_itens, [14, 13, 18, 16, 28, 30, 36, 44, 30, 10, 13, 14, 15])
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    livro.save(destino)
    return destino
