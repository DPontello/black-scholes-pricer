"""API do book: ``GET /api/book`` e ``POST /api/book/direcional`` com o ``BookService`` falso."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.book import format_metric, router_book
from options_engine.adapters.inbound.web.profiles import router_perfis
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.use_cases.book import BookService
from options_engine.application.use_cases.profiles import ProfileService
from options_engine.domain.book.model import Metric, MetricUnit
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.errors import UnderlyingUnavailableError
from tests.application._book_falso import MontadorFalso, resultado_no_vencimento, servico_do_book
from tests.application._fakes import FakeProfileRepository
from tests.application._mercado_falso import MercadoFalso

AGORA = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)


class _SemCotahist(MercadoFalso):
    def get_chain(self, underlying_symbol: str) -> OptionChain:
        raise UnderlyingUnavailableError("sem COTAHIST na biblioteca: importe o arquivo da B3")


def _cliente(pasta: Path | None, book: BookService | None = None) -> TestClient:
    perfis = ProfileService(FakeProfileRepository(), FixedClock(AGORA), "PC-TESTE")
    if pasta is not None:
        perfis.create("Hugo", str(pasta))
        perfis.open("Hugo")
    servico = book or servico_do_book()
    return TestClient(create_app([router_perfis(perfis), router_book(servico, perfis)]))


def test_sem_perfil_aberto_o_book_devolve_404(tmp_path: Path) -> None:
    cliente = _cliente(None)
    assert cliente.get("/api/book").status_code == 404
    visao = {"ativo": "PETR4", "direcao": "alta", "alvo": 33, "vencimento": "2026-11-19"}
    assert cliente.post("/api/book/direcional", json=visao).status_code == 404


def test_book_do_perfil_com_o_pregao_o_preset_e_as_familias(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    cliente.put("/api/perfil/book", json={"preset": "arrojado"})

    corpo = cliente.get("/api/book").json()

    assert (corpo["pregao"], corpo["fonte"]) == ("2026-10-23", "fim_de_dia")
    assert corpo["preset"]["preset"] == "arrojado"
    assert set(corpo["familias"]) == {"renda", "volatilidade", "direcionais", "protecao"}
    assert [c["ativo"] for c in corpo["contextos"]] == ["PETR4", "VALE3"]
    assert corpo["contextos"][0]["regime"] == "baixa"
    item = corpo["familias"]["renda"]["itens"][0]
    assert item["familia"] == "renda"
    assert item["pedido"]["ativo"] == item["ativo"]
    assert item["pedido"]["modelo"] == item["estrutura"]
    assert [p["ticker"] for p in item["pedido"]["pernas"]] == [p["ticker"] for p in item["pernas"]]
    assert all(p["preco"] is None for p in item["pedido"]["pernas"])
    assert item["criterio"]["texto"] in item["porque"]
    assert "{" not in item["porque"]
    assert item["qualidade"] == "executavel"


def test_rotulos_vao_com_o_texto(tmp_path: Path) -> None:
    corpo = _cliente(tmp_path).get("/api/book").json()
    protecao = corpo["familias"]["protecao"]["itens"]
    assert protecao
    assert {"chave": "posicao_hipotetica", "texto": "posição hipotética de 100 ações"} in protecao[
        0
    ]["rotulos"]


def test_item_leva_o_resultado_no_vencimento_com_os_textos_em_pt_br(tmp_path: Path) -> None:
    montador = MontadorFalso(resultado_no_vencimento(350.11, -16433.11, 0.62))

    corpo = _cliente(tmp_path, servico_do_book(builder=montador)).get("/api/book").json()

    assert corpo["familias"]["renda"]["itens"][0]["resultado"] == {
        "ganha_ate": 350.11,
        "perde_ate": 16433.11,
        "chance_de_lucro": 0.62,
        "ganha_ate_texto": "R$ 350,11",
        "perde_ate_texto": "R$ 16.433,11",
        "chance_texto": "62,0%",
    }


def test_resultado_sem_limite_sai_null_com_o_texto_sem_limite(tmp_path: Path) -> None:
    montador = MontadorFalso(resultado_no_vencimento(None, -16433.11, 0.62))

    corpo = _cliente(tmp_path, servico_do_book(builder=montador)).get("/api/book").json()

    resultado = corpo["familias"]["renda"]["itens"][0]["resultado"]
    assert (resultado["ganha_ate"], resultado["ganha_ate_texto"]) == (None, "sem limite")
    assert resultado["perde_ate_texto"] == "R$ 16.433,11"


@pytest.mark.parametrize("ganho", [-0.01, 0.0])
def test_ganho_maximo_que_nao_e_lucro_sai_com_o_texto_nao_da_lucro(
    tmp_path: Path, ganho: float
) -> None:
    montador = MontadorFalso(resultado_no_vencimento(ganho, -16433.11, 0.0))

    corpo = _cliente(tmp_path, servico_do_book(builder=montador)).get("/api/book").json()

    resultado = corpo["familias"]["renda"]["itens"][0]["resultado"]
    assert (resultado["ganha_ate"], resultado["ganha_ate_texto"]) == (ganho, "não dá lucro")
    assert resultado["perde_ate_texto"] == "R$ 16.433,11"


def test_perda_sem_limite_sai_null_com_o_texto_sem_limite(tmp_path: Path) -> None:
    montador = MontadorFalso(resultado_no_vencimento(350.11, None, 0.62))

    corpo = _cliente(tmp_path, servico_do_book(builder=montador)).get("/api/book").json()

    resultado = corpo["familias"]["renda"]["itens"][0]["resultado"]
    assert (resultado["perde_ate"], resultado["perde_ate_texto"]) == (None, "sem limite")
    assert resultado["ganha_ate_texto"] == "R$ 350,11"


def test_item_sem_resultado_sai_com_resultado_null(tmp_path: Path) -> None:
    corpo = _cliente(tmp_path).get("/api/book").json()

    assert corpo["familias"]["renda"]["itens"][0]["resultado"] is None


def test_item_da_venda_coberta_leva_a_frase_curta(tmp_path: Path) -> None:
    corpo = _cliente(tmp_path).get("/api/book").json()

    item = next(i for i in corpo["familias"]["renda"]["itens"] if i["estrutura"] == "venda_coberta")
    assert item["porque_curto"] == (
        "Renda com as suas ações: recebe o prêmio e aceita vender no strike."
    )


def test_sem_cotahist_o_book_diz_por_que_e_nao_mostra_itens(tmp_path: Path) -> None:
    corpo = _cliente(tmp_path, servico_do_book(mercado=_SemCotahist())).get("/api/book").json()
    assert corpo["pregao"] is None
    assert {e["motivo"] for e in corpo["indisponiveis"]} == {
        "sem COTAHIST na biblioteca: importe o arquivo da B3"
    }
    assert all(not f["itens"] for f in corpo["familias"].values())


def test_direcionais_com_visao(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    cliente.put("/api/perfil/book", json={"preset": "arrojado"})
    visao = {"ativo": "petr4", "direcao": "alta", "alvo": 33, "vencimento": "2026-11-19"}

    r = cliente.post("/api/book/direcional", json=visao)

    assert r.status_code == 200
    assert {i["estrutura"] for i in r.json()["itens"]} <= {"compra_call", "trava_alta_call"}
    assert r.json()["itens"]


def test_visao_com_alvo_do_lado_errado_ou_fora_do_formato_devolve_422(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    errada = {"ativo": "PETR4", "direcao": "alta", "alvo": 29, "vencimento": "2026-11-19"}
    r = cliente.post("/api/book/direcional", json=errada)
    assert (r.status_code, r.json()["erro"]) == (422, "InvalidDomainValueError")
    assert "acima do spot" in r.json()["mensagem"]
    torta = {"ativo": "PETR4", "direcao": "lateral", "alvo": 33, "vencimento": "2026-11-19"}
    r = cliente.post("/api/book/direcional", json=torta)
    assert (r.status_code, r.json()["erro"]) == (422, "RequisicaoInvalida")


@pytest.mark.parametrize(
    ("unidade", "valor", "texto"),
    [
        (MetricUnit.PERCENT, 0.1234, "12,3%"),
        (MetricUnit.CURRENCY, 1234.5, "R$ 1.234,50"),
        (MetricUnit.CURRENCY, -12.0, "-R$ 12,00"),
        (MetricUnit.RATIO, 0.354, "0,35"),
        (MetricUnit.STD_DEVS, 1.234, "1,23 desvios-padrão"),
        (MetricUnit.BUSINESS_DAYS, 18.0, "18 dias úteis"),
        (MetricUnit.NUMBER, -0.256, "-0,26"),
    ],
)
def test_numeros_do_porque_em_pt_br(unidade: MetricUnit, valor: float, texto: str) -> None:
    assert format_metric(Metric("x", "x", valor, unidade)) == texto
