"""Formulário genérico para cadastros simples (projetos, solicitantes, feriados)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .componentes import CampoData, executar


@dataclass
class Campo:
    nome: str
    rotulo: str
    tipo: str = "texto"  # texto | texto_longo | inteiro | data | booleano | opcoes | sugestoes
    obrigatorio: bool = False
    opcoes: Callable[[], list[tuple[str, Any]]] | list[tuple[str, Any]] = field(default_factory=list)
    dica: str = ""
    minimo: int = 0
    maximo: int = 999999


class DialogoFormulario(QDialog):
    """Monta um formulário a partir da lista de campos e devolve um dicionário."""

    def __init__(
        self,
        titulo: str,
        campos: list[Campo],
        valores: dict[str, Any] | None = None,
        ao_salvar: Callable[[dict[str, Any]], Any] | None = None,
        pai: QWidget | None = None,
    ):
        super().__init__(pai)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(480)
        self.campos = campos
        self.ao_salvar = ao_salvar
        self.resultado: Any = None
        self._widgets: dict[str, QWidget] = {}
        valores = valores or {}

        layout = QVBoxLayout(self)
        formulario = QFormLayout()
        formulario.setSpacing(10)
        for campo in campos:
            widget = self._criar_widget(campo, valores.get(campo.nome))
            self._widgets[campo.nome] = widget
            rotulo = campo.rotulo + (" *" if campo.obrigatorio else "")
            if campo.dica:
                widget.setToolTip(campo.dica)
            formulario.addRow(rotulo, widget)
        layout.addLayout(formulario)
        obs = QLabel("* campo obrigatório")
        obs.setObjectName("dica")
        layout.addWidget(obs)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Save).setText("Salvar")
        botoes.button(QDialogButtonBox.StandardButton.Save).setProperty("primario", True)
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _criar_widget(self, campo: Campo, valor: Any) -> QWidget:
        if campo.tipo == "texto_longo":
            widget = QPlainTextEdit(valor or "")
            widget.setFixedHeight(80)
        elif campo.tipo == "inteiro":
            widget = QSpinBox()
            widget.setRange(campo.minimo, campo.maximo)
            widget.setSpecialValueText("—" if campo.minimo == 0 and not campo.obrigatorio else "")
            widget.setValue(int(valor or 0))
        elif campo.tipo == "data":
            widget = CampoData(valor)
        elif campo.tipo == "booleano":
            widget = QCheckBox()
            widget.setChecked(bool(valor) if valor is not None else True)
        elif campo.tipo in ("opcoes", "sugestoes"):
            widget = QComboBox()
            opcoes = campo.opcoes() if callable(campo.opcoes) else campo.opcoes
            if campo.tipo == "sugestoes":
                widget.setEditable(True)
                widget.addItems([texto for texto, _ in opcoes])
                widget.setCurrentText(valor or "")
            else:
                for texto, dado in opcoes:
                    widget.addItem(texto, dado)
                indice = widget.findData(valor)
                widget.setCurrentIndex(max(indice, 0))
        else:
            widget = QLineEdit(valor or "")
        return widget

    def valores(self) -> dict[str, Any]:
        resultado: dict[str, Any] = {}
        for campo in self.campos:
            widget = self._widgets[campo.nome]
            if isinstance(widget, QPlainTextEdit):
                valor: Any = widget.toPlainText().strip()
            elif isinstance(widget, QSpinBox):
                valor = widget.value() or None
            elif isinstance(widget, CampoData):
                valor = widget.valor()
            elif isinstance(widget, QCheckBox):
                valor = widget.isChecked()
            elif isinstance(widget, QComboBox):
                valor = widget.currentText().strip() if campo.tipo == "sugestoes" else widget.currentData()
            else:
                valor = widget.text().strip()
            resultado[campo.nome] = valor
        return resultado

    def _salvar(self) -> None:
        valores = self.valores()
        faltando = [c.rotulo for c in self.campos if c.obrigatorio and valores.get(c.nome) in (None, "")]
        if faltando:
            from .componentes import avisar

            avisar(self, "Preencha: " + ", ".join(faltando))
            return
        if self.ao_salvar is None:
            self.accept()
            return
        ok, resultado = executar(self, lambda: self.ao_salvar(valores))
        if ok:
            self.resultado = resultado
            self.accept()

