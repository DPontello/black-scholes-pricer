"""CLI da ponte — argumentos, despacho e ``espiar`` contra um ``ServidorTcp`` com sessão falsa."""

import io
import socket
import threading
import time
from collections.abc import Callable, Iterator

import pytest

from options_ponte import __main__ as cli
from options_ponte import rtd
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
)
from options_ponte.servidor import Ponte, ServidorTcp

AGORA = "2026-10-28T12:03:00-03:00"


class SessaoMinima:
    """``SessaoRtd`` em memória: devolve o valor inicial configurado e guarda as chamadas."""

    def __init__(self) -> None:
        self.valores: dict[tuple[str, str], object] = {}
        self.conectados: list[tuple[int, tuple[str, str]]] = []
        self.desconectados: list[int] = []

    def conectar(self, id_: int, strings: tuple[str, str]) -> object:
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


def test_servir_sem_pywin32_sai_com_erro_claro_sem_abrir_a_porta(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def sem_pywin32() -> object:
        raise rtd.ErroRtd("pywin32 não instalado: use o Python do Windows (ou do Wine)")

    monkeypatch.setattr(rtd, "carregar_tipos", sem_pywin32)
    porta = _porta_sem_ninguem()
    assert cli.main(["servir", "--porta", str(porta)]) == 1
    assert "pywin32" in capsys.readouterr().err
    with socket.socket() as sock:  # a porta ficou livre
        sock.bind(("127.0.0.1", porta))


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

    def __init__(self, monkeypatch: pytest.MonkeyPatch, pids_tryd: frozenset[int]) -> None:
        self.sessoes: list[SessaoMinima] = []
        self.codigo: list[int] = []
        self.porta = _porta_sem_ninguem()
        monkeypatch.setattr(rtd, "carregar_tipos", lambda: None)
        monkeypatch.setattr(rtd, "SessaoRtdCom", self._abrir)
        monkeypatch.setattr(rtd, "processos_tryd", lambda: pids_tryd)
        monkeypatch.setattr(rtd, "bombear", lambda _passo: time.sleep(0.002))
        self.thread = threading.Thread(target=self._servir, daemon=True)
        self.thread.start()

    def _servir(self) -> None:
        self.codigo.append(cli.main(["servir", "--porta", str(self.porta)]))

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
