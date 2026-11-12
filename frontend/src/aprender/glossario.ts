/**
 * O glossário da aba Aprender. Os "?" do app levam a `/aprender/termos#<id>`, então os ids não mudam.
 * O arquivo não se chama `termos.ts`: no Windows, que não diferencia maiúsculas, o import
 * `./Termos` acharia este arquivo em vez do componente `Termos.tsx`.
 * Nos textos, `[palavra](id)` vira um link para outro termo (ver `ComTermos`).
 */
export type TermoGlossario = {
  id: string;
  titulo: string;
  texto: string;
  exemplo: string;
  onde: string;
};

export const TERMOS: TermoGlossario[] = [
  {
    id: "call",
    titulo: "Call",
    texto:
      "Uma opção de compra. Quem compra a call ganha o direito de comprar a ação pelo [strike](strike) até o [vencimento](vencimento). Quem vende a call recebe o [prêmio](premio) e fica obrigado a vender a ação se a call for exercida.",
    exemplo:
      "Com uma call de PETR4 de strike R$ 52,00, quem tem a call pode comprar PETR4 a R$ 52,00, mesmo que ela esteja a R$ 55,00.",
    onde: "Na cadeia do Mercado e do Montador, as calls ficam à esquerda do strike.",
  },
  {
    id: "put",
    titulo: "Put",
    texto:
      "Uma opção de venda. Quem compra a put ganha o direito de vender a ação pelo [strike](strike) até o [vencimento](vencimento). Quem vende a put recebe o [prêmio](premio) e fica obrigado a comprar a ação se a put for exercida.",
    exemplo:
      "Com uma put de PETR4 de strike R$ 48,00, quem tem a put pode vender PETR4 a R$ 48,00, mesmo que ela tenha caído para R$ 45,00.",
    onde: "Na cadeia do Mercado e do Montador, as puts ficam à direita do strike.",
  },
  {
    id: "strike",
    titulo: "Strike",
    texto:
      "O preço combinado na opção: o preço pelo qual a ação é comprada (na call) ou vendida (na put) no [exercício](exercicio). Quando a empresa paga dividendos ou JCP, a B3 reduz o strike pelo valor pago.",
    exemplo: "Na call de PETR4 de strike R$ 52,00, o direito é comprar a ação a R$ 52,00.",
    onde: "Na coluna Strike, no meio da cadeia, e nas pernas do Montador e da Carteira.",
  },
  {
    id: "premio",
    titulo: "Prêmio",
    texto:
      "O preço da opção. Quem compra paga o prêmio na hora; quem vende recebe. O prêmio da tela é por opção: multiplique pela quantidade.",
    exemplo: "Vender 100 calls a R$ 1,14 rende R$ 114,00 de prêmio.",
    onde:
      "Nas colunas Compra, Venda e Último da cadeia, e no preço de cada perna do Montador e da Carteira.",
  },
  {
    id: "vencimento",
    titulo: "Vencimento",
    texto:
      "A data em que a opção acaba. Depois dela, a opção deixa de existir: ou foi exercida, ou virou [pó](po). As opções mensais de ações vencem na terceira sexta-feira do mês (no dia útil anterior, se for feriado); alguns ativos têm também vencimentos semanais.",
    exemplo: "Uma call de PETR4 que vence em 19/11 vale até o pregão de 19/11.",
    onde:
      "Nas abas de vencimento da cadeia, com os [dias úteis](dias-uteis) que faltam, por exemplo \"19/11 (15 du)\".",
  },
  {
    id: "dias-uteis",
    titulo: "Dias úteis",
    texto:
      "Os dias com pregão na B3, sem fins de semana nem feriados. O app conta o prazo das opções em dias úteis (\"du\") e usa 252 dias úteis por ano.",
    exemplo: "De uma segunda-feira até a segunda seguinte há 5 dias úteis, se não houver feriado.",
    onde: "Ao lado de cada vencimento e nos números do Book e do Montador.",
  },
  {
    id: "lote",
    titulo: "Lote",
    texto:
      "A quantidade padrão de negociação. Nas opções de ações, o lote é de 100 opções, e cada opção vale por uma ação.",
    exemplo:
      "Vender 1 lote de calls de PETR4 é vender 100 calls; se elas forem exercidas, você entrega 100 ações.",
    onde:
      "Na quantidade das pernas do Montador e da Carteira, e na família Proteção do Book, que protege a posição de 100 em 100 ações.",
  },
  {
    id: "exercicio",
    titulo: "Exercício",
    texto:
      "Usar o direito da opção: quem tem a [call](call) compra a ação pelo [strike](strike); quem tem a [put](put) vende a ação pelo strike. No [vencimento](vencimento), a opção que vale a pena exercer costuma ser exercida. Para a Receita, o prêmio entra no preço da ação.",
    exemplo:
      "Com a call de strike R$ 52,00 e PETR4 a R$ 55,00, exercer é comprar a R$ 52,00 uma ação que vale R$ 55,00.",
    onde:
      "Na Carteira, o botão Exercício transforma a opção em ações, com o prêmio no preço, como a Receita trata.",
  },
  {
    id: "atribuicao",
    titulo: "Atribuição",
    texto:
      "O outro lado do [exercício](exercicio): quem vendeu a opção é escolhido para cumprir a obrigação. Na [call](call) vendida, você vende a ação pelo [strike](strike); na [put](put) vendida, você compra a ação pelo strike.",
    exemplo:
      "Você vendeu a call de strike R$ 52,00 e PETR4 fechou a R$ 55,00 no vencimento: você vende as suas ações a R$ 52,00.",
    onde:
      "Na Carteira, pelo botão Exercício: a atribuição registra a venda ou a compra das ações, com o prêmio no preço.",
  },
  {
    id: "po",
    titulo: "Pó",
    texto:
      "A opção que vence sem valer nada, porque ninguém ganharia exercendo. Para quem vendeu, é o melhor resultado: fica com o [prêmio](premio) inteiro. Para quem comprou, é a perda do prêmio.",
    exemplo: "A call de strike R$ 52,00 vira pó se PETR4 fechar a R$ 50,00 no vencimento.",
    onde:
      "Na Carteira, depois do vencimento: a opção que fechou fora do dinheiro vira pó sozinha, pelo [COTAHIST](cotahist) do dia do vencimento. Até ele chegar, ela fica aguardando o fechamento.",
  },
  {
    id: "americana-europeia",
    titulo: "Americana e europeia",
    texto:
      "A opção americana pode ser exercida em qualquer dia até o [vencimento](vencimento); a europeia, só no vencimento. O estilo de cada série vem do [Cadastro de Instrumentos](cadastro). Na B3, as calls de ações são quase todas americanas.",
    exemplo:
      "Uma call americana de PETR4 pode ser exercida antes do vencimento, por exemplo às vésperas de um dividendo.",
    onde:
      "No aviso \"call americana avaliada como europeia\", no Book e no Montador: o app calcula essa call como se fosse europeia, uma aproximação. As puts americanas ficam fora do Book.",
  },
  {
    id: "delta",
    titulo: "Delta",
    texto:
      "Quanto o preço da opção muda quando a ação sobe R$ 1. Vai de 0 a 1 na call e de 0 a -1 na put. Também dá uma ideia aproximada da chance de a opção terminar valendo alguma coisa.",
    exemplo: "Uma call com delta 0,50 sobe uns R$ 0,50 quando PETR4 sobe R$ 1,00.",
    onde:
      "Na coluna Delta da cadeia; no Montador, o delta da estrutura, em ações equivalentes; nos critérios do Book, a faixa de delta das opções vendidas.",
  },
  {
    id: "gamma",
    titulo: "Gamma",
    texto:
      "Quanto o [delta](delta) muda quando a ação sobe R$ 1. Gamma alto quer dizer que o resultado muda depressa com o preço, o que é comum perto do vencimento e do strike.",
    exemplo: "Com gamma de 0,10, se PETR4 sobe R$ 1,00, um delta de 0,50 vira uns 0,60.",
    onde: "Nas gregas do Montador.",
  },
  {
    id: "theta",
    titulo: "Theta",
    texto:
      "Quanto a operação ganha ou perde com a passagem do tempo, se nada mais mudar. Quem compra opção perde com o tempo; quem vende ganha.",
    exemplo:
      "Com theta de -R$ 5,00 por dia útil, a estrutura perde uns R$ 5,00 de um dia útil para o outro, com o resto parado.",
    onde: "No Montador, em \"Theta por dia útil\", em reais.",
  },
  {
    id: "vega",
    titulo: "Vega",
    texto:
      "Quanto a operação ganha ou perde se a [IV](iv) subir 1 ponto. Quem compra opção ganha quando a IV sobe; quem vende perde.",
    exemplo: "Com vega de R$ 8,00 por ponto, se a IV passa de 30% para 31%, a estrutura ganha uns R$ 8,00.",
    onde: "No Montador, em \"Vega por ponto\", em reais.",
  },
  {
    id: "iv",
    titulo: "IV (vol implícita)",
    texto:
      "A volatilidade que o preço da opção embute: o quanto o mercado espera que a ação balance até o vencimento, em ritmo de um ano. Opção cara tem IV alta; opção barata, IV baixa. O app calcula a IV de cada série pelo modelo de Black-Scholes.",
    exemplo:
      "IV de 30% quer dizer que o mercado espera que PETR4 balance uns 30% num ano, para cima ou para baixo.",
    onde: "Na coluna IV da cadeia, no smile da aba Análise do Mercado e nos números do Book.",
  },
  {
    id: "iv-30",
    titulo: "IV 30",
    texto:
      "A [IV](iv) para um prazo fixo de 30 dias úteis, tirada dos vencimentos de antes e de depois desse prazo. Serve para comparar a vol de um dia com a de outro, mesmo com os vencimentos mudando. Sem vencimento depois dos 30 dias úteis, ela é estendida e vem marcada.",
    exemplo:
      "Se o vencimento de 20 dias úteis tem IV de 30% e o de 40 dias úteis tem 34%, a IV 30 fica perto de 32,7%.",
    onde:
      "Na aba Análise do Mercado e nas etiquetas de vol do Book (ao passar o mouse).",
  },
  {
    id: "hv-21",
    titulo: "HV 21",
    texto:
      "A volatilidade que a ação teve de verdade nos últimos 21 pregões (cerca de um mês), em ritmo de um ano. É a vol realizada, para comparar com a [IV 30](iv-30).",
    exemplo: "Se PETR4 balançou muito no último mês, a HV 21 sobe; se ficou parada, cai.",
    onde:
      "Na aba Análise do Mercado (a linha contra a IV 30) e nas etiquetas de vol do Book (ao passar o mouse).",
  },
  {
    id: "iv-rank",
    titulo: "IV rank",
    texto:
      "Onde a [IV 30](iv-30) de hoje está entre a menor e a maior do último ano (252 pregões): 0% é a menor do ano e 100% é a maior. Precisa de pelo menos 60 pregões de histórico.",
    exemplo:
      "Se a IV 30 de PETR4 foi de 20% a 40% no ano e hoje está em 35%, o IV rank é de 75%.",
    onde: "Na aba Análise do Mercado, nas etiquetas de vol do Book e nas Direcionais do Book.",
  },
  {
    id: "percentil",
    titulo: "Percentil",
    texto:
      "A parte dos pregões do último ano em que a [IV 30](iv-30) ficou abaixo da de hoje. Diferente do [IV rank](iv-rank), ele não se deixa levar por um único dia de vol muito alta ou muito baixa.",
    exemplo:
      "Percentil de 80% quer dizer que, em 80% dos pregões do último ano, a IV 30 esteve abaixo da de hoje.",
    onde: "Na aba Análise do Mercado e nas etiquetas de vol do Book (ao passar o mouse).",
  },
  {
    id: "vol-cara-barata",
    titulo: "Vol cara, normal e barata",
    texto:
      "Como o app resume a volatilidade de um ativo. Cara: o [IV rank](iv-rank) está em 50% ou mais e a [IV 30](iv-30) não está abaixo da [HV 21](hv-21). Barata: o IV rank está em 30% ou menos e a IV 30 não está acima da HV 21. Normal: o resto. Sem histórico para o IV rank, o app compara só a IV 30 com a HV 21, com folga de 10%, e avisa \"pela HV\".",
    exemplo:
      "\"PETR4 · vol cara\": as opções de PETR4 estão caras perto do que a ação tem balançado. Vender opção rende mais; comprar sai mais caro.",
    onde: "Nas etiquetas do topo do Book. É ela que decide o que entra na família Volatilidade.",
  },
  {
    id: "spread",
    titulo: "Spread",
    texto:
      "A diferença entre o melhor preço de venda e o melhor preço de compra da opção no livro de ofertas. Spread grande quer dizer que entrar e sair custa caro. O app mede o spread em % do preço do meio.",
    exemplo:
      "Oferta de compra a R$ 1,72 e de venda a R$ 1,94: o spread é de R$ 0,22, uns 12% do preço do meio (R$ 1,83).",
    onde: "Nos critérios do Book (spread máximo) e no [preço executável](preco-executavel).",
  },
  {
    id: "negocios",
    titulo: "Negócios",
    texto:
      "Quantos negócios a série teve no pregão. Mais negócios quer dizer mais fácil comprar e vender perto do preço da tela.",
    exemplo: "Uma série com 300 negócios no dia é bem negociada; com 2, pode ser difícil sair dela.",
    onde: "Na coluna Neg. da cadeia e nos critérios do Book (mínimo de negócios).",
  },
  {
    id: "preco-executavel",
    titulo: "Preço executável, indicativo e teórico",
    texto:
      "De onde vem o preço que o app usa. Executável: a oferta do livro pelo lado certo, o que você conseguiria agora (compra pela oferta de venda, venda pela oferta de compra). Indicativo: o último negócio, que pode estar velho. Teórico: calculado pelo modelo com a [IV](iv) das séries vizinhas, quando não há preço nenhum.",
    exemplo:
      "Para vender uma call com oferta de compra a R$ 1,72 e oferta de venda a R$ 1,94, o preço executável é R$ 1,72.",
    onde:
      "Na origem do preço de cada perna do Montador e no Book, que só destaca operação com preço executável.",
  },
  {
    id: "preco-de-zerar",
    titulo: "Preço de zerar",
    texto:
      "O preço pelo qual você encerraria a posição agora: a opção comprada é vendida pela oferta de compra do livro, e a vendida é recomprada pela oferta de venda. É o preço que a Carteira usa no resultado.",
    exemplo: "Você vendeu uma call; para zerar, recompra pela oferta de venda da tela, por exemplo R$ 1,94.",
    onde: "Na Carteira, na coluna Preço de zerar e no resultado não realizado de cada operação.",
  },
  {
    id: "ao-vivo-fim-de-dia",
    titulo: "Ao vivo, atrasado e fim de dia",
    texto:
      "De onde vêm os preços da tela. Ao vivo: do Tryd, na hora. Atrasado: a ligação com o Tryd está lenta ou o Tryd ainda não entrega dados, então os preços podem estar velhos. Fim de dia: o fechamento do último pregão, pelos arquivos da B3, quando o Tryd está fechado.",
    exemplo:
      "À noite, com o Tryd fechado, a tela mostra \"Fim de dia (B3)\" com os preços de fechamento. Não monte operação por esses preços.",
    onde: "No indicador do topo da tela e no rótulo dos preços do Montador e da Carteira.",
  },
  {
    id: "cadastro",
    titulo: "Cadastro de Instrumentos",
    texto:
      "O arquivo da B3 com todas as séries de opções que existem: o ativo, o tipo, o strike, o vencimento e o estilo (americana ou europeia). Sem ele, o app não monta a cadeia. Baixe uma vez por semana: é o pesquisa-pregao.zip.",
    exemplo:
      "Uma série lançada nesta semana só aparece na cadeia depois que você baixa o Cadastro novo.",
    onde:
      "Na aba Arquivos B3, na rotina da semana. O topo da tela avisa quando ele passa de 5 dias úteis.",
  },
  {
    id: "cotahist",
    titulo: "COTAHIST",
    texto:
      "O arquivo da B3 com o fechamento de cada pregão: os preços da ação e de cada opção. O app usa o COTAHIST para o fim de dia, para o histórico de vol ([IV rank](iv-rank), [HV 21](hv-21)), para o Book e para o vencimento na Carteira. Baixe o anual do ano corrente uma vez por semana.",
    exemplo: "O COTAHIST_A2026.zip traz todos os pregões de 2026 até o último.",
    onde: "Na aba Arquivos B3, na rotina da semana.",
  },
  {
    id: "custos-ir",
    titulo: "Custos e IR",
    texto:
      "O que sai da sua conta além do prêmio. Custos: os emolumentos da B3 em cada ordem e a corretagem, se houver. IR: o imposto de renda sobre o ganho do mês. No Montador e no Book, os números são brutos, como a corretora mostra: os custos aparecem à parte e o IR não é descontado. O IR fica no [IR mensal](ir-mensal), onde o prejuízo de um mês abate o ganho dos seguintes.",
    exemplo: "Numa venda de 100 calls a R$ 1,14 (R$ 114,00), os emolumentos ficam em uns R$ 0,15.",
    onde: "No Montador, em Custos de montagem; o IR, na Carteira, na aba IR mensal.",
  },
  {
    id: "ir-mensal",
    titulo: "IR mensal",
    texto:
      "A estimativa do imposto de renda das suas opções, mês a mês. Entra o resultado de cada opção encerrada ou que virou [pó](po), já com os custos. O preço médio é por série: se a mesma série está em duas operações, as duas entram juntas. Operação comum paga 15% e day trade (comprar e vender a mesma série no mesmo dia) paga 20%. O prejuízo de um mês abate o ganho dos meses seguintes, cada tipo com o seu. IR abaixo de R$ 10 não se paga na hora: soma com o IR dos meses seguintes até chegar a R$ 10. O [exercício](exercicio) e a [atribuição](atribuicao) não entram: o prêmio vai para o preço da ação. É estimativa, não o cálculo do imposto: ficam de fora as ações, o IR retido na fonte e o prejuízo de antes do app.",
    exemplo:
      "Em outubro, um prejuízo comum de R$ 52,00 e um day trade de R$ 28,00 dão R$ 5,60 de IR, que fica para novembro. Em novembro, um ganho comum de R$ 137,00 menos os R$ 52,00 dá R$ 85,00 de base e R$ 12,75 de IR; com os R$ 5,60 de outubro, o DARF fica em R$ 18,35, até o último dia útil de dezembro.",
    onde: "Na Carteira, na aba IR mensal.",
  },
  {
    id: "stop-e-alvo",
    titulo: "Stop e alvo",
    texto:
      "Dois limites em reais que você põe numa operação para o app avisar. O stop é a perda que você aceita; o alvo, o ganho em que pensa sair. O app compara com o resultado total da operação: o que já foi realizado, com os custos, mais o que daria zerar o resto agora, pelo [preço de zerar](preco-de-zerar). O app só avisa: quem encerra é você, na corretora.",
    exemplo:
      "Uma trava com stop de R$ 200,00: se o realizado é R$ -150,00 e zerar o resto agora daria R$ -60,00, o total é R$ -210,00, e o alerta de stop aparece.",
    onde: "No registro da operação e no botão Stop e alvo da Carteira; os alertas aparecem na aba Alertas.",
  },
  {
    id: "risco-de-exercicio",
    titulo: "Risco de exercício",
    texto:
      "A chance de uma opção que você vendeu ser exercida contra você, perto do [vencimento](vencimento). O app avisa quando a opção vendida está dentro do dinheiro (a ação passou do [strike](strike)) ou a menos de 2% dele, a 5 [dias úteis](dias-uteis) ou menos do vencimento. Os dois números mudam nos limites da aba Alertas. Se for exercida, vem a [atribuição](atribuicao): você vende a ação (na call) ou compra (na put) pelo strike.",
    exemplo:
      "Uma put de PETR4 vendida com strike R$ 28,00, com a ação a R$ 28,30 e 2 dias úteis até o vencimento, está a menos de 2% do strike: o alerta aparece.",
    onde: "Na aba Alertas, com os botões Abrir na Carteira e Rolar.",
  },
  {
    id: "rolagem",
    titulo: "Rolagem",
    texto:
      "Trocar uma operação que está vencendo pela mesma operação num [vencimento](vencimento) mais longe: zerar as pernas atuais e abrir as novas. Serve para não ser exercido ou para seguir recebendo [prêmio](premio). O app mostra o custo de zerar as pernas atuais pelo [preço de zerar](preco-de-zerar) e abre no Montador a mesma estrutura no vencimento seguinte, com os preços do momento. Nada é enviado: as duas ordens são suas, na corretora.",
    exemplo:
      "Uma put vendida de novembro que custa R$ 35,00 para recomprar, rolada para uma de dezembro que paga R$ 60,00: a rolagem dá R$ 25,00 de caixa.",
    onde: "No botão Rolar da aba Alertas, que abre o Montador com uma faixa no topo.",
  },
  {
    id: "anualizado",
    titulo: "Anualizado",
    texto:
      "O retorno de uma operação levado para o prazo de um ano, com juros compostos, para comparar operações de prazos diferentes entre si e com o CDI. Usa 252 [dias úteis](dias-uteis) por ano.",
    exemplo: "Ganhar 1% em 21 dias úteis equivale a uns 12,7% ao ano.",
    onde: "No critério da família Renda do Book.",
  },
  {
    id: "retorno-sobre-risco",
    titulo: "Retorno sobre o risco",
    texto:
      "Quanto você pode ganhar perto do que está arriscando: o ganho dividido pela perda máxima. Serve para comparar travas entre si.",
    exemplo:
      "Uma trava que ganha até R$ 40,00 e perde até R$ 160,00 tem retorno sobre o risco de 25%.",
    onde: "No critério das travas da família Renda e das Direcionais com visão, no Book.",
  },
  {
    id: "chance-de-lucro",
    titulo: "Chance de lucro",
    texto:
      "A chance de a operação terminar com lucro no vencimento, calculada pelo modelo com a [IV](iv) de hoje, sem custos nem IR. É uma estimativa do modelo, não uma previsão.",
    exemplo:
      "Chance de lucro de 70%: pelo modelo, em 7 de cada 10 cenários a operação termina no lucro.",
    onde: "No Montador e nos cartões e na tabela do Book.",
  },
  {
    id: "probabilidade-de-exercicio",
    titulo: "Probabilidade de exercício",
    texto:
      "A chance, pelo modelo, de a opção vendida terminar valendo a pena para quem a comprou e ser exercida no vencimento. Também é uma estimativa do modelo, não uma previsão.",
    exemplo:
      "Uma call vendida com probabilidade de exercício de 25%: pelo modelo, uma vez em quatro você teria de vender as ações.",
    onde: "Nos números da família Renda do Book.",
  },
  {
    id: "empate",
    titulo: "Ponto de empate",
    texto:
      "O preço da ação no vencimento em que a operação não ganha nem perde. Algumas operações têm dois pontos de empate, um de cada lado. Também é chamado de breakeven.",
    exemplo:
      "Na venda coberta com PETR4 comprada a R$ 50,00 e prêmio de R$ 1,14, o empate é em R$ 48,86.",
    onde:
      "No resumo e no gráfico do Montador, nos exemplos do Aprender e nos números do Book (breakeven).",
  },
  {
    id: "ganho-perda-maximos",
    titulo: "Ganho e perda máximos",
    texto:
      "O máximo que a operação pode ganhar e o máximo que pode perder no vencimento, sem [custos nem IR](custos-ir), como a corretora mostra. \"Sem limite\" quer dizer que não há teto.",
    exemplo:
      "Na venda coberta do exemplo do Aprender, o ganho máximo é R$ 314,00 e a perda máxima é R$ 4.886,00.",
    onde: "Nos cartões e na tabela do Book (ganha até e perde até) e no Montador.",
  },
];

export function termoPorId(id: string): TermoGlossario | undefined {
  return TERMOS.find((termo) => termo.id === id);
}
