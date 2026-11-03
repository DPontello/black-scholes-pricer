import { ComTermos } from "../componentes/Termo";

type Tela = { titulo: string; texto: string };

// Uma seção por aba do menu, na ordem do menu.
export const TELAS: Tela[] = [
  {
    titulo: "Mercado",
    texto:
      "A lista dos seus ativos com a cotação e, ao escolher um, a cadeia de opções: [calls](call) à esquerda, [puts](put) à direita e o [strike](strike) no meio, com compra, venda, último, [IV](iv), [delta](delta) e [negócios](negocios). A aba Análise mostra a [IV 30](iv-30) contra a [HV 21](hv-21) no último ano, o [IV rank](iv-rank), o [percentil](percentil), o smile de cada vencimento e a estrutura a termo.",
  },
  {
    titulo: "Montador",
    texto:
      "Onde você monta uma operação, por um modelo pronto ou série a série, pelo + da cadeia. Mostra o resultado no vencimento e hoje, o [ganho e a perda máximos](ganho-perda-maximos), os [custos e o IR](custos-ir), a [chance de lucro](chance-de-lucro), as gregas e a grade de cenários. Daí você salva a simulação ou registra a operação como executada.",
  },
  {
    titulo: "Book",
    texto:
      "As melhores operações de hoje entre os seus ativos, uma por família no topo e as outras nas abas, cada uma com o porquê. As etiquetas dizem se a vol de cada ativo está [cara, normal ou barata](vol-cara-barata). Os critérios ficam em \"ajustar\". \"Abrir no montador\" refaz os preços com a cadeia do momento.",
  },
  {
    titulo: "Carteira",
    texto:
      "As operações que você executou na corretora e as ações que você já tem. Mostra o resultado realizado e o não realizado, pelo [preço de zerar](preco-de-zerar), e é onde você encerra uma operação ou registra o [exercício](exercicio) e a [atribuição](atribuicao). Os avisos de vencimento aparecem no topo.",
  },
  {
    titulo: "Aprender",
    texto:
      "Esta aba: os passos para usar o app, as operações explicadas com exemplo, os termos e o que cada tela faz. Abre também sem perfil.",
  },
  {
    titulo: "Alertas",
    texto:
      "Ainda em construção: avisos de vencimento próximo, risco de exercício, proventos e o calendário.",
  },
  {
    titulo: "Arquivos B3",
    texto:
      "A rotina da semana, com os links para baixar o [Cadastro de Instrumentos](cadastro) e o [COTAHIST](cotahist) anual, e o estado de cada um (em dia ou hora de baixar). Os arquivos que caem na pasta Downloads entram sozinhos; também dá para arrastá-los para a tela.",
  },
];

type Indicador = { rotulo: string; texto: string };

export const INDICADORES: Indicador[] = [
  {
    rotulo: "Ao vivo (Tryd)",
    texto: "Os preços chegam do Tryd, na hora. É o estado para montar e registrar operações.",
  },
  {
    rotulo: "Atrasado",
    texto:
      "A ligação com o Tryd está lenta ou o Tryd ainda não entrega dados: os preços podem estar velhos. Espere voltar para \"Ao vivo\" antes de decidir.",
  },
  {
    rotulo: "Fim de dia (B3)",
    texto:
      "O Tryd está fechado ou desconectado e os preços são do fechamento do último pregão, pelos arquivos da B3. Servem para estudar, não para operar.",
  },
];

export const ROTULOS: Indicador[] = [
  {
    rotulo: "preço indicativo, preço teórico",
    texto:
      "O preço não é o da oferta do livro: é o último negócio ou o calculado pelo modelo. Veja [preço executável, indicativo e teórico](preco-executavel).",
  },
  {
    rotulo: "call americana avaliada como europeia",
    texto:
      "O app calcula essa call como se só pudesse ser exercida no vencimento, uma aproximação. Veja [americana e europeia](americana-europeia).",
  },
  {
    rotulo: "posição hipotética de 100 ações",
    texto:
      "Na Proteção do Book, quando você não tem a ação na Carteira, o app mostra quanto custaria proteger 100 ações, pelo preço do último fechamento.",
  },
  {
    rotulo: "Cadastro com N dias úteis",
    texto:
      "O [Cadastro de Instrumentos](cadastro) da biblioteca está velho e séries novas podem estar faltando na cadeia. Baixe o novo em Arquivos B3.",
  },
];

export function Telas() {
  return (
    <div className="corpo-aprender telas">
      <h2>Telas do app</h2>
      {TELAS.map((tela) => (
        <section key={tela.titulo} aria-labelledby={`tela-${tela.titulo}`}>
          <h3 id={`tela-${tela.titulo}`}>{tela.titulo}</h3>
          <p>
            <ComTermos texto={tela.texto} />
          </p>
        </section>
      ))}
      <section aria-labelledby="tela-indicador">
        <h3 id="tela-indicador">O indicador do topo</h3>
        <p>
          No alto da tela, ele diz <ComTermos texto="[de onde vêm os preços](ao-vivo-fim-de-dia)" />:
        </p>
        <dl className="indicadores">
          {INDICADORES.map((indicador) => (
            <div key={indicador.rotulo}>
              <dt>{indicador.rotulo}</dt>
              <dd>{indicador.texto}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section aria-labelledby="tela-rotulos">
        <h3 id="tela-rotulos">Rótulos e avisos</h3>
        <dl className="indicadores">
          {ROTULOS.map((rotulo) => (
            <div key={rotulo.rotulo}>
              <dt>{rotulo.rotulo}</dt>
              <dd>
                <ComTermos texto={rotulo.texto} />
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
