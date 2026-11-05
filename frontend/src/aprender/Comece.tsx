import { Link } from "react-router-dom";

import { ComTermos } from "../componentes/Termo";

type Passo = { titulo: string; texto: string; link?: { para: string; nome: string } };

// O caminho de quem usa o app sozinho, na ordem em que as coisas acontecem.
export const PASSOS: Passo[] = [
  {
    titulo: "Crie o seu perfil",
    texto:
      "Na tela de perfis, crie o seu perfil com um nome e, em \"Escolher pasta…\", escolha a pasta onde ficam a sua carteira e as simulações (pode ser uma pasta na nuvem ou num pendrive). Cada pessoa usa o próprio perfil, com a própria carteira.",
    link: { para: "/perfis", nome: "Abrir os perfis" },
  },
  {
    titulo: "Baixe os arquivos da semana",
    texto:
      "Uma vez por semana, baixe no site da B3 o [Cadastro de Instrumentos](cadastro) (o pesquisa-pregao.zip) e o [COTAHIST](cotahist) anual do ano corrente. Deixe os dois na pasta Downloads: o app importa sozinho. Os links e o estado de cada arquivo ficam na aba Arquivos B3.",
    link: { para: "/arquivos", nome: "Abrir Arquivos B3" },
  },
  {
    titulo: "Abra o Tryd",
    texto:
      "Com o Tryd aberto, os preços chegam [ao vivo](ao-vivo-fim-de-dia) e o indicador no topo da tela mostra \"Ao vivo (Tryd)\". Se ele mostrar \"Fim de dia (B3)\", os preços são do fechamento do último pregão: servem para estudar, não para montar uma operação.",
  },
  {
    titulo: "Veja as melhores operações no Book",
    texto:
      "O Book mostra, para os ativos da sua lista, a melhor operação de cada família, com o porquê em números. Os critérios (Conservador, Moderado ou Arrojado) ficam em \"ajustar\". O Book escolhe pelo fechamento do último pregão; os preços do momento vêm no passo seguinte.",
    link: { para: "/book", nome: "Abrir o Book" },
  },
  {
    titulo: "Confira e ajuste no Montador",
    texto:
      "Em \"Abrir no montador\", a operação abre com os preços do momento. Confira o resultado no vencimento, o [ganho e a perda máximos](ganho-perda-maximos), os [custos e o IR](custos-ir) e a [chance de lucro](chance-de-lucro). Mude as pernas se quiser e salve como simulação.",
    link: { para: "/montador", nome: "Abrir o Montador" },
  },
  {
    titulo: "Registre o que executou na Carteira",
    texto:
      "O app não envia ordens: você executa a operação no home broker da corretora. Depois, registre com os preços que conseguiu de verdade, em \"Registrar como executada\" no Montador ou em \"Registrar operação\" na Carteira. A Carteira acompanha o resultado pelo [preço de zerar](preco-de-zerar).",
    link: { para: "/carteira", nome: "Abrir a Carteira" },
  },
  {
    titulo: "No vencimento",
    texto:
      "A opção que vence fora do dinheiro vira [pó](po): a Carteira a encerra sozinha quando chega o COTAHIST do dia do vencimento. A que vence dentro do dinheiro costuma ser exercida: se você comprou a opção, é [exercício](exercicio); se você vendeu, é [atribuição](atribuicao). Registre na Carteira, no botão Exercício: as ações entram ou saem, com o prêmio no preço.",
  },
];

export function Comece({ comPerfil }: { comPerfil: boolean }) {
  return (
    <div className="corpo-aprender comece">
      <h2>Comece aqui</h2>
      <p className="secundario">
        O caminho para usar o app sozinho, do perfil ao vencimento. Os termos sublinhados levam ao
        glossário.
      </p>
      <ol className="passos">
        {PASSOS.map((passo) => (
          <li key={passo.titulo}>
            <h3>{passo.titulo}</h3>
            <p>
              <ComTermos texto={passo.texto} />
            </p>
            {passo.link !== undefined && (comPerfil || passo.link.para === "/perfis") && (
              <Link to={passo.link.para}>{passo.link.nome}</Link>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
