"""Registro dos tópicos assinados — o ``id`` de cada um para o ``ConnectData`` do RTD."""

from collections.abc import Iterable

__all__ = ["LimiteDeTopicos", "RegistroDeTopicos"]


class LimiteDeTopicos(Exception):
    """O lote passaria do limite de tópicos simultâneos da ponte."""


class RegistroDeTopicos:
    """Tópicos ``(ticker, campo)`` assinados, cada um com um id inteiro único.

    O id vai ao ``ConnectData`` e volta no ``RefreshData``; por isso nunca é reaproveitado
    depois de um ``remover``, para uma atualização atrasada do tópico antigo não cair no novo.
    """

    def __init__(self, limite: int) -> None:
        self._limite = limite
        self._ids: dict[tuple[str, str], int] = {}
        self._topicos: dict[int, tuple[str, str]] = {}
        self._ultimo_id = 0

    @property
    def total(self) -> int:
        return len(self._ids)

    def adicionar(
        self, topicos: Iterable[tuple[str, str]]
    ) -> tuple[tuple[int, tuple[str, str]], ...]:
        """Registra os tópicos ainda não assinados e devolve ``(id, tópico)`` de cada novo.

        Tudo ou nada: se o lote passar do limite, nenhum tópico dele é registrado.
        """
        novos = tuple(dict.fromkeys(t for t in topicos if t not in self._ids))
        if self.total + len(novos) > self._limite:
            raise LimiteDeTopicos(
                f"limite de tópicos excedido: {self.total} assinados + {len(novos)} novos "
                f"> {self._limite}"
            )
        registrados = []
        for topico in novos:
            self._ultimo_id += 1
            self._ids[topico] = self._ultimo_id
            self._topicos[self._ultimo_id] = topico
            registrados.append((self._ultimo_id, topico))
        return tuple(registrados)

    def remover(self, topicos: Iterable[tuple[str, str]]) -> tuple[int, ...]:
        """Esquece os tópicos assinados e devolve os ids, para o ``DisconnectData``."""
        removidos = []
        for topico in topicos:
            id_ = self._ids.pop(topico, None)
            if id_ is not None:
                del self._topicos[id_]
                removidos.append(id_)
        return tuple(removidos)

    def topico(self, id_: int) -> tuple[str, str] | None:
        return self._topicos.get(id_)

    def assinados(self) -> tuple[tuple[int, tuple[str, str]], ...]:
        """``(id, tópico)`` de cada assinado, na ordem em que entraram."""
        return tuple(self._topicos.items())
