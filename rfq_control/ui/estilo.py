"""Tema visual do aplicativo (cores, fontes e folha de estilo Qt)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ..caminhos import pasta_recursos
from ..modelos import SITUACAO_ATRASADA, StatusRFQ

# Superfícies e tinta (texto nunca usa a cor da série).
PLANO = "#f3f4f6"
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_SECUNDARIA = "#52514e"
TINTA_SUAVE = "#898781"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"
BORDA = "#e2e1dc"

# Destaque (azul) e suas variações.
DESTAQUE = "#2a78d6"
DESTAQUE_ESCURO = "#1c5cab"
DESTAQUE_CLARO = "#cde2fb"
DESTAQUE_FUNDO = "#eaf2fc"

LATERAL = "#17212f"
LATERAL_TEXTO = "#c9d1db"
LATERAL_TITULO = "#7d8a9a"

# Cores de status (reservadas: nunca usadas como "série").
BOM = "#0ca30c"
BOM_TEXTO = "#006300"
ALERTA = "#fab219"
SERIO = "#ec835a"
CRITICO = "#d03b3b"

COR_SITUACAO = {
    StatusRFQ.RASCUNHO.value: "#898781",
    StatusRFQ.ENVIADA.value: DESTAQUE,
    SITUACAO_ATRASADA: CRITICO,
    StatusRFQ.RESPONDIDA.value: BOM,
    StatusRFQ.SELECIONADA.value: BOM_TEXTO,
    StatusRFQ.NAO_SELECIONADA.value: "#a8a7a0",
    StatusRFQ.DECLINADA.value: SERIO,
    StatusRFQ.CANCELADA.value: EIXO,
}


def cor_situacao(situacao: str) -> QColor:
    return QColor(COR_SITUACAO.get(situacao, TINTA_SUAVE))


_FOLHA = """
QWidget {{
    color: {TINTA};
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background: {PLANO};
}}
QWidget#conteudo, QWidget#pagina {{
    background: {PLANO};
}}
QFrame#cartao {{
    background: {SUPERFICIE};
    border: 1px solid {BORDA};
    border-radius: 8px;
}}
QLabel#tituloPagina {{
    font-size: 17pt;
    font-weight: 600;
}}
QLabel#subtitulo {{
    color: {TINTA_SECUNDARIA};
}}
QLabel#rotuloCartao {{
    color: {TINTA_SECUNDARIA};
    font-size: 9pt;
}}
QLabel#valorCartao {{
    font-size: 22pt;
    font-weight: 600;
}}
QLabel#tituloSecao {{
    font-size: 11pt;
    font-weight: 600;
}}
QLabel#dica {{
    color: {TINTA_SUAVE};
    font-size: 9pt;
}}

/* ---------- menu lateral ---------- */
QWidget#lateral {{
    background: {LATERAL};
}}
QLabel#marca {{
    color: #ffffff;
    font-size: 14pt;
    font-weight: 700;
    padding: 4px 6px;
}}
QLabel#versao {{
    color: {LATERAL_TITULO};
    font-size: 8pt;
    padding: 0 6px;
}}
QListWidget#menu {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget#menu::item {{
    color: {LATERAL_TEXTO};
    padding: 8px 12px;
    border-radius: 6px;
    margin: 1px 0;
}}
QListWidget#menu::item:hover {{
    background: #223044;
    color: #ffffff;
}}
QListWidget#menu::item:selected {{
    background: {DESTAQUE};
    color: #ffffff;
}}
QListWidget#menu::item:disabled {{
    color: {LATERAL_TITULO};
    font-size: 8pt;
    font-weight: 700;
    padding: 14px 12px 4px 12px;
    background: transparent;
}}

/* ---------- botões ---------- */
QPushButton {{
    background: {SUPERFICIE};
    border: 1px solid #cfd3da;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: #f0f2f5;
    border-color: #b8bec8;
}}
QPushButton:pressed {{
    background: #e4e7ec;
}}
QPushButton:disabled {{
    color: #a9a9a9;
    background: #f4f4f4;
    border-color: #e1e1e1;
}}
QPushButton[primario="true"] {{
    background: {DESTAQUE};
    border-color: {DESTAQUE};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[primario="true"]:hover {{
    background: #256abf;
}}
QPushButton[primario="true"]:pressed {{
    background: {DESTAQUE_ESCURO};
}}
QPushButton[perigo="true"] {{
    color: {CRITICO};
}}
QPushButton#novaSolicitacao {{
    background: {DESTAQUE};
    border: none;
    color: #ffffff;
    font-weight: 600;
    padding: 9px 12px;
    text-align: left;
}}
QPushButton#novaSolicitacao:hover {{
    background: #3987e5;
}}
QPushButton#botaoLateral {{
    background: transparent;
    border: 1px solid #34465d;
    color: #ffffff;
    padding: 8px 12px;
    text-align: left;
}}
QPushButton#botaoLateral:hover {{
    background: #223044;
    border-color: #4a5f7a;
}}
QPushButton#botaoLateral:checked {{
    background: #223044;
    border: 1px solid {DESTAQUE};
}}
QTabWidget#abasPlanilha::pane {{
    border: 1px solid {BORDA};
    border-radius: 6px;
    background: {SUPERFICIE};
}}
QTabWidget#abasPlanilha QTabBar::tab {{
    background: #e9ebef;
    border: 1px solid {BORDA};
    border-top: none;
    border-bottom-left-radius: 6px;
    border-bottom-right-radius: 6px;
    padding: 6px 16px;
    margin-right: 2px;
    color: {TINTA_SECUNDARIA};
}}
QTabWidget#abasPlanilha QTabBar::tab:selected {{
    background: {SUPERFICIE};
    color: {TINTA};
    font-weight: 600;
    border-bottom: 3px solid {DESTAQUE};
}}
QToolButton {{
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 2px 6px;
}}
QToolButton:hover {{
    background: #e8ebef;
    border-color: #d5d9df;
}}

/* ---------- campos ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background: #ffffff;
    border: 1px solid #cfd3da;
    border-radius: 5px;
    padding: 5px 7px;
    selection-background-color: {DESTAQUE};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus {{
    border: 1px solid {DESTAQUE};
}}
QLineEdit#busca {{
    padding-left: 10px;
    min-width: 260px;
}}
QComboBox::drop-down, QDateEdit::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow, QDateEdit::down-arrow {{
    image: url("{seta_baixo}");
    width: 10px;
    height: 6px;
}}
QSpinBox, QDoubleSpinBox {{
    padding-right: 24px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid {GRADE};
    border-top-right-radius: 5px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    border-left: 1px solid {GRADE};
    border-bottom-right-radius: 5px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: #e8ebef;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{seta_cima}");
    width: 8px;
    height: 5px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{seta_baixo}");
    width: 8px;
    height: 5px;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid {EIXO};
    selection-background-color: {DESTAQUE_FUNDO};
    selection-color: {TINTA};
    outline: none;
}}

/* ---------- tabelas ---------- */
QTableView, QTableWidget, QListWidget, QTreeWidget {{
    background: {SUPERFICIE};
    alternate-background-color: #f6f7f8;
    border: 1px solid {BORDA};
    border-radius: 6px;
    gridline-color: {GRADE};
    selection-background-color: {DESTAQUE_FUNDO};
    selection-color: {TINTA};
}}
QTableView::item, QTableWidget::item {{
    padding: 4px 6px;
}}
QListWidget::item {{
    padding: 5px 6px;
}}
QHeaderView::section {{
    background: #eef0f3;
    color: {TINTA_SECUNDARIA};
    font-weight: 600;
    border: none;
    border-bottom: 1px solid {BORDA};
    border-right: 1px solid {GRADE};
    padding: 6px 8px;
}}
QTableCornerButton::section {{
    background: #eef0f3;
    border: none;
}}

/* ---------- abas / grupos ---------- */
QTabWidget::pane {{
    border: 1px solid {BORDA};
    border-radius: 6px;
    background: {SUPERFICIE};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    padding: 7px 16px;
    border-bottom: 2px solid transparent;
    color: {TINTA_SECUNDARIA};
}}
QTabBar::tab:selected {{
    color: {TINTA};
    border-bottom: 2px solid {DESTAQUE};
    font-weight: 600;
}}
QGroupBox {{
    background: {SUPERFICIE};
    border: 1px solid {BORDA};
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {TINTA_SECUNDARIA};
}}
QStatusBar {{
    background: {SUPERFICIE};
    border-top: 1px solid {BORDA};
    color: {TINTA_SECUNDARIA};
}}
QToolTip {{
    background: #ffffff;
    color: {TINTA};
    border: 1px solid {EIXO};
    padding: 5px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
"""


def folha_de_estilo() -> str:
    recursos = pasta_recursos()
    return _FOLHA.format(
        seta_baixo=(recursos / "seta_baixo.png").as_posix(),
        seta_cima=(recursos / "seta_cima.png").as_posix(),
        **{nome: valor for nome, valor in globals().items() if nome.isupper() and isinstance(valor, str)},
    )


def aplicar_tema(app: QApplication) -> None:
    app.setStyle("Fusion")
    paleta = QPalette()
    paleta.setColor(QPalette.ColorRole.Window, QColor(PLANO))
    paleta.setColor(QPalette.ColorRole.WindowText, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    paleta.setColor(QPalette.ColorRole.AlternateBase, QColor("#f6f7f8"))
    paleta.setColor(QPalette.ColorRole.Text, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.Button, QColor(SUPERFICIE))
    paleta.setColor(QPalette.ColorRole.ButtonText, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.Highlight, QColor(DESTAQUE))
    paleta.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    paleta.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    paleta.setColor(QPalette.ColorRole.ToolTipText, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.PlaceholderText, QColor(TINTA_SUAVE))
    app.setPalette(paleta)
    fonte = QFont("Segoe UI")
    fonte.setPointSize(10)
    app.setFont(fonte)
    app.setStyleSheet(folha_de_estilo())
