"""Fixtures com dados fictícios (nunca usar dados reais da planilha)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rfq_control.armazenamento import BaseDados  # noqa: E402
from rfq_control.modelos import (  # noqa: E402
    Contato,
    Fornecedor,
    Idioma,
    Item,
    Pacote,
    Projeto,
)


@pytest.fixture(autouse=True)
def sem_outlook_real(monkeypatch):
    """Nenhum teste fala com o Outlook de verdade nem abre arquivos (em Windows isso abriria e-mails reais).

    Os testes que precisam do Outlook trocam ``_conectar_outlook`` pelo ``tests/outlook_falso.py``.
    """
    from rfq_control.servicos import envio_email

    def sem_outlook(iniciar=True):
        raise envio_email.ErroOutlook("Outlook desativado nos testes.")

    monkeypatch.setattr(envio_email, "_conectar_outlook", sem_outlook)
    monkeypatch.setattr(envio_email, "abrir_arquivo", lambda _caminho: None)


@pytest.fixture
def pasta_dados(tmp_path: Path) -> Path:
    return tmp_path / "dados"


@pytest.fixture
def base(pasta_dados: Path) -> BaseDados:
    return BaseDados.abrir(pasta_dados)


@pytest.fixture
def base_populada(base: BaseDados) -> BaseDados:
    cfg = base.configuracoes.model_copy(update={"empresa": "Empresa Exemplo"})
    base.salvar_configuracoes(cfg)
    base.projetos.salvar_varios(
        [
            Projeto(id="prj1", nome="Projeto Alfa", cliente="Cliente A", planta="Planta Sul"),
            Projeto(id="prj2", nome="Projeto Beta", cliente="Cliente B", planta="Planta Norte", lifetime_anos=6),
        ]
    )
    base.fornecedores.salvar_varios(
        [
            Fornecedor(
                id="f1",
                nome="Fornecedor Um",
                contatos=[
                    Contato(nome="João", email="joao@um.com"),
                    Contato(nome="Cópia Um", email="copia@um.com", copia=True),
                ],
            ),
            Fornecedor(
                id="f2",
                nome="Supplier Two",
                idioma=Idioma.EN,
                contatos=[Contato(nome="Anna", email="anna@two.com")],
            ),
            Fornecedor(id="f3", nome="Sem Email"),
        ]
    )
    return base


@pytest.fixture
def pacote_exemplo() -> Pacote:
    return Pacote(
        projeto_id="prj1",
        data=date(2026, 9, 28),
        itens=[
            Item(ref_op="PECA A", ref_cdc="CDC-PECA-A", unidade="PC", quantidade=2),
            Item(ref_op="PECA B", ref_cdc="CDC-PECA-B", unidade="EA", quantidade=1, volume_anual=154000),
            Item(),
        ],
    )
