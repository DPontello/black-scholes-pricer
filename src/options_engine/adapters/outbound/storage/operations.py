"""``JsonOperationRepository``: uma operação por arquivo em ``operacoes/`` na pasta do perfil.

Nome ``<AAAA-MM-DD>_<ATIVO>_<id8>.json`` (data de criação), regravado a cada evento com escrita
atômica: um arquivo por operação reduz conflito na nuvem. Arquivo ilegível (JSON quebrado, versão
desconhecida, campo faltando, eventos que o domínio recusa) é listado com o motivo e nunca
sobrescrito.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Final

from options_engine.adapters.outbound.storage.json_files import write_json_atomic
from options_engine.application.ports.outbound import UnreadableFile
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side, StockOrigin
from options_engine.domain.model.errors import (
    DomainError,
    ProfileFolderUnavailableError,
    UnknownRecordError,
    UnreadableRecordError,
)
from options_engine.domain.portfolio.model import (
    Assignment,
    Close,
    Event,
    Exercise,
    Expired,
    LegRef,
    Open,
    Operation,
    OptionLegRef,
    StockLegRef,
)

__all__ = ["JsonOperationRepository"]

_VERSAO: Final = 1
_PASTA: Final = "operacoes"
_ID: Final = re.compile(r"[0-9A-Za-z_-]{8,64}")
_LADO: Final = {Side.BUY: "compra", Side.SELL: "venda"}
_ESTILO: Final = {ExerciseStyle.AMERICAN: "americana", ExerciseStyle.EUROPEAN: "europeia"}


def _inverso(mapa: dict[Any, str]) -> dict[str, Any]:
    return {texto: valor for valor, texto in mapa.items()}


_LADO_DO_TEXTO: Final = _inverso(_LADO)
_ESTILO_DO_TEXTO: Final = _inverso(_ESTILO)


class JsonOperationRepository:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def list(self) -> tuple[Operation | UnreadableFile, ...]:
        pasta = self._folder / _PASTA
        if not pasta.is_dir():
            return ()
        itens: list[Operation | UnreadableFile] = []
        for caminho in sorted(pasta.glob("*.json")):
            try:
                itens.append(_ler(caminho))
            except UnreadableRecordError as erro:
                itens.append(UnreadableFile(str(caminho), str(erro)))
        return tuple(itens)

    def save(self, operation: Operation) -> None:
        if not self._folder.is_dir():
            raise ProfileFolderUnavailableError(
                f"pasta do perfil fora do ar: {self._folder} (a nuvem está montada?)"
            )
        caminho = self._folder / _PASTA / _nome(operation)
        if caminho.exists():
            try:
                _ler(caminho)
            except UnreadableRecordError as erro:
                raise UnreadableRecordError(
                    f"não regravo um arquivo ilegível, confira-o antes: {erro}"
                ) from erro
        caminho.parent.mkdir(exist_ok=True)
        write_json_atomic(caminho, _para_json(operation))

    def load(self, operation_id: str) -> Operation:
        if _ID.fullmatch(operation_id):
            for caminho in sorted((self._folder / _PASTA).glob(f"*_{operation_id[:8]}.json")):
                operacao = _ler(caminho)
                if operacao.id == operation_id:
                    return operacao
        raise UnknownRecordError(f"operação desconhecida: {operation_id!r}")


def _nome(operation: Operation) -> str:
    if not _ID.fullmatch(operation.id):
        raise UnknownRecordError(f"id de operação inválido: {operation.id!r}")
    return f"{operation.created_on.isoformat()}_{operation.underlying}_{operation.id[:8]}.json"


def _perna_json(perna: LegRef) -> dict[str, object]:
    if isinstance(perna, StockLegRef):
        return {"tipo": "acao", "ticker": perna.symbol, "origem": perna.origin.value}
    termos = perna.terms
    return {
        "tipo": "opcao",
        "ticker": perna.symbol,
        "opcao": {
            "tipo": termos.option_type.value,
            "strike": termos.strike,
            "vencimento": termos.expiry.isoformat(),
            "estilo": _ESTILO[termos.exercise_style],
        },
    }


def _evento_json(evento: Event) -> dict[str, object]:
    base: dict[str, object] = {"perna": evento.leg, "data": evento.on.isoformat()}
    match evento:
        case Open():
            return {
                "tipo": "abertura",
                **base,
                "lado": _LADO[evento.side],
                "quantidade": evento.quantity,
                "preco": evento.price,
                "custos": evento.costs,
            }
        case Close():
            corpo = {
                "tipo": "encerramento",
                **base,
                "quantidade": evento.quantity,
                "preco": evento.price,
                "custos": evento.costs,
            }
            if evento.cost_basis is not None:
                corpo["custo_medio"] = evento.cost_basis
            return corpo
        case Exercise() | Assignment():
            tipo = "exercicio" if isinstance(evento, Exercise) else "atribuicao"
            return {"tipo": tipo, **base, "quantidade": evento.quantity, "custos": evento.costs}
        case Expired():
            return {"tipo": "po", **base}


def _para_json(operation: Operation) -> dict[str, object]:
    return {
        "versao": _VERSAO,
        "id": operation.id,
        "ativo": operation.underlying,
        "nome": operation.name,
        "criada_em": operation.created_on.isoformat(),
        "pernas": [_perna_json(p) for p in operation.legs],
        "eventos": [_evento_json(e) for e in operation.events],
    }


def _perna(dados: Any, ativo: str) -> LegRef:
    if dados["tipo"] == "acao":
        return StockLegRef(str(dados["ticker"]), StockOrigin(dados["origem"]))
    opcao = dados["opcao"]
    return OptionLegRef(
        str(dados["ticker"]),
        OptionTerms(
            underlying=ativo,
            strike=float(opcao["strike"]),
            expiry=date.fromisoformat(opcao["vencimento"]),
            option_type=OptionType(opcao["tipo"]),
            exercise_style=_ESTILO_DO_TEXTO[opcao["estilo"]],
        ),
    )


def _custos(valor: Any) -> float | None:
    return None if valor is None else float(valor)


def _evento(dados: Any) -> Event:
    perna, dia = int(dados["perna"]), date.fromisoformat(dados["data"])
    match dados["tipo"]:
        case "abertura":
            return Open(
                perna,
                dia,
                _LADO_DO_TEXTO[dados["lado"]],
                int(dados["quantidade"]),
                float(dados["preco"]),
                _custos(dados["custos"]),
            )
        case "encerramento":
            return Close(
                perna,
                dia,
                int(dados["quantidade"]),
                float(dados["preco"]),
                _custos(dados["custos"]),
                _custos(dados.get("custo_medio")),
            )
        case "exercicio":
            return Exercise(perna, dia, int(dados["quantidade"]), _custos(dados["custos"]))
        case "atribuicao":
            return Assignment(perna, dia, int(dados["quantidade"]), _custos(dados["custos"]))
        case "po":
            return Expired(perna, dia)
    raise ValueError(f"tipo de evento desconhecido: {dados['tipo']!r}")


def _ler(caminho: Path) -> Operation:
    try:
        dados: Any = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise UnreadableRecordError(f"{caminho}: JSON ilegível ({erro})") from erro
    if not isinstance(dados, dict):
        raise UnreadableRecordError(f"{caminho}: JSON ilegível (não é um objeto)")
    if dados.get("versao") != _VERSAO:
        raise UnreadableRecordError(f"{caminho}: versão {dados.get('versao')!r} desconhecida")
    try:
        ativo = str(dados["ativo"])
        return Operation(
            id=str(dados["id"]),
            underlying=ativo,
            name=str(dados["nome"]),
            created_on=date.fromisoformat(dados["criada_em"]),
            legs=tuple(_perna(p, ativo) for p in dados["pernas"]),
            events=tuple(_evento(e) for e in dados["eventos"]),
        )
    except (KeyError, TypeError, ValueError) as erro:
        raise UnreadableRecordError(f"{caminho}: campo faltando ou inválido ({erro!r})") from erro
    except DomainError as erro:
        raise UnreadableRecordError(f"{caminho}: {erro}") from erro
