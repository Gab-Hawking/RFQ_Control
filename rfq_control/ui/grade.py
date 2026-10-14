"""Grade editável tipo planilha para as abas de cadastro da Base de dados.

- edição direto na célula (comece a digitar, como no Excel); a linha atual fica destacada e a
  célula atual ganha uma moldura azul;
- colunas com várias opções (ex.: Commodity) abrem uma lista para marcar;
- colunas calculadas (ex.: e-mail do Commodity Buyer) aparecem em cinza e não são editáveis;
- cada linha é validada e salva sozinha ao terminar a edição;
- linhas com problema ficam destacadas, com o motivo na dica (tooltip);
- Ctrl+V cola várias linhas/colunas copiadas do Excel; Ctrl+C copia; Delete limpa células.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QKeySequence, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTableView,
)

from ..armazenamento import BaseDados, ErroDados
from ..servicos import cadastros
from ..servicos.abas import DefinicaoAba
from ..servicos.formatos import ler_data, normalizar_nome, separar_valores
from ..servicos.rfq import ErroNegocio
from . import estilo
from .componentes import PAPEL_ORDEM, DelegadoBase, FiltroBusca, sem_acentos

FUNDO_ERRO = QColor("#fdecea")
FUNDO_NOVA = QColor("#fff8e1")
FUNDO_CALCULADA = QColor("#eef0f2")


@dataclass
class LinhaGrade:
    registro: Any | None
    valores: dict[str, str]
    erro: str = ""

    @property
    def id(self) -> str | None:
        return getattr(self.registro, "id", None)


class ModeloGrade(QAbstractTableModel):
    """Linhas de uma aba de cadastro, salvas uma a uma na base de dados."""

    alterado = Signal()

    def __init__(self, base: BaseDados, definicao: DefinicaoAba, pai=None):
        super().__init__(pai)
        self.base = base
        self.definicao = definicao
        self.linhas: list[LinhaGrade] = []

    # ------------------------------------------------ carga
    def carregar(self, manter_pendentes: bool = False) -> None:
        """Lê os registros de novo. ``manter_pendentes``: linhas não salvas continuam como estão (as demais
        são atualizadas — ex.: uma commodity renomeada em outra aba)."""
        pendentes = self.pendentes() if manter_pendentes else []
        por_id = {l.id: l for l in pendentes if l.id}
        self.beginResetModel()
        self.linhas = [
            por_id.get(r.id) or LinhaGrade(r, self.definicao.para_linha(self.base, r))
            for r in self.definicao.listar(self.base)
        ] + [l for l in pendentes if l.registro is None]
        self.endResetModel()
        self.alterado.emit()

    def pendentes(self) -> list[LinhaGrade]:
        """Linhas que não foram salvas (novas incompletas ou com erro)."""
        return [l for l in self.linhas if l.erro or (l.registro is None and any(l.valores.values()))]

    # ------------------------------------------------ API Qt
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - API Qt
        return 0 if parent.isValid() else len(self.linhas)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.definicao.colunas)

    def headerData(self, secao, orientacao, papel=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientacao == Qt.Orientation.Horizontal:
            coluna = self.definicao.colunas[secao]
            if papel == Qt.ItemDataRole.DisplayRole:
                return coluna.titulo + (" *" if coluna.obrigatoria else "")
            if papel == Qt.ItemDataRole.ToolTipRole:
                opcoes = coluna.opcoes_de(self.base)
                return coluna.dica or (", ".join(opcoes) if opcoes else None)
        if orientacao == Qt.Orientation.Vertical and papel == Qt.ItemDataRole.DisplayRole:
            return str(secao + 1)
        return None

    def flags(self, indice: QModelIndex):
        if indice.isValid() and self.definicao.colunas[indice.column()].somente_leitura:
            return super().flags(indice)
        return super().flags(indice) | Qt.ItemFlag.ItemIsEditable

    def data(self, indice: QModelIndex, papel=Qt.ItemDataRole.DisplayRole):
        if not indice.isValid():
            return None
        linha = self.linhas[indice.row()]
        coluna = self.definicao.colunas[indice.column()]
        valor = linha.valores.get(coluna.chave, "")
        if papel in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return valor
        if papel == PAPEL_ORDEM:
            if coluna.tipo == "data":
                try:
                    dia = ler_data(valor)
                    return dia.isoformat() if dia else ""
                except ValueError:
                    return valor
            if coluna.tipo == "inteiro" and valor.strip().isdigit():
                return f"{int(valor):012d}"
            return sem_acentos(valor)
        if papel == Qt.ItemDataRole.BackgroundRole:
            if linha.erro:
                return FUNDO_ERRO
            if linha.registro is None:
                return FUNDO_NOVA
            if coluna.somente_leitura:
                return FUNDO_CALCULADA
        if papel == Qt.ItemDataRole.ToolTipRole:
            if linha.erro:
                return f"Não salvo: {linha.erro}"
            if linha.registro is None:
                return "Linha nova: preencha as colunas obrigatórias (*) para salvar."
            return coluna.dica or None
        if papel == Qt.ItemDataRole.ForegroundRole and (
            coluna.somente_leitura or (coluna.chave == "ativo" and valor == "Não")
        ):
            return QColor(estilo.TINTA_SECUNDARIA)
        return None

    def setData(self, indice: QModelIndex, valor, papel=Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if not indice.isValid() or papel != Qt.ItemDataRole.EditRole:
            return False
        linha = self.linhas[indice.row()]
        coluna = self.definicao.colunas[indice.column()]
        if coluna.somente_leitura:
            return False
        chave = coluna.chave
        texto = "" if valor is None else str(valor).strip()
        if linha.valores.get(chave, "") == texto and not linha.erro:
            return False
        linha.valores[chave] = texto
        self.salvar_linha(indice.row())
        return True

    # ------------------------------------------------ gravação
    def salvar_linha(self, numero: int) -> bool:
        linha = self.linhas[numero]
        if linha.registro is None and not any(linha.valores.values()):
            linha.erro = ""
            self._linha_alterada(numero)
            return False
        try:
            registro = self.definicao.gravar_linha(self.base, dict(linha.valores), linha.registro)
        except (ErroNegocio, ErroDados) as problema:
            linha.erro = str(problema)
            self._linha_alterada(numero)
            return False
        linha.registro = registro
        linha.valores = self.definicao.para_linha(self.base, registro)
        linha.erro = ""
        self._linha_alterada(numero)
        return True

    def _linha_alterada(self, numero: int) -> None:
        self.dataChanged.emit(self.index(numero, 0), self.index(numero, self.columnCount() - 1))
        self.alterado.emit()

    def nova_linha(self) -> int:
        numero = len(self.linhas)
        self.beginInsertRows(QModelIndex(), numero, numero)
        self.linhas.append(LinhaGrade(None, self.definicao.linha_vazia()))
        self.endInsertRows()
        self.alterado.emit()
        return numero

    def definir_celulas(self, alteracoes: dict[int, dict[str, str]]) -> tuple[int, int]:
        """Altera várias células e salva cada linha uma vez. Devolve (linhas salvas, linhas com erro)."""
        salvas = erros = 0
        calculadas = {c.chave for c in self.definicao.colunas if c.somente_leitura}
        alteracoes = {n: {k: v for k, v in valores.items() if k not in calculadas} for n, valores in alteracoes.items()}
        for numero in sorted(alteracoes):
            while numero >= len(self.linhas):
                self.nova_linha()
            self.linhas[numero].valores.update(alteracoes[numero])
            if self.salvar_linha(numero):
                salvas += 1
            elif self.linhas[numero].erro:
                erros += 1
        return salvas, erros

    def remover(self, numeros: list[int]) -> int:
        """Exclui as linhas; registros em uso (com RFQs/pacotes) não são excluídos."""
        numeros = sorted(set(numeros), reverse=True)
        registros = [self.linhas[n].registro for n in numeros if self.linhas[n].registro is not None]
        if registros:
            cadastros.excluir_registros(self.base, registros)  # ErroNegocio se algum estiver em uso
        for numero in numeros:
            self.beginRemoveRows(QModelIndex(), numero, numero)
            del self.linhas[numero]
            self.endRemoveRows()
        self.alterado.emit()
        return len(numeros)


class EditorMultiplo(QListWidget):
    """Lista com caixas para marcar vários valores (ex.: as commodities de um fornecedor).

    Clique (ou espaço) marca/desmarca; Enter ou sair da lista grava.
    """

    def __init__(self, opcoes: tuple[str, ...], pai=None):
        super().__init__(pai)
        self.setObjectName("editorMultiplo")
        for opcao in opcoes:
            self._adicionar(opcao)
        if not opcoes:
            aviso = QListWidgetItem("Nenhuma cadastrada — use a aba Commodities")
            aviso.setFlags(Qt.ItemFlag.NoItemFlags)
            self.addItem(aviso)
        self.itemClicked.connect(self._alternar)

    def _adicionar(self, texto: str) -> QListWidgetItem:
        item = QListWidgetItem(texto)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.addItem(item)
        return item

    def _alternar(self, item: QListWidgetItem) -> None:
        if item.flags() & Qt.ItemFlag.ItemIsEnabled:
            marcado = item.checkState() == Qt.CheckState.Checked
            item.setCheckState(Qt.CheckState.Unchecked if marcado else Qt.CheckState.Checked)

    def keyPressEvent(self, evento):  # noqa: N802
        if evento.key() == Qt.Key.Key_Space and self.currentItem():
            self._alternar(self.currentItem())
            return
        super().keyPressEvent(evento)

    def definir(self, valores: list[str]) -> None:
        # mesma comparação do cadastro (maiúsculas e espaços): "Fundição" e "Fundicao" são commodities diferentes
        chaves = {normalizar_nome(v) for v in valores}
        presentes = set()
        for linha in range(self.count()):
            item = self.item(linha)
            if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                presentes.add(normalizar_nome(item.text()))
                item.setCheckState(Qt.CheckState.Checked if normalizar_nome(item.text()) in chaves
                                   else Qt.CheckState.Unchecked)
        for valor in valores:  # valor que não está mais na lista: mostra marcado para não perder
            if normalizar_nome(valor) not in presentes:
                self._adicionar(valor).setCheckState(Qt.CheckState.Checked)
        if self.count():
            self.setCurrentRow(0)

    def valores(self) -> list[str]:
        return [
            self.item(i).text() for i in range(self.count())
            if self.item(i).flags() & Qt.ItemFlag.ItemIsEnabled and self.item(i).checkState() == Qt.CheckState.Checked
        ]


class DelegadoGrade(DelegadoBase):
    """Editor de acordo com o tipo da coluna; destaca a linha atual e emoldura a célula atual."""

    def __init__(self, definicao: DefinicaoAba, base: BaseDados | None = None, pai=None):
        super().__init__(pai)
        self.definicao = definicao
        self.base = base

    # ------------------------------------------------ aparência
    def initStyleOption(self, opcao, indice):  # noqa: N802
        super().initStyleOption(opcao, indice)
        vista = self.parent()
        atual = vista.currentIndex() if isinstance(vista, QAbstractItemView) else QModelIndex()
        if atual.isValid() and atual.row() == indice.row() and opcao.backgroundBrush.style() == Qt.BrushStyle.NoBrush:
            opcao.backgroundBrush = QBrush(QColor(estilo.LINHA_ATUAL))

    def paint(self, pintor, opcao, indice):
        super().paint(pintor, opcao, indice)
        vista = self.parent()
        if isinstance(vista, QAbstractItemView) and vista.currentIndex() == indice:
            pintor.save()
            pintor.setPen(QPen(QColor(estilo.DESTAQUE), 2))
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.drawRect(opcao.rect.adjusted(1, 1, -1, -1))
            pintor.restore()

    # ------------------------------------------------ edição
    def createEditor(self, pai, opcao, indice):  # noqa: N802
        coluna = self.definicao.colunas[indice.column()]
        opcoes = coluna.opcoes_de(self.base)
        if coluna.tipo == "multilista":
            return EditorMultiplo(opcoes, pai)
        if opcoes:
            editor = QComboBox(pai)
            editor.setObjectName("editorCelula")
            editor.addItems(([""] if coluna.tipo == "lista" else []) + list(opcoes))
            # escolher na lista já grava, sem precisar sair da célula
            editor.activated.connect(lambda _i, e=editor: (self.commitData.emit(e), self.closeEditor.emit(e)))
            return editor
        editor = QLineEdit(pai)
        editor.setObjectName("editorCelula")
        if coluna.tipo == "data":
            editor.setPlaceholderText("dd/mm/aaaa")
        elif coluna.tipo == "emails":
            editor.setPlaceholderText("email@empresa.com; outro@empresa.com")
        return editor

    def updateEditorGeometry(self, editor, opcao, indice):  # noqa: N802
        if isinstance(editor, EditorMultiplo):
            area = opcao.rect
            altura = min(8, max(1, editor.count())) * 28 + 8
            largura = max(area.width(), 260)
            y = area.y()
            visivel = editor.parentWidget().height() if editor.parentWidget() else y + altura
            if y + altura > visivel:  # perto do fim da tabela: abre para cima
                y = max(0, visivel - altura)
            editor.setGeometry(area.x(), y, largura, altura)
            return
        super().updateEditorGeometry(editor, opcao, indice)

    def setEditorData(self, editor, indice):  # noqa: N802
        valor = indice.data(Qt.ItemDataRole.EditRole) or ""
        if isinstance(editor, EditorMultiplo):
            editor.definir(separar_valores(valor))
        elif isinstance(editor, QComboBox):
            posicao = editor.findText(valor)
            editor.setCurrentIndex(max(0, posicao))
            editor.showPopup()
        else:
            editor.setText(valor)

    def setModelData(self, editor, modelo, indice):  # noqa: N802
        if isinstance(editor, EditorMultiplo):
            texto = "; ".join(editor.valores())
        else:
            texto = editor.currentText() if isinstance(editor, QComboBox) else editor.text()
        modelo.setData(indice, texto, Qt.ItemDataRole.EditRole)


class GradeEditavel(QTableView):
    """Tabela editável com busca, colar/copiar do Excel e exclusão de linhas."""

    mensagem = Signal(str)

    def __init__(self, base: BaseDados, definicao: DefinicaoAba, pai=None):
        super().__init__(pai)
        self.definicao = definicao
        self.modelo = ModeloGrade(base, definicao, self)
        self.filtro = FiltroBusca(self)
        self.filtro.setSourceModel(self.modelo)
        self.setModel(self.filtro)
        self.setItemDelegate(DelegadoGrade(definicao, base, self))
        self.setSortingEnabled(True)
        self.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.verticalHeader().setDefaultSectionSize(32)
        self.verticalHeader().setMinimumWidth(36)
        cabecalho = self.horizontalHeader()
        cabecalho.setHighlightSections(False)
        cabecalho.setStretchLastSection(True)
        for indice, coluna in enumerate(definicao.colunas):
            self.setColumnWidth(indice, coluna.largura)
        # a linha atual é desenhada destacada: redesenha quando a célula atual muda
        self.selectionModel().currentChanged.connect(lambda *_: self.viewport().update())

    # ------------------------------------------------ auxiliares
    def _origem(self, indice: QModelIndex) -> QModelIndex:
        return self.filtro.mapToSource(indice)

    def linhas_selecionadas(self) -> list[int]:
        return sorted({self._origem(i).row() for i in self.selectionModel().selectedIndexes()})

    def registro_atual(self) -> Any | None:
        indice = self.currentIndex()
        if not indice.isValid():
            return None
        return self.modelo.linhas[self._origem(indice).row()].registro

    def nova_linha(self) -> None:
        self.filtro.definir_busca("")
        numero = self.modelo.nova_linha()
        destino = self.filtro.mapFromSource(self.modelo.index(numero, 0))
        self.scrollTo(destino)
        self.setCurrentIndex(destino)
        self.edit(destino)

    # ------------------------------------------------ teclado: colar, copiar, limpar
    def keyPressEvent(self, evento):  # noqa: N802
        if self.state() != QAbstractItemView.State.EditingState:
            if evento.matches(QKeySequence.StandardKey.Paste):
                self.colar(QGuiApplication.clipboard().text())
                return
            if evento.matches(QKeySequence.StandardKey.Copy):
                self.copiar()
                return
            if evento.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.limpar_celulas()
                return
        super().keyPressEvent(evento)

    def colar(self, texto: str) -> None:
        linhas_texto = [l for l in texto.replace("\r\n", "\n").rstrip("\n").split("\n")]
        if not texto.strip():
            return
        atual = self.currentIndex()
        if atual.isValid():
            origem = self._origem(atual)
            linha_inicial, coluna_inicial = origem.row(), origem.column()
        else:
            linha_inicial, coluna_inicial = len(self.modelo.linhas), 0
        # as colunas coladas caem nas colunas editáveis a partir da atual (as calculadas são puladas,
        # como na planilha de 'Baixar modelo', que só tem as editáveis)
        destino = [c for c in self.definicao.colunas[coluna_inicial:] if not c.somente_leitura]
        alteracoes: dict[int, dict[str, str]] = {}
        for deslocamento, linha_texto in enumerate(linhas_texto):
            valores = {}
            for passo, valor in enumerate(linha_texto.split("\t")):
                if passo < len(destino):
                    valores[destino[passo].chave] = valor.strip()
            alteracoes[linha_inicial + deslocamento] = valores
        salvas, erros = self.modelo.definir_celulas(alteracoes)
        texto_erros = f" · {erros} com erro (passe o mouse na linha vermelha)" if erros else ""
        self.mensagem.emit(f"{len(alteracoes)} linha(s) coladas: {salvas} salva(s){texto_erros}.")

    def copiar(self) -> None:
        indices = sorted(self.selectionModel().selectedIndexes(), key=lambda i: (i.row(), i.column()))
        if not indices:
            return
        linhas: dict[int, dict[int, str]] = {}
        for indice in indices:
            linhas.setdefault(indice.row(), {})[indice.column()] = indice.data() or ""
        colunas = sorted({c for valores in linhas.values() for c in valores})
        texto = "\n".join("\t".join(valores.get(c, "") for c in colunas) for valores in linhas.values())
        QGuiApplication.clipboard().setText(texto)

    def limpar_celulas(self) -> None:
        alteracoes: dict[int, dict[str, str]] = {}
        for indice in self.selectionModel().selectedIndexes():
            origem = self._origem(indice)
            coluna = self.definicao.colunas[origem.column()]
            alteracoes.setdefault(origem.row(), {})[coluna.chave] = ""
        if alteracoes:
            self.modelo.definir_celulas(alteracoes)
