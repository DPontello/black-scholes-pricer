"""CLI da ponte — argumentos, despacho e ``espiar`` contra um ``ServidorTcp`` com sessão falsa."""

import io
import logging
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from options_ponte import __main__ as cli
from options_ponte import rtd, servidor, tryd7
from options_ponte.protocolo import (
    Assinar,
    Encerrar,
    ErroDeProtocolo,
    Mensagem,
    Ping,
    Pong,
    Status,
    Valor,
    codificar,
    decodificar,
    topico_rtd,
)
from options_ponte.servidor import Ponte, ServidorTcp
from options_ponte.vias import CLSID_TRYD7, Visao
from tests.ponte.registro_falso import RegistroFalso

AGORA = "2026-10-28T12:03:00-03:00"
IDENTIDADE = "StRtd, Version=1.13.0.0, Culture=neutral, PublicKeyToken=cad2126db594d9d0"
VISOES: tuple[Visao, ...] = (64, 32)


class SessaoMinima:
    """``SessaoRtd`` em memória: devolve o valor inicial configurado e guarda as chamadas."""

    def __init__(self) -> None:
        self.valores: dict[tuple[str, ...], object] = {}
        self.conectados: list[tuple[int, tuple[str, ...]]] = []
        self.desconectados: list[int] = []

    def topico(self, ticker: str, campo: str) -> tuple[str, ...]:
        return topico_rtd(ticker, campo)

    def conectar(self, id_: int, strings: tuple[str, ...]) -> object:
        self.conectados.append((id_, strings))
        return self.valores.get(strings, 0.0)

    def desconectar(self, id_: int) -> None:
        self.desconectados.append(id_)

    def atualizar(self) -> list[tuple[int, object]]:
        return []

    def vivo(self) -> bool:
        return True

    def avisos(self) -> int:
        return 0

    def encerrar(self) -> None:
        pass


class PonteNoAr:
    """Ponte + ``ServidorTcp`` numa thread própria; o relógio anda 1 s por volta (status rápido)."""

    def __init__(self) -> None:
        self.sessao = SessaoMinima()
        self._segundos = 0.0
        ponte = Ponte(lambda: self.sessao, self._relogio, lambda: AGORA, limite=20)
        self.servidor = ServidorTcp(ponte, 0, lambda _passo: time.sleep(0.002))
        self.parar = threading.Event()
        self.thread = threading.Thread(target=self.servidor.rodar, args=(self.parar,), daemon=True)

    def _relogio(self) -> float:
        self._segundos += 1.0
        return self._segundos

    @property
    def porta(self) -> int:
        return self.servidor.endereco[1]


@pytest.fixture
def no_ar() -> Iterator[PonteNoAr]:
    ponte = PonteNoAr()
    ponte.thread.start()
    yield ponte
    ponte.parar.set()
    ponte.thread.join(timeout=5)
    assert not ponte.thread.is_alive(), "rodar não voltou"


def _porta_sem_ninguem() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# --------------------------------------------------------------------------- argumentos


def test_servir_tem_porta_e_limite_padrao_da_ponte() -> None:
    args = cli.montar_parser().parse_args(["servir"])
    assert (args.comando, args.porta, args.limite) == ("servir", 8766, 600)


def test_servir_aceita_porta_e_limite() -> None:
    args = cli.montar_parser().parse_args(["servir", "--porta", "9000", "--limite", "50"])
    assert (args.porta, args.limite) == (9000, 50)


def test_servir_tem_o_log_opcional() -> None:
    parser = cli.montar_parser()
    assert parser.parse_args(["servir"]).log is None
    assert parser.parse_args(["servir", "--log", "L/ponte.log"]).log == Path("L/ponte.log")


def test_espiar_normaliza_ativos_e_usa_campos_e_tempo_padrao() -> None:
    args = cli.montar_parser().parse_args(["espiar", "--ativos", " petr4, VALE3 ,petr4,"])
    assert args.comando == "espiar"
    assert args.ativos == ("PETR4", "VALE3")
    assert args.campos == ("ULT", "OCP", "OVD", "NEG", "VOL", "FEC", "HOR", "DAT")
    assert (args.porta, args.segundos) == (8766, 10.0)


def test_espiar_aceita_campos_e_segundos() -> None:
    args = cli.montar_parser().parse_args(
        ["espiar", "--ativos", "PETRK500", "--campos", "ult,ocp", "--segundos", "2.5"]
    )
    assert (args.campos, args.segundos) == (("ULT", "OCP"), 2.5)


@pytest.mark.parametrize(
    "argv",
    [
        [],  # falta o subcomando
        ["servir", "--porta", "0"],
        ["servir", "--porta", "65536"],
        ["servir", "--porta", "abc"],
        ["servir", "--limite", "0"],
        ["espiar"],  # falta --ativos
        ["espiar", "--ativos", ",,"],
        ["espiar", "--ativos", "PETR4", "--segundos", "0"],
        ["espiar", "--ativos", "PETR4", "--segundos", "-1"],
        ["espiar", "--ativos", "PETR4", "--segundos", "nan"],
        ["espiar", "--ativos", "PETR4", "--segundos", "inf"],
        ["espiar", "--ativos", "PETR4", "--campos", ","],
        ["registrar", "--pasta"],  # falta o valor
        ["desregistrar", "--pasta", "C:\\Tryd"],  # o desregistrar não tem opções
        ["desconhecido"],
    ],
)
def test_argumentos_invalidos_saem_com_erro_de_uso(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as saida:
        cli.montar_parser().parse_args(argv)
    assert saida.value.code == 2
    assert capsys.readouterr().err  # explica o erro


def test_diagnostico_autoteste_e_servidor_falso_nao_pedem_argumentos() -> None:
    parser = cli.montar_parser()
    assert parser.parse_args(["diagnostico"]).comando == "diagnostico"
    assert parser.parse_args(["autoteste"]).comando == "autoteste"
    assert parser.parse_args(["servidor-falso", "--segundos", "3"]).segundos == 3.0


def test_registrar_e_desregistrar_tem_a_pasta_so_no_registrar() -> None:
    parser = cli.montar_parser()
    assert parser.parse_args(["registrar"]).pasta is None
    assert parser.parse_args(["registrar", "--pasta", "C:\\Tryd"]).pasta == Path("C:\\Tryd")
    assert parser.parse_args(["desregistrar"]).comando == "desregistrar"


# --------------------------------------------------------------------------- despacho


def test_main_despacha_diagnostico_e_autoteste_e_devolve_o_codigo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rtd, "diagnostico", lambda: 7)
    monkeypatch.setattr(rtd, "autoteste", lambda: 3)
    assert cli.main(["diagnostico"]) == 7
    assert cli.main(["autoteste"]) == 3


def test_main_despacha_servidor_falso_com_os_segundos(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos: list[float] = []

    def servir_falso(segundos: float) -> int:
        pedidos.append(segundos)
        return 0

    monkeypatch.setattr(rtd, "servir_falso", servir_falso)
    assert cli.main(["servidor-falso", "--segundos", "4"]) == 0
    assert pedidos == [4.0]


def test_servir_com_a_porta_ocupada_falha_antes_de_tocar_no_servidor_rtd(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def nao_deveria_tocar() -> object:
        pytest.fail("o pywin32 não pode ser tocado se a porta já está ocupada")

    monkeypatch.setattr(rtd, "carregar_tipos", nao_deveria_tocar)
    monkeypatch.setattr(rtd, "SessaoRtdCom", nao_deveria_tocar)
    with socket.create_server(("127.0.0.1", 0)) as ocupada:
        porta = int(ocupada.getsockname()[1])
        assert cli.main(["servir", "--porta", str(porta)]) == 1
    assert f"127.0.0.1:{porta}" in capsys.readouterr().err


class ServirComTrydFalso:
    """``servir`` de verdade numa thread, com pywin32, COM e processos do Tryd falsos."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        pids_tryd: frozenset[int],
        *,
        log: Path | None = None,
        erro_nos_tipos: rtd.ErroRtd | None = None,
    ) -> None:
        """Com ``erro_nos_tipos``, a ``SessaoRtdCom`` é a de verdade: ela falha ao carregar os
        tipos, como no PC sem a type library."""
        self.sessoes: list[SessaoMinima] = []
        self.codigo: list[int] = []
        self.porta = _porta_sem_ninguem()
        self._argumentos = ["servir", "--porta", str(self.porta)]
        if log is not None:
            self._argumentos += ["--log", str(log)]
        if erro_nos_tipos is None:
            monkeypatch.setattr(rtd, "carregar_tipos", lambda: None)
            monkeypatch.setattr(rtd, "SessaoRtdCom", self._abrir)
        else:

            def sem_tipos() -> object:
                raise erro_nos_tipos

            monkeypatch.setattr(rtd, "carregar_tipos", sem_tipos)
        monkeypatch.setattr(rtd, "processos_tryd", lambda: pids_tryd)
        monkeypatch.setattr(rtd, "bombear", lambda _passo: time.sleep(0.002))
        self.thread = threading.Thread(target=self._servir, daemon=True)
        self.thread.start()

    def _servir(self) -> None:
        self.codigo.append(cli.main(self._argumentos))

    def _abrir(self) -> SessaoMinima:
        sessao = SessaoMinima()
        self.sessoes.append(sessao)
        return sessao

    def conectar(self) -> socket.socket:
        """Conexão que a ponte já atendeu (Ping/Pong)."""
        limite = time.monotonic() + 3
        while True:
            try:
                conexao = socket.create_connection(("127.0.0.1", self.porta), timeout=5)
            except OSError:
                conexao = None
            if conexao is not None:
                try:
                    conexao.sendall(codificar(Ping()))
                    _receber_ate(conexao, Pong)
                    return conexao
                except (OSError, ErroDeProtocolo):  # era a checagem da porta, que já fechou
                    conexao.close()
            assert time.monotonic() < limite, "servir não atendeu"
            time.sleep(0.01)

    def encerrar(self, conexao: socket.socket) -> None:
        with conexao:
            conexao.sendall(codificar(Encerrar()))
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), "servir não voltou"


def _receber_ate[T: Mensagem](conexao: socket.socket, tipo: type[T]) -> T:
    resto = b""
    while True:
        dados = conexao.recv(65536)
        if not dados:
            raise ErroDeProtocolo("a ponte fechou a conexão")
        *linhas, resto = (resto + dados).split(b"\n")
        for linha in linhas:
            mensagem = decodificar(linha)
            if isinstance(mensagem, tipo):
                return mensagem


def test_servir_com_o_tryd_fechado_atende_sem_criar_a_sessao_rtd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servir = ServirComTrydFalso(monkeypatch, frozenset())
    conexao = servir.conectar()
    conexao.sendall(codificar(Assinar((("PETR4", "ULT"),))) + codificar(Ping()))
    _receber_ate(conexao, Pong)
    servir.encerrar(conexao)
    assert servir.codigo == [0]
    assert servir.sessoes == []  # com o Tryd fechado, criar a sessão abriria o Tryd


def test_servir_com_o_tryd_aberto_abre_a_sessao_pelo_sessao_rtd_com(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servir = ServirComTrydFalso(monkeypatch, frozenset({4242}))
    conexao = servir.conectar()
    conexao.sendall(codificar(Assinar((("PETR4", "ULT"),))))
    valor = _receber_ate(conexao, Valor)
    servir.encerrar(conexao)
    assert (valor.ticker, valor.campo, valor.inicial) == ("PETR4", "ULT", True)
    assert [s.conectados for s in servir.sessoes] == [[(1, ("PETR4_B_0", "ULT"))]]


def test_servir_sem_type_library_fica_no_ar_e_reporta_perdido(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Sem a type library (ou o pywin32) a ponte não sai: o motivo vai no ``Status``.

    A ``Ponte`` só marca ``perdido`` com a sessão já aberta; antes disso, uma sessão que não abre
    é ``iniciando`` com o motivo, e o app trata os dois como "sem dado".
    """
    monkeypatch.setattr(servidor, "INTERVALO_STATUS_S", 0.05)
    erro = rtd.ErroRtd("nenhuma type library com IRtdServer/IRTDUpdateEvent carregou (RTDTrading)")
    with caplog.at_level(logging.WARNING):
        servir = ServirComTrydFalso(monkeypatch, frozenset({4242}), erro_nos_tipos=erro)
        conexao = servir.conectar()
        conexao.sendall(codificar(Assinar((("PETR4", "ULT"),))))
        status = _receber_ate(conexao, Status)
        servir.encerrar(conexao)
    assert servir.codigo == [0]
    assert status.tryd == "iniciando"
    assert str(erro) in (status.motivo or "")
    assert any(str(erro) in registro.getMessage() for registro in caplog.records)  # no log também


def test_servir_com_log_grava_o_ouvindo_no_arquivo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "logs" / "ponte.log"  # a pasta ainda não existe
    raiz = logging.getLogger()
    handlers_antes, nivel_antes = list(raiz.handlers), raiz.level
    servir = ServirComTrydFalso(monkeypatch, frozenset(), log=log)
    servir.encerrar(servir.conectar())
    assert servir.codigo == [0]
    assert f"ponte ouvindo em 127.0.0.1:{servir.porta} (limite de 600 tópicos)" in log.read_text(
        encoding="utf-8"
    )
    # o arquivo não fica preso ao logging depois do servir (nem o nível que ele pôs)
    assert raiz.handlers == handlers_antes
    assert raiz.level == nivel_antes


def test_servir_com_log_trunca_o_arquivo_da_execucao_anterior(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "ponte.log"
    log.write_text("linha da execução anterior\n", encoding="utf-8")
    servir = ServirComTrydFalso(monkeypatch, frozenset(), log=log)
    servir.encerrar(servir.conectar())
    texto = log.read_text(encoding="utf-8")
    assert "execução anterior" not in texto
    assert "ponte ouvindo" in texto


def test_servir_com_log_que_nao_abre_segue_no_ar_e_avisa(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    arquivo = tmp_path / "arquivo"
    arquivo.write_text("não é uma pasta", encoding="utf-8")
    log = arquivo / "ponte.log"  # a pasta-pai não dá para criar
    servir = ServirComTrydFalso(monkeypatch, frozenset(), log=log)
    servir.encerrar(servir.conectar())
    assert servir.codigo == [0]
    assert f"aviso: não foi possível gravar o log em {log}" in capsys.readouterr().err


def test_gravando_log_so_poe_o_info_no_arquivo_e_respeita_o_nivel_do_root(
    tmp_path: Path,
) -> None:
    log = tmp_path / "ponte.log"
    raiz = logging.getLogger()
    nivel_antes = raiz.level
    raiz.setLevel(logging.DEBUG)  # o root já deixa passar o INFO: não há o que mudar
    try:
        with cli._gravando_log(log):
            assert raiz.level == logging.DEBUG
            logging.getLogger("teste").debug("detalhe fino")
            logging.getLogger("teste").info("fato relevante")
        texto = log.read_text(encoding="utf-8")
        assert "fato relevante" in texto
        assert "detalhe fino" not in texto
        assert raiz.level == logging.DEBUG
    finally:
        raiz.setLevel(nivel_antes)


def test_gravando_log_sem_arquivo_nao_mexe_no_logging() -> None:
    raiz = logging.getLogger()
    handlers_antes, nivel_antes = list(raiz.handlers), raiz.level
    with cli._gravando_log(None):
        assert (raiz.handlers, raiz.level) == (handlers_antes, nivel_antes)


def _servidor_que_levanta(
    erro: Exception,
) -> Callable[[Ponte, int, Callable[[float], None]], object]:
    """Um ``ServidorTcp`` cujo ``rodar`` levanta ``erro``: o que escapa do laço da ponte."""

    class Servidor:
        endereco = ("127.0.0.1", 8766)

        def rodar(self, _parar: threading.Event) -> None:
            raise erro

    return lambda _ponte, _porta, _bombear: Servidor()


@pytest.mark.parametrize(
    "erro",
    [rtd.ErroRtd("módulo 'pythoncom' indisponível"), RuntimeError("bug no ciclo da ponte")],
    ids=["ErroRtd", "RuntimeError"],
)
def test_servir_que_cai_deixa_o_erro_e_o_traceback_no_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, erro: Exception
) -> None:
    """O erro sobe para o ``main``, que o imprime no stderr; o do app instalado vai para
    DEVNULL, então só o arquivo guarda o rastro do crash."""
    log = tmp_path / "logs" / "ponte.log"
    monkeypatch.setattr(rtd, "carregar_tipos", lambda: None)
    monkeypatch.setattr(cli, "ServidorTcp", _servidor_que_levanta(erro))
    raiz = logging.getLogger()
    handlers_antes = list(raiz.handlers)
    with pytest.raises(type(erro)):
        cli.servir(_porta_sem_ninguem(), 600, log)
    texto = log.read_text(encoding="utf-8")
    assert "ERROR" in texto
    assert "a ponte caiu com um erro não tratado" in texto
    assert "Traceback (most recent call last)" in texto
    assert f"{type(erro).__name__}: {erro}" in texto
    assert raiz.handlers == handlers_antes  # o arquivo foi solto mesmo com o erro


def test_servir_com_a_porta_ocupada_deixa_o_log_existente_intacto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Uma segunda ponte que acha a porta ocupada (a viva pode estar travada) não zera nem
    escreve o ``ponte.log``: é nele que está a evidência da ponte viva. O erro vai ao stderr."""
    log = tmp_path / "ponte.log"
    log.write_text("evidência da ponte travada\n", encoding="utf-8")
    monkeypatch.setattr(rtd, "carregar_tipos", lambda: None)
    with socket.create_server(("127.0.0.1", 0)) as ocupada:
        porta = int(ocupada.getsockname()[1])
        assert cli.main(["servir", "--porta", str(porta), "--log", str(log)]) == 1
    assert log.read_text(encoding="utf-8") == "evidência da ponte travada\n"
    assert f"não foi possível ouvir em 127.0.0.1:{porta}" in capsys.readouterr().err


def test_servir_com_a_porta_tomada_depois_da_checagem_deixa_o_erro_no_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "logs" / "ponte.log"
    monkeypatch.setattr(rtd, "carregar_tipos", lambda: None)

    def tomada(_ponte: Ponte, _porta: int, _bombear: Callable[[float], None]) -> object:
        raise OSError("[Errno 98] Address already in use")

    monkeypatch.setattr(cli, "ServidorTcp", tomada)
    porta = _porta_sem_ninguem()
    assert cli.main(["servir", "--porta", str(porta), "--log", str(log)]) == 1
    texto = log.read_text(encoding="utf-8")
    assert "ERROR" in texto
    assert f"não foi possível ouvir em 127.0.0.1:{porta}: [Errno 98]" in texto


def test_servir_interrompido_avisa_e_sai_com_0(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class ServidorInterrompido:
        endereco = ("127.0.0.1", 8766)

        def __init__(self, _ponte: Ponte, _porta: int, _bombear: Callable[[float], None]) -> None:
            pass

        def rodar(self, _parar: threading.Event) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(rtd, "carregar_tipos", lambda: None)
    monkeypatch.setattr(cli, "ServidorTcp", ServidorInterrompido)
    assert cli.main(["servir", "--porta", str(_porta_sem_ninguem())]) == 0
    captura = capsys.readouterr()
    assert "ponte ouvindo em 127.0.0.1:8766" in captura.out
    assert "ponte interrompida" in captura.err


# ----------------------------------------------------------------------- a ponte sem console


class SaidaQueFalha:
    """Um stdout cuja escrita (ou o ``flush``) falha, como o de um processo sem console."""

    def __init__(self, erro: Exception, *, no_write: bool = True) -> None:
        self._erro = erro
        self._no_write = no_write

    def write(self, texto: str) -> int:
        if self._no_write:
            raise self._erro
        return len(texto)

    def flush(self) -> None:
        raise self._erro


def test_dizer_escreve_no_stdout_ou_no_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    cli._dizer("tudo certo")
    cli._dizer("deu ruim", erro=True)
    captura = capsys.readouterr()
    assert (captura.out, captura.err) == ("tudo certo\n", "deu ruim\n")


@pytest.mark.parametrize("fluxo", ["stdout", "stderr"])
def test_dizer_nao_derruba_sem_console(monkeypatch: pytest.MonkeyPatch, fluxo: str) -> None:
    erro = fluxo == "stderr"
    monkeypatch.setattr(sys, fluxo, None)  # o processo sem console
    cli._dizer("ponte ouvindo", erro=erro)
    for saida in (
        SaidaQueFalha(OSError("[Errno 9] Bad file descriptor")),  # a escrita
        SaidaQueFalha(OSError("[Errno 9] Bad file descriptor"), no_write=False),  # o flush
        SaidaQueFalha(ValueError("I/O operation on closed file")),
    ):
        monkeypatch.setattr(sys, fluxo, saida)
        cli._dizer("ponte ouvindo", erro=erro)


# --------------------------------------------------------------------------- espiar


def _decodificar_saida(saida: io.StringIO) -> list[Valor | Status]:
    mensagens = [decodificar(linha.encode()) for linha in saida.getvalue().splitlines()]
    return [m for m in mensagens if isinstance(m, Valor | Status)]


def _esperar(condicao: Callable[[], bool]) -> None:
    limite = time.monotonic() + 3
    while not condicao():
        assert time.monotonic() < limite, "condição não aconteceu em 3 s"
        time.sleep(0.01)


def test_espiar_imprime_os_valores_e_um_status_conectado(no_ar: PonteNoAr) -> None:
    no_ar.sessao.valores = {
        ("PETR4_B_0", "ULT"): 38.42,
        ("PETR4_B_0", "OCP"): 38.41,
        ("PETR4_B_0", "OVD"): 38.43,
        ("VALE3_B_0", "ULT"): 61.1,
        ("VALE3_B_0", "OCP"): 61.0,
        ("VALE3_B_0", "OVD"): 61.2,
    }
    saida = io.StringIO()
    codigo = cli.espiar(no_ar.porta, ("PETR4", "VALE3"), ("ULT", "OCP", "OVD"), 0.5, saida)
    assert codigo == 0
    mensagens = _decodificar_saida(saida)
    valores = {(m.ticker, m.campo): m.valor for m in mensagens if isinstance(m, Valor)}
    assert valores == {
        ("PETR4", "ULT"): 38.42,
        ("PETR4", "OCP"): 38.41,
        ("PETR4", "OVD"): 38.43,
        ("VALE3", "ULT"): 61.1,
        ("VALE3", "OCP"): 61.0,
        ("VALE3", "OVD"): 61.2,
    }
    status = [m for m in mensagens if isinstance(m, Status)]
    assert status
    assert status[-1].tryd == "conectado"
    assert status[-1].topicos == 6


def test_espiar_imprime_a_linha_do_jeito_que_veio_da_ponte(no_ar: PonteNoAr) -> None:
    no_ar.sessao.valores = {("PETR4_B_0", "ULT"): 38.42}
    saida = io.StringIO()
    cli.espiar(no_ar.porta, ("PETR4",), ("ULT",), 0.3, saida)
    assert (
        '{"tipo":"valor","ticker":"PETR4","campo":"ULT","tipo_valor":"float",'
        '"valor":38.42,"instante":"2026-10-28T12:03:00-03:00","inicial":true}'
    ) in saida.getvalue().splitlines()


def test_espiar_assina_os_topicos_do_rtd_e_os_deixa_assinados(no_ar: PonteNoAr) -> None:
    cli.espiar(no_ar.porta, ("PETR4", "VALE3"), ("ULT", "OCP"), 0.3, io.StringIO())
    # Ping/Pong ANTES de conferir: a fila de comandos é uma só, então o Pong garante que a
    # ponte já tratou tudo o que o espiar mandou (sob carga, 0,3 s pode não bastar).
    outro = socket.create_connection(("127.0.0.1", no_ar.porta), timeout=5)
    with outro, outro.makefile("rb") as linhas:
        outro.sendall(codificar(Ping()))
        while decodificar(linhas.readline()) != Pong():  # o status periódico pode vir antes
            pass
    assert [topico for _, topico in no_ar.sessao.conectados] == [
        ("PETR4_B_0", "ULT"),
        ("PETR4_B_0", "OCP"),
        ("VALE3_B_0", "ULT"),
        ("VALE3_B_0", "OCP"),
    ]
    assert no_ar.sessao.desconectados == []


def test_espiar_manda_so_o_assinar_e_nunca_cancelar() -> None:
    """A ponte não conta referências: um ``cancelar`` do espiar derrubaria o tópico do app."""
    escuta = socket.create_server(("127.0.0.1", 0))
    recebido: list[bytes] = []

    def gravar_ate_o_eof() -> None:
        conexao, _ = escuta.accept()
        with conexao:
            while dados := conexao.recv(65536):
                recebido.append(dados)

    thread = threading.Thread(target=gravar_ate_o_eof, daemon=True)
    thread.start()
    try:
        porta = int(escuta.getsockname()[1])
        assert cli.espiar(porta, ("PETR4", "VALE3"), ("ULT", "OCP"), 0.3, io.StringIO()) == 0
    finally:
        thread.join(timeout=5)
        escuta.close()
    mensagens = [decodificar(linha) for linha in b"".join(recebido).splitlines() if linha.strip()]
    assert mensagens == [
        Assinar(
            (("PETR4", "ULT"), ("PETR4", "OCP"), ("VALE3", "ULT"), ("VALE3", "OCP")),
        )
    ]


def test_espiar_sem_ponte_ouvindo_avisa_e_sai_com_1(capsys: pytest.CaptureFixture[str]) -> None:
    porta = _porta_sem_ninguem()
    saida = io.StringIO()
    assert cli.espiar(porta, ("PETR4",), ("ULT",), 0.3, saida) == 1
    assert saida.getvalue() == ""
    assert f"127.0.0.1:{porta}" in capsys.readouterr().err


def test_espiar_com_a_ponte_que_fecha_a_conexao_sai_com_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    escuta = socket.create_server(("127.0.0.1", 0))

    def aceitar_e_fechar() -> None:
        conexao, _ = escuta.accept()
        conexao.recv(65536)  # lê o Assinar: o fechamento chega como EOF, não como reset
        conexao.close()

    thread = threading.Thread(target=aceitar_e_fechar, daemon=True)
    thread.start()
    try:
        porta = int(escuta.getsockname()[1])
        assert cli.espiar(porta, ("PETR4",), ("ULT",), 5.0, io.StringIO()) == 1
    finally:
        thread.join(timeout=5)
        escuta.close()
    assert "fechou a conexão" in capsys.readouterr().err


def test_espiar_resume_a_contagem_no_stderr(
    no_ar: PonteNoAr, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.espiar(no_ar.porta, ("PETR4",), ("ULT",), 0.3, io.StringIO())
    assert "1 valor(es)" in capsys.readouterr().err


def test_main_espiar_escreve_no_stdout(
    no_ar: PonteNoAr, capsys: pytest.CaptureFixture[str]
) -> None:
    no_ar.sessao.valores = {("PETR4_B_0", "ULT"): 38.42}
    codigo = cli.main(
        ["espiar", "--porta", str(no_ar.porta), "--ativos", "PETR4", "--campos", "ULT",
         "--segundos", "0.3"]
    )  # fmt: skip
    assert codigo == 0
    assert '"ticker":"PETR4"' in capsys.readouterr().out


# ----------------------------------------------------------------------- registrar e desregistrar


def _nao_deveria_tocar() -> object:
    pytest.fail("o registro não pode ser tocado neste cenário")


def _tryd_instalado(pasta: Path) -> Path:
    """A pasta do Tryd com a DLL do ``StRtd`` (vazia: o PowerShell é trocado por um falso)."""
    dll = pasta / tryd7.DLL_RELATIVA
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"")
    return dll


def test_registrar_sem_pasta_avisa_e_sai_com_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tryd7, "pasta_do_tryd", lambda: None)
    monkeypatch.setattr(tryd7, "RegistroWinreg", _nao_deveria_tocar)
    assert cli.main(["registrar"]) == 2
    captura = capsys.readouterr()
    assert captura.out == ""
    assert captura.err == (
        'erro: não achei a pasta do Tryd: abra o Tryd ou passe --pasta "<pasta do tryd.exe>"\n'
    )


def test_registrar_sem_a_dll_avisa_e_sai_com_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(tryd7, "RegistroWinreg", _nao_deveria_tocar)
    assert cli.main(["registrar", "--pasta", str(tmp_path)]) == 2
    captura = capsys.readouterr()
    assert captura.out == ""
    assert captura.err == f"erro: não achei {tmp_path / tryd7.DLL_RELATIVA}\n"


def test_registrar_grava_e_manda_rodar_o_diagnostico(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    dll = _tryd_instalado(tmp_path)
    registro = RegistroFalso()
    dlls: list[Path] = []

    def identidade(arquivo: Path) -> str:
        dlls.append(arquivo)
        return IDENTIDADE

    monkeypatch.setattr(tryd7, "pasta_do_tryd", lambda: tmp_path)
    monkeypatch.setattr(tryd7, "identidade_do_assembly", identidade)
    monkeypatch.setattr(tryd7, "RegistroWinreg", lambda: registro)
    assert cli.main(["registrar"]) == 0
    linhas = capsys.readouterr().out.splitlines()
    assert dlls == [dll]
    assert linhas[-1] == "pronto: rode 'PonteTryd.exe diagnostico' para conferir"
    assert sum("CodeBase = " in linha for linha in linhas) == 4  # 2 chaves x 2 visões
    assert len(linhas) - 1 == len(tryd7.chaves_tryd7(dll, IDENTIDADE)) * 2
    for visao in VISOES:
        assert any(CLSID_TRYD7.lower() in chave for chave in registro.gravado("HKCU", visao))
        assert registro.gravado("HKLM", visao) == {}


def test_registrar_com_pasta_nao_procura_o_tryd_aberto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _tryd_instalado(tmp_path)
    registro = RegistroFalso()
    monkeypatch.setattr(tryd7, "pasta_do_tryd", _nao_deveria_tocar)
    monkeypatch.setattr(tryd7, "identidade_do_assembly", lambda _dll: IDENTIDADE)
    monkeypatch.setattr(tryd7, "RegistroWinreg", lambda: registro)
    assert cli.main(["registrar", "--pasta", str(tmp_path)]) == 0
    assert registro.gravado("HKCU", 32)


def test_registrar_com_pasta_relativa_grava_o_caminho_absoluto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O ``CodeBase`` vai para o registro: um caminho relativo não serviria a outro processo."""
    dll = _tryd_instalado(tmp_path / "Tryd")
    monkeypatch.chdir(tmp_path)
    dlls: list[Path] = []

    def identidade(arquivo: Path) -> str:
        dlls.append(arquivo)
        return IDENTIDADE

    monkeypatch.setattr(tryd7, "identidade_do_assembly", identidade)
    monkeypatch.setattr(tryd7, "RegistroWinreg", RegistroFalso)
    assert cli.main(["registrar", "--pasta", "Tryd"]) == 0
    assert dlls == [dll]


@pytest.mark.parametrize("erro", [ValueError("saída inesperada: Foo"), PermissionError("negado")])
def test_registrar_que_falha_avisa_e_sai_com_1_sem_gravar(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    erro: Exception,
) -> None:
    _tryd_instalado(tmp_path)
    registro = RegistroFalso()

    def falha(_dll: Path) -> str:
        raise erro

    monkeypatch.setattr(tryd7, "identidade_do_assembly", falha)
    monkeypatch.setattr(tryd7, "RegistroWinreg", lambda: registro)
    assert cli.main(["registrar", "--pasta", str(tmp_path)]) == 1
    captura = capsys.readouterr()
    assert captura.out == ""
    assert captura.err == f"erro: {erro}\n"
    assert registro.gravado("HKCU", 64) == {}


def test_desregistrar_despacha(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registro = RegistroFalso()
    for visao in VISOES:
        registro.definir("HKCU", "Software\\Classes\\Tryd.RtdServer", "x", visao=visao)
        registro.definir("HKCU", "Software\\Classes\\Outro", "y", visao=visao)
    monkeypatch.setattr(tryd7, "RegistroWinreg", lambda: registro)
    assert cli.main(["desregistrar"]) == 0
    linhas = capsys.readouterr().out.splitlines()
    assert len(linhas) == 4  # 2 chaves x 2 visões
    assert sum("Tryd.RtdServer" in linha for linha in linhas) == 2
    for visao in VISOES:
        assert list(registro.gravado("HKCU", visao)) == ["software\\classes\\outro"]
