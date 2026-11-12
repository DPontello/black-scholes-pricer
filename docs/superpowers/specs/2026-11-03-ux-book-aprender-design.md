# App de opções — UX: Book mais simples, aba Aprender, layout e rotina da B3 — desenho (2026-11-03)

> Melhoria de uso pedida pelo autor em 03/11, fora do cronograma das semanas
> ([desenho geral](2026-10-28-app-opcoes-design.md)). As decisões marcadas **(autor, 03/11)**
> foram dadas pelo autor na conversa, com rascunhos de tela aprovados; o resto é decisão de quem
> escreveu, revisável. Público: o autor e a mãe dele, pouco técnica.

## 1. Por quê

- **O Book está confuso, com informação demais** (autor). O que o autor quer ao abrir o Book:
  **"as melhores operações pra fazer hoje"**.
- **Bug de layout ao aumentar a janela** (autor, confirmado nos prints de 03/11):
  - no Montador, acima de 1100 px de largura o resultado (gráfico, números, "Salvar simulação")
    pula para o lado da cadeia; em 1366 px a cadeia fica cortada (as puts somem atrás de rolagem
    lateral) e o lado direito fica apertado; em 1920 px e 2560 px o lado direito estica;
  - na Carteira, o formulário "Registrar operação" ocupa a largura toda: os campos ficam
    espalhados e o × de cada perna vai para a ponta direita. O campo Série mostra o ticker cortado
    ("BOVAK168W" para "BOVAK168W1").
- **Uma aba que explique tudo** (autor): as operações, o que cada uma faz, quando é usada, com
  exemplo, **em sub-abas**, para não virar uma página única gigante.
- **Link exato para os downloads da semana** na aba Arquivos B3 (autor).

**Sucesso:** o autor abre o Book e vê de cara as melhores operações do dia; a mãe dele entende uma
operação e o que fazer no app sem precisar perguntar; nenhuma tela corta tabela nem estica painel
entre 1280 px e 2560 px de largura.

## 2. Escopo e ordem de construção

Quatro partes, nesta ordem (decisão de quem escreveu: da menor e mais independente para a maior):

1. **Arquivos B3:** a rotina da semana com os links exatos (§3).
2. **Layout:** Montador e "Registrar operação", e a conferência das outras telas (§4).
3. **Book** mais simples (§5).
4. **Aba Aprender** (§6).

**Entrega por parte** (decisão de quem escreveu): cada parte é uma branch a partir da `development`
e entra sozinha, para o autor testar logo o que fica pronto. Os "?" do Book e das outras telas
entram na parte 4, junto com os termos para onde apontam; até lá, o Book novo não tem "?". Só a
parte 4 espera a revisão dos textos pelo autor.

**Fora do escopo:**

- As regras do Book (famílias, critérios, filtros, presets, ordenação dentro de cada família)
  não mudam; muda só a apresentação.
- Nenhuma operação nova no catálogo do Montador.
- Nada de dado de mercado na aba Aprender.
- Tutorial interativo, assistente passo a passo ou tela de boas-vindas.
- Layout de celular: o app é de desktop. Abaixo de 1280 px vale o empilhamento de hoje.
- Alertas, vencimentos, proventos, IR e instalador (semana 4).

## 3. Arquivos B3: a rotina da semana

- No topo da aba, um quadro **"Rotina da semana"** com dois passos, cada um com o link, o que
  fazer na página, o nome do arquivo que cai na pasta Downloads e o estado na biblioteca:
  1. **Cadastro de Instrumentos:**
     <https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/boletins-diarios/pesquisa-por-pregao/>
     **(autor, 03/11)**. Arquivo: `pesquisa-pregao.zip`.
  2. **COTAHIST anual:**
     <https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/>
     **(autor, 03/11)**. Arquivo: `COTAHIST_A<ano>.zip`, do ano corrente.
- O texto do "o que fazer na página" é curto e o autor confere com a página aberta, porque o
  agente não pode abrir o site da B3 (termos, ADR-0006). Rascunho: "escolha o último pregão e o
  Cadastro de Instrumentos" e "baixe a série anual do ano corrente".
- **Estado de cada passo** (decisão de quem escreveu): o arquivo mais recente da biblioteca e a
  data dele, com **"em dia"** ou **"hora de baixar"**. O Cadastro fica "hora de baixar" pela regra
  que já existe (mais de 5 dias úteis); o COTAHIST, quando o último pregão da biblioteca tem mais
  de 5 dias úteis. Sem arquivo: "ainda não baixado".
- Uma linha diz que o diário é dispensável quando o anual é baixado no dia (ADR-0006, "COTAHIST
  anual atualizado").
- A lista "Onde baixar" do fim da página sai; o link antigo do Boletim Diário
  (`.../consultas/boletim-diario/`) é trocado pelo da Pesquisa por pregão.
- Em janeiro, o anual do ano novo tem poucos pregões: o anual do ano anterior continua na
  biblioteca, e o texto não manda apagar nada.

## 4. Layout

### 4.1 Montador

- **Lado a lado só quando os dois cabem inteiros:** a coluna do resultado tem largura fixa, por
  volta de 600 px, e a cadeia fica com o resto. Abaixo da largura em que a cadeia inteira (calls,
  strike e puts) mais o resultado cabem, o resultado desce para baixo da cadeia, como hoje. O ponto
  de troca sai da largura mínima real da cadeia, não dos 1100 px de hoje.
- **Em tela larga o resultado não estica:** o gráfico e a grade ficam no tamanho da coluna; a
  sobra vai para a cadeia.
- **"Salvar simulação", o nome e "Registrar como executada" sobem para logo abaixo da tabela de
  pernas**, antes do resumo, do gráfico e da grade.
- (Autor aprovou estes quatro pontos em 03/11.)

### 4.2 Carteira — "Registrar operação"

- O formulário tem **largura máxima** de uns 900 px.
- Em cada perna, Série, Lado, Execuções e o × ficam juntos; o × não vai para a ponta da tela.
- **O campo Série mostra o ticker inteiro** (no mínimo 12 caracteres visíveis; o maior ticker de
  opção hoje tem 10, como `BOVAK168W1`).
- (Autor aprovou em 03/11.)

### 4.3 As outras telas

Mercado, Book, Carteira, Arquivos B3 e Aprender são conferidas nas mesmas larguras (1280, 1366,
1920 e 2560 px): sem tabela principal cortada, sem painel esticado sem necessidade, sem botão de
ação longe do que ele afeta. O que aparecer de igual ao §4.1 e ao §4.2 é corrigido do mesmo jeito.
Problema de outro tipo que se resolva só com CSS também é corrigido; o que pedir mudança de
comportamento vai para uma lista ao autor, sem corrigir (decisão de quem escreveu).

### 4.4 Como se confere

Pelo agente, com um navegador automático **fora do repositório** (como nos prints de 03/11),
contra o app rodando com os arquivos reais da B3 deste PC e, no pregão, com o Tryd. Nenhum teste de
navegador nem dependência nova entra no repositório; os testes do Vitest cobrem o comportamento
(o que abre, o que fecha, o que aparece), não a largura. Os prints vão para o autor no fim de cada
parte (decisão de quem escreveu).

## 5. Book

Rascunho aprovado pelo autor em 03/11 ("Melhores operações de hoje", com o melhor de cada família
em cartões e as abas compactas embaixo).

### 5.1 Topo

- Título **"Melhores operações de hoje"**, com o pregão e a fonte ao lado ("pregão de 30/10/2026 ·
  fim de dia (B3)").
- **"Critérios: Moderado · ajustar ▸"**: o editor de preset fica fechado e abre no clique. Nada
  muda nos campos nem no salvar.

### 5.2 Vol de cada ativo

- A tabela de vol vira **etiquetas por ativo**: "BOVA11 · vol barata". Palavras (decisão de quem
  escreveu): regime `baixa` → **barata**, `neutra` → **normal**, `alta` → **cara**. Com o regime
  pela HV (histórico curto), a etiqueta diz isso.
- Ao passar o mouse, a etiqueta mostra IV 30, HV 21, IV rank e percentil. Os números continuam na
  aba Análise do Mercado.
- Um link "o que é vol barata ou cara?" leva ao termo na aba Aprender.

### 5.3 O melhor de cada família

- Quatro cartões, **um por família** (Renda, Volatilidade, Direcionais, Proteção). Não há lista
  única misturando as famílias: comparar o "% ao ano" de uma venda coberta com o "retorno sobre o
  risco" de uma trava exigiria uma nota comum, e isso é regra de negócio que ninguém decidiu
  (decisão de quem escreveu).
- **O destaque é o primeiro item da família na ordem em que o Book já mostra hoje** (`itens[0]`
  da família: as estruturas na ordem em que aparecem, e dentro de cada uma o melhor pelo critério
  dela) **(autor, 03/11)**. Nenhuma regra nova de preferência entre estruturas. O número grande é
  o critério **do próprio item**: "% ao ano" numa venda coberta, "retorno sobre o risco" numa
  trava, e assim por diante.
- Só item **executável** vira destaque (ADR-0004). Família sem item executável: o cartão diz
  "Nada hoje em <família>" com o motivo curto (sem séries com preço, nenhuma passou nos filtros) e
  o link para a aba dela.
- **O que o cartão mostra:**
  - a família, o nome da estrutura, o ativo e o vencimento com os dias úteis;
  - **o que fazer, numa linha**: "vender 100 BOVAK168W1 a 1,12 · comprar 100 BOVA11";
  - **um número grande**: o critério da família (o `criterio` de hoje), com o rótulo em linguagem
    simples ("41,2% ao ano, líquido");
  - **até três números pequenos, os mesmos em todas as famílias** (decisão de quem escreveu):
    **ganha até**, **perde até** e **chance de lucro**, líquidos de custos e IR, pelo mesmo
    cálculo do Montador para o pedido do item com os preços do book. "Sem limite" quando o ganho
    ou a perda não tem teto;
  - **o porquê em uma frase curta que não repete os números** ("prêmio alto para só 4 dias
    úteis"; "aposta em alta com perda limitada"). A frase longa de hoje continua no detalhe;
  - os avisos que o item já traz (`rotulos`, como "posição hipotética de 100 ações" e "call
    americana avaliada como europeia"), pequenos;
  - o botão **"Abrir no montador"**;
  - um **"?"** ao lado de cada termo, que abre o termo na aba Aprender.

### 5.4 Abas por família

- Embaixo dos cartões, as abas com a contagem ("Renda (9)").
- Cada aba é uma **tabela compacta**, uma linha por item: operação (nome, ativo, strikes), vence
  (data e dias úteis), o critério, ganha até, perde até, chance de lucro e "abrir".
- **Clicar na linha expande o detalhe**: todos os `numeros` de hoje e a frase longa do porquê.
  Nenhum número que existe hoje some do Book; ele fica um clique abaixo.
- A aba Direcionais mantém, no topo, o formulário "com visão" de hoje.

### 5.5 O que fica fechado

- "Referências sem preço de compra e venda agora (N)", "Fora do book por dado ruim (N)" e os
  ativos indisponíveis ficam em seções recolhidas no fim, como "Fora do book" já é hoje.

### 5.6 Tempo de resposta

Ganha até, perde até e chance de lucro por item podem pesar no `GET /api/book`. Meta: o Book não
fica perceptivelmente mais lento que hoje com o cache quente. Se ficar, calcular primeiro os
destaques e a aba aberta.

## 6. Aba Aprender

Rascunho aprovado pelo autor em 03/11 (sub-abas; Operações com a lista à esquerda e a operação à
direita).

### 6.1 Onde fica

- No menu, **"Aprender"**, entre Carteira e Alertas (decisão de quem escreveu).
- Cada sub-aba tem endereço próprio, para o "?" e o botão voltar funcionarem: `/aprender/comece`,
  `/aprender/operacoes/<modelo>` (a chave do catálogo do Montador, como `venda_coberta`),
  `/aprender/termos#<termo>` e `/aprender/telas`. `/aprender` sozinho abre "Comece aqui".
- **O Aprender abre também sem perfil** (decisão de quem escreveu): a tela de perfis ganha um link
  "Como usar o app" para `/aprender/comece`, já que o primeiro passo é justamente criar o perfil.
  Sem perfil, o botão "Montar no Montador" fica desabilitado com o motivo ("abra um perfil
  primeiro").
- **"Montar uma <operação> no Montador"** (decisão de quem escreveu): abre o Montador com o modelo
  escolhido, no ativo que o Montador já estiver usando (senão o primeiro da lista do perfil) e no
  vencimento padrão do modelo. O modelo é aplicado quando a cadeia chega, com "aguardando a
  cadeia" enquanto isso; se a sugestão do modelo falhar (por exemplo, faltam strikes para um iron
  condor), aparece a mensagem de erro que o Montador já tem, e o resto da tela segue usável. O
  ativo do exemplo (PETR4) não é forçado.

### 6.2 Sub-abas **(autor, 03/11: sub-abas, não página única)**

1. **Comece aqui:** os passos para usar o app sozinho: criar o perfil e escolher a pasta; a
   rotina da semana na B3 (com link para Arquivos B3); abrir o Tryd e ler o indicador do topo;
   o caminho Book → Montador → Carteira; o que fazer no vencimento.
2. **Operações** **(autor, 03/11: o que cada uma faz, quando é usada, com exemplo):** as 18
   estruturas do catálogo do Montador (`/api/montador/modelos`), agrupadas por família, numa
   lista à esquerda; à direita, a operação escolhida com:
   - etiquetas: família, o que é preciso ter (a ação, o caixa), o cenário (parado, alta, queda,
     mexer muito) e o risco em uma frase;
   - **o que é**, em linguagem simples;
   - **quando usar**: o cenário de mercado e se a vol está cara ou barata;
   - **como montar**: as pernas, pela ordem do catálogo;
   - **exemplo com números**: o que acontece se a ação subir, ficar parada ou cair, o ponto de
     empate, o ganho e a perda máximos, e o **gráfico do resultado no vencimento**;
   - **o que pode dar errado**;
   - **no app**: onde ela aparece no Book e o botão "Montar uma <operação> no Montador", que abre
     o Montador com esse modelo escolhido. As estruturas que o Book não varre (straddle vendido,
     iron condor comprado, borboleta vendida) dizem isso e ficam só com o botão.
3. **Termos:** glossário com busca. Cada termo tem de uma a três frases, um exemplo curto e onde
   ele aparece no app. No mínimo: call, put, strike, prêmio, vencimento, dias úteis, lote,
   exercício, atribuição, pó, americana e europeia, delta, gamma, theta, vega, IV, IV 30, HV 21,
   IV rank, percentil, vol cara, normal e barata, spread, negócios, preço executável, indicativo e
   teórico, preço de zerar, ao vivo, atrasado e fim de dia, Cadastro de Instrumentos, COTAHIST,
   custos e IR, anualizado, retorno sobre o risco, chance de lucro, probabilidade de exercício.
4. **Telas do app:** para que serve cada aba e o que diz cada indicador (o status do topo, os
   rótulos de preço, os avisos).

### 6.3 Exemplos

- **Fixos e inventados** (decisão de quem escreveu): PETR4 a R$ 50,00, lote de 100, prêmios
  plausíveis, marcados como exemplo e "sem custos nem IR". Não usam preço de mercado, para a
  explicação não mudar todo dia nem quebrar quando faltar dado.
- **Os números do exemplo saem da mesma conta do domínio:** um teste confere, para cada uma das
  18 operações, o ganho máximo, a perda máxima, o(s) ponto(s) de empate e o gráfico contra o
  payoff no vencimento do domínio (`Strategy`). Texto e gráfico nunca divergem.
- Exemplo do rascunho aprovado (venda coberta): compra de 100 PETR4 a R$ 50,00 e venda de 100
  calls de strike R$ 52,00 a R$ 1,00; recebe R$ 100; ganho máximo R$ 300 acima de R$ 52; empate
  em R$ 49,00; a R$ 45,00 perde R$ 400.

### 6.4 Textos

O construtor escreve os textos das 18 operações, dos termos e das telas em português simples. **O
autor revisa** os textos financeiros antes do merge (risco: explicação errada ensina errado).

### 6.5 O "?" pelo app

- **Obrigatório no Book:** as etiquetas de vol, os números grandes e pequenos dos cartões e os
  cabeçalhos da tabela compacta.
- Nas outras telas, onde o rótulo já existe e cabe um "?" sem poluir: os cabeçalhos da cadeia
  (IV, Delta), o resumo do Montador, a Carteira (preço de zerar). O construtor escolhe; o critério
  é não encher a tela de "?".
- Nos textos da aba Aprender, os termos do glossário ficam sublinhados e abrem o termo.

## 7. Riscos (anti-objetivos)

- **Explicação ou exemplo errado:** os números dos exemplos são conferidos por teste (§6.3) e o
  autor revisa os textos (§6.4).
- **Esconder do Book o que o autor usa para decidir:** todo número de hoje continua um clique
  abaixo (§5.4).
- **Inventar ranking entre famílias:** não fazer (§5.3).
- **Destaque com preço que não executa:** só item executável vira destaque (ADR-0004).
- **Book mais lento** (§5.6).
- **Consertar o layout de uma tela e deixar o mesmo problema em outra** (§4.3).

## 8. Critérios de pronto

1. Prints em 1280, 1366, 1920 e 2560 px do Montador com uma estrutura montada, do "Registrar
   operação", do Book, da aba Aprender (as quatro sub-abas) e de Arquivos B3: sem tabela principal
   cortada, sem painel esticado, ticker inteiro no campo Série, "Salvar" logo abaixo das pernas.
2. Book: título novo, preset fechado, vol em etiquetas, um cartão por família (ou "Nada hoje"),
   abas compactas com linha expansível que mostra todos os números de antes; "?" leva ao termo.
3. Aprender: quatro sub-abas com endereço próprio; as 18 operações com todos os blocos do §6.2;
   glossário com busca e âncoras; "Montar no Montador" abre o modelo certo.
4. Teste dos exemplos das 18 operações contra o payoff do domínio.
5. Arquivos B3: a rotina com os dois links do autor e o estado de cada arquivo.
6. Textos revisados pelo autor.
7. Gates: pytest com cobertura, mypy, ruff, ruff format, import-linter; frontend `verificar` e
   `build`.

## 9. Fica com o construtor

- As larguras exatas e o ponto de troca do Montador (§4.1).
- Como calcular ganha até, perde até e chance de lucro dos itens do Book sem duplicar o Montador
  (§5.3, §5.6).
- As frases curtas do porquê por estrutura (§5.3).
- Como servir o gráfico e os números dos exemplos da aba Aprender a partir do domínio, reusando o
  `GraficoPayoff` onde der (§6.3).
- Os textos das operações, dos termos e das telas, para a revisão do autor (§6.4).
- Onde mais o "?" entra além do Book (§6.5).
