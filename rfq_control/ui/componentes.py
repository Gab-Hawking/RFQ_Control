"""Componentes reutilizáveis da interface."""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QModelIndex,
    QPoint,
    QRectF,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from pydantic import ValidationError

from ..armazenamento import ErroDados
from ..servicos.formatos import data_curta
from ..servicos.leitor_xlsx import ErroPlanilha
from ..servicos.rfq import ErroNegocio
from . import estilo

log = logging.getLogger(__name__)

PAPEL_ORDEM = Qt.ItemDataRole.UserRole + 1
PAPEL_OBJETO = Qt.ItemDataRole.UserRole + 2


# ---------------------------------------------------------------- mensagens


def informar(pai: QWidget | None, texto: str, titulo: str = "RFQ Control") -> None:
    QMessageBox.information(pai, titulo, texto)


def avisar(pai: QWidget | None, texto: str, titulo: str = "Atenção") -> None:
    QMessageBox.warning(pai, titulo, texto)


def erro(pai: QWidget | None, texto: str, titulo: str = "Erro") -> None:
    QMessageBox.critical(pai, titulo, texto)


def confirmar(pai: QWidget | None, texto: str, titulo: str = "Confirmar", botao_sim: str = "Sim") -> bool:
    caixa = QMessageBox(QMessageBox.Icon.Question, titulo, texto, parent=pai)
    sim = caixa.addButton(botao_sim, QMessageBox.ButtonRole.AcceptRole)
    caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    caixa.exec()
    return caixa.clickedButton() is sim


def mensagem_validacao(problema: ValidationError) -> str:
    partes = []
    for detalhe in problema.errors()[:5]:
        local = ".".join(str(p) for p in detalhe.get("loc", ()))
        texto = str(detalhe.get("msg", "")).replace("Value error, ", "")
        partes.append(f"{local}: {texto}" if local else texto)
    return "Verifique os dados:\n" + "\n".join(partes)


def executar(pai: QWidget | None, funcao: Callable[[], Any]) -> tuple[bool, Any]:
    """Executa uma ação mostrando erros de negócio/dados como mensagem (sem travar o app)."""
    try:
        return True, funcao()
    except (ErroNegocio, ErroDados, ErroPlanilha) as problema:
        avisar(pai, str(problema))
    except ValidationError as problema:
        avisar(pai, mensagem_validacao(problema))
    except Exception as problema:  # noqa: BLE001 - qualquer falha inesperada vira mensagem
        log.exception("Erro inesperado")
        erro(pai, f"Ocorreu um erro inesperado:\n{problema}\n\nDetalhes foram gravados em dados/logs.")
    return False, None


def mostrar_resultado(
    pai: QWidget | None,
    titulo: str,
    resumo: str,
    titulo_lista: str,
    itens: list[str],
    pasta_backup=None,
) -> None:
    """Janela de resultado (importação, envio de e-mails…) com resumo e lista de detalhes."""
    dialogo = QDialog(pai)
    dialogo.setWindowTitle(titulo)
    dialogo.resize(720, 520)
    layout = QVBoxLayout(dialogo)
    cabecalho = QLabel(titulo)
    cabecalho.setObjectName("tituloPagina")
    layout.addWidget(cabecalho)
    texto_resumo = QLabel(resumo)
    texto_resumo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(texto_resumo)
    if pasta_backup:
        dica = QLabel(f"Cópia de segurança anterior: {pasta_backup}")
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        layout.addWidget(dica)
    rotulo = QLabel(f"{titulo_lista} ({len(itens)})")
    rotulo.setObjectName("tituloSecao")
    layout.addWidget(rotulo)
    detalhes = QPlainTextEdit("\n".join(f"• {item}" for item in itens) or "Nenhum.")
    detalhes.setReadOnly(True)
    layout.addWidget(detalhes, 1)
    linha = QHBoxLayout()
    linha.addStretch()
    linha.addWidget(botao("Fechar", dialogo.accept, primario=True))
    layout.addLayout(linha)
    dialogo.exec()


def botao(texto: str, ao_clicar: Callable | None = None, primario: bool = False, perigo: bool = False,
          dica: str = "") -> QPushButton:
    b = QPushButton(texto)
    if primario:
        b.setProperty("primario", True)
    if perigo:
        b.setProperty("perigo", True)
    if dica:
        b.setToolTip(dica)
    if ao_clicar:
        b.clicked.connect(ao_clicar)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def cabecalho_pagina(titulo: str, subtitulo: str = "") -> QWidget:
    caixa = QWidget()
    layout = QVBoxLayout(caixa)
    layout.setContentsMargins(0, 0, 0, 4)
    layout.setSpacing(2)
    rotulo = QLabel(titulo)
    rotulo.setObjectName("tituloPagina")
    layout.addWidget(rotulo)
    if subtitulo:
        sub = QLabel(subtitulo)
        sub.setObjectName("subtitulo")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    return caixa


def sem_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(c) != "Mn"
    )


# ---------------------------------------------------------------- tabela


@dataclass
class Coluna:
    titulo: str
    valor: Callable[[Any], Any]
    largura: int | None = None
    alinhamento: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft
    formato: Callable[[Any], str] | None = None
    dica: Callable[[Any], str] | None = None
    esticar: bool = False


def _texto_padrao(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, date):
        return data_curta(valor)
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, float):
        return f"{valor:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return str(valor)


class ModeloTabela(QAbstractTableModel):
    def __init__(self, colunas: list[Coluna], pai=None):
        super().__init__(pai)
        self.colunas = colunas
        self.linhas: list[Any] = []
        self._cache: list[list[Any]] = []

    def definir(self, objetos: list[Any]) -> None:
        self.beginResetModel()
        self.linhas = list(objetos)
        self._cache = [[c.valor(o) for c in self.colunas] for o in self.linhas]
        self.endResetModel()

    def objeto(self, linha: int) -> Any:
        return self.linhas[linha]

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - API Qt
        return 0 if parent.isValid() else len(self.linhas)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.colunas)

    def headerData(self, secao, orientacao, papel=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientacao == Qt.Orientation.Horizontal and papel == Qt.ItemDataRole.DisplayRole:
            return self.colunas[secao].titulo
        return None

    def data(self, indice: QModelIndex, papel=Qt.ItemDataRole.DisplayRole):
        if not indice.isValid():
            return None
        coluna = self.colunas[indice.column()]
        valor = self._cache[indice.row()][indice.column()]
        if papel == Qt.ItemDataRole.DisplayRole:
            return coluna.formato(valor) if coluna.formato else _texto_padrao(valor)
        if papel == PAPEL_ORDEM:
            if valor is None:
                return ""
            if isinstance(valor, date):
                return valor.toordinal()
            if isinstance(valor, str):
                return sem_acentos(valor)
            return valor
        if papel == PAPEL_OBJETO:
            return self.linhas[indice.row()]
        if papel == Qt.ItemDataRole.TextAlignmentRole:
            return int(coluna.alinhamento | Qt.AlignmentFlag.AlignVCenter)
        if papel == Qt.ItemDataRole.ToolTipRole and coluna.dica:
            return coluna.dica(self.linhas[indice.row()])
        return None


class FiltroBusca(QSortFilterProxyModel):
    """Filtra por texto em todas as colunas, ignorando acentos e maiúsculas."""

    def __init__(self, pai=None):
        super().__init__(pai)
        self._termos: list[str] = []
        self.setSortRole(PAPEL_ORDEM)
        self.setDynamicSortFilter(False)

    def definir_busca(self, texto: str) -> None:
        termos = sem_acentos(texto).split()
        if hasattr(self, "beginFilterChange"):  # Qt 6.9+
            self.beginFilterChange()
            self._termos = termos
            self.endFilterChange()
        else:
            self._termos = termos
            self.invalidateFilter()

    def filterAcceptsRow(self, linha: int, pai: QModelIndex) -> bool:  # noqa: N802
        if not self._termos:
            return True
        modelo = self.sourceModel()
        textos = " ".join(
            str(modelo.data(modelo.index(linha, c, pai), PAPEL_ORDEM) or "") for c in range(modelo.columnCount())
        )
        return all(termo in textos for termo in self._termos)

    def lessThan(self, esquerda: QModelIndex, direita: QModelIndex) -> bool:  # noqa: N802
        a, b = esquerda.data(PAPEL_ORDEM), direita.data(PAPEL_ORDEM)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


class Tabela(QTableView):
    """Tabela somente leitura com busca, ordenação e seleção de linhas."""

    ativada = Signal(object)

    def __init__(self, colunas: list[Coluna], pai=None, selecao_multipla: bool = True):
        super().__init__(pai)
        self.modelo = ModeloTabela(colunas, self)
        self.filtro = FiltroBusca(self)
        self.filtro.setSourceModel(self.modelo)
        self.setModel(self.filtro)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
            if selecao_multipla else QAbstractItemView.SelectionMode.SingleSelection
        )
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)
        cabecalho = self.horizontalHeader()
        cabecalho.setHighlightSections(False)
        cabecalho.setSectionsMovable(True)
        cabecalho.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for indice, coluna in enumerate(colunas):
            if coluna.esticar:
                cabecalho.setSectionResizeMode(indice, QHeaderView.ResizeMode.Stretch)
            elif coluna.largura:
                self.setColumnWidth(indice, coluna.largura)
        self.doubleClicked.connect(lambda indice: self.ativada.emit(indice.data(PAPEL_OBJETO)))

    def definir(self, objetos: list[Any]) -> None:
        """Troca as linhas mantendo selecionados os mesmos registros (pelo id)."""
        ids = {getattr(o, "id", None) for o in self.selecionados()} - {None}
        self.modelo.definir(objetos)
        if not ids:
            return
        selecao = self.selectionModel()
        for linha in range(self.filtro.rowCount()):
            indice = self.filtro.index(linha, 0)
            if getattr(indice.data(PAPEL_OBJETO), "id", None) in ids:
                selecao.select(
                    indice,
                    selecao.SelectionFlag.Select | selecao.SelectionFlag.Rows,
                )

    def selecionados(self) -> list[Any]:
        linhas = sorted({i.row() for i in self.selectionModel().selectedRows()}) if self.selectionModel() else []
        return [self.filtro.index(r, 0).data(PAPEL_OBJETO) for r in linhas]

    def atual(self) -> Any | None:
        itens = self.selecionados()
        if itens:
            return itens[0]
        indice = self.currentIndex()
        return indice.data(PAPEL_OBJETO) if indice.isValid() else None

    def visiveis(self) -> list[Any]:
        return [self.filtro.index(r, 0).data(PAPEL_OBJETO) for r in range(self.filtro.rowCount())]

    def keyPressEvent(self, evento):  # noqa: N802
        if evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.currentIndex().isValid():
            self.ativada.emit(self.currentIndex().data(PAPEL_OBJETO))
            return
        super().keyPressEvent(evento)


class DelegadoSituacao(QStyledItemDelegate):
    """Desenha a situação como etiqueta: bolinha colorida + texto em tinta."""

    def paint(self, pintor: QPainter, opcao: QStyleOptionViewItem, indice: QModelIndex) -> None:
        texto = indice.data(Qt.ItemDataRole.DisplayRole) or ""
        opcao_base = QStyleOptionViewItem(opcao)
        self.initStyleOption(opcao_base, indice)
        opcao_base.text = ""
        estilo_widget = opcao.widget.style() if opcao.widget else None
        if estilo_widget:
            estilo_widget.drawControl(QStyle.ControlElement.CE_ItemViewItem, opcao_base, pintor, opcao.widget)
        if not texto:
            return
        cor = estilo.cor_situacao(texto)
        pintor.save()
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        metricas = QFontMetrics(opcao.font)
        largura = metricas.horizontalAdvance(texto) + 28
        altura = 22
        area = opcao.rect
        caixa = QRectF(area.x() + 6, area.y() + (area.height() - altura) / 2, largura, altura)
        fundo = QColor(cor)
        fundo.setAlpha(28)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(fundo)
        pintor.drawRoundedRect(caixa, altura / 2, altura / 2)
        pintor.setBrush(cor)
        pintor.drawEllipse(QRectF(caixa.x() + 9, caixa.center().y() - 4, 8, 8))
        pintor.setPen(QColor(estilo.TINTA))
        pintor.drawText(caixa.adjusted(22, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, texto)
        pintor.restore()


class DelegadoMedidor(QStyledItemDelegate):
    """Percentual (0–1) como barra: preenchimento azul sobre trilho azul-claro."""

    def paint(self, pintor: QPainter, opcao: QStyleOptionViewItem, indice: QModelIndex) -> None:
        valor = indice.data(PAPEL_ORDEM)
        opcao_base = QStyleOptionViewItem(opcao)
        self.initStyleOption(opcao_base, indice)
        opcao_base.text = ""
        if opcao.widget:
            opcao.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opcao_base, pintor, opcao.widget)
        if not isinstance(valor, (int, float)):
            return
        pintor.save()
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = opcao.rect.adjusted(8, 0, -8, 0)
        texto = f"{valor:.0%}"
        largura_texto = 42
        trilho = QRectF(area.x(), area.center().y() - 3, max(10, area.width() - largura_texto), 6)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(estilo.DESTAQUE_CLARO))
        pintor.drawRoundedRect(trilho, 3, 3)
        cheio = QRectF(trilho.x(), trilho.y(), trilho.width() * max(0.0, min(1.0, valor)), trilho.height())
        pintor.setBrush(QColor(estilo.DESTAQUE))
        pintor.drawRoundedRect(cheio, 3, 3)
        pintor.setPen(QColor(estilo.TINTA_SECUNDARIA))
        pintor.drawText(
            QRectF(trilho.right() + 6, area.y(), largura_texto, area.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, texto,
        )
        pintor.restore()


# ---------------------------------------------------------------- campos


class CampoData(QWidget):
    """Data opcional: calendário + botão para limpar."""

    MINIMA = QDate(1900, 1, 1)

    def __init__(self, valor: date | None = None, pai=None):
        super().__init__(pai)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.editor = QDateEdit()
        self.editor.setCalendarPopup(True)
        self.editor.setDisplayFormat("dd/MM/yyyy")
        self.editor.setMinimumDate(self.MINIMA)
        self.editor.setSpecialValueText("—")
        self.editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        limpar = QToolButton()
        limpar.setText("✕")
        limpar.setToolTip("Limpar data")
        limpar.clicked.connect(lambda: self.definir(None))
        layout.addWidget(self.editor)
        layout.addWidget(limpar)
        self.definir(valor)

    def definir(self, valor: date | None) -> None:
        if valor is None:
            self.editor.setDate(self.MINIMA)
        else:
            self.editor.setDate(QDate(valor.year, valor.month, valor.day))

    def valor(self) -> date | None:
        qdata = self.editor.date()
        if qdata == self.MINIMA:
            return None
        return date(qdata.year(), qdata.month(), qdata.day())


class CaixaBusca(QLineEdit):
    def __init__(self, texto_ajuda: str = "Buscar…", pai=None):
        super().__init__(pai)
        self.setObjectName("busca")
        self.setPlaceholderText(texto_ajuda)
        self.setClearButtonEnabled(True)


# ---------------------------------------------------------------- painel


class CartaoIndicador(QFrame):
    """Indicador: rótulo, valor e observação."""

    clicado = Signal()

    def __init__(self, rotulo: str, pai=None):
        super().__init__(pai)
        self.setObjectName("cartao")
        self.setMinimumWidth(170)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        linha = QHBoxLayout()
        linha.setSpacing(6)
        self._marca = QLabel()
        self._marca.setFixedSize(8, 8)
        self._marca.hide()
        self._rotulo = QLabel(rotulo)
        self._rotulo.setObjectName("rotuloCartao")
        linha.addWidget(self._marca)
        linha.addWidget(self._rotulo)
        linha.addStretch()
        self._valor = QLabel("—")
        self._valor.setObjectName("valorCartao")
        self._obs = QLabel("")
        self._obs.setObjectName("dica")
        layout.addLayout(linha)
        layout.addWidget(self._valor)
        layout.addWidget(self._obs)

    def definir(self, valor: str, observacao: str = "", cor_status: str | None = None) -> None:
        self._valor.setText(valor)
        self._obs.setText(observacao)
        if cor_status:
            self._marca.setStyleSheet(f"background:{cor_status}; border-radius:4px;")
            self._marca.show()
        else:
            self._marca.hide()

    def mousePressEvent(self, evento):  # noqa: N802
        self.clicado.emit()
        super().mousePressEvent(evento)


def _numero_curto(valor: float) -> str:
    return f"{int(valor)}" if float(valor).is_integer() else f"{valor:.1f}".replace(".", ",")


class GraficoColunas(QWidget):
    """Colunas de uma série (ex.: RFQs por mês), com dica ao passar o mouse."""

    def __init__(self, unidade: str = "RFQs", pai=None):
        super().__init__(pai)
        self.unidade = unidade
        self.dados: list[tuple[str, float]] = []
        self.setMinimumHeight(220)
        self.setMouseTracking(True)
        self._areas: list[tuple[QRectF, str, float]] = []
        self._destacada = -1

    def definir(self, dados: list[tuple[str, float]]) -> None:
        self.dados = list(dados)
        self.update()

    def _escala(self, maximo: float) -> tuple[float, list[float]]:
        if maximo <= 0:
            return 4, [0, 1, 2, 3, 4]
        passos = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000]
        passo = next((p for p in passos if maximo / p <= 5), passos[-1])
        topo = passo * (int(maximo // passo) + (0 if maximo % passo == 0 else 1))
        return topo, [passo * i for i in range(int(topo / passo) + 1)]

    def paintEvent(self, _evento):  # noqa: N802
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        fonte = QFont(self.font())
        fonte.setPointSizeF(8.5)
        pintor.setFont(fonte)
        metricas = QFontMetrics(fonte)
        area = QRectF(self.rect()).adjusted(36, 18, -8, -26)
        self._areas = []
        if not self.dados:
            pintor.setPen(QColor(estilo.TINTA_SUAVE))
            pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sem dados")
            return
        maximo = max(v for _, v in self.dados)
        topo, marcas = self._escala(maximo)

        for marca in marcas:
            y = area.bottom() - area.height() * (marca / topo)
            pintor.setPen(QPen(QColor(estilo.EIXO if marca == 0 else estilo.GRADE), 1))
            pintor.drawLine(int(area.left()), int(y), int(area.right()), int(y))
            pintor.setPen(QColor(estilo.TINTA_SUAVE))
            pintor.drawText(QRectF(0, y - 8, area.left() - 6, 16),
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _numero_curto(marca))

        faixa = area.width() / len(self.dados)
        largura = min(24.0, faixa * 0.6)
        indice_max = max(range(len(self.dados)), key=lambda i: self.dados[i][1])
        for indice, (rotulo, valor) in enumerate(self.dados):
            x = area.left() + faixa * indice + (faixa - largura) / 2
            altura = area.height() * (valor / topo) if topo else 0
            coluna = QRectF(x, area.bottom() - altura, largura, altura)
            if altura > 0:
                raio = min(4.0, altura, largura / 2)
                caminho = QPainterPath()
                caminho.moveTo(coluna.left(), coluna.bottom())
                caminho.lineTo(coluna.left(), coluna.top() + raio)
                caminho.quadTo(coluna.left(), coluna.top(), coluna.left() + raio, coluna.top())
                caminho.lineTo(coluna.right() - raio, coluna.top())
                caminho.quadTo(coluna.right(), coluna.top(), coluna.right(), coluna.top() + raio)
                caminho.lineTo(coluna.right(), coluna.bottom())
                caminho.closeSubpath()
                cor = QColor(estilo.DESTAQUE_ESCURO if indice == self._destacada else estilo.DESTAQUE)
                pintor.fillPath(caminho, cor)
            # rótulos seletivos: só o maior valor e o mês atual (último)
            if valor and indice in (indice_max, len(self.dados) - 1):
                pintor.setPen(QColor(estilo.TINTA_SECUNDARIA))
                pintor.drawText(QRectF(x - 20, coluna.top() - 16, largura + 40, 14),
                                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, _numero_curto(valor))
            pintor.setPen(QColor(estilo.TINTA_SUAVE))
            texto = metricas.elidedText(rotulo, Qt.TextElideMode.ElideRight, int(faixa))
            pintor.drawText(QRectF(area.left() + faixa * indice, area.bottom() + 4, faixa, 18),
                            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, texto)
            alvo = QRectF(area.left() + faixa * indice, area.top(), faixa, area.height())
            self._areas.append((alvo, rotulo, valor))

    def mouseMoveEvent(self, evento):  # noqa: N802
        posicao = evento.position()
        for indice, (alvo, rotulo, valor) in enumerate(self._areas):
            if alvo.contains(posicao):
                if indice != self._destacada:
                    self._destacada = indice
                    self.update()
                QToolTip.showText(evento.globalPosition().toPoint() + QPoint(12, 12),
                                  f"<b>{rotulo}</b><br>{_numero_curto(valor)} {self.unidade}", self)
                return
        self.leaveEvent(None)

    def leaveEvent(self, _evento):  # noqa: N802
        if self._destacada != -1:
            self._destacada = -1
            self.update()
        QToolTip.hideText()


class GraficoBarras(QWidget):
    """Barras horizontais rotuladas (categoria → valor)."""

    barra_clicada = Signal(str)

    def __init__(self, pai=None):
        super().__init__(pai)
        self.dados: list[tuple[str, float, str]] = []  # (rótulo, valor, cor)
        self.setMouseTracking(True)
        self._areas: list[tuple[QRectF, str, float]] = []

    def definir(self, dados: list[tuple[str, float, str]]) -> None:
        self.dados = list(dados)
        self.setMinimumHeight(max(60, 30 * len(self.dados) + 8))
        self.update()

    def paintEvent(self, _evento):  # noqa: N802
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        metricas = QFontMetrics(self.font())
        self._areas = []
        if not self.dados:
            pintor.setPen(QColor(estilo.TINTA_SUAVE))
            pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sem dados")
            return
        maximo = max(v for _, v, _ in self.dados) or 1
        coluna_rotulo = min(150, max(metricas.horizontalAdvance(r) for r, _, _ in self.dados) + 12)
        largura_total = self.width() - coluna_rotulo - 50
        for indice, (rotulo, valor, cor) in enumerate(self.dados):
            y = 4 + indice * 30
            pintor.setPen(QColor(estilo.TINTA))
            pintor.drawText(QRectF(0, y, coluna_rotulo - 8, 22), Qt.AlignmentFlag.AlignVCenter, rotulo)
            comprimento = largura_total * (valor / maximo)
            barra = QRectF(coluna_rotulo, y + 4, max(2.0, comprimento), 14)
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(QColor(cor))
            raio = min(4.0, barra.width() / 2)
            caminho = QPainterPath()
            caminho.moveTo(barra.left(), barra.top())
            caminho.lineTo(barra.right() - raio, barra.top())
            caminho.quadTo(barra.right(), barra.top(), barra.right(), barra.top() + raio)
            caminho.lineTo(barra.right(), barra.bottom() - raio)
            caminho.quadTo(barra.right(), barra.bottom(), barra.right() - raio, barra.bottom())
            caminho.lineTo(barra.left(), barra.bottom())
            caminho.closeSubpath()
            pintor.fillPath(caminho, QColor(cor))
            pintor.setPen(QColor(estilo.TINTA_SECUNDARIA))
            pintor.drawText(QRectF(barra.right() + 6, y, 44, 22), Qt.AlignmentFlag.AlignVCenter, _numero_curto(valor))
            self._areas.append((QRectF(0, y, self.width(), 26), rotulo, valor))

    def mouseMoveEvent(self, evento):  # noqa: N802
        for alvo, rotulo, _valor in self._areas:
            if alvo.contains(evento.position()):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                QToolTip.showText(evento.globalPosition().toPoint() + QPoint(12, 12),
                                  f"Ver RFQs: <b>{rotulo}</b>", self)
                return
        self.unsetCursor()
        QToolTip.hideText()

    def mousePressEvent(self, evento):  # noqa: N802
        for alvo, rotulo, _valor in self._areas:
            if alvo.contains(evento.position()):
                self.barra_clicada.emit(rotulo)
                return
