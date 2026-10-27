# ADR-0008 — Intraday via RTD do Tryd

- **Status:** Proposta — **emenda a decisão 3 da ADR-0006**; depende do
  roteiro de [`docs/spikes/tryd-intraday.md`](../spikes/tryd-intraday.md).
  Nada é implementado antes da aceitação.
- **Data:** 2026-10-27
- **Decisores:** mesa de operações

## Contexto

A decisão 3 da ADR-0006 deixou o intraday para depois da Sprint 5, com a
ordem de avaliação **MT5 → ProfitDLL → RTD (Excel e Profit abertos)**. Desde
então:

- **MT5 na Necton** segue não confirmado (ADR-0006, "Fase intraday").
- **ProfitDLL** exige licença paga da Nelogica.
- O usuário opera com o **Tryd**, que publica cotações por **RTD** (ProgID
  `tryd.rtdserver`) e por **DDE**, ligados em **Arquivo > Ativar DDE e RTD**
  com o Tryd rodando como administrador. Fórmula documentada:
  `=RTD("tryd.rtdserver";;"COT";ATIVO;CAMPO)`.
- O RTD é uma interface COM (`IRtdServer`). O Excel é o cliente usual, mas
  qualquer cliente COM consome o mesmo servidor. **O Excel não é
  obrigatório**, e isso remove a maior fragilidade da opção RTD da ADR-0006.
- A prova de conceito `tools/tryd_spike/tryd_poc.py` implementa um cliente
  RTD direto em Python (pywin32). Na máquina de desenvolvimento ela passou
  nos testes que não precisam do Tryd (detalhe no roteiro, "Teste sem
  Tryd"):
  - cliente RTD contra um servidor falso no mesmo processo e noutro
    processo;
  - detecção do servidor que morre no meio da captura;
  - leitura DDE contra um servidor DDE real, o Excel.
  **Ainda não rodou contra um Tryd real:** essa máquina não tem Tryd.
- Pelo site do Tryd (27/10/2026), os dois planos incluem **DDE/RTD** e o
  **módulo de opções**, a partir de R$ 89,90/mês. O termo de uso prevê o
  cliente não profissional e descreve DDE/RTD como recurso do produto
  (roteiro, pergunta 16).
- Os campos conhecidos do tipo `COT` (`Ult`, `PrcCpa`, `PrcVda`, `QtdNeg`,
  `Vol`, `DataHora`, `Exerc`, `Expir`, ...) vêm de um blog de terceiros de
  2017. A fonte de verdade é o **Gerar Links RTD** da versão instalada.

O que o Tryd **não** resolve, pelo que se sabe hoje:

- **Estilo de exercício:** não há campo conhecido para ele, e a ADR-0006
  torna o estilo obrigatório e vindo do Cadastro de Instrumentos;
- **Volume financeiro:** `Vol` parece ser **quantidade**, e o `OptionQuote`
  exige volume **financeiro** (ADR-0003);
- **Histórico para a vol realizada** do subjacente.

## Decisão (proposta)

1. **Nova ordem de avaliação do intraday**, emendando a decisão 3 da
   ADR-0006: **RTD do Tryd com cliente direto** → MT5 → ProfitDLL. O Tryd
   sobe para o primeiro lugar porque o usuário já o tem, não exige licença
   nova e o cliente direto dispensa o Excel. Se a ADR for descartada, volta
   a ordem da ADR-0006.

2. **Adapter híbrido** `TrydOptionChainAdapter`, que implementa o mesmo
   `OptionChainPort`:
   - **Tryd (RTD):** book e negócios ao vivo das séries e do subjacente:
     `bid`, `ask`, `last`, `trades`, `volume`, horário;
   - **Cadastro de Instrumentos** (CSV local, como na fase 1): universo de
     séries do subjacente, estilo de exercício, lote padrão e strike. É dele
     que sai a lista de tickers a assinar: o Tryd não precisa listar a
     cadeia;
   - **COTAHIST** (arquivos locais, como na fase 1): histórico do
     subjacente para a vol realizada.

   A obtenção manual dos arquivos B3 e o estilo obrigatório da ADR-0006 não
   mudam.

3. **Transporte, em ordem de preferência:**
   - **A — cliente RTD direto (pywin32):** o da prova de conceito. É a
     escolha se o servidor do Tryd carregar no processo Python. Uma DLL de
     32 bits só carrega num Python de 32 bits (pergunta 3 do roteiro);
   - **B — DDE:** reserva se o RTD falhar. Protocolo mais antigo; no teste
     com o Excel, tudo chegou como texto terminado em CR LF, inclusive
     número, célula vazia e erro. A prova de conceito só faz leitura pontual
     (`Request`);
   - **C — Excel como ponte:** planilha com fórmulas RTD lida pelo adapter.
     Último recurso: volta a depender do Excel aberto e do throttle do RTD
     (2 s por padrão).

4. **Dependência e camadas:**
   - `pywin32` entra como **extra opcional** `[tryd]` e só é importado em
     `adapters/outbound/tryd/`;
   - um contrato novo do import-linter proíbe `win32com`, `pythoncom` e
     `pywintypes` fora desse pacote. Domínio e aplicação seguem stdlib-only;
   - só Windows: em outro sistema, ou sem o extra, a composição falha com
     erro explícito, sem fallback silencioso para o COTAHIST.

5. **Tradução para o domínio**, na borda e testada sem COM:
   - o transporte fica atrás de um Protocol interno que devolve valores
     crus por (ativo, campo). A tradução para `OptionQuote` é Python puro e
     roda no CI (ubuntu) contra capturas **sintéticas**, no formato do JSON
     da prova de conceito;
   - **lado vazio vira `None`**, na forma que o Tryd usar (zero, vazio,
     traço ou erro: pergunta 7). Nunca vira zero (ADR-0003);
   - **número em texto pt-BR** é convertido de forma estrita. Valor
     ilegível tira a série do painel **com motivo explícito**, nunca vira
     zero nem é suposto;
   - **volume:** só entra um campo **financeiro** da fonte. Se o Tryd tiver
     só quantidade, a forma de obter o financeiro volta à mesa antes da
     implementação (pergunta 6). Quantidade nunca vai para o campo
     `volume`;
   - **horário:** cada cotação usa o `DataHora` do Tryd (fuso
     `America/Sao_Paulo`); a cadeia usa o instante da leitura;
   - **nomes de campo** ficam em configuração do adapter, validados na
     conexão: campo ausente ou renomeado numa versão nova do Tryd falha
     explicitamente.

6. **Leitura é uma foto, não um stream:**
   - o adapter conecta, assina, espera os valores iniciais (com timeout),
     lê e desconecta;
   - o painel continua um relatório HTML estático (ADR-0007). Painel que se
     atualiza sozinho fica fora desta ADR;
   - **servidor perdido falha explicitamente.** Depois de um silêncio, o
     adapter chama `Heartbeat`, como o Excel; sem resposta, a leitura falha,
     em vez de devolver valores congelados como se fossem atuais. O teste
     entre processos mostrou que, sem isso, a queda passa despercebida;
   - a foto **não é atômica**: spot e séries chegam em instantes diferentes,
     e cada cotação guarda o seu horário. Filtro de cotação velha, se
     houver, é parâmetro do comando, sem valor padrão (como os filtros de
     liquidez da ADR-0004).

7. **Regras de preço da ADR-0004 inalteradas:** preço executável por lado;
   `last` continua só `INDICATIVO`, também no intraday.

8. **Dados:** capturas reais do Tryd nunca entram no repositório
   (`.gitignore`); fixtures e testes usam valores sintéticos. Uso pessoal,
   sem redistribuição (ADR-0006). O termo do Tryd proíbe redistribuir também
   os relatórios gerados, então o **painel feito com dados do Tryd não é
   publicado nem compartilhado**.

## Critérios de aceitação

A mesa aceita esta ADR quando o roteiro mostrar:

- o plano do Tryd entrega **opções em tempo real com book** (pergunta 1;
  o site diz que sim nos dois planos, falta conferir no cadastro);
- o servidor RTD carrega em um Python viável, de 64 ou de 32 bits
  (pergunta 3);
- os campos de preço, negócios e horário existem para opções e o lado vazio
  é distinguível (perguntas 5, 7 e 8);
- há volume financeiro, ou uma decisão da mesa sobre ele (pergunta 6);
- os termos de uso permitem a captura automatizada para uso pessoal
  (pergunta 16; a leitura dos termos públicos indica que sim, e a mesa
  confirma o ponto do Anexo I da B3 sobre "índice, taxas, benchmarks").

Se falhar a pergunta 1 ou a 16, a ADR é **descartada** e vale a ordem da
ADR-0006. Se só o RTD falhar, testa-se o DDE (opção B) antes do Excel
(opção C).

## Perguntas em aberto

As perguntas numeradas no roteiro do spike, com destaque para:

- se o cliente Python precisa rodar **como administrador**, já que o Tryd
  roda elevado e o COM não atravessa níveis de integridade (pergunta 3);
- cadência e atraso reais, e o custo de assinar ~250 tópicos (perguntas 11
  e 12);
- o que o Tryd publica fora do pregão (pergunta 13);
- se `Exerc` já vem ajustado por proventos: a mesma dúvida do `PREEXE` na
  ADR-0006 (pergunta 10).

## Consequências

- **Positivas:**
  - book intraday sem licença nova;
  - mesmo port e mesma suíte de contrato, então o painel não muda;
  - a fase 1 (COTAHIST) continua como fonte de fim de dia e de histórico.
- **Negativas:**
  - só Windows, com o Tryd aberto, logado e como administrador;
  - dependência de nomes de campo não documentados oficialmente;
  - restrição de bitness entre o servidor RTD e o Python;
  - o CI não exercita o COM: o `autoteste` da prova de conceito cobre o
    encanamento só no Windows, e os testes de CI cobrem a tradução.
- **Na ADR-0006:** ela continua aceita. Se esta ADR for aceita, o status da
  0006 ganha "decisão 3 emendada pela ADR-0008", como a 0002 fez com a
  decisão nº 2.
