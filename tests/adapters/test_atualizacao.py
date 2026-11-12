"""Atualização do app instalado: consultar o GitHub, baixar, conferir e abrir o instalador.

Nada aqui toca a rede, o GitHub, os perfis reais nem abre processo: tudo entra por funções
falsas."""

import hashlib
import http.client
import io
import logging
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Self

import pytest

from options_engine.adapters.outbound.atualizacao import (
    ATRASO_ENCERRAR_S,
    PREFIXO_DOWNLOAD,
    URL_ULTIMA_VERSAO,
    VALIDADE_S,
    Atualizador,
    EstadoAtualizacao,
    VersaoNova,
    argumentos_do_instalador,
    atualizador_do_app,
    ler_release,
    numeros,
)

ATUAL = "0.5.0"
PID = 4242
CONTEUDO = b"instalador-de-mentira-" * 50
SHA = hashlib.sha256(CONTEUDO).hexdigest()
TAMANHO = len(CONTEUDO)
PEDACOS: tuple[bytes, ...] = (CONTEUDO[:300], CONTEUDO[300:700], CONTEUDO[700:])
NOME = "PainelOpcoes-0.5.1-setup.exe"
URL_ARQUIVO = f"{PREFIXO_DOWNLOAD}v0.5.1/{NOME}"


def _asset(versao: str = "0.5.1", **campos: object) -> dict[str, object]:
    nome = f"PainelOpcoes-{versao}-setup.exe"
    base: dict[str, object] = {
        "name": nome,
        "size": TAMANHO,
        "browser_download_url": f"{PREFIXO_DOWNLOAD}v{versao}/{nome}",
        "digest": f"sha256:{SHA}",
    }
    return {**base, **campos}


def _release(versao: str = "0.5.1", **campos: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tag_name": f"v{versao}",
        "body": "- Montador simples\n- Cores suaves\n",
        "assets": [_asset(versao)],
    }
    return {**base, **campos}


def _arquivos(pasta: Path) -> list[str]:
    return sorted(p.name for p in pasta.iterdir()) if pasta.exists() else []


def _avisos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


class _Falsos:
    """Os pontos de contato do ``Atualizador`` (rede, processo, thread, relógio) trocados por
    registros. Por padrão a thread roda na hora; com ``deferir`` só guarda a função."""

    def __init__(
        self,
        tmp_path: Path,
        release: object = None,
        *,
        ativo: bool = True,
        deferir: bool = False,
    ) -> None:
        self.pasta = tmp_path / "temporaria"
        self.log = tmp_path / "logs" / "atualizacao.log"
        self.release: object = _release() if release is None else release
        self.agora = 100.0
        self.consultas = 0
        self.falha_na_consulta: Exception | None = None
        self.download: list[bytes | Exception] = list(PEDACOS)
        self.urls: list[str] = []
        self.estados: list[EstadoAtualizacao] = []
        self.falha_ao_abrir: OSError | None = None
        self.abertos: list[list[str]] = []
        self.encerramentos = 0
        self.eventos: list[str] = []
        self.tarefas: list[Callable[[], None]] = []
        self._deferir = deferir
        self.atualizador = Atualizador(
            ATUAL,
            ativo=ativo,
            buscar_json=self._buscar_json,
            baixar=self._baixar,
            abrir_instalador=self._abrir_instalador,
            encerrar=self._encerrar,
            pasta=self.pasta,
            log=self.log,
            pid=PID,
            relogio=lambda: self.agora,
            esperar=self._esperar,
            em_segundo_plano=self._em_segundo_plano,
        )

    def _buscar_json(self, url: str) -> object:
        assert url == URL_ULTIMA_VERSAO
        self.consultas += 1
        if self.falha_na_consulta is not None:
            raise self.falha_na_consulta
        return self.release

    def _baixar(self, url: str) -> Iterator[bytes]:
        self.urls.append(url)
        return self._pedacos()

    def _pedacos(self) -> Iterator[bytes]:
        for item in self.download:
            if isinstance(item, Exception):
                raise item
            yield item
            # Só volta aqui quando o Atualizador já gravou o pedaço e contou.
            self.estados.append(self.atualizador.estado())

    def _abrir_instalador(self, argumentos: Sequence[str]) -> None:
        if self.falha_ao_abrir is not None:
            raise self.falha_ao_abrir
        self.eventos.append("abrir")
        self.abertos.append(list(argumentos))

    def _esperar(self, segundos: float) -> None:
        self.eventos.append(f"esperar {segundos}")

    def _encerrar(self) -> None:
        self.eventos.append("encerrar")
        self.encerramentos += 1

    def _em_segundo_plano(self, tarefa: Callable[[], None]) -> None:
        if self._deferir:
            self.tarefas.append(tarefa)
        else:
            tarefa()


# --------------------------------------------------------------------------- a versão


def test_versao_mais_nova_vira_aviso_com_as_novidades() -> None:
    assert ler_release(_release(), "0.5.0") == VersaoNova(
        "0.5.1", ("Montador simples", "Cores suaves"), TAMANHO, URL_ARQUIVO, SHA
    )


def test_versao_igual_ou_mais_velha_nao_avisa() -> None:
    assert ler_release(_release(), "0.5.1") is None
    assert ler_release(_release(), "0.6.0") is None


def test_comparacao_e_numero_a_numero() -> None:
    assert ler_release(_release("0.5.10"), "0.5.9") is not None
    assert ler_release(_release("0.5.0"), "0.5.0.dev0") is None


def test_numeros_pega_os_tres_primeiros() -> None:
    assert numeros("0.5.0.dev0") == (0, 5, 0)
    assert numeros("0.5.10") == (0, 5, 10)
    assert numeros("1.2") is None
    assert numeros("abc") is None
    assert numeros("") is None


def test_versao_atual_ilegivel_nao_avisa(caplog: pytest.LogCaptureFixture) -> None:
    assert ler_release(_release(), "desconhecida") is None
    assert len(_avisos(caplog)) == 1


@pytest.mark.parametrize("atual", ["0.5.1", "0.6.0"])
def test_versao_igual_ou_mais_velha_nao_registra_nada(
    atual: str, caplog: pytest.LogCaptureFixture
) -> None:
    assert ler_release(_release(), atual) is None
    assert _avisos(caplog) == []


@pytest.mark.parametrize(
    ("corpo", "avisa"),
    [
        pytest.param(_release(tag_name="v0.5.1-rc1"), False, id="tag-de-pre-lancamento"),
        pytest.param(_release(tag_name="0.5.1"), False, id="tag-sem-v"),
        pytest.param(_release(body=None), True, id="sem-notas"),
        pytest.param(_release(assets=[]), False, id="sem-arquivos"),
        pytest.param(_release(assets=["x"]), False, id="arquivo-que-nao-e-objeto"),
        pytest.param(_release(assets=None), False, id="arquivos-ausentes"),
        pytest.param(_release(assets=[_asset(name="outro.exe")]), False, id="outro-nome"),
        pytest.param(
            _release(assets=[_asset(browser_download_url=f"https://exemplo.com/{NOME}")]),
            False,
            id="outro-host",
        ),
        pytest.param(
            _release(assets=[_asset(browser_download_url=f"http://github.com/{NOME}")]),
            False,
            id="sem-https",
        ),
        pytest.param(_release(assets=[_asset(size=0)]), False, id="tamanho-zero"),
        pytest.param(_release(assets=[_asset(size="31")]), False, id="tamanho-que-nao-e-numero"),
        pytest.param(_release(assets=[_asset(digest="sha1:abc")]), False, id="digest-estranho"),
        pytest.param(["nao", "e", "dict"], False, id="corpo-que-nao-e-objeto"),
        pytest.param(None, False, id="corpo-nulo"),
    ],
)
def test_release_estranho_nao_avisa(
    corpo: object, avisa: bool, caplog: pytest.LogCaptureFixture
) -> None:
    nova = ler_release(corpo, ATUAL)
    assert (nova is not None) is avisa
    if nova is not None:
        assert nova.novidades == ()
    # Resposta fora do formato deixa uma linha no log; release bom (mesmo sem notas) não.
    assert len(_avisos(caplog)) == (0 if avisa else 1)


def test_novidades_tiram_o_marcador_e_as_linhas_vazias() -> None:
    corpo = _release(body="- Um\r\n\r\n* Dois\n  - Três  \n")
    nova = ler_release(corpo, ATUAL)
    assert nova is not None
    assert nova.novidades == ("Um", "Dois", "Três")


def test_digest_em_maiusculas_vira_hex_minusculo() -> None:
    nova = ler_release(_release(assets=[_asset(digest=f"sha256:{SHA.upper()}")]), ATUAL)
    assert nova is not None
    assert nova.sha256 == SHA


def test_sem_digest_o_release_vale_e_a_conferencia_cai_para_o_tamanho() -> None:
    nulo = ler_release(_release(assets=[_asset(digest=None)]), ATUAL)
    ausente = _asset()
    del ausente["digest"]
    sem_campo = ler_release(_release(assets=[ausente]), ATUAL)
    assert nulo is not None
    assert nulo.sha256 is None
    assert sem_campo is not None
    assert sem_campo.sha256 is None


def test_sem_digest_confere_pelo_tamanho(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path, _release(assets=[_asset(digest=None)]))
    nova = falsos.atualizador.conferir()
    assert nova is not None
    assert nova.sha256 is None
    falsos.atualizador.iniciar()
    assert falsos.atualizador.estado().fase == "instalando"
    assert len(falsos.abertos) == 1
    assert falsos.encerramentos == 1


def test_sem_digest_e_tamanho_errado_nao_confere(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path, _release(assets=[_asset(digest=None)]))
    falsos.download = [CONTEUDO[:-1]]
    estado = falsos.atualizador.iniciar()
    assert estado == EstadoAtualizacao("erro", 0, 0, "o arquivo baixado não confere")
    assert _arquivos(falsos.pasta) == []
    assert falsos.abertos == []


# --------------------------------------------------------------------------- a consulta


def test_estado_inicial_e_parado(tmp_path: Path) -> None:
    assert _Falsos(tmp_path).atualizador.estado() == EstadoAtualizacao("parado")


def test_fora_do_app_instalado_nao_consulta_a_rede(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path, ativo=False)
    assert falsos.atualizador.conferir() is None
    assert falsos.consultas == 0
    assert falsos.atualizador.iniciar().fase == "erro"
    assert falsos.consultas == 0


def test_falha_na_consulta_vira_none_e_fica_guardada(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path)
    falsos.falha_na_consulta = urllib.error.URLError("sem internet")
    assert falsos.atualizador.conferir() is None
    falsos.agora += VALIDADE_S - 1
    assert falsos.atualizador.conferir() is None
    assert falsos.consultas == 1
    falsos.agora += 2
    assert falsos.atualizador.conferir() is None
    assert falsos.consultas == 2


def test_falha_qualquer_na_consulta_tambem_vira_none(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path)
    falsos.falha_na_consulta = ValueError("JSON ilegível")
    assert falsos.atualizador.conferir() is None


def test_falha_na_consulta_deixa_uma_linha_no_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    falsos = _Falsos(tmp_path)
    falsos.falha_na_consulta = urllib.error.URLError("sem internet")
    falsos.atualizador.conferir()
    falsos.atualizador.conferir()  # guardada: não consulta nem registra de novo
    (aviso,) = _avisos(caplog)
    assert "sem internet" in aviso


def test_resposta_fora_do_formato_deixa_uma_linha_no_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Release criado antes de o arquivo subir: ficaria 30 min sem aviso e sem explicação.
    falsos = _Falsos(tmp_path, _release(assets=[]))
    assert falsos.atualizador.conferir() is None
    assert falsos.atualizador.conferir() is None
    (aviso,) = _avisos(caplog)
    assert NOME in aviso


def test_sem_versao_nova_nao_deixa_aviso_no_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    falsos = _Falsos(tmp_path, _release("0.5.0"))
    assert falsos.atualizador.conferir() is None
    assert _avisos(caplog) == []


def test_consulta_com_sucesso_fica_guardada_30_min(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path)
    primeira = falsos.atualizador.conferir()
    assert primeira is not None
    assert primeira.versao == "0.5.1"
    falsos.release = _release("0.5.2")
    falsos.agora += VALIDADE_S - 1
    assert falsos.atualizador.conferir() == primeira
    assert falsos.consultas == 1
    falsos.agora += 2
    depois = falsos.atualizador.conferir()
    assert depois is not None
    assert depois.versao == "0.5.2"
    assert falsos.consultas == 2


def test_resposta_que_nao_e_release_tambem_fica_guardada(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path, {"message": "API rate limit exceeded"})
    assert falsos.atualizador.conferir() is None
    assert falsos.atualizador.conferir() is None
    assert falsos.consultas == 1


# --------------------------------------------------------------------------- atualizar


def test_atualizar_baixa_confere_abre_o_instalador_e_encerra(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path)
    falsos.atualizador.iniciar()
    assert falsos.urls == [URL_ARQUIVO]
    assert [e.baixado for e in falsos.estados] == [300, 700, TAMANHO]
    assert all(e.fase == "baixando" and e.total == TAMANHO for e in falsos.estados)
    arquivo = falsos.pasta / NOME
    assert arquivo.read_bytes() == CONTEUDO
    assert falsos.abertos == [
        [
            str(arquivo),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/RELANCAR=1",
            f"/ESPERAR={PID}",
            f"/LOG={falsos.log}",
        ]
    ]
    assert falsos.eventos == ["abrir", f"esperar {ATRASO_ENCERRAR_S}", "encerrar"]
    assert ATRASO_ENCERRAR_S == 2.0
    assert falsos.atualizador.estado() == EstadoAtualizacao("instalando", TAMANHO, TAMANHO)


def test_argumentos_do_instalador() -> None:
    assert argumentos_do_instalador(Path("/t/a.exe"), 7, Path("/l/atualizacao.log")) == [
        str(Path("/t/a.exe")),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/RELANCAR=1",
        "/ESPERAR=7",
        f"/LOG={Path('/l/atualizacao.log')}",
    ]


def test_dois_pedidos_abrem_um_download_so(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path, deferir=True)
    primeiro = falsos.atualizador.iniciar()
    assert primeiro == EstadoAtualizacao("baixando", 0, TAMANHO)
    assert falsos.atualizador.iniciar().fase == "baixando"
    assert len(falsos.tarefas) == 1
    falsos.tarefas[0]()
    assert falsos.atualizador.estado().fase == "instalando"
    # Já instalando: um pedido a mais também não começa outro download.
    assert falsos.atualizador.iniciar().fase == "instalando"
    assert len(falsos.tarefas) == 1
    assert falsos.urls == [URL_ARQUIVO]


def test_arquivo_que_nao_confere_e_apagado_e_vira_erro(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path, _release(assets=[_asset(digest=f"sha256:{'0' * 64}")]))
    estado = falsos.atualizador.iniciar()
    assert estado.fase == "erro"
    assert estado.mensagem == "o arquivo baixado não confere"
    assert _arquivos(falsos.pasta) == []
    assert falsos.abertos == []
    assert falsos.encerramentos == 0


@pytest.mark.parametrize(
    "falha",
    [
        OSError("caiu"),
        urllib.error.URLError("sem rede"),
        http.client.IncompleteRead(b"x"),
        ValueError("fora do prefixo"),
    ],
    ids=["oserror", "urlerror", "incompleteread", "valueerror"],
)
def test_conexao_que_cai_no_meio_apaga_o_parcial_e_tentar_de_novo_funciona(
    tmp_path: Path, falha: Exception
) -> None:
    falsos = _Falsos(tmp_path)
    falsos.download = [PEDACOS[0], falha]
    estado = falsos.atualizador.iniciar()
    assert estado.fase == "erro"
    assert estado.mensagem == "a conexão com o GitHub falhou"
    assert _arquivos(falsos.pasta) == []
    assert falsos.encerramentos == 0

    falsos.download = list(PEDACOS)
    falsos.estados.clear()
    falsos.atualizador.iniciar()
    assert falsos.estados[0].baixado == 300  # recomeçou do zero, não do parcial
    assert falsos.atualizador.estado() == EstadoAtualizacao("instalando", TAMANHO, TAMANHO)
    assert (falsos.pasta / NOME).read_bytes() == CONTEUDO


def test_valueerror_na_chamada_do_baixar_tambem_vira_erro(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path)

    def recusa(url: str) -> Iterator[bytes]:
        raise ValueError("fora do prefixo")

    falsos.atualizador._baixar = recusa
    estado = falsos.atualizador.iniciar()
    assert estado.fase == "erro"
    assert estado.mensagem == "a conexão com o GitHub falhou"


def test_instalador_que_nao_abre_vira_erro_e_o_servidor_fica(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path)
    falsos.falha_ao_abrir = OSError("recusado")
    estado = falsos.atualizador.iniciar()
    assert estado.fase == "erro"
    assert estado.mensagem == "não deu para abrir o instalador"
    assert falsos.encerramentos == 0
    assert falsos.eventos == []
    assert _arquivos(falsos.pasta) == []


def test_excecao_fora_da_lista_vira_erro_e_tentar_de_novo_funciona(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    falsos = _Falsos(tmp_path)
    falsos.download = [PEDACOS[0], RuntimeError("bug")]
    estado = falsos.atualizador.iniciar()
    assert estado.fase == "erro"
    assert estado.mensagem == "erro inesperado na atualização"
    assert _arquivos(falsos.pasta) == []
    assert falsos.abertos == []
    assert falsos.encerramentos == 0
    # Sem engolir em silêncio: o erro vai para o log com a pilha.
    (registro,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert registro.exc_info is not None
    assert isinstance(registro.exc_info[1], RuntimeError)

    falsos.download = list(PEDACOS)
    falsos.atualizador.iniciar()
    assert falsos.atualizador.estado() == EstadoAtualizacao("instalando", TAMANHO, TAMANHO)
    assert falsos.encerramentos == 1


def test_thread_que_nao_sobe_vira_erro_em_vez_de_ficar_baixando(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    falsos = _Falsos(tmp_path)

    def recusa(tarefa: Callable[[], None]) -> None:
        raise RuntimeError("não deu para criar a thread")

    falsos.atualizador._em_segundo_plano = recusa
    estado = falsos.atualizador.iniciar()
    assert estado == EstadoAtualizacao("erro", 0, 0, "erro inesperado na atualização")
    assert falsos.atualizador.estado() == estado
    assert falsos.urls == []
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_sem_versao_nova_iniciar_vira_erro(tmp_path: Path) -> None:
    falsos = _Falsos(tmp_path, _release("0.5.0"))
    estado = falsos.atualizador.iniciar()
    assert estado == EstadoAtualizacao("erro", 0, 0, "não há versão nova para baixar")
    assert falsos.urls == []
    assert falsos.tarefas == []


# --------------------------------------------------------------------------- as funções reais


def _sem_rede(*args: object, **kwargs: object) -> object:
    raise AssertionError("não deveria abrir conexão")


def _real(tmp_path: Path) -> Atualizador:
    return atualizador_do_app(ATUAL, ativo=True, config_dir=tmp_path, encerrar=lambda: None)


class _Resposta:
    def __init__(self, corpo: bytes, url: str = "https://objects.githubusercontent.com/x") -> None:
        self._corpo = io.BytesIO(corpo)
        self._url = url

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, quantos: int = -1) -> bytes:
        return self._corpo.read(quantos)

    def geturl(self) -> str:
        return self._url


def _urlopen_falso(
    monkeypatch: pytest.MonkeyPatch, resposta: _Resposta
) -> list[tuple[object, float | None]]:
    chamadas: list[tuple[object, float | None]] = []

    def urlopen(alvo: object, *, timeout: float | None = None) -> _Resposta:
        chamadas.append((alvo, timeout))
        return resposta

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return chamadas


def test_download_fora_do_prefixo_e_recusado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _sem_rede)
    baixar = _real(tmp_path)._baixar
    with pytest.raises(ValueError):
        baixar("https://exemplo.com/x.exe")
    with pytest.raises(ValueError):
        baixar(URL_ARQUIVO.replace("https://", "http://"))


def test_download_real_recusa_redirecionamento_para_fora_do_https(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _urlopen_falso(monkeypatch, _Resposta(CONTEUDO, "http://objects.githubusercontent.com/x"))
    with pytest.raises(ValueError):
        list(_real(tmp_path)._baixar(URL_ARQUIVO))


def test_download_real_entrega_pedacos_de_64_kib_com_limite_de_30_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpo = b"x" * (64 * 1024 * 2 + 10)
    chamadas = _urlopen_falso(monkeypatch, _Resposta(corpo))
    pedacos = list(_real(tmp_path)._baixar(URL_ARQUIVO))
    assert [len(p) for p in pedacos] == [65536, 65536, 10]
    assert b"".join(pedacos) == corpo
    assert chamadas == [(URL_ARQUIVO, 30)]


def test_consulta_real_manda_os_cabecalhos_do_github_com_limite_de_5_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas = _urlopen_falso(monkeypatch, _Resposta(b'{"tag_name": "v0.5.1"}'))
    assert _real(tmp_path)._buscar_json(URL_ULTIMA_VERSAO) == {"tag_name": "v0.5.1"}
    ((pedido, limite),) = chamadas
    assert isinstance(pedido, urllib.request.Request)
    assert pedido.full_url == URL_ULTIMA_VERSAO
    assert pedido.get_header("Accept") == "application/vnd.github+json"
    assert pedido.get_header("User-agent") == f"PainelOpcoes/{ATUAL}"
    assert limite == 5


def test_instalador_real_abre_separado_do_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abertos: list[tuple[list[str], dict[str, object]]] = []

    class PopenFalso:
        def __init__(self, argumentos: list[str], **kwargs: object) -> None:
            abertos.append((argumentos, kwargs))

    monkeypatch.setattr(subprocess, "Popen", PopenFalso)
    monkeypatch.setenv("VARIAVEL_DO_USUARIO", "fica")
    _real(tmp_path)._abrir_instalador(["setup.exe", "/VERYSILENT"])
    ((argumentos, kwargs),) = abertos
    assert argumentos == ["setup.exe", "/VERYSILENT"]
    # O PyInstaller põe _PYI_* no ambiente: sem isto o instalador, e o app que ele reabre,
    # herdariam o do app que está fechando.
    assert kwargs["env"] == {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["close_fds"] is True
    assert kwargs["creationflags"] == (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )


def test_atualizador_do_app_usa_a_pasta_de_logs_e_a_temporaria(tmp_path: Path) -> None:
    atualizador = atualizador_do_app(
        "0.5.0.dev0", ativo=False, config_dir=tmp_path, encerrar=lambda: None
    )
    assert atualizador.atual == "0.5.0.dev0"
    assert atualizador.log == tmp_path / "logs" / "atualizacao.log"
    assert atualizador.pasta == Path(tempfile.gettempdir()) / "PainelOpcoes-atualizacao"
    assert atualizador._pid == os.getpid()
