"""Tema visual do aplicativo (cores, fontes e folha de estilo Qt)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from ..caminhos import pasta_recursos
from ..modelos import SITUACAO_AGUARDANDO, SITUACAO_ATRASADA, StatusRFQ

# Fundo da tela (cinza) e superfícies claras (tabelas, cartões, campos) — texto nunca usa a cor da série.
PLANO = "#7A7A7A"
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_SECUNDARIA = "#52514e"
TINTA_SUAVE = "#898781"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"
BORDA = "#d6d5cf"
TEXTO_FUNDO = "#ffffff"  # texto direto sobre o fundo cinza
ABA_INATIVA = "#8d8d8d"

# Destaque (azul claro) e suas variações.
DESTAQUE = "#2a78d6"
DESTAQUE_ESCURO = "#1c5cab"
DESTAQUE_CLARO = "#cde2fb"
DESTAQUE_FUNDO = "#eaf2fc"
SELECAO = "#d3e5fb"  # linhas selecionadas
LINHA_ATUAL = "#eef4fc"  # linha em edição na grade

# Escuro (menu lateral, cabeçalhos, barra de título).
ESCURO = "#2E2E2E"
LATERAL = ESCURO
LATERAL_TEXTO = "#d6d6d6"
LATERAL_TITULO = "#9a9a9a"
LATERAL_HOVER = "#3d3d3d"
LATERAL_BORDA = "#4d4d4d"

# Cores de status (reservadas: nunca usadas como "série").
BOM = "#0ca30c"
BOM_TEXTO = "#006300"
ALERTA = "#fab219"
SERIO = "#ec835a"
CRITICO = "#d03b3b"

COR_SITUACAO = {
    StatusRFQ.RASCUNHO.value: "#898781",
    SITUACAO_AGUARDANDO: ALERTA,
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

/* ---------- textos sobre o fundo cinza ---------- */
QLabel, QCheckBox, QRadioButton {{
    color: {TEXTO_FUNDO};
}}
QLabel#tituloPagina {{
    font-size: 17pt;
    font-weight: 600;
}}
QLabel#rotuloCartao {{
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
    font-size: 9pt;
}}

/* ---------- caixas de marcar e opções: indicador próprio (o texto branco não pode apagar a marca) ---------- */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    background: #ffffff;
    border: 1px solid #5f636a;
}}
QCheckBox::indicator {{
    border-radius: 3px;
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {DESTAQUE};
}}
QCheckBox::indicator:checked {{
    background: {DESTAQUE};
    border-color: {DESTAQUE_ESCURO};
    image: url("{marcado}");
}}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                stop:0 #ffffff, stop:0.32 #ffffff, stop:0.42 {DESTAQUE}, stop:1 {DESTAQUE});
    border-color: {DESTAQUE_ESCURO};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: #e2e2e2;
    border-color: #a9a9a9;
}}

/* ---------- textos sobre superfícies claras (abas, grupos, cartões) ---------- */
QTabWidget QLabel, QGroupBox QLabel, QFrame#cartao QLabel,
QTabWidget QCheckBox, QGroupBox QCheckBox, QTabWidget QRadioButton, QGroupBox QRadioButton {{
    color: {TINTA};
}}
QTabWidget QLabel#subtitulo, QGroupBox QLabel#subtitulo, QFrame#cartao QLabel#subtitulo,
QTabWidget QLabel#rotuloCartao, QGroupBox QLabel#rotuloCartao, QFrame#cartao QLabel#rotuloCartao {{
    color: {TINTA_SECUNDARIA};
}}
QTabWidget QLabel#dica, QGroupBox QLabel#dica, QFrame#cartao QLabel#dica {{
    color: {TINTA_SUAVE};
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
    background: {LATERAL_HOVER};
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
    border: 1px solid #b9bcc2;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: #f0f2f5;
    border-color: #9da3ad;
}}
QPushButton:pressed {{
    background: #e4e7ec;
}}
QPushButton:disabled {{
    color: #8f8f8f;
    background: #d9d9d9;
    border-color: #c4c4c4;
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
QPushButton[primario="true"]:disabled {{
    background: #9fbde3;
    border-color: #9fbde3;
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
    border: 1px solid {LATERAL_BORDA};
    color: #ffffff;
    padding: 8px 12px;
    text-align: left;
}}
QPushButton#botaoLateral:hover {{
    background: {LATERAL_HOVER};
    border-color: #6a6a6a;
}}
QPushButton#botaoLateral:checked {{
    background: {LATERAL_HOVER};
    border: 1px solid {DESTAQUE};
}}
QToolButton {{
    background: {SUPERFICIE};
    border: 1px solid #b9bcc2;
    border-radius: 5px;
    padding: 3px 7px;
}}
QToolButton:hover {{
    background: #e8ebef;
    border-color: #9da3ad;
}}

/* ---------- campos ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background: #ffffff;
    border: 1px solid #b9bcc2;
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
    selection-background-color: {SELECAO};
    selection-color: {TINTA};
    outline: none;
}}

/* ---------- tabelas ---------- */
QTableView, QTableWidget, QListWidget, QTreeWidget {{
    background: {SUPERFICIE};
    alternate-background-color: #f4f5f7;
    border: 1px solid {BORDA};
    border-radius: 6px;
    gridline-color: {GRADE};
    selection-background-color: {SELECAO};
    selection-color: {TINTA};
    outline: 0;
}}
QTableView::item, QTableWidget::item {{
    padding: 4px 6px;
}}
QTableView::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
    background: {SELECAO};
    color: {TINTA};
}}
QListWidget::item {{
    padding: 5px 6px;
}}
QHeaderView::section {{
    background: {ESCURO};
    color: #ffffff;
    font-weight: 600;
    border: none;
    border-right: 1px solid #454545;
    border-bottom: 2px solid {DESTAQUE};
    padding: 6px 8px;
}}
QHeaderView::section:vertical {{
    background: #eceef1;
    color: {TINTA_SECUNDARIA};
    font-weight: 400;
    border: none;
    border-right: 1px solid {GRADE};
    border-bottom: 1px solid {GRADE};
    padding: 0 6px;
}}
QTableCornerButton::section {{
    background: {ESCURO};
    border: none;
}}
QHeaderView {{
    background: {SUPERFICIE};
}}
/* editor dentro da célula: borda azul forte, sem margens que cortem o texto */
QLineEdit#editorCelula, QLineEdit#editorCelula:focus {{
    background: #ffffff;
    border: 2px solid {DESTAQUE};
    border-radius: 0;
    padding: 0 5px;
    margin: 0;
    selection-background-color: {DESTAQUE_CLARO};
    selection-color: {TINTA};
}}
QComboBox#editorCelula, QComboBox#editorCelula:focus {{
    background: #ffffff;
    border: 2px solid {DESTAQUE};
    border-radius: 0;
    padding: 0 5px;
}}
QListWidget#editorMultiplo {{
    background: #ffffff;
    border: 2px solid {DESTAQUE};
    border-radius: 0;
}}

/* ---------- calendário (campos de data) ---------- */
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background: #e9ecf1;
    border-bottom: 2px solid {DESTAQUE};
}}
QCalendarWidget QToolButton {{
    background: transparent;
    border: none;
    color: {TINTA};
    font-weight: 600;
    padding: 4px 8px;
}}
QCalendarWidget QToolButton:hover {{
    background: {DESTAQUE_CLARO};
}}
QCalendarWidget QTableView {{
    border: none;
    border-radius: 0;
}}
QCalendarWidget QTableView::item {{
    padding: 0;
}}

/* ---------- abas / grupos ---------- */
QTabWidget::pane {{
    border: 1px solid {BORDA};
    border-radius: 6px;
    background: {SUPERFICIE};
    top: -1px;
}}
QTabBar::tab {{
    background: {ABA_INATIVA};
    color: #ffffff;
    border: 1px solid #6c6c6c;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 7px 18px;
    margin-right: 2px;
}}
QTabBar::tab:hover {{
    background: #9a9a9a;
}}
QTabBar::tab:selected {{
    background: {SUPERFICIE};
    color: {TINTA};
    font-weight: 600;
    border-color: {BORDA};
    border-top: 3px solid {DESTAQUE};
}}
QTabWidget#abasPlanilha QTabBar::tab {{
    padding: 8px 20px;
}}
QGroupBox {{
    background: {SUPERFICIE};
    border: 1px solid {BORDA};
    border-radius: 8px;
    margin-top: 18px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 4px;
    padding: 0 4px 2px 4px;
    color: {TEXTO_FUNDO};
}}
QStatusBar {{
    background: {ESCURO};
    color: #e6e6e6;
}}
QStatusBar QLabel {{
    color: #e6e6e6;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QToolTip {{
    background: #ffffff;
    color: {TINTA};
    border: 1px solid {EIXO};
    padding: 5px;
}}
"""


def folha_de_estilo() -> str:
    recursos = pasta_recursos()
    return _FOLHA.format(
        seta_baixo=(recursos / "seta_baixo.png").as_posix(),
        seta_cima=(recursos / "seta_cima.png").as_posix(),
        marcado=(recursos / "marcado.png").as_posix(),
        **{nome: valor for nome, valor in globals().items() if nome.isupper() and isinstance(valor, str)},
    )


class _BarraDeTituloEscura(QObject):
    """No Windows, pinta a barra de título de cada janela de cinza escuro (em vez de branco)."""

    PROPRIEDADE = "_rfqBarraEscura"

    def eventFilter(self, objeto, evento):  # noqa: N802 - API Qt
        if evento.type() == QEvent.Type.Show and isinstance(objeto, QWidget) and objeto.isWindow():
            # a marca fica no próprio objeto Qt (o id() do wrapper Python é reaproveitado entre janelas)
            hwnd = int(objeto.winId())
            if objeto.property(self.PROPRIEDADE) != hwnd:
                objeto.setProperty(self.PROPRIEDADE, hwnd)
                barra_de_titulo_escura(objeto)
        return False


def barra_de_titulo_escura(janela: QWidget) -> bool:
    """Barra de título escura via DWM (Windows 10 20H1+ e 11; a cor exata só no Windows 11)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        hwnd = ctypes.c_void_p(int(janela.winId()))
        dwm = ctypes.windll.dwmapi
        escuro = ctypes.c_int(1)
        for atributo in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (19 nas versões antigas do Windows 10)
            if dwm.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(escuro), ctypes.sizeof(escuro)) == 0:
                break
        cor = int(ESCURO[5:7] + ESCURO[3:5] + ESCURO[1:3], 16)  # COLORREF = 0x00BBGGRR
        for atributo, valor in ((35, cor), (34, cor), (36, 0x00FFFFFF)):  # legenda, borda e texto
            dado = ctypes.c_uint(valor)
            dwm.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(dado), ctypes.sizeof(dado))
        return True
    except Exception:  # noqa: BLE001 - só aparência: nunca impede a janela de abrir
        return False


def aplicar_tema(app: QApplication) -> None:
    app.setStyle("Fusion")
    paleta = QPalette()
    paleta.setColor(QPalette.ColorRole.Window, QColor(PLANO))
    paleta.setColor(QPalette.ColorRole.WindowText, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    paleta.setColor(QPalette.ColorRole.AlternateBase, QColor("#f4f5f7"))
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
    if sys.platform == "win32" and not hasattr(app, "_barra_escura"):
        app._barra_escura = _BarraDeTituloEscura(app)
        app.installEventFilter(app._barra_escura)
