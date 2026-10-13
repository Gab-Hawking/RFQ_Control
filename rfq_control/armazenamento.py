"""Base de dados em arquivos JSON — um arquivo por coleção (como as abas da planilha).

    dados/
    ├── configuracoes.json
    ├── fornecedores.json      (antiga aba CadastroContatos)
    ├── commodities.json       (commodities e o Commodity Buyer de cada uma)
    ├── projetos.json          (antiga aba CadastroProjetos)
    ├── solicitantes.json
    ├── feriados.json          (antiga aba Feriados)
    ├── modelos_email.json     (antiga aba CorpoEmail)
    ├── pacotes.json           (pacotes de cotação com seus itens)
    ├── rfqs.json              (antiga aba Controle)
    ├── anexos/<pacote>/       (CDC, desenhos…)
    ├── emails/                (rascunhos .eml gerados)
    ├── backup/AAAA-MM-DD/     (cópia diária automática)
    └── logs/

Cada gravação é atômica (arquivo temporário + substituição), então uma queda
de energia ou erro no meio da gravação nunca deixa um arquivo pela metade.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .modelos import (
    RFQ,
    Commodity,
    Configuracoes,
    Feriado,
    Fornecedor,
    ModeloEmail,
    Pacote,
    Projeto,
    Registro,
    Solicitante,
)
from .padroes import CORPOS_PADRAO_ANTIGOS, modelos_email_padrao
from .servicos.dias_uteis import feriados_nacionais_brasil
from .servicos.formatos import normalizar_nome

log = logging.getLogger(__name__)

VERSAO_ESQUEMA = 1
BACKUPS_MANTIDOS = 30

T = TypeVar("T", bound=Registro)


class ErroDados(Exception):
    """Problema ao ler ou gravar os arquivos da base de dados."""


def gravar_json_atomico(caminho: Path, conteudo: object) -> None:
    texto = json.dumps(conteudo, ensure_ascii=False, indent=2, default=str)
    temporario = caminho.with_name(caminho.name + ".tmp")
    with open(temporario, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(texto)
        arquivo.flush()
        os.fsync(arquivo.fileno())
    # No Windows, antivírus/indexadores podem segurar o arquivo por instantes.
    for tentativa in range(10):
        try:
            os.replace(temporario, caminho)
            return
        except PermissionError:
            time.sleep(0.1 * (tentativa + 1))
    raise ErroDados(
        f"Não foi possível gravar {caminho.name}: o arquivo está bloqueado por outro programa."
    )


def ler_json(caminho: Path) -> object:
    try:
        with open(caminho, encoding="utf-8-sig") as arquivo:
            return json.load(arquivo)
    except json.JSONDecodeError as erro:
        raise ErroDados(
            f"O arquivo {caminho.name} está corrompido (linha {erro.lineno}, coluna {erro.colno}). "
            "Restaure uma cópia da pasta 'backup'."
        ) from erro
    except OSError as erro:
        raise ErroDados(f"Não foi possível ler {caminho.name}: {erro}") from erro


def _descrever_erro_validacao(erro: ValidationError) -> str:
    partes = []
    for detalhe in erro.errors()[:5]:
        campo = ".".join(str(p) for p in detalhe["loc"]) or "registro"
        partes.append(f"{campo}: {detalhe['msg']}")
    return "; ".join(partes)


class Colecao(Generic[T]):
    """Lista de registros gravada em um arquivo JSON."""

    def __init__(self, caminho: Path, modelo: type[T], titulo: str):
        self.caminho = caminho
        self.modelo = modelo
        self.titulo = titulo
        self._itens: dict[str, T] = {}

    # ------------------------------------------------------------ leitura
    def carregar(self) -> None:
        self._itens = {}
        if not self.caminho.exists():
            return
        conteudo = ler_json(self.caminho)
        registros = conteudo.get("registros") if isinstance(conteudo, dict) else conteudo
        if not isinstance(registros, list):
            raise ErroDados(f"Formato inesperado em {self.caminho.name}: esperada uma lista de registros.")
        for posicao, bruto in enumerate(registros, start=1):
            try:
                registro = self.modelo.model_validate(bruto)
            except ValidationError as erro:
                raise ErroDados(
                    f"Registro {posicao} inválido em {self.caminho.name}: {_descrever_erro_validacao(erro)}"
                ) from erro
            if registro.id in self._itens:
                raise ErroDados(f"Identificador repetido em {self.caminho.name}: {registro.id}")
            self._itens[registro.id] = registro

    def todos(self) -> list[T]:
        return list(self._itens.values())

    def obter(self, identificador: str | None) -> T | None:
        if not identificador:
            return None
        return self._itens.get(identificador)

    def __len__(self) -> int:
        return len(self._itens)

    def __iter__(self):
        return iter(list(self._itens.values()))

    # ------------------------------------------------------------ escrita
    def gravar(self) -> None:
        conteudo = {
            "versao_esquema": VERSAO_ESQUEMA,
            "colecao": self.titulo,
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
            "registros": [r.model_dump(mode="json") for r in self._itens.values()],
        }
        gravar_json_atomico(self.caminho, conteudo)

    def validar(self, registro: T | dict) -> T:
        dados = registro.model_dump() if isinstance(registro, BaseModel) else registro
        try:
            return self.modelo.model_validate(dados)
        except ValidationError as erro:
            raise ErroDados(_descrever_erro_validacao(erro)) from erro

    def salvar(self, registro: T) -> T:
        return self.salvar_varios([registro])[0]

    def salvar_varios(self, registros: Iterable[T]) -> list[T]:
        validados = [self.validar(r) for r in registros]
        anterior = dict(self._itens)
        for registro in validados:
            self._itens[registro.id] = registro
        try:
            self.gravar()
        except Exception:
            self._itens = anterior
            raise
        return validados

    def remover(self, identificador: str) -> None:
        self.remover_varios([identificador])

    def remover_varios(self, identificadores: Iterable[str]) -> None:
        anterior = dict(self._itens)
        for identificador in identificadores:
            self._itens.pop(identificador, None)
        try:
            self.gravar()
        except Exception:
            self._itens = anterior
            raise


class BaseDados:
    """Todas as coleções do aplicativo, lidas da pasta ``dados``."""

    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self.fornecedores: Colecao[Fornecedor] = self._colecao("fornecedores", Fornecedor)
        self.commodities: Colecao[Commodity] = self._colecao("commodities", Commodity)
        self.projetos: Colecao[Projeto] = self._colecao("projetos", Projeto)
        self.solicitantes: Colecao[Solicitante] = self._colecao("solicitantes", Solicitante)
        self.feriados: Colecao[Feriado] = self._colecao("feriados", Feriado)
        self.modelos_email: Colecao[ModeloEmail] = self._colecao("modelos_email", ModeloEmail)
        self.pacotes: Colecao[Pacote] = self._colecao("pacotes", Pacote)
        self.rfqs: Colecao[RFQ] = self._colecao("rfqs", RFQ)
        self.configuracoes = Configuracoes()
        self.primeira_execucao = False

    def _colecao(self, nome: str, modelo: type[T]) -> Colecao[T]:
        return Colecao(self.pasta / f"{nome}.json", modelo, nome)

    @property
    def colecoes(self) -> list[Colecao]:
        return [
            self.fornecedores,
            self.commodities,
            self.projetos,
            self.solicitantes,
            self.feriados,
            self.modelos_email,
            self.pacotes,
            self.rfqs,
        ]

    # ------------------------------------------------------------ pastas
    @property
    def arquivo_configuracoes(self) -> Path:
        return self.pasta / "configuracoes.json"

    @property
    def pasta_backup(self) -> Path:
        return self.pasta / "backup"

    @property
    def pasta_emails(self) -> Path:
        return self.pasta / "emails"

    @property
    def pasta_logs(self) -> Path:
        return self.pasta / "logs"

    def pasta_anexos(self, pacote_id: str) -> Path:
        return self.pasta / "anexos" / pacote_id

    # ------------------------------------------------------------ abertura
    @classmethod
    def abrir(cls, pasta: Path) -> BaseDados:
        base = cls(pasta)
        try:
            base.pasta.mkdir(parents=True, exist_ok=True)
            for sub in (base.pasta_backup, base.pasta_emails, base.pasta_logs, base.pasta / "anexos"):
                sub.mkdir(exist_ok=True)
        except OSError as erro:
            raise ErroDados(f"Não foi possível criar a pasta de dados {base.pasta}: {erro}") from erro
        base.primeira_execucao = not base.arquivo_configuracoes.exists()
        base.carregar()
        if base.primeira_execucao:
            base._criar_conteudo_inicial()
        base._completar_modelos_email()
        base._completar_feriados()
        base._migrar_categorias()
        return base

    def carregar(self) -> None:
        if self.arquivo_configuracoes.exists():
            bruto = ler_json(self.arquivo_configuracoes)
            try:
                self.configuracoes = Configuracoes.model_validate(bruto)
            except ValidationError as erro:
                raise ErroDados(
                    f"configuracoes.json inválido: {_descrever_erro_validacao(erro)}"
                ) from erro
        for colecao in self.colecoes:
            colecao.carregar()

    def _criar_conteudo_inicial(self) -> None:
        self.salvar_configuracoes(self.configuracoes)
        if not len(self.modelos_email):
            self.modelos_email.salvar_varios(modelos_email_padrao())
        for colecao in self.colecoes:
            if not colecao.caminho.exists():
                colecao.gravar()

    def _completar_modelos_email(self) -> None:
        """Acrescenta os modelos padrão que faltarem e atualiza os que ainda têm o texto padrão antigo.

        Modelos editados pelo usuário nunca são alterados.
        """
        padroes = {(m.tipo, m.idioma): m for m in modelos_email_padrao()}
        existentes = {(m.tipo, m.idioma) for m in self.modelos_email}
        alterados = [m for m in padroes.values() if (m.tipo, m.idioma) not in existentes]
        for modelo in self.modelos_email:
            antigo = CORPOS_PADRAO_ANTIGOS.get((modelo.tipo, modelo.idioma))
            novo = padroes.get((modelo.tipo, modelo.idioma))
            if antigo and novo and modelo.corpo.strip() == antigo.strip():
                alterados.append(modelo.model_copy(update={"corpo": novo.corpo}))
        if alterados:
            self.modelos_email.salvar_varios(alterados)

    def _completar_feriados(self, hoje: date | None = None) -> None:
        """Gera os feriados nacionais do ano atual e do próximo, se o ano ainda não tiver nenhum.

        Evita que os prazos de um ano novo ignorem os feriados (bug B08 da planilha antiga).
        """
        ano = (hoje or date.today()).year
        anos_com_feriado = {f.data.year for f in self.feriados}
        novos = [
            Feriado(data=dia, descricao=nome)
            for a in (ano, ano + 1) if a not in anos_com_feriado
            for dia, nome in feriados_nacionais_brasil(a)
        ]
        if novos:
            self.feriados.salvar_varios(novos)

    def _migrar_categorias(self) -> None:
        """Bases até a versão 0.2: a 'Categoria' (texto) do fornecedor vira cadastro de commodities."""
        pendentes = [f for f in self.fornecedores if f.categoria.strip()]
        if not pendentes:
            return
        por_nome = {normalizar_nome(c.nome): c for c in self.commodities}
        novas: dict[str, Commodity] = {}
        fornecedores = []
        for fornecedor in pendentes:
            ids = list(fornecedor.commodity_ids)
            for nome in re.split(r"[;,/]", fornecedor.categoria):
                chave = normalizar_nome(nome)
                if not chave:
                    continue
                commodity = por_nome.get(chave)
                if commodity is None:
                    commodity = por_nome[chave] = novas[chave] = Commodity(nome=nome.strip())
                if commodity.id not in ids:
                    ids.append(commodity.id)
            fornecedores.append(fornecedor.model_copy(update={"commodity_ids": ids, "categoria": ""}))
        if novas:
            self.commodities.salvar_varios(novas.values())
        self.fornecedores.salvar_varios(fornecedores)
        log.info("Categorias de %d fornecedor(es) migradas para commodities.", len(fornecedores))

    def salvar_configuracoes(self, configuracoes: Configuracoes) -> Configuracoes:
        try:
            validado = Configuracoes.model_validate(configuracoes.model_dump())
        except ValidationError as erro:
            raise ErroDados(_descrever_erro_validacao(erro)) from erro
        gravar_json_atomico(self.arquivo_configuracoes, validado.model_dump(mode="json"))
        self.configuracoes = validado
        return validado

    # ------------------------------------------------------------ backup
    def _arquivos_json(self) -> list[Path]:
        return [self.arquivo_configuracoes] + [c.caminho for c in self.colecoes]

    def backup(self, nome: str | None = None) -> Path:
        nome = nome or datetime.now().strftime("%Y-%m-%d_%H%M%S")
        destino = self.pasta_backup / nome
        destino.mkdir(parents=True, exist_ok=True)
        for arquivo in self._arquivos_json():
            if arquivo.exists():
                shutil.copy2(arquivo, destino / arquivo.name)
        self._limpar_backups_antigos()
        return destino

    def backup_diario(self) -> Path | None:
        """Cria a cópia do dia, se ainda não existir."""
        destino = self.pasta_backup / date.today().isoformat()
        if destino.exists():
            return None
        return self.backup(destino.name)

    def _limpar_backups_antigos(self) -> None:
        pastas = sorted((p for p in self.pasta_backup.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
        for antiga in pastas[:-BACKUPS_MANTIDOS]:
            shutil.rmtree(antiga, ignore_errors=True)

    # ------------------------------------------------------------ consultas úteis
    def datas_feriados(self) -> set[date]:
        return {f.data for f in self.feriados}

    def rfqs_do_pacote(self, pacote_id: str) -> list[RFQ]:
        return sorted((r for r in self.rfqs if r.pacote_id == pacote_id), key=lambda r: r.numero)

    def rfqs_do_fornecedor(self, fornecedor_id: str) -> list[RFQ]:
        return [r for r in self.rfqs if r.fornecedor_id == fornecedor_id]

    def rfqs_do_projeto(self, projeto_id: str) -> list[RFQ]:
        pacotes = {p.id for p in self.pacotes_do_projeto(projeto_id)}
        return sorted((r for r in self.rfqs if r.pacote_id in pacotes), key=lambda r: r.numero)

    def commodities_do_fornecedor(self, fornecedor: Fornecedor) -> list[Commodity]:
        return [c for c in (self.commodities.obter(i) for i in fornecedor.commodity_ids) if c]

    def nomes_commodities(self, ids: list[str] | str | None) -> str:
        if isinstance(ids, str):
            ids = [ids]
        return ", ".join(c.nome for c in (self.commodities.obter(i) for i in ids or []) if c)

    def fornecedores_da_commodity(self, commodity_id: str) -> list[Fornecedor]:
        return [f for f in self.fornecedores if commodity_id in f.commodity_ids]

    def pacotes_do_projeto(self, projeto_id: str) -> list[Pacote]:
        return [p for p in self.pacotes if p.projeto_id == projeto_id]

    def pacotes_do_solicitante(self, solicitante_id: str) -> list[Pacote]:
        return [p for p in self.pacotes if p.solicitante_id == solicitante_id]

    def pacotes_da_commodity(self, commodity_id: str) -> list[Pacote]:
        return [p for p in self.pacotes if p.commodity_id == commodity_id]

    def projeto_do_pacote(self, pacote: Pacote | None) -> Projeto | None:
        return self.projetos.obter(pacote.projeto_id) if pacote else None
