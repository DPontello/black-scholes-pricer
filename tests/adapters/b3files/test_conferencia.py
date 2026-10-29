"""Conferência dos arquivos da B3 contra as premissas do app (Task 18), com a fixture."""

from pathlib import Path

import pytest

from options_engine.__main__ import main
from options_engine.adapters.outbound.b3files.conferencia import (
    Premissa,
    Situacao,
    conferir_arquivos_b3,
    formatar_relatorio,
)
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "cotahist"
COTAHIST = FIXTURE / COTAHIST_NAME
CADASTRO = FIXTURE / INSTRUMENTS_NAME


def _por_nome(premissas: tuple[Premissa, ...], inicio: str) -> Premissa:
    (achada,) = [p for p in premissas if p.nome.startswith(inicio)]
    return achada


def _cadastro_editado(tmp_path: Path, trocas: dict[str, str]) -> Path:
    texto = CADASTRO.read_bytes().decode("utf-8-sig")
    for velho, novo in trocas.items():
        assert velho in texto, velho
        texto = texto.replace(velho, novo)
    destino = tmp_path / INSTRUMENTS_NAME  # mesmo nome: mesma data de referência
    destino.write_bytes(texto.encode("utf-8-sig"))
    return destino


def test_a_fixture_passa_nas_premissas_de_leitura_e_de_cruzamento() -> None:
    premissas = conferir_arquivos_b3([COTAHIST], CADASTRO)
    for inicio in (
        "TOTREG",
        "Valores de OptnTp",
        "Formato do ExrcPric",
        "Formato do XprtnDt",
        "PREEXE",
        "DATVEN",
        "Cadastro do mesmo pregão",
    ):
        assert _por_nome(premissas, inicio).situacao is Situacao.OK, inicio
    assert _por_nome(premissas, "ESPECI").situacao is Situacao.INFO
    assert not any(p.situacao is Situacao.FALHA for p in premissas)


def test_cadastro_sem_ativo_objeto_nas_opcoes_pede_atencao() -> None:
    premissa = _por_nome(conferir_arquivos_b3([COTAHIST], CADASTRO), "UndrlygTckrSymb1")
    assert premissa.situacao is Situacao.ATENCAO
    assert "PETR3/PETR4" in premissa.detalhe


def test_totreg_que_nao_conta_header_e_trailer_e_falha_explicada(tmp_path: Path) -> None:
    linhas = COTAHIST.read_bytes().decode("cp1252").splitlines()
    trailer = linhas[-1]
    total = len(linhas)
    linhas[-1] = trailer[:31] + f"{total - 2:011d}" + trailer[42:]
    arquivo = tmp_path / COTAHIST_NAME
    arquivo.write_bytes("\r\n".join(linhas).encode("cp1252") + b"\r\n")
    premissa = _por_nome(conferir_arquivos_b3([arquivo], CADASTRO), "TOTREG")
    assert premissa.situacao is Situacao.FALHA
    assert "NÃO conta header e trailer" in premissa.detalhe


def test_strike_com_milhar_e_estilo_desconhecido_sao_falhas(tmp_path: Path) -> None:
    cadastro = _cadastro_editado(
        tmp_path,
        {"PETRK270;PETR;2026-11-19;27.00;AMER": "PETRK270;PETR;2026-11-19;1.027,00;AMERICANA"},
    )
    premissas = conferir_arquivos_b3([COTAHIST], cadastro)
    strike = _por_nome(premissas, "Formato do ExrcPric")
    assert strike.situacao is Situacao.FALHA and "1.027,00" in strike.detalhe
    assert _por_nome(premissas, "Valores de OptnStyle").situacao is not Situacao.FALHA
    estranho = _cadastro_editado(
        tmp_path, {"PETRK280;PETR;2026-11-19;28.00;AMER": "PETRK280;PETR;2026-11-19;28.00;BERM"}
    )
    estilo = _por_nome(conferir_arquivos_b3([COTAHIST], estranho), "Valores de OptnStyle")
    assert estilo.situacao is Situacao.FALHA and "BERM" in estilo.detalhe


def test_strike_divergente_entre_cotahist_e_cadastro_e_falha(tmp_path: Path) -> None:
    cadastro = _cadastro_editado(
        tmp_path, {"PETRK300;PETR;2026-11-19;30.00": "PETRK300;PETR;2026-11-19;29.50"}
    )
    premissa = _por_nome(conferir_arquivos_b3([COTAHIST], cadastro), "PREEXE")
    assert premissa.situacao is Situacao.FALHA
    assert "PETRK300: 30.00 x 29.50" in premissa.detalhe


def test_pex_do_tryd_confirma_ou_derruba_o_ajuste_por_proventos() -> None:
    iguais = _por_nome(conferir_arquivos_b3([COTAHIST], CADASTRO, {"PETRK300": 30.0}), "PEX")
    assert iguais.situacao is Situacao.OK
    ajustado = _por_nome(conferir_arquivos_b3([COTAHIST], CADASTRO, {"PETRK300": 29.5}), "PEX")
    assert ajustado.situacao is Situacao.FALHA and "DIFERE" in ajustado.detalhe
    sem = _por_nome(conferir_arquivos_b3([COTAHIST], CADASTRO, {"XPTOK10": 10.0}), "PEX")
    assert sem.situacao is Situacao.FALHA and "sem strike na B3" in sem.detalhe


def test_cadastro_de_outro_pregao_pede_atencao(tmp_path: Path) -> None:
    outro = tmp_path / "InstrumentsConsolidatedFile_20261020.csv"
    outro.write_bytes(CADASTRO.read_bytes())
    premissa = _por_nome(conferir_arquivos_b3([COTAHIST], outro), "Cadastro do mesmo pregão")
    assert premissa.situacao is Situacao.ATENCAO and "2026-10-20" in premissa.detalhe


def test_cotahist_que_nao_abre_vira_falha_sem_excecao(tmp_path: Path) -> None:
    quebrado = tmp_path / "COTAHIST_A2026.TXT"
    quebrado.write_bytes(b"isto nao e um cotahist\r\n")
    premissas = conferir_arquivos_b3([quebrado], CADASTRO)
    assert _por_nome(premissas, "TOTREG").situacao is Situacao.FALHA
    assert _por_nome(premissas, "PREEXE").situacao is Situacao.ATENCAO  # nada a cruzar


def test_relatorio_tem_uma_linha_por_premissa_e_o_resumo() -> None:
    premissas = conferir_arquivos_b3([COTAHIST], CADASTRO)
    texto = formatar_relatorio(premissas)
    assert len(texto.splitlines()) == len(premissas) + 2  # linha em branco + resumo
    assert texto.splitlines()[-1].endswith("0 falha(s)")


def test_comando_sai_com_1_quando_alguma_premissa_falha(
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = ["conferir-b3", "--cotahist", str(COTAHIST), "--cadastro", str(CADASTRO)]
    assert main(base) == 0
    assert main([*base, "--pex", "PETRK300=29,50"]) == 1
    assert "DIFERE" in capsys.readouterr().out


def test_comando_com_arquivo_ausente_ou_pex_mal_escrito(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ausente = ["conferir-b3", "--cotahist", str(tmp_path / "x.zip"), "--cadastro", str(CADASTRO)]
    assert main(ausente) == 2
    assert "não encontrado" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(
            [
                "conferir-b3",
                "--cotahist",
                str(COTAHIST),
                "--cadastro",
                str(CADASTRO),
                "--pex",
                "PETRK300",
            ]
        )
