"""API de perfis — ``ProfileService`` e ``JsonProfileRepository`` reais atrás do FastAPI."""

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.profiles import router_perfis
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.storage.profiles import JsonProfileRepository
from options_engine.application.use_cases.profiles import ProfileService

AGORA = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)  # 09:00 em Brasília
BOOK_MODERADO = {
    "preset": "moderado",
    "delta_min": 0.15,
    "delta_max": 0.35,
    "negocios_min": 10,
    "spread_max": 0.20,
    "risco_max": 3000.0,
    "vencimentos": 2,
    "piso_protecao": 0.90,
    "perda_ilimitada": False,
}
ALERTAS_PADRAO = {"dias_vencimento": 5, "distancia_strike": 0.02}


def _cliente(config: Path, maquina: str = "PC-SALA") -> TestClient:
    servico = ProfileService(JsonProfileRepository(config), FixedClock(AGORA), maquina)
    return TestClient(create_app([router_perfis(servico)]))


def _pasta(tmp_path: Path, nome: str = "hugo") -> str:
    pasta = tmp_path / "nuvem" / nome
    pasta.mkdir(parents=True)
    return str(pasta)


def test_lista_vazia_antes_de_criar_perfil(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").get("/api/perfis")
    assert (r.status_code, r.json()) == (200, [])


def test_cria_e_lista_perfil(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path / "config.json")
    pasta = _pasta(tmp_path)

    r = cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": pasta})
    assert r.status_code == 201
    assert r.json() == {
        "nome": "Hugo",
        "ativos": ["PETR4", "VALE3"],
        "cdi_anual": 0.15,
        "book": BOOK_MODERADO,
        "alertas": ALERTAS_PADRAO,
    }

    r = cliente.get("/api/perfis")
    assert (r.status_code, r.json()) == (200, [{"nome": "Hugo", "pasta": pasta}])


def test_criar_perfil_repetido_devolve_409(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path / "config.json")
    cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": _pasta(tmp_path)})
    r = cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": _pasta(tmp_path, "outra")})
    assert r.status_code == 409
    assert r.json()["erro"] == "DuplicateProfileError"
    assert "Hugo" in r.json()["mensagem"]


def test_criar_perfil_em_pasta_inexistente_devolve_422_com_o_caminho(tmp_path: Path) -> None:
    ausente = str(tmp_path / "nuvem-desmontada" / "hugo")
    cliente = _cliente(tmp_path / "config.json")

    r = cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": ausente})
    assert r.status_code == 422
    assert r.json()["erro"] == "ProfileFolderUnavailableError"
    assert ausente in r.json()["mensagem"]
    # Nada foi criado em outro lugar nem cadastrado.
    assert cliente.get("/api/perfis").json() == []


def test_abrir_perfil_devolve_o_perfil_e_ele_vira_o_ativo(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path / "config.json")
    cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": _pasta(tmp_path)})

    r = cliente.post("/api/perfis/Hugo/abrir", json={"forcar": False})
    assert r.status_code == 200
    esperado = {
        "nome": "Hugo",
        "ativos": ["PETR4", "VALE3"],
        "cdi_anual": 0.15,
        "book": BOOK_MODERADO,
        "alertas": ALERTAS_PADRAO,
    }
    assert r.json() == esperado
    assert cliente.get("/api/perfil").json() == esperado


def test_abrir_perfil_desconhecido_devolve_404(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").post(
        "/api/perfis/Fantasma/abrir", json={"forcar": False}
    )
    assert (r.status_code, r.json()["erro"]) == (404, "UnknownProfileError")


def test_abrir_perfil_com_barra_no_nome_funciona_pela_url_codificada(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path / "config.json")
    cliente.post("/api/perfis", json={"nome": "Casa/Sala", "pasta": _pasta(tmp_path)})

    r = cliente.post(f"/api/perfis/{quote('Casa/Sala', safe='')}/abrir", json={"forcar": False})
    assert (r.status_code, r.json()["nome"]) == (200, "Casa/Sala")


def test_trava_de_outro_pc_devolve_409_com_pc_e_desde_e_forcar_abre(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    sala = _cliente(config, "PC-SALA")
    quarto = _cliente(config, "PC-QUARTO")
    sala.post("/api/perfis", json={"nome": "Hugo", "pasta": _pasta(tmp_path)})
    assert sala.post("/api/perfis/Hugo/abrir", json={"forcar": False}).status_code == 200

    r = quarto.post("/api/perfis/Hugo/abrir", json={"forcar": False})
    assert r.status_code == 409
    corpo = r.json()
    assert corpo["erro"] == "ProfileLockedError"
    assert "PC-SALA" in corpo["mensagem"]
    # ISO 8601 com fuso: a trava é gravada em horário de Brasília (UTC-3).
    assert corpo["trava"] == {"pc": "PC-SALA", "desde": "2026-11-03T09:00:00-03:00"}
    assert quarto.get("/api/perfil").status_code == 404

    r = quarto.post("/api/perfis/Hugo/abrir", json={"forcar": True})
    assert (r.status_code, r.json()["nome"]) == (200, "Hugo")


def test_abrir_sem_o_corpo_devolve_422_no_formato_unico(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").post("/api/perfis/Hugo/abrir")
    assert (r.status_code, r.json()["erro"]) == (422, "RequisicaoInvalida")


def test_perfil_ativo_antes_de_abrir_devolve_404(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").get("/api/perfil")
    assert r.status_code == 404
    assert r.json()["erro"] == "NoActiveProfileError"


def test_ativos_sao_normalizados_sem_repeticao_e_ficam_gravados(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    cliente = _cliente(config)
    cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": _pasta(tmp_path)})
    cliente.post("/api/perfis/Hugo/abrir", json={"forcar": False})

    r = cliente.put("/api/perfil/ativos", json={"ativos": [" petr4", "bbas3", "PETR4"]})
    assert r.status_code == 200
    esperado = {
        "nome": "Hugo",
        "ativos": ["PETR4", "BBAS3"],
        "cdi_anual": 0.15,
        "book": BOOK_MODERADO,
        "alertas": ALERTAS_PADRAO,
    }
    assert r.json() == esperado
    assert cliente.get("/api/perfil").json() == esperado

    # Gravado no arquivo do perfil: um serviço novo (outro processo) enxerga a mudança.
    outro = _cliente(config)
    assert outro.post("/api/perfis/Hugo/abrir", json={"forcar": False}).json() == esperado


def test_ativos_com_ticker_invalido_devolve_422_de_dominio(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path / "config.json")
    cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": _pasta(tmp_path)})
    cliente.post("/api/perfis/Hugo/abrir", json={"forcar": False})

    r = cliente.put("/api/perfil/ativos", json={"ativos": ["PE TR4"]})
    assert (r.status_code, r.json()["erro"]) == (422, "InvalidDomainValueError")
    assert cliente.get("/api/perfil").json()["ativos"] == ["PETR4", "VALE3"]


def test_ativos_sem_perfil_aberto_devolve_404(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").put("/api/perfil/ativos", json={"ativos": ["PETR4"]})
    assert (r.status_code, r.json()["erro"]) == (404, "NoActiveProfileError")


def test_ativos_com_corpo_fora_do_formato_devolve_422_requisicao_invalida(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").put("/api/perfil/ativos", json={"ativos": "PETR4"})
    assert (r.status_code, r.json()["erro"]) == (422, "RequisicaoInvalida")
    assert r.json()["mensagem"] == "campo 'ativos' deve ser uma lista"


def test_fechar_devolve_204_sem_corpo_e_solta_a_trava(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    sala = _cliente(config, "PC-SALA")
    quarto = _cliente(config, "PC-QUARTO")
    sala.post("/api/perfis", json={"nome": "Hugo", "pasta": _pasta(tmp_path)})
    sala.post("/api/perfis/Hugo/abrir", json={"forcar": False})

    r = sala.post("/api/perfil/fechar")
    assert (r.status_code, r.content) == (204, b"")
    assert sala.get("/api/perfil").status_code == 404
    # Sem trava, o outro PC abre sem pedir confirmação.
    assert quarto.post("/api/perfis/Hugo/abrir", json={"forcar": False}).status_code == 200


def test_fechar_sem_perfil_aberto_tambem_devolve_204(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").post("/api/perfil/fechar")
    assert r.status_code == 204


def _aberto(tmp_path: Path) -> tuple[TestClient, Path]:
    config = tmp_path / "config.json"
    cliente = _cliente(config)
    cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": _pasta(tmp_path)})
    cliente.post("/api/perfis/Hugo/abrir", json={"forcar": False})
    return cliente, config


def _valores(**mudancas: object) -> dict[str, object]:
    return {k: v for k, v in BOOK_MODERADO.items() if k != "preset"} | mudancas


def test_trocar_o_preset_do_book_salva_os_padroes_dele(tmp_path: Path) -> None:
    cliente, config = _aberto(tmp_path)

    r = cliente.put("/api/perfil/book", json={"preset": "arrojado"})
    assert r.status_code == 200
    assert r.json()["book"] == {
        "preset": "arrojado",
        "delta_min": 0.25,
        "delta_max": 0.45,
        "negocios_min": 3,
        "spread_max": 0.35,
        "risco_max": 10000.0,
        "vencimentos": 3,
        "piso_protecao": 0.85,
        "perda_ilimitada": True,
    }
    outro = _cliente(config)
    assert outro.post("/api/perfis/Hugo/abrir", json={"forcar": False}).json() == r.json()


def test_valores_editados_do_book_ficam_salvos_e_voltar_ao_padrao_os_descarta(
    tmp_path: Path,
) -> None:
    cliente, _ = _aberto(tmp_path)

    r = cliente.put(
        "/api/perfil/book", json={"preset": "moderado", "valores": _valores(negocios_min=50)}
    )
    assert r.json()["book"] == BOOK_MODERADO | {"negocios_min": 50}
    assert cliente.get("/api/perfil").json()["book"]["negocios_min"] == 50

    r = cliente.put("/api/perfil/book", json={"preset": "moderado"})
    assert r.json()["book"] == BOOK_MODERADO


def test_book_com_faixa_invalida_devolve_422_e_nao_grava(tmp_path: Path) -> None:
    cliente, _ = _aberto(tmp_path)

    r = cliente.put(
        "/api/perfil/book", json={"preset": "moderado", "valores": _valores(delta_min=0.5)}
    )
    assert (r.status_code, r.json()["erro"]) == (422, "InvalidDomainValueError")
    assert cliente.get("/api/perfil").json()["book"] == BOOK_MODERADO


def test_book_com_preset_desconhecido_e_requisicao_invalida(tmp_path: Path) -> None:
    cliente, _ = _aberto(tmp_path)
    r = cliente.put("/api/perfil/book", json={"preset": "agressivo"})
    assert (r.status_code, r.json()["erro"]) == (422, "RequisicaoInvalida")


def test_book_sem_perfil_aberto_devolve_404(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").put("/api/perfil/book", json={"preset": "moderado"})
    assert (r.status_code, r.json()["erro"]) == (404, "NoActiveProfileError")


def test_perfil_mostra_os_alertas_padrao(tmp_path: Path) -> None:
    cliente, _ = _aberto(tmp_path)
    assert cliente.get("/api/perfil").json()["alertas"] == ALERTAS_PADRAO


def test_alertas_editados_ficam_salvos(tmp_path: Path) -> None:
    cliente, config = _aberto(tmp_path)
    corpo = {"dias_vencimento": 10, "distancia_strike": 0.03}
    r = cliente.put("/api/perfil/alertas", json=corpo)
    assert (r.status_code, r.json()["alertas"]) == (200, corpo)
    outro = _cliente(config)
    assert outro.post("/api/perfis/Hugo/abrir", json={"forcar": False}).json()["alertas"] == corpo


def test_alertas_fora_da_faixa_devolvem_422_e_nao_gravam(tmp_path: Path) -> None:
    cliente, _ = _aberto(tmp_path)
    r = cliente.put("/api/perfil/alertas", json={"dias_vencimento": 5, "distancia_strike": 0.5})
    assert (r.status_code, r.json()["erro"]) == (422, "InvalidDomainValueError")
    assert cliente.get("/api/perfil").json()["alertas"]["distancia_strike"] == 0.02


def test_alertas_sem_perfil_aberto_devolve_404(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "config.json").put(
        "/api/perfil/alertas", json={"dias_vencimento": 5, "distancia_strike": 0.02}
    )
    assert (r.status_code, r.json()["erro"]) == (404, "NoActiveProfileError")
