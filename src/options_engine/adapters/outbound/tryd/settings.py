"""Constantes do adapter ao vivo do Tryd — fonte única no app.

As da ponte (porta, limite de tópicos, campos) moram em ``options_ponte.protocolo``, que
a ponte e o app compartilham; aqui são reexportadas. O que é só do app fica definido aqui.
"""

from options_ponte.protocolo import CAMPOS_ATIVO, CAMPOS_OPCAO, LIMITE_TOPICOS, PORTA_PONTE

__all__ = [
    "CAMPOS_ATIVO",
    "CAMPOS_OPCAO",
    "FAIXA_STRIKES",
    "LIMITE_TOPICOS",
    "PONTE_ATRASADA_S",
    "PONTE_PERDIDA_S",
    "PORTA_PONTE",
    "TEMPO_CARGA_S",
    "VENCIMENTOS_PADRAO",
]

# Depois da assinatura, o RTD manda zeros até o Tryd carregar o tópico (~1 s). Passado este
# tempo sem nenhuma atualização, o ativo conta como carregado: o lado sem oferta é lado vazio.
TEMPO_CARGA_S = 3.0

# Idade da última mensagem da ponte: abaixo de ATRASADA a conexão está boa; até PERDIDA está
# atrasada; depois disso, desconectada (o app cai para o fim de dia).
PONTE_ATRASADA_S = 10.0
PONTE_PERDIDA_S = 30.0

# Strikes assinados: até FAIXA_STRIKES (fração) acima ou abaixo do spot.
FAIXA_STRIKES = 0.20
# Quantos vencimentos (a partir de hoje) entram na cadeia assinada.
VENCIMENTOS_PADRAO = 2
