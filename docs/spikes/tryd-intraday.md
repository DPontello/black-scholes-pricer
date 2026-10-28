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
    (erro, `Disconnect`, valores congelados)? A captura deve registrar
    `servidor_perdido`. Se o servidor RTD for DLL (pergunta 3), quem
    responde ao Heartbeat é a DLL dentro do próprio Python: confira se ela
    percebe a saída do Tryd.
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
- `autoteste` valida o cliente RTD contra um servidor falso, sem Tryd:
  primeiro no mesmo processo, depois noutro processo que morre no meio da
  captura (tem de ser detectado).
- `rtd` grava cada valor **cru** (tipo e `repr`), para responder às perguntas
  5 a 7 sem adivinhar conversões. Troque `PETRK300` por tickers reais do mês;
  `--campos` aceita outros nomes, se os links gerados mostrarem nomes novos.
  Se o servidor some (pergunta 14), a captura registra `servidor_perdido` e o
  comando sai com código 1.
- `dde` devolve cada item como texto cru; item que não existe vira
  `{"erro": ...}` sem derrubar os outros.
- O `.venv-tryd/` e a `captura.json` não vão para o git (veja o `.gitignore`).

## Teste sem Tryd (2026-10-27)

Feito na máquina de desenvolvimento, **sem Tryd instalado**: Windows 11,
Python 3.14.5 64 bits, pywin32 312, Microsoft 365 com Excel 16.0 de 64 bits
(type library 1.9). Valida a ferramenta e o encanamento COM/DDE, não o Tryd.

| Teste | Resultado |
|---|---|
| Venv e `pip install pywin32` como nas instruções acima | ok; `.venv-tryd/` fica fora do git |
| `diagnostico` | ProgID `tryd.rtdserver` ausente (esperado); type library do Excel 1.9 |
| `diagnostico` com ProgID trocado no código (só no teste) | `Excel.Application`: EXE 64 bits; `Scripting.FileSystemObject`: DLL 64 bits e DLL 32 bits, uma em cada visão do registro |
| `autoteste` no mesmo processo | ok: valor inicial, UpdateNotify, RefreshData, parâmetros ByRef |
| `autoteste` entre processos | ok: 3 atualizações; servidor morto detectado por Heartbeat cerca de 1 s após o silêncio |
| `rtd` sem Tryd | erro limpo ("cadeia de caracteres de classe inválida"), código 1 |
| `dde` sem Tryd | erro limpo ("ConnectTo failed"), código 1 |
| `dde` contra o Excel (servidor DDE real, instância só do teste) | ok. Tudo chega como **texto** terminado em CR LF: número `"12.34"`, texto pt-BR `"12,34"`, célula vazia `""`, traço `"-"`, erro `"#DIV/0!"`. O item segue o idioma do Excel (`R1C1` no inglês; `L1C1` falhou) |

Bugs que o teste achou, já corrigidos no `tryd_poc.py`:

1. **Servidor morto passava despercebido:** sem Heartbeat, a captura seguia
   até o fim com os últimos valores congelados e saía com código 0. Agora o
   cliente chama `Heartbeat` depois de 5 s sem aviso e registra
   `servidor_perdido`.
2. **`dde` não funcionava:** `import dde` exige o `win32ui` carregado antes
   ("This must be an MFC application"), e a mensagem de erro dizia que
   faltava o pywin32.
3. **Um item DDE inexistente derrubava o pedido inteiro**, com traceback.
4. **`diagnostico` não achava o arquivo do servidor** quando o caminho vem
   sem aspas e com argumentos (`EXCEL.EXE /automation`). Ele agora também
   lê os registros por usuário (HKCR em vez de só HKLM).

## Resultados

As respostas das perguntas 1, 16 e 17 vêm do site público do Tryd,
consultado em 27/10/2026 ([planos](https://www.tryd.com.br/planos) e
[termos de uso](https://www.tryd.com.br/tryd/acordo_de_uso.html)). As demais
foram medidas em **2026-10-28**, com o Tryd PRO 8.5.6.12 (conta de teste de
15 dias), em pregão aberto. A máquina foi o **Aurora Linux**: Tryd no Wine
11.20, dentro do distrobox `tryd`; Python 3.12 do Windows com pywin32 no mesmo
prefixo. Como montar o ambiente:
[`scripts/linux/preparar_ponte_wine.sh`](../../scripts/linux/preparar_ponte_wine.sh)
e [`src/options_ponte/README.md`](../../src/options_ponte/README.md).

**Achado principal: o Tryd atual (Nelogica) usa o servidor RTD do Profit.**
Isso invalida as premissas de 2017:

- **Servidor e fórmula:** é `RTDTrading.RtdServer`, CLSID
  `{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}`. O ProgID `tryd.rtdserver` não
  existe. Fórmula: `=RTD("RTDTrading.RtdServer";;"PETR4_B_0";"ULT")`.
- **Campos:** são os do Profit, não `Ult`/`PrcCpa`/`PrcVda`.

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Versão, plano, opções com book em tempo real? | Tryd PRO 8.5.6.12, conta de teste. Gráfico, monitor e **livro completo** de PETR4 ao vivo. Opções ao vivo pelo RTD: bid, ask, último, negócios, volume e gregas |
| 2 | Excel 32 ou 64 bits | Não se aplica: o cliente RTD dispensa o Excel. No Wine não há Excel, e uma type library mínima ("shim", `src/options_ponte/rtd_shim.idl`) define `IRtdServer`/`IRTDUpdateEvent` com os IIDs e DISPIDs do Excel |
| 3 | Servidor RTD: DLL/EXE, bits (saída do `diagnostico`); terminal comum ou administrador | **EXE fora do processo**: `LocalServer32` é o próprio `tryd.exe`. Por isso **não há restrição de bits**; Python de 64 bits funciona. Registro só em `HKCU\Software\Classes`. No Wine, o ProgID não resolve pelo nome (`CO_E_CLASSSTRING`), mas o CLSID com `CLSCTX_LOCAL_SERVER` funciona. A type library do Tryd (`{EFCFBDCA-…}` 1.0, só `win32`) não carrega no Wine, então a ponte usa o shim. Administrador não se aplica no Wine |
| 5 | Campos e formatos de uma opção | Tópico `ATIVO_B_0` + campo. Números chegam como `float` nativo, `NEG` como `int`, `HOR` ("12:02:31"), `DAT` ("28/10/2026") e `DUV` ("16") como texto. Campos úteis: `ULT`, `OCP` (compra), `OVD` (venda), `VOC`/`VOV` (quantidade nas ofertas), `NEG`, `VOL`, `QTT`, `ABE`, `FEC`, `PEX` (strike), `VEN` (vencimento), `EST` (estado do pregão), `DELTA`, `GAMA`, `THETA`, `VEGA`, `RHO`, `IMPVT` (vol implícita), `BLACK`, `VINT`/`VEXT`. São 73 no total (`DDEPreferences` do registro) |
| 6 | Volume financeiro: campo | **`VOL` é financeiro** e `QTT` é quantidade. Conferido: PETR4 com `VOL` 679.557.741 ÷ `QTT` 12.915.600 = R$ 52,61, o preço médio |
| 7 | Lado vazio chega como | Parcial. **O valor inicial do `ConnectData` vem `0.0` até o dado carregar (~1 s)**, e um ticker inexistente também devolve zeros. Por isso a ponte marca o valor inicial (`Valor.inicial`) e o app só considera a série carregada depois de uma atualização real ou de 3 s. Falta observar uma opção sem oferta para confirmar que o lado vazio fica `0.0` |
| 8 | LVL2 bate com PrcCpa/PrcVda? | Não testado (o app usa só o topo do livro, `OCP`/`OVD`) |
| 9 | Estilo de exercício no Tryd? | **Não há.** `EST` é o estado do pregão ("Aberto"). O Cadastro de Instrumentos da B3 continua obrigatório |
| 10 | `Exerc` ajustado por proventos? | Provável. `PEX` de PETRK500 = 48,91, um valor quebrado. Conferir contra o `PREEXE`/`ExrcPric` de um arquivo real da B3 |
| 11 | Cadência e atraso (60 s) | 147 atualizações em 20 s (PETR4 e VALE3, 10 campos); 133 valores em 10 s pela ponte. Atraso aparente: nenhum perceptível contra a tela |
| 12 | 250 tópicos: desempenho | Não medido. O app limita a 600 tópicos e assina só o que está na tela |
| 13 | Fora do pregão | Não medido |
| 14 | Tryd fechado durante a captura | Com o servidor fechado ou morto, o Heartbeat detecta a queda em ~7 s. Com o servidor pendurado, **`RefreshData` bloqueia sem prazo** (medido com servidor falso: 6,9 s). A ponte espaça novas tentativas em 1 s após falha; o app trata 30 s de Tryd perdido como desconectado e cai para o fim de dia |
| 15 | DDE: serviço, tópico, funciona? | Não testado (o RTD funcionou) |
| 16 | Termos de uso | Ver "Leitura dos termos" abaixo. Uso próprio como **cliente não profissional** é o caso previsto; DDE/RTD é recurso documentado do produto. Proibidos: redistribuir dados **ou relatórios gerados** e "flood" na transmissão de dados |
| 17 | Custo | Trader: R$ 149,90/mês no mensal, a partir de R$ 89,90/mês no anual. Pro: R$ 207,44/mês no mensal, a partir de R$ 129,94/mês no anual. Teste do Pro por 15 dias, sem cartão; corretoras parceiras dão desconto ou isenção |

### Leitura dos termos (pergunta 16)

Leitura técnica, não parecer jurídico. Termo e Condições Gerais de Uso do
Tryd (Nelogica), com o Anexo I de Market Data da B3, consultado em
27/10/2026:

- **Uso próprio:** o termo prevê o usuário que recebe as informações "para
  uso próprio", na escolha dos próprios investimentos e sem fins comerciais
  (cliente não profissional). É o caso deste projeto.
- **DDE/RTD previsto:** o termo descreve o recebimento de informações via
  DDE e RTD numa planilha do usuário, no módulo de automação de ordens.
  Ler cotações por DDE/RTD é uso documentado, não contorno.
- **Proibido redistribuir:** dados de mercado, e também relatórios,
  documentos ou bancos de dados gerados pelo Tryd. O Anexo I proíbe
  retransmitir, reformatar ou publicar os dados sem consentimento da B3.
  Portanto o **painel HTML gerado com dados do Tryd não pode ser publicado
  nem compartilhado**, e capturas reais não entram no repositório.
- **Sem "flood":** o termo veda mecanismos que causem flood no Tryd ou na
  transmissão de dados. Assinar centenas de tópicos (pergunta 12) deve ser
  moderado e medido.
- **Ponto para a mesa:** o Anexo I proíbe usar os dados, sem consentimento
  da B3, para criar ou calcular "índice, taxas, benchmarks e assemelhados"
  ou instrumentos financeiros. Pela nossa leitura, isso mira produtos
  publicados; vol implícita e rendimento para decisão própria cabem no uso
  permitido, de "auxiliá-lo em decisões de investimento". A mesa deve
  confirmar essa leitura.
