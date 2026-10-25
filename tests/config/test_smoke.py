"""Smoke ``python -m options_engine`` — executa e é reprodutível dada a seed."""

import pytest

from options_engine.__main__ import main


def _saida(capsys: pytest.CaptureFixture[str], seed: str | None = None) -> str:
    main([seed] if seed is not None else [])
    return capsys.readouterr().out


def test_smoke_imprime_preco_gregas_payoff_e_estresse(capsys: pytest.CaptureFixture[str]) -> None:
    saida = _saida(capsys)
    assert "[price]" in saida
    assert "gregas:" in saida
    assert "[payoff]" in saida
    assert "breakevens=('27.00', '33.00')" in saida  # forma fechada K2-1, K3+1
    assert "[stress]" in saida
    assert "var=  +0.0000" in saida  # cenário identidade reproduz a base


def test_smoke_e_reprodutivel_dada_a_seed(capsys: pytest.CaptureFixture[str]) -> None:
    assert _saida(capsys, seed="7") == _saida(capsys, seed="7")


def test_smoke_muda_com_a_seed(capsys: pytest.CaptureFixture[str]) -> None:
    assert _saida(capsys, seed="7") != _saida(capsys, seed="8")
