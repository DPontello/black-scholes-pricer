"""Gerador DETERMINÍSTICO da fixture sintética do COTAHIST e do Cadastro de Instrumentos.

Dados inventados — nunca redistribuir arquivos reais da B3 (ROADMAP, Sprint 5).
Rodar da raiz do repositório:

    PYTHONPATH=src python -m tests.data.cotahist.build_fixture

Conteúdo (pregão de referência 2026-10-23, sexta-feira):

- fechamentos de ``PREGOES`` pregões úteis até o de referência (calendário B3
  empacotado — atravessa o feriado de 12/10) para PETR4, PETR3 e VALE3,
  por retornos senoidais fixos (vol realizada ~20-25%);
- ITUB4 com só 5 pregões (histórico insuficiente) e BBAS3 sem registro no
  pregão de referência (sem fechamento);
- VALE3 sem ofertas no pregão (ativo "sem ofertas", ADR-0004);
- séries de PETR4 em dois vencimentos (2026-11-19, quinta, porque 20/11 é
  feriado nacional, e 2026-12-18) com prêmios do próprio kernel sob um smile
  conhecido, arredondados ao centavo, e os casos de borda: só bid, só ask,
  book vazio com e sem negócio, sem estilo no cadastro, ausente do
  cadastro, INDOPC != 0, book cruzado, vínculo ambíguo (ESPECI ``UNT`` com
  PETR3 e PETR4 na mesma raiz), vínculo pelo cadastro (``UndrlygTckrSymb1``),
  ticker duplicado com dados divergentes, série vencida e put americana;
- séries de PETR3 (ESPECI ``ON``) e de VALE3.
"""

import csv
import io
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.b3_calendar import StaticHolidayCalendar
from options_engine.domain.kernel.black_scholes import bs_price
from tests.adapters.cotahist._layout import arquivo, registro

__all__ = [
    "COTAHIST_NAME",
    "INSTRUMENTS_NAME",
    "REFERENCE_SESSION",
    "build",
    "render",
]

REFERENCE_SESSION: Final = date(2026, 10, 23)
NOVEMBRO: Final = date(2026, 11, 19)
DEZEMBRO: Final = date(2026, 12, 18)
VENCIDA: Final = date(2026, 10, 16)
PREGOES: Final = 30
CDI: Final = 0.15
COTAHIST_NAME: Final = "COTAHIST_SINTETICO_2026.TXT"
INSTRUMENTS_NAME: Final = "InstrumentsConsolidatedFile_20261023_SINTETICO.csv"

_CALENDARIO = StaticHolidayCalendar.from_packaged_data()
_A_VISTA, _CALL, _PUT = 10, 70, 80


def _pregoes(ate: date, quantidade: int) -> list[date]:
    """Os ``quantidade`` pregões úteis da B3 que terminam em ``ate`` (inclusive)."""
    dias: list[date] = []
    dia = ate
    while len(dias) < quantidade:
        if _CALENDARIO.business_days_between(dia, dia + timedelta(days=1)) == 1:
            dias.append(dia)
        dia -= timedelta(days=1)
    return sorted(dias)


def _fechamentos(
    ultimo: float, amplitude: float, frequencia: float, fase: float, n: int
) -> list[float]:
    """Série de ``n`` fechamentos que termina em ``ultimo``, por retornos senoidais fixos."""
    valores = [ultimo]
    for i in range(n - 1, 0, -1):
        valores.append(valores[-1] / math.exp(amplitude * math.sin(frequencia * i + fase)))
    return [round(v, 2) for v in reversed(valores)]


@dataclass(frozen=True)
class _Ativo:
    simbolo: str
    especificacao: str
    ultimo: float
    amplitude: float
    frequencia: float
    fase: float
    oferta: float | None  # meia-largura do book no pregão; None = sem ofertas
    pregoes: int = PREGOES
    no_pregao: bool = True


_ATIVOS: Final = (
    _Ativo("PETR4", "PN      N2", 30.00, 0.018, 1.7, 0.0, 0.01),
    _Ativo("PETR3", "ON      N2", 32.00, 0.017, 1.3, 1.0, 0.02),
    _Ativo("VALE3", "ON      NM", 60.00, 0.020, 1.1, 0.5, None),
    _Ativo("ITUB4", "PN      N1", 35.00, 0.015, 0.9, 0.2, 0.02, pregoes=5),
    _Ativo("BBAS3", "ON      NM", 28.00, 0.016, 1.5, 0.3, 0.01, no_pregao=False),
)


@dataclass(frozen=True)
class _Serie:
    simbolo: str
    objeto: str  # ativo-objeto cujo spot entra no prêmio
    tipo: int
    strike: float
    vencimento: date
    especificacao: str = "PN"
    estilo: str | None = "EURO"  # None = ausente do cadastro; "" = sem OptnStyle
    book: str = "completo"  # completo, so_bid, so_ask, vazio_com_negocio, vazio_sem_negocio
    indopc: int = 0
    cruzado: bool = False
    objeto_no_cadastro: str = ""


def _series_petr4() -> list[_Serie]:
    series = [
        _Serie(f"PETRK{int(k * 10)}", "PETR4", _CALL, k, NOVEMBRO, estilo="AMER")
        for k in (27.0, 28.0, 29.0, 31.0, 32.0, 33.0)
    ]
    series += [_Serie("PETRK300", "PETR4", _CALL, 30.0, NOVEMBRO, estilo="EURO")]
    series += [
        _Serie(f"PETRW{int(k * 10)}", "PETR4", _PUT, k, NOVEMBRO)
        for k in (26.0, 27.0, 28.0, 29.0, 30.0, 31.0, 32.0)
    ]
    series += [
        _Serie(f"PETRL{int(k * 10)}", "PETR4", _CALL, k, DEZEMBRO, estilo="EURO")
        for k in (29.0, 30.0, 31.0, 32.0)
    ]
    series += [
        _Serie(f"PETRX{int(k * 10)}", "PETR4", _PUT, k, DEZEMBRO) for k in (28.0, 29.0, 31.0)
    ]
    especiais = {
        "PETRK320": {"book": "so_bid"},
        "PETRK330": {"book": "so_ask"},
        "PETRW260": {"book": "vazio_com_negocio"},
        "PETRW270": {"book": "vazio_sem_negocio"},
    }
    series = [_Serie(**{**s.__dict__, **especiais.get(s.simbolo, {})}) for s in series]
    series += [
        _Serie("PETRX300", "PETR4", _PUT, 30.0, DEZEMBRO, estilo="AMER"),  # put americana
        _Serie("PETRK285", "PETR4", _CALL, 28.5, NOVEMBRO, estilo="AMER", cruzado=True),
        _Serie("PETRK340", "PETR4", _CALL, 34.0, NOVEMBRO, estilo=""),  # sem OptnStyle
        _Serie("PETRK350", "PETR4", _CALL, 35.0, NOVEMBRO, estilo=None),  # ausente do cadastro
        _Serie("PETRW250", "PETR4", _PUT, 25.0, NOVEMBRO, indopc=1),
        _Serie("PETRK360", "PETR4", _CALL, 36.0, NOVEMBRO, especificacao="UNT", estilo="AMER"),
        _Serie(
            "PETRK305",
            "PETR4",
            _CALL,
            30.5,
            NOVEMBRO,
            especificacao="ON",
            estilo="AMER",
            objeto_no_cadastro="PETR4",
        ),
        _Serie("PETRJ300", "PETR4", _CALL, 30.0, VENCIDA, estilo="AMER"),
    ]
    return series


def _series_outros() -> list[_Serie]:
    series = [
        _Serie(
            f"PETRK{int(k * 10) + 2}",
            "PETR3",
            _CALL,
            k,
            NOVEMBRO,
            especificacao="ON",
            estilo="AMER",
        )
        for k in (31.0, 32.0, 33.0)
    ]
    series += [
        _Serie(f"VALEK{int(k * 10)}", "VALE3", _CALL, k, NOVEMBRO, especificacao="ON")
        for k in (56.0, 58.0, 60.0, 62.0, 64.0)
    ]
    series += [
        _Serie(f"VALEW{int(k * 10)}", "VALE3", _PUT, k, NOVEMBRO, especificacao="ON")
        for k in (56.0, 58.0, 60.0, 62.0, 64.0)
    ]
    return [
        _Serie(**{**s.__dict__, "book": "so_bid"}) if s.simbolo == "VALEK640" else s for s in series
    ]


def _premio(serie: _Serie, spot: float) -> float:
    """Prêmio do kernel sob o smile sigma(K) = 0,30 + 0,4·ln(K/F)², ao centavo.

    Série já vencida (só existe para ser rejeitada) recebe um prêmio fixo.
    """
    if serie.vencimento < REFERENCE_SESSION:
        return 0.50
    du = _CALENDARIO.business_days_between(REFERENCE_SESSION, serie.vencimento)
    tau = du / 252.0
    r = math.log(1.0 + CDI)
    forward = spot * math.exp(r * tau)
    sigma = 0.30 + 0.4 * math.log(serie.strike / forward) ** 2
    preco = bs_price(spot, serie.strike, tau, r, sigma, is_call=serie.tipo == _CALL)
    return max(round(preco, 2), 0.02)


def _registro_serie(serie: _Serie, spot: float, *, desvio: float = 0.0) -> str:
    meio = _premio(serie, spot) + desvio
    negocios = 10 + (int(serie.strike * 10) % 7) * 9
    compra, venda, ultimo = round(meio - 0.01, 2), round(meio + 0.01, 2), meio
    if serie.book == "so_bid":
        venda = 0.0
    elif serie.book == "so_ask":
        compra = 0.0
    elif serie.book == "vazio_com_negocio":
        compra = venda = 0.0
        negocios = 3
    elif serie.book == "vazio_sem_negocio":
        compra = venda = ultimo = 0.0
        negocios = 0
    if serie.cruzado:
        compra, venda = round(meio + 0.05, 2), round(meio - 0.05, 2)
    return registro(
        pregao=REFERENCE_SESSION,
        simbolo=serie.simbolo,
        mercado=serie.tipo,
        nome=serie.objeto[:4],
        especificacao=serie.especificacao,
        ultimo=ultimo,
        oferta_compra=compra,
        oferta_venda=venda,
        negocios=negocios,
        quantidade=negocios * 100,
        volume=round(negocios * 100 * ultimo, 2),
        strike=serie.strike,
        indopc=serie.indopc,
        vencimento=serie.vencimento,
        codbdi="78" if serie.tipo == _CALL else "82",
    )


def render() -> tuple[bytes, bytes]:
    """(COTAHIST em cp1252, cadastro CSV em utf-8 com BOM) — bytes idênticos a cada chamada."""
    linhas: list[str] = []
    spots: dict[str, float] = {}
    for ativo in _ATIVOS:
        dias = _pregoes(REFERENCE_SESSION, ativo.pregoes)
        closes = _fechamentos(
            ativo.ultimo, ativo.amplitude, ativo.frequencia, ativo.fase, len(dias)
        )
        for dia, close in zip(dias, closes, strict=True):
            if dia == REFERENCE_SESSION and not ativo.no_pregao:
                continue
            no_pregao = dia == REFERENCE_SESSION
            meia = ativo.oferta if (no_pregao and ativo.oferta is not None) else None
            linhas.append(
                registro(
                    pregao=dia,
                    simbolo=ativo.simbolo,
                    mercado=_A_VISTA,
                    nome=ativo.simbolo[:4],
                    especificacao=ativo.especificacao,
                    ultimo=close,
                    oferta_compra=round(close - meia, 2) if meia else 0.0,
                    oferta_venda=round(close + meia, 2) if meia else 0.0,
                    negocios=5000,
                    quantidade=1_000_000,
                    volume=round(1_000_000 * close, 2),
                )
            )
        spots[ativo.simbolo] = ativo.ultimo
    series = [*_series_petr4(), *_series_outros()]
    for serie in series:
        linhas.append(_registro_serie(serie, spots[serie.objeto]))
    duplicada = _Serie("PETRW315", "PETR4", _PUT, 31.5, NOVEMBRO)
    linhas.append(_registro_serie(duplicada, spots["PETR4"]))
    linhas.append(_registro_serie(duplicada, spots["PETR4"], desvio=0.10))
    cotahist = arquivo(linhas, geracao=REFERENCE_SESSION, ano=2026).encode("cp1252")

    texto = io.StringIO()
    texto.write("Cadastro de Instrumentos (SINTETICO - nao e dado da B3)\r\n")
    texto.write("Data de referencia;2026-10-23\r\n")
    escritor = csv.writer(texto, delimiter=";", lineterminator="\r\n")
    escritor.writerow(
        ["TckrSymb", "Asst", "XprtnDt", "ExrcPric", "OptnStyle", "OptnTp", "UndrlygTckrSymb1"]
    )
    for ativo in _ATIVOS:
        escritor.writerow([ativo.simbolo, ativo.simbolo[:4], "", "", "", "", ""])
    for serie in [*series, duplicada]:
        if serie.estilo is None:
            continue
        escritor.writerow(
            [
                serie.simbolo,
                serie.objeto[:4],
                serie.vencimento.isoformat(),
                f"{serie.strike:.2f}",
                serie.estilo,
                "CALL" if serie.tipo == _CALL else "PUT",
                serie.objeto_no_cadastro,
            ]
        )
    cadastro = texto.getvalue().encode("utf-8-sig")
    return cotahist, cadastro


def build(destino: Path) -> tuple[Path, Path]:
    """Grava os dois arquivos em ``destino`` e devolve (COTAHIST, cadastro)."""
    cotahist, cadastro = render()
    caminho_cotahist = destino / COTAHIST_NAME
    caminho_cadastro = destino / INSTRUMENTS_NAME
    caminho_cotahist.write_bytes(cotahist)
    caminho_cadastro.write_bytes(cadastro)
    return caminho_cotahist, caminho_cadastro


if __name__ == "__main__":
    for caminho in build(Path(__file__).resolve().parent):
        print(caminho)
