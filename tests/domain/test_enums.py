"""Enums fundamentais — sinal de direção e fronteira enum -> bool."""

from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side


def test_sign_buy_e_mais_um_sell_e_menos_um() -> None:
    """CONVENTIONS §4: exposição assinada = side.sign * quantity, com sinal
    derivado do enum num único lugar do código."""
    assert Side.BUY.sign == 1
    assert Side.SELL.sign == -1


def test_opposite_e_involucao() -> None:
    assert Side.BUY.opposite is Side.SELL
    assert Side.SELL.opposite is Side.BUY
    assert Side.BUY.opposite.opposite is Side.BUY


def test_is_call_e_a_fronteira_enum_para_bool() -> None:
    assert OptionType.CALL.is_call is True
    assert OptionType.PUT.is_call is False


def test_exercise_style_declara_american_sem_suporta_lo() -> None:
    """Decisão nº 2: AMERICAN existe no domínio (é legal na B3) — a rejeição
    acontece nos caminhos de precificação, nunca por omissão no enum."""
    assert {e.name for e in ExerciseStyle} == {"EUROPEAN", "AMERICAN"}
