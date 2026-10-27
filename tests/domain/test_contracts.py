"""OptionTerms (igualdade estrutural) vs OptionContract (identidade = ticker)."""

import pytest

from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import InvalidDomainValueError
from tests.domain._builders import make_contract, make_terms

# ---------------------------------------------------------------------------
# OptionTerms — Value Object
# ---------------------------------------------------------------------------


def test_termos_identicos_sao_iguais_estruturalmente() -> None:
    """Dois contratos de termos idênticos são economicamente intercambiáveis."""
    assert make_terms() == make_terms()


def test_termos_de_subjacentes_distintos_diferem() -> None:
    assert make_terms(underlying="PETR4") != make_terms(underlying="VALE3")


def test_default_de_estilo_e_europeu_decisao_2() -> None:
    assert make_terms().exercise_style is ExerciseStyle.EUROPEAN


def test_american_e_construivel_no_dominio() -> None:
    """Legal no domínio (há séries americanas na B3); aceitar a call como
    aproximação (ADR-0002) ou rejeitar a put pertence aos caminhos de
    precificação, não à construção."""
    termos = make_terms(exercise_style=ExerciseStyle.AMERICAN)
    assert termos.exercise_style is ExerciseStyle.AMERICAN


@pytest.mark.parametrize("strike", [0.0, -30.0, float("nan"), float("inf")])
def test_strike_ilegal_e_irrepresentavel(strike: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_terms(strike=strike)


def test_underlying_vazio_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        make_terms(underlying="")


# ---------------------------------------------------------------------------
# OptionContract — Entity (identidade = symbol)
# ---------------------------------------------------------------------------


def test_igualdade_e_hash_exclusivamente_pelo_symbol() -> None:
    """Mesmo ticker = mesmo instrumento, ainda que os objetos de termos
    difiram; tickers distintos = books distintos, ainda que os termos
    coincidam."""
    call = make_terms(option_type=OptionType.CALL)
    put = make_terms(option_type=OptionType.PUT)

    assert make_contract("PETRA300", call) == make_contract("PETRA300", put)
    assert hash(make_contract("PETRA300", call)) == hash(make_contract("PETRA300", put))
    assert make_contract("PETRA300", call) != make_contract("PETRM300", call)


def test_contrato_e_utilizavel_em_set_por_identidade() -> None:
    contratos = {make_contract("PETRA300"), make_contract("PETRA300"), make_contract("PETRM300")}
    assert len(contratos) == 2


def test_comparacao_com_tipo_estranho_nao_explode() -> None:
    assert make_contract("PETRA300") != "PETRA300"


def test_symbol_vazio_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        make_contract(symbol="")
