"""``build_web_app`` — o app montado: saúde, perfis, ciclo de vida da ponte e status da B3."""

import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.outbound.b3_calendar import StaticHolidayCalendar
from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from options_engine.application.ports.outbound import CadastroFreshness
from options_engine.config.web_app import (
    MARKET_DIR_NAME,
    _cotahist_range,
    _freshness,
    _lifespan,
    build_web_app,
)
from tests.adapters._mercado import FIXTURE, biblioteca, relogio
from tests.data.cotahist.build_fixture import INSTRUMENTS_NAME, REFERENCE_SESSION

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
