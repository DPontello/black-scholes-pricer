"""Ponte do Tryd — lê cotações por RTD e as entrega ao app por TCP local (JSON por linha).

Processo separado do app: roda no Python do Windows (nativo, ou dentro do Wine no
Linux). Os módulos deste pacote, exceto ``rtd``, são só stdlib e importam em qualquer
sistema; a camada COM (pywin32) fica isolada em ``rtd``.
"""
