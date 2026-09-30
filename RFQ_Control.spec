# -*- mode: python ; coding: utf-8 -*-
"""Especificação do PyInstaller para o RFQ Control.

Gera a pasta dist/RFQ_Control com a estrutura:

    RFQ_Control.exe
    programa/      <- bibliotecas (contents_directory)
    dados/         <- criada pelo build.py / na primeira execução

Use sempre:  python build.py
"""
import sys
from pathlib import Path

raiz = Path(SPECPATH)
recursos = raiz / "rfq_control" / "recursos"

ocultos = []
if sys.platform == "win32":
    ocultos += ["win32com", "win32com.client", "pythoncom", "pywintypes"]

a = Analysis(
    [str(raiz / "main.py")],
    pathex=[str(raiz)],
    datas=[(str(recursos), "rfq_control/recursos")],
    hiddenimports=ocultos,
    excludes=["tkinter", "pytest", "PIL", "numpy", "pandas", "matplotlib", "IPython", "lxml"],
    noarchive=False,
)
# Das traduções do Qt, só a de português do Brasil é usada.
a.datas = [
    item for item in a.datas
    if "translations" not in Path(item[0]).parts or Path(item[0]).name == "qtbase_pt_BR.qm"
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RFQ_Control",
    console=False,
    icon=str(recursos / "icone.ico"),
    contents_directory="programa",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="RFQ_Control")
