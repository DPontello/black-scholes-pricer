"""Registro do Windows em memória, para os testes da ponte — cumpre o ``Registro`` de ``vias``.

O que ele imita: o caminho e o nome do valor não diferenciam maiúscula; ``apagar_arvore`` leva as
subchaves junto; e o ``HKCR`` lido junta, nesta ordem, o ``HKCU`` e o ``HKLM`` (ambos sob
``Software\\Classes\\``) e só depois o que foi gravado direto no ``HKCR``. Com
``hkcr_ve_hkcu=False`` o ``HKCR`` pula o ``HKCU``, como no Wine. Cada visão (32/64 bits) é um
registro à parte. Nada aqui toca o registro de verdade.
"""

from options_ponte.vias import Raiz, Visao

_PREFIXO_CLASSES = "software\\classes\\"


def _chave(caminho: str) -> str:
    return caminho.strip("\\").lower()


def _achar_nome(valores: dict[str, str], nome: str) -> str | None:
    """O nome do valor como foi gravado, sem diferenciar maiúscula."""
    return next((gravado for gravado in valores if gravado.lower() == nome.lower()), None)


class RegistroFalso:
    """Chaves ``(raiz, visao, caminho em minúsculas) -> {nome do valor: valor}``."""

    def __init__(self, *, hkcr_ve_hkcu: bool = True) -> None:
        self.hkcr_ve_hkcu = hkcr_ve_hkcu
        self._chaves: dict[tuple[Raiz, Visao, str], dict[str, str]] = {}

    def ler(self, raiz: Raiz, caminho: str, nome: str, visao: Visao) -> str | None:
        for origem, prefixo in self._origens(raiz):
            valores = self._chaves.get((origem, visao, prefixo + _chave(caminho)))
            if valores is None:
                continue
            gravado = _achar_nome(valores, nome)
            if gravado is not None:
                return valores[gravado]
        return None

    def gravar(self, raiz: Raiz, caminho: str, nome: str, valor: str, visao: Visao) -> None:
        valores = self._chaves.setdefault((raiz, visao, _chave(caminho)), {})
        antigo = _achar_nome(valores, nome)
        if antigo is not None:
            del valores[antigo]
        valores[nome] = valor

    def apagar_arvore(self, raiz: Raiz, caminho: str, visao: Visao) -> None:
        base = _chave(caminho)
        for chave in [
            (r, v, c)
            for (r, v, c) in self._chaves
            if r == raiz and v == visao and (c == base or c.startswith(base + "\\"))
        ]:
            del self._chaves[chave]

    def definir(
        self, raiz: Raiz, caminho: str, valor: str, *, nome: str = "", visao: Visao = 64
    ) -> None:
        """Monta o cenário de um teste; é o ``gravar`` com ``nome=""`` e ``visao=64`` por padrão."""
        self.gravar(raiz, caminho, nome, valor, visao)

    def gravado(self, raiz: Raiz, visao: Visao) -> dict[str, dict[str, str]]:
        """Cópia do que há em ``(raiz, visao)``: ``{caminho em minúsculas: {nome: valor}}``.

        Para o ``HKCR`` é só o que foi gravado direto nele, não a junção que ``ler`` faz.
        """
        return {c: dict(v) for (r, vi, c), v in self._chaves.items() if r == raiz and vi == visao}

    def _origens(self, raiz: Raiz) -> list[tuple[Raiz, str]]:
        """Onde ``ler`` procura, em ordem: ``(raiz de verdade, prefixo do caminho)``."""
        if raiz != "HKCR":
            return [(raiz, "")]
        origens: list[tuple[Raiz, str]] = [("HKCU", _PREFIXO_CLASSES)] if self.hkcr_ve_hkcu else []
        return [*origens, ("HKLM", _PREFIXO_CLASSES), ("HKCR", "")]
