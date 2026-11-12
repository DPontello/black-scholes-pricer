"""Confere arquivos reais da B3 contra as premissas de leitura do app. Só lê."""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Final

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
    iter_cotahist,
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
    ultimo = _UltimoPregao()
    for path in cotahist_paths:
        totreg = _totreg(path)
        premissas.append(totreg)
        try:
            ultimo.ler(path)
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
    sessao, do_pregao = ultimo.pregao, list(ultimo.opcoes.values())
    premissas += [
        _dominio(colunas, opcoes, "OptnStyle", ("AMER", "EURO"), "sem estilo, a série sai do app"),
        _dominio(colunas, opcoes, "OptnTp", ("CALL", "PUT"), "sem tipo, a série não é assinada"),
        _strike_formato(colunas, opcoes),
        _vencimento_formato(colunas, opcoes),
        _ativo_objeto(colunas, opcoes, cadastro),
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


class _UltimoPregao:
    """Opções do pregão mais recente entre os arquivos, lidas em fluxo, uma por ticker.

    O anual já contém o pregão do diário: sem tirar a repetição, cada série contaria duas vezes.
    """

    def __init__(self) -> None:
        self.pregao: date | None = None
        self.opcoes: dict[str, CotahistRecord] = {}

    def _escolher(self, pregao: date, mercado: int) -> bool:
        if self.pregao is None or pregao > self.pregao:
            self.pregao = pregao
            self.opcoes = {}
        return pregao == self.pregao and mercado in (MARKET_CALL, MARKET_PUT)

    def ler(self, path: Path) -> None:
        # Arquivo recusado não contribui com nada, nem com o que leu antes do erro.
        antes = (self.pregao, self.opcoes)
        self.opcoes = dict(self.opcoes)
        try:
            for registro in iter_cotahist(path, self._escolher):
                self.opcoes.setdefault(registro.symbol, registro)
        except SourceFileError:
            self.pregao, self.opcoes = antes
            raise


def _totreg(path: Path) -> Premissa:
    nome = f"TOTREG do trailer ({path.name})"
    total, ultima = 0, ""
    try:
        for _, linha in raw_lines(path):
            total, ultima = total + 1, linha
    except (SourceFileError, OSError) as erro:
        return Premissa(nome, Situacao.FALHA, f"arquivo ilegível: {erro}")
    if not ultima.startswith("99"):
        return Premissa(nome, Situacao.FALHA, "sem trailer 99 no fim: arquivo truncado?")
    bruto = ultima[31:42]
    if not bruto.strip().isdigit():
        return Premissa(nome, Situacao.FALHA, f"TOTREG ilegível: {bruto!r}")
    declarado = int(bruto)
    if declarado == total - 2:
        return Premissa(nome, Situacao.OK, f"{declarado} registros, sem header e trailer")
    if declarado == total:
        return Premissa(
            nome,
            Situacao.FALHA,
            f"TOTREG {declarado} conta header e trailer, como diz o layout, mas os arquivos "
            "reais de 28/10/2026 não contam: o app recusa o arquivo",
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
    # Inteiro ("170") é lido igual nos dois formatos: não conta para nenhum.
    inteiros = sum(1 for b in brutos if b.isdigit())
    ponto = sum(1 for b in brutos if _DECIMAL_PONTO.match(b) and not b.isdigit())
    virgula = sum(1 for b in brutos if _DECIMAL_VIRGULA.match(b) and not b.isdigit())
    # "1.234" e "1,234" são ambíguos: o app leria 1,234 em vez de 1234.
    ambiguos = {b for b in brutos if _MILHAR.match(b) and not _DECIMAL_PONTO.match(b)}
    ilegiveis = {
        b for b in brutos if b and not (_DECIMAL_PONTO.match(b) or _DECIMAL_VIRGULA.match(b))
    }
    resumo = (
        f"ponto decimal: {ponto}, vírgula decimal: {virgula}, inteiros: {inteiros}, "
        f"vazios: {brutos.count('')}"
    )
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


def _ativo_objeto(
    colunas: Sequence[str],
    opcoes: Sequence[Sequence[str]],
    cadastro: Mapping[str, InstrumentInfo],
) -> Premissa:
    nome = "Ativo-objeto das opções (UndrlygTckrSymb1 ou Asst)"
    i_simbolo = _coluna(colunas, "TckrSymb")
    i_categoria = _coluna(colunas, "SctyCtgyNm")
    i_proprio = _coluna(colunas, "UndrlygTckrSymb1")
    # Opção de índice ou de futuro não tem ativo à vista: só as de ações contam.
    de_acoes = [
        linha
        for linha in opcoes
        if i_categoria is None or _celula(linha, i_categoria) == "OPTION ON EQUITIES"
    ]
    if not de_acoes:
        return Premissa(nome, Situacao.ATENCAO, "nenhuma opção sobre ações no cadastro")
    com_objeto = [
        linha
        for linha in de_acoes
        if (info := cadastro.get(_celula(linha, i_simbolo))) and info.underlying_symbol
    ]
    pela_coluna = sum(1 for linha in com_objeto if _celula(linha, i_proprio))
    detalhe = (
        f"{len(com_objeto)} de {len(de_acoes)} opções sobre ações "
        f"({len(com_objeto) / len(de_acoes):.0%}): {pela_coluna} pela UndrlygTckrSymb1, "
        f"{len(com_objeto) - pela_coluna} pelo Asst"
    )
    if len(com_objeto) == len(de_acoes):
        return Premissa(nome, Situacao.OK, detalhe)
    return Premissa(
        nome,
        Situacao.ATENCAO,
        f"{detalhe}; as sem ativo-objeto de raiz dividida (PETR3/PETR4) saem rejeitadas no ao vivo",
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
    nota = ""
    if campo == "strike":
        # Opção de índice (FATCOT 100 no IBOV real) traz o PREEXE em pontos, sem o fator.
        indice = [p for p in pares if p[0].quote_factor != 1]
        pares = [p for p in pares if p[0].quote_factor == 1]
        if indice:
            nota = (
                f"; {len(indice)} opção(ões) de índice (FATCOT diferente de 1) fora: "
                "o app não as usa"
            )
    if not pares:
        return Premissa(nome, Situacao.ATENCAO, "nenhuma opção do último pregão nos dois arquivos")
    if campo == "strike":
        diferentes = [(r, a, b) for r, a, b in pares if abs(a - b) > _TOLERANCIA_STRIKE]
    else:
        diferentes = [(r, a, b) for r, a, b in pares if a != b]
    detalhe = f"{len(pares) - len(diferentes)} de {len(pares)} iguais{nota}"
    if not diferentes:
        return Premissa(nome, Situacao.OK, detalhe)
    deslocadas = _raizes_deslocadas(diferentes) if campo == "strike" else None
    if deslocadas:
        return Premissa(
            nome,
            Situacao.ATENCAO,
            f"{detalhe}; strike deslocado pelo mesmo valor em {deslocadas}: provável ajuste "
            "por provento entre o pregão do COTAHIST e o cadastro (conferir com o PEX)",
        )
    exemplos = ", ".join(
        f"{r.symbol}: {_texto(a)} x {_texto(b)}" for r, a, b in diferentes[:_AMOSTRA]
    )
    return Premissa(nome, Situacao.FALHA, f"{detalhe}; diferentes: {exemplos}")


def _raizes_deslocadas(diferentes: Sequence[tuple[CotahistRecord, Any, Any]]) -> str | None:
    """ "JHSF (76 séries, -0.07)" se cada raiz com diferença tem 2+ séries, todas com o mesmo
    deslocamento. No real de 28/10 só parte das séries de JHSF mudou: as de strike já ajustado
    antes ficaram iguais."""
    deslocamentos: dict[str, list[float]] = {}
    for r, a, b in diferentes:
        deslocamentos.setdefault(r.symbol[:4], []).append(b - a)
    partes = []
    for raiz, valores in sorted(deslocamentos.items()):
        if len(valores) < 2 or max(valores) - min(valores) > _TOLERANCIA_STRIKE:
            return None
        partes.append(f"{raiz} ({len(valores)} séries, {valores[0]:+.2f})")
    return ", ".join(partes)


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
