"""Detalhes e acompanhamento de uma RFQ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..modelos import RFQ, Idioma, StatusRFQ, TipoModelo
from ..servicos import rfq as srv
from ..servicos.condicoes import condicoes_aplicaveis
from ..servicos.dias_uteis import dias_uteis_entre
from ..servicos.email_rfq import destinatarios
from ..servicos.formatos import data_curta, data_por_extenso, numero_br, valor_monetario
from . import estilo
from .componentes import MOEDAS, CampoData, Coluna, Tabela, botao, confirmar, executar
from .tabela_cotacao import TabelaCotacao

if TYPE_CHECKING:
    from .janela_principal import JanelaPrincipal


class DialogoRFQ(QDialog):
    def __init__(self, janela: JanelaPrincipal, rfq: RFQ, pai=None):
        super().__init__(pai or janela)
        self.janela = janela
        self.base = janela.base
        self.rfq = rfq
        self.alterou = False
        self.setWindowTitle(f"RFQ {rfq.numero}")
        self.resize(1240, 720)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ------------------------------------------------ cabeçalho
        topo = QHBoxLayout()
        self.titulo = QLabel()
        self.titulo.setObjectName("tituloPagina")
        self.etiqueta = QLabel()
        topo.addWidget(self.titulo)
        topo.addSpacing(10)
        topo.addWidget(self.etiqueta)
        topo.addStretch()
        layout.addLayout(topo)

        self.info = QGridLayout()
        self.info.setHorizontalSpacing(18)
        self.info.setVerticalSpacing(4)
        layout.addLayout(self.info)

        # ------------------------------------------------ abas
        abas = QTabWidget()
        layout.addWidget(abas, 1)

        acompanhamento = QWidget()
        formulario = QFormLayout(acompanhamento)
        formulario.setSpacing(10)
        self.status = QComboBox()
        for status in StatusRFQ:
            self.status.addItem(status.value, status)
        self.idioma = QComboBox()
        for idioma in Idioma:
            self.idioma.addItem(idioma.rotulo, idioma)
        self.data_envio = CampoData()
        self.prazo = CampoData()
        self.data_resposta = CampoData()
        self.observacoes = QPlainTextEdit()
        self.observacoes.setFixedHeight(90)
        formulario.addRow("Status", self.status)
        formulario.addRow("Idioma", self.idioma)
        formulario.addRow("Data de envio", self.data_envio)
        formulario.addRow("Prazo de resposta", self.prazo)
        formulario.addRow("Data da resposta", self.data_resposta)
        formulario.addRow("Observações", self.observacoes)
        abas.addTab(acompanhamento, "Acompanhamento")

        # ------------------------------------------------ cotação (resposta do fornecedor)
        aba_cotacao = QWidget()
        cotacao_layout = QVBoxLayout(aba_cotacao)
        cabecalho_cotacao = QHBoxLayout()
        dados_proposta = QFormLayout()
        self.moeda = QComboBox()
        self.moeda.setEditable(True)
        self.moeda.addItems(MOEDAS)
        self.moeda.setToolTip("Moeda de todos os valores desta proposta")
        self.validade = CampoData()
        self.validade.setToolTip("Até quando a proposta do fornecedor vale")
        dados_proposta.addRow("Moeda", self.moeda)
        dados_proposta.addRow("Validade da proposta", self.validade)
        cabecalho_cotacao.addLayout(dados_proposta)
        cabecalho_cotacao.addSpacing(24)
        totais_proposta = QFormLayout()
        self.valor = QDoubleSpinBox()
        self.valor.setRange(0, 1e12)
        self.valor.setDecimals(2)
        self.valor.setGroupSeparatorShown(True)
        self.valor.setSpecialValueText("—")
        self.valor.setToolTip("Valor total informado pelo fornecedor (opcional; aparece na lista de RFQs)")
        self.lead_time = QLineEdit()
        self.lead_time.setPlaceholderText("ex.: 12 semanas")
        self.lead_time.setToolTip("Lead time geral da proposta (texto livre)")
        totais_proposta.addRow("Valor total cotado", self.valor)
        totais_proposta.addRow("Lead time geral", self.lead_time)
        cabecalho_cotacao.addLayout(totais_proposta, 1)
        cotacao_layout.addLayout(cabecalho_cotacao)
        dica_cotacao = QLabel(
            "Digite ou cole do Excel (Ctrl+V) o preço unitário, o ferramental, o lead time (dias — ou '6 semanas'), "
            "o frete e a embalagem por peça de cada item. Ao salvar a primeira cotação de uma RFQ enviada, ela "
            "passa a Respondida."
        )
        dica_cotacao.setObjectName("dica")
        dica_cotacao.setWordWrap(True)
        cotacao_layout.addWidget(dica_cotacao)
        self.tabela_cotacao = TabelaCotacao()
        self.tabela_cotacao.alterada.connect(self._atualizar_totais)
        self.moeda.currentTextChanged.connect(lambda _t: self._atualizar_totais())
        cotacao_layout.addWidget(self.tabela_cotacao, 1)
        linha_cotacao = QHBoxLayout()
        self.totais = QLabel()
        self.totais.setObjectName("dica")
        linha_cotacao.addWidget(self.totais, 1)
        linha_cotacao.addWidget(botao("Colar do Excel", lambda: self.tabela_cotacao.colar(),
                                      dica="Cola a partir da célula selecionada (ou do preço do item selecionado)"))
        linha_cotacao.addWidget(botao("Comparativo do pacote…", self._comparativo,
                                      dica="Fornecedores do mesmo pacote lado a lado"))
        cotacao_layout.addLayout(linha_cotacao)
        self.indice_aba_cotacao = abas.addTab(aba_cotacao, "Cotação")

        aba_itens = QWidget()
        itens_layout = QVBoxLayout(aba_itens)
        self.tabela_itens = Tabela([
            Coluna("OP - Ref", lambda i: i.ref_op, largura=190),
            Coluna("CDC - Ref", lambda i: i.ref_cdc, esticar=True),
            Coluna("Descrição", lambda i: i.descricao, largura=160),
            Coluna("Unidade", lambda i: i.unidade, largura=70),
            Coluna("Quantidade", lambda i: i.quantidade, largura=95, alinhamento=Qt.AlignmentFlag.AlignRight,
                   formato=numero_br),
            Coluna("Volume anual", lambda i: i.volume_anual, largura=105, alinhamento=Qt.AlignmentFlag.AlignRight,
                   formato=numero_br),
        ])
        itens_layout.addWidget(self.tabela_itens)
        linha = QHBoxLayout()
        linha.addStretch()
        linha.addWidget(botao("Editar pacote…", self._editar_pacote))
        itens_layout.addLayout(linha)
        self.indice_aba_itens = abas.addTab(aba_itens, "Itens")
        self.abas = abas

        aba_historico = QWidget()
        historico_layout = QVBoxLayout(aba_historico)
        self.historico = QListWidget()
        historico_layout.addWidget(self.historico)
        abas.addTab(aba_historico, "Histórico")

        # ------------------------------------------------ botões
        acoes = QHBoxLayout()
        acoes.addWidget(botao("Gerar e-mail", lambda: self._email(self.idioma.currentData()),
                              dica="Abre o e-mail desta RFQ no idioma escolhido acima"))
        acoes.addWidget(botao("Cobrança", self._cobranca,
                              dica="Responde ao e-mail da RFQ (mesma conversa) lembrando o fornecedor do prazo"))
        self.botao_confirmar = botao(
            "Confirmar envio", self._confirmar_envio,
            dica="O e-mail já foi enviado: marca a RFQ como Enviada (o Outlook confirma sozinho pelos Itens Enviados)")
        acoes.addWidget(self.botao_confirmar)
        self.botao_nao_enviado = botao(
            "E-mail não enviado", self._nao_enviado,
            dica="O rascunho do e-mail foi apagado ou não saiu: a RFQ volta para Rascunho")
        acoes.addWidget(self.botao_nao_enviado)
        acoes.addWidget(botao("Selecionar como vencedora", self._vencedora))
        acoes.addStretch()
        acoes.addWidget(botao("Fechar", self.reject))
        acoes.addWidget(botao("Salvar", self._salvar, primario=True))
        layout.addLayout(acoes)

        self._carregar()
        # envio confirmado pelo Outlook com esta tela aberta: mostra a situação nova
        janela.envios_confirmados.connect(self._envios_confirmados)

    def _envios_confirmados(self, numeros: list) -> None:
        if self.rfq.numero in numeros and not self._tem_alteracoes():
            self._carregar()

    # ------------------------------------------------ exibição
    def _carregar(self) -> None:
        rfq = self.rfq = self.base.rfqs.obter(self.rfq.id) or self.rfq
        pacote = self.base.pacotes.obter(rfq.pacote_id)
        projeto = self.base.projeto_do_pacote(pacote)
        fornecedor = self.base.fornecedores.obter(rfq.fornecedor_id)

        self.titulo.setText(rfq.numero)
        situacao = rfq.situacao()
        cor = estilo.COR_SITUACAO.get(situacao, estilo.TINTA_SUAVE)
        self.etiqueta.setText(f"<span style='color:{cor}'>●</span> {situacao}")
        # pílula clara: a bolinha colorida continua visível sobre o fundo cinza
        self.etiqueta.setStyleSheet(
            f"background:{estilo.SUPERFICIE}; color:{estilo.TINTA}; border-radius:11px; padding:3px 12px;")

        while self.info.count():
            item = self.info.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        prazo = ""
        if rfq.aguardando_envio() and rfq.prazo:
            prazo = (f"{data_por_extenso(rfq.prazo, Idioma.PT)} (escrito no e-mail aberto em "
                     f"{data_curta(rfq.aguardando_envio_desde)}; gravado quando o envio for confirmado)")
        elif rfq.prazo and rfq.data_envio:
            dias = dias_uteis_entre(rfq.data_envio, rfq.prazo, self.base.datas_feriados())
            prazo = f"{data_por_extenso(rfq.prazo, Idioma.PT)} ({dias} dias úteis após o envio)"
        pares = [
            ("Fornecedor", fornecedor.nome if fornecedor else "—"),
            ("Commodity", self.base.nomes_commodities(pacote.commodity_id if pacote else None)
             or (self.base.nomes_commodities(fornecedor.commodity_ids) if fornecedor else "")),
            ("Para", "; ".join(fornecedor.emails_para()) if fornecedor else ""),
            ("Cópia", self._copia(fornecedor, pacote)),
            ("Pacote", pacote.titulo if pacote else "—"),
            ("Projeto", " · ".join(p for p in (projeto.nome, projeto.cliente, projeto.planta, projeto.regiao) if p)
             if projeto else "—"),
            ("Condições", ", ".join(c.nome for c in condicoes_aplicaveis(self.base, fornecedor, pacote, projeto))
             if fornecedor else ""),
            ("Prazo", prazo or "definido quando o e-mail for enviado"),
        ]
        for linha, (rotulo, valor) in enumerate(pares):
            titulo = QLabel(rotulo)
            titulo.setObjectName("rotuloCartao")
            texto = QLabel(valor or "—")
            texto.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            texto.setWordWrap(True)
            self.info.addWidget(titulo, linha, 0, Qt.AlignmentFlag.AlignTop)
            self.info.addWidget(texto, linha, 1)
        self.info.setColumnStretch(1, 1)

        self.botao_confirmar.setVisible(rfq.aguardando_envio())
        self.botao_nao_enviado.setVisible(rfq.aguardando_envio())
        self.status.setCurrentIndex(self.status.findData(rfq.status))
        self.idioma.setCurrentIndex(self.idioma.findData(rfq.idioma))
        self.data_envio.definir(rfq.data_envio)
        self.prazo.definir(rfq.prazo)
        self.data_resposta.definir(rfq.data_resposta)
        self.valor.setValue(rfq.valor_total or 0)
        self.moeda.setCurrentText(rfq.moeda)
        self.lead_time.setText(rfq.lead_time)
        self.validade.definir(rfq.validade)
        self.observacoes.setPlainText(rfq.observacoes)

        itens = pacote.itens if pacote else []
        self.tabela_cotacao.definir(itens, rfq.cotacao)
        self._atualizar_totais()
        self.tabela_itens.definir(itens)
        self.abas.setTabText(self.indice_aba_itens, f"Itens ({len(itens)})")
        self.historico.clear()
        for evento in reversed(rfq.historico):
            self.historico.addItem(f"{data_curta(evento.data_hora)}   {evento.descricao}")

    def _copia(self, fornecedor, pacote) -> str:
        """Cc do e-mail: Supplier (Cc) + Commodity Buyer + cópia padrão."""
        if not fornecedor or not pacote:
            return ""
        try:
            return "; ".join(destinatarios(self.base, fornecedor, [pacote])[1])
        except srv.ErroNegocio:  # fornecedor sem e-mail (Para): mostra só os da cópia do fornecedor
            return "; ".join(fornecedor.emails_copia())

    # ------------------------------------------------ ações
    def _dados_formulario(self) -> RFQ:
        # model_validate converte os valores dos combos (o Qt devolve enums como texto).
        return RFQ.model_validate({
            **self.rfq.model_dump(),
            "status": self.status.currentData(),
            "idioma": self.idioma.currentData(),
            "data_envio": self.data_envio.valor(),
            "prazo": self.prazo.valor(),
            "data_resposta": self.data_resposta.valor(),
            "valor_total": self.valor.value() or None,
            "moeda": self.moeda.currentText().strip().upper() or "BRL",
            "lead_time": self.lead_time.text().strip(),
            "validade": self.validade.valor(),
            "cotacao": [c.model_dump() for c in self.tabela_cotacao.cotacao()],
            "observacoes": self.observacoes.toPlainText().strip(),
        })

    def _tem_alteracoes(self) -> bool:
        try:
            novo = self._dados_formulario()
        except srv.ErroNegocio:
            return True  # valor inválido na cotação: salvar mostra o erro
        return any(getattr(novo, c) != getattr(self.rfq, c) for c in srv.CAMPOS_EDITAVEIS)

    def _atualizar_totais(self) -> None:
        pacote = self.base.pacotes.obter(self.rfq.pacote_id)
        itens = pacote.itens if pacote else []
        try:
            cotacao = {c.item_id: c for c in self.tabela_cotacao.cotacao()}
        except srv.ErroNegocio as erro:
            self.totais.setText(f"<span style='color:{estilo.CRITICO}'>{erro}</span>")
            return
        moeda = self.moeda.currentText().strip().upper()
        com_preco = [(i, cotacao[i.id]) for i in itens if i.id in cotacao and cotacao[i.id].preco is not None]
        pecas = sum(c.custo_unitario() * i.peso() for i, c in com_preco)
        ferramental = sum(c.ferramental or 0 for c in cotacao.values())
        self.totais.setText(
            f"{len(com_preco)} de {len(itens)} item(ns) com preço · custo das peças (× volume anual ou qtd.): "
            f"{moeda} {valor_monetario(pecas)} · ferramental: {moeda} {valor_monetario(ferramental)}"
        )

    def _comparativo(self) -> None:
        from .dialogo_comparativo import DialogoComparativo

        if not self._gravar_se_alterado():
            return
        dialogo = DialogoComparativo(self.janela, self.rfq.pacote_id, self)
        dialogo.exec()
        if dialogo.alterou:
            self.alterou = True
            self._carregar()

    def _gravar_se_alterado(self) -> bool:
        if not self._tem_alteracoes():
            return True
        # só o que foi mudado no formulário é gravado sobre o registro atual (que pode ter mudado)
        ok, rfq = executar(self, lambda: srv.salvar_rfq(self.base, self._dados_formulario(), carregada=self.rfq))
        if ok:
            self.rfq = rfq
            self.alterou = True
        return ok

    def _salvar(self) -> None:
        if self._gravar_se_alterado():
            self.janela.mensagem(f"{self.rfq.numero} salva.")
            self.accept()

    def _email(self, idioma, tipo: TipoModelo = TipoModelo.RFQ) -> None:
        from .acoes import gerar_emails

        if not self._gravar_se_alterado():
            return
        if gerar_emails(self.janela, [self.rfq], Idioma(idioma), tipo):
            self.alterou = True
            self._carregar()

    def _confirmar_envio(self) -> None:
        if not self._gravar_se_alterado():
            return
        ok, _ = executar(self, lambda: srv.confirmar_envio(self.base, self.rfq, descricao="Envio confirmado manualmente"))
        if ok:
            self.alterou = True
            self._carregar()

    def _nao_enviado(self) -> None:
        if not self._gravar_se_alterado():
            return
        ok, _ = executar(self, lambda: srv.alterar_status(self.base, [self.rfq.id], StatusRFQ.RASCUNHO))
        if ok:
            self.alterou = True
            self._carregar()

    def _cobranca(self) -> None:
        self._email(self.idioma.currentData(), TipoModelo.COBRANCA)

    def _vencedora(self) -> None:
        if not confirmar(
            self,
            "Marcar esta RFQ como selecionada? As demais RFQs respondidas do mesmo pacote serão marcadas "
            "como 'Não selecionada'.",
            "Selecionar vencedora",
            "Selecionar",
        ):
            return
        if not self._gravar_se_alterado():
            return
        ok, _ = executar(self, lambda: srv.selecionar_vencedora(self.base, self.rfq.id))
        if ok:
            self.alterou = True
            self._carregar()

    def _editar_pacote(self) -> None:
        from .acoes import abrir_pacote

        if abrir_pacote(self.janela, self.rfq.pacote_id):
            self.alterou = True
            self._carregar()

    def reject(self) -> None:  # noqa: D401 - fechar pergunta se há alterações
        if self._tem_alteracoes() and confirmar(
            self, "Há alterações não salvas. Deseja salvar antes de fechar?", "Alterações", "Salvar"
        ):
            if not self._gravar_se_alterado():
                return
        super().reject()
