"""``JsonSimulationRepository``: ``simulacoes/<id>.json`` na pasta do perfil, um por simulação.

Arquivo ilegível (JSON quebrado, versão desconhecida, campo faltando) é listado com o motivo e
nunca apagado nem sobrescrito: é dado do usuário, talvez editado à mão ou a meio da nuvem.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from options_engine.adapters.outbound.storage.json_files import write_json_atomic
from options_engine.application.ports.inbound import (
    BuilderLegInput,
    BuilderRequest,
    BuilderStockInput,
)
from options_engine.application.ports.simulations import SavedSimulation, UnreadableFile
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import (
    DomainError,
    ProfileFolderUnavailableError,
    UnknownRecordError,
    UnreadableRecordError,
)

__all__ = ["JsonSimulationRepository"]

_VERSAO: Final = 1
_PASTA: Final = "simulacoes"
_ID: Final = re.compile(r"[0-9A-Za-z_-]{1,64}")
_LADO: Final = {Side.BUY: "compra", Side.SELL: "venda"}
_LADO_DO_TEXTO: Final = {texto: lado for lado, texto in _LADO.items()}


class JsonSimulationRepository:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def list(self) -> tuple[SavedSimulation | UnreadableFile, ...]:
        pasta = self._folder / _PASTA
        if not pasta.is_dir():
            return ()
        itens: list[SavedSimulation | UnreadableFile] = []
        for caminho in sorted(pasta.glob("*.json")):
            try:
                itens.append(_ler(caminho))
            except UnreadableRecordError as erro:
                itens.append(UnreadableFile(str(caminho), str(erro)))
        return tuple(itens)

    def save(self, simulation: SavedSimulation) -> None:
        if not self._folder.is_dir():
            raise ProfileFolderUnavailableError(
                f"pasta do perfil fora do ar: {self._folder} (a nuvem está montada?)"
            )
        pasta = self._folder / _PASTA
        pasta.mkdir(exist_ok=True)
        write_json_atomic(self._caminho(simulation.id), _para_json(simulation))

    def load(self, simulation_id: str) -> SavedSimulation:
        return _ler(self._existente(simulation_id))

    def delete(self, simulation_id: str) -> None:
        self._existente(simulation_id).unlink()

    def _caminho(self, simulation_id: str) -> Path:
        if not _ID.fullmatch(simulation_id):
            raise UnknownRecordError(f"simulação desconhecida: {simulation_id!r}")
        return self._folder / _PASTA / f"{simulation_id}.json"

    def _existente(self, simulation_id: str) -> Path:
        caminho = self._caminho(simulation_id)
        if not caminho.is_file():
            raise UnknownRecordError(f"simulação desconhecida: {simulation_id!r}")
        return caminho


def _para_json(simulation: SavedSimulation) -> dict[str, object]:
    pedido = simulation.request
    acao = pedido.stock
    return {
        "versao": _VERSAO,
        "id": simulation.id,
        "nome": simulation.name,
        "criada_em": simulation.created_at.isoformat(),
        "ativo": pedido.underlying,
        "modelo": pedido.template,
        "pernas": [
            {"ticker": p.symbol, "lado": _LADO[p.side], "quantidade": p.quantity, "preco": p.price}
            for p in pedido.legs
        ],
        "acao": None
        if acao is None
        else {
            "lado": _LADO[acao.side],
            "quantidade": acao.quantity,
            "origem": acao.origin.value,
            "preco": acao.price,
        },
    }


def _ler(caminho: Path) -> SavedSimulation:
    try:
        dados: Any = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise UnreadableRecordError(f"{caminho}: JSON ilegível ({erro})") from erro
    if not isinstance(dados, dict):
        raise UnreadableRecordError(f"{caminho}: JSON ilegível (não é um objeto)")
    if dados.get("versao") != _VERSAO:
        raise UnreadableRecordError(f"{caminho}: versão {dados.get('versao')!r} desconhecida")
    try:
        acao = dados["acao"]
        return SavedSimulation(
            id=str(dados["id"]),
            name=str(dados["nome"]),
            created_at=datetime.fromisoformat(dados["criada_em"]),
            request=BuilderRequest(
                underlying=str(dados["ativo"]),
                legs=tuple(
                    BuilderLegInput(
                        str(p["ticker"]),
                        _LADO_DO_TEXTO[p["lado"]],
                        int(p["quantidade"]),
                        None if p["preco"] is None else float(p["preco"]),
                    )
                    for p in dados["pernas"]
                ),
                stock=None
                if acao is None
                else BuilderStockInput(
                    _LADO_DO_TEXTO[acao["lado"]],
                    int(acao["quantidade"]),
                    StockOrigin(acao["origem"]),
                    None if acao["preco"] is None else float(acao["preco"]),
                ),
                template=None if dados["modelo"] is None else str(dados["modelo"]),
            ),
        )
    except (KeyError, TypeError, ValueError, DomainError) as erro:
        raise UnreadableRecordError(f"{caminho}: campo faltando ou inválido ({erro!r})") from erro
