"""Cotações ao vivo do Tryd: quadro, cliente da ponte e lançador da ponte.

A ponte (``options_ponte``) é um processo à parte; este pacote só fala com ela por TCP
local e a mantém no ar. Só stdlib mais o protocolo da ponte (também stdlib).
"""

from options_engine.adapters.outbound.tryd.board import LiveBoard, RawValue
from options_engine.adapters.outbound.tryd.client import BridgeHealth, TrydBridgeClient
from options_engine.adapters.outbound.tryd.launcher import BridgeProcess, default_bridge_command

__all__ = [
    "BridgeHealth",
    "BridgeProcess",
    "LiveBoard",
    "RawValue",
    "TrydBridgeClient",
    "default_bridge_command",
]
