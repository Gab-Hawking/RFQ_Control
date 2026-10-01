"""Criação/edição de pacote de cotação e envio para fornecedores."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..modelos import RFQ, Fornecedor, Item, Pacote, StatusRFQ
from ..servicos import rfq as srv
from ..servicos.envio_email import abrir_arquivo
from ..servicos.formatos import ler_numero, numero_br
from .componentes import CaixaBusca, CampoData, avisar, botao, confirmar, executar, sem_acentos

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal

COLUNAS_ITENS = [
    ("ref_op", "OP - Ref", 200),
    ("ref_cdc", "CDC - Ref", 260),
    ("descricao", "Descrição", 200),
    ("unidade", "Unidade", 80),
    ("quantidade", "Quantidade", 105),
    ("volume_anual", "Volume anual", 125),
]
_NUMERICAS = {"quantidade", "volume_anual"}


class TabelaItens(QTableWidget):
    """Grade de itens que aceita colar várias linhas/colunas do Excel (Ctrl+V)."""

    def __init__(self, pai=None):
        super().__init__(0, len(COLUNAS_ITENS), pai)
        self.setHorizontalHeaderLabels([titulo for _, titulo, _ in COLUNAS_ITENS])
        for indice, (_, _, largura) in enumerate(COLUNAS_ITENS):
            self.setColumnWidth(indice, largura)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setDefaultSectionSize(28)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)

    def definir_itens(self, itens: list[Item]) -> None:
        self.setRowCount(0)
        for item in itens:
            self.adicionar_linha(item)

    def adicionar_linha(self, item: Item | None = None) -> int:
        linha = self.rowCount()
        self.insertRow(linha)
        for coluna, (campo, _, _) in enumerate(COLUNAS_ITENS):
            valor = getattr(item, campo) if item else None
            texto = numero_br(valor) if campo in _NUMERICAS else (valor or "")
            celula = QTableWidgetItem(texto)
            if campo in _NUMERICAS:
                celula.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(linha, coluna, celula)
        return linha

    def remover_selecionadas(self) -> None:
        for linha in sorted({i.row() for i in self.selectedIndexes()}, reverse=True):
            self.removeRow(linha)

    def colar(self) -> int:
        texto = QGuiApplication.clipboard().text()
        if not texto.strip():
            return 0
        linhas = [l for l in texto.replace("\r\n", "\n").rstrip("\n").split("\n")]
        linha_inicial = max(self.currentRow(), 0) if self.rowCount() else 0
        coluna_inicial = max(self.currentColumn(), 0)
        for deslocamento, linha_texto in enumerate(linhas):
            destino = linha_inicial + deslocamento
            while destino >= self.rowCount():
                self.adicionar_linha()
            for passo, valor in enumerate(linha_texto.split("\t")):
                coluna = coluna_inicial + passo
                if coluna < self.columnCount():
                    self.item(destino, coluna).setText(valor.strip())
        return len(linhas)

    def keyPressEvent(self, evento):  # noqa: N802
        if evento.matches(QKeySequence.StandardKey.Paste):
            self.colar()
            return
        if evento.key() == Qt.Key.Key_Delete and self.state() != QAbstractItemView.State.EditingState:
            for indice in self.selectedIndexes():
                self.item(indice.row(), indice.column()).setText("")
            return
        super().keyPressEvent(evento)

    def itens(self) -> list[Item]:
        itens = []
        for linha in range(self.rowCount()):
            dados = {}
            for coluna, (campo, titulo, _) in enumerate(COLUNAS_ITENS):
                texto = self.item(linha, coluna).text().strip() if self.item(linha, coluna) else ""
                if campo in _NUMERICAS:
                    numero = ler_numero(texto)
                    if texto and numero is None:
                        raise srv.ErroNegocio(f"Linha {linha + 1}: '{texto}' não é um número válido em {titulo}.")
                    dados[campo] = numero
                else:
                    dados[campo] = texto
            item = Item(**dados)
            if not item.vazio():
                itens.append(item)
        return itens


class ListaFornecedores(QWidget):
    """Lista de fornecedores com caixas de seleção e busca."""

    def __init__(self, janela: JanelaPrincipal, ja_incluidos: set[str], ao_mudar, pai=None):
        super().__init__(pai)
        self.janela = janela
        self.ja_incluidos = ja_incluidos
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        barra = QHBoxLayout()
        self.busca = CaixaBusca("Buscar fornecedor ou categoria…")
        self.busca.textChanged.connect(self._filtrar)
        barra.addWidget(self.busca)
        barra.addWidget(botao("+ Novo fornecedor", self._novo_fornecedor))
        layout.addLayout(barra)
        self.lista = QListWidget()
        self.lista.itemChanged.connect(lambda _: ao_mudar())
        layout.addWidget(self.lista, 1)
        self.carregar()

    def carregar(self, marcar: set[str] | None = None) -> None:
        marcados = set(self.selecionados()) | (marcar or set())
        self.lista.blockSignals(True)
        self.lista.clear()
        fornecedores = sorted(
            (f for f in self.janela.base.fornecedores if f.ativo or f.id in marcados),
            key=lambda f: f.nome.casefold(),
        )
        for fornecedor in fornecedores:
            self.lista.addItem(self._criar_item(fornecedor, fornecedor.id in marcados))
        self.lista.blockSignals(False)
        self._filtrar(self.busca.text())

    def _criar_item(self, fornecedor: Fornecedor, marcado: bool) -> QListWidgetItem:
        emails = fornecedor.emails_para()
        detalhe = emails[0] if emails else "⚠ sem e-mail cadastrado"
        extra = f" · {fornecedor.categoria}" if fornecedor.categoria else ""
        item = QListWidgetItem(f"{fornecedor.nome}   —   {fornecedor.idioma.value} · {detalhe}{extra}")
        item.setData(Qt.ItemDataRole.UserRole, fornecedor.id)
        if fornecedor.id in self.ja_incluidos:
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setText(item.text() + "   (já incluído)")
        else:
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked)
        if not emails:
            item.setToolTip("Cadastre um e-mail (Para) antes de gerar o e-mail desta RFQ.")
        return item

    def _filtrar(self, texto: str) -> None:
        termos = sem_acentos(texto).split()
        for linha in range(self.lista.count()):
            item = self.lista.item(linha)
            alvo = sem_acentos(item.text())
            item.setHidden(not all(t in alvo for t in termos))

    def _novo_fornecedor(self) -> None:
        from .dialogos_cadastro import DialogoFornecedor

        dialogo = DialogoFornecedor(self.janela, pai=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.resultado:
            self.carregar(marcar={dialogo.resultado.id})

    def selecionados(self) -> list[str]:
        ids = []
        for linha in range(self.lista.count()):
            item = self.lista.item(linha)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids


class DialogoPacote(QDialog):
    """Nova solicitação (pacote + fornecedores) ou edição de um pacote existente."""

    def __init__(self, janela: JanelaPrincipal, pacote: Pacote | None = None, aba_inicial: str = "itens", pai=None):
        super().__init__(pai or janela)
        self.janela = janela
        self.base = janela.base
        self.original = pacote
        self.rfqs_criadas: list[RFQ] = []
        self._anexos_pendentes: list[Path] = []
        novo = pacote is None
        self.setWindowTitle("Nova solicitação de cotação" if novo else f"Pacote — {pacote.titulo}")
        self.resize(1080, 720)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ------------------------------------------------ cabeçalho do pacote
        grade = QGridLayout()
        grade.setHorizontalSpacing(12)
        grade.setVerticalSpacing(8)
        self.projeto = QComboBox()
        self.projeto.setMinimumWidth(280)
        self._carregar_projetos(pacote.projeto_id if pacote else None)
        self.projeto.currentIndexChanged.connect(self._atualizar_info_projeto)
        mais_projeto = QToolButton()
        mais_projeto.setText("+")
        mais_projeto.setToolTip("Cadastrar novo projeto")
        mais_projeto.clicked.connect(self._novo_projeto)
        linha_projeto = QHBoxLayout()
        linha_projeto.addWidget(self.projeto, 1)
        linha_projeto.addWidget(mais_projeto)
        self.info_projeto = QLabel()
        self.info_projeto.setObjectName("dica")

        self.solicitante = QComboBox()
        self.solicitante.addItem("—", None)
        for solicitante in sorted(self.base.solicitantes, key=lambda s: s.nome.casefold()):
            if solicitante.ativo or (pacote and pacote.solicitante_id == solicitante.id):
                self.solicitante.addItem(solicitante.nome, solicitante.id)
        if pacote:
            self.solicitante.setCurrentIndex(max(0, self.solicitante.findData(pacote.solicitante_id)))
        elif self.solicitante.count() == 2:
            self.solicitante.setCurrentIndex(1)

        self.titulo = QLineEdit(pacote.titulo if pacote else "")
        self.titulo.setPlaceholderText("Automático: projeto + data")
        self.data = CampoData(pacote.data if pacote else date.today())
        self.prazo = QSpinBox()
        self.prazo.setRange(0, 60)
        self.prazo.setSuffix(" dias úteis")
        self.prazo.setValue(pacote.prazo_dias_uteis if pacote else self.base.configuracoes.prazo_dias_uteis)
        self.prazo.setToolTip("Prazo de resposta contado a partir do envio do e-mail")

        grade.addWidget(QLabel("Projeto *"), 0, 0)
        grade.addLayout(linha_projeto, 0, 1)
        grade.addWidget(QLabel("Solicitante"), 0, 2)
        grade.addWidget(self.solicitante, 0, 3)
        grade.addWidget(QLabel(""), 1, 0)
        grade.addWidget(self.info_projeto, 1, 1)
        grade.addWidget(QLabel("Título"), 2, 0)
        grade.addWidget(self.titulo, 2, 1)
        grade.addWidget(QLabel("Data"), 2, 2)
        grade.addWidget(self.data, 2, 3)
        grade.addWidget(QLabel("Prazo de resposta"), 3, 2)
        grade.addWidget(self.prazo, 3, 3)
        grade.setColumnStretch(1, 1)
        layout.addLayout(grade)

        # ------------------------------------------------ abas
        self.abas = QTabWidget()
        layout.addWidget(self.abas, 1)

        aba_itens = QWidget()
        itens_layout = QVBoxLayout(aba_itens)
        dica = QLabel(
            "Cole os itens direto do Excel (Ctrl+V) na ordem: OP - Ref, CDC - Ref, Descrição, Unidade, "
            "Quantidade, Volume anual. Linhas vazias são ignoradas."
        )
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        itens_layout.addWidget(dica)
        self.tabela_itens = TabelaItens()
        self.tabela_itens.definir_itens(pacote.itens if pacote else [])
        if not pacote:
            for _ in range(3):
                self.tabela_itens.adicionar_linha()
        itens_layout.addWidget(self.tabela_itens, 1)
        botoes_itens = QHBoxLayout()
        botoes_itens.addWidget(botao("+ Linha", lambda: self.tabela_itens.adicionar_linha()))
        botoes_itens.addWidget(botao("Colar do Excel", self._colar))
        botoes_itens.addWidget(botao("Remover linhas", self.tabela_itens.remover_selecionadas))
        botoes_itens.addStretch()
        itens_layout.addLayout(botoes_itens)
        self.abas.addTab(aba_itens, "Itens")

        aba_fornecedores = QWidget()
        fornecedores_layout = QVBoxLayout(aba_fornecedores)
        ja_incluidos = set()
        if pacote:
            rfqs = self.base.rfqs_do_pacote(pacote.id)
            ja_incluidos = {r.fornecedor_id for r in rfqs if r.status != StatusRFQ.CANCELADA}
            if rfqs:
                resumo = QLabel(
                    "RFQs deste pacote: " + ", ".join(
                        f"{r.numero} ({self._nome_fornecedor(r.fornecedor_id)})" for r in rfqs
                    )
                )
                resumo.setWordWrap(True)
                resumo.setObjectName("dica")
                fornecedores_layout.addWidget(resumo)
        texto = (
            "Marque os fornecedores que vão receber este pacote. Cada fornecedor recebe uma RFQ com número próprio."
            if novo else "Marque novos fornecedores para enviar este mesmo pacote (uma nova RFQ para cada um)."
        )
        explicacao = QLabel(texto)
        explicacao.setWordWrap(True)
        fornecedores_layout.addWidget(explicacao)
        self.fornecedores = ListaFornecedores(janela, ja_incluidos, self._atualizar_botao)
        fornecedores_layout.addWidget(self.fornecedores, 1)
        self.abas.addTab(aba_fornecedores, "Fornecedores")

        aba_anexos = QWidget()
        anexos_layout = QVBoxLayout(aba_anexos)
        dica_anexos = QLabel("Arquivos (CDC, desenhos, especificações) anexados automaticamente a cada e-mail de RFQ.")
        dica_anexos.setObjectName("dica")
        anexos_layout.addWidget(dica_anexos)
        self.lista_anexos = QListWidget()
        self.lista_anexos.itemDoubleClicked.connect(self._abrir_anexo)
        anexos_layout.addWidget(self.lista_anexos, 1)
        botoes_anexos = QHBoxLayout()
        botoes_anexos.addWidget(botao("Adicionar arquivos…", self._adicionar_anexos))
        botoes_anexos.addWidget(botao("Remover", self._remover_anexo))
        botoes_anexos.addStretch()
        anexos_layout.addLayout(botoes_anexos)
        self.abas.addTab(aba_anexos, "Anexos")
        self._carregar_anexos()

        aba_obs = QWidget()
        obs_layout = QFormLayout(aba_obs)
        self.observacoes = QPlainTextEdit(pacote.observacoes if pacote else "")
        obs_layout.addRow("Observações internas", self.observacoes)
        self.abas.addTab(aba_obs, "Observações")

        # ------------------------------------------------ rodapé
        rodape = QHBoxLayout()
        self.aviso = QLabel()
        self.aviso.setObjectName("dica")
        rodape.addWidget(self.aviso, 1)
        rodape.addWidget(botao("Cancelar", self.reject))
        self.botao_salvar = botao("Salvar", self._salvar, primario=True)
        rodape.addWidget(self.botao_salvar)
        layout.addLayout(rodape)

        if aba_inicial == "fornecedores":
            self.abas.setCurrentIndex(1)
        self._atualizar_info_projeto()
        self._atualizar_botao()

    # ------------------------------------------------ auxiliares
    def _nome_fornecedor(self, fornecedor_id: str) -> str:
        fornecedor = self.base.fornecedores.obter(fornecedor_id)
        return fornecedor.nome if fornecedor else "?"

    def _carregar_projetos(self, selecionado: str | None) -> None:
        self.projeto.blockSignals(True)
        self.projeto.clear()
        self.projeto.addItem("Selecione o projeto…", None)
        for projeto in sorted(self.base.projetos, key=lambda p: p.nome.casefold()):
            if projeto.ativo or projeto.id == selecionado:
                texto = projeto.nome + (f"  ({projeto.cliente})" if projeto.cliente else "")
                self.projeto.addItem(texto, projeto.id)
        self.projeto.setCurrentIndex(max(0, self.projeto.findData(selecionado)))
        self.projeto.blockSignals(False)

    def _atualizar_info_projeto(self) -> None:
        projeto = self.base.projetos.obter(self.projeto.currentData())
        if not projeto:
            self.info_projeto.setText("")
            return
        partes = [f"Cliente: {projeto.cliente or '—'}", f"Planta: {projeto.planta or '—'}"]
        if projeto.lifetime_anos:
            partes.append(f"Lifetime: {projeto.lifetime_anos} anos")
        self.info_projeto.setText("   ·   ".join(partes))

    def _novo_projeto(self) -> None:
        from .dialogos_cadastro import editar_projeto

        projeto = editar_projeto(self.janela, None, self)
        if projeto:
            self._carregar_projetos(projeto.id)
            self._atualizar_info_projeto()

    def _colar(self) -> None:
        if self.tabela_itens.rowCount() and not self.tabela_itens.itens():
            self.tabela_itens.setRowCount(0)
            self.tabela_itens.adicionar_linha()
            self.tabela_itens.setCurrentCell(0, 0)
        total = self.tabela_itens.colar()
        self.aviso.setText(f"{total} linha(s) coladas." if total else "A área de transferência está vazia.")

    def _atualizar_botao(self) -> None:
        total = len(self.fornecedores.selecionados())
        if self.original is None:
            self.botao_salvar.setText(f"Criar {total} RFQ(s)" if total else "Criar RFQs")
        else:
            self.botao_salvar.setText(f"Salvar e criar {total} RFQ(s)" if total else "Salvar alterações")

    # ------------------------------------------------ anexos
    def _carregar_anexos(self) -> None:
        self.lista_anexos.clear()
        if self.original:
            for nome in self.original.anexos:
                item = QListWidgetItem(nome)
                item.setData(Qt.ItemDataRole.UserRole, str(self.base.pasta_anexos(self.original.id) / nome))
                self.lista_anexos.addItem(item)
        for caminho in self._anexos_pendentes:
            item = QListWidgetItem(f"{caminho.name}   (será anexado ao salvar)")
            item.setData(Qt.ItemDataRole.UserRole, str(caminho))
            self.lista_anexos.addItem(item)
        self.abas.setTabText(2, f"Anexos ({self.lista_anexos.count()})")

    def _adicionar_anexos(self) -> None:
        arquivos, _ = QFileDialog.getOpenFileNames(self, "Selecionar anexos")
        if not arquivos:
            return
        if self.original:
            ok, pacote = executar(self, lambda: srv.anexar_arquivos(self.base, self.original.id, [Path(a) for a in arquivos]))
            if ok:
                self.original = pacote
        else:
            self._anexos_pendentes.extend(Path(a) for a in arquivos)
        self._carregar_anexos()

    def _remover_anexo(self) -> None:
        item = self.lista_anexos.currentItem()
        if not item:
            return
        caminho = Path(item.data(Qt.ItemDataRole.UserRole))
        if caminho in self._anexos_pendentes:
            self._anexos_pendentes.remove(caminho)
        elif self.original and confirmar(self, f"Remover o anexo '{caminho.name}'?", "Remover anexo", "Remover"):
            ok, pacote = executar(self, lambda: srv.remover_anexo(self.base, self.original.id, caminho.name))
            if ok:
                self.original = pacote
        self._carregar_anexos()

    def _abrir_anexo(self, item: QListWidgetItem) -> None:
        executar(self, lambda: abrir_arquivo(Path(item.data(Qt.ItemDataRole.UserRole))))

    # ------------------------------------------------ gravação
    def _montar_pacote(self) -> Pacote:
        projeto_id = self.projeto.currentData()
        if not projeto_id:
            raise srv.ErroNegocio("Selecione o projeto.")
        dados = {
            "titulo": self.titulo.text().strip(),
            "projeto_id": projeto_id,
            "solicitante_id": self.solicitante.currentData(),
            "data": self.data.valor() or date.today(),
            "prazo_dias_uteis": self.prazo.value(),
            "observacoes": self.observacoes.toPlainText().strip(),
            "itens": self.tabela_itens.itens(),
        }
        if self.original:
            return self.original.model_copy(update=dados)
        return Pacote(**dados)

    def _salvar(self) -> None:
        fornecedores = self.fornecedores.selecionados()
        base = self.base

        def salvar():
            pacote = self._montar_pacote()
            if self.original is None:
                if not fornecedores:
                    self.abas.setCurrentIndex(1)
                    raise srv.ErroNegocio("Marque pelo menos um fornecedor na aba 'Fornecedores'.")
                pacote, rfqs = srv.criar_pacote_com_rfqs(base, pacote, fornecedores)
            else:
                pacote = srv.salvar_pacote(base, pacote)
                rfqs = srv.adicionar_fornecedores(base, pacote.id, fornecedores) if fornecedores else []
            return pacote, rfqs

        ok, resultado = executar(self, salvar)
        if not ok:
            return
        self.original, self.rfqs_criadas = resultado
        if self._anexos_pendentes:
            # O pacote já existe: uma falha aqui só avisa, sem desfazer as RFQs criadas.
            pendentes, self._anexos_pendentes = self._anexos_pendentes, []
            anexado, pacote = executar(self, lambda: srv.anexar_arquivos(base, self.original.id, pendentes))
            if anexado:
                self.original = pacote
        if self.rfqs_criadas:
            sem_email = [
                self._nome_fornecedor(r.fornecedor_id) for r in self.rfqs_criadas
                if not base.fornecedores.obter(r.fornecedor_id).emails_para()
            ]
            if sem_email:
                avisar(self, "RFQs criadas. Atenção: estes fornecedores estão sem e-mail cadastrado:\n• "
                       + "\n• ".join(sem_email))
        self.accept()
