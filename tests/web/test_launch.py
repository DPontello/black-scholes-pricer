"""Comando ``app`` (Task 14): pasta de configuração, porta, janela de app e frontend ausente."""

import logging
import logging.handlers
import os
import platform
import socket
import sys
import urllib.error
from collections.abc import Callable
from pathlib import Path

import pytest

from options_engine.__main__ import main
from options_engine.adapters.inbound.web import launch
from options_engine.adapters.inbound.web.launch import (
    app_window_command,
    downloads_dir,
    find_free_port,
    platform_config_dir,
    windows_edge_paths,
)

URL = "http://127.0.0.1:8765/"


def test_downloads_no_windows_vem_do_registro_mesmo_movida() -> None:
    movida = downloads_dir("Windows", {}, Path("/h"), lambda: r"D:\Nuvem\Downloads")
    assert movida == Path(r"D:\Nuvem\Downloads")
    assert downloads_dir("Windows", {}, Path("/h"), lambda: None) == Path("/h/Downloads")


def test_downloads_no_linux_segue_o_user_dirs(tmp_path: Path) -> None:
    config = tmp_path / ".config"
    config.mkdir()
    assert downloads_dir("Linux", {}, tmp_path) == tmp_path / "Downloads"
    linhas = ['XDG_DESKTOP_DIR="$HOME/Área de trabalho"', 'XDG_DOWNLOAD_DIR="$HOME/Transferências"']
    (config / "user-dirs.dirs").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    assert downloads_dir("Linux", {}, tmp_path) == tmp_path / "Transferências"


def _which(*disponiveis: str):  # type: ignore[no-untyped-def]  # justificativa: fábrica de teste
    return lambda nome: f"/usr/bin/{nome}" if nome in disponiveis else None


def _sem_flatpak(_app_id: str) -> bool:
    return False


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


def test_app_sem_o_frontend_compilado_sai_com_codigo_2_e_mensagem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(launch, "default_static_dir", lambda meipass=None: tmp_path / "nao-existe")
    assert main(["app", "--sem-janela", "--sem-ponte"]) == 2
    assert "npm --prefix frontend run build" in capsys.readouterr().err


# --------------------------------------------------------------------------- app instalado


def test_tela_do_app_instalado_fica_dentro_do_executavel(tmp_path: Path) -> None:
    assert launch.default_static_dir(tmp_path) == tmp_path / "static"
    assert launch.default_static_dir().name == "static"
    assert launch.default_static_dir().parent.name == "web"


def test_log_do_app_instalado_e_rotativo_na_pasta_de_configuracao(tmp_path: Path) -> None:
    handler = launch.log_handler(tmp_path / "cfg")
    try:
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert Path(handler.baseFilename) == tmp_path / "cfg" / "logs" / "app.log"
        assert handler.maxBytes == launch.LOG_MAX_BYTES
        assert handler.backupCount == launch.LOG_BACKUPS
    finally:
        handler.close()


def test_console_do_app_instalado_guarda_so_a_ultima_execucao(tmp_path: Path) -> None:
    with launch.console_log(tmp_path) as saida:
        saida.write("primeira\n")
    with launch.console_log(tmp_path) as saida:
        saida.write("segunda\n")
    assert (tmp_path / "logs" / "console.log").read_text(encoding="utf-8") == "segunda\n"


def _config_isolada(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Tira a configuração da pasta do usuário real, nos dois sistemas, e devolve a que o app vai
    usar. No Linux pelo home: o ``XDG_CONFIG_HOME`` só vale com caminho POSIX, e o ``tmp_path`` do
    Windows não é um. No Windows pelo ``APPDATA``."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return launch.platform_config_dir(platform.system(), os.environ, Path.home())


def test_comando_app_instalado_usa_a_tela_a_ponte_e_o_log_de_dentro_do_executavel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from options_engine.config import web_app

    meipass = tmp_path / "_internal"
    (meipass / "static").mkdir(parents=True)
    (meipass / "static" / "index.html").write_text("<html></html>", encoding="utf-8")
    programa = tmp_path / "PainelOpcoes"
    recebido: dict[str, object] = {}

    def build_falso(**kwargs: object) -> object:
        recebido.update(kwargs)
        return object()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(programa / "PainelOpcoes.exe"))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    config = _config_isolada(monkeypatch, tmp_path)
    monkeypatch.setattr(web_app, "build_web_app", build_falso)
    monkeypatch.setattr(launch, "find_free_port", lambda porta: 8765)
    monkeypatch.setattr(launch, "already_running", lambda porta: False)
    monkeypatch.setattr(launch, "serve", lambda *a, **k: None)
    antes = list(logging.getLogger().handlers)
    try:
        assert main(["app", "--sem-janela", "--sem-ponte"]) == 0
    finally:
        for handler in logging.getLogger().handlers:
            if handler not in antes:
                logging.getLogger().removeHandler(handler)
                handler.close()
        if sys.stdout is not None:
            sys.stdout.close()

    assert recebido["static_dir"] == meipass / "static"
    assert recebido["frozen_dir"] == programa
    logs = config / "logs"
    assert (logs / "app.log").exists()
    assert "Painel de Opções em http://127.0.0.1:8765/" in (logs / "console.log").read_text(
        encoding="utf-8"
    )


def test_comando_app_fora_do_executavel_nao_passa_pasta_do_programa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from options_engine.config import web_app

    estatico = tmp_path / "static"
    estatico.mkdir()
    (estatico / "index.html").write_text("<html></html>", encoding="utf-8")
    recebido: dict[str, object] = {}

    def build_falso(**kwargs: object) -> object:
        recebido.update(kwargs)
        return object()

    monkeypatch.delattr(sys, "frozen", raising=False)
    config = _config_isolada(monkeypatch, tmp_path)
    monkeypatch.setattr(launch, "default_static_dir", lambda meipass=None: estatico)
    monkeypatch.setattr(web_app, "build_web_app", build_falso)
    monkeypatch.setattr(launch, "find_free_port", lambda porta: 8765)
    monkeypatch.setattr(launch, "already_running", lambda porta: False)
    monkeypatch.setattr(launch, "serve", lambda *a, **k: None)
    assert main(["app", "--sem-janela", "--sem-ponte"]) == 0
    assert recebido["frozen_dir"] is None
    assert not (config / "logs").exists()


# --------------------------------------------------------------------------- já está aberto


def _erro(url: str) -> object:
    raise urllib.error.URLError("recusada")


def test_ja_aberto_quando_a_porta_responde_com_o_nome_do_app() -> None:
    urls: list[str] = []

    def saude(url: str) -> object:
        urls.append(url)
        return {"status": "ok", "versao": "0.5.0", "app": "painel-de-opcoes"}

    assert launch.already_running(8765, saude)
    assert urls == ["http://127.0.0.1:8765/"]


@pytest.mark.parametrize(
    "fetch",
    [
        _erro,
        lambda url: {"status": "ok"},  # outro serviço na porta
        lambda url: {"status": "ok", "app": "outro-app"},
        lambda url: ["painel-de-opcoes"],
    ],
)
def test_nao_esta_aberto_sem_resposta_ou_com_outro_servico(fetch: Callable[[str], object]) -> None:
    assert not launch.already_running(8765, fetch)


def test_json_ilegivel_na_porta_nao_e_o_app() -> None:
    def ilegivel(url: str) -> object:
        raise ValueError("Expecting value")

    assert not launch.already_running(8765, ilegivel)


def test_porta_sem_ninguem_nao_esta_aberto() -> None:
    assert not launch.already_running(find_free_port(0))


def test_comando_app_ja_aberto_so_abre_a_janela_na_porta_dele(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from options_engine.config import web_app

    estatico = tmp_path / "static"
    estatico.mkdir()
    (estatico / "index.html").write_text("<html></html>", encoding="utf-8")
    janelas: list[str] = []

    def nao_pode(*args: object, **kwargs: object) -> object:
        raise AssertionError("não deveria subir outro servidor")

    _config_isolada(monkeypatch, tmp_path)
    monkeypatch.setattr(launch, "default_static_dir", lambda meipass=None: estatico)
    monkeypatch.setattr(launch, "already_running", lambda porta: porta == 8770)
    monkeypatch.setattr(launch, "open_window", lambda comando, url: janelas.append(url))
    monkeypatch.setattr(web_app, "build_web_app", nao_pode)
    monkeypatch.setattr(launch, "serve", nao_pode)
    assert main(["app", "--porta", "8770"]) == 0
    assert janelas == ["http://127.0.0.1:8770/"]
    assert main(["app", "--porta", "8770", "--sem-janela"]) == 0
    assert janelas == ["http://127.0.0.1:8770/"]
