"""Regras de negócio de pacotes de cotação e RFQs."""

from __future__ import annotations

import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..armazenamento import BaseDados
from ..modelos import (
    RFQ,
    STATUS_COM_RESPOSTA,
    Idioma,
    Pacote,
    StatusRFQ,
)
from .dias_uteis import dias_uteis_entre, somar_dias_uteis


class ErroNegocio(Exception):
    """Operação não permitida pelas regras do sistema (mensagem para o usuário)."""


# ---------------------------------------------------------------- numeração


def _padrao_numero(prefixo: str, ano: int) -> re.Pattern:
    return re.compile(rf"^{re.escape(prefixo)}{ano}(\d{{3,}})$", re.IGNORECASE)


def proximo_numero(base: BaseDados, ano: int | None = None, reservados: set[str] | None = None) -> str:
    """Próximo número livre no formato ``RFQ{AAAA}{NNN}`` (sequência por ano)."""
    ano = ano or date.today().year
    prefixo = base.configuracoes.prefixo_rfq
    padrao = _padrao_numero(prefixo, ano)
    numeros = [r.numero for r in base.rfqs] + list(reservados or ())
    maior = max((int(m.group(1)) for n in numeros if (m := padrao.match(n))), default=0)
    return f"{prefixo}{ano}{maior + 1:03d}"


# ---------------------------------------------------------------- pacotes


def prazo_para(base: BaseDados, pacote: Pacote, inicio: date | None = None) -> date:
    inicio = inicio or date.today()
    return somar_dias_uteis(inicio, pacote.prazo_dias_uteis, base.datas_feriados())


def _validar_pacote(base: BaseDados, pacote: Pacote) -> Pacote:
    if not base.projetos.obter(pacote.projeto_id):
        raise ErroNegocio("Selecione um projeto válido para o pacote.")
    if pacote.solicitante_id and not base.solicitantes.obter(pacote.solicitante_id):
        raise ErroNegocio("O solicitante selecionado não existe mais.")
    itens = [i for i in pacote.itens if not i.vazio()]
    if not itens:
        raise ErroNegocio("Inclua pelo menos um item no pacote.")
    pacote = pacote.model_copy(update={"itens": itens})
    if not pacote.titulo:
        projeto = base.projetos.obter(pacote.projeto_id)
        pacote = pacote.model_copy(update={"titulo": f"{projeto.nome} — {pacote.data:%d/%m/%Y}"})
    return pacote


def salvar_pacote(base: BaseDados, pacote: Pacote) -> Pacote:
    return base.pacotes.salvar(_validar_pacote(base, pacote))


def criar_pacote_com_rfqs(
    base: BaseDados, pacote: Pacote, fornecedor_ids: list[str]
) -> tuple[Pacote, list[RFQ]]:
    """Grava o pacote e gera uma RFQ para cada fornecedor selecionado."""
    if not fornecedor_ids:
        raise ErroNegocio("Selecione pelo menos um fornecedor.")
    pacote = _validar_pacote(base, pacote)
    _conferir_fornecedores(base, fornecedor_ids)
    pacote = base.pacotes.salvar(pacote)
    rfqs = adicionar_fornecedores(base, pacote.id, fornecedor_ids)
    return pacote, rfqs


def _conferir_fornecedores(base: BaseDados, fornecedor_ids: list[str]) -> None:
    repetidos = [f for f, n in Counter(fornecedor_ids).items() if n > 1]
    if repetidos:
        raise ErroNegocio("Há fornecedores repetidos na seleção.")
    for fornecedor_id in fornecedor_ids:
        if not base.fornecedores.obter(fornecedor_id):
            raise ErroNegocio("Um dos fornecedores selecionados não existe mais.")


def adicionar_fornecedores(base: BaseDados, pacote_id: str, fornecedor_ids: list[str]) -> list[RFQ]:
    """Envia um pacote existente para novos fornecedores (uma RFQ por fornecedor)."""
    pacote = base.pacotes.obter(pacote_id)
    if not pacote:
        raise ErroNegocio("Pacote não encontrado.")
    _conferir_fornecedores(base, fornecedor_ids)
    ja_incluidos = {
        r.fornecedor_id for r in base.rfqs_do_pacote(pacote_id) if r.status != StatusRFQ.CANCELADA
    }
    duplicados = [base.fornecedores.obter(f).nome for f in fornecedor_ids if f in ja_incluidos]
    if duplicados:
        raise ErroNegocio("Estes fornecedores já têm RFQ neste pacote: " + ", ".join(duplicados))

    reservados: set[str] = set()
    novas = []
    for fornecedor_id in fornecedor_ids:
        fornecedor = base.fornecedores.obter(fornecedor_id)
        numero = proximo_numero(base, reservados=reservados)
        reservados.add(numero)
        rfq = RFQ(
            numero=numero,
            pacote_id=pacote.id,
            fornecedor_id=fornecedor.id,
            idioma=fornecedor.idioma,
            moeda=base.configuracoes.moeda_padrao,
        )
        rfq.registrar(f"RFQ criada para {fornecedor.nome}")
        novas.append(rfq)
    return base.rfqs.salvar_varios(novas)


def duplicar_pacote(base: BaseDados, pacote_id: str) -> Pacote:
    original = base.pacotes.obter(pacote_id)
    if not original:
        raise ErroNegocio("Pacote não encontrado.")
    copia = Pacote(
        titulo=f"{original.titulo} (cópia)",
        projeto_id=original.projeto_id,
        solicitante_id=original.solicitante_id,
        prazo_dias_uteis=original.prazo_dias_uteis,
        observacoes=original.observacoes,
        itens=[i.model_copy() for i in original.itens],
    )
    origem = base.pasta_anexos(original.id)
    anexos = []
    for nome in original.anexos:
        if (origem / nome).exists():
            destino = base.pasta_anexos(copia.id)
            destino.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem / nome, destino / nome)
            anexos.append(nome)
    copia.anexos = anexos
    return base.pacotes.salvar(copia)


def excluir_pacote(base: BaseDados, pacote_id: str) -> None:
    """Exclui um pacote que ainda não foi enviado a nenhum fornecedor."""
    rfqs = base.rfqs_do_pacote(pacote_id)
    enviadas = [r.numero for r in rfqs if r.status not in (StatusRFQ.RASCUNHO, StatusRFQ.CANCELADA)]
    if enviadas:
        raise ErroNegocio(
            "O pacote já tem RFQs enviadas (" + ", ".join(enviadas) + "). "
            "Cancele as RFQs em vez de excluir o pacote."
        )
    base.rfqs.remover_varios([r.id for r in rfqs])
    base.pacotes.remover(pacote_id)
    shutil.rmtree(base.pasta_anexos(pacote_id), ignore_errors=True)


def anexar_arquivos(base: BaseDados, pacote_id: str, arquivos: list[Path]) -> Pacote:
    pacote = base.pacotes.obter(pacote_id)
    if not pacote:
        raise ErroNegocio("Salve o pacote antes de anexar arquivos.")
    destino = base.pasta_anexos(pacote_id)
    destino.mkdir(parents=True, exist_ok=True)
    nomes = list(pacote.anexos)
    for arquivo in arquivos:
        arquivo = Path(arquivo)
        if not arquivo.is_file():
            raise ErroNegocio(f"Arquivo não encontrado: {arquivo}")
        shutil.copy2(arquivo, destino / arquivo.name)
        if arquivo.name not in nomes:
            nomes.append(arquivo.name)
    return base.pacotes.salvar(pacote.model_copy(update={"anexos": nomes}))


def remover_anexo(base: BaseDados, pacote_id: str, nome: str) -> Pacote:
    pacote = base.pacotes.obter(pacote_id)
    if not pacote:
        raise ErroNegocio("Pacote não encontrado.")
    (base.pasta_anexos(pacote_id) / nome).unlink(missing_ok=True)
    nomes = [n for n in pacote.anexos if n != nome]
    return base.pacotes.salvar(pacote.model_copy(update={"anexos": nomes}))


def caminhos_anexos(base: BaseDados, pacote: Pacote) -> list[Path]:
    pasta = base.pasta_anexos(pacote.id)
    return [pasta / nome for nome in pacote.anexos if (pasta / nome).is_file()]


# ---------------------------------------------------------------- RFQs


def registrar_envio(
    base: BaseDados,
    rfq: RFQ,
    idioma: Idioma,
    descricao: str,
    hoje: date | None = None,
    prazo: date | None = None,
) -> RFQ:
    """Marca a RFQ como enviada e grava a data de envio e o prazo informado ao fornecedor."""
    hoje = hoje or date.today()
    rfq = rfq.model_copy(deep=True)
    idioma = Idioma(idioma)
    if rfq.status == StatusRFQ.RASCUNHO:
        rfq.status = StatusRFQ.ENVIADA
    if rfq.data_envio is None:
        rfq.data_envio = hoje
    if rfq.prazo is None:
        rfq.prazo = prazo or prazo_para(base, base.pacotes.obter(rfq.pacote_id), hoje)
    rfq.idioma = idioma
    rfq.registrar(descricao)
    return base.rfqs.salvar(rfq)


def alterar_status(
    base: BaseDados, rfq_ids: list[str], status: StatusRFQ, observacao: str = "", hoje: date | None = None
) -> list[RFQ]:
    hoje = hoje or date.today()
    status = StatusRFQ(status)
    alteradas = []
    for rfq_id in rfq_ids:
        rfq = base.rfqs.obter(rfq_id)
        if not rfq or rfq.status == status:
            continue
        rfq = rfq.model_copy(deep=True)
        anterior = rfq.status
        rfq.status = status
        if status in STATUS_COM_RESPOSTA and rfq.data_resposta is None:
            rfq.data_resposta = hoje
        if status == StatusRFQ.ENVIADA and rfq.data_envio is None:
            rfq.data_envio = hoje
            rfq.prazo = rfq.prazo or prazo_para(base, base.pacotes.obter(rfq.pacote_id), hoje)
        texto = f"Status alterado de {anterior.value} para {status.value}"
        rfq.registrar(f"{texto}: {observacao}" if observacao else texto)
        alteradas.append(rfq)
    return base.rfqs.salvar_varios(alteradas) if alteradas else []


def selecionar_vencedora(base: BaseDados, rfq_id: str) -> list[RFQ]:
    """Marca a RFQ como selecionada e as demais respondidas do pacote como não selecionadas."""
    vencedora = base.rfqs.obter(rfq_id)
    if not vencedora:
        raise ErroNegocio("RFQ não encontrada.")
    outras = [
        r.id for r in base.rfqs_do_pacote(vencedora.pacote_id)
        if r.id != rfq_id and r.status in (StatusRFQ.RESPONDIDA, StatusRFQ.SELECIONADA)
    ]
    resultado = alterar_status(base, [rfq_id], StatusRFQ.SELECIONADA)
    resultado += alterar_status(base, outras, StatusRFQ.NAO_SELECIONADA, "outra proposta selecionada")
    return resultado


def salvar_rfq(base: BaseDados, rfq: RFQ, descricao: str = "Dados da RFQ atualizados") -> RFQ:
    atual = base.rfqs.obter(rfq.id)
    rfq = base.rfqs.validar(rfq)
    if atual and atual.status != rfq.status:
        texto = f"Status alterado de {atual.status.value} para {rfq.status.value}"
        rfq.registrar(texto)
        if rfq.status in STATUS_COM_RESPOSTA and rfq.data_resposta is None:
            rfq.data_resposta = date.today()
    rfq.registrar(descricao)
    return base.rfqs.salvar(rfq)


def excluir_rfq(base: BaseDados, rfq_id: str) -> None:
    rfq = base.rfqs.obter(rfq_id)
    if not rfq:
        return
    if rfq.status != StatusRFQ.RASCUNHO:
        raise ErroNegocio("Só é possível excluir RFQs em rascunho. Para as demais, use o status 'Cancelada'.")
    base.rfqs.remover(rfq_id)


# ---------------------------------------------------------------- indicadores


@dataclass
class ResumoFornecedor:
    nome: str
    total: int = 0
    respondidas: int = 0
    selecionadas: int = 0
    dias_resposta: list[int] = field(default_factory=list)

    @property
    def taxa_resposta(self) -> float:
        return self.respondidas / self.total if self.total else 0.0

    @property
    def media_dias(self) -> float | None:
        return sum(self.dias_resposta) / len(self.dias_resposta) if self.dias_resposta else None


@dataclass
class Indicadores:
    total: int = 0
    rascunhos: int = 0
    em_aberto: int = 0
    atrasadas: int = 0
    respondidas: int = 0
    vencendo: int = 0
    taxa_resposta: float = 0.0
    media_dias_resposta: float | None = None
    por_mes: list[tuple[str, int]] = field(default_factory=list)
    por_situacao: dict[str, int] = field(default_factory=dict)
    fornecedores: list[ResumoFornecedor] = field(default_factory=list)
    pendencias: list[RFQ] = field(default_factory=list)


_MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def calcular_indicadores(base: BaseDados, hoje: date | None = None, meses: int = 12) -> Indicadores:
    hoje = hoje or date.today()
    feriados = base.datas_feriados()
    ind = Indicadores()
    rfqs = [r for r in base.rfqs if r.status != StatusRFQ.CANCELADA]
    ind.total = len(rfqs)

    chaves_meses = []
    ano, mes = hoje.year, hoje.month
    for _ in range(meses):
        chaves_meses.append((ano, mes))
        ano, mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    chaves_meses.reverse()
    contagem_mes: Counter = Counter()

    resumos: dict[str, ResumoFornecedor] = {}
    dias_resposta: list[int] = []
    enviadas = 0
    for rfq in rfqs:
        situacao = rfq.situacao(hoje)
        ind.por_situacao[situacao] = ind.por_situacao.get(situacao, 0) + 1
        referencia = rfq.data_envio or rfq.data_criacao
        contagem_mes[(referencia.year, referencia.month)] += 1

        if rfq.status == StatusRFQ.RASCUNHO:
            ind.rascunhos += 1
            continue
        enviadas += 1
        fornecedor = base.fornecedores.obter(rfq.fornecedor_id)
        resumo = resumos.setdefault(
            rfq.fornecedor_id, ResumoFornecedor(fornecedor.nome if fornecedor else "(excluído)")
        )
        resumo.total += 1
        if rfq.status in STATUS_COM_RESPOSTA:
            ind.respondidas += 1
            resumo.respondidas += 1
            if rfq.status == StatusRFQ.SELECIONADA:
                resumo.selecionadas += 1
            if rfq.data_envio and rfq.data_resposta:
                dias = max(0, dias_uteis_entre(rfq.data_envio, rfq.data_resposta, feriados))
                dias_resposta.append(dias)
                resumo.dias_resposta.append(dias)
        elif rfq.status == StatusRFQ.ENVIADA:
            ind.em_aberto += 1
            if rfq.atrasada(hoje):
                ind.atrasadas += 1
            elif rfq.prazo and dias_uteis_entre(hoje, rfq.prazo, feriados) <= 1:
                ind.vencendo += 1
            ind.pendencias.append(rfq)

    ind.taxa_resposta = ind.respondidas / enviadas if enviadas else 0.0
    ind.media_dias_resposta = sum(dias_resposta) / len(dias_resposta) if dias_resposta else None
    ind.por_mes = [
        (f"{_MESES_CURTOS[m - 1]}/{str(a)[2:]}", contagem_mes.get((a, m), 0)) for a, m in chaves_meses
    ]
    ind.fornecedores = sorted(resumos.values(), key=lambda r: (-r.total, r.nome))
    ind.pendencias.sort(key=lambda r: (r.prazo or date.max, r.numero))
    return ind
