"""Importação da planilha antiga RFQ_Controle.xlsm.

Mapeamento (ver docs/01-analise-planilha-legado.md):

* ``Controle``: 1 linha = 1 item de uma RFQ → agrupado em RFQs; RFQs com o
  mesmo projeto e os mesmos itens viram um único **pacote de cotação**.
* ``CadastroProjetos`` (Tabela1 A:E e solicitantes na coluna J).
* ``CadastroContatos`` (fornecedor, responsável, e-mails To/Cc/Buyer).
* ``Feriados`` (coluna A).

A importação pode ser repetida: RFQs cujo número já existe são ignoradas e
cadastros são reaproveitados pelo nome (ignorando maiúsculas e espaços).
"""

from __future__ import annotations

import re
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..armazenamento import BaseDados
from ..modelos import (
    RFQ,
    Contato,
    Evento,
    Feriado,
    Fornecedor,
    Item,
    Pacote,
    Projeto,
    Solicitante,
    StatusRFQ,
    agora,
    email_valido,
    separar_emails,
)
from .dias_uteis import somar_dias_uteis
from .formatos import ler_numero, normalizar_nome
from .rfq import proximo_numero
from .leitor_xlsx import ErroPlanilha, LeitorXlsx, Valor, data_excel

LINHAS_VAZIAS_PARA_PARAR = 2000
_REGEX_NUMERICO = re.compile(r"^\s*-?[\d.,]+\s*$")


@dataclass
class RelatorioImportacao:
    linhas_lidas: int = 0
    rfqs_importadas: int = 0
    rfqs_novas: int = 0
    rfqs_existentes: int = 0
    pacotes_criados: int = 0
    fornecedores_criados: int = 0
    projetos_criados: int = 0
    solicitantes_criados: int = 0
    feriados_criados: int = 0
    avisos: list[str] = field(default_factory=list)
    pasta_backup: Path | None = None

    def resumo(self) -> str:
        linhas = [
            f"Linhas de item lidas: {self.linhas_lidas}",
            f"RFQs importadas: {self.rfqs_importadas}",
            f"RFQs novas criadas (rascunho): {self.rfqs_novas}",
            f"Pacotes de cotação criados: {self.pacotes_criados}",
            f"Fornecedores criados: {self.fornecedores_criados}",
            f"Projetos criados: {self.projetos_criados}",
            f"Solicitantes criados: {self.solicitantes_criados}",
            f"Feriados adicionados: {self.feriados_criados}",
        ]
        if self.rfqs_existentes:
            linhas.append(f"RFQs ignoradas (número já existente): {self.rfqs_existentes}")
        return "\n".join(linhas)


def _texto(valor: Valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else str(valor)
    return re.sub(r"\s+", " ", str(valor)).strip()


def _numero(valor: Valor) -> float | None:
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, float):
        return round(valor, 4)
    if _REGEX_NUMERICO.match(str(valor)):
        numero = ler_numero(str(valor))
        return round(numero, 4) if numero is not None else None
    return None


class _Cadastros:
    """Índices por nome normalizado para reaproveitar/criar cadastros."""

    def __init__(self, base: BaseDados, relatorio: RelatorioImportacao):
        self.relatorio = relatorio
        # Cópias: os registros da base só mudam quando a gravação final acontece.
        self.projetos = {normalizar_nome(p.nome): p.model_copy(deep=True) for p in base.projetos}
        self.fornecedores = {normalizar_nome(f.nome): f.model_copy(deep=True) for f in base.fornecedores}
        self.solicitantes = {normalizar_nome(s.nome): s.model_copy(deep=True) for s in base.solicitantes}
        self.novos_projetos: dict[str, Projeto] = {}
        self.novos_fornecedores: dict[str, Fornecedor] = {}
        self.novos_solicitantes: dict[str, Solicitante] = {}
        self.alterados: set[str] = set()

    def projeto(self, nome: str, cliente: str = "", planta: str = "", origem: str = "") -> Projeto:
        chave = normalizar_nome(nome)
        existente = self.projetos.get(chave)
        if existente:
            if (cliente and not existente.cliente) or (planta and not existente.planta):
                existente.cliente = existente.cliente or cliente
                existente.planta = existente.planta or planta
                self.alterados.add(existente.id)
            return existente
        projeto = Projeto(nome=nome, cliente=cliente, planta=planta)
        self.projetos[chave] = self.novos_projetos[chave] = projeto
        if origem:
            self.relatorio.avisos.append(f"Projeto '{nome}' não estava no cadastro de projetos ({origem}); foi criado.")
        return projeto

    def fornecedor(self, nome: str, origem: str = "") -> Fornecedor:
        chave = normalizar_nome(nome)
        existente = self.fornecedores.get(chave)
        if existente:
            return existente
        fornecedor = Fornecedor(nome=nome)
        self.fornecedores[chave] = self.novos_fornecedores[chave] = fornecedor
        if origem:
            self.relatorio.avisos.append(
                f"Fornecedor '{nome}' não estava no cadastro de contatos ({origem}); foi criado sem e-mail."
            )
        return fornecedor

    def solicitante(self, nome: str) -> Solicitante:
        chave = normalizar_nome(nome)
        existente = self.solicitantes.get(chave)
        if existente:
            return existente
        solicitante = Solicitante(nome=nome)
        self.solicitantes[chave] = self.novos_solicitantes[chave] = solicitante
        return solicitante


def _contatos(nome_responsavel: str, para: str, copia: str, comprador: str, avisos: list[str], fornecedor: str) -> list[Contato]:
    contatos = []
    nome = "" if normalizar_nome(nome_responsavel) in {"", "fornecedor", "supplier"} else nome_responsavel
    for texto, eh_copia, rotulo in ((para, False, nome), (copia, True, ""), (comprador, True, "Comprador")):
        for email in separar_emails(texto.replace("mailto:", "")):
            if email_valido(email):
                contatos.append(Contato(nome=rotulo, email=email, copia=eh_copia))
            else:
                avisos.append(f"E-mail inválido ignorado para {fornecedor}: {email}")
    return contatos


@dataclass
class _LinhaControle:
    linha: int
    numero: str
    data: date | None
    solicitante: str
    cliente: str
    projeto: str
    fornecedor: str
    item: Item


def _ler_controle(leitor: LeitorXlsx, progresso: Callable[[str], None]) -> list[_LinhaControle]:
    linhas = []
    for numero_linha, valores in leitor.linhas(
        "Controle",
        inicio=2,
        coluna_chave=("A", "F"),  # número da RFQ ou fornecedor (RFQ nova sem número)
        parar_apos_vazias=LINHAS_VAZIAS_PARA_PARAR,
        progresso=lambda n: progresso(f"Lendo aba Controle… linha {n}"),
    ):
        numero = _texto(valores.get("A")).upper().replace(" ", "")
        if not numero and not (_texto(valores.get("F")) and _texto(valores.get("E"))):
            continue  # sem número, só vira RFQ nova se tiver fornecedor e projeto
        um_qtd = valores.get("J")
        quantidade = _numero(um_qtd)
        item = Item(
            ref_op=_texto(valores.get("G")),
            ref_cdc=_texto(valores.get("H")),
            descricao=_texto(valores.get("I")),
            unidade="" if quantidade is not None else _texto(um_qtd).upper(),
            quantidade=quantidade,
            volume_anual=_numero(valores.get("K")),
        )
        linhas.append(
            _LinhaControle(
                linha=numero_linha,
                numero=numero,
                data=data_excel(valores.get("B")),
                solicitante=_texto(valores.get("C")),
                cliente=_texto(valores.get("D")),
                projeto=_texto(valores.get("E")),
                fornecedor=_texto(valores.get("F")),
                item=item,
            )
        )
    return linhas


def _assinatura_itens(itens: list[Item]) -> tuple:
    return tuple(
        sorted(
            (normalizar_nome(i.ref_op), normalizar_nome(i.ref_cdc), normalizar_nome(i.descricao),
             i.unidade, i.quantidade, i.volume_anual)
            for i in itens
        )
    )


def importar_planilha(
    base: BaseDados, caminho: Path | str, progresso: Callable[[str], None] | None = None
) -> RelatorioImportacao:
    progresso = progresso or (lambda _msg: None)
    relatorio = RelatorioImportacao()
    avisos = relatorio.avisos

    with LeitorXlsx(caminho) as leitor:
        if "Controle" not in leitor.abas:
            raise ErroPlanilha("A planilha não tem a aba 'Controle'. Selecione o arquivo RFQ_Controle.xlsm.")
        progresso("Criando cópia de segurança dos dados atuais…")
        relatorio.pasta_backup = base.backup(f"antes_importacao_{agora():%Y-%m-%d_%H%M%S}")
        cadastros = _Cadastros(base, relatorio)

        # ------------------------------------------------ feriados
        novos_feriados = []
        if "Feriados" in leitor.abas:
            progresso("Lendo feriados…")
            existentes = base.datas_feriados()
            for _, valores in leitor.linhas("Feriados"):
                dia = data_excel(valores.get("A"))
                if dia and dia not in existentes:
                    existentes.add(dia)
                    novos_feriados.append(Feriado(data=dia, descricao="Importado da planilha"))

        # ------------------------------------------------ projetos e solicitantes
        if "CadastroProjetos" in leitor.abas:
            progresso("Lendo cadastro de projetos…")
            for _, valores in leitor.linhas("CadastroProjetos", inicio=2):
                nome = _texto(valores.get("C"))
                if nome:
                    projeto = cadastros.projeto(nome, _texto(valores.get("B")), _texto(valores.get("A")))
                    sop = data_excel(valores.get("D")) if isinstance(valores.get("D"), float) else None
                    lifetime = _numero(valores.get("E"))
                    if sop and not projeto.sop:
                        projeto.sop = sop
                        cadastros.alterados.add(projeto.id)
                    if lifetime and not projeto.lifetime_anos and 0 < lifetime <= 50:
                        projeto.lifetime_anos = int(lifetime)
                        cadastros.alterados.add(projeto.id)
                solicitante = _texto(valores.get("J"))
                if solicitante:
                    cadastros.solicitante(solicitante)

        # ------------------------------------------------ fornecedores
        if "CadastroContatos" in leitor.abas:
            progresso("Lendo cadastro de fornecedores…")
            vistos = set()
            for _, valores in leitor.linhas("CadastroContatos", inicio=2):
                nome = _texto(valores.get("A"))
                if not nome:
                    continue
                chave = normalizar_nome(nome)
                if chave in vistos:
                    avisos.append(f"Fornecedor repetido no cadastro de contatos: '{nome}' (mantido o primeiro).")
                    continue
                vistos.add(chave)
                fornecedor = cadastros.fornecedor(nome)
                if not fornecedor.contatos:
                    fornecedor.contatos = _contatos(
                        _texto(valores.get("B")), _texto(valores.get("C")), _texto(valores.get("D")),
                        _texto(valores.get("E")), avisos, nome,
                    )
                    cadastros.alterados.add(fornecedor.id)

        # ------------------------------------------------ controle
        progresso("Lendo aba Controle…")
        linhas = _ler_controle(leitor, progresso)
    relatorio.linhas_lidas = len(linhas)

    progresso("Organizando RFQs e pacotes…")
    por_numero: OrderedDict[str, list[_LinhaControle]] = OrderedDict()
    sem_numero: OrderedDict[tuple, list[_LinhaControle]] = OrderedDict()
    for linha in linhas:
        if linha.numero:
            por_numero.setdefault(linha.numero, []).append(linha)
        else:
            chave = (normalizar_nome(linha.projeto), normalizar_nome(linha.fornecedor), linha.data)
            sem_numero.setdefault(chave, []).append(linha)
    grupos: list[tuple[str | None, list[_LinhaControle]]] = []

    numeros_existentes = {r.numero for r in base.rfqs}
    feriados = base.datas_feriados() | {f.data for f in novos_feriados}
    prazo_padrao = base.configuracoes.prazo_dias_uteis
    pacotes: dict[tuple, Pacote] = {}
    novas_rfqs: list[RFQ] = []

    for numero, grupo in por_numero.items():
        por_fornecedor: OrderedDict[str, list[_LinhaControle]] = OrderedDict()
        for linha in grupo:
            por_fornecedor.setdefault(normalizar_nome(linha.fornecedor), []).append(linha)
        if len(por_fornecedor) > 1:
            avisos.append(
                f"{numero} tem {len(por_fornecedor)} fornecedores na planilha; "
                f"foi dividida em {', '.join(_numero_parte(numero, i) for i in range(len(por_fornecedor)))}."
            )
        for parte, linhas_rfq in enumerate(por_fornecedor.values()):
            numero_rfq = _numero_parte(numero, parte)
            if numero_rfq in numeros_existentes:
                relatorio.rfqs_existentes += 1
                continue
            numeros_existentes.add(numero_rfq)
            grupos.append((numero_rfq, linhas_rfq))
    grupos.extend((None, linhas_rfq) for linhas_rfq in sem_numero.values())

    novas_numeradas: list[str] = []
    for numero_rfq, linhas_rfq in grupos:
        nova = numero_rfq is None
        if nova:
            numero_rfq = proximo_numero(base, reservados=numeros_existentes)
            numeros_existentes.add(numero_rfq)
            novas_numeradas.append(numero_rfq)
        primeira = linhas_rfq[0]
        nomes_projeto = Counter(l.projeto for l in linhas_rfq if l.projeto)
        if len(nomes_projeto) > 1:
            avisos.append(
                f"{numero_rfq} tem itens de {len(nomes_projeto)} projetos "
                f"({', '.join(nomes_projeto)}); usado o mais frequente."
            )
        nome_projeto = nomes_projeto.most_common(1)[0][0] if nomes_projeto else "(sem projeto)"
        cliente = next((l.cliente for l in linhas_rfq if l.projeto == nome_projeto and l.cliente), "")
        projeto = cadastros.projeto(nome_projeto, cliente, origem=f"linha {primeira.linha}")
        if not primeira.fornecedor:
            avisos.append(f"{numero_rfq} (linha {primeira.linha}) está sem fornecedor.")
        fornecedor = cadastros.fornecedor(primeira.fornecedor or "(sem fornecedor)", origem=f"linha {primeira.linha}")
        solicitante = cadastros.solicitante(primeira.solicitante) if primeira.solicitante else None
        datas = [l.data for l in linhas_rfq if l.data]
        data_envio = min(datas) if datas else None
        if not data_envio and not nova:
            avisos.append(f"{numero_rfq} (linha {primeira.linha}) está sem data válida.")

        itens = [l.item for l in linhas_rfq if not l.item.vazio()]
        chave = (projeto.id, _assinatura_itens(itens))
        pacote = pacotes.get(chave)
        if pacote is None:
            pacote = Pacote(
                projeto_id=projeto.id,
                solicitante_id=solicitante.id if solicitante else None,
                data=data_envio or date.today(),
                prazo_dias_uteis=prazo_padrao,
                itens=itens,
                observacoes="Importado da planilha RFQ_Controle.xlsm",
            )
            pacotes[chave] = pacote
        elif data_envio and data_envio < pacote.data:
            pacote.data = data_envio

        linhas_texto = f"linhas {primeira.linha}–{linhas_rfq[-1].linha}"
        if nova:
            # Sem número na planilha: RFQ nova, em rascunho, pronta para o envio dos e-mails.
            rfq = RFQ(
                numero=numero_rfq,
                pacote_id=pacote.id,
                fornecedor_id=fornecedor.id,
                idioma=fornecedor.idioma,
                data_criacao=data_envio or date.today(),
                moeda=base.configuracoes.moeda_padrao,
                historico=[Evento(descricao=f"Criada pela importação em massa ({Path(caminho).name}, {linhas_texto})")],
            )
        else:
            rfq = RFQ(
                numero=numero_rfq,
                pacote_id=pacote.id,
                fornecedor_id=fornecedor.id,
                idioma=fornecedor.idioma,
                status=StatusRFQ.ENVIADA,
                data_criacao=data_envio or date.today(),
                data_envio=data_envio,
                prazo=somar_dias_uteis(data_envio, prazo_padrao, feriados) if data_envio else None,
                moeda=base.configuracoes.moeda_padrao,
                historico=[
                    Evento(
                        descricao=(
                            f"Importada da planilha {Path(caminho).name} ({linhas_texto}); "
                            "prazo estimado pela regra de dias úteis."
                        )
                    )
                ],
            )
        novas_rfqs.append(rfq)

    for pacote in pacotes.values():
        projeto = next(p for p in cadastros.projetos.values() if p.id == pacote.projeto_id)
        pacote.titulo = f"{projeto.nome} — {pacote.data:%d/%m/%Y}"

    # ------------------------------------------------ gravação
    progresso("Gravando dados…")
    novos_cadastros = [
        (base.projetos, list(cadastros.novos_projetos.values()), cadastros.projetos),
        (base.fornecedores, list(cadastros.novos_fornecedores.values()), cadastros.fornecedores),
        (base.solicitantes, list(cadastros.novos_solicitantes.values()), cadastros.solicitantes),
    ]
    for colecao, novos, indice in novos_cadastros:
        ids_novos = {r.id for r in novos}
        alterados = [r for r in indice.values() if r.id in cadastros.alterados and r.id not in ids_novos]
        if novos or alterados:
            colecao.salvar_varios(alterados + novos)
    if novos_feriados:
        base.feriados.salvar_varios(novos_feriados)
    if pacotes:
        base.pacotes.salvar_varios(list(pacotes.values()))
    if novas_rfqs:
        base.rfqs.salvar_varios(novas_rfqs)

    relatorio.projetos_criados = len(cadastros.novos_projetos)
    relatorio.fornecedores_criados = len(cadastros.novos_fornecedores)
    relatorio.solicitantes_criados = len(cadastros.novos_solicitantes)
    relatorio.feriados_criados = len(novos_feriados)
    relatorio.pacotes_criados = len(pacotes)
    relatorio.rfqs_importadas = len(novas_rfqs) - len(novas_numeradas)
    relatorio.rfqs_novas = len(novas_numeradas)
    sem_email = [f.nome for f in cadastros.fornecedores.values() if not f.emails_para()]
    if sem_email:
        avisos.append(
            f"{len(sem_email)} fornecedor(es) sem e-mail de destinatário — complete na Base de dados (Cadastro de Fornecedores) "
            "antes de gerar os e-mails."
        )
    if relatorio.rfqs_importadas:
        avisos.append(
            "As RFQs importadas ficaram com status 'Enviada' (a planilha não registrava respostas). "
            "Atualize o status das que já foram respondidas ou encerradas."
        )
    if novas_numeradas:
        avisos.append(
            f"{len(novas_numeradas)} RFQ(s) nova(s) em rascunho ({novas_numeradas[0]} a {novas_numeradas[-1]}): "
            "use 'Enviar e-mails' para disparar."
        )
    progresso("Importação concluída.")
    return relatorio


def _numero_parte(numero: str, parte: int) -> str:
    return numero if parte == 0 else f"{numero}-{parte + 1}"
