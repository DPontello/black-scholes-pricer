/**
 * Os textos de cada operação do catálogo do Montador, sem número: os números do exemplo vêm da API.
 * `etiquetas` são três, na ordem: o que é preciso ter, o cenário e o risco em uma frase (a família
 * vem do exemplo). A chave é a de `TEMPLATES`. Nos textos, `[palavra](id)` vira link para o termo
 * do glossário (`termos.ts`).
 */
export type TextoOperacao = {
  etiquetas: string[];
  oQueE: string;
  quandoUsar: string;
  comoMontar: string;
  oQuePodeDarErrado: string;
  noApp: string;
};

const SO_NO_MONTADOR =
  "O Book não varre esta operação: ela só se monta no Montador, onde você escolhe o modelo e o app sugere os strikes.";

const NO_MONTADOR = "No Montador, você escolhe o modelo e o app sugere os strikes.";

function noBook(familia: string): string {
  return `Aparece no Book, na família ${familia}. ${NO_MONTADOR}`;
}

// As estruturas de Volatilidade só entram no Book conforme a vol do ativo (e o critério do preset).
function noBookSe(condicao: string): string {
  return `Pode aparecer no Book, na família Volatilidade, ${condicao}. ${NO_MONTADOR}`;
}

export const TEXTOS_OPERACOES: Record<string, TextoOperacao> = {
  venda_coberta: {
    etiquetas: [
      "você precisa ter a ação",
      "para mercado parado ou subindo devagar",
      "risco: a ação cair (o prêmio só amortece)",
    ],
    oQueE:
      "Você tem a ação e vende a alguém o direito de comprá-la de você por um preço combinado (o [strike](strike)) até o [vencimento](vencimento). Em troca, recebe um dinheiro na hora: o [prêmio](premio).",
    quandoUsar:
      "Quando você já tem a ação (ou quer ter) e acha que ela vai ficar parada ou subir devagar até o [vencimento](vencimento). Rende mais quando a [vol está cara](vol-cara-barata).",
    comoMontar:
      "Compra as ações (ou usa as que você já tem) e vende uma call com strike acima do preço atual.",
    oQuePodeDarErrado:
      "Se a ação cair, você perde: o prêmio só amortece a queda. Se ela subir acima do strike, você é obrigado a vender ([atribuição](atribuicao)) e deixa de ganhar o resto da alta.",
    noApp: noBook("Renda"),
  },
  put_coberta: {
    etiquetas: [
      "você precisa ter o caixa para comprar a ação",
      "para mercado parado ou subindo",
      "risco: a ação cair abaixo do strike",
    ],
    oQueE:
      "Você vende a alguém o direito de vender a ação para você, por um preço combinado (o [strike](strike)), até o [vencimento](vencimento). Em troca, recebe o [prêmio](premio) na hora. Você guarda o caixa para o caso de ter de comprar a ação.",
    quandoUsar:
      "Quando você aceitaria comprar a ação por esse preço e acha que ela vai ficar parada ou subir. Se nada acontecer, você fica com o prêmio. Rende mais quando a [vol está cara](vol-cara-barata).",
    comoMontar: "Vende uma put com strike abaixo do preço atual e guarda o caixa para comprar a ação.",
    oQuePodeDarErrado:
      "Se a ação cair abaixo do strike, você é obrigado a comprá-la ([atribuição](atribuicao)) por um preço mais alto do que o mercado paga naquele momento. O prêmio amortece a perda, mas não a evita.",
    noApp: noBook("Renda"),
  },
  trava_alta_put: {
    etiquetas: [
      "você precisa de margem (garantia) para a perda máxima",
      "para a ação não cair",
      "risco: a ação cair (a perda é limitada)",
    ],
    oQueE:
      "Você vende uma [put](put) e compra outra, mais barata, com strike menor. Recebe a diferença na hora. A put comprada limita a sua perda.",
    quandoUsar:
      "Quando você acha que a ação vai ficar parada ou subir, ou ao menos não cair muito, e quer uma perda com limite. Rende mais quando a [vol está cara](vol-cara-barata).",
    comoMontar:
      "Compra uma put com strike mais baixo e vende outra com strike mais alto, abaixo do preço atual, as duas no mesmo vencimento.",
    oQuePodeDarErrado:
      "Se a ação cair abaixo do strike da put vendida, o seu ganho vai encolhendo e, além do [ponto de empate](empate), vira perda. Abaixo do strike da put comprada, a perda para de crescer: o máximo é a distância entre os dois strikes menos o que você recebeu.",
    noApp: noBook("Renda"),
  },
  trava_baixa_call: {
    etiquetas: [
      "você precisa de margem (garantia) para a perda máxima",
      "para a ação não subir",
      "risco: a ação subir (a perda é limitada)",
    ],
    oQueE:
      "Você vende uma [call](call) e compra outra, mais barata, com strike maior. Recebe a diferença na hora. A call comprada limita a sua perda.",
    quandoUsar:
      "Quando você acha que a ação vai ficar parada ou cair, ou ao menos não subir muito, e quer uma perda com limite. Rende mais quando a [vol está cara](vol-cara-barata).",
    comoMontar:
      "Vende uma call com strike acima do preço atual e compra outra com strike ainda maior, as duas no mesmo vencimento.",
    oQuePodeDarErrado:
      "Se a ação subir acima do strike da call vendida, o seu ganho vai encolhendo e, além do [ponto de empate](empate), vira perda. Acima do strike da call comprada, a perda para de crescer: o máximo é a distância entre os dois strikes menos o que você recebeu.",
    noApp: noBook("Renda"),
  },
  compra_call: {
    etiquetas: [
      "você precisa ter o prêmio",
      "para alta forte",
      "risco: perder o prêmio se a ação não subir",
    ],
    oQueE:
      "Você paga um [prêmio](premio) para ter o direito de comprar a ação por um preço combinado (o [strike](strike)) até o [vencimento](vencimento). Se a ação subir bastante, esse direito vale muito.",
    quandoUsar:
      "Quando você acha que a ação vai subir forte, e logo. Sai mais barata quando a [vol está barata](vol-cara-barata).",
    comoMontar: "Compra uma call com strike perto do preço atual.",
    oQuePodeDarErrado:
      "Se a ação ficar abaixo do strike no vencimento, você perde o prêmio inteiro: a call vira [pó](po). Entre o strike e o [ponto de empate](empate), você perde só parte do prêmio.",
    noApp: noBook("Direcionais"),
  },
  compra_put: {
    etiquetas: [
      "você precisa ter o prêmio",
      "para queda forte",
      "risco: perder o prêmio se a ação não cair",
    ],
    oQueE:
      "Você paga um [prêmio](premio) para ter o direito de vender a ação por um preço combinado (o [strike](strike)) até o [vencimento](vencimento). Se a ação cair bastante, esse direito vale muito.",
    quandoUsar:
      "Quando você acha que a ação vai cair forte, e logo. Sai mais barata quando a [vol está barata](vol-cara-barata).",
    comoMontar: "Compra uma put com strike perto do preço atual.",
    oQuePodeDarErrado:
      "Se a ação ficar acima do strike no vencimento, você perde o prêmio inteiro: a put vira [pó](po). Entre o [ponto de empate](empate) e o strike, você perde só parte do prêmio.",
    noApp: noBook("Direcionais"),
  },
  trava_alta_call: {
    etiquetas: [
      "você precisa ter o valor que vai pagar",
      "para alta moderada",
      "risco: perder o que pagou (e o ganho tem teto)",
    ],
    oQueE:
      "Você compra uma [call](call) e vende outra com strike maior. O que você recebe pela vendida paga parte da comprada, então a trava custa menos que a call sozinha. Em troca, o ganho tem um teto.",
    quandoUsar:
      "Quando você acha que a ação vai subir, mas não muito. A [vol](iv) pesa pouco, porque você compra e vende ao mesmo tempo.",
    comoMontar:
      "Compra uma call com strike perto do preço atual e vende outra com strike maior, as duas no mesmo vencimento.",
    oQuePodeDarErrado:
      "Se a ação não subir acima do strike da call comprada até o [vencimento](vencimento), você perde o que pagou. Se subir muito, o ganho para no strike da call vendida: você não aproveita o resto da alta.",
    noApp: noBook("Direcionais"),
  },
  trava_baixa_put: {
    etiquetas: [
      "você precisa ter o valor que vai pagar",
      "para queda moderada",
      "risco: perder o que pagou (e o ganho tem teto)",
    ],
    oQueE:
      "Você compra uma [put](put) e vende outra com strike menor. O que você recebe pela vendida paga parte da comprada, então a trava custa menos que a put sozinha. Em troca, o ganho tem um teto.",
    quandoUsar:
      "Quando você acha que a ação vai cair, mas não muito. A [vol](iv) pesa pouco, porque você compra e vende ao mesmo tempo.",
    comoMontar:
      "Vende uma put com strike mais baixo e compra outra com strike mais alto, perto do preço atual, as duas no mesmo vencimento.",
    oQuePodeDarErrado:
      "Se a ação não cair abaixo do strike da put comprada até o [vencimento](vencimento), você perde o que pagou. Se cair muito, o ganho para no strike da put vendida: você não aproveita o resto da queda.",
    noApp: noBook("Direcionais"),
  },
  straddle_comprado: {
    etiquetas: [
      "você precisa ter o prêmio das duas",
      "para movimento grande, para qualquer lado",
      "risco: perder tudo se a ação ficar parada",
    ],
    oQueE:
      "Você compra uma [call](call) e uma [put](put), no mesmo strike e no mesmo vencimento. Ganha se a ação andar bastante, para cima ou para baixo.",
    quandoUsar:
      "Quando você espera um movimento grande, mas não sabe para que lado. Sai mais barata quando a [vol está barata](vol-cara-barata).",
    comoMontar: "Compra uma call e uma put com o mesmo strike, perto do preço atual.",
    oQuePodeDarErrado:
      "Se a ação ficar parada, as duas opções viram [pó](po) e você perde tudo o que pagou. O movimento precisa ser grande o bastante para pagar o prêmio das duas.",
    noApp: noBookSe("quando a vol do ativo não está cara"),
  },
  straddle_vendido: {
    etiquetas: [
      "você precisa de margem (garantia) alta",
      "para mercado parado",
      "risco: perda sem limite se a ação andar muito",
    ],
    oQueE:
      "Você vende uma [call](call) e uma [put](put), no mesmo strike e no mesmo vencimento. Recebe os dois prêmios na hora. Ganha se a ação ficar perto do strike.",
    quandoUsar: "Quando você acha que a ação vai ficar parada. Rende mais quando a [vol está cara](vol-cara-barata).",
    comoMontar: "Vende uma call e uma put com o mesmo strike, perto do preço atual.",
    oQuePodeDarErrado:
      "Se a ação subir muito, a perda não tem limite. Se cair muito, a perda também é grande: só para quando a ação chega a zero. Por isso a corretora pede uma margem alta.",
    noApp: SO_NO_MONTADOR,
  },
  strangle_comprado: {
    etiquetas: [
      "você precisa ter o prêmio das duas",
      "para movimento grande",
      "risco: perder tudo se a ação ficar na faixa",
    ],
    oQueE:
      "Você compra uma [put](put) com strike abaixo do preço atual e uma [call](call) com strike acima. Ganha se a ação sair da faixa entre os dois strikes e passar do [ponto de empate](empate), para qualquer lado. Custa menos que o straddle, mas pede um movimento maior.",
    quandoUsar:
      "Quando você espera um movimento grande, para qualquer lado. Sai mais barata quando a [vol está barata](vol-cara-barata).",
    comoMontar: "Compra uma put com strike abaixo do preço atual e uma call com strike acima.",
    oQuePodeDarErrado:
      "Se a ação ficar entre os dois strikes até o [vencimento](vencimento), as duas opções viram [pó](po) e você perde tudo o que pagou. Fora da faixa, mas antes do [ponto de empate](empate), você perde só parte. O movimento precisa ser grande o bastante para pagar o que você pagou.",
    noApp: noBookSe("quando a vol do ativo não está cara"),
  },
  strangle_vendido: {
    etiquetas: [
      "você precisa de margem (garantia) alta",
      "para a ação ficar dentro da faixa",
      "risco: perda sem limite se a ação sair da faixa",
    ],
    oQueE:
      "Você vende uma [put](put) com strike abaixo do preço atual e uma [call](call) com strike acima. Recebe os dois prêmios na hora. Ganha se a ação ficar na faixa entre os dois strikes.",
    quandoUsar:
      "Quando você acha que a ação vai ficar na faixa. Rende mais quando a [vol está cara](vol-cara-barata). Recebe menos que no straddle vendido, mas a ação tem mais espaço para andar.",
    comoMontar: "Vende uma put com strike abaixo do preço atual e uma call com strike acima.",
    oQuePodeDarErrado:
      "Se a ação subir muito, a perda não tem limite. Se cair muito, a perda também é grande: só para quando a ação chega a zero. Por isso a corretora pede uma margem alta.",
    noApp: noBookSe(
      'quando a vol do ativo não está barata e os critérios do Book aceitam perda ilimitada (a opção "Aceitar perda ilimitada")',
    ),
  },
  iron_condor_vendido: {
    etiquetas: [
      "você precisa de margem (garantia) para a perda máxima",
      "para a ação ficar dentro da faixa",
      "risco: a ação sair da faixa (a perda é limitada)",
    ],
    oQueE:
      "Você vende uma [put](put) e uma [call](call), uma de cada lado do preço atual, e compra uma put e uma call mais afastadas, para limitar a perda. Recebe a diferença na hora.",
    quandoUsar:
      "Quando você acha que a ação vai ficar dentro da faixa entre os strikes vendidos e quer uma perda com limite. Rende mais quando a [vol está cara](vol-cara-barata).",
    comoMontar:
      "Compra uma put com strike baixo, vende uma put com strike abaixo do preço atual, vende uma call com strike acima do preço atual e compra uma call com strike mais alto.",
    oQuePodeDarErrado:
      "Se a ação sair da faixa, o seu ganho vai encolhendo e, além do [ponto de empate](empate), vira perda. Passando dos strikes comprados, a perda para de crescer: o máximo é a distância entre os dois strikes de um lado (o da put ou o da call) menos o que você recebeu.",
    noApp: noBookSe("quando a vol do ativo não está barata"),
  },
  iron_condor_comprado: {
    etiquetas: [
      "você precisa ter o valor que vai pagar",
      "para a ação sair da faixa",
      "risco: perder o que pagou se a ação ficar na faixa",
    ],
    oQueE:
      "É o contrário do iron condor vendido. Você compra uma [put](put) e uma [call](call), uma de cada lado do preço atual, e vende uma put e uma call mais afastadas, para pagar parte do custo. Ganha se a ação sair da faixa e passar do [ponto de empate](empate).",
    quandoUsar:
      "Quando você espera um movimento grande, para qualquer lado, e quer gastar menos que num strangle comprado, aceitando um ganho com teto.",
    comoMontar:
      "Vende uma put com strike baixo, compra uma put com strike abaixo do preço atual, compra uma call com strike acima do preço atual e vende uma call com strike mais alto.",
    oQuePodeDarErrado:
      "Se a ação ficar entre os strikes comprados (os de dentro) até o [vencimento](vencimento), você perde tudo o que pagou. Fora dessa faixa, mas antes do [ponto de empate](empate), perde só parte. O ganho tem teto: não cresce depois dos strikes vendidos (os de fora).",
    noApp: SO_NO_MONTADOR,
  },
  borboleta_comprada: {
    etiquetas: [
      "você precisa ter o valor que vai pagar",
      "para a ação parar perto do strike do meio",
      "risco: perder o que pagou se a ação terminar longe do meio",
    ],
    oQueE:
      "Você compra uma [call](call) com strike abaixo do preço atual, vende duas calls no strike do meio e compra uma call com strike acima. Ganha mais se a ação parar perto do strike do meio no vencimento.",
    quandoUsar:
      "Quando você acha que a ação vai parar perto do strike do meio e quer pagar pouco. O ganho tem teto.",
    comoMontar:
      "Compra uma call com strike abaixo do preço atual, vende duas calls com strike perto do preço atual (o meio) e compra uma call com strike acima.",
    oQuePodeDarErrado:
      "Se a ação terminar além dos strikes de fora, você perde tudo o que pagou. Mais perto do meio, perde só parte ou ganha: o ganho só é grande perto do strike do meio.",
    noApp: noBookSe("quando a vol do ativo não está barata"),
  },
  borboleta_vendida: {
    etiquetas: [
      "você precisa de margem (garantia) para a perda máxima",
      "para a ação se afastar do meio",
      "risco: perder se a ação parar perto do meio",
    ],
    oQueE:
      "É o contrário da borboleta comprada. Você vende uma [call](call) com strike abaixo do preço atual, compra duas calls no strike do meio e vende uma call com strike acima. Recebe um dinheiro na hora e ganha se a ação se afastar do meio, para qualquer lado.",
    quandoUsar:
      "Quando você acha que a ação vai andar para um dos lados e não vai parar perto do strike do meio. O ganho tem teto: é o que você recebeu.",
    comoMontar:
      "Vende uma call com strike abaixo do preço atual, compra duas calls com strike perto do preço atual (o meio) e vende uma call com strike acima.",
    oQuePodeDarErrado:
      "Se a ação parar perto do strike do meio no vencimento, você perde. A perda é limitada, mas pode ser bem maior que o que você recebeu.",
    noApp: SO_NO_MONTADOR,
  },
  put_protetora: {
    etiquetas: [
      "você precisa ter a ação",
      "para quem quer manter a ação com seguro",
      "risco: o custo do seguro (e o seguro vence)",
    ],
    oQueE:
      "Você tem a ação e compra uma [put](put). A put funciona como um seguro: se a ação cair, você pode vendê-la pelo preço combinado (o [strike](strike)), e isso limita a sua perda.",
    quandoUsar:
      "Quando você quer continuar com a ação, mas teme uma queda até o [vencimento](vencimento). O seguro sai mais barato quando a [vol está barata](vol-cara-barata).",
    comoMontar:
      "Compra as ações (ou usa as que você já tem) e compra uma put com strike abaixo do preço atual.",
    oQuePodeDarErrado:
      "O seguro custa dinheiro: se a ação não cair, você perde o que pagou pela put. E o seguro vence: depois do vencimento, a ação fica sem proteção até você comprar outra put.",
    noApp: noBook("Proteção"),
  },
  collar: {
    etiquetas: [
      "você precisa ter a ação",
      "para quem quer seguro barato",
      "risco: abrir mão da alta acima da call vendida",
    ],
    oQueE:
      "Você tem a ação, compra uma [put](put) (o seguro) e vende uma [call](call). O prêmio da call paga parte do seguro, ou até todo ele. Em troca, você abre mão da alta acima do strike da call.",
    quandoUsar:
      "Quando você quer manter a ação protegida, gastando pouco ou nada com o seguro, e aceita não ganhar com uma alta grande.",
    comoMontar:
      "Compra as ações (ou usa as que você já tem), compra uma put com strike abaixo do preço atual e vende uma call com strike acima.",
    oQuePodeDarErrado:
      "Se a ação subir acima do strike da call, você é obrigado a vender ([atribuição](atribuicao)) e perde o resto da alta. Se cair, a put limita a perda, mas ela existe.",
    noApp: noBook("Proteção"),
  },
};
