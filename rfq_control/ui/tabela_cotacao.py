"""Cotação por item de uma RFQ: os itens do pacote com as colunas da resposta do fornecedor.

As colunas do item (referências, quantidade, volume) ficam em cinza e não são editáveis; preço,
ferramental, lead time, frete e embalagem são digitados ou colados do Excel (Ctrl+V a partir da
célula atual — colado numa coluna do item, começa no preço).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from ..modelos import CotacaoItem, Item
from ..servicos.formatos import ler_lead_time, ler_numero, numero_br, valor_monetario
from ..servicos.rfq import ErroNegocio
from . import estilo
from .componentes import DelegadoBase

# (campo, título, largura) — campos do item (somente leitura) e da cotação (editáveis)
COLUNAS_ITEM = [
    ("posicao", "#", 36),
    ("ref_op", "OP - Ref", 130),
    ("ref_cdc", "CDC - Ref", 140),
    ("descricao", "Descrição", 120),
    ("quantidade", "Qtd.", 70),
    ("volume_anual", "Volume anual", 100),
]
COLUNAS_COTACAO = [
    ("preco", "Preço unit.", 100),
    ("ferramental", "Ferramental", 110),
    ("lead_time_dias", "Lead time (dias)", 130),
    ("frete", "Frete / peça", 100),
    ("embalagem", "Embalagem / peça", 135),
]
_FUNDO_ITEM = QColor("#eef0f2")


class TabelaCotacao(QTableWidget):
    alterada = Signal()

    def __init__(self, pai=None):
        super().__init__(0, len(COLUNAS_ITEM) + len(COLUNAS_COTACAO), pai)
        colunas = COLUNAS_ITEM + COLUNAS_COTACAO
        self.setHorizontalHeaderLabels([titulo for _, titulo, _ in colunas])
        for indice, (_, _, largura) in enumerate(colunas):
            self.setColumnWidth(indice, largura)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(32)
        self.setItemDelegate(DelegadoBase(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._itens: list[Item] = []
        self._carregando = False
        self.itemChanged.connect(lambda _celula: None if self._carregando else self.alterada.emit())

    @property
    def primeira_editavel(self) -> int:
        return len(COLUNAS_ITEM)

    # ------------------------------------------------ dados
    def definir(self, itens: list[Item], cotacao: list[CotacaoItem]) -> None:
        self._carregando = True
        self._itens = list(itens)
        por_item = {c.item_id: c for c in cotacao}
        self.setRowCount(len(itens))
        for linha, item in enumerate(itens):
            valores_item = {
                "posicao": str(linha + 1), "ref_op": item.ref_op, "ref_cdc": item.ref_cdc,
                "descricao": item.descricao,
                "quantidade": " ".join(p for p in (numero_br(item.quantidade), item.unidade) if p),
                "volume_anual": numero_br(item.volume_medio()),  # com volumes por ano: a média
            }
            for coluna, (campo, _, _) in enumerate(COLUNAS_ITEM):
                celula = QTableWidgetItem(valores_item[campo])
                celula.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                celula.setBackground(_FUNDO_ITEM)
                celula.setForeground(QColor(estilo.TINTA_SECUNDARIA))
                if campo in ("posicao", "quantidade", "volume_anual"):
                    celula.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(linha, coluna, celula)
            cotacao_item = por_item.get(item.id)
            for deslocamento, (campo, _, _) in enumerate(COLUNAS_COTACAO):
                valor = getattr(cotacao_item, campo) if cotacao_item else None
                texto = str(valor) if campo == "lead_time_dias" and valor is not None else valor_monetario(valor)
                celula = QTableWidgetItem(texto)
                celula.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(linha, self.primeira_editavel + deslocamento, celula)
        self._carregando = False

    def cotacao(self) -> list[CotacaoItem]:
        """Lê as colunas editáveis; erro claro (linha e coluna) para valores inválidos."""
        resultado = []
        for linha, item in enumerate(self._itens):
            dados: dict = {"item_id": item.id}
            for deslocamento, (campo, titulo, _) in enumerate(COLUNAS_COTACAO):
                celula = self.item(linha, self.primeira_editavel + deslocamento)
                texto = celula.text().strip() if celula else ""
                try:
                    valor = ler_lead_time(texto) if campo == "lead_time_dias" else ler_numero(texto)
                except ValueError as erro:
                    raise ErroNegocio(f"Item {linha + 1}, {titulo}: {erro}") from erro
                if texto and valor is None:
                    raise ErroNegocio(f"Item {linha + 1}, {titulo}: '{texto}' não é um número válido.")
                if valor is not None and valor < 0:
                    raise ErroNegocio(f"Item {linha + 1}, {titulo}: o valor não pode ser negativo.")
                dados[campo] = valor
            cotacao = CotacaoItem(**dados)
            if not cotacao.vazia():
                resultado.append(cotacao)
        return resultado

    # ------------------------------------------------ teclado: colar e limpar
    def colar(self, texto: str | None = None) -> int:
        texto = QGuiApplication.clipboard().text() if texto is None else texto
        if not texto.strip() or not self._itens:
            return 0
        linhas = texto.replace("\r\n", "\n").rstrip("\n").split("\n")
        linha_inicial = max(self.currentRow(), 0)
        coluna_inicial = max(self.currentColumn(), self.primeira_editavel)
        coladas = 0
        for deslocamento, linha_texto in enumerate(linhas):
            destino = linha_inicial + deslocamento
            if destino >= self.rowCount():
                break  # os itens vêm do pacote: linhas a mais são ignoradas
            for passo, valor in enumerate(linha_texto.split("\t")):
                coluna = coluna_inicial + passo
                if coluna < self.columnCount():
                    self.item(destino, coluna).setText(valor.strip())
            coladas += 1
        return coladas

    def keyPressEvent(self, evento):  # noqa: N802
        if self.state() != QAbstractItemView.State.EditingState:
            if evento.matches(QKeySequence.StandardKey.Paste):
                self.colar()
                return
            if evento.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                for indice in self.selectedIndexes():
                    if indice.column() >= self.primeira_editavel:
                        self.item(indice.row(), indice.column()).setText("")
                return
        super().keyPressEvent(evento)
