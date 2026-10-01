"""Leitor de planilhas .xlsx/.xlsm em streaming, só com a biblioteca padrão.

A planilha antiga tem a coluna D preenchida até a linha 1.048.576; bibliotecas
comuns carregam tudo isso na memória. Este leitor percorre o XML linha a linha
e pode parar assim que os dados reais acabam.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL_DOC = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NS_REL_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_REGEX_REF = re.compile(r"([A-Z]+)(\d+)")

Valor = str | float | bool | None


class ErroPlanilha(Exception):
    pass


def indice_coluna(letras: str) -> int:
    total = 0
    for letra in letras:
        total = total * 26 + (ord(letra) - 64)
    return total


def letras_coluna(indice: int) -> str:
    letras = ""
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def data_excel(valor: Valor) -> date | None:
    """Converte número serial do Excel (ou texto de data) em ``date``."""
    if valor is None or valor == "" or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        if not 1 <= valor < 2958466:
            return None
        return date(1899, 12, 30) + timedelta(days=int(valor))
    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _texto_rico(elemento: ET.Element) -> str:
    """Texto de <si>/<is>, ignorando anotações fonéticas (<rPh>)."""
    partes = []
    for filho in elemento:
        if filho.tag == _NS + "t":
            partes.append(filho.text or "")
        elif filho.tag == _NS + "r":
            t = filho.find(_NS + "t")
            if t is not None:
                partes.append(t.text or "")
    return "".join(partes)


class LeitorXlsx:
    def __init__(self, caminho: Path | str):
        self.caminho = Path(caminho)
        try:
            self._zip = zipfile.ZipFile(self.caminho)
        except (zipfile.BadZipFile, OSError) as erro:
            raise ErroPlanilha(f"Não foi possível abrir {self.caminho.name}: não é uma planilha .xlsx/.xlsm válida.") from erro
        self._abas = self._ler_abas()
        self._textos: list[str] | None = None

    def fechar(self) -> None:
        self._zip.close()

    def __enter__(self) -> LeitorXlsx:
        return self

    def __exit__(self, *_) -> None:
        self.fechar()

    # ------------------------------------------------------------ estrutura
    def _ler_abas(self) -> dict[str, str]:
        try:
            livro = ET.fromstring(self._zip.read("xl/workbook.xml"))
            relacoes = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        except KeyError as erro:
            raise ErroPlanilha("Estrutura de planilha não reconhecida (workbook.xml ausente).") from erro
        alvos = {}
        for rel in relacoes.iter(_NS_REL_PKG + "Relationship"):
            alvo = rel.get("Target", "")
            alvo = alvo.lstrip("/") if alvo.startswith("/") else posixpath.normpath(posixpath.join("xl", alvo))
            alvos[rel.get("Id")] = alvo
        abas = {}
        for aba in livro.iter(_NS + "sheet"):
            alvo = alvos.get(aba.get(_NS_REL_DOC + "id"))
            if alvo:
                abas[aba.get("name")] = alvo
        return abas

    @property
    def abas(self) -> list[str]:
        return list(self._abas)

    def _textos_compartilhados(self) -> list[str]:
        if self._textos is None:
            self._textos = []
            try:
                arquivo = self._zip.open("xl/sharedStrings.xml")
            except KeyError:
                return self._textos
            with arquivo:
                for _, elemento in ET.iterparse(arquivo, events=("end",)):
                    if elemento.tag == _NS + "si":
                        self._textos.append(_texto_rico(elemento))
                        elemento.clear()
        return self._textos

    # ------------------------------------------------------------ dados
    def _valor(self, celula: ET.Element) -> Valor:
        tipo = celula.get("t")
        if tipo == "inlineStr":
            interno = celula.find(_NS + "is")
            return _texto_rico(interno) if interno is not None else ""
        v = celula.find(_NS + "v")
        if v is None or v.text is None:
            return None
        texto = v.text
        if tipo == "s":
            textos = self._textos_compartilhados()
            indice = int(texto)
            return textos[indice] if 0 <= indice < len(textos) else ""
        if tipo in ("str", "d"):
            return texto
        if tipo == "b":
            return texto == "1"
        if tipo == "e":
            return None
        try:
            return float(texto)
        except ValueError:
            return texto

    def linhas(
        self,
        aba: str,
        inicio: int = 1,
        coluna_chave: str | tuple[str, ...] = "A",
        parar_apos_vazias: int | None = None,
        progresso: Callable[[int], None] | None = None,
    ) -> Iterator[tuple[int, dict[str, Valor]]]:
        """Gera (número da linha, {coluna: valor}) das linhas com algum valor.

        Com ``parar_apos_vazias``, interrompe a leitura depois de tantas linhas
        seguidas sem valor na ``coluna_chave`` (fim dos dados reais). Com várias
        colunas-chave, basta uma delas ter valor para a linha contar.
        """
        chaves = (coluna_chave,) if isinstance(coluna_chave, str) else tuple(coluna_chave)
        if aba not in self._abas:
            raise ErroPlanilha(f"A aba '{aba}' não existe na planilha.")
        self._textos_compartilhados()
        vazias = 0
        ultima = 0
        pai = None
        with self._zip.open(self._abas[aba]) as arquivo:
            for evento, elemento in ET.iterparse(arquivo, events=("start", "end")):
                if evento == "start":
                    if elemento.tag == _NS + "sheetData":
                        pai = elemento
                    continue
                if elemento.tag != _NS + "row":
                    continue
                numero = int(elemento.get("r") or ultima + 1)
                ultima = numero
                valores: dict[str, Valor] = {}
                posicao = 0
                for celula in elemento.iter(_NS + "c"):
                    ref = celula.get("r")
                    if ref:
                        encontrado = _REGEX_REF.match(ref)
                        coluna = encontrado.group(1)
                        posicao = indice_coluna(coluna)
                    else:
                        posicao += 1
                        coluna = letras_coluna(posicao)
                    valor = self._valor(celula)
                    if valor is not None and valor != "":
                        valores[coluna] = valor
                if pai is not None:
                    pai.clear()
                if progresso and numero % 500 == 0:
                    progresso(numero)
                if numero < inicio:
                    continue
                if parar_apos_vazias is not None:
                    if not any(
                        valores.get(c) is not None and not (isinstance(valores[c], str) and not valores[c].strip())
                        for c in chaves
                    ):
                        vazias += 1
                        if vazias >= parar_apos_vazias:
                            return
                        continue
                    vazias = 0
                if valores:
                    yield numero, valores
