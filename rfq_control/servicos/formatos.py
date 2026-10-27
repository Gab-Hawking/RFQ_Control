"""Conversões de texto ↔ números/datas no padrão brasileiro e por idioma."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

from ..modelos import Idioma

_DIAS_SEMANA = {
    Idioma.PT: ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"],
    Idioma.ES: ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    Idioma.EN: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
_MESES = {
    Idioma.PT: ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                "agosto", "setembro", "outubro", "novembro", "dezembro"],
    Idioma.ES: ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    Idioma.EN: ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"],
}


def data_por_extenso(dia: date, idioma: Idioma) -> str:
    """'terça-feira, 6 de outubro de 2026', 'martes, 6 de octubre de 2026' ou 'Tuesday, October 6, 2026'."""
    semana = _DIAS_SEMANA[idioma][dia.weekday()]
    mes = _MESES[idioma][dia.month - 1]
    if idioma == Idioma.EN:
        return f"{semana}, {mes} {dia.day}, {dia.year}"
    return f"{semana}, {dia.day} de {mes} de {dia.year}"


def data_curta(dia: date | datetime | None) -> str:
    if dia is None:
        return ""
    if isinstance(dia, datetime):
        return dia.strftime("%d/%m/%Y %H:%M")
    return dia.strftime("%d/%m/%Y")


def ler_data(texto: str) -> date | None:
    """Aceita 'dd/mm/aaaa', 'dd/mm/aa' e 'aaaa-mm-dd'."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"data inválida: {texto} (use dd/mm/aaaa)")


def ler_numero(texto: str | float | int | None) -> float | None:
    """Converte '1.464,76', '1464,76', '1,464.76', '154000' ou 'R$ 10' em número."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    limpo = re.sub(r"[^\d,.\-]", "", str(texto))
    if not limpo or limpo in {"-", ",", "."}:
        return None
    if "," in limpo and "." in limpo:
        if limpo.rfind(",") > limpo.rfind("."):
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            limpo = limpo.replace(",", "")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    elif limpo.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", limpo):
        # Padrão brasileiro: '154.000' é cento e cinquenta e quatro mil.
        limpo = limpo.replace(".", "")
    try:
        return float(limpo)
    except ValueError:
        return None


def numero_br(valor: float | None, casas: int | None = None) -> str:
    """Formata número no padrão brasileiro, sem casas decimais desnecessárias."""
    if valor is None:
        return ""
    if casas is None:
        casas = 0 if float(valor).is_integer() else 2
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def valor_monetario(valor: float | None) -> str:
    """Preço no padrão brasileiro com 2 a 4 casas: 0,1234 · 1.234,50 · 2,00."""
    if valor is None:
        return ""
    texto = f"{valor:,.4f}"
    inteiro, decimais = texto.split(".")
    decimais = decimais.rstrip("0").ljust(2, "0")
    return inteiro.replace(",", ".") + "," + decimais


def ler_lead_time(texto: str) -> int | None:
    """Lead time em dias: '30', '30 dias', '6 semanas', '6 sem', '6 weeks', '2 meses' (30 dias cada)."""
    texto = (texto or "").strip().casefold()
    if not texto:
        return None
    encontrado = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([a-zçãé]*)\.?", texto)
    if not encontrado:
        raise ValueError(f"lead time inválido: '{texto}' (ex.: 30, 30 dias, 6 semanas)")
    numero = float(encontrado.group(1).replace(",", "."))
    unidade = encontrado.group(2)
    if unidade in ("", "d", "dia", "dias", "day", "days", "dd"):
        fator = 1
    elif unidade in ("s", "sem", "semana", "semanas", "w", "wk", "wks", "week", "weeks"):
        fator = 7
    elif unidade in ("m", "mes", "mês", "meses", "month", "months"):
        fator = 30
    else:
        raise ValueError(f"lead time inválido: '{texto}' (use dias, semanas ou meses)")
    return round(numero * fator)


def numero_por_idioma(valor: float | None, idioma: Idioma) -> str:
    if valor is None:
        return ""
    if idioma == Idioma.EN:
        casas = 0 if float(valor).is_integer() else 2
        return f"{valor:,.{casas}f}"
    return numero_br(valor)


def chave_cabecalho(texto: Any) -> str:
    """'  EMAIL (To) ' → 'emailto'; 'Descrição' → 'descricao'."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or "").casefold()) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", sem_acento)


def normalizar_nome(texto: str) -> str:
    """Chave para comparar nomes ignorando espaços extras e maiúsculas."""
    return re.sub(r"\s+", " ", (texto or "")).strip().casefold()


def separar_valores(texto: str) -> list[str]:
    """'A; B' → ['A', 'B'] (valores de uma coluna com várias opções)."""
    return [v.strip() for v in re.split(r"[;\n]", texto or "") if v.strip()]


def nomes_de_opcoes(texto: str, existentes: set[str]) -> list[str]:
    """Nomes citados numa coluna de várias opções (ex.: commodities).

    Separa por ';' (e quebra de linha); um valor com vírgula que não é o nome de uma opção existente
    (``existentes``: nomes já normalizados) também é separado pela vírgula — 'A, B' vira A e B.
    Importação, grade e migração usam esta mesma regra.
    """
    nomes: list[str] = []
    for valor in separar_valores(texto):
        if "," in valor and normalizar_nome(valor) not in existentes:
            nomes += [parte.strip() for parte in valor.split(",") if parte.strip()]
        else:
            nomes.append(valor)
    return nomes
