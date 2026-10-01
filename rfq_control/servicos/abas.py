"""Abas da base de dados (as antigas abas da planilha) e cadastro em massa.

Cada aba de cadastro é descrita por uma ``DefinicaoAba``: as colunas que aparecem na grade e nas
planilhas de importação/exportação, e como converter uma linha (textos) em registro e vice-versa.
A mesma definição é usada pela tela "Base de dados" (edição direto nas células) e pela
importação em massa de arquivos Excel/CSV.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import BaseModel, ValidationError

from ..armazenamento import BaseDados
from ..modelos import Contato, Feriado, Fornecedor, Idioma, Projeto, Solicitante, agora, separar_emails
from . import cadastros
from .formatos import data_curta, ler_data, normalizar_nome
from .leitor_xlsx import ErroPlanilha, LeitorXlsx, Valor, data_excel, letras_coluna
from .rfq import ErroNegocio

SIM, NAO = "Sim", "Não"
IDIOMAS = tuple(i.rotulo for i in Idioma)  # ("Português", "Espanhol", "Inglês")


# ---------------------------------------------------------------- colunas e conversões


@dataclass(frozen=True)
class ColunaAba:
    chave: str
    titulo: str
    tipo: str = "texto"  # texto | data | inteiro | lista | booleano | emails
    opcoes: tuple[str, ...] = ()
    obrigatoria: bool = False
    largura: int = 150
    apelidos: tuple[str, ...] = ()  # outros cabeçalhos aceitos na importação (inclui os da planilha antiga)
    dica: str = ""


def chave_cabecalho(texto: Any) -> str:
    """'  EMAIL (To) ' → 'emailto'; 'Descrição' → 'descricao'."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or "").casefold()) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", sem_acento)


def ler_booleano(texto: str, padrao: bool = True) -> bool:
    chave = chave_cabecalho(texto)
    if not chave:
        return padrao
    if chave in {"sim", "s", "yes", "y", "true", "verdadeiro", "1", "x", "ativo"}:
        return True
    if chave in {"nao", "n", "no", "false", "falso", "0", "inativo"}:
        return False
    raise ValueError(f"valor inválido: '{texto}' (use Sim ou Não)")


def texto_booleano(valor: bool) -> str:
    return SIM if valor else NAO


def _limpar_responsavel(nome: str) -> str:
    # A planilha antiga preenchia RESPONSÁVEL com "fornecedor" quando não havia nome.
    return "" if normalizar_nome(nome) in {"fornecedor", "supplier", "proveedor"} else nome.strip()


def _validar(modelo: type[BaseModel], dados: dict, nomes: dict[str, str]) -> Any:
    try:
        return modelo.model_validate(dados)
    except ValidationError as erro:
        partes = []
        for detalhe in erro.errors()[:3]:
            campo = str(detalhe["loc"][0]) if detalhe["loc"] else ""
            mensagem = str(detalhe["msg"]).replace("Value error, ", "")
            partes.append(f"{nomes.get(campo, campo)}: {mensagem}" if campo else mensagem)
        raise ErroNegocio("; ".join(partes)) from erro


@dataclass
class DefinicaoAba:
    chave: str
    titulo: str
    nome_legado: str
    descricao: str
    colunas: list[ColunaAba]
    listar: Callable[[BaseDados], list]
    para_linha: Callable[[Any], dict[str, str]]
    de_linha: Callable[[BaseDados, dict[str, str], Any | None], Any]
    salvar: Callable[[BaseDados, Any], Any]
    chave_linha: Callable[[dict[str, str]], str]
    chave_registro: Callable[[Any], str]
    coluna_a_sem_cabecalho: str | None = None  # ex.: aba Feriados antiga (só datas na coluna A)

    def coluna(self, chave: str) -> ColunaAba:
        return next(c for c in self.colunas if c.chave == chave)

    @property
    def obrigatoria(self) -> ColunaAba:
        return next(c for c in self.colunas if c.obrigatoria)

    def nomes_campos(self) -> dict[str, str]:
        nomes = {c.chave: c.titulo for c in self.colunas}
        nomes.update({"contatos": "E-mail", "data": nomes.get("data", "Data")})
        return nomes

    def linha_vazia(self) -> dict[str, str]:
        return {c.chave: "" for c in self.colunas}

    def registro_de_linha(self, base: BaseDados, linha: dict[str, str], existente: Any | None) -> Any:
        """Converte e valida (sem gravar). Colunas ausentes em ``linha`` mantêm o valor atual."""
        obrigatoria = self.obrigatoria
        if obrigatoria.chave in linha and not str(linha[obrigatoria.chave]).strip():
            raise ErroNegocio(f"Preencha a coluna '{obrigatoria.titulo}'.")
        if existente is None and not str(linha.get(obrigatoria.chave, "")).strip():
            raise ErroNegocio(f"Preencha a coluna '{obrigatoria.titulo}'.")
        try:
            return self.de_linha(base, linha, existente)
        except ErroNegocio:
            raise
        except ValueError as erro:  # idioma, Sim/Não…
            raise ErroNegocio(str(erro)) from erro

    def gravar_linha(self, base: BaseDados, linha: dict[str, str], existente: Any | None) -> Any:
        return self.salvar(base, self.registro_de_linha(base, linha, existente))


# ---------------------------------------------------------------- fornecedores

_CHAVES_CONTATO = ("responsavel", "email_para", "email_cc", "telefone")


def _linha_fornecedor(f: Fornecedor) -> dict[str, str]:
    principal = next((c for c in f.contatos if not c.copia), None)
    return {
        "nome": f.nome,
        "responsavel": f.nome_contato(),
        "email_para": "; ".join(f.emails_para()),
        "email_cc": "; ".join(f.emails_copia()),
        "idioma": f.idioma.rotulo,
        "categoria": f.categoria,
        "telefone": principal.telefone if principal else "",
        "ativo": texto_booleano(f.ativo),
        "observacoes": f.observacoes,
    }


def _contatos_da_linha(linha: dict[str, str], existente: Fornecedor | None) -> list[Contato]:
    atual = _linha_fornecedor(existente) if existente else {c: "" for c in _CHAVES_CONTATO}
    mesclado = {c: str(linha[c]).strip() if c in linha else atual[c] for c in _CHAVES_CONTATO}
    if existente and all(mesclado[c] == atual[c] for c in _CHAVES_CONTATO):
        return existente.contatos  # nada mudou: preserva nomes e telefones de todos os contatos
    antigos = {c.email: c for c in existente.contatos if c.email} if existente else {}
    responsavel = _limpar_responsavel(mesclado["responsavel"])
    contatos: list[Contato] = []
    emails_para = separar_emails(mesclado["email_para"])
    for posicao, email in enumerate(emails_para):
        antigo = antigos.get(email)
        if posicao == 0:
            nome, telefone = responsavel, mesclado["telefone"]
        else:
            nome, telefone = (antigo.nome, antigo.telefone) if antigo else ("", "")
        contatos.append(_contato(nome, email, False, telefone))
    if not emails_para and (responsavel or mesclado["telefone"]):
        contatos.append(_contato(responsavel, "", False, mesclado["telefone"]))
    for email in separar_emails(mesclado["email_cc"]):
        if email in emails_para:
            continue
        antigo = antigos.get(email)
        contatos.append(_contato(antigo.nome if antigo else "", email, True, antigo.telefone if antigo else ""))
    return contatos


def _contato(nome: str, email: str, copia: bool, telefone: str) -> Contato:
    try:
        return Contato(nome=nome, email=email, copia=copia, telefone=telefone)
    except ValidationError as erro:
        raise ErroNegocio(f"E-mail inválido: {email}") from erro


def _fornecedor_de_linha(base: BaseDados, linha: dict[str, str], existente: Fornecedor | None) -> Fornecedor:
    dados = existente.model_dump() if existente else {}
    if "nome" in linha:
        dados["nome"] = linha["nome"]
    if str(linha.get("idioma", "")).strip():
        dados["idioma"] = Idioma.de_texto(linha["idioma"])
    for chave in ("categoria", "observacoes"):
        if chave in linha:
            dados[chave] = linha[chave]
    if "ativo" in linha:
        dados["ativo"] = ler_booleano(linha["ativo"])
    dados["contatos"] = [c.model_dump() for c in _contatos_da_linha(linha, existente)]
    return _validar(Fornecedor, dados, ABA_FORNECEDORES.nomes_campos())


ABA_FORNECEDORES = DefinicaoAba(
    chave="fornecedores",
    titulo="Cadastro de Fornecedores",
    nome_legado="CadastroContatos",
    descricao="Fornecedores, contatos e idioma dos e-mails (antiga aba CadastroContatos).",
    colunas=[
        ColunaAba("nome", "Fornecedor", obrigatoria=True, largura=220,
                  apelidos=("fornecedor", "supplier", "supplierdistributor", "nome", "razaosocial")),
        ColunaAba("responsavel", "Responsável", largura=150, apelidos=("responsavel", "contato", "nomecontato")),
        ColunaAba("email_para", "E-mail (Para)", "emails", largura=230,
                  apelidos=("emailto", "emailpara", "email", "to", "para", "destinatario"),
                  dica="Vários e-mails separados por ;"),
        ColunaAba("email_cc", "E-mail (Cc)", "emails", largura=200,
                  apelidos=("emailcc", "cc", "copia", "emailcopia", "buyeremail"),
                  dica="Vários e-mails separados por ;"),
        ColunaAba("idioma", "Idioma", "lista", IDIOMAS, largura=110, apelidos=("lingua", "language", "idiomas"),
                  dica="Idioma dos e-mails de RFQ para este fornecedor"),
        ColunaAba("categoria", "Categoria", largura=130, apelidos=("categoria", "category", "segmento")),
        ColunaAba("telefone", "Telefone", largura=120, apelidos=("telefone", "fone", "phone", "celular")),
        ColunaAba("ativo", "Ativo", "booleano", (SIM, NAO), largura=70, apelidos=("ativo", "active")),
        ColunaAba("observacoes", "Observações", largura=220, apelidos=("observacoes", "obs", "observacao", "notas")),
    ],
    listar=lambda base: sorted(base.fornecedores, key=lambda f: f.nome.casefold()),
    para_linha=_linha_fornecedor,
    de_linha=_fornecedor_de_linha,
    salvar=cadastros.salvar_fornecedor,
    chave_linha=lambda linha: normalizar_nome(linha.get("nome", "")),
    chave_registro=lambda f: normalizar_nome(f.nome),
)


# ---------------------------------------------------------------- projetos


def _inteiro(texto: str, titulo: str) -> int | None:
    texto = str(texto or "").strip()
    if not texto:
        return None
    try:
        return int(float(texto.replace(",", ".")))
    except ValueError as erro:
        raise ErroNegocio(f"{titulo}: '{texto}' não é um número inteiro.") from erro


def _data(texto: str, titulo: str) -> date | None:
    try:
        return ler_data(str(texto or ""))
    except ValueError as erro:
        raise ErroNegocio(f"{titulo}: {erro}") from erro


def _projeto_de_linha(base: BaseDados, linha: dict[str, str], existente: Projeto | None) -> Projeto:
    dados = existente.model_dump() if existente else {}
    for chave in ("nome", "cliente", "planta"):
        if chave in linha:
            dados[chave] = linha[chave]
    if "sop" in linha:
        dados["sop"] = _data(linha["sop"], "SOP")
    if "lifetime_anos" in linha:
        dados["lifetime_anos"] = _inteiro(linha["lifetime_anos"], "Lifetime (anos)")
    if "ativo" in linha:
        dados["ativo"] = ler_booleano(linha["ativo"])
    return _validar(Projeto, dados, ABA_PROJETOS.nomes_campos())


ABA_PROJETOS = DefinicaoAba(
    chave="projetos",
    titulo="Cadastro de Projetos",
    nome_legado="CadastroProjetos",
    descricao="Projetos, clientes e plantas (antiga aba CadastroProjetos).",
    colunas=[
        ColunaAba("planta", "Planta", largura=180, apelidos=("plantaop", "planta", "plant")),
        ColunaAba("cliente", "Cliente", largura=140, apelidos=("cliente", "customer")),
        ColunaAba("nome", "Projeto", obrigatoria=True, largura=240, apelidos=("projeto", "project", "nome")),
        ColunaAba("sop", "SOP", "data", largura=110, apelidos=("sop", "startofproduction"), dica="dd/mm/aaaa"),
        ColunaAba("lifetime_anos", "Lifetime (anos)", "inteiro", largura=120,
                  apelidos=("lifetimeyears", "lifetime", "lifetimeanos", "vidautil")),
        ColunaAba("ativo", "Ativo", "booleano", (SIM, NAO), largura=70, apelidos=("ativo", "active")),
    ],
    listar=lambda base: sorted(base.projetos, key=lambda p: p.nome.casefold()),
    para_linha=lambda p: {
        "planta": p.planta, "cliente": p.cliente, "nome": p.nome, "sop": data_curta(p.sop),
        "lifetime_anos": str(p.lifetime_anos or ""), "ativo": texto_booleano(p.ativo),
    },
    de_linha=_projeto_de_linha,
    salvar=cadastros.salvar_projeto,
    chave_linha=lambda linha: normalizar_nome(linha.get("nome", "")),
    chave_registro=lambda p: normalizar_nome(p.nome),
)


# ---------------------------------------------------------------- solicitantes


def _solicitante_de_linha(base: BaseDados, linha: dict[str, str], existente: Solicitante | None) -> Solicitante:
    dados = existente.model_dump() if existente else {}
    for chave in ("nome", "email"):
        if chave in linha:
            dados[chave] = linha[chave]
    if "ativo" in linha:
        dados["ativo"] = ler_booleano(linha["ativo"])
    return _validar(Solicitante, dados, ABA_SOLICITANTES.nomes_campos())


ABA_SOLICITANTES = DefinicaoAba(
    chave="solicitantes",
    titulo="Solicitantes",
    nome_legado="Requester",
    descricao="Pessoas que solicitam as cotações.",
    colunas=[
        ColunaAba("nome", "Nome", obrigatoria=True, largura=240,
                  apelidos=("nome", "solicitante", "requester", "comprador", "buyer")),
        ColunaAba("email", "E-mail", largura=260, apelidos=("email", "mail")),
        ColunaAba("ativo", "Ativo", "booleano", (SIM, NAO), largura=70, apelidos=("ativo", "active")),
    ],
    listar=lambda base: sorted(base.solicitantes, key=lambda s: s.nome.casefold()),
    para_linha=lambda s: {"nome": s.nome, "email": s.email, "ativo": texto_booleano(s.ativo)},
    de_linha=_solicitante_de_linha,
    salvar=cadastros.salvar_solicitante,
    chave_linha=lambda linha: normalizar_nome(linha.get("nome", "")),
    chave_registro=lambda s: normalizar_nome(s.nome),
)


# ---------------------------------------------------------------- feriados


def _feriado_de_linha(base: BaseDados, linha: dict[str, str], existente: Feriado | None) -> Feriado:
    dados = existente.model_dump() if existente else {}
    if "data" in linha:
        dados["data"] = _data(linha["data"], "Data")
    if "descricao" in linha:
        dados["descricao"] = linha["descricao"]
    return _validar(Feriado, dados, ABA_FERIADOS.nomes_campos())


def _chave_data(texto: str) -> str:
    try:
        dia = ler_data(str(texto or ""))
    except ValueError:
        return ""
    return dia.isoformat() if dia else ""


ABA_FERIADOS = DefinicaoAba(
    chave="feriados",
    titulo="Feriados",
    nome_legado="Feriados",
    descricao="Datas desconsideradas no cálculo do prazo em dias úteis.",
    colunas=[
        ColunaAba("data", "Data", "data", obrigatoria=True, largura=120, apelidos=("data", "date", "dia"),
                  dica="dd/mm/aaaa"),
        ColunaAba("descricao", "Descrição", largura=320, apelidos=("descricao", "feriado", "nome", "holiday")),
    ],
    listar=lambda base: sorted(base.feriados, key=lambda f: f.data, reverse=True),
    para_linha=lambda f: {"data": data_curta(f.data), "descricao": f.descricao},
    de_linha=_feriado_de_linha,
    salvar=cadastros.salvar_feriado,
    chave_linha=lambda linha: _chave_data(linha.get("data", "")),
    chave_registro=lambda f: f.data.isoformat(),
    coluna_a_sem_cabecalho="data",
)

ABAS_CADASTRO = [ABA_FORNECEDORES, ABA_PROJETOS, ABA_SOLICITANTES, ABA_FERIADOS]


# ---------------------------------------------------------------- leitura de arquivos


def _texto_celula(valor: Valor, coluna: ColunaAba) -> str:
    if valor is None:
        return ""
    if coluna.tipo == "data" and isinstance(valor, float):
        dia = data_excel(valor)
        return data_curta(dia) if dia else ""
    if coluna.tipo == "booleano" and isinstance(valor, bool):
        return texto_booleano(valor)
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else str(valor)
    return str(valor).strip()


def _linhas_csv(caminho: Path) -> list[list[str]]:
    bruto = caminho.read_bytes()
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    primeira = texto.splitlines()[0] if texto.strip() else ""
    separador = max((";", ",", "\t"), key=primeira.count) if primeira else ";"
    return [linha for linha in csv.reader(io.StringIO(texto), delimiter=separador)]


def _mapear_cabecalho(definicao: DefinicaoAba, cabecalho: dict[str, Valor]) -> dict[str, list[str]]:
    """{chave da coluna: [colunas do arquivo]} — uma chave pode juntar mais de uma coluna (ex.: Cc + Buyer)."""
    mapa: dict[str, list[str]] = {}
    for letra, texto in cabecalho.items():
        chave_arquivo = chave_cabecalho(texto)
        if not chave_arquivo:
            continue
        for coluna in definicao.colunas:
            if chave_arquivo in {chave_cabecalho(coluna.titulo), *coluna.apelidos}:
                mapa.setdefault(coluna.chave, []).append(letra)
                break
    return mapa


@dataclass
class _Tabela:
    linhas: list[tuple[int, dict[str, Valor]]]  # (número da linha no arquivo, {coluna: valor})
    mapa: dict[str, list[str]]
    cabecalhos: dict[str, str]


def _localizar_tabela(
    definicao: DefinicaoAba, linhas: Iterator[tuple[int, dict[str, Valor]]], aceitar_sem_cabecalho: bool
) -> _Tabela | None:
    """Procura o cabeçalho nas 10 primeiras linhas; sem cabeçalho, usa a coluna A se a aba permitir."""
    iniciais = []
    for numero, valores in linhas:
        iniciais.append((numero, valores))
        mapa = _mapear_cabecalho(definicao, valores)
        if definicao.obrigatoria.chave in mapa:
            cabecalhos = {letra: str(texto) for letra, texto in valores.items()}
            return _Tabela(list(linhas), mapa, cabecalhos)
        if len(iniciais) >= 10:
            break
    if aceitar_sem_cabecalho and definicao.coluna_a_sem_cabecalho and iniciais:
        return _Tabela(iniciais + list(linhas), {definicao.coluna_a_sem_cabecalho: ["A"]}, {"A": "(coluna A)"})
    return None


def _linhas_do_arquivo(definicao: DefinicaoAba, caminho: Path) -> _Tabela:
    sufixo = caminho.suffix.lower()
    if sufixo in (".csv", ".txt"):
        linhas = (
            (numero, {letras_coluna(i): v for i, v in enumerate(linha, start=1) if v.strip()})
            for numero, linha in enumerate(_linhas_csv(caminho), start=1)
        )
        tabela = _localizar_tabela(definicao, (l for l in linhas if l[1]), aceitar_sem_cabecalho=True)
        if tabela is None:
            raise ErroNegocio(_mensagem_sem_cabecalho(definicao))
        return tabela

    if sufixo not in (".xlsx", ".xlsm"):
        raise ErroNegocio("Formato não suportado. Use planilhas .xlsx/.xlsm ou arquivos .csv.")
    with LeitorXlsx(caminho) as leitor:
        preferidos = {chave_cabecalho(n) for n in (definicao.titulo, definicao.chave, definicao.nome_legado)}
        # Primeiro a aba com o nome do cadastro (ex.: 'CadastroContatos' na planilha antiga), depois as demais.
        for aba in sorted(leitor.abas, key=lambda a: chave_cabecalho(a) not in preferidos):
            # Ler sem cabeçalho só faz sentido na aba de mesmo nome ou em arquivo de uma aba só.
            sem_cabecalho = chave_cabecalho(aba) in preferidos or len(leitor.abas) == 1
            tabela = _localizar_tabela(definicao, leitor.linhas(aba, parar_apos_vazias=1000), sem_cabecalho)
            if tabela:
                return tabela
    raise ErroNegocio(_mensagem_sem_cabecalho(definicao))


def _mensagem_sem_cabecalho(definicao: DefinicaoAba) -> str:
    return (
        f"Não encontrei a coluna '{definicao.obrigatoria.titulo}' no arquivo. Use o botão 'Baixar modelo' "
        "para ver o formato esperado."
    )


# ---------------------------------------------------------------- importação em massa


@dataclass
class ResultadoImportacaoAba:
    criados: int = 0
    atualizados: int = 0
    sem_alteracao: int = 0
    erros: list[str] = field(default_factory=list)
    colunas_reconhecidas: list[str] = field(default_factory=list)
    colunas_ignoradas: list[str] = field(default_factory=list)
    pasta_backup: Path | None = None

    def resumo(self) -> str:
        partes = [
            f"Novos: {self.criados}",
            f"Atualizados: {self.atualizados}",
            f"Sem alteração: {self.sem_alteracao}",
        ]
        if self.erros:
            partes.append(f"Linhas com erro: {len(self.erros)}")
        return "\n".join(partes)


def _sem_id(registro: BaseModel) -> dict:
    dados = registro.model_dump(mode="json")
    dados.pop("id", None)
    return dados


def importar_arquivo(base: BaseDados, definicao: DefinicaoAba, caminho: Path | str) -> ResultadoImportacaoAba:
    """Cadastro em massa: cria ou atualiza (pelo nome/data) os registros de uma planilha ou CSV."""
    caminho = Path(caminho)
    try:
        tabela = _linhas_do_arquivo(definicao, caminho)
    except ErroPlanilha as erro:
        raise ErroNegocio(str(erro)) from erro
    resultado = ResultadoImportacaoAba()
    resultado.colunas_reconhecidas = [definicao.coluna(c).titulo for c in tabela.mapa]
    usadas = {letra for letras in tabela.mapa.values() for letra in letras}
    resultado.colunas_ignoradas = [t for l, t in tabela.cabecalhos.items() if l not in usadas and t.strip()]
    resultado.pasta_backup = base.backup(f"antes_importacao_{definicao.chave}_{agora():%Y-%m-%d_%H%M%S}")

    existentes = {definicao.chave_registro(r): r for r in definicao.listar(base)}
    for numero, valores in tabela.linhas:
        linha: dict[str, str] = {}
        for chave, letras in tabela.mapa.items():
            coluna = definicao.coluna(chave)
            textos = [_texto_celula(valores.get(letra), coluna) for letra in letras]
            separador = "; " if coluna.tipo == "emails" else " "
            linha[chave] = separador.join(t for t in textos if t)
        if not any(linha.values()):
            continue
        chave = definicao.chave_linha(linha)
        if not chave:
            resultado.erros.append(f"Linha {numero}: coluna '{definicao.obrigatoria.titulo}' vazia ou inválida.")
            continue
        existente = existentes.get(chave)
        try:
            registro = definicao.registro_de_linha(base, linha, existente)
            if existente is not None and _sem_id(registro) == _sem_id(existente):
                resultado.sem_alteracao += 1
                continue
            salvo = definicao.salvar(base, registro)
        except (ErroNegocio, ValueError) as erro:
            resultado.erros.append(f"Linha {numero}: {erro}")
            continue
        existentes[chave] = salvo
        if existente is None:
            resultado.criados += 1
        else:
            resultado.atualizados += 1
    return resultado


# ---------------------------------------------------------------- exportação e modelo

_FONTE_CABECALHO = Font(bold=True, color="FFFFFF")
_FUNDO_CABECALHO = PatternFill("solid", fgColor="1F4E79")
_FUNDO_OBRIGATORIA = PatternFill("solid", fgColor="C0392B")


def _planilha_da_aba(definicao: DefinicaoAba, linhas: list[dict[str, str]], destino: Path, instrucoes: bool) -> Path:
    livro = Workbook()
    aba = livro.active
    aba.title = definicao.titulo[:31]
    aba.append([c.titulo for c in definicao.colunas])
    for celula, coluna in zip(aba[1], definicao.colunas):
        celula.font = _FONTE_CABECALHO
        celula.fill = _FUNDO_OBRIGATORIA if coluna.obrigatoria else _FUNDO_CABECALHO
    for indice, coluna in enumerate(definicao.colunas, start=1):
        aba.column_dimensions[get_column_letter(indice)].width = max(12, coluna.largura // 7)
        if coluna.opcoes:
            validacao = DataValidation(type="list", formula1='"' + ",".join(coluna.opcoes) + '"', allow_blank=True)
            validacao.error = "Escolha um valor da lista: " + ", ".join(coluna.opcoes)
            validacao.prompt = coluna.dica or ("Opções: " + ", ".join(coluna.opcoes))
            aba.add_data_validation(validacao)
            letra = get_column_letter(indice)
            validacao.add(f"{letra}2:{letra}5000")
    for linha in linhas:
        aba.append([linha.get(c.chave, "") for c in definicao.colunas])
    aba.freeze_panes = "A2"
    if instrucoes:
        guia = livro.create_sheet("Instruções")
        guia.column_dimensions["A"].width = 28
        guia.column_dimensions["B"].width = 90
        guia.append([f"Importação em massa — {definicao.titulo}"])
        guia["A1"].font = Font(bold=True, size=13)
        guia.append([])
        guia.append(["Como usar", "Preencha uma linha por registro na primeira aba e importe pelo botão "
                                  "'Importar Excel/CSV' na tela Base de dados."])
        guia.append(["Registros existentes", "Linhas com o mesmo nome (ou data, nos feriados) atualizam o "
                                             "registro existente; colunas removidas da planilha não são alteradas."])
        guia.append(["Coluna em vermelho", f"'{definicao.obrigatoria.titulo}' é obrigatória."])
        for coluna in definicao.colunas:
            detalhes = coluna.dica or ""
            if coluna.opcoes:
                detalhes = (detalhes + " — " if detalhes else "") + "valores: " + ", ".join(coluna.opcoes)
            if coluna.tipo == "data":
                detalhes = detalhes or "dd/mm/aaaa"
            guia.append([coluna.titulo, detalhes])
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    livro.save(destino)
    return destino


def gerar_modelo(definicao: DefinicaoAba, destino: Path | str) -> Path:
    return _planilha_da_aba(definicao, [], Path(destino), instrucoes=True)


def exportar_aba(base: BaseDados, definicao: DefinicaoAba, destino: Path | str) -> Path:
    linhas = [definicao.para_linha(r) for r in definicao.listar(base)]
    return _planilha_da_aba(definicao, linhas, Path(destino), instrucoes=False)


CABECALHO_CONTROLE = [
    "RFQ Nº", "DATA", "SOLICITANTE", "CLIENTE", "PROJETO", "FORNECEDOR", "OP - Ref", "CDC - Ref",
    "PART DESCRIPTION", "UM / QTY", "Volume annual",
]


def gerar_modelo_controle(destino: Path | str) -> Path:
    """Planilha no formato da aba Controle antiga, para criar RFQs em massa."""
    livro = Workbook()
    aba = livro.active
    aba.title = "Controle"
    aba.append(CABECALHO_CONTROLE)
    for celula in aba[1]:
        celula.font = _FONTE_CABECALHO
        celula.fill = _FUNDO_CABECALHO
    for indice, largura in enumerate([14, 12, 18, 14, 24, 24, 28, 32, 28, 12, 14], start=1):
        aba.column_dimensions[get_column_letter(indice)].width = largura
    aba.freeze_panes = "A2"
    guia = livro.create_sheet("Instruções")
    guia.column_dimensions["A"].width = 24
    guia.column_dimensions["B"].width = 100
    textos = [
        ("Importação de RFQs", ""),
        ("", ""),
        ("Uma linha por item", "Repita RFQ/fornecedor/projeto em cada linha de item, como na aba Controle antiga."),
        ("RFQ Nº preenchido", "A RFQ é registrada com esse número como já enviada (histórico)."),
        ("RFQ Nº em branco", "O sistema cria RFQs novas em rascunho, numeradas automaticamente — uma por "
                             "fornecedor — prontas para o envio dos e-mails."),
        ("Mesmos itens", "Fornecedores com o mesmo projeto e os mesmos itens ficam no mesmo pacote de cotação."),
        ("UM / QTY", "Unidade (EA, PC…) ou quantidade numérica."),
        ("Cadastros", "Projetos, fornecedores e solicitantes que não existirem são criados automaticamente."),
    ]
    for titulo, texto in textos:
        guia.append([titulo, texto])
    guia["A1"].font = Font(bold=True, size=13)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    livro.save(destino)
    return destino
