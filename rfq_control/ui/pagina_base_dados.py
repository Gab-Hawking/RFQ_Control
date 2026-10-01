"""Base de dados: as antigas abas da planilha, editáveis como planilha.

Abas (embaixo, como no Excel): Controle · Cadastro de Fornecedores · Cadastro de Projetos ·
Solicitantes · Feriados · Corpo do E-mail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..modelos import RFQ, Item
from ..servicos import abas as servico_abas
from ..servicos.abas import DefinicaoAba
from ..servicos.cadastros import adicionar_feriados_nacionais
from ..servicos.envio_email import abrir_arquivo
from ..servicos.exportacao import exportar_rfqs
from ..servicos.formatos import numero_br
from . import acoes
from .componentes import (
    CaixaBusca,
    Coluna,
    DelegadoSituacao,
    Tabela,
    avisar,
    botao,
    cabecalho_pagina,
    confirmar,
    executar,
    informar,
    mostrar_resultado,
)
from .dialogos_cadastro import DialogoFeriadosNacionais, DialogoFornecedor
from .grade import GradeEditavel
from .pagina_modelos import PaginaModelos

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal

FILTRO_ARQUIVOS = "Planilhas e CSV (*.xlsx *.xlsm *.csv);;Planilhas Excel (*.xlsx *.xlsm);;CSV (*.csv)"


def _salvar_como(janela, titulo: str, nome: str) -> Path | None:
    caminho, _ = QFileDialog.getSaveFileName(janela, titulo, str(Path.home() / nome), "Planilha Excel (*.xlsx)")
    return Path(caminho) if caminho else None


def _oferecer_abrir(janela, destino: Path, titulo: str) -> None:
    janela.mensagem(f"Arquivo gerado: {destino}")
    if confirmar(janela, f"Arquivo gerado:\n{destino}\n\nAbrir agora?", titulo, "Abrir"):
        executar(janela, lambda: abrir_arquivo(destino))


# ---------------------------------------------------------------- abas de cadastro


class AbaCadastro(QWidget):
    """Uma aba de cadastro: grade editável + cadastro em massa (importar, modelo, exportar)."""

    def __init__(self, janela: JanelaPrincipal, definicao: DefinicaoAba, extras: list[QPushButton] | None = None):
        super().__init__()
        self.janela = janela
        self.definicao = definicao
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        barra = QHBoxLayout()
        self.busca = CaixaBusca(f"Buscar em {definicao.titulo.lower()}…")
        barra.addWidget(self.busca, 1)
        barra.addWidget(botao("+ Linha", self.nova_linha, dica="Nova linha no fim da tabela"))
        barra.addWidget(botao("Excluir linhas", self.excluir, perigo=True))
        for extra in extras or []:
            barra.addWidget(extra)
        barra.addSpacing(16)
        barra.addWidget(botao("Importar Excel/CSV…", self.importar, primario=True,
                              dica="Cadastro em massa: cria ou atualiza registros a partir de uma planilha"))
        barra.addWidget(botao("Baixar modelo", self.baixar_modelo, dica="Planilha vazia no formato da importação"))
        barra.addWidget(botao("Exportar", self.exportar, dica="Salva esta aba em Excel (pode ser reimportada)"))
        layout.addLayout(barra)

        dica = QLabel(
            f"{definicao.descricao} Edite direto nas células — cada linha é salva automaticamente. "
            "Cole várias linhas do Excel com Ctrl+V. Colunas com * são obrigatórias."
        )
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        layout.addWidget(dica)

        self.grade = GradeEditavel(janela.base, definicao)
        self.grade.mensagem.connect(janela.mensagem)
        self.grade.modelo.alterado.connect(self._atualizar_contador)
        self.busca.textChanged.connect(self.grade.filtro.definir_busca)
        layout.addWidget(self.grade, 1)
        self.contador = QLabel()
        self.contador.setObjectName("dica")
        layout.addWidget(self.contador)

    def atualizar(self) -> None:
        if not self.grade.modelo.pendentes():
            self.grade.modelo.carregar()
        self._atualizar_contador()

    def pendentes(self) -> int:
        return len(self.grade.modelo.pendentes())

    def descartar_pendentes(self) -> None:
        self.grade.modelo.carregar()

    def _atualizar_contador(self) -> None:
        total = sum(1 for linha in self.grade.modelo.linhas if linha.registro is not None)
        texto = f"{total} registro(s)"
        pendentes = self.pendentes()
        if pendentes:
            texto += f" · {pendentes} linha(s) não salvas (destacadas — passe o mouse para ver o motivo)"
        self.contador.setText(texto)

    # ------------------------------------------------ ações
    def nova_linha(self) -> None:
        self.grade.nova_linha()

    def excluir(self) -> None:
        linhas = self.grade.linhas_selecionadas()
        if not linhas:
            avisar(self, "Selecione uma célula das linhas que deseja excluir.")
            return
        if not confirmar(self, f"Excluir {len(linhas)} linha(s)?", "Excluir", "Excluir"):
            return
        ok, total = executar(self, lambda: self.grade.modelo.remover(linhas))
        if ok:
            self.janela.mensagem(f"{total} linha(s) excluída(s).")

    def importar(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, f"Importar {self.definicao.titulo}", str(Path.home()), FILTRO_ARQUIVOS
        )
        if not caminho:
            return
        ok, resultado = executar(
            self, lambda: servico_abas.importar_arquivo(self.janela.base, self.definicao, Path(caminho))
        )
        if not ok:
            return
        self.grade.modelo.carregar()
        detalhes = list(resultado.erros)
        if resultado.colunas_ignoradas:
            detalhes.append("Colunas ignoradas (não reconhecidas): " + ", ".join(resultado.colunas_ignoradas))
        resumo = resultado.resumo() + "\nColunas reconhecidas: " + ", ".join(resultado.colunas_reconhecidas)
        mostrar_resultado(self, f"Importação — {self.definicao.titulo}", resumo, "Detalhes", detalhes,
                          resultado.pasta_backup)

    def baixar_modelo(self) -> None:
        destino = _salvar_como(self, "Salvar modelo", f"Modelo - {self.definicao.titulo}.xlsx")
        if destino:
            ok, arquivo = executar(self, lambda: servico_abas.gerar_modelo(self.definicao, destino))
            if ok:
                _oferecer_abrir(self.janela, arquivo, "Modelo gerado")

    def exportar(self) -> None:
        destino = _salvar_como(self, "Exportar", f"{self.definicao.titulo} {date.today():%Y-%m-%d}.xlsx")
        if destino:
            ok, arquivo = executar(self, lambda: servico_abas.exportar_aba(self.janela.base, self.definicao, destino))
            if ok:
                _oferecer_abrir(self.janela, arquivo, "Exportação concluída")


# ---------------------------------------------------------------- aba Controle


@dataclass
class LinhaControle:
    """Uma linha da antiga aba Controle: um item de uma RFQ."""

    rfq: RFQ
    item: Item
    ordem: int
    solicitante: str
    cliente: str
    projeto: str
    fornecedor: str

    @property
    def id(self) -> str:
        return f"{self.rfq.id}:{self.ordem}"


def _um_qtd(item: Item) -> str:
    if item.unidade and item.quantidade is not None:
        return f"{numero_br(item.quantidade)} {item.unidade}"
    return item.unidade or numero_br(item.quantidade)


class AbaControle(QWidget):
    """Visão da antiga aba Controle: uma linha por item de cada RFQ."""

    def __init__(self, janela: JanelaPrincipal):
        super().__init__()
        self.janela = janela
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)
        barra = QHBoxLayout()
        self.busca = CaixaBusca("Buscar RFQ, fornecedor, projeto, referência…")
        barra.addWidget(self.busca, 1)
        barra.addWidget(botao("Abrir RFQ", self._abrir_atual, dica="Duplo clique na linha"))
        barra.addWidget(botao("Enviar e-mails…", self._enviar, dica="Escolher a RFQ e os fornecedores"))
        barra.addSpacing(16)
        barra.addWidget(botao("Importar RFQs (Excel)…", self._importar, primario=True,
                              dica="Planilha no formato da aba Controle (a planilha antiga ou o modelo)"))
        barra.addWidget(botao("Baixar modelo", self._modelo, dica="Modelo para criar RFQs em massa"))
        barra.addWidget(botao("Exportar", self._exportar))
        layout.addLayout(barra)
        dica = QLabel(
            "Uma linha por item de cada RFQ, como na aba Controle da planilha. Para alterar itens ou "
            "fornecedores, abra a RFQ (duplo clique) ou use Nova solicitação."
        )
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        layout.addWidget(dica)
        self.tabela = Tabela([
            Coluna("RFQ Nº", lambda l: l.rfq.numero, largura=120),
            Coluna("Data", lambda l: l.rfq.data_envio or l.rfq.data_criacao, largura=95),
            Coluna("Solicitante", lambda l: l.solicitante, largura=120),
            Coluna("Cliente", lambda l: l.cliente, largura=95),
            Coluna("Projeto", lambda l: l.projeto, largura=170),
            Coluna("Fornecedor", lambda l: l.fornecedor, largura=170),
            Coluna("OP - Ref", lambda l: l.item.ref_op, largura=170),
            Coluna("CDC - Ref", lambda l: l.item.ref_cdc, largura=230),
            Coluna("Descrição", lambda l: l.item.descricao, largura=130),
            Coluna("UM / QTY", lambda l: _um_qtd(l.item), largura=90, alinhamento=Qt.AlignmentFlag.AlignRight),
            Coluna("Volume anual", lambda l: l.item.volume_anual, largura=105,
                   alinhamento=Qt.AlignmentFlag.AlignRight, formato=numero_br),
            Coluna("Situação", lambda l: l.rfq.situacao(), largura=140),
            Coluna("Prazo", lambda l: l.rfq.prazo, largura=95),
        ])
        self.tabela.setItemDelegateForColumn(11, DelegadoSituacao(self.tabela))
        self.tabela.ativada.connect(self._abrir)
        self.busca.textChanged.connect(self.tabela.filtro.definir_busca)
        layout.addWidget(self.tabela, 1)
        self.contador = QLabel()
        self.contador.setObjectName("dica")
        layout.addWidget(self.contador)

    def atualizar(self) -> None:
        base = self.janela.base
        linhas = []
        for rfq in sorted(base.rfqs, key=lambda r: r.numero):
            pacote = base.pacotes.obter(rfq.pacote_id)
            if not pacote:
                continue
            projeto = base.projeto_do_pacote(pacote)
            fornecedor = base.fornecedores.obter(rfq.fornecedor_id)
            solicitante = base.solicitantes.obter(pacote.solicitante_id)
            for ordem, item in enumerate(pacote.itens):
                linhas.append(LinhaControle(
                    rfq, item, ordem,
                    solicitante.nome if solicitante else "",
                    projeto.cliente if projeto else "",
                    projeto.nome if projeto else "",
                    fornecedor.nome if fornecedor else "",
                ))
        self.tabela.definir(linhas)
        self.contador.setText(f"{len(linhas)} linha(s) de item · {len(base.rfqs)} RFQ(s)")

    def pendentes(self) -> int:
        return 0

    def _abrir(self, linha: LinhaControle | None) -> None:
        if linha is not None and acoes.abrir_rfq(self.janela, linha.rfq):
            self.atualizar()

    def _abrir_atual(self) -> None:
        linha = self.tabela.atual()
        if linha is None:
            avisar(self, "Selecione uma linha.")
            return
        self._abrir(linha)

    def _enviar(self) -> None:
        linha = self.tabela.atual()
        if acoes.enviar_emails(self.janela, linha.rfq.pacote_id if linha else None):
            self.atualizar()

    def _importar(self) -> None:
        from .pagina_configuracoes import importar_planilha_antiga

        if importar_planilha_antiga(self.janela, "Importar RFQs — planilha com a aba Controle"):
            self.atualizar()

    def _modelo(self) -> None:
        destino = _salvar_como(self, "Salvar modelo", "Modelo - Controle (RFQs).xlsx")
        if destino:
            ok, arquivo = executar(self, lambda: servico_abas.gerar_modelo_controle(destino))
            if ok:
                _oferecer_abrir(self.janela, arquivo, "Modelo gerado")

    def _exportar(self) -> None:
        destino = _salvar_como(self, "Exportar RFQs", f"RFQs {date.today():%Y-%m-%d}.xlsx")
        if destino:
            ok, arquivo = executar(self, lambda: exportar_rfqs(self.janela.base, destino))
            if ok:
                _oferecer_abrir(self.janela, arquivo, "Exportação concluída")


# ---------------------------------------------------------------- página


class PaginaBaseDados(QWidget):
    def __init__(self, janela: JanelaPrincipal):
        super().__init__()
        self.setObjectName("pagina")
        self.janela = janela
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(cabecalho_pagina(
            "Base de dados",
            "As antigas abas da planilha. Cada aba é um arquivo na pasta 'dados' e pode ser editada aqui, "
            "importada em massa de uma planilha ou exportada para o Excel.",
        ))

        self.controle = AbaControle(janela)
        self.fornecedores = AbaCadastro(
            janela, servico_abas.ABA_FORNECEDORES,
            [botao("Contatos detalhados…", self._contatos, dica="Vários contatos, nomes e telefones")],
        )
        self.projetos = AbaCadastro(janela, servico_abas.ABA_PROJETOS)
        self.solicitantes = AbaCadastro(janela, servico_abas.ABA_SOLICITANTES)
        self.feriados = AbaCadastro(
            janela, servico_abas.ABA_FERIADOS,
            [botao("Feriados nacionais…", self._feriados_nacionais, dica="Gera os feriados nacionais de um ano")],
        )
        self.modelos = PaginaModelos(janela, embutida=True)

        self.abas = QTabWidget()
        self.abas.setObjectName("abasPlanilha")
        self.abas.setTabPosition(QTabWidget.TabPosition.South)
        self.abas.setDocumentMode(True)
        for widget, titulo in (
            (self.controle, "Controle"),
            (self.fornecedores, "Cadastro de Fornecedores"),
            (self.projetos, "Cadastro de Projetos"),
            (self.solicitantes, "Solicitantes"),
            (self.feriados, "Feriados"),
            (self.modelos, "Corpo do E-mail"),
        ):
            self.abas.addTab(widget, titulo)
        self.abas.currentChanged.connect(lambda _: self.atualizar())
        layout.addWidget(self.abas, 1)

    @property
    def abas_cadastro(self) -> list[AbaCadastro]:
        return [self.fornecedores, self.projetos, self.solicitantes, self.feriados]

    def mostrar(self, chave: str) -> None:
        mapa = {"controle": self.controle, "fornecedores": self.fornecedores, "projetos": self.projetos,
                "solicitantes": self.solicitantes, "feriados": self.feriados, "modelos": self.modelos}
        self.abas.setCurrentWidget(mapa[chave])
        self.atualizar()

    def atualizar(self) -> None:
        atual = self.abas.currentWidget()
        if hasattr(atual, "atualizar"):
            atual.atualizar()

    def pendentes(self) -> int:
        return sum(aba.pendentes() for aba in self.abas_cadastro)

    def descartar_pendentes(self) -> None:
        for aba in self.abas_cadastro:
            if aba.pendentes():
                aba.descartar_pendentes()

    # ------------------------------------------------ ações específicas
    def _contatos(self) -> None:
        fornecedor = self.fornecedores.grade.registro_atual()
        if fornecedor is None:
            avisar(self, "Selecione um fornecedor já salvo na tabela.")
            return
        if DialogoFornecedor(self.janela, fornecedor).exec() == QDialog.DialogCode.Accepted:
            self.fornecedores.grade.modelo.carregar()

    def _feriados_nacionais(self) -> None:
        dialogo = DialogoFeriadosNacionais(self.janela)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        ok, total = executar(self, lambda: adicionar_feriados_nacionais(
            self.janela.base, dialogo.ano.value(), dialogo.carnaval.isChecked(), dialogo.corpus.isChecked()))
        if ok:
            informar(self, f"{total} feriado(s) adicionado(s) para {dialogo.ano.value()}.")
            self.feriados.grade.modelo.carregar()
