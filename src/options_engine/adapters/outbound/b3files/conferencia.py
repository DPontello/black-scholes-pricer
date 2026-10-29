"""Confere arquivos reais da B3 contra as premissas de leitura do app. Só lê."""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.cotahist.errors import SourceFileError
from options_engine.adapters.outbound.cotahist.instruments import (
    InstrumentInfo,
    load_instruments,
    raw_rows,
)
from options_engine.adapters.outbound.cotahist.parser import (
    MARKET_CALL,
    MARKET_PUT,
    CotahistRecord,
    parse_cotahist,
    raw_lines,
)

__all__ = ["Premissa", "Situacao", "conferir_arquivos_b3", "formatar_relatorio"]

_TOLERANCIA_STRIKE: Final = 0.005
_AMOSTRA: Final = 5
_MILHAR: Final = re.compile(r"^\d{1,3}([.,]\d{3})+([.,]\d+)?$")
_DECIMAL_PONTO: Final = re.compile(r"^\d+(\.\d+)?$")
_DECIMAL_VIRGULA: Final = re.compile(r"^\d+(,\d+)?$")
_ISO: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BR: Final = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_DATA_NO_NOME: Final = re.compile(r"_(\d{8})(?!\d)")


class Situacao(Enum):
    OK = "ok"
    ATENCAO = "atenção"
    FALHA = "FALHA"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Premissa:
    nome: str
    situacao: Situacao
    detalhe: str


def conferir_arquivos_b3(
    cotahist_paths: Sequence[Path],
    cadastro_path: Path,
    pex: Mapping[str, float] | None = None,
) -> tuple[Premissa, ...]:
    premissas: list[Premissa] = []
    registros: list[CotahistRecord] = []
    for path in cotahist_paths:
        totreg = _totreg(path)
        premissas.append(totreg)
        try:
            registros.extend(parse_cotahist(path))
        except SourceFileError as erro:
            if totreg.situacao is Situacao.OK:
                nome = f"Leitura do COTAHIST ({path.name})"
                premissas.append(Premissa(nome, Situacao.FALHA, str(erro)))
    try:
        colunas, linhas = raw_rows(cadastro_path)
        cadastro = load_instruments(cadastro_path)
    except SourceFileError as erro:
        premissas.append(Premissa("Leitura do cadastro", Situacao.FALHA, str(erro)))
        return tuple(premissas)

    opcoes = _linhas_de_opcao(colunas, linhas)
    sessao = max((r.session for r in registros), default=None)
    do_pregao = [
        r for r in registros if r.session == sessao and r.market in (MARKET_CALL, MARKET_PUT)
    ]
    premissas += [
        _dominio(colunas, opcoes, "OptnStyle", ("AMER", "EURO"), "sem estilo, a série sai do app"),
        _dominio(colunas, opcoes, "OptnTp", ("CALL", "PUT"), "sem tipo, a série não é assinada"),
        _strike_formato(colunas, opcoes),
        _vencimento_formato(colunas, opcoes),
        _ativo_objeto(colunas, opcoes),
        _especi(do_pregao),
        _cruzar(do_pregao, cadastro, "PREEXE (COTAHIST) = ExrcPric (cadastro)", "strike"),
        _cruzar(do_pregao, cadastro, "DATVEN (COTAHIST) = XprtnDt (cadastro)", "expiry"),
        _mesmo_pregao(cadastro_path, sessao),
    ]
    if pex:
        premissas.append(_cruzar_pex(pex, do_pregao, cadastro))
    return tuple(premissas)


def formatar_relatorio(premissas: Sequence[Premissa]) -> str:
    largura = max((len(p.situacao.value) for p in premissas), default=0)
    linhas = [f"[{p.situacao.value:<{largura}}] {p.nome}: {p.detalhe}" for p in premissas]
    contagem = Counter(p.situacao for p in premissas)
    linhas.append(
        f"\n{contagem[Situacao.OK]} ok, {contagem[Situacao.ATENCAO]} atenção, "
        f"{contagem[Situacao.FALHA]} falha(s)"
    )
    return "\n".join(linhas)


def _totreg(path: Path) -> Premissa:
    nome = f"TOTREG do trailer ({path.name})"
    try:
        linhas = raw_lines(path)
    except (SourceFileError, OSError) as erro:
        return Premissa(nome, Situacao.FALHA, f"arquivo ilegível: {erro}")
    if not linhas or not linhas[-1][1].startswith("99"):
        return Premissa(nome, Situacao.FALHA, "sem trailer 99 no fim: arquivo truncado?")
    bruto = linhas[-1][1][31:42]
    if not bruto.strip().isdigit():
        return Premissa(nome, Situacao.FALHA, f"TOTREG ilegível: {bruto!r}")
    declarado, total = int(bruto), len(linhas)
    if declarado == total:
        return Premissa(nome, Situacao.OK, f"{total} registros, contando header e trailer")
    if declarado == total - 2:
        return Premissa(
            nome,
            Situacao.FALHA,
            f"TOTREG {declarado} NÃO conta header e trailer ({total} linhas): o app recusa o "
            "arquivo; corrigir o parser",
        )
    return Premissa(nome, Situacao.FALHA, f"TOTREG {declarado} e {total} linhas no arquivo")


def _especi(opcoes: Sequence[CotahistRecord]) -> Premissa:
    nome = "ESPECI das opções"
    if not opcoes:
        return Premissa(nome, Situacao.ATENCAO, "nenhuma opção no último pregão do COTAHIST")
    primeiros = Counter(r.specification.split()[0] if r.specification else "" for r in opcoes)
    resumo = ", ".join(f"{termo or '(vazio)'}: {n}" for termo, n in primeiros.most_common(8))
    exemplos = ", ".join(
        f"{r.symbol}={r.specification!r}" for r in sorted(opcoes, key=lambda r: r.symbol)[:3]
    )
    return Premissa(
        nome,
        Situacao.INFO,
        f"1º termo nas {len(opcoes)} opções: {resumo} (ex.: {exemplos}); "
        "o adapter COTAHIST usa a classe (ON/PN/UNT) para separar PETR3 de PETR4",
    )


def _coluna(colunas: Sequence[str], nome: str) -> int | None:
    return colunas.index(nome) if nome in colunas else None


def _celula(linha: Sequence[str], indice: int | None) -> str:
    return linha[indice] if indice is not None and indice < len(linha) else ""


def _linhas_de_opcao(
    colunas: Sequence[str], linhas: Sequence[Sequence[str]]
) -> tuple[Sequence[str], ...]:
    i_tipo = _coluna(colunas, "OptnTp")
    indice = i_tipo if i_tipo is not None else _coluna(colunas, "ExrcPric")
    return tuple(linha for linha in linhas if _celula(linha, indice))


def _sem_coluna(nome: str, coluna: str) -> Premissa:
    return Premissa(nome, Situacao.FALHA, f"coluna {coluna!r} ausente no cadastro")


def _dominio(
    colunas: Sequence[str],
    opcoes: Sequence[Sequence[str]],
    coluna: str,
    prefixos: tuple[str, ...],
    consequencia: str,
) -> Premissa:
    nome = f"Valores de {coluna}"
    indice = _coluna(colunas, coluna)
    if indice is None:
        return _sem_coluna(nome, coluna)
    valores = Counter(_celula(linha, indice) for linha in opcoes)
    resumo = ", ".join(f"{v or '(vazio)'}: {n}" for v, n in valores.most_common(6))
    estranhos = {v for v in valores if v and not v.upper().startswith(prefixos)}
    if estranhos:
        return Premissa(
            nome,
            Situacao.FALHA,
            f"valores fora de {'/'.join(p + '*' for p in prefixos)}: {sorted(estranhos)!r} "
            f"({resumo}); {consequencia}",
        )
    if valores.get(""):
        return Premissa(nome, Situacao.ATENCAO, f"{valores['']} opção(ões) sem valor ({resumo})")
    return Premissa(nome, Situacao.OK, f"{len(opcoes)} opções ({resumo})")


def _strike_formato(colunas: Sequence[str], opcoes: Sequence[Sequence[str]]) -> Premissa:
    nome = "Formato do ExrcPric"
    indice = _coluna(colunas, "ExrcPric")
    if indice is None:
        return _sem_coluna(nome, "ExrcPric")
    brutos = [_celula(linha, indice) for linha in opcoes]
    ponto = sum(1 for b in brutos if _DECIMAL_PONTO.match(b))
    virgula = sum(1 for b in brutos if _DECIMAL_VIRGULA.match(b) and not _DECIMAL_PONTO.match(b))
    # "1.234" e "1,234" são ambíguos: o app leria 1,234 em vez de 1234.
    ambiguos = {b for b in brutos if _MILHAR.match(b) and not _DECIMAL_PONTO.match(b)}
    ilegiveis = {
        b for b in brutos if b and not (_DECIMAL_PONTO.match(b) or _DECIMAL_VIRGULA.match(b))
    }
    resumo = f"ponto decimal: {ponto}, vírgula decimal: {virgula}, vazios: {brutos.count('')}"
    if ambiguos or ilegiveis:
        exemplos = sorted(ambiguos | ilegiveis)
        return Premissa(
            nome,
            Situacao.FALHA,
            f"{len(exemplos)} formato(s) que o app lê errado ou não lê, ex.: "
            f"{exemplos[:_AMOSTRA]!r} ({resumo}); corrigir a leitura do strike",
        )
    if ponto and virgula:
        return Premissa(nome, Situacao.ATENCAO, f"formatos misturados ({resumo})")
    return Premissa(nome, Situacao.OK, resumo)


def _vencimento_formato(colunas: Sequence[str], opcoes: Sequence[Sequence[str]]) -> Premissa:
    nome = "Formato do XprtnDt"
    indice = _coluna(colunas, "XprtnDt")
    if indice is None:
        return _sem_coluna(nome, "XprtnDt")
    brutos = [_celula(linha, indice) for linha in opcoes]
    estranhos = sorted({b for b in brutos if b and not (_ISO.match(b) or _BR.match(b))})
    iso = sum(1 for b in brutos if _ISO.match(b))
    br = sum(1 for b in brutos if _BR.match(b))
    resumo = f"AAAA-MM-DD: {iso}, DD/MM/AAAA: {br}, vazios: {brutos.count('')}"
    if estranhos:
        return Premissa(
            nome, Situacao.FALHA, f"formatos que o app não lê: {estranhos[:_AMOSTRA]!r} ({resumo})"
        )
    return Premissa(nome, Situacao.OK, resumo)


def _ativo_objeto(colunas: Sequence[str], opcoes: Sequence[Sequence[str]]) -> Premissa:
    nome = "UndrlygTckrSymb1 nas opções"
    indice = _coluna(colunas, "UndrlygTckrSymb1")
    if indice is None:
        return Premissa(
            nome,
            Situacao.ATENCAO,
            "coluna ausente: o ao vivo rejeita as séries de raiz dividida (PETR3 e PETR4)",
        )
    if not opcoes:
        return Premissa(nome, Situacao.ATENCAO, "nenhuma opção no cadastro")
    preenchidas = sum(1 for linha in opcoes if _celula(linha, indice))
    detalhe = f"{preenchidas} de {len(opcoes)} opções ({preenchidas / len(opcoes):.0%})"
    if preenchidas == len(opcoes):
        return Premissa(nome, Situacao.OK, detalhe)
    return Premissa(
        nome,
        Situacao.ATENCAO,
        f"{detalhe}: as sem ativo-objeto de raiz dividida (PETR3/PETR4) saem rejeitadas no ao "
        "vivo; se forem muitas, usar a regra do ESPECI do adapter COTAHIST",
    )


def _cruzar(
    opcoes: Sequence[CotahistRecord],
    cadastro: Mapping[str, InstrumentInfo],
    nome: str,
    campo: str,
) -> Premissa:
    pares = [
        (r, getattr(r, campo), getattr(cadastro[r.symbol], campo))
        for r in opcoes
        if r.symbol in cadastro and getattr(cadastro[r.symbol], campo) is not None
    ]
    if not pares:
        return Premissa(nome, Situacao.ATENCAO, "nenhuma opção do último pregão nos dois arquivos")
    if campo == "strike":
        diferentes = [(r, a, b) for r, a, b in pares if abs(a - b) > _TOLERANCIA_STRIKE]
    else:
        diferentes = [(r, a, b) for r, a, b in pares if a != b]
    detalhe = f"{len(pares) - len(diferentes)} de {len(pares)} iguais"
    if not diferentes:
        return Premissa(nome, Situacao.OK, detalhe)
    exemplos = ", ".join(
        f"{r.symbol}: {_texto(a)} x {_texto(b)}" for r, a, b in diferentes[:_AMOSTRA]
    )
    return Premissa(nome, Situacao.FALHA, f"{detalhe}; diferentes: {exemplos}")


def _texto(valor: object) -> str:
    return f"{valor:.2f}" if isinstance(valor, float) else str(valor)


def _mesmo_pregao(cadastro_path: Path, sessao: date | None) -> Premissa:
    nome = "Cadastro do mesmo pregão do último COTAHIST"
    achado = _DATA_NO_NOME.search(cadastro_path.name)
    if achado is None:
        return Premissa(nome, Situacao.ATENCAO, "o nome do cadastro não traz a data (_AAAAMMDD)")
    texto = achado.group(1)
    data = date(int(texto[:4]), int(texto[4:6]), int(texto[6:]))
    if sessao is None:
        return Premissa(nome, Situacao.ATENCAO, f"cadastro de {data}; COTAHIST sem pregão legível")
    if data == sessao:
        return Premissa(nome, Situacao.OK, f"os dois são de {data}")
    return Premissa(
        nome,
        Situacao.ATENCAO,
        f"cadastro de {data} e último pregão do COTAHIST em {sessao}: séries novas ou "
        "vencidas podem não bater",
    )


def _cruzar_pex(
    pex: Mapping[str, float],
    opcoes: Sequence[CotahistRecord],
    cadastro: Mapping[str, InstrumentInfo],
) -> Premissa:
    nome = "PEX do Tryd = strike da B3 (ajuste por proventos)"
    preexe = {r.symbol: r.strike for r in opcoes}
    linhas = []
    diferentes = 0
    for ticker, valor in sorted(pex.items()):
        b3 = preexe.get(ticker)
        if b3 is None and ticker in cadastro:
            b3 = cadastro[ticker].strike
        if b3 is None:
            linhas.append(f"{ticker}: PEX {valor:.2f}, sem strike na B3")
            diferentes += 1
            continue
        igual = abs(b3 - valor) <= _TOLERANCIA_STRIKE
        diferentes += 0 if igual else 1
        linhas.append(f"{ticker}: PEX {valor:.2f} x B3 {b3:.2f}{'' if igual else ' (DIFERE)'}")
    detalhe = "; ".join(linhas)
    if diferentes:
        return Premissa(
            nome,
            Situacao.FALHA,
            f"{detalhe} — o strike da B3 não vem ajustado como o do Tryd: o app usaria o "
            "strike errado nas séries ajustadas",
        )
    return Premissa(nome, Situacao.OK, f"{detalhe} — a B3 já publica o strike ajustado")
