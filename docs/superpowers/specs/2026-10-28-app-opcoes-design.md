# App de opções — desenho (2026-10-28)

> Documento de desenho para planejar a construção. Decidido pelo usuário em
> questionário em 2026-10-28; o que está marcado **(decisão minha)** foi
> escolha de quem escreveu este documento e pode ser revisto pelo usuário.

## 1. Intenção

Transformar o motor `options_engine` (v0.4.0) num **app completo e fácil de
usar** para analisar, montar e acompanhar operações com opções da B3, com
**toda a realidade do trade tratada por trás**: preço executável pelo lado
certo do book, custos, IR, liquidez, exercício, vencimentos e proventos.

Usuários: **o autor e a mãe dele**. Cada um tem a sua conta na Necton e a sua
carteira; nada se mistura. A referência de usabilidade é o **home broker da
Necton**, que o autor acha intuitivo. A mãe precisa conseguir usar sem ajuda.

O repositório deixa de ser peça de portfólio e **vira ferramenta pessoal**:
o rigor de testes do domínio continua (um erro de sinal dá número errado em
silêncio), mas itens só de vitrine da antiga Sprint 4 (benchmark, ADRs de
apresentação, badges) saem do escopo.

Prazo: **tudo pronto até 2026-11-30** (decisão do usuário).

## 2. Objetivos

O app tem cinco áreas, mais o perfil:

1. **Mercado (análise):** lista de ativos com cotação ao vivo; por ativo,
   gráfico de preço, vol implícita x realizada, IV rank e percentil, smile
   por vencimento, estrutura a termo, cadeia de opções com bid/ask, último,
   IV, gregas e liquidez, e o calendário de vencimentos e proventos.
2. **Montador de estruturas:** montar qualquer estrutura das quatro famílias
   (abaixo) por modelo pronto ou perna a perna, clicando na cadeia; ver
   payoff no vencimento e hoje, gregas, breakevens, ganho e perda máximos,
   custos, IR, resultado líquido, grade de cenários (spot x vol) e
   probabilidade risco-neutra. Daí: salvar como simulação ou **registrar
   como executada** (com os preços reais da Necton), indo para a carteira.
3. **Book de recomendações (scanner):** as melhores operações de cada
   família entre os ativos acompanhados, por **regras transparentes**: cada
   recomendação mostra o porquê em números e abre no montador com um clique.
4. **Carteira:** posições de ações e de opções do perfil, com P&L ao vivo,
   gregas agregadas, dias até o vencimento, histórico das operações
   encerradas com resultado realizado e estimativa de IR mensal.
5. **Alertas e vencimentos:** avisos no app de vencimento próximo, risco de
   exercício, sugestão de rolagem, stop e alvo atingidos, data-com e data-ex
   de proventos; visão de calendário.

Famílias de estratégia (todas pedidas pelo usuário):

| Família | Estruturas |
|---|---|
| Renda | venda coberta, put coberta (cash secured), travas de crédito (alta com put, baixa com call) |
| Direcionais | compra de call e de put a seco, travas de débito de alta e de baixa |
| Volatilidade | straddle, strangle, iron condor, borboleta (compradas e vendidas) |
| Proteção | put protetora, collar, proteção de posição de ações da carteira |

"Realidade do trade" (pedido do usuário), além do que o motor já trata
(custos, IR por operação, liquidez, preço executável, qualidade
EXECUTAVEL/INDICATIVO/TEORICO):

- **Carteira e P&L ao vivo:** marcação a mercado pelo preço de **zerar**
  (comprada vende no bid, vendida recompra no ask), com a qualidade do preço
  sempre visível; teórico ao lado, rotulado.
- **Alertas e vencimentos** (item 5 acima).
- **Proventos e ajustes:** calendário de proventos por ativo; ajuste de
  strike das posições abertas na data-ex, pela regra da B3 já levantada na
  ADR-0002; proventos recebidos pela perna de ação entram no resultado;
  alerta de risco de exercício antecipado de call vendida dentro do dinheiro
  perto da data-com.
- **Exercício e atribuição:** registrar o exercício de uma opção converte a
  perna em posição de ação, com o prêmio entrando no custo ou na venda da
  ação, como a Receita trata.
- **IR mensal estimado:** apuração por mês, operações comuns (15%) e day
  trade (20%) separadas, com compensação de prejuízo dentro de cada
  categoria. Sempre rotulado como **estimativa**, não cálculo fiscal.

## 3. Não-objetivos

- **Enviar ordens.** O app só analisa; a execução é no home broker da
  Necton, e o usuário registra o que executou.
- **Margem da B3.** Não pedida; a largura da trava segue como proxy de risco.
- Spreads de calendário e diagonais, estruturas com mais de um ativo-objeto
  (a decisão 6 do ROADMAP continua: mesmo ativo e mesmo vencimento), com uma
  exceção nova: **perna de ação** no agregado (seção 6).
- Acesso pela internet, celular, hospedagem ou servidor na nuvem.
- Recomendação por IA. As recomendações são só por regras.
- Precificação americana exata, Monte Carlo.
- Declaração de IR (o IR é estimativa).
- Atualização automática do app (reinstala-se a versão nova) **(decisão minha)**.

## 4. Anti-objetivos (fracasso mesmo funcionando)

- Número errado em silêncio: sinal de perna invertido, unidade trocada
  (theta/ano x theta/dia, CDI x contínua), P&L com o lado errado do book.
- Ranking que premia iliquidez: série de spread largo ou sem oferta
  aparecendo como oportunidade executável.
- **Dado parado mostrado como ao vivo.** Todo número de mercado mostra de
  onde veio e quando: "ao vivo (Tryd)", "atrasado" ou "fim de dia (B3)".
- App difícil para a mãe do autor: jargão sem explicação, telas lotadas sem
  hierarquia, fluxo que exige terminal.
- Perder ou misturar carteiras: a do autor e a da mãe nunca se misturam, e
  uma falha de sincronização da nuvem não pode corromper a carteira.
- Publicar dado do Tryd ou da B3 (termos proíbem redistribuir).

## 5. Restrições

- **Plataformas:** este PC (Aurora Linux, Tryd no Wine dentro do distrobox
  `tryd`) e **3 PCs Windows** (Tryd nativo). Usa-se **um PC de cada vez**.
- **Dados (decisão do usuário):** Tryd ao vivo + arquivos da B3.
  - Ao vivo: RTD do Tryd. Medido no spike de 2026-10-28: ProgID
    `RTDTrading.RtdServer`, CLSID `{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}`,
    servidor fora do processo (o próprio `tryd.exe`, sem restrição de bits);
    tópico `ATIVO_B_0` + campo (`ULT`, `OCP`, `OVD`, `VOC`, `VOV`, `NEG`,
    `VOL` financeiro, `QTT`, `HOR`, `PEX`, `VEN`, `DUV`...); números chegam
    como `float`; o valor inicial é `0.0` até o dado carregar (~1 s) e ticker
    inexistente também devolve zeros. No Wine o ProgID não resolve pelo nome
    (criar pelo CLSID). Sem campo de estilo de exercício.
  - B3: COTAHIST (histórico do ativo e das opções) e **Cadastro de
    Instrumentos** (universo de séries, estilo de exercício e strike). Os
    termos da B3 **proíbem coleta automática** e o download tem CAPTCHA
    (ADR-0006): a importação é manual, mas tem de ser fácil.
  - Tryd fechado ou ausente: o app funciona com o último fim de dia
    importado, com o rótulo "fim de dia".
- **Termos do Tryd:** uso próprio; nada de redistribuir dados nem relatórios;
  nada de "flood": assinar só o necessário (seção 6.3).
- **Teste do Tryd expira por volta de 2026-11-12.** O autor precisa da
  assinatura antes disso para seguir testando ao vivo.
- **Arquitetura existente:** domínio e aplicação continuam stdlib-only
  (import-linter); frameworks só em adapters. Idioma do projeto: português.
- **Instalação no Windows:** instalador `.exe` (decisão do usuário).
- **Fluxo do autor:** quem constrói nunca faz commit nem push; o autor
  commita.

## 6. Como (o que já está decidido)

### 6.1 Forma do app (decisão minha)

App **web local**: um servidor Python na própria máquina (só `127.0.0.1`)
servindo uma interface no navegador, aberta numa **janela de app** (Edge
`--app` no Windows, Chrome/Brave `--app` no Linux; navegador padrão como
reserva). Parece um programa, não um site.

- **Backend:** o pacote `options_engine` com um adapter inbound novo,
  FastAPI (REST + WebSocket para empurrar cotações). Pydantic só na borda.
  FastAPI e uvicorn entram como **extra opcional** (`[app]`): o núcleo
  segue sem dependência de runtime, como manda o `CLAUDE.md` do projeto.
- A CLI atual (`python -m options_engine` e `painel`) continua funcionando.
- **Frontend:** React + TypeScript (Vite), Apache ECharts para todos os
  gráficos (candles, payoff, smile, grade de cenários). Tema escuro e
  denso, inspirado no home broker da Necton, com detalhes avançados
  recolhíveis.
- **Linguagem simples por cima:** cada estrutura ganha um resumo em
  português claro ("você recebe R$ X agora; no pior caso perde R$ Y; ganha
  no máximo R$ Z; empata se PETR4 ficar entre A e B no vencimento"), e todo
  termo técnico tem dica de tela (glossário).

### 6.2 Perfis e armazenamento (decisão minha, a pedido do usuário)

- Ao abrir, o app pergunta **quem está usando** (autor ou mãe; perfis
  criáveis). Cada perfil aponta para a **sua pasta de dados**, escolhida no
  primeiro uso. O app sugere uma pasta sincronizada da pessoa (Google Drive,
  OneDrive, Dropbox), para a carteira aparecer em qualquer PC.
- Na pasta do perfil: `perfil.json` (nome, lista de ativos acompanhados,
  preferências, custos próprios quando diferem da tabela) e **um arquivo
  JSON por operação**. Escrita atômica (temporário + renomear). Arquivo por
  operação reduz conflito de sincronização; JSON é legível e recuperável.
- **Trava de uso:** um arquivo de trava com PC e horário. Se o perfil
  estiver aberto noutro PC, o app avisa antes de seguir.
- Configuração da máquina (lista de perfis e pastas, pasta de dados de
  mercado) fica na pasta de configuração do sistema operacional.
- **Dados de mercado** (arquivos da B3 importados, cache e histórico de IV)
  ficam numa pasta da máquina, que também pode apontar para a nuvem.

### 6.3 Dados ao vivo: ponte do Tryd (decisão minha)

- Um processo pequeno, a **ponte**, em Python **do Windows** com pywin32,
  conecta no RTD do Tryd **pelo CLSID**, assina e devolve valores crus (tipo
  e valor) e horário por (ticker, campo) ao app, via WebSocket em
  `127.0.0.1`. É o mesmo código nos dois sistemas: nativo no Windows; no
  Linux, roda no Python do Windows dentro do Wine (distrobox `tryd`, prefixo
  `~/.local/share/wineprefixes/tryd`, como no spike).
- O app inicia e encerra a ponte sozinho. A tradução de valores crus para o
  domínio fica no app e é testada sem COM (ADR-0008, item 5): **zero
  inicial não é dado**, lado vazio vira `None`, nunca zero.
- **Universo de séries vem do Cadastro** (o Tryd não lista a cadeia). O app
  assina só o que está na tela ou é necessário: ativos acompanhados, cadeia
  do ativo aberto nos vencimentos filtrados, pernas da carteira. Há um
  limite configurável de tópicos.
- Heartbeat e indicador de status sempre visível: Tryd conectado,
  atrasado, desconectado (usando fim de dia).
- `pywin32` só na ponte; um contrato do import-linter impede `win32com`,
  `pythoncom` e `pywintypes` no pacote principal.

### 6.4 Arquivos da B3 (importação manual fácil)

- Arrastar e soltar (ou botão) para COTAHIST (anual, mensal ou diário) e
  Cadastro; o app reconhece o tipo do arquivo pelo conteúdo.
- O app avisa quando o Cadastro está velho ("Cadastro de 9 dias atrás:
  séries novas podem estar faltando") e explica onde baixar, com o link da
  página da B3.
- **Histórico de IV:** calculado das cotações diárias de opções do COTAHIST
  importado e completado por uma foto diária que o app grava quando há dado
  ao vivo (decisão minha). Alimenta IV rank e percentil.

### 6.5 Domínio: o que muda

- **Perna de ação** no agregado `Strategy`, para payoff, gregas e métricas
  de venda coberta, put protetora e collar.
- Factories novas: compra de call/put, travas de débito, collar, put
  protetora (as de volatilidade e renda já existem ou foram estendidas na
  S5).
- **Carteira:** operação (pernas com preços executados, data, custos
  reais), posição, exercício e atribuição, encerramento parcial e total,
  P&L realizado e não realizado, IR mensal estimado com compensação.
- **Proventos:** VO de provento (tipo, valor, data-com, data-ex); ajuste de
  strike pela regra da ADR-0002 aplicado às posições abertas; detecção
  automática de ajuste quando um Cadastro novo traz strike diferente do
  registrado (o app propõe e o usuário confirma).
- **Alertas:** regras puras sobre carteira + mercado + calendário, com
  limites configuráveis por perfil.
- Precificação: continua `q = 0`. O ajuste de strike pela B3 neutraliza a
  maior parte do efeito dos proventos em dinheiro (ADR-0002); o construtor
  deve confirmar essa premissa ao implementar o ajuste.

### 6.6 Recomendações por regras (decisão do usuário: transparentes)

- O book é **separado por família** e, dentro dela, por tipo de estrutura,
  cada um com o seu critério padrão. Isso resolve a distorção do ranking
  misto, em que travas lideravam pela anualização composta (HANDOFF da S5).
- Só entra preço EXECUTAVEL; INDICATIVO e TEORICO aparecem à parte e
  rotulados; filtros de liquidez; custos e IR no resultado líquido. Cada
  item mostra os números do critério e o motivo de estar ali.
- **Presets** Conservador, Moderado e Arrojado (faixa de delta, liquidez
  mínima, risco máximo), visíveis e editáveis (decisão minha).
- Por família (decisão minha):
  - **Renda:** o `RankIncomeOpportunitiesService` existente. Venda coberta
    e put coberta por anualizado líquido; travas de crédito por retorno
    sobre risco com probabilidade ao lado.
  - **Direcionais:** dois modos. Com visão (o usuário diz ativo, direção,
    alvo e prazo): ordena pelo resultado no alvo sobre o risco. Sem visão:
    "opções baratas" pela vol (IV baixa contra a realizada e o IV rank),
    rotulado como não direcional.
  - **Volatilidade:** IV contra realizada e IV rank. Vol alta sugere venda
    (iron condor, strangle e borboleta vendidos); vol baixa sugere compra
    (straddle e strangle comprados). Métricas: crédito ou débito sobre
    risco, breakevens em desvios-padrão, probabilidade risco-neutra.
  - **Proteção:** para posições de ações da carteira (ou quantidade
    hipotética): custo em % da posição, piso protegido, custo mensal
    equivalente e teto do collar.

### 6.7 Distribuição

- **Windows:** instalador `.exe` (PyInstaller + Inno Setup) com app, ponte e
  interface já compilada; atalho na área de trabalho que abre a janela do
  app. Gerado por um job Windows no GitHub Actions, que publica o instalador
  como artefato (decisão minha: PyInstaller não gera `.exe` a partir do
  Linux). O instalador não é assinado: o Windows mostra o aviso do
  SmartScreen na primeira vez, e o README explica o "Executar assim mesmo".
- **Linux (Aurora):** script de instalação (venv com o Python do sistema;
  ponte no distrobox `tryd` já montado) e atalho `.desktop`.
- O Tryd é instalado à parte em cada PC, pelo próprio usuário.

## 7. Critérios de pronto (2026-11-30)

1. Nos dois sistemas: abrir pelo atalho, escolher perfil, ver cotações ao
   vivo do Tryd e, com ele fechado, o fim de dia rotulado.
2. Montador: as quatro famílias com modelo pronto e perna a perna; payoff,
   gregas, cenários, custos e IR conferidos contra os golden e oráculos do
   domínio.
3. Book com as quatro famílias, cada item com o porquê e "abrir no montador".
4. Carteira dos dois perfis em pastas diferentes; registrar, encerrar e
   exercer; P&L ao vivo pelo preço de zerar; IR mensal estimado.
5. Alertas e calendário de vencimentos e proventos funcionando; ajuste de
   strike aplicado a uma posição aberta.
6. Análise de mercado com IV x realizada, IV rank, smile e estrutura a
   termo.
7. Instalador `.exe` testado num dos PCs Windows; script do Linux testado
   neste PC.
8. Gates verdes: pytest com cobertura, mypy strict, ruff, import-linter
   (com o contrato novo do pywin32), checagem de tipos e testes do frontend.
9. A mãe do autor consegue montar e registrar uma operação sozinha, num
   teste de usabilidade.

## 8. Ordem de construção (decisão minha)

Para cada semana terminar com algo usável:

| Semana | Entrega |
|---|---|
| 28/10–03/11 | Base: backend FastAPI, esqueleto da interface (tema Necton), perfis e pastas, ponte do Tryd no Linux e cotações ao vivo, importação da B3 e conferência com arquivo real |
| 04/11–10/11 | Montador (quatro famílias, perna de ação) e carteira com P&L ao vivo |
| 11/11–17/11 | Book de recomendações e análise de mercado (histórico de IV) |
| 18/11–24/11 | Alertas, vencimentos, proventos e ajustes, IR mensal; instalador Windows |
| 25/11–30/11 | Teste com a mãe do autor, acabamento, correções, documentação |

Risco honesto: é muito escopo para um mês. Se algo atrasar, a ordem acima
garante que o que fica pronto primeiro é o que mais se usa.

## 9. Fica com o construtor

- Desenho interno da API, das telas e dos componentes, e a biblioteca de
  estado do frontend.
- Fórmulas exatas dos critérios e valores dos presets, dentro dos princípios
  da seção 6.6, sempre exibidos ao usuário.
- Limites padrão dos alertas e do número de tópicos assinados.
- Formato exato dos JSON do perfil e das operações (versionado, com campo de
  versão do esquema).
- Testes de interface: o mínimo que proteja os fluxos principais.

Decisões menores já tomadas por quem escreveu (revisáveis):

- **CDI** é campo das configurações, com valor padrão e data de referência
  visíveis no app; nada de buscar na internet.
- **Registro de operação** aceita execução parcial (várias execuções por
  perna, preço médio) e custos reais digitados, que substituem a estimativa.
- **Day trade** para o IR: compra e venda da mesma série no mesmo dia,
  pela data registrada nas execuções.
- Posições de ações entram **à mão** (quantidade e preço médio); importar
  nota de corretagem fica fora.
- Dados pessoais (perfis, carteiras) **nunca** ficam dentro do repositório,
  que é público.

## 10. Em aberto (verificar no início)

1. Perguntas restantes do spike do Tryd: lado vazio (7), desempenho com
   muitos tópicos (12), fora do pregão (13), DDE (15).
2. Se o Tryd tem fonte de proventos utilizável; se não, provento entra à mão
   e por detecção no Cadastro.
3. Premissas do COTAHIST e do Cadastro num arquivo real (HANDOFF da S5).
4. Comportamento do RTD no Windows nativo (ProgID pelo nome deve resolver).
5. Documentação: ROADMAP, ADR-0008 (aceita com as correções do spike) e uma
   ADR curta para o app local com ponte.
