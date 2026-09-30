"""Localização das pastas do aplicativo.

Estrutura da instalação (gerada pelo PyInstaller):

    RFQ_Control/
    ├── RFQ_Control.exe
    ├── programa/      ← bibliotecas e recursos do executável
    └── dados/         ← arquivos da base de dados (um por "aba")

Durante o desenvolvimento, a pasta ``dados`` fica na raiz do repositório
(ignorada pelo Git). A variável de ambiente ``RFQ_CONTROL_DADOS`` permite
apontar para outra pasta (usada nos testes).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

VARIAVEL_PASTA_DADOS = "RFQ_CONTROL_DADOS"


def executando_como_exe() -> bool:
    return bool(getattr(sys, "frozen", False))


def pasta_raiz() -> Path:
    """Pasta onde fica o .exe (ou a raiz do repositório no desenvolvimento)."""
    if executando_como_exe():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def pasta_dados() -> Path:
    personalizada = os.environ.get(VARIAVEL_PASTA_DADOS)
    if personalizada:
        return Path(personalizada).expanduser().resolve()
    return pasta_raiz() / "dados"


def pasta_recursos() -> Path:
    """Ícones e outros arquivos empacotados junto com o programa."""
    if executando_como_exe():
        return Path(getattr(sys, "_MEIPASS")) / "rfq_control" / "recursos"
    return Path(__file__).resolve().parent / "recursos"
