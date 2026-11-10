# Montador simples: menos informação à vista, cores suaves (desenho)

Data: 2026-11-09. Pedido do autor: "Quero deixar mais simples de entender algumas telas como a
por exemplo do montador. Tem muita informação parece ou então está mal espaçado, as cores e as
muitas informações estão poluindo muito."

Este desenho cobre **só o Montador** e a regra de cor do app. As outras telas (Mercado, Book,
Carteira) entram depois, cada uma com o seu desenho, herdando a regra de cor daqui.

As decisões da §2 são do autor e foram tomadas sobre rascunhos visuais em 09/11. As demais são
minhas, para o autor conferir ao ler.

## 1. Intenção e diagnóstico

O Montador mostra tudo de uma vez e com o mesmo peso. Lido no código da `development` em 09/11
(`fa4a8c7`):

1. **Cadeia larga demais.** São 15 colunas: "+", 6 da call, strike, 6 da put e "+". O resultado
   só fica ao lado da cadeia a partir de 1780 px (`tema.css`, `.montador-corpo`). Em qualquer
   notebook ele fica abaixo da cadeia inteira.
2. **Ordem invertida no resultado.** A ordem é pernas → Salvar/Registrar → simulações →
   análise. As ações aparecem antes de você ver o que está fazendo.
3. **Números demais com o mesmo peso.** Aparecem juntos a frase, 6 números (ganho, perda,
   custos, IR, chance, dias úteis), 4 gregas, os avisos, o gráfico e a grade de cenários.
4. **Cor em quase todo número.** Na cadeia, toda compra é azul e toda venda é vermelha. Na grade
   de cenários, toda célula é verde ou vermelha.
5. **Vencimento escolhido em três lugares:** o seletor "Vencimento" do topo, a fileira de botões
   de vencimentos da cadeia e as abas da cadeia.

## 2. Decisões do autor

| Tema | Decisão |
|---|---|
| Público | A tela abre no modo simples, com "ver detalhes" para quem quer mais. Não é um modo global: vale só para este desenho. |
| Layout | **B**: duas colunas, com a cadeia enxuta à esquerda e o resultado à direita. |
| Cores | **Suave**: as cores de hoje (compra/venda, alta/baixa), em tons mais apagados. Não é a opção "neutro". |
| Números à vista | **Ganho máximo · Perda máxima · Chance de lucro.** Quanto recebe ou paga agora já está na frase. |
| Vencimento | **Só o seletor do topo.** Ele manda no modelo pronto e na cadeia. |

## 3. Objetivos (o que se constrói)

### A. Cadeia enxuta no Montador

- `TabelaCadeia` ganha a opção `enxuta`. O Montador a usa; o **Mercado continua com a cadeia
  completa**, sem nenhuma mudança de colunas.
- Na enxuta, as colunas são: "+" · Compra · Venda (call) · Strike · Venda · Compra (put) · "+".
- O link "mostrar IV, delta e negócios" abre as outras colunas (Último, IV, Delta, Neg.) e passa
  a se chamar "esconder IV, delta e negócios". O estado fica guardado no navegador
  (`localStorage`, com leitura e escrita protegidas por `try/catch`; sem ele, começa fechado).
- A enxuta não tem a fileira de botões de vencimentos nem as abas. Ela mostra o vencimento
  escolhido no topo (objetivo B).
- O cabeçalho continua com o ativo, o spot, a fonte e a hora. A linha "no dinheiro" continua
  marcada. As séries rejeitadas continuam no `details` do pé.

### B. Vencimento único, no topo

- As opções do seletor "Vencimento" são **todos os vencimentos disponíveis** da cadeia
  (`cadeia.disponiveis`), não só os acompanhados. Os semanais aparecem marcados com "S", como na
  fileira de hoje.
- Valor padrão, sem escolha: o primeiro mensal, regra que já existe (`vencimentoDoModelo`).
- O Montador acompanha a cadeia só desse vencimento (`seguirCadeia(ativo, [vencimento])`).
- **Trocar o vencimento não mexe nas pernas.** Para montar com dois vencimentos, é só trocar o
  seletor e clicar no "+" de novo.
- O modelo pronto continua usando esse mesmo vencimento.

### C. Resultado simples, com "ver detalhes"

O cartão do resultado tem, de cima para baixo:

1. O título (nome da estrutura, vencimento, fonte dos preços), como hoje.
2. **A frase**, com o mesmo texto de hoje (`frase()` não muda; o roteiro do teste de
   usabilidade conta com ela).
3. **Três números grandes:** Ganho máximo · Perda máxima · Chance de lucro, com o "?" do
   glossário onde ele já existe.
4. **O gráfico de payoff.**
5. **Os avisos** e o "Sem avaliação de hoje", sempre visíveis, porque mudam a leitura do
   resultado.
6. **"▸ ver detalhes"**, que abre os custos de montagem, o IR estimado (se ainda existir depois
   da mudança do valor bruto, §8), os dias úteis, as 4 gregas e a grade de cenários. O estado
   fica guardado no navegador, como no objetivo A, e começa fechado.

Ganho e perda usam o valor que a `development` tiver depois da mudança do IR (§8). Se continuarem
existindo as versões bruta e líquida, entra a bruta, como o autor pediu nessa mudança.

### D. Ordem da coluna da direita

1. Cartão do resultado (C). Antes de existir uma perna, ele dá lugar à dica de hoje: "Escolha
   um modelo pronto ou clique em + numa série da cadeia…".
2. Cartão das pernas: a tabela de hoje e, embaixo, **"Registrar como executada"** (botão
   principal) e o nome + "Salvar simulação" (secundário).
3. Simulações salvas, recolhidas, como hoje.

A faixa da rolagem (vinda dos Alertas) continua no topo da página.

### E. Cores suaves e espaçamento (vale para o app inteiro)

- Entra a cor `--destaque` (o azul forte de hoje, `#1e88e5`). Ela fica com os links, o menu
  ativo, o vencimento selecionado, a borda de foco e o botão principal. Hoje esses lugares usam
  `--compra`.
- `--compra`, `--venda`, `--alta` e `--baixa` passam para tons mais apagados. Valores do
  rascunho aprovado: compra `#7fb3e6`, venda `#e09a98`, alta `#5fbfb4`, baixa `#e5807e`. Na
  implementação, cada um precisa de contraste de pelo menos 4,5:1 sobre `--fundo` e `--painel`.
- A regra "cor nunca é a única pista" do `tema.css` continua valendo: todo estado também vem
  escrito.
- No Montador, cada bloco vira um cartão (fundo `--painel`, borda, cantos arredondados e
  respiro interno), com o mesmo espaço entre os cartões.
- Nova classe `.botao-principal` para o botão de destaque.

### F. Quando cadeia e resultado ficam lado a lado

- Lado a lado a partir de cerca de 1280 px de janela. O número final sai da medida da cadeia
  enxuta com o Segoe UI no Windows, anotada no CSS como a de hoje.
- Abaixo disso, a cadeia fica em cima e o resultado embaixo, e a rolagem até a montagem quando
  ela chega de fora da cadeia (semana 5, objetivo C) continua valendo.

### G. Documentação

- Aprender → "Telas do app": o texto do Montador passa a descrever a tela nova.
- README, ROADMAP e HANDOFF: uma linha cada.

## 4. Não-objetivos

- Simplificar a estrutura do Mercado, do Book, da Carteira ou dos Alertas. Eles só recebem as
  cores suaves.
- Modo simples global ou chave no perfil.
- Tema claro.
- Mudar o texto da frase do resumo.

## 5. Anti-objetivos (fracasso mesmo funcionando)

- Mudar qualquer número: cálculo, preço, custo, IR ou chance. Este trabalho é só de tela.
- Atrapalhar o fluxo perna a perna: o "+" da cadeia **não** rola a tela, como hoje.
- Esconder um aviso que muda a leitura do resultado atrás de "ver detalhes".
- Tirar colunas da cadeia do Mercado.
- Deixar algum texto com contraste abaixo de 4,5:1 por causa das cores suaves.

## 6. Impacto

| Onde | Impacto |
|---|---|
| `paginas/Montador.tsx` | Layout, ordem, vencimento único e acompanhamento da cadeia por um vencimento só. |
| `componentes/TabelaCadeia.tsx` | Opção `enxuta`, com vencimento fixo vindo de fora. O padrão continua sendo a cadeia completa. |
| `componentes/ResumoEstrutura.tsx` | Separa a parte simples dos detalhes. **Mesmo arquivo da mudança do IR (§8).** |
| `componentes/GradeCenarios.tsx` | Vai para dentro dos detalhes. Só pega as cores suaves. |
| `tema.css` | `--destaque`, tons suaves, cartões e o novo ponto de quebra. |
| Mercado, Book, Carteira, Alertas, Aprender | Só as cores suaves, pelas variáveis. Conferir visualmente cada tela. |
| Testes do frontend | `Montador.test.tsx` (seletor de vencimento, rótulos dos números, detalhes fechados), `TabelaCadeia` (modo enxuto) e `Mercado` (continua completo). |
| Backend, APIs, jobs, arquivos de dados | Nenhum. |

## 7. Critérios de aceite

1. Numa janela de 1366 × 768, ao escolher um modelo pronto, a frase, os três números e o
   gráfico ficam visíveis sem rolar a página.
2. A cadeia do Montador mostra 7 colunas. "mostrar IV, delta e negócios" mostra as outras 4, e
   a escolha continua depois de recarregar a página.
3. A cadeia do Mercado continua com as 15 colunas, a fileira de vencimentos e as abas.
4. O Montador tem um único controle de vencimento. Trocar o vencimento troca a cadeia e mantém
   as pernas já postas.
5. "ver detalhes" começa fechado e, aberto, mostra custos, dias úteis, gregas e grade de
   cenários. A escolha continua depois de recarregar.
6. Avisos e "Sem avaliação de hoje" aparecem sem abrir os detalhes.
7. Os números são os mesmos de antes para o mesmo pedido: o golden do backend não muda, e um
   teste de tela confere os valores.
8. Links, menu ativo e botão principal continuam no azul forte. Os preços de compra e venda e os
   resultados de alta e baixa ficam nos tons suaves.
9. Os gates do frontend passam: `npm --prefix frontend run verificar` e `run build`.

## 8. Dependência e ordem

1. **A mudança do IR e do valor bruto, feita no outro PC, entra na `development` primeiro.** Ela
   mexe no `ResumoEstrutura` e nos números de ganho e perda, então começar antes dela é pedir
   conflito.
2. Atualizar a `development` local e abrir a `feat/montador-simples` a partir dela.
3. Plano de implementação a partir deste desenho.
4. Conferir na tela, a 1366 px e a 1920 px, no Windows.

## 9. Casos de teste

**Positivos**
- Modelo pronto "Put coberta" em PETR4: a frase, os 3 números e o gráfico aparecem, e os
  detalhes ficam fechados.
- "+" numa put da cadeia enxuta: a perna entra, o resultado é recalculado e a tela não rola.
- Trocar o vencimento com uma perna posta: a cadeia troca e a perna continua.
- Abrir os detalhes, recarregar: os detalhes continuam abertos.

**Negativos**
- Perna sem preço: a frase diz "Falta o preço de alguma perna…", e os números grandes não
  aparecem (como hoje, `no_vencimento` nulo).
- Cadeia indisponível: o aviso de hoje aparece no lugar da cadeia, e o seletor de vencimento
  fica desabilitado.
- `localStorage` bloqueado (janela anônima, por exemplo): a tela abre com tudo fechado, sem erro.

**De borda**
- Só semanais disponíveis: o padrão é o primeiro da lista, marcado com "S".
- Ganho ou perda ilimitados: o número grande mostra "ilimitado".
- Estrutura com a ação (venda coberta): a linha da ação aparece no cartão das pernas, como hoje.
- Janela 1 px abaixo e 1 px acima do ponto de quebra medido (objetivo F): empilhado e lado a
  lado, respectivamente, sem rolagem horizontal da página.
