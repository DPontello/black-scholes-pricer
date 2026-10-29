"""CLI da ponte: ``python -m options_ponte <servir|diagnostico|autoteste|espiar>``.

``servir``, ``diagnostico`` e ``autoteste`` falam com o RTD e exigem o Python do Windows (ou
do Wine) com pywin32. ``espiar`` é só stdlib e roda em qualquer Python: assina uns ativos na
ponte e imprime o que ela devolve.
"""

import argparse
import datetime as dt
import logging
import math
import socket
import sys
import threading
import time
from collections.abc import Sequence
from typing import TextIO

from options_ponte import rtd
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

    sub.add_parser("diagnostico", help="registro, type library e ambiente (só leitura)")
    sub.add_parser("autoteste", help="cliente RTD contra servidor falso, sem Tryd")

    espiar = sub.add_parser("espiar", help="assina ativos na ponte e imprime o que ela devolve")
    espiar.add_argument("--porta", type=_porta, default=PORTA_PONTE)
    espiar.add_argument("--ativos", type=_lista, required=True, help="ex.: PETR4,VALE3")
    espiar.add_argument("--campos", type=_lista, default=CAMPOS_ATIVO, help="ex.: ULT,OCP,OVD")
    espiar.add_argument("--segundos", type=_segundos, default=10.0)

    falso = sub.add_parser("servidor-falso", help=argparse.SUPPRESS)  # uso interno do autoteste
    falso.add_argument("--segundos", type=_segundos, default=2.0)
    return parser


def _agora_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def _erro_de_porta(porta: int, erro: OSError) -> int:
    print(f"erro: não foi possível ouvir em 127.0.0.1:{porta}: {erro}", file=sys.stderr)
    return 1


def servir(porta: int, limite: int) -> int:
    """Sobe a ponte: sessão RTD (esta thread, STA) + servidor TCP local. Roda até ``Encerrar``."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:  # antes de assinar no Tryd: porta ocupada (outra ponte) não deve abrir uma 2ª sessão RTD
        socket.create_server(("127.0.0.1", porta)).close()
    except OSError as erro:
        return _erro_de_porta(porta, erro)
    sessao = rtd.SessaoRtdCom()
    ponte = Ponte(sessao, time.monotonic, _agora_iso, limite)
    try:
        servidor = ServidorTcp(ponte, porta, rtd.bombear)
    except OSError as erro:  # alguém ocupou a porta entre a checagem e agora
        ponte.encerrar()
        return _erro_de_porta(porta, erro)
    host, porta_real = servidor.endereco
    print(f"ponte ouvindo em {host}:{porta_real} (limite de {limite} tópicos)", flush=True)
    try:
        servidor.rodar(threading.Event())
    except KeyboardInterrupt:
        print("ponte interrompida", file=sys.stderr)
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


def main(argv: Sequence[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    try:
        match args.comando:
            case "servir":
                return servir(args.porta, args.limite)
            case "diagnostico":
                return rtd.diagnostico()
            case "autoteste":
                return rtd.autoteste()
            case "servidor-falso":
                return rtd.servir_falso(args.segundos)
            case _:
                return espiar(args.porta, args.ativos, args.campos, args.segundos, sys.stdout)
    except rtd.ErroRtd as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
