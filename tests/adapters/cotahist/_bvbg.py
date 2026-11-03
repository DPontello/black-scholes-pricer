"""XML BVBG.028 sintético (o Cadastro de Instrumentos da "Pesquisa por pregão" da B3).

Mesma estrutura do arquivo real de 03/11/2026 (``Document > BizFileHdr > Xchg > BizGrp >
Document > Instrm``, um ``BizGrp`` por instrumento), só com os campos que a conversão lê.
Dados inventados: o arquivo real não pode ir para o repositório (termos da B3).
"""

import io
import zipfile
from collections.abc import Mapping, Sequence
from datetime import date

__all__ = ["acao", "opcao", "pacote", "xml_cadastro", "zip_de"]


def _instrumento(id_: str, asst: str, data: date, info: str) -> str:
    return (
        "<Instrm>"
        "<RptParams><ActvtyInd>true</ActvtyInd>"
        f"<RptDtAndTm><Dt>{data.isoformat()}</Dt></RptDtAndTm></RptParams>"
        f"<FinInstrmId><OthrId><Id>{id_}</Id><Tp><Prtry>8</Prtry></Tp></OthrId></FinInstrmId>"
        f"<FinInstrmAttrCmon><Asst>{asst}</Asst><AsstDesc>{asst}</AsstDesc></FinInstrmAttrCmon>"
        f"<InstrmInf>{info}</InstrmInf>"
        "</Instrm>"
    )


def acao(id_: str, ticker: str, asst: str, *, lote: int = 1, data: date | None = None) -> str:
    info = (
        f"<EqtyInf><SctyCtgy>11</SctyCtgy><TckrSymb>{ticker}</TckrSymb>"
        f"<AllcnRndLot>{lote}</AllcnRndLot></EqtyInf>"
    )
    return _instrumento(id_, asst, data or date(2026, 11, 3), info)


def opcao(
    id_: str,
    ticker: str,
    asst: str,
    *,
    tipo: str,
    strike: str,
    estilo: str,
    vencimento: str,
    objeto_id: str,
    lote: int = 100,
    data: date | None = None,
) -> str:
    info = (
        f"<OptnOnEqtsInf><SctyCtgy>7</SctyCtgy><TckrSymb>{ticker}</TckrSymb>"
        f"<ExrcPric>{strike}</ExrcPric><OptnStyle>{estilo}</OptnStyle>"
        f"<XprtnDt>{vencimento}</XprtnDt><OptnTp>{tipo}</OptnTp>"
        f"<UndrlygInstrmId><OthrId><Id>{objeto_id}</Id></OthrId></UndrlygInstrmId>"
        f"<AllcnRndLot>{lote}</AllcnRndLot></OptnOnEqtsInf>"
    )
    return _instrumento(id_, asst, data or date(2026, 11, 3), info)


def xml_cadastro(instrumentos: Sequence[str]) -> bytes:
    grupos = "".join(
        "<BizGrp>"
        '<AppHdr xmlns="urn:iso:std:iso:20022:tech:xsd:head.001.001.01">'
        "<MsgDefIdr>bvmf.100.02</MsgDefIdr></AppHdr>"
        f'<Document xmlns="urn:bvmf.100.02.xsd">{instrumento}</Document>'
        "</BizGrp>"
        for instrumento in instrumentos
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Document xmlns="urn:bvmf.052.01.xsd"><BizFileHdr><Xchg>'
        "<BizGrpDesc><BizGrpDtls><BizGrpTp>BVBG.028.02</BizGrpTp></BizGrpDtls></BizGrpDesc>"
        f"{grupos}</Xchg></BizFileHdr></Document>"
    ).encode()


def zip_de(membros: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in membros.items():
            z.writestr(nome, conteudo)
    return buffer.getvalue()


def pacote(xmls: Mapping[str, bytes]) -> bytes:
    """``pesquisa-pregao.zip``: um ``IN<AAMMDD>.zip`` por pregão, cada um com o seu XML."""
    return zip_de(
        {interno: zip_de({f"BVBG.028.02_{interno[:-4]}.xml": xml}) for interno, xml in xmls.items()}
    )
