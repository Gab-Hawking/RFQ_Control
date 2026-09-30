"""Montagem do e-mail de RFQ (assunto, destinatários e corpo HTML/texto).

Substitui as macros Ctrl+E / Ctrl+R da planilha, corrigindo os bugs
documentados em docs/01-analise-planilha-legado.md (Cc sobrescrito, planta
errada, saudação genérica, data em português no e-mail em inglês, colunas
ocultas que não chegavam ao fornecedor, HTML malformado).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..armazenamento import BaseDados
from ..modelos import RFQ, Idioma, Item, ModeloEmail, Pacote, Projeto, TipoModelo
from ..padroes import modelos_email_padrao
from .formatos import data_por_extenso, numero_por_idioma
from .rfq import ErroNegocio, caminhos_anexos, prazo_para

_ESTILO_TABELA = "border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:11pt;margin:4px 0 12px 0;"
_ESTILO_TH = "border:1px solid #7f8c9d;background:#1f4e79;color:#ffffff;padding:4px 8px;text-align:left;"
_ESTILO_TD = "border:1px solid #7f8c9d;padding:4px 8px;text-align:left;vertical-align:top;"
_ESTILO_TD_ROTULO = _ESTILO_TD + "background:#dde6f0;font-weight:bold;"
_ESTILO_TD_PREENCHER = _ESTILO_TD + "background:#fff7d6;"
_ESTILO_CORPO = "font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#000000;"

_ROTULOS = {
    Idioma.PT: {
        "ref_op": "OP - Ref",
        "ref_cdc": "CDC - Ref",
        "descricao": "Descrição",
        "unidade": "UM",
        "quantidade": "Qtd",
        "volume_anual": "Volume anual",
        "capacidade": "Confirma capacidade de 120% do volume anual? [S/N]",
        "cobertura": "Cobertura máxima (%)",
        "planta": "Planta",
        "projeto": "Projeto",
        "cliente": "Cliente",
        "sop": "SOP",
        "lifetime": "Lifetime (anos)",
        "contato": "fornecedor",
    },
    Idioma.EN: {
        "ref_op": "OP - Ref",
        "ref_cdc": "CDC - Ref",
        "descricao": "Part description",
        "unidade": "UoM",
        "quantidade": "Qty",
        "volume_anual": "Annual volume",
        "capacidade": "Please confirm 120% capacity to support our Annual Volume Forecast [Y/N]",
        "cobertura": "Maximum % coverage",
        "planta": "Plant",
        "projeto": "Project",
        "cliente": "Customer",
        "sop": "SOP",
        "lifetime": "Lifetime (years)",
        "contato": "supplier",
    },
}

_CAMPOS_ITEM = ["ref_op", "ref_cdc", "descricao", "unidade", "quantidade", "volume_anual"]
_BLOCOS = {"tabela_itens", "tabela_projeto"}
_REGEX_VARIAVEL = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


@dataclass
class EmailMontado:
    para: list[str]
    copia: list[str]
    assunto: str
    html: str
    texto: str
    anexos: list[Path] = field(default_factory=list)
    prazo: date | None = None
    idioma: Idioma = Idioma.PT


# ---------------------------------------------------------------- tabelas


def _valor_item(item: Item, campo: str, idioma: Idioma) -> str:
    valor = getattr(item, campo)
    if isinstance(valor, float):
        return numero_por_idioma(valor, idioma)
    return valor or ""


def tabela_itens(itens: list[Item], idioma: Idioma, colunas_fornecedor: bool) -> tuple[str, str]:
    """Tabela HTML e versão texto dos itens; só inclui colunas com algum valor."""
    rotulos = _ROTULOS[idioma]
    campos = [c for c in _CAMPOS_ITEM if any(_valor_item(i, c, idioma) for i in itens)]
    cabecalho = [rotulos[c] for c in campos]
    if colunas_fornecedor:
        cabecalho += [rotulos["capacidade"], rotulos["cobertura"]]

    linhas_html = ["<tr>" + "".join(f'<th style="{_ESTILO_TH}">{html.escape(t)}</th>' for t in cabecalho) + "</tr>"]
    linhas_texto = [" | ".join(cabecalho)]
    for item in itens:
        valores = [_valor_item(item, c, idioma) for c in campos]
        celulas = "".join(f'<td style="{_ESTILO_TD}">{html.escape(v)}</td>' for v in valores)
        if colunas_fornecedor:
            celulas += f'<td style="{_ESTILO_TD_PREENCHER}">&nbsp;</td>' * 2
            valores += ["", ""]
        linhas_html.append(f"<tr>{celulas}</tr>")
        linhas_texto.append(" | ".join(valores))
    tabela = f'<table style="{_ESTILO_TABELA}">' + "".join(linhas_html) + "</table>"
    return tabela, "\n".join(linhas_texto)


def tabela_projeto(projeto: Projeto, idioma: Idioma) -> tuple[str, str]:
    rotulos = _ROTULOS[idioma]
    pares = [
        (rotulos["planta"], projeto.planta),
        (rotulos["projeto"], projeto.nome),
        (rotulos["cliente"], projeto.cliente),
    ]
    if projeto.sop:
        pares.append((rotulos["sop"], projeto.sop.strftime("%m/%Y")))
    if projeto.lifetime_anos:
        pares.append((rotulos["lifetime"], str(projeto.lifetime_anos)))
    pares = [(r, v) for r, v in pares if v]
    linhas = "".join(
        f'<tr><td style="{_ESTILO_TD_ROTULO}">{html.escape(r)}</td><td style="{_ESTILO_TD}">{html.escape(v)}</td></tr>'
        for r, v in pares
    )
    return f'<table style="{_ESTILO_TABELA}">{linhas}</table>', "\n".join(f"{r}: {v}" for r, v in pares)


# ---------------------------------------------------------------- modelo


def _negrito(texto_escapado: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto_escapado)


def renderizar(
    modelo: str, variaveis: dict[str, str], blocos: dict[str, tuple[str, str]]
) -> tuple[str, str]:
    """Aplica variáveis ``{{nome}}`` ao modelo e devolve (html, texto).

    Parágrafos são separados por linha em branco; ``**texto**`` vira negrito;
    ``{{tabela_itens}}`` e ``{{tabela_projeto}}`` devem ficar em linha própria.
    """

    def substituir(texto: str, escapar: bool) -> str:
        def troca(m: re.Match) -> str:
            valor = variaveis.get(m.group(1))
            if valor is None:
                return m.group(0)
            return html.escape(valor) if escapar else valor

        return _REGEX_VARIAVEL.sub(troca, texto)

    partes_html, partes_texto = [], []
    for paragrafo in re.split(r"\n\s*\n", modelo.replace("\r\n", "\n").strip()):
        paragrafo = paragrafo.strip()
        bloco = _REGEX_VARIAVEL.fullmatch(paragrafo)
        if bloco and bloco.group(1) in _BLOCOS:
            conteudo_html, conteudo_texto = blocos.get(bloco.group(1), ("", ""))
            if conteudo_html:
                partes_html.append(conteudo_html)
                partes_texto.append(conteudo_texto)
            continue
        linhas = [_negrito(substituir(html.escape(linha), escapar=True)) for linha in paragrafo.split("\n")]
        partes_html.append(f'<p style="{_ESTILO_CORPO}margin:0 0 10px 0;">' + "<br>".join(linhas) + "</p>")
        partes_texto.append(substituir(paragrafo, escapar=False).replace("**", ""))
    return "\n".join(partes_html), "\n\n".join(partes_texto)


def obter_modelo(base: BaseDados, tipo: TipoModelo, idioma: Idioma) -> ModeloEmail:
    for modelo in base.modelos_email:
        if modelo.tipo == tipo and modelo.idioma == idioma:
            return modelo
    for modelo in modelos_email_padrao():
        if modelo.tipo == tipo and modelo.idioma == idioma:
            return modelo
    raise ErroNegocio(f"Não há modelo de e-mail '{tipo.value}' em {idioma.rotulo}.")


# ---------------------------------------------------------------- montagem


def _sem_repetidos(emails: list[str], excluir: set[str] = frozenset()) -> list[str]:
    vistos, resultado = set(excluir), []
    for email in emails:
        chave = email.lower()
        if chave not in vistos:
            vistos.add(chave)
            resultado.append(email)
    return resultado


def montar_email(
    base: BaseDados,
    rfq: RFQ,
    idioma: Idioma | None = None,
    tipo: TipoModelo = TipoModelo.RFQ,
    hoje: date | None = None,
) -> EmailMontado:
    idioma = Idioma(idioma or rfq.idioma)
    pacote: Pacote | None = base.pacotes.obter(rfq.pacote_id)
    fornecedor = base.fornecedores.obter(rfq.fornecedor_id)
    if not pacote:
        raise ErroNegocio(f"O pacote da {rfq.numero} não foi encontrado.")
    if not fornecedor:
        raise ErroNegocio(f"O fornecedor da {rfq.numero} não foi encontrado.")
    projeto = base.projetos.obter(pacote.projeto_id) or Projeto(nome="?")
    solicitante = base.solicitantes.obter(pacote.solicitante_id)
    config = base.configuracoes

    para = _sem_repetidos(fornecedor.emails_para())
    if not para:
        raise ErroNegocio(
            f"O fornecedor {fornecedor.nome} não tem e-mail de destinatário (Para) cadastrado. "
            "Cadastre um contato em Fornecedores."
        )
    copia = fornecedor.emails_copia() + config.emails_copia_padrao()
    if config.copiar_solicitante and solicitante and solicitante.email:
        copia.append(solicitante.email)
    copia = _sem_repetidos(copia, excluir={e.lower() for e in para})

    prazo = rfq.prazo or prazo_para(base, pacote, hoje or date.today())
    rotulos = _ROTULOS[idioma]
    variaveis = {
        "contato": fornecedor.nome_contato() or rotulos["contato"],
        "fornecedor": fornecedor.nome,
        "empresa": config.empresa or ("nossa empresa" if idioma == Idioma.PT else "Our company"),
        "rfq": rfq.numero,
        "projeto": projeto.nome,
        "cliente": projeto.cliente,
        "planta": projeto.planta,
        "solicitante": solicitante.nome if solicitante else "",
        "pacote": pacote.titulo,
        "prazo": data_por_extenso(prazo, idioma),
    }
    blocos = {
        "tabela_itens": tabela_itens(pacote.itens, idioma, config.incluir_colunas_fornecedor),
        "tabela_projeto": tabela_projeto(projeto, idioma),
    }
    modelo = obter_modelo(base, tipo, idioma)
    corpo_html, corpo_texto = renderizar(modelo.corpo, variaveis, blocos)
    assunto, _ = renderizar(modelo.assunto, variaveis, {})
    assunto = html.unescape(re.sub(r"<[^>]+>", "", assunto)).strip()

    return EmailMontado(
        para=para,
        copia=copia,
        assunto=assunto,
        html=f'<div style="{_ESTILO_CORPO}">{corpo_html}</div>',
        texto=corpo_texto,
        anexos=caminhos_anexos(base, pacote),
        prazo=prazo,
        idioma=idioma,
    )
