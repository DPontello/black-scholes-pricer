"""``python -m options_engine painel`` de ponta a ponta sobre a fixture sintética (tmp_path)."""

from datetime import date
from pathlib import Path

import pytest

from options_engine.__main__ import main
from tests.adapters.cotahist._layout import arquivo, registro
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "cotahist"


def _args(saida: Path, *extra: str, cotahist: Path | None = None) -> list[str]:
    return [
        "painel",
        "--pregao",
        "2026-10-23",
        "--cotahist",
        str(cotahist or FIXTURE / COTAHIST_NAME),
        "--cadastro",
        str(FIXTURE / INSTRUMENTS_NAME),
        "--ativos",
        "petr4, VALE3",
        "--saida",
        str(saida),
        *extra,
    ]


def test_gera_o_painel_e_resume_no_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saida = tmp_path / "painel.html"
    assert main(_args(saida)) == 0
    html = saida.read_text(encoding="utf-8")
    assert "PETR4" in html and "VALE3" in html
    assert "COTAHIST_SINTETICO_2026.TXT" in html  # nome do arquivo, não o caminho
    assert str(FIXTURE) not in html
    assert "painel gravado em" in capsys.readouterr().out


def test_mesma_entrada_produz_bytes_identicos(tmp_path: Path) -> None:
    a, b = tmp_path / "a.html", tmp_path / "b.html"
    assert main(_args(a)) == 0
    assert main(_args(b, "--cache", str(tmp_path / "cache.sqlite"))) == 0
    assert a.read_bytes() == b.read_bytes()


def test_parametros_do_comando_chegam_ao_painel(tmp_path: Path) -> None:
    saida = tmp_path / "painel.html"
    extras = (
        "--delta-min",
        "0.10",
        "--delta-max",
        "0.40",
        "--vencimentos",
        "1",
        "--min-negocios",
        "5",
        "--spread-max",
        "12.5",
        "--ordenar",
        "anual-bruto",
        "--acoes",
        "200",
        "--cdi",
        "0.1475",
        "--gerado-em",
        "2026-10-24",
    )
    assert main(_args(saida, *extras)) == 0
    html = saida.read_text(encoding="utf-8")
    assert "0,1 a 0,4" in html
    assert "<dd>12,5%</dd>" in html
    assert "<dd>200</dd>" in html
    assert "<dd>14,75%</dd>" in html
    assert "ordenado por rendimento anualizado bruto" in html
    assert "gerado em 24/10/2026" in html
    assert "18/12/2026" not in html.split("<h2>Ranking")[1].split("<h2>Exclusões")[0]


def test_arquivo_ausente_sai_com_2_sem_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_args(tmp_path / "p.html", cotahist=tmp_path / "nao_existe.TXT")) == 2
    erro = capsys.readouterr().err
    assert erro.startswith("erro de arquivo:")
    assert "Traceback" not in erro
    assert not (tmp_path / "p.html").exists()


def test_cotahist_fora_do_layout_aponta_a_linha(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ruim = tmp_path / "ruim.TXT"
    linhas = arquivo(
        [registro(pregao=date(2026, 10, 23), simbolo="PETR4", mercado=10)],
        geracao=date(2026, 10, 23),
        ano=2026,
    ).split("\r\n")
    linhas[1] = linhas[1][:-3]
    ruim.write_bytes("\r\n".join(linhas).encode("cp1252"))
    assert main(_args(tmp_path / "p.html", cotahist=ruim)) == 2
    assert "linha 2" in capsys.readouterr().err


def test_parametro_invalido_de_dominio_sai_com_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_args(tmp_path / "p.html", "--vencimentos", "0")) == 1
    assert capsys.readouterr().err.startswith("erro: expiries deve ser >= 1")


def test_saida_em_diretorio_inexistente_sai_com_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_args(tmp_path / "nao" / "existe" / "p.html")) == 2
    assert "não foi possível gravar" in capsys.readouterr().err


def test_argumento_obrigatorio_faltando_e_erro_de_uso(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        main(["painel", "--pregao", "2026-10-23"])
    assert saida.value.code == 2
    assert "--cotahist" in capsys.readouterr().err


def test_lista_de_ativos_vazia_e_erro_de_uso(tmp_path: Path) -> None:
    args = _args(tmp_path / "p.html")
    args[args.index("--ativos") + 1] = " , "
    with pytest.raises(SystemExit):
        main(args)
