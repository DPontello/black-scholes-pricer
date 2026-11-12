"""A versão e as notas do release que o workflow de publicação cria a cada subida na master.

Só biblioteca padrão. No workflow, com ``<sha>`` o commit que o CI testou:

    python packaging/publicar.py versao --commit <sha>   -> 0.5.0 (vazio se o commit já tem tag)
    python packaging/publicar.py notas --commit <sha>    -> as notas do release, em Markdown
    python packaging/publicar.py gravar 0.5.0            -> reescreve o version do pyproject.toml

Os dois primeiros números da versão vêm do ``pyproject.toml``; o terceiro é o maior já publicado
nessa linha (tags ``vX.Y.Z``) mais 1, ou 0 se ainda não há nenhum.
"""

import argparse
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

_TAG = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
_MERGE_DE_PR = re.compile(r"Merge pull request #\d+ from \S+/(\S+)")
_PREFIXO = re.compile(r"([a-z]+)(\(([^)]*)\))?!?:\s*")
_RAMOS_DE_RELEASE = {"development", "master"}
_TIPOS_INTERNOS = {"docs", "test", "ci", "chore"}
_ESCOPOS_INTERNOS = {"testes"}


def _git(*args: str) -> str:
    resultado = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return resultado.stdout


def linha(versao_pyproject: str) -> tuple[int, int]:
    achado = re.match(r"(\d+)\.(\d+)", versao_pyproject)
    if achado is None:
        raise ValueError(f"versão sem números no começo: {versao_pyproject!r}")
    return int(achado.group(1)), int(achado.group(2))


def numeros(tag_ou_versao: str) -> tuple[int, int, int] | None:
    achado = _TAG.fullmatch(tag_ou_versao)
    if achado is None:
        return None
    return int(achado.group(1)), int(achado.group(2)), int(achado.group(3))


def proxima_versao(versao_pyproject: str, tags: Sequence[str]) -> str:
    esta = linha(versao_pyproject)
    publicadas = [n for n in map(numeros, tags) if n is not None]
    ultima = max(publicadas, default=None)
    if ultima is not None and ultima[:2] > esta:
        raise ValueError(
            f"a linha {esta[0]}.{esta[1]} do pyproject.toml é menor que a do último release "
            f"(v{ultima[0]}.{ultima[1]}.{ultima[2]})"
        )
    da_linha = [n[2] for n in publicadas if n[:2] == esta]
    return f"{esta[0]}.{esta[1]}.{max(da_linha) + 1 if da_linha else 0}"


def tag_anterior(tags: Sequence[str]) -> str | None:
    releases = [(n, tag) for tag in tags if (n := numeros(tag)) is not None]
    return max(releases)[1] if releases else None


def _titulo_para_nota(mensagem: str) -> str | None:
    linhas = mensagem.strip().splitlines()
    achado = _MERGE_DE_PR.fullmatch(linhas[0].strip()) if linhas else None
    if achado is None or achado.group(1) in _RAMOS_DE_RELEASE:
        return None
    titulo = next((texto.strip() for texto in linhas[1:] if texto.strip()), "")
    prefixo = _PREFIXO.match(titulo)
    if prefixo is not None:
        if prefixo.group(1) in _TIPOS_INTERNOS or prefixo.group(3) in _ESCOPOS_INTERNOS:
            return None
        titulo = titulo[prefixo.end() :]
    return titulo[:1].upper() + titulo[1:] if titulo else None


def notas(mensagens: Sequence[str]) -> str:
    itens: list[str] = []
    for mensagem in mensagens:
        titulo = _titulo_para_nota(mensagem)
        if titulo is not None and titulo not in itens:
            itens.append(titulo)
    return "\n".join(f"- {item}" for item in itens) or "- Ajustes internos"


def gravar_versao(texto_pyproject: str, versao: str) -> str:
    if re.fullmatch(r"\d+\.\d+\.\d+", versao) is None:
        raise ValueError(f"versão do release com três números, sem sufixo: {versao!r}")
    secao = re.search(r"^\[project\]\n(.*?)(?=^\[|\Z)", texto_pyproject, re.M | re.S)
    if secao is None:
        raise ValueError("sem a seção [project] no pyproject.toml")
    corpo, trocas = re.subn(
        r'^(version\s*=\s*)"[^"]*"',
        lambda achado: f'{achado.group(1)}"{versao}"',
        secao.group(1),
        count=1,
        flags=re.M,
    )
    if trocas == 0:
        raise ValueError("sem o version na seção [project] do pyproject.toml")
    return texto_pyproject[: secao.start(1)] + corpo + texto_pyproject[secao.end(1) :]


def _versao_do_pyproject(pyproject: Path) -> str:
    with pyproject.open("rb") as arquivo:
        return str(tomllib.load(arquivo)["project"]["version"])


def _tags(git: Callable[..., str], *args: str) -> list[str]:
    return git("tag", *args, "--list", "v*").split()


def main(argv: Sequence[str] | None = None, git: Callable[..., str] = _git) -> int:
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--pyproject", type=Path, default=PYPROJECT)
    pedido = argparse.ArgumentParser()
    comandos = pedido.add_subparsers(dest="comando", required=True)
    for nome in ("versao", "notas"):
        comandos.add_parser(nome, parents=[comum]).add_argument("--commit", required=True)
    comandos.add_parser("gravar", parents=[comum]).add_argument("versao")
    args = pedido.parse_args(sys.argv[1:] if argv is None else list(argv))

    if args.comando == "versao":
        if any(numeros(tag) is not None for tag in _tags(git, "--points-at", args.commit)):
            print()
        else:
            print(proxima_versao(_versao_do_pyproject(args.pyproject), _tags(git)))
    elif args.comando == "notas":
        anterior = tag_anterior(_tags(git, "--merged", args.commit))
        intervalo = args.commit if anterior is None else f"{anterior}..{args.commit}"
        saida = git("log", "--merges", "--format=%B%x00", intervalo)
        print(notas([mensagem for mensagem in saida.split("\0") if mensagem.strip()]))
    else:
        texto = args.pyproject.read_text(encoding="utf-8")
        args.pyproject.write_text(gravar_versao(texto, args.versao), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
