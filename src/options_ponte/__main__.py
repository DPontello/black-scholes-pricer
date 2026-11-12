"""CLI da ponte: ``python -m options_ponte <comando>`` (servir, diagnostico, autoteste, espiar,
registrar, desregistrar).

``servir``, ``diagnostico`` e ``autoteste`` falam com o RTD e exigem o Python do Windows (ou
do Wine) com pywin32. ``espiar`` é só stdlib e roda em qualquer Python: assina uns ativos na
ponte e imprime o que ela devolve. ``registrar`` e ``desregistrar`` também são só stdlib (mas
mexem no registro do Windows): gravam e apagam o servidor RTD do Tryd 7 em ``HKCU``.
"""

import argparse
import contextlib
import datetime as dt
import logging
import math
import socket
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TextIO

from options_ponte import rtd, tryd7
from options_ponte.protocolo import (
    CAMPOS_ATIVO,
    LIMITE_TOPICOS,
    PORTA_PONTE,
    Assinar,
    ErroDeProtocolo,
    Status,
    Valor,
    codificar,
    decodificar,
)
from options_ponte.servidor import Ponte, ServidorTcp

_log = logging.getLogger(__name__)
_FORMATO_DO_LOG = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_ESPERA_CONEXAO_S = 5.0
_FATIA_DE_LEITURA_S = 0.2  # a leitura volta ao laço nesse intervalo para ver o fim do prazo
_BYTES_POR_LEITURA = 65536


def _porta(texto: str) -> int:
    try:
        porta = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"porta inválida: {texto!r}") from None
    if not 1 <= porta <= 65535:
        raise argparse.ArgumentTypeError(f"porta fora de 1 a 65535: {porta}")
    return porta


def _limite(texto: str) -> int:
    try:
        limite = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"limite inválido: {texto!r}") from None
    if limite < 1:
        raise argparse.ArgumentTypeError(f"o limite deve ser pelo menos 1: {limite}")
    return limite


def _segundos(texto: str) -> float:
    try:
        segundos = float(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"tempo inválido: {texto!r}") from None
    if not (math.isfinite(segundos) and segundos > 0):  # forma negada: NaN também cai aqui
        raise argparse.ArgumentTypeError(f"o tempo deve ser um número positivo: {texto!r}")
    return segundos


def _lista(texto: str) -> tuple[str, ...]:
    itens = tuple(dict.fromkeys(t.strip().upper() for t in texto.split(",") if t.strip()))
    if not itens:
        raise argparse.ArgumentTypeError("a lista está vazia")
    return itens


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="options_ponte", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="comando", required=True)

    servir = sub.add_parser("servir", help="serve as cotações do Tryd por TCP local (127.0.0.1)")
    servir.add_argument("--porta", type=_porta, default=PORTA_PONTE)
    servir.add_argument(
        "--limite", type=_limite, default=LIMITE_TOPICOS, help="tópicos simultâneos"
    )
    servir.add_argument(
        "--log", type=Path, default=None, help="arquivo do log da ponte (recriado a cada execução)"
    )

    sub.add_parser("diagnostico", help="registro, type library e ambiente (só leitura)")
    sub.add_parser("autoteste", help="cliente RTD contra servidor falso, sem Tryd")

    espiar = sub.add_parser("espiar", help="assina ativos na ponte e imprime o que ela devolve")
    espiar.add_argument("--porta", type=_porta, default=PORTA_PONTE)
    espiar.add_argument("--ativos", type=_lista, required=True, help="ex.: PETR4,VALE3")
    espiar.add_argument("--campos", type=_lista, default=CAMPOS_ATIVO, help="ex.: ULT,OCP,OVD")
    espiar.add_argument("--segundos", type=_segundos, default=10.0)

    registrar = sub.add_parser(
        "registrar", help="registra o servidor RTD do Tryd 7 em HKCU (sem administrador)"
    )
    registrar.add_argument(
        "--pasta",
        type=Path,
        default=None,
        help="pasta do tryd.exe (padrão: a do Tryd aberto agora)",
    )
    sub.add_parser("desregistrar", help="desfaz o 'registrar' (só o que ele gravou em HKCU)")

    falso = sub.add_parser("servidor-falso", help=argparse.SUPPRESS)  # uso interno do autoteste
    falso.add_argument("--segundos", type=_segundos, default=2.0)
    return parser


def _agora_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def _dizer(texto: str, *, erro: bool = False) -> None:
    """Escreve uma linha de status no stdout (ou no stderr, com ``erro``). A ponte do app
    instalado sobe sem console: o fluxo pode ser ``None`` ou a escrita falhar, e isso não derruba
    a ponte."""
    saida = sys.stderr if erro else sys.stdout
    with contextlib.suppress(OSError, ValueError, AttributeError):
        saida.write(texto + "\n")
        saida.flush()


def _texto_de_porta(porta: int, erro: OSError) -> str:
    return f"não foi possível ouvir em 127.0.0.1:{porta}: {erro}"


def _erro_de_porta(porta: int, erro: OSError) -> int:
    texto = _texto_de_porta(porta, erro)
    _log.error("%s", texto)  # o stderr da ponte do app vai para DEVNULL: o arquivo é o rastro
    _dizer(f"erro: {texto}", erro=True)
    return 1


def _abrir_log(log: Path) -> logging.FileHandler | None:
    """O arquivo do log, recriado (``mode="w"``), com a pasta-pai criada. Se não abre, avisa e
    devolve ``None``: o log não derruba a ponte."""
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        arquivo = logging.FileHandler(log, mode="w", encoding="utf-8")
    except OSError as erro:
        _dizer(f"aviso: não foi possível gravar o log em {log}: {erro}", erro=True)
        return None
    arquivo.setLevel(logging.INFO)
    arquivo.setFormatter(logging.Formatter(_FORMATO_DO_LOG))
    return arquivo


@contextlib.contextmanager
def _gravando_log(log: Path | None) -> Iterator[None]:
    """Enquanto o bloco roda, copia o logging para o arquivo ``log`` (se houver).

    O handler é próprio, e não ``basicConfig(filename=...)``: este não faz nada quando o root já
    tem handlers. Sai do root, e é fechado, ao fim do bloco; o nível do root volta ao que era.
    """
    arquivo = None if log is None else _abrir_log(log)
    if arquivo is None:
        yield
        return
    raiz = logging.getLogger()
    nivel_antes = raiz.level
    raiz.addHandler(arquivo)
    if raiz.getEffectiveLevel() > logging.INFO:
        raiz.setLevel(logging.INFO)
    try:
        yield
    finally:
        raiz.removeHandler(arquivo)
        arquivo.close()
        raiz.setLevel(nivel_antes)


def servir(porta: int, limite: int, log: Path | None = None) -> int:
    """Sobe a ponte: servidor TCP local e, enquanto o Tryd estiver aberto, a sessão RTD (nesta
    thread, STA). Roda até ``Encerrar``. Com ``log``, o logging vai também para esse arquivo."""
    logging.basicConfig(level=logging.INFO, format=_FORMATO_DO_LOG)
    try:  # porta ocupada (outra ponte) falha antes de tocar no pywin32 e no log
        socket.create_server(("127.0.0.1", porta)).close()
    except OSError as erro:
        # Fora do arquivo: o ponte.log existente é da ponte que está no ar (talvez travada), e
        # abri-lo agora o zeraria.
        _dizer(f"erro: {_texto_de_porta(porta, erro)}", erro=True)
        return 1
    with _gravando_log(log):
        try:
            return _servir(porta, limite)
        except Exception:
            # O erro que derruba a ponte sobe para o ``main``, que o imprime no stderr, e o do
            # app vai para DEVNULL: aqui ele ainda chega ao arquivo.
            _log.exception("a ponte caiu com um erro não tratado")
            raise


def _servir(porta: int, limite: int) -> int:
    try:
        rtd.carregar_tipos()
    except rtd.ErroRtd as erro:
        # A ponte segue no ar: a Ponte tenta abrir a sessão de novo a cada abertura e manda o
        # motivo no Status, que o app mostra. Sair aqui o deixaria sem explicação.
        _log.warning("sem type library: %s", erro)
    ponte = Ponte(
        rtd.SessaoRtdCom, time.monotonic, _agora_iso, limite, processos_tryd=rtd.processos_tryd
    )
    try:
        servidor = ServidorTcp(ponte, porta, rtd.bombear)
    except OSError as erro:  # alguém ocupou a porta entre a checagem e agora
        ponte.encerrar()
        return _erro_de_porta(porta, erro)
    host, porta_real = servidor.endereco
    ouvindo = f"ponte ouvindo em {host}:{porta_real} (limite de {limite} tópicos)"
    _log.info("%s", ouvindo)
    _dizer(ouvindo)
    try:
        servidor.rodar(threading.Event())
    except KeyboardInterrupt:
        _dizer("ponte interrompida", erro=True)
    return 0


def _imprimir(linha: bytes, saida: TextIO, contagem: dict[str, int]) -> None:
    saida.write(linha.decode("utf-8", errors="replace") + "\n")
    saida.flush()
    try:
        mensagem = decodificar(linha)
    except ErroDeProtocolo:
        return
    if isinstance(mensagem, Valor):
        contagem["valor"] += 1
    elif isinstance(mensagem, Status):
        contagem["status"] += 1


def _ler_ate(conexao: socket.socket, fim: float, saida: TextIO, contagem: dict[str, int]) -> bool:
    """Imprime as linhas que chegam até ``fim`` (monotônico); verdadeiro se a ponte fechou."""
    resto = b""
    while (restante := fim - time.monotonic()) > 0:
        conexao.settimeout(min(restante, _FATIA_DE_LEITURA_S))
        try:
            dados = conexao.recv(_BYTES_POR_LEITURA)
        except TimeoutError:
            continue
        if not dados:
            return True
        *linhas, resto = (resto + dados).split(b"\n")
        for linha in linhas:
            if linha.strip():
                _imprimir(linha, saida, contagem)
    return False


def espiar(
    porta: int, ativos: Sequence[str], campos: Sequence[str], segundos: float, saida: TextIO
) -> int:
    """Assina ``ativos`` x ``campos`` na ponte e imprime em ``saida`` cada linha que ela manda
    durante ``segundos``. Só stdlib.

    Não cancela ao sair: os tópicos ficam assinados até a ponte encerrar. A ponte não conta
    referências, e um ``Cancelar`` do espiar derrubaria os mesmos tópicos que o app assinou.
    """
    topicos = tuple((ativo, campo) for ativo in ativos for campo in campos)
    try:
        conexao = socket.create_connection(("127.0.0.1", porta), timeout=_ESPERA_CONEXAO_S)
    except OSError as erro:
        print(
            f"erro: a ponte não responde em 127.0.0.1:{porta} ({erro}); "
            f"suba com: python -m options_ponte servir --porta {porta}",
            file=sys.stderr,
        )
        return 1
    contagem = {"valor": 0, "status": 0}
    with conexao:
        try:
            conexao.sendall(codificar(Assinar(topicos)))
            fechou = _ler_ate(conexao, time.monotonic() + segundos, saida, contagem)
        except OSError as erro:
            print(f"erro: a conexão com a ponte caiu ({erro})", file=sys.stderr)
            return 1
    if fechou:
        print("erro: a ponte fechou a conexão", file=sys.stderr)
        return 1
    print(
        f"# {contagem['valor']} valor(es) e {contagem['status']} status em {segundos:g} s",
        file=sys.stderr,
    )
    return 0


def registrar(pasta: Path | None) -> int:
    """Grava o ``Tryd.RtdServer`` do Tryd 7 em ``HKCU`` (sem administrador), nas visões de 64 e
    32 bits. A pasta é ``--pasta`` ou a do ``tryd.exe`` em execução."""
    pasta = pasta.absolute() if pasta is not None else tryd7.pasta_do_tryd()
    if pasta is None:
        print(
            'erro: não achei a pasta do Tryd: abra o Tryd ou passe --pasta "<pasta do tryd.exe>"',
            file=sys.stderr,
        )
        return 2
    dll = pasta / tryd7.DLL_RELATIVA
    if not dll.is_file():
        print(f"erro: não achei {dll}", file=sys.stderr)
        return 2
    try:
        identidade = tryd7.identidade_do_assembly(dll)
        gravadas = tryd7.registrar(tryd7.RegistroWinreg(), dll, identidade)
    except (ValueError, OSError) as erro:  # PowerShell sem a identidade, ou registro sem acesso
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    for descricao in gravadas:
        print(descricao)
    print("pronto: rode 'PonteTryd.exe diagnostico' para conferir")
    return 0


def desregistrar() -> int:
    """Apaga o ``Tryd.RtdServer`` do Tryd 7 de ``HKCU`` (só o que o ``registrar`` grava)."""
    try:
        apagadas = tryd7.desregistrar(tryd7.RegistroWinreg())
    except OSError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    for descricao in apagadas:
        print(descricao)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    try:
        match args.comando:
            case "servir":
                return servir(args.porta, args.limite, args.log)
            case "diagnostico":
                return rtd.diagnostico()
            case "autoteste":
                return rtd.autoteste()
            case "servidor-falso":
                return rtd.servir_falso(args.segundos)
            case "registrar":
                return registrar(args.pasta)
            case "desregistrar":
                return desregistrar()
            case _:
                return espiar(args.porta, args.ativos, args.campos, args.segundos, sys.stdout)
    except rtd.ErroRtd as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
