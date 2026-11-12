"""Atualização do app instalado: confere no GitHub se há versão nova, baixa o instalador, confere
o SHA-256 e o abre em modo silencioso.

Só stdlib (``urllib``), como o ``launch.py``. Rede, processo e thread entram por funções
injetadas no ``Atualizador``; ``atualizador_do_app`` monta as reais."""

import hashlib
import http.client
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

__all__ = [
    "ATRASO_ENCERRAR_S",
    "PREFIXO_DOWNLOAD",
    "URL_ULTIMA_VERSAO",
    "VALIDADE_S",
    "Atualizador",
    "EstadoAtualizacao",
    "Fase",
    "VersaoNova",
    "argumentos_do_instalador",
    "atualizador_do_app",
    "ler_release",
    "numeros",
]

_log = logging.getLogger(__name__)

URL_ULTIMA_VERSAO: Final = (
    "https://api.github.com/repos/DPontello/black-scholes-pricer/releases/latest"
)
PREFIXO_DOWNLOAD: Final = "https://github.com/DPontello/black-scholes-pricer/releases/download/"
# A API sem token aceita 60 consultas por hora: o resultado, bom ou ruim, vale por 30 min.
VALIDADE_S: Final = 1800.0
# Tempo para o instalador abrir antes de o servidor se encerrar.
ATRASO_ENCERRAR_S: Final = 2.0
_PEDACO: Final = 64 * 1024
_NUMEROS: Final = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_TAG: Final = re.compile(r"v(\d+\.\d+\.\d+)")
_DIGEST: Final = re.compile(r"sha256:([0-9a-fA-F]{64})")
_MARCADOR: Final = re.compile(r"^[-*+]\s+")
_FALHAS_DO_DOWNLOAD: Final = (OSError, ValueError, http.client.HTTPException)

Fase = Literal["parado", "baixando", "instalando", "erro"]


@dataclass(frozen=True, slots=True)
class VersaoNova:
    versao: str
    novidades: tuple[str, ...]
    tamanho: int
    url: str
    sha256: str | None  # hex minúsculo, do campo "digest" ("sha256:<hex>")


@dataclass(frozen=True, slots=True)
class EstadoAtualizacao:
    fase: Fase
    baixado: int = 0
    total: int = 0
    mensagem: str = ""


def numeros(versao: str) -> tuple[int, int, int] | None:
    """Os três primeiros números da versão: ``0.5.0.dev0`` vale ``(0, 5, 0)``."""
    achado = _NUMEROS.match(versao)
    return None if achado is None else (int(achado[1]), int(achado[2]), int(achado[3]))


def _novidades(body: object) -> tuple[str, ...]:
    if not isinstance(body, str):
        return ()
    linhas = (_MARCADOR.sub("", linha.strip()) for linha in body.splitlines())
    return tuple(linha for linha in linhas if linha)


class _ReleaseEstranho(Exception):
    """A resposta da API não tem a forma de um release utilizável; o motivo vai para o log."""


def ler_release(corpo: object, atual: str) -> VersaoNova | None:
    """A versão nova que o release da API do GitHub oferece, ou ``None``. Versão igual ou mais
    velha é o normal e não registra nada; release que não é o esperado (tag fora de ``vX.Y.Z``,
    sem o arquivo do instalador, endereço fora do release do projeto, tamanho ou ``digest`` que
    não são o que a API devolve) também dá ``None``, mas com uma linha de aviso no log."""
    try:
        return _ler_release(corpo, atual)
    except _ReleaseEstranho as estranho:
        _log.warning("o release do GitHub não é o esperado: %s", estranho)
        return None


def _ler_release(corpo: object, atual: str) -> VersaoNova | None:
    if not isinstance(corpo, dict):
        raise _ReleaseEstranho("a resposta não é um objeto JSON")
    tag = corpo.get("tag_name")
    achado = _TAG.fullmatch(tag) if isinstance(tag, str) else None
    if achado is None:
        raise _ReleaseEstranho(f"tag_name fora de vX.Y.Z: {str(tag)[:40]!r}")
    velha = numeros(atual)
    if velha is None:
        raise _ReleaseEstranho(f"versão atual ilegível: {atual[:40]!r}")
    versao = achado[1]
    nova = numeros(versao)
    if nova is None or nova <= velha:
        return None
    nome = f"PainelOpcoes-{versao}-setup.exe"
    assets = corpo.get("assets")
    arquivos = assets if isinstance(assets, list) else []
    arquivo = next((a for a in arquivos if isinstance(a, dict) and a.get("name") == nome), None)
    if arquivo is None:
        raise _ReleaseEstranho(f"sem o arquivo {nome}")
    tamanho = arquivo.get("size")
    url = arquivo.get("browser_download_url")
    digest = arquivo.get("digest")
    if not isinstance(tamanho, int) or isinstance(tamanho, bool) or tamanho <= 0:
        raise _ReleaseEstranho(f"tamanho inválido: {str(tamanho)[:40]!r}")
    if not isinstance(url, str) or not url.startswith(PREFIXO_DOWNLOAD):
        raise _ReleaseEstranho("endereço do arquivo fora do release do projeto")
    sha256 = None
    if digest is not None:
        achado_digest = _DIGEST.fullmatch(digest) if isinstance(digest, str) else None
        if achado_digest is None:
            raise _ReleaseEstranho(f"digest que não é sha256: {str(digest)[:40]!r}")
        sha256 = achado_digest[1].lower()
    return VersaoNova(versao, _novidades(corpo.get("body")), tamanho, url, sha256)


def argumentos_do_instalador(arquivo: Path, pid: int, log: Path) -> list[str]:
    """Instalação silenciosa que espera este processo sair, reabre o app e registra o que fez."""
    return [
        str(arquivo),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/RELANCAR=1",
        f"/ESPERAR={pid}",
        f"/LOG={log}",
    ]


def _em_thread(tarefa: Callable[[], None]) -> None:
    threading.Thread(target=tarefa, name="atualizacao", daemon=True).start()


class Atualizador:
    """Confere se há versão nova (resultado guardado por ``VALIDADE_S``) e faz a atualização em
    segundo plano: baixa, confere, abre o instalador e encerra o servidor. O estado fica atrás de
    um ``Lock``; um pedido durante uma atualização em andamento não abre outro download."""

    def __init__(
        self,
        atual: str,
        *,
        ativo: bool,
        buscar_json: Callable[[str], object],
        baixar: Callable[[str], Iterable[bytes]],
        abrir_instalador: Callable[[Sequence[str]], None],
        encerrar: Callable[[], None],
        pasta: Path,
        log: Path,
        pid: int,
        relogio: Callable[[], float] = time.monotonic,
        esperar: Callable[[float], None] = time.sleep,
        em_segundo_plano: Callable[[Callable[[], None]], None] = _em_thread,
    ) -> None:
        self._atual = atual
        self._ativo = ativo
        self._buscar_json = buscar_json
        self._baixar = baixar
        self._abrir_instalador = abrir_instalador
        self._encerrar = encerrar
        self._pasta = pasta
        self._log = log
        self._pid = pid
        self._relogio = relogio
        self._esperar = esperar
        self._em_segundo_plano = em_segundo_plano
        self._lock = threading.Lock()
        self._estado = EstadoAtualizacao("parado")
        self._lock_consulta = threading.Lock()
        self._consulta: tuple[float, VersaoNova | None] | None = None

    @property
    def atual(self) -> str:
        return self._atual

    @property
    def pasta(self) -> Path:
        return self._pasta

    @property
    def log(self) -> Path:
        return self._log

    def conferir(self) -> VersaoNova | None:
        """A versão nova, ou ``None``. Falha na consulta também dá ``None`` e fica guardada."""
        if not self._ativo:
            return None
        with self._lock_consulta:
            agora = self._relogio()
            if self._consulta is not None and agora - self._consulta[0] < VALIDADE_S:
                return self._consulta[1]
            try:
                nova = ler_release(self._buscar_json(URL_ULTIMA_VERSAO), self._atual)
            except Exception as erro:
                _log.warning("não deu para conferir se há versão nova: %s", erro)
                nova = None
            self._consulta = (agora, nova)
            return nova

    def iniciar(self) -> EstadoAtualizacao:
        """Começa a atualização; durante uma em andamento só devolve o estado dela."""
        nova = self.conferir()
        with self._lock:
            if self._estado.fase in ("baixando", "instalando"):
                return self._estado
            if nova is None:
                self._estado = EstadoAtualizacao("erro", mensagem="não há versão nova para baixar")
                return self._estado
            self._estado = EstadoAtualizacao("baixando", 0, nova.tamanho)
        try:
            self._em_segundo_plano(lambda: self._atualizar(nova))
        except Exception as erro:
            self._falhar_inesperado(self._arquivo(nova), erro)
        return self.estado()

    def estado(self) -> EstadoAtualizacao:
        with self._lock:
            return self._estado

    def _definir(self, estado: EstadoAtualizacao) -> None:
        with self._lock:
            self._estado = estado

    def _arquivo(self, nova: VersaoNova) -> Path:
        return self._pasta / f"PainelOpcoes-{nova.versao}-setup.exe"

    def _atualizar(self, nova: VersaoNova) -> None:
        arquivo = self._arquivo(nova)
        try:
            try:
                baixado, sha256 = self._baixar_para(arquivo, nova)
            except _FALHAS_DO_DOWNLOAD as erro:
                self._falhar(arquivo, "a conexão com o GitHub falhou", erro)
                return
            if not self._confere(nova, baixado, sha256):
                detalhe = f"{baixado} bytes, sha256 {sha256}"
                self._falhar(arquivo, "o arquivo baixado não confere", detalhe)
                return
            try:
                self._abrir_instalador(argumentos_do_instalador(arquivo, self._pid, self._log))
            except (OSError, ValueError) as erro:
                self._falhar(arquivo, "não deu para abrir o instalador", erro)
                return
            self._definir(EstadoAtualizacao("instalando", baixado, nova.tamanho))
            self._esperar(ATRASO_ENCERRAR_S)
            self._encerrar()
        except Exception as erro:
            # Sem isto, uma exceção fora da lista deixaria a janela em "baixando" para sempre.
            self._falhar_inesperado(arquivo, erro)

    def _baixar_para(self, arquivo: Path, nova: VersaoNova) -> tuple[int, str]:
        self._pasta.mkdir(parents=True, exist_ok=True)
        calculo = hashlib.sha256()
        baixado = 0
        with arquivo.open("wb") as saida:
            for pedaco in self._baixar(nova.url):
                saida.write(pedaco)
                calculo.update(pedaco)
                baixado += len(pedaco)
                self._definir(EstadoAtualizacao("baixando", baixado, nova.tamanho))
        return baixado, calculo.hexdigest()

    @staticmethod
    def _confere(nova: VersaoNova, baixado: int, sha256: str) -> bool:
        # Sem digest na API, só o tamanho dá para conferir.
        return sha256 == nova.sha256 if nova.sha256 is not None else baixado == nova.tamanho

    def _falhar_inesperado(self, arquivo: Path, erro: Exception) -> None:
        _log.exception("erro inesperado na atualização", exc_info=erro)
        self._falhar(arquivo, "erro inesperado na atualização", erro)

    def _falhar(self, arquivo: Path, mensagem: str, detalhe: object) -> None:
        _log.warning("atualização falhou: %s (%s)", mensagem, detalhe)
        try:
            arquivo.unlink(missing_ok=True)
        except OSError as impedimento:
            _log.warning("não deu para apagar %s: %s", arquivo, impedimento)
        self._definir(EstadoAtualizacao("erro", mensagem=mensagem))


def _baixar_do_github(url: str) -> Iterator[bytes]:
    """Confere o endereço na hora, antes de abrir qualquer conexão; os pedaços vêm depois."""
    if not url.startswith(PREFIXO_DOWNLOAD):
        raise ValueError(f"endereço fora do release do projeto: {url}")
    return _pedacos_do_download(url)


def _pedacos_do_download(url: str) -> Iterator[bytes]:
    with urllib.request.urlopen(url, timeout=30) as resposta:
        # O GitHub redireciona para o servidor de arquivos dele: vale, mas só por HTTPS.
        if not resposta.geturl().startswith("https://"):
            raise ValueError("o download foi redirecionado para fora do HTTPS")
        while pedaco := resposta.read(_PEDACO):
            yield pedaco


def _abrir_separado_do_app(argumentos: Sequence[str]) -> None:
    subprocess.Popen(
        list(argumentos),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        # O PyInstaller põe _PYI_* no ambiente; assim o instalador e o app que ele reabre começam
        # limpos, como uma instância independente.
        env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
    )


def atualizador_do_app(
    atual: str, *, ativo: bool, config_dir: Path, encerrar: Callable[[], None]
) -> Atualizador:
    """O ``Atualizador`` com a rede, o processo e a thread reais."""

    def buscar_json(url: str) -> object:
        pedido = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"PainelOpcoes/{atual}",
            },
        )
        with urllib.request.urlopen(pedido, timeout=5) as resposta:
            return json.loads(resposta.read().decode("utf-8"))

    return Atualizador(
        atual,
        ativo=ativo,
        buscar_json=buscar_json,
        baixar=_baixar_do_github,
        abrir_instalador=_abrir_separado_do_app,
        encerrar=encerrar,
        pasta=Path(tempfile.gettempdir()) / "PainelOpcoes-atualizacao",
        log=config_dir / "logs" / "atualizacao.log",
        pid=os.getpid(),
    )
