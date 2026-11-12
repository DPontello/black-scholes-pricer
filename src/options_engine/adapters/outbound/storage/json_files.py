"""Escrita atômica de JSON — o arquivo ou está inteiro, ou é o anterior.

Os arquivos do usuário vivem em pastas sincronizadas (nuvem, pendrive): uma
escrita interrompida no meio deixaria um JSON truncado que o sincronizador
espalharia para o outro PC. Por isso grava num ``*.tmp`` ao lado e troca com
``os.replace``, que é atômico no mesmo volume.
"""

import contextlib
import json
import os
from pathlib import Path

__all__ = ["write_json_atomic"]


def write_json_atomic(path: Path, data: object) -> None:
    """Grava ``data`` em ``path`` (UTF-8, indentado) sem passar por estado parcial.

    ``allow_nan=False``: NaN/Infinity não são JSON e outro leitor (ou a edição
    à mão) recusaria o arquivo — falha na gravação, não na leitura. Em qualquer
    falha o temporário é apagado (se nem isso der, o erro original é o que
    sobe) e o arquivo anterior segue intacto.
    """
    temporario = path.with_name(path.name + ".tmp")
    try:
        with temporario.open("w", encoding="utf-8") as arquivo:
            json.dump(data, arquivo, ensure_ascii=False, indent=2, allow_nan=False)
            arquivo.write("\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, path)
    except BaseException:
        with contextlib.suppress(OSError):
            temporario.unlink(missing_ok=True)
        raise
