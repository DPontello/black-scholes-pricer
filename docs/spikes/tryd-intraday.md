# Spike — Tryd como fonte intraday (RTD/DDE)

Objetivo: decidir se o Tryd alimenta o `OptionChainPort` em tempo real, e como.
Resultado esperado: a [ADR-0008](../adr/0008-intraday-tryd-rtd.md) sai de
"proposta" para "aceita" (ou é descartada) com as respostas abaixo.
Timebox: **1 pregão** de verificação, mais o tempo de rodar a prova de conceito.

O que já se sabe (central de ajuda e blog do Tryd, e um blog de terceiros de 2017):

- O Tryd tem servidor RTD (`tryd.rtdserver`) e DDE, ligados em
  **Arquivo > Ativar DDE e RTD**; o RTD exige rodar o Tryd **como
  administrador** e usa uma DLL do Windows.
- Fórmula RTD: `=RTD("tryd.rtdserver";;"COT";ATIVO;CAMPO)`; campos do tipo
  `COT` em 2017: `Ult`, `PrcCpa`, `PrcVda`, `QtdNeg`, `Vol`, `DataHora`,
  `Exerc`, `Expir`, `DiaUtExp`, `Estado`, `Desc`. Book em `LVL2`.
- No Monitor de Cotações, **Mais > Gerar Links RTD** gera as fórmulas reais
  da versão instalada — é a fonte de verdade dos nomes de campo.

## Roteiro no seu Tryd

Anote as respostas na tabela de resultados no fim deste arquivo.

### A. Ambiente (fora do pregão serve)

1. Versão do Tryd, plano contratado e se o plano inclui **opções em tempo
   real com book** (não só ações).
2. Windows e Office: Excel de **32 ou 64 bits** (Arquivo > Conta > Sobre o Excel).
3. Com o Tryd aberto como administrador e o RTD ativado, rode o diagnóstico
   (instruções da prova de conceito abaixo) e copie a saída. Ele mostra se o
   servidor RTD é DLL ou EXE e de quantos bits: uma DLL de 32 bits não carrega
   num Python de 64 bits — o adapter teria de usar Python de 32 bits ou o
   Excel como ponte.
   Rode o `diagnostico` e o `rtd` primeiro num terminal **comum**. Se o
   `rtd` falhar com acesso negado ou falha de execução do servidor,
   repita num terminal **como administrador**: o Tryd roda elevado e o
   COM não atravessa níveis de integridade. Anote qual funcionou.

### B. Campos de uma opção (durante o pregão)

4. Abra um Monitor de Cotações com PETR4 e 5 a 10 opções de PETR4 do mês
   (calls e puts, dentro e fora do dinheiro, ao menos uma pouco negociada) e
   use **Mais > Gerar Links RTD**. Guarde as fórmulas geradas.
5. No Excel, confira para uma opção: `Ult`, `PrcCpa`, `PrcVda`, `QtdNeg`,
   `Vol`, `DataHora`, `Exerc`, `Expir`, `DiaUtExp`, `Estado`. Para cada um:
   o nome atual do campo, o formato (número ou texto com vírgula) e um valor
   de exemplo.
6. **Volume:** `Vol` é quantidade ou financeiro? Existe um campo de volume
   **financeiro** (o domínio exige financeiro, ADR-0003)?
7. **Lado vazio:** numa opção sem oferta de compra ou de venda, o que vem em
   `PrcCpa`/`PrcVda` — zero, célula vazia, traço ou erro? (A regra é: lado
   ausente vira `None`, nunca zero — ADR-0003.)
8. **Book:** `=RTD("tryd.rtdserver";;"LVL2";ATIVO;"0";"0";"2")` e `"3"` batem
   com `PrcCpa` e `PrcVda`?
9. Algum campo traz o **estilo de exercício** (americana/europeia) ou o
   ativo-objeto da série? (Sem isso, o Cadastro de Instrumentos continua
   obrigatório — esperado.)
10. `Exerc` é o strike já ajustado por proventos?

### C. Comportamento

11. **Cadência:** com a prova de conceito, capture 60 s em pleno pregão
    (comando `rtd` abaixo) e compare com a tela do Tryd: quantas
    atualizações, e com que atraso aparente?
12. **Escala:** repita com 50 séries x 5 campos (250 tópicos). O Tryd ou o
    Python ficam lentos? Há limite de tópicos?
13. **Fora do pregão:** depois do fechamento, o que vem em `Ult`, ofertas e
    `Estado`? (Decide como o painel trata o pós-fechamento.)
14. **Queda:** feche o Tryd com a captura rodando. O que o Python recebe
    (erro, `Disconnect`, valores congelados)?
15. **DDE:** os links gerados também têm formato DDE (`servico|topico!item`)?
    Se sim, teste o comando `dde` com o serviço e o tópico deles.

### D. Termos e custo

16. Os termos de uso do Tryd e da corretora permitem capturar cotações por
    automação para **uso pessoal**? (Não redistribuímos dados da B3: capturas
    reais não entram no repositório.)
17. Custo mensal do plano com opções em tempo real.

## Prova de conceito

`tools/tryd_spike/tryd_poc.py` — só Windows, com `pywin32` num venv separado
(ele NÃO é dependência do projeto). Da raiz do repositório:

```bash
python -m venv .venv-tryd
.venv-tryd/Scripts/pip install pywin32
```

```bash
.venv-tryd/Scripts/python tools/tryd_spike/tryd_poc.py diagnostico
```

```bash
.venv-tryd/Scripts/python tools/tryd_spike/tryd_poc.py autoteste
```

```bash
.venv-tryd/Scripts/python tools/tryd_spike/tryd_poc.py rtd --ativos PETR4,PETRK300 --segundos 60 --saida captura.json
```

```bash
.venv-tryd/Scripts/python tools/tryd_spike/tryd_poc.py dde --servico SERVICO --topico TOPICO --itens ITEM1,ITEM2
```

- `diagnostico` só lê o registro do Windows: ProgID, arquivo do servidor RTD
  e a arquitetura dele, bitness do Python, type library do Excel, Tryd rodando.
- `autoteste` valida o cliente RTD contra um servidor falso, sem Tryd — já
  passou no ambiente de desenvolvimento (Python 3.14 64 bits, Excel 1.9).
- `rtd` grava cada valor **cru** (tipo e `repr`), para responder às perguntas
  5 a 7 sem adivinhar conversões. Troque `PETRK300` por tickers reais do mês;
  `--campos` aceita outros nomes, se os links gerados mostrarem nomes novos.
- O `.venv-tryd/` e a `captura.json` não vão para o git (veja o `.gitignore`).

## Resultados (preencher)

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Versão, plano, opções com book em tempo real? | |
| 2 | Excel 32 ou 64 bits | |
| 3 | Servidor RTD: DLL/EXE, bits (saída do `diagnostico`); terminal comum ou administrador | |
| 5 | Campos e formatos de uma opção | |
| 6 | Volume financeiro: campo | |
| 7 | Lado vazio chega como | |
| 8 | LVL2 bate com PrcCpa/PrcVda? | |
| 9 | Estilo de exercício no Tryd? | |
| 10 | `Exerc` ajustado por proventos? | |
| 11 | Cadência e atraso (60 s) | |
| 12 | 250 tópicos: desempenho | |
| 13 | Fora do pregão | |
| 14 | Tryd fechado durante a captura | |
| 15 | DDE: serviço, tópico, funciona? | |
| 16 | Termos de uso | |
| 17 | Custo | |
