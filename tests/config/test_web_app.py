"""``build_web_app`` — o app montado: saúde, perfis, ciclo de vida da ponte e status da B3."""

import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.outbound.b3_calendar import StaticHolidayCalendar
from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from options_engine.adapters.outbound.b3files.loaded import LibraryLoader
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.ports.outbound import CadastroFreshness
from options_engine.config.web_app import (
    MARKET_DIR_NAME,
    _close,
    _cotahist_age,
    _cotahist_range,
    _freshness,
    _lifespan,
    build_web_app,
)
from tests.adapters._mercado import FIXTURE, biblioteca, cadastro_com_objetos, relogio
from tests.data.cotahist.build_fixture import INSTRUMENTS_NAME, NOVEMBRO, REFERENCE_SESSION

CALENDARIO = StaticHolidayCalendar.from_packaged_data()


def _app(config_dir: Path) -> TestClient:
    return TestClient(
        build_web_app(
            config_dir=config_dir,
            static_dir=None,
            bridge=False,
            machine_name="PC-TESTE",
            clock=relogio(),
        )
    )


def test_app_sem_ponte_responde_a_saude_e_os_perfis(tmp_path: Path) -> None:
    with _app(tmp_path) as cliente:
        assert cliente.get("/api/saude").json()["status"] == "ok"
        assert cliente.get("/api/perfis").json() == []


def test_desligar_o_app_solta_a_trava_do_perfil_aberto(tmp_path: Path) -> None:
    pasta = tmp_path / "perfil-hugo"
    pasta.mkdir()
    with _app(tmp_path / "config") as cliente:
        assert cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": str(pasta)}).is_success
        assert cliente.post("/api/perfis/Hugo/abrir", json={"forcar": False}).is_success
        assert (pasta / "perfil.lock").is_file()
    assert not (pasta / "perfil.lock").exists()


@dataclass
class _Registro:
    chamadas: list[str] = field(default_factory=list)
    falhar: frozenset[str] = frozenset()

    def anotar(self, nome: str) -> None:
        self.chamadas.append(nome)
        if nome in self.falhar:
            raise RuntimeError(f"falha simulada em {nome}")


@dataclass
class _Ponte:
    registro: _Registro

    def start(self) -> None:
        self.registro.anotar("ponte.start")

    def ensure_running(self) -> None:
        self.registro.anotar("ponte.ensure_running")

    def stop(self) -> None:
        self.registro.anotar("ponte.stop")


@dataclass
class _Cliente:
    registro: _Registro

    def start(self) -> None:
        self.registro.anotar("cliente.start")

    def stop(self) -> None:
        self.registro.anotar("cliente.stop")


@dataclass
class _Perfis:
    registro: _Registro

    def close(self) -> None:
        self.registro.anotar("perfis.close")


def _rodar_ciclo(registro: _Registro, *, com_ponte: bool = True) -> None:
    ciclo = _lifespan(
        _Perfis(registro),  # type: ignore[arg-type]  # justificativa: só close é usado
        _Cliente(registro),
        _Ponte(registro) if com_ponte else None,
        ensure_interval_s=0.01,
    )
    with TestClient(create_app([], lifespan=ciclo)) as cliente:
        assert cliente.get("/api/saude").status_code == 200
        _esperar(lambda: "ponte.ensure_running" in registro.chamadas or not com_ponte)


def _esperar(condicao: Callable[[], bool], prazo_s: float = 5.0) -> None:
    fim = time.monotonic() + prazo_s
    while not condicao():
        assert time.monotonic() < fim, "a condição não aconteceu no prazo"
        time.sleep(0.01)


def test_ciclo_de_vida_sobe_o_cliente_e_a_ponte_confere_e_encerra_tudo_ao_desligar() -> None:
    registro = _Registro()
    _rodar_ciclo(registro)
    assert registro.chamadas[:2] == ["cliente.start", "ponte.start"]
    assert registro.chamadas[-3:] == ["ponte.stop", "cliente.stop", "perfis.close"]


def test_sem_ponte_o_desligar_so_fecha_o_perfil() -> None:
    registro = _Registro()
    _rodar_ciclo(registro, com_ponte=False)
    assert registro.chamadas == ["perfis.close"]


def test_ponte_que_nao_sobe_nao_derruba_o_app_e_continua_sendo_conferida() -> None:
    registro = _Registro(falhar=frozenset({"ponte.start"}))
    _rodar_ciclo(registro)
    assert "ponte.ensure_running" in registro.chamadas


def test_falhas_ao_encerrar_nao_impedem_soltar_a_trava_do_perfil() -> None:
    registro = _Registro(falhar=frozenset({"ponte.stop", "cliente.stop", "perfis.close"}))
    _rodar_ciclo(registro)  # sem exceção
    assert registro.chamadas[-3:] == ["ponte.stop", "cliente.stop", "perfis.close"]


def test_idade_do_cadastro_datado_em_dias_uteis(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path)
    # 23/10 (sexta) a 28/10: 23, 26 e 27 contam (intervalo meio-aberto do calendário).
    assert _freshness(lib, CALENDARIO, relogio()) == CadastroFreshness(REFERENCE_SESSION, 3, False)


def test_sem_cadastro_ou_sem_data_no_nome_o_status_diz_por_que(tmp_path: Path) -> None:
    vazia = B3FileLibrary(tmp_path / "vazia", relogio())
    assert _freshness(vazia, CALENDARIO, relogio()) == "nenhum Cadastro de Instrumentos importado"
    sem_data = B3FileLibrary(tmp_path / "sem-data", relogio())
    sem_data.import_file("cadastro.csv", (FIXTURE / INSTRUMENTS_NAME).read_bytes())
    motivo = _freshness(sem_data, CALENDARIO, relogio())
    assert isinstance(motivo, str) and "cadastro.csv" in motivo and "_AAAAMMDD" in motivo


def test_faixa_de_pregoes_dos_cotahist_importados(tmp_path: Path) -> None:
    assert _cotahist_range(B3FileLibrary(tmp_path / "vazia", relogio())) is None
    inicio, fim = _cotahist_range(biblioteca(tmp_path / "cheia")) or (None, None)
    assert fim == REFERENCE_SESSION
    assert isinstance(inicio, date) and inicio < fim


def _hoje(ano: int, mes: int, dia: int) -> FixedClock:
    return FixedClock(datetime(ano, mes, dia, 15, 0, tzinfo=UTC))


def test_idade_do_cotahist_em_dias_uteis(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path)
    # 23/10 (sexta) a 03/11: 23 e 26 a 30/10 contam (intervalo meio-aberto); 02/11 é feriado.
    assert _cotahist_age(lib, CALENDARIO, _hoje(2026, 11, 3)) == 6


def test_idade_do_cotahist_sem_arquivo_e_nula(tmp_path: Path) -> None:
    vazia = B3FileLibrary(tmp_path / "vazia", relogio())
    assert _cotahist_age(vazia, CALENDARIO, relogio()) is None


def test_idade_do_cotahist_com_pregao_no_futuro_e_zero(tmp_path: Path) -> None:
    assert _cotahist_age(biblioteca(tmp_path), CALENDARIO, _hoje(2026, 10, 20)) == 0


def test_idade_do_cotahist_fora_do_calendario_e_nula(tmp_path: Path) -> None:
    assert _cotahist_age(biblioteca(tmp_path), CALENDARIO, _hoje(2028, 6, 1)) is None


def test_a_biblioteca_do_app_mora_em_config_dir_mercado(tmp_path: Path) -> None:
    biblioteca(tmp_path / MARKET_DIR_NAME)
    with _app(tmp_path) as cliente:
        nomes = {arquivo["nome"] for arquivo in cliente.get("/api/mercado/arquivos").json()}
    assert INSTRUMENTS_NAME in nomes


def test_o_nucleo_e_o_painel_de_linha_de_comando_nao_importam_o_fastapi() -> None:
    codigo = (
        "import sys, options_engine.config.composition, options_engine.__main__; "
        "print('fastapi' in sys.modules)"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert saida == "False"


@dataclass
class _Varredor:
    passadas: int = 0

    def scan(self) -> tuple[()]:
        self.passadas += 1
        return ()


def test_ciclo_de_vida_varre_a_pasta_downloads_de_tempos_em_tempos() -> None:
    varredor = _Varredor()
    registro = _Registro()
    ciclo = _lifespan(
        _Perfis(registro),  # type: ignore[arg-type]  # justificativa: só close é usado
        _Cliente(registro),
        None,
        varredor,
        scan_interval_s=0.01,
    )
    with TestClient(create_app([], lifespan=ciclo)):
        _esperar(lambda: varredor.passadas >= 3)
    assert registro.chamadas == ["perfis.close"]


def test_app_com_downloads_expoe_a_importacao_automatica(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    app = build_web_app(
        config_dir=tmp_path / "config",
        static_dir=None,
        bridge=False,
        machine_name="PC-TESTE",
        clock=relogio(),
        downloads_dir=downloads,
    )
    with TestClient(app) as cliente:
        corpo = cliente.get("/api/mercado/arquivos/automatico").json()
    assert corpo == {"pasta": str(downloads), "eventos": []}


def test_carteira_do_app_usa_o_cadastro_e_os_cotahist_da_biblioteca(tmp_path: Path) -> None:
    biblioteca(tmp_path / "config" / MARKET_DIR_NAME, cadastro=cadastro_com_objetos())
    pasta = tmp_path / "perfil-hugo"
    pasta.mkdir()
    venda = {
        "ativo": "PETR4",
        "nome": "call vendida",
        "data": REFERENCE_SESSION.isoformat(),
        "pernas": [
            {"ticker": "PETRK300", "lado": "venda", "execucoes": [{"quantidade": 100, "preco": 1}]}
        ],
    }
    with _app(tmp_path / "config") as cliente:
        assert cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": str(pasta)}).is_success
        assert cliente.post("/api/perfis/Hugo/abrir", json={"forcar": False}).is_success
        assert cliente.post("/api/carteira/operacoes", json=venda).status_code == 201
        carteira = cliente.get("/api/carteira").json()
    assert carteira["fonte"] == "fim_de_dia"  # sem ponte: os preços de zerar são do COTAHIST
    (perna,) = carteira["operacoes"][0]["pernas"]
    assert (perna["vencimento"], perna["strike"]) == (NOVEMBRO.isoformat(), 30.0)
    assert perna["marca"]["preco"] is not None
    assert len(list((pasta / "operacoes").iterdir())) == 1


def test_fechamento_do_pregao_vem_dos_cotahist_importados(tmp_path: Path) -> None:
    loader = LibraryLoader(biblioteca(tmp_path / "mercado"))
    assert _close(loader, "PETR4", REFERENCE_SESSION) == 30.0
    assert _close(loader, "PETR4", date(2026, 11, 19)) is None
    vazio = LibraryLoader(B3FileLibrary(tmp_path / "vazia", relogio()))
    assert _close(vazio, "PETR4", REFERENCE_SESSION) is None


def test_book_do_app_usa_o_fim_de_dia_e_o_historico_da_biblioteca(tmp_path: Path) -> None:
    biblioteca(tmp_path / "config" / MARKET_DIR_NAME, cadastro=cadastro_com_objetos())
    pasta = tmp_path / "perfil-hugo"
    pasta.mkdir()
    with _app(tmp_path / "config") as cliente:
        assert cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": str(pasta)}).is_success
        assert cliente.post("/api/perfis/Hugo/abrir", json={"forcar": False}).is_success
        assert cliente.put("/api/perfil/ativos", json={"ativos": ["PETR4"]}).is_success
        r = cliente.get("/api/book")
    assert r.status_code == 200
    corpo = r.json()
    assert (corpo["pregao"], corpo["fonte"]) == (REFERENCE_SESSION.isoformat(), "fim_de_dia")
    assert corpo["indisponiveis"] == []
    (contexto,) = corpo["contextos"]
    assert contexto["ativo"] == "PETR4"
    # A fixture tem opções só no pregão de referência: IV 30 sem rank, regime pela HV.
    assert contexto["iv30"] is not None and contexto["iv_rank"] is None
    assert contexto["regime_pela_hv"] is True
    # O montador entra na fiação do book: item executável sai com o resultado no vencimento.
    itens = [i for familia in corpo["familias"].values() for i in familia["itens"]]
    assert any(i["resultado"] is not None for i in itens)
    assert (tmp_path / "config" / MARKET_DIR_NAME / "vol_history.sqlite").exists()


def test_alertas_e_rolagem_do_app_montados(tmp_path: Path) -> None:
    biblioteca(tmp_path / "config" / MARKET_DIR_NAME, cadastro=cadastro_com_objetos())
    pasta = tmp_path / "perfil-hugo"
    pasta.mkdir()
    venda = {
        "ativo": "PETR4",
        "nome": "call vendida",
        "data": REFERENCE_SESSION.isoformat(),
        "pernas": [
            {"ticker": "PETRK300", "lado": "venda", "execucoes": [{"quantidade": 100, "preco": 1}]}
        ],
    }
    with _app(tmp_path / "config") as cliente:
        assert cliente.post("/api/perfis", json={"nome": "Hugo", "pasta": str(pasta)}).is_success
        assert cliente.post("/api/perfis/Hugo/abrir", json={"forcar": False}).is_success
        operacao = cliente.post("/api/carteira/operacoes", json=venda).json()["id"]
        alertas = cliente.get("/api/alertas")
        rolagem = cliente.get(f"/api/alertas/rolagem/{operacao}")
    assert alertas.status_code == 200, alertas.json()
    assert alertas.json()["fonte"] == "fim_de_dia"
    assert rolagem.status_code == 200, rolagem.json()
    assert (rolagem.json()["vencimento_atual"], rolagem.json()["pedido"]) == (
        NOVEMBRO.isoformat(),
        None,  # registrada sem modelo
    )
