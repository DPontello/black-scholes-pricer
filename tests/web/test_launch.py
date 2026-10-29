"""Comando ``app`` (Task 14): pasta de configuração, porta, janela de app e frontend ausente."""

import socket
from pathlib import Path

import pytest

from options_engine.__main__ import main
from options_engine.adapters.inbound.web import launch
from options_engine.adapters.inbound.web.launch import (
    app_window_command,
    find_free_port,
    platform_config_dir,
    windows_edge_paths,
)

URL = "http://127.0.0.1:8765/"


def _which(*disponiveis: str):  # type: ignore[no-untyped-def]  # justificativa: fábrica de teste
    return lambda nome: f"/usr/bin/{nome}" if nome in disponiveis else None


def _sem_flatpak(_app_id: str) -> bool:
    return False


# --- pasta de configuração -----------------------------------------------------------------------


def test_pasta_de_configuracao_no_linux_segue_o_xdg() -> None:
    assert platform_config_dir("Linux", {"XDG_CONFIG_HOME": "/x"}, Path("/h")) == Path(
        "/x/painel-opcoes"
    )
    assert platform_config_dir("Linux", {}, Path("/h")) == Path("/h/.config/painel-opcoes")
    # XDG relativo é ignorado, como manda a especificação.
    assert platform_config_dir("Linux", {"XDG_CONFIG_HOME": "rel"}, Path("/h")) == Path(
        "/h/.config/painel-opcoes"
    )


def test_pasta_de_configuracao_no_windows_fica_no_appdata() -> None:
    appdata = r"C:\Users\Hugo\AppData\Roaming"
    assert platform_config_dir("Windows", {"APPDATA": appdata}, Path("/h")) == (
        Path(appdata) / "PainelOpcoes"
    )
    assert platform_config_dir("Windows", {}, Path("/h")) == Path("/h/AppData/Roaming/PainelOpcoes")


# --- porta ---------------------------------------------------------------------------------------


def test_porta_preferida_livre_e_ela_mesma() -> None:
    livre = find_free_port(0)  # o SO escolhe uma livre; ela segue livre logo depois
    assert find_free_port(livre) == livre


def test_porta_ocupada_vira_outra_livre() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ocupada:
        ocupada.bind(("127.0.0.1", 0))
        ocupada.listen()
        porta = ocupada.getsockname()[1]
        outra = find_free_port(porta)
    assert outra != porta


# --- janela de app -------------------------------------------------------------------------------


def test_janela_no_windows_usa_o_edge_do_path() -> None:
    assert app_window_command("Windows", URL, _which("msedge"), _sem_flatpak) == (
        "/usr/bin/msedge",
        f"--app={URL}",
    )


def test_janela_no_windows_acha_o_edge_fora_do_path(tmp_path: Path) -> None:
    edge = tmp_path / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_bytes(b"")
    caminhos = windows_edge_paths(
        {"ProgramFiles(x86)": str(tmp_path / "nada"), "ProgramFiles": str(tmp_path)}
    )
    assert app_window_command("Windows", URL, _which(), _sem_flatpak, caminhos) == (
        str(edge),
        f"--app={URL}",
    )


def test_janela_no_linux_prefere_o_chrome_nativo_e_depois_o_flatpak() -> None:
    assert app_window_command("Linux", URL, _which("chromium", "brave-browser"), _sem_flatpak) == (
        "chromium",
        f"--app={URL}",
    )
    so_flatpak = app_window_command(
        "Linux", URL, _which(), lambda app_id: app_id == "com.google.Chrome"
    )
    assert so_flatpak == ("flatpak", "run", "com.google.Chrome", f"--app={URL}")


def test_sem_navegador_de_janela_de_app_devolve_none() -> None:
    assert app_window_command("Linux", URL, _which(), _sem_flatpak) is None
    assert app_window_command("Windows", URL, _which(), _sem_flatpak) is None


# --- comando -------------------------------------------------------------------------------------


def test_app_sem_o_frontend_compilado_sai_com_codigo_2_e_mensagem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(launch, "default_static_dir", lambda: tmp_path / "nao-existe")
    assert main(["app", "--sem-janela", "--sem-ponte"]) == 2
    assert "npm --prefix frontend run build" in capsys.readouterr().err
