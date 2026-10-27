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

## Resultados (preencher)

As respostas das perguntas 1, 16 e 17 vêm do site público do Tryd,
consultado em 27/10/2026 ([planos](https://www.tryd.com.br/planos) e
[termos de uso](https://www.tryd.com.br/tryd/acordo_de_uso.html)). Confira
no seu cadastro.

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Versão, plano, opções com book em tempo real? | Pelo site, os dois planos (Trader e Pro) têm **DDE/RTD**, **módulo de opções** e negócios em tempo real; livro de ofertas: Trader "máximo 10", Pro completo. Falta conferir a versão e o plano do seu cadastro |
| 2 | Excel 32 ou 64 bits | Máquina de desenvolvimento: 64 bits. Conferir na do Tryd, se for outra |
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
