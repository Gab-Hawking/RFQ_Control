"""Gera o executável do RFQ Control com o PyInstaller.

Uso (na raiz do repositório, com as dependências de requirements-build.txt):

    python build.py

Resultado:

    dist/RFQ_Control/
    ├── RFQ_Control.exe
    ├── programa/          (bibliotecas do executável)
    ├── dados/             (preservada se já existir — nunca é apagada pelo build)
    └── LEIA-ME.txt
    dist/RFQ_Control-<versão>.zip   (pronto para copiar para outro computador, sem dados)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DIST = RAIZ / "dist"
SAIDA = DIST / "RFQ_Control"

LEIA_ME = """RFQ Control {versao}
====================

Estrutura:
  RFQ_Control.exe   programa (abra este arquivo)
  programa\\         bibliotecas do programa — não mexa
  dados\\            base de dados: um arquivo .json para cada cadastro
                    (fornecedores, projetos, solicitantes, feriados,
                    modelos de e-mail, pacotes e RFQs), anexos, e-mails
                    gerados, cópias de segurança e registros de erro

Instalação:
  Copie a pasta RFQ_Control inteira para um local do seu computador
  (por exemplo, Documentos\\RFQ_Control) e abra o RFQ_Control.exe.

Atualização para uma nova versão:
  Substitua apenas o RFQ_Control.exe e a pasta programa.
  NUNCA apague nem substitua a pasta dados.

Cópias de segurança:
  O programa copia todos os arquivos de dados para dados\\backup uma vez
  por dia (mantém as 30 últimas). Para restaurar, feche o programa e copie
  os arquivos .json de uma pasta de backup para a pasta dados.
"""


def versao() -> str:
    sys.path.insert(0, str(RAIZ))
    from rfq_control import __version__

    return __version__


def gerar() -> Path:
    dados = SAIDA / "dados"
    preservado = Path(tempfile.mkdtemp(prefix="rfq_dados_")) / "dados"
    tinha_dados = dados.exists() and any(dados.iterdir())
    if tinha_dados:
        shutil.move(str(dados), preservado)
        print(f"Pasta de dados existente guardada temporariamente em {preservado}")
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(RAIZ / "RFQ_Control.spec")],
            check=True,
            cwd=RAIZ,
        )
    finally:
        if tinha_dados:
            if dados.exists():
                shutil.rmtree(dados)
            SAIDA.mkdir(parents=True, exist_ok=True)
            shutil.move(str(preservado), dados)
            print("Pasta de dados restaurada.")
    dados.mkdir(parents=True, exist_ok=True)
    (SAIDA / "LEIA-ME.txt").write_text(LEIA_ME.format(versao=versao()), encoding="utf-8")
    return SAIDA


def verificar(saida: Path) -> None:
    """Abre o executável em modo de autoteste com uma pasta de dados temporária."""
    executavel = saida / ("RFQ_Control.exe" if os.name == "nt" else "RFQ_Control")
    with tempfile.TemporaryDirectory() as temporaria:
        ambiente = dict(os.environ, RFQ_CONTROL_DADOS=str(Path(temporaria) / "dados"))
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            ambiente.setdefault("QT_QPA_PLATFORM", "offscreen")
        resultado = subprocess.run([str(executavel), "--verificar"], env=ambiente, timeout=180)
    if resultado.returncode != 0:
        raise SystemExit(f"O executável falhou no autoteste (código {resultado.returncode}).")
    print("Autoteste do executável: OK")


def compactar(saida: Path) -> Path:
    destino = DIST / f"RFQ_Control-{versao()}.zip"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as arquivo:
        for caminho in sorted(saida.rglob("*")):
            relativo = caminho.relative_to(saida.parent)
            if relativo.parts[1:2] == ("dados",):
                continue  # dados nunca vão no pacote de distribuição
            arquivo.write(caminho, relativo.as_posix())
        arquivo.writestr("RFQ_Control/dados/", "")
    return destino


def main() -> None:
    saida = gerar()
    if "--sem-teste" not in sys.argv:
        verificar(saida)
    pacote = compactar(saida)
    print(f"\nPronto:\n  {saida}\n  {pacote}")


if __name__ == "__main__":
    main()
