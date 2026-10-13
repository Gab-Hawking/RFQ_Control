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
from ..modelos import RFQ, Fornecedor, Idioma, Item, ModeloEmail, Pacote, Projeto, StatusRFQ, TipoModelo
from ..padroes import modelos_email_padrao
from .formatos import data_por_extenso, numero_por_idioma
from .rfq import ErroNegocio, caminhos_anexos, prazo_para

# Visual do e-mail: tabelas com cabeçalho escuro e linhas zebradas, quadro do projeto e destaque do prazo.
# Só estilos em linha e tabelas, que o Outlook (motor do Word) desenha corretamente.
FONTE = "'Segoe UI',Calibri,Arial,sans-serif"
COR_ESCURA = "#2E2E2E"
COR_DESTAQUE = "#2A78D6"
COR_TEXTO = "#1F1F1F"
COR_SUAVE = "#6B6F76"
COR_BORDA = "#D9DCE1"
COR_LINHA = "#E6E8EB"
COR_ZEBRA = "#F6F7F9"
COR_QUADRO = "#F7F8FA"
COR_PRAZO = "#FFF4D6"
COR_PRAZO_BORDA = "#F2A900"
_ESTILO_CORPO = f"font-family:{FONTE};font-size:11pt;color:{COR_TEXTO};"
_TABELA = 'cellpadding="0" cellspacing="0" border="0"'

_ROTULOS = {
    Idioma.PT: {
        "numero": "#",
        "ref_op": "OP - Ref",
        "ref_cdc": "CDC - Ref",
        "descricao": "Descrição",
        "quantidade": "Qtd.",
        "volume_anual": "Volume anual",
        "titulo_itens": "Itens para cotação",
        "titulo_projeto": "Dados do projeto",
        "planta": "Planta",
        "projeto": "Projeto",
        "cliente": "Cliente",
        "sop": "SOP",
        "lifetime": "Lifetime (anos)",
        "contato": "fornecedor",
        "empresa": "nossa empresa",
    },
    Idioma.ES: {
        "numero": "#",
        "ref_op": "OP - Ref",
        "ref_cdc": "CDC - Ref",
        "descricao": "Descripción",
        "quantidade": "Cant.",
        "volume_anual": "Volumen anual",
        "titulo_itens": "Ítems para cotizar",
        "titulo_projeto": "Datos del proyecto",
        "planta": "Planta",
        "projeto": "Proyecto",
        "cliente": "Cliente",
        "sop": "SOP",
        "lifetime": "Vida útil (años)",
        "contato": "proveedor",
        "empresa": "nuestra empresa",
    },
    Idioma.EN: {
        "numero": "#",
        "ref_op": "OP - Ref",
        "ref_cdc": "CDC - Ref",
        "descricao": "Part description",
        "quantidade": "Qty",
        "volume_anual": "Annual volume",
        "titulo_itens": "Items to quote",
        "titulo_projeto": "Project information",
        "planta": "Plant",
        "projeto": "Project",
        "cliente": "Customer",
        "sop": "SOP",
        "lifetime": "Lifetime (years)",
        "contato": "supplier",
        "empresa": "Our company",
    },
}

_CAMPOS_ITEM = ["ref_op", "ref_cdc", "descricao", "quantidade", "volume_anual"]
_SEMPRE = {"volume_anual"}  # o volume anual sempre aparece na tabela, mesmo sem valor
_NUMERICOS = {"quantidade", "volume_anual"}
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
    if campo == "quantidade":
        quantidade = numero_por_idioma(item.quantidade, idioma) if item.quantidade is not None else ""
        return " ".join(p for p in (quantidade, item.unidade) if p)
    valor = getattr(item, campo)
    if isinstance(valor, float):
        return numero_por_idioma(valor, idioma)
    return valor or ""


def _titulo_bloco(texto: str) -> str:
    return (
        f'<p style="margin:16px 0 6px 0;font-family:{FONTE};font-size:9pt;font-weight:bold;'
        f'letter-spacing:0.6px;text-transform:uppercase;color:{COR_SUAVE};">{html.escape(texto)}</p>'
    )


def tabela_itens(itens: list[Item], idioma: Idioma) -> tuple[str, str]:
    """Tabela HTML e versão texto dos itens; colunas sem nenhum valor ficam de fora (menos o volume)."""
    rotulos = _ROTULOS[idioma]
    campos = [c for c in _CAMPOS_ITEM if c in _SEMPRE or any(_valor_item(i, c, idioma) for i in itens)]

    def celula(tag: str, texto: str, campo: str, fundo: str, extra: str = "") -> str:
        alinhamento = "right" if campo in _NUMERICOS else "left"
        if tag == "th":
            estilo = (f"background:{COR_ESCURA};color:#FFFFFF;font-family:{FONTE};font-size:9pt;font-weight:bold;"
                      f"letter-spacing:0.3px;padding:9px 12px;border-bottom:3px solid {COR_DESTAQUE};"
                      f"text-align:{alinhamento};white-space:nowrap;")
        else:
            estilo = (f"background:{fundo};font-family:{FONTE};font-size:10.5pt;color:{COR_TEXTO};"
                      f"padding:8px 12px;border-bottom:1px solid {COR_LINHA};text-align:{alinhamento};"
                      f"vertical-align:top;")
        return f'<{tag} bgcolor="{fundo}" style="{estilo}{extra}">{texto}</{tag}>'

    cabecalho = celula("th", rotulos["numero"], "", COR_ESCURA, "width:28px;") + "".join(
        celula("th", html.escape(rotulos[c]), c, COR_ESCURA) for c in campos
    )
    linhas_html = [f"<tr>{cabecalho}</tr>"]
    linhas_texto = [" | ".join([rotulos["numero"]] + [rotulos[c] for c in campos])]
    for posicao, item in enumerate(itens, start=1):
        fundo = "#FFFFFF" if posicao % 2 else COR_ZEBRA
        valores = [_valor_item(item, c, idioma) for c in campos]
        celulas = celula("td", str(posicao), "", fundo, f"color:{COR_SUAVE};width:28px;") + "".join(
            celula("td", html.escape(v) if v else f'<span style="color:{COR_SUAVE};">—</span>', c, fundo)
            for c, v in zip(campos, valores)
        )
        linhas_html.append(f"<tr>{celulas}</tr>")
        linhas_texto.append(" | ".join([str(posicao)] + [v or "-" for v in valores]))
    tabela = (
        f'<table {_TABELA} width="100%" style="border-collapse:collapse;border:1px solid {COR_BORDA};'
        f'margin:0 0 14px 0;width:100%;">' + "".join(linhas_html) + "</table>"
    )
    titulo = f"{rotulos['titulo_itens']} ({len(itens)})"
    return _titulo_bloco(titulo) + tabela, titulo + "\n" + "\n".join(linhas_texto)


def tabela_projeto(projeto: Projeto, idioma: Idioma) -> tuple[str, str]:
    """Quadro com os dados do projeto lado a lado (rótulo pequeno em cima, valor em negrito)."""
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
    if not pares:
        return "", ""
    celulas = []
    for posicao, (rotulo, valor) in enumerate(pares):
        divisoria = f"border-left:1px solid {COR_LINHA};" if posicao else ""
        celulas.append(
            f'<td bgcolor="{COR_QUADRO}" style="background:{COR_QUADRO};padding:10px 22px 10px 14px;'
            f'vertical-align:top;font-family:{FONTE};{divisoria}">'
            f'<div style="font-size:8pt;color:{COR_SUAVE};text-transform:uppercase;letter-spacing:0.5px;">'
            f"{html.escape(rotulo)}</div>"
            f'<div style="font-size:11pt;font-weight:bold;color:{COR_TEXTO};padding-top:2px;">{html.escape(valor)}</div>'
            "</td>"
        )
    quadro = (
        f'<table {_TABELA} style="border-collapse:collapse;border:1px solid {COR_BORDA};'
        f'border-left:4px solid {COR_DESTAQUE};margin:0 0 14px 0;"><tr>' + "".join(celulas) + "</tr></table>"
    )
    texto = "\n".join(f"{r}: {v}" for r, v in pares)
    return _titulo_bloco(rotulos["titulo_projeto"]) + quadro, rotulos["titulo_projeto"] + "\n" + texto


def _quadro_destaque(conteudo_html: str) -> str:
    return (
        f'<table {_TABELA} style="border-collapse:collapse;margin:6px 0 14px 0;"><tr>'
        f'<td bgcolor="{COR_PRAZO}" style="background:{COR_PRAZO};border-left:4px solid {COR_PRAZO_BORDA};'
        f'padding:10px 18px;font-family:{FONTE};font-size:11pt;color:{COR_TEXTO};">{conteudo_html}</td>'
        "</tr></table>"
    )


# ---------------------------------------------------------------- modelo


def _negrito(texto_escapado: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto_escapado)


def renderizar(
    modelo: str, variaveis: dict[str, str], blocos: dict[str, tuple[str, str]]
) -> tuple[str, str]:
    """Aplica variáveis ``{{nome}}`` ao modelo e devolve (html, texto).

    Parágrafos são separados por linha em branco; ``**texto**`` vira negrito e um parágrafo inteiro
    em negrito vira um quadro de destaque (como o prazo); ``{{tabela_itens}}`` e ``{{tabela_projeto}}``
    devem ficar em linha própria. Parágrafos que ficam vazios depois das variáveis são omitidos.
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
        texto = substituir(paragrafo, escapar=False)
        if not texto.replace("*", "").strip():
            continue
        linhas = [_negrito(substituir(html.escape(linha), escapar=True)) for linha in paragrafo.split("\n")]
        conteudo = "<br>".join(linhas)
        if paragrafo.startswith("**") and paragrafo.endswith("**") and paragrafo.count("**") == 2:
            partes_html.append(_quadro_destaque(conteudo))
        else:
            partes_html.append(f'<p style="{_ESTILO_CORPO}margin:0 0 10px 0;">{conteudo}</p>')
        partes_texto.append(texto.replace("**", ""))
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


def idioma_padrao(rfq: RFQ, fornecedor: Fornecedor) -> Idioma:
    """RFQ ainda não enviada segue o idioma atual do fornecedor; já enviada, o idioma em que foi enviada."""
    return fornecedor.idioma if rfq.status == StatusRFQ.RASCUNHO else rfq.idioma


def emails_commodity_buyer(base: BaseDados, fornecedor: Fornecedor, pacotes: list[Pacote]) -> list[str]:
    """Commodity Buyer em cópia: o da commodity do pacote; sem commodity no pacote, os do fornecedor."""
    ids = [p.commodity_id for p in pacotes if p.commodity_id] or fornecedor.commodity_ids
    commodities = (base.commodities.obter(i) for i in dict.fromkeys(ids))
    return [c.email for c in commodities if c and c.email]


def destinatarios(
    base: BaseDados, fornecedor: Fornecedor, pacotes: list[Pacote]
) -> tuple[list[str], list[str]]:
    """(Para, Cc): Cc = fornecedor (Supplier) + Commodity Buyer + cópia padrão (+ solicitante)."""
    config = base.configuracoes
    para = _sem_repetidos(fornecedor.emails_para())
    if not para:
        raise ErroNegocio(
            f"O fornecedor {fornecedor.nome} não tem e-mail de destinatário (Para) cadastrado. "
            "Cadastre o e-mail na Base de dados (Fornecedores)."
        )
    copia = fornecedor.emails_copia() + emails_commodity_buyer(base, fornecedor, pacotes) + config.emails_copia_padrao()
    if config.copiar_solicitante:
        for pacote in pacotes:
            solicitante = base.solicitantes.obter(pacote.solicitante_id)
            if solicitante and solicitante.email:
                copia.append(solicitante.email)
    return para, _sem_repetidos(copia, excluir={e.lower() for e in para})


def _assunto(modelo: ModeloEmail, variaveis: dict[str, str]) -> str:
    assunto, _ = renderizar(modelo.assunto, variaveis, {})
    return html.unescape(re.sub(r"<[^>]+>", "", assunto)).strip()


def montar_email(
    base: BaseDados,
    rfq: RFQ,
    idioma: Idioma | None = None,
    tipo: TipoModelo = TipoModelo.RFQ,
    hoje: date | None = None,
) -> EmailMontado:
    pacote: Pacote | None = base.pacotes.obter(rfq.pacote_id)
    fornecedor = base.fornecedores.obter(rfq.fornecedor_id)
    if not pacote:
        raise ErroNegocio(f"O pacote da {rfq.numero} não foi encontrado.")
    if not fornecedor:
        raise ErroNegocio(f"O fornecedor da {rfq.numero} não foi encontrado.")
    idioma = Idioma(idioma or idioma_padrao(rfq, fornecedor))
    projeto = base.projetos.obter(pacote.projeto_id) or Projeto(nome="?")
    solicitante = base.solicitantes.obter(pacote.solicitante_id)
    config = base.configuracoes
    para, copia = destinatarios(base, fornecedor, [pacote])

    # Em rascunho o prazo ainda é uma proposta: vale o calculado a partir de hoje.
    if rfq.status == StatusRFQ.RASCUNHO or rfq.prazo is None:
        prazo = prazo_para(base, pacote, hoje or date.today())
    else:
        prazo = rfq.prazo
    rotulos = _ROTULOS[idioma]
    variaveis = {
        "contato": fornecedor.nome_contato() or rotulos["contato"],
        "fornecedor": fornecedor.nome,
        "empresa": config.empresa or rotulos["empresa"],
        "rfq": rfq.numero,
        "rfqs": rfq.numero,
        "projeto": projeto.nome,
        "cliente": projeto.cliente,
        "planta": projeto.planta,
        "solicitante": solicitante.nome if solicitante else "",
        "pacote": pacote.titulo,
        "commodity": base.nomes_commodities(pacote.commodity_id),
        "prazo": data_por_extenso(prazo, idioma),
        "motivo": "",
    }
    blocos = {
        "tabela_itens": tabela_itens(pacote.itens, idioma),
        "tabela_projeto": tabela_projeto(projeto, idioma),
    }
    modelo = obter_modelo(base, tipo, idioma)
    corpo_html, corpo_texto = renderizar(modelo.corpo, variaveis, blocos)

    return EmailMontado(
        para=para,
        copia=copia,
        assunto=_assunto(modelo, variaveis),
        html=f'<div style="{_ESTILO_CORPO}">{corpo_html}</div>',
        texto=corpo_texto,
        anexos=caminhos_anexos(base, pacote) if tipo == TipoModelo.RFQ else [],
        prazo=prazo,
        idioma=idioma,
    )


def montar_email_agradecimento(
    base: BaseDados, fornecedor: Fornecedor, rfqs: list[RFQ], idioma: Idioma, motivo: str
) -> EmailMontado:
    """Um e-mail por fornecedor, citando todas as RFQs dele no projeto."""
    if not rfqs:
        raise ErroNegocio("Selecione ao menos uma RFQ.")
    pacotes = [p for p in (base.pacotes.obter(i) for i in dict.fromkeys(r.pacote_id for r in rfqs)) if p]
    if not pacotes:
        raise ErroNegocio("O pacote das RFQs não foi encontrado.")
    idioma = Idioma(idioma)
    projeto = base.projetos.obter(pacotes[0].projeto_id) or Projeto(nome="?")
    solicitante = base.solicitantes.obter(pacotes[0].solicitante_id)
    config = base.configuracoes
    para, copia = destinatarios(base, fornecedor, pacotes)
    rotulos = _ROTULOS[idioma]
    numeros = sorted(r.numero for r in rfqs)
    variaveis = {
        "contato": fornecedor.nome_contato() or rotulos["contato"],
        "fornecedor": fornecedor.nome,
        "empresa": config.empresa or rotulos["empresa"],
        "rfq": numeros[0],
        "rfqs": ", ".join(numeros),
        "projeto": projeto.nome,
        "cliente": projeto.cliente,
        "planta": projeto.planta,
        "solicitante": solicitante.nome if solicitante else "",
        "pacote": ", ".join(p.titulo for p in pacotes),
        "commodity": base.nomes_commodities([p.commodity_id for p in pacotes if p.commodity_id]),
        "prazo": "",
        "motivo": motivo,
    }
    blocos = {
        "tabela_itens": tabela_itens([i for p in pacotes for i in p.itens], idioma),
        "tabela_projeto": tabela_projeto(projeto, idioma),
    }
    modelo = obter_modelo(base, TipoModelo.AGRADECIMENTO, idioma)
    corpo_html, corpo_texto = renderizar(modelo.corpo, variaveis, blocos)
    return EmailMontado(
        para=para,
        copia=copia,
        assunto=_assunto(modelo, variaveis),
        html=f'<div style="{_ESTILO_CORPO}">{corpo_html}</div>',
        texto=corpo_texto,
        idioma=idioma,
    )
