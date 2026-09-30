import json
from datetime import date

import pytest

from rfq_control.armazenamento import BaseDados, ErroDados
from rfq_control.modelos import Contato, Fornecedor, TipoModelo


def test_primeira_execucao_cria_um_arquivo_por_colecao(base, pasta_dados):
    esperados = {
        "configuracoes.json", "fornecedores.json", "projetos.json", "solicitantes.json",
        "feriados.json", "modelos_email.json", "pacotes.json", "rfqs.json",
    }
    assert esperados <= {p.name for p in pasta_dados.glob("*.json")}
    assert base.primeira_execucao
    assert {(m.tipo, m.idioma.value) for m in base.modelos_email} == {
        (TipoModelo.RFQ, "PT"), (TipoModelo.RFQ, "EN"),
        (TipoModelo.COBRANCA, "PT"), (TipoModelo.COBRANCA, "EN"),
    }
    ano = date.today().year
    assert date(ano, 12, 25) in base.datas_feriados()
    assert date(ano + 1, 1, 1) in base.datas_feriados()


def test_salvar_e_reabrir(base, pasta_dados):
    fornecedor = base.fornecedores.salvar(
        Fornecedor(nome="  Acme  ", contatos=[Contato(nome="Ana", email="ANA@ACME.COM")])
    )
    assert fornecedor.nome == "Acme"  # espaços removidos
    assert fornecedor.contatos[0].email == "ana@acme.com"

    reaberta = BaseDados.abrir(pasta_dados)
    assert not reaberta.primeira_execucao
    assert reaberta.fornecedores.obter(fornecedor.id).nome == "Acme"

    conteudo = json.loads((pasta_dados / "fornecedores.json").read_text(encoding="utf-8"))
    assert conteudo["versao_esquema"] == 1
    assert conteudo["registros"][0]["nome"] == "Acme"


def test_validacao_impede_dados_invalidos(base):
    with pytest.raises(ErroDados):
        base.fornecedores.salvar(Fornecedor.model_construct(id="x", nome="", contatos=[]))
    with pytest.raises(ValueError):
        Contato(email="nao-e-email")
    assert len(base.fornecedores) == 0


def test_arquivo_corrompido_gera_erro_claro(base, pasta_dados):
    (pasta_dados / "projetos.json").write_text("{ isso não é json", encoding="utf-8")
    with pytest.raises(ErroDados, match="projetos.json está corrompido"):
        BaseDados.abrir(pasta_dados)


def test_registro_invalido_no_arquivo(base, pasta_dados):
    (pasta_dados / "projetos.json").write_text(json.dumps({"registros": [{"id": "a", "nome": ""}]}), encoding="utf-8")
    with pytest.raises(ErroDados, match="Registro 1 inválido em projetos.json"):
        BaseDados.abrir(pasta_dados)


def test_gravacao_atomica_nao_deixa_temporarios(base, pasta_dados):
    base.fornecedores.salvar(Fornecedor(nome="X"))
    assert not list(pasta_dados.glob("*.tmp"))


def test_falha_na_gravacao_desfaz_memoria(base, monkeypatch):
    def falhar(*_):
        raise ErroDados("disco cheio")

    monkeypatch.setattr("rfq_control.armazenamento.gravar_json_atomico", falhar)
    with pytest.raises(ErroDados):
        base.fornecedores.salvar(Fornecedor(nome="Não grava"))
    assert len(base.fornecedores) == 0


def test_backup_diario(base):
    destino = base.backup_diario()
    assert destino is not None and (destino / "rfqs.json").exists()
    assert base.backup_diario() is None  # só uma vez por dia


def test_backups_antigos_sao_removidos(base, monkeypatch):
    import os
    import time

    monkeypatch.setattr("rfq_control.armazenamento.BACKUPS_MANTIDOS", 3)
    agora = time.time()
    for indice in range(5):
        pasta = base.backup(f"copia_{indice}")
        os.utime(pasta, (agora - 100 + indice, agora - 100 + indice))
    base.backup("antes_importacao_x")
    restantes = sorted(p.name for p in base.pasta_backup.iterdir())
    assert restantes == ["antes_importacao_x", "copia_3", "copia_4"]
