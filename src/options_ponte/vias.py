"""As duas vias RTD da ponte e a escolha entre elas a partir do registro.

O Tryd 8 expõe o ``RTDTrading.RtdServer`` (fora do processo, ``tryd.exe``) e o Profit usa o mesmo
CLSID; o Tryd 7 não tem esse servidor e expõe o ``Tryd.RtdServer`` (dentro do processo, via
``mscoree.dll``), com outro formato de tópico. A ponte lê o registro, descobre quem atende cada
um e escolhe a via a cada abertura de sessão. O registro entra por uma interface injetável
(``Registro``): este módulo só usa a stdlib e não importa ``winreg`` nem COM.
"""

import ntpath
import re
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from options_ponte.protocolo import CLSID, PROGID, topico_rtd

__all__ = [
    "CLSID_TRYD7",
    "CODIGOS_TRYD7",
    "MOTIVO_SEM_RTD",
    "MOTIVO_SO_PROFIT",
    "MOTIVO_TRYD7_OUTRA_VISAO",
    "PROGID_TRYD7",
    "VIA_TRYD7",
    "VIA_TRYD8",
    "VISAO_DO_PROCESSO",
    "Raiz",
    "Registro",
    "Via",
    "Visao",
    "arquivo_do_comando",
    "dono_do_rtdtrading",
    "escolher_via",
    "executavel",
    "servidor_do_clsid",
    "tryd7_registrado",
    "valor_da_classe",
]

Raiz = Literal["HKCR", "HKCU", "HKLM"]
Visao = Literal[32, 64]
VISAO_DO_PROCESSO: Final[Visao] = 32 if struct.calcsize("P") == 4 else 64


class Registro(Protocol):
    """O registro do Windows, no que a ponte usa (``RegistroWinreg`` e o falso dos testes)."""

    def ler(self, raiz: Raiz, caminho: str, nome: str, visao: Visao) -> str | None:
        """O valor ``nome`` (``""`` é o padrão) ou ``None`` se a chave ou o valor não existem.

        Valor numérico (DWORD) volta como texto.
        """
        ...

    def gravar(self, raiz: Raiz, caminho: str, nome: str, valor: str, visao: Visao) -> None: ...

    def apagar_arvore(self, raiz: Raiz, caminho: str, visao: Visao) -> None:
        """Apaga a chave e as subchaves; chave ausente não é erro."""
        ...


@dataclass(frozen=True, slots=True)
class Via:
    """Um jeito de falar com o Tryd por RTD: o servidor COM e o formato do tópico."""

    nome: str
    progid: str
    clsid: str
    dentro_do_processo: bool
    montar_topico: Callable[[str, str], tuple[str, ...]]

    def topico(self, ticker: str, campo: str) -> tuple[str, ...]:
        """As strings do ``ConnectData`` para o ativo e o campo (códigos do app)."""
        return self.montar_topico(ticker, campo)


PROGID_TRYD7: Final = "Tryd.RtdServer"
CLSID_TRYD7: Final = "{5209F8A0-88D3-4D20-870C-E0C44DE1C48D}"

# PALPITE: são os códigos do DDE do Tryd 8 (ADR-0008). Confirmar no Tryd 7.5.4 pela lista de
# cotações -> gerar link, e corrigir aqui o que for diferente.
CODIGOS_TRYD7: Final[Mapping[str, str]] = {
    "ULT": "ULT",
    "OCP": "OCP",
    "OVD": "OVD",
    "NEG": "NEG",
    "VOL": "VOL",
    "FEC": "FEC",
    "HOR": "HOR",
    "DAT": "DAT",
}


def _topico_tryd7(ticker: str, campo: str) -> tuple[str, ...]:
    """O tópico do Tryd 7: três strings, ``("COT", "PETR4", "ULT")``."""
    codigo = CODIGOS_TRYD7.get(campo)
    if codigo is None:
        raise ValueError(f"campo {campo!r} sem código no Tryd 7 (CODIGOS_TRYD7)")
    return ("COT", ticker, codigo)


VIA_TRYD8: Final = Via("Tryd 8 (RTDTrading)", PROGID, CLSID, False, topico_rtd)
VIA_TRYD7: Final = Via("Tryd 7 (Tryd.RtdServer)", PROGID_TRYD7, CLSID_TRYD7, True, _topico_tryd7)

MOTIVO_SO_PROFIT: Final = (
    "o RTD RTDTrading desta máquina é o do Profit (profitchart.exe), e o "
    "Tryd.RtdServer do Tryd 7 não está registrado: rode 'PonteTryd.exe registrar' com o Tryd aberto"
)
MOTIVO_SEM_RTD: Final = (
    "nenhum servidor RTD do Tryd registrado (nem o RTDTrading do Tryd 8, nem o "
    "Tryd.RtdServer do Tryd 7): rode 'PonteTryd.exe diagnostico'"
)
MOTIVO_TRYD7_OUTRA_VISAO: Final = (
    "o Tryd.RtdServer está registrado só na visão de {outra} bits, e a "
    "ponte é de {visao} bits: rode 'PonteTryd.exe registrar'"
)

# Onde a escolha procura o servidor de um CLSID, nesta ordem. Um caso só não basta: no Windows
# o HKCR já junta HKCU e HKLM, mas no Wine ele não enxerga o HKCU.
_ORIGENS: Final[tuple[tuple[Raiz, str], ...]] = (
    ("HKCR", ""),
    ("HKCU", "Software\\Classes\\"),
    ("HKLM", "Software\\Classes\\"),
)


def arquivo_do_comando(comando: str) -> str:
    """O executável/DLL de um valor InprocServer32/LocalServer32.

    O valor pode vir com aspas ou sem, com argumentos (``EXCEL.EXE /automation``) e com
    variáveis de ambiente (``%SystemRoot%``).
    """
    texto = ntpath.expandvars(comando.strip())
    if texto.startswith('"'):
        return texto[1:].split('"', 1)[0]
    achado = re.search(r"\.(exe|dll)\b", texto, re.IGNORECASE)
    return texto[: achado.end()] if achado else texto


def executavel(comando: str) -> str:
    """O nome do ``.exe``/``.dll`` de um comando do registro, em minúsculas."""
    return ntpath.basename(arquivo_do_comando(comando)).lower()


def valor_da_classe(registro: Registro, caminho: str, nome: str, visao: Visao) -> str | None:
    """O valor ``nome`` (``""`` é o padrão) de uma chave sob ``Software\\Classes`` (``caminho``).

    Procura em ``HKCR``, ``HKCU`` e ``HKLM``, nesta ordem, e devolve o primeiro valor não vazio
    (ou ``None``).
    """
    for raiz, prefixo in _ORIGENS:
        valor = registro.ler(raiz, f"{prefixo}{caminho}", nome, visao)
        if valor:
            return valor
    return None


def servidor_do_clsid(registro: Registro, clsid: str, visao: Visao) -> str | None:
    """O comando do ``LocalServer32`` do CLSID, senão o do ``InprocServer32`` (ou ``None``)."""
    for servidor in ("LocalServer32", "InprocServer32"):
        comando = valor_da_classe(registro, f"CLSID\\{clsid}\\{servidor}", "", visao)
        if comando:
            return comando
    return None


def dono_do_rtdtrading(registro: Registro, visao: Visao = VISAO_DO_PROCESSO) -> str | None:
    """O executável que atende o ``RTDTrading`` (``tryd.exe``, ``profitchart.exe``...), em
    minúsculas, ou ``None`` se ele não está registrado.

    Procura na visão do processo e, se não houver, na outra: o servidor fora do processo
    (``LocalServer32``) é ativado atravessando as visões.
    """
    outra: Visao = 64 if visao == 32 else 32
    rtdtrading = servidor_do_clsid(registro, CLSID, visao)
    if rtdtrading is None:
        rtdtrading = servidor_do_clsid(registro, CLSID, outra)
    return executavel(rtdtrading) if rtdtrading is not None else None


def tryd7_registrado(registro: Registro, visao: Visao) -> bool:
    """Se o ``Tryd.RtdServer`` está registrado na visão: o servidor do CLSID é o ``mscoree.dll``."""
    servidor = servidor_do_clsid(registro, CLSID_TRYD7, visao)
    return servidor is not None and executavel(servidor) == "mscoree.dll"


def escolher_via(registro: Registro, visao: Visao = VISAO_DO_PROCESSO) -> Via | str:
    """A via a usar, ou o motivo (texto) de nenhuma servir nesta máquina.

    A ordem: o RTDTrading do ``tryd.exe`` (Tryd 8); o ``Tryd.RtdServer`` na visão do processo
    (Tryd 7); o ``Tryd.RtdServer`` só na outra visão; o RTDTrading do Profit; nenhum.

    O dono do RTDTrading é procurado na visão do processo e, se não houver, na outra: o servidor
    fora do processo (``LocalServer32``) é ativado atravessando as visões. O ``Tryd.RtdServer``
    carrega dentro do processo e só vale na visão dele.
    """
    outra: Visao = 64 if visao == 32 else 32
    dono = dono_do_rtdtrading(registro, visao)
    if dono == "tryd.exe":
        return VIA_TRYD8
    if tryd7_registrado(registro, visao):
        return VIA_TRYD7
    if tryd7_registrado(registro, outra):
        return MOTIVO_TRYD7_OUTRA_VISAO.format(outra=outra, visao=visao)
    if dono == "profitchart.exe":
        return MOTIVO_SO_PROFIT
    return MOTIVO_SEM_RTD
