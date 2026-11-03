"""Cadastro de Instrumentos no XML da "Pesquisa por pregão" da B3, convertido no CSV.

O site entrega o cadastro do pregão como ``pesquisa-pregao.zip``: dentro, um ``IN<AAMMDD>.zip``
com o XML ``BVBG.028.02_*.xml`` (centenas de MB). A conversão lê o XML em fluxo e devolve o
CSV que ``load_instruments`` já lê, só com as ações e as opções sobre ações; o resto do app
não muda. Vale também o ZIP com o XML direto (o ``IN<AAMMDD>.zip`` tirado do pacote).

No XML, o ``Asst`` da opção é só a raiz (``PETR``): o ativo-objeto vem do ``UndrlygInstrmId``,
que é o id da ação no próprio arquivo, e vai para ``UndrlygTckrSymb1``. Id fora do arquivo
deixa a coluna vazia, e vale a regra de raiz do ticker.
"""

import contextlib
import csv
import io
import zipfile
import zlib
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import IO, Final
from xml.etree import ElementTree

from options_engine.adapters.outbound.cotahist.errors import InstrumentsFileError

__all__ = ["instruments_csv_from_xml_package", "is_instruments_xml_package"]

_ASSINATURA: Final = b"BVBG.028"
# A assinatura está no cabeçalho do arquivo, antes do primeiro instrumento.
_CABECA_BYTES: Final = 4096
_COLUNAS: Final = (
    "TckrSymb",
    "Asst",
    "OptnTp",
    "ExrcPric",
    "XprtnDt",
    "OptnStyle",
    "AllcnRndLot",
    "UndrlygTckrSymb1",
)
_ACAO: Final = "EqtyInf"
_OPCAO: Final = "OptnOnEqtsInf"
_ERROS_ZIP: Final = (zipfile.BadZipFile, NotImplementedError, RuntimeError, zlib.error, EOFError)


def is_instruments_xml_package(content: bytes) -> bool:
    """ZIP com um XML BVBG.028, direto ou num ZIP dentro dele."""
    try:
        with contextlib.ExitStack() as pilha:
            pacote = pilha.enter_context(zipfile.ZipFile(io.BytesIO(content)))
            return _localizar(pacote, pilha) is not None
    except _ERROS_ZIP:
        return False


def instruments_csv_from_xml_package(path: Path) -> tuple[date | None, str]:
    """``(data do pregão, CSV)`` do XML mais recente do pacote, pelo nome."""
    try:
        with contextlib.ExitStack() as pilha:
            pacote = pilha.enter_context(zipfile.ZipFile(path))
            achado = _localizar(pacote, pilha)
            if achado is None:
                raise InstrumentsFileError(path, None, "nenhum XML BVBG.028 no pacote")
            zip_do_xml, membro = achado
            with zip_do_xml.open(membro) as xml:
                data, linhas = _ler(xml)
    except ElementTree.ParseError as erro:
        raise InstrumentsFileError(path, None, f"XML ilegível ({erro})") from erro
    except _ERROS_ZIP as erro:
        raise InstrumentsFileError(path, None, f"ZIP ilegível ({erro})") from erro
    except OSError as erro:
        raise InstrumentsFileError(path, None, f"não foi possível ler o arquivo: {erro}") from erro
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(_COLUNAS)
    escritor.writerows(linhas)
    return data, saida.getvalue()


def _localizar(
    pacote: zipfile.ZipFile, pilha: contextlib.ExitStack
) -> tuple[zipfile.ZipFile, str] | None:
    achados: list[tuple[str, zipfile.ZipFile, str]] = []
    for membro in pacote.namelist():
        if membro.upper().endswith(".XML"):
            if _e_cadastro(pacote, membro):
                achados.append((membro, pacote, membro))
        elif membro.upper().endswith(".ZIP"):
            try:
                interno = pilha.enter_context(zipfile.ZipFile(io.BytesIO(pacote.read(membro))))
            except zipfile.BadZipFile:
                continue
            achados.extend(
                (f"{membro}/{m}", interno, m)
                for m in interno.namelist()
                if m.upper().endswith(".XML") and _e_cadastro(interno, m)
            )
    if not achados:
        return None
    # IN<AAMMDD>.zip: o maior nome é o pregão mais recente.
    _, zip_do_xml, membro = max(achados, key=lambda achado: achado[0])
    return zip_do_xml, membro


def _e_cadastro(pacote: zipfile.ZipFile, membro: str) -> bool:
    with pacote.open(membro) as xml:
        return _ASSINATURA in xml.read(_CABECA_BYTES)


def _ler(xml: IO[bytes]) -> tuple[date | None, list[tuple[str, ...]]]:
    data: date | None = None
    tickers_por_id: dict[str, str] = {}
    acoes: list[tuple[str, ...]] = []
    opcoes: list[tuple[tuple[str, ...], str]] = []
    for instrumento in _instrumentos(xml):
        info = instrumento.find("{*}InstrmInf")
        detalhe = info[0] if info is not None and len(info) else None
        if detalhe is None or _local(detalhe.tag) not in (_ACAO, _OPCAO):
            continue
        ticker = _texto(detalhe, "TckrSymb")
        if not ticker:
            continue
        if data is None:
            dia = _texto(instrumento, "RptParams/RptDtAndTm/Dt")
            with contextlib.suppress(ValueError):
                data = date.fromisoformat(dia)
        asst = _texto(instrumento, "FinInstrmAttrCmon/Asst")
        lote = _texto(detalhe, "AllcnRndLot")
        if _local(detalhe.tag) == _ACAO:
            tickers_por_id[_texto(instrumento, "FinInstrmId/OthrId/Id")] = ticker
            acoes.append((ticker, asst, "", "", "", "", lote))
            continue
        termos = tuple(_texto(detalhe, c) for c in ("OptnTp", "ExrcPric", "XprtnDt", "OptnStyle"))
        opcoes.append(((ticker, asst, *termos, lote), _texto(detalhe, "UndrlygInstrmId/OthrId/Id")))
    # O ativo-objeto pode vir antes ou depois da opção no arquivo.
    linhas = [(*acao, "") for acao in acoes]
    linhas.extend((*opcao, tickers_por_id.get(objeto, "")) for opcao, objeto in opcoes)
    return data, linhas


def _instrumentos(xml: IO[bytes]) -> Iterator[ElementTree.Element]:
    """Cada ``Instrm`` do arquivo, soltando o ``BizGrp`` lido para a memória não crescer."""
    abertos: list[ElementTree.Element] = []
    for evento, elemento in ElementTree.iterparse(xml, events=("start", "end")):
        if evento == "start":
            abertos.append(elemento)
            continue
        abertos.pop()
        nome = _local(elemento.tag)
        if nome == "Instrm":
            yield elemento
        elif nome == "BizGrp" and abertos:
            abertos[-1].remove(elemento)


def _texto(elemento: ElementTree.Element, caminho: str) -> str:
    achado = elemento.find("/".join(f"{{*}}{parte}" for parte in caminho.split("/")))
    return "" if achado is None or achado.text is None else achado.text.strip()


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]
