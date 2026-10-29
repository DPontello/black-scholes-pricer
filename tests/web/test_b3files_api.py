"""API dos arquivos da B3 — upload pelo conteúdo cru e listagem, com a biblioteca real."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.b3files import router_arquivos_b3
from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from options_engine.adapters.outbound.clock import FixedClock
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "cotahist"
AGORA = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
_OCTET = {"Content-Type": "application/octet-stream"}


def _cliente(raiz: Path) -> TestClient:
    return TestClient(create_app([router_arquivos_b3(B3FileLibrary(raiz, FixedClock(AGORA)))]))


def test_upload_do_cadastro_devolve_201_com_tipo_nome_e_data(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "mercado").post(
        "/api/mercado/arquivos",
        params={"nome": INSTRUMENTS_NAME},
        content=(FIXTURE / INSTRUMENTS_NAME).read_bytes(),
        headers=_OCTET,
    )
    assert r.status_code == 201
    assert r.json() == {"tipo": "cadastro", "nome": INSTRUMENTS_NAME, "data": "2026-10-23"}


def test_upload_do_cotahist_sem_content_type_tambem_funciona(tmp_path: Path) -> None:
    # O navegador manda o tipo MIME que o SO sabe (ou nenhum): o corpo é lido cru de qualquer jeito.
    r = _cliente(tmp_path / "mercado").post(
        "/api/mercado/arquivos",
        params={"nome": COTAHIST_NAME},
        content=(FIXTURE / COTAHIST_NAME).read_bytes(),
    )
    assert (r.status_code, r.json()["tipo"], r.json()["data"]) == (201, "cotahist", "2026-10-23")


def test_upload_de_pdf_devolve_422_com_o_motivo_e_nao_grava(tmp_path: Path) -> None:
    raiz = tmp_path / "mercado"
    r = _cliente(raiz).post(
        "/api/mercado/arquivos",
        params={"nome": "nota.pdf"},
        content=b"%PDF-1.4 ...",
        headers={"Content-Type": "application/pdf"},
    )
    assert r.status_code == 422
    corpo = r.json()
    assert corpo["erro"] == "B3FileRejectedError"
    assert "tipo de arquivo não reconhecido" in corpo["mensagem"]
    assert not [p for p in raiz.rglob("*") if p.is_file()]


def test_upload_com_nome_fora_da_raiz_devolve_422_e_nao_grava(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "mercado").post(
        "/api/mercado/arquivos",
        params={"nome": "../../fora.csv"},
        content=(FIXTURE / INSTRUMENTS_NAME).read_bytes(),
        headers=_OCTET,
    )
    assert (r.status_code, r.json()["erro"]) == (422, "B3FileRejectedError")
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_upload_sem_o_parametro_nome_devolve_422_de_validacao(tmp_path: Path) -> None:
    r = _cliente(tmp_path / "mercado").post("/api/mercado/arquivos", content=b"x", headers=_OCTET)
    assert (r.status_code, r.json()["erro"]) == (422, "RequisicaoInvalida")
    assert "nome" in r.json()["mensagem"]


def test_get_lista_os_arquivos_importados_com_a_data_de_importacao(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path / "mercado")
    assert cliente.get("/api/mercado/arquivos").json() == []
    cliente.post(
        "/api/mercado/arquivos",
        params={"nome": INSTRUMENTS_NAME},
        content=(FIXTURE / INSTRUMENTS_NAME).read_bytes(),
        headers=_OCTET,
    )
    r = cliente.get("/api/mercado/arquivos")
    assert r.status_code == 200
    assert r.json() == [
        {
            "tipo": "cadastro",
            "nome": INSTRUMENTS_NAME,
            "data": "2026-10-23",
            "importado_em": "2026-10-28T15:00:00Z",
        }
    ]
