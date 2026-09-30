"""Cálculo de prazos em dias úteis e geração de feriados nacionais."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


def somar_dias_uteis(inicio: date, dias: int, feriados: Iterable[date] = ()) -> date:
    """Equivalente à função DIATRABALHO/WORKDAY do Excel.

    Avança ``dias`` dias úteis a partir de ``inicio`` (que não é contado),
    pulando sábados, domingos e feriados.
    """
    feriados = set(feriados)
    atual = inicio
    restantes = dias
    passo = 1 if dias >= 0 else -1
    while restantes != 0:
        atual += timedelta(days=passo)
        if atual.weekday() < 5 and atual not in feriados:
            restantes -= passo
    return atual


def dias_uteis_entre(inicio: date, fim: date, feriados: Iterable[date] = ()) -> int:
    """Quantidade de dias úteis após ``inicio`` até ``fim`` (inclusive).

    Negativo quando ``fim`` é anterior a ``inicio``.
    """
    if fim == inicio:
        return 0
    feriados = set(feriados)
    sinal = 1 if fim > inicio else -1
    menor, maior = sorted((inicio, fim))
    total = 0
    atual = menor
    while atual < maior:
        atual += timedelta(days=1)
        if atual.weekday() < 5 and atual not in feriados:
            total += 1
    return total * sinal


def domingo_de_pascoa(ano: int) -> date:
    """Algoritmo de Meeus/Jones/Butcher (calendário gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    mes, dia = divmod(h + ell - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def feriados_nacionais_brasil(
    ano: int, incluir_carnaval: bool = True, incluir_corpus_christi: bool = True
) -> list[tuple[date, str]]:
    """Feriados nacionais do Brasil (e pontos facultativos usuais) de um ano."""
    pascoa = domingo_de_pascoa(ano)
    feriados = [
        (date(ano, 1, 1), "Confraternização Universal"),
        (pascoa - timedelta(days=2), "Sexta-feira Santa"),
        (date(ano, 4, 21), "Tiradentes"),
        (date(ano, 5, 1), "Dia do Trabalho"),
        (date(ano, 9, 7), "Independência do Brasil"),
        (date(ano, 10, 12), "Nossa Senhora Aparecida"),
        (date(ano, 11, 2), "Finados"),
        (date(ano, 11, 15), "Proclamação da República"),
        (date(ano, 12, 25), "Natal"),
    ]
    if ano >= 2024:
        feriados.append((date(ano, 11, 20), "Dia Nacional de Zumbi e da Consciência Negra"))
    if incluir_carnaval:
        feriados.append((pascoa - timedelta(days=48), "Carnaval (segunda-feira)"))
        feriados.append((pascoa - timedelta(days=47), "Carnaval (terça-feira)"))
    if incluir_corpus_christi:
        feriados.append((pascoa + timedelta(days=60), "Corpus Christi"))
    return sorted(feriados)
