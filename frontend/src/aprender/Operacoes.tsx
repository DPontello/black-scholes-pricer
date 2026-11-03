import { useEffect, useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { carregarExemplos, type Exemplo } from "../api/aprender";
import type { Familia } from "../api/book";
import { ErroApi } from "../api/cliente";
import { ComTermos } from "../componentes/Termo";
import { formatarInteiro, formatarPreco } from "../formatacao";
import { GraficoExemplo } from "./GraficoExemplo";
import { type TextoOperacao, TEXTOS_OPERACOES } from "./operacoes";

// A API não diz o ativo do exemplo: ele é sempre este.
const ATIVO_DO_EXEMPLO = "PETR4";

const FAMILIAS: Record<Familia, string> = {
  renda: "Renda",
  direcionais: "Direcionais",
  volatilidade: "Volatilidade",
  protecao: "Proteção",
};

// "um straddle", mas "uma venda coberta": o botão fala o português do nome.
const MASCULINAS = new Set([
  "straddle_comprado",
  "straddle_vendido",
  "strangle_comprado",
  "strangle_vendido",
  "iron_condor_vendido",
  "iron_condor_comprado",
  "collar",
]);

type Props = { comPerfil: boolean };

function mensagem(erro: unknown, padrao: string): string {
  return erro instanceof ErroApi ? erro.mensagem : padrao;
}

function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

const reais = (valor: number) => `R$ ${formatarPreco(valor)}`;

// As famílias na ordem em que aparecem no catálogo, cada uma com as suas operações.
function porFamilia(exemplos: Exemplo[]): [Familia, Exemplo[]][] {
  const grupos = new Map<Familia, Exemplo[]>();
  for (const exemplo of exemplos)
    grupos.set(exemplo.familia, [...(grupos.get(exemplo.familia) ?? []), exemplo]);
  return [...grupos];
}

export function Operacoes({ comPerfil }: Props) {
  const { modelo } = useParams();
  const [exemplos, setExemplos] = useState<Exemplo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    carregarExemplos()
      .then((lista) => {
        if (!cancelado) setExemplos(lista);
      })
      .catch((e: unknown) => {
        if (!cancelado) setErro(mensagem(e, "Não foi possível carregar os exemplos."));
      });
    return () => {
      cancelado = true;
    };
  }, []);

  if (erro !== null)
    return (
      <p className="erro" role="alert">
        {erro}
      </p>
    );
  if (exemplos === null) return <p className="secundario">Carregando os exemplos…</p>;

  // Um endereço sem modelo, ou com um modelo que não existe, abre a primeira operação.
  const escolhida = exemplos.find((e) => e.chave === modelo) ?? exemplos[0];
  const texto = escolhida === undefined ? undefined : TEXTOS_OPERACOES[escolhida.chave];

  return (
    <div className="operacoes">
      <ListaOperacoes exemplos={exemplos} escolhida={escolhida?.chave ?? null} />
      {escolhida !== undefined && texto !== undefined && (
        <Operacao exemplo={escolhida} texto={texto} comPerfil={comPerfil} />
      )}
    </div>
  );
}

function ListaOperacoes({ exemplos, escolhida }: { exemplos: Exemplo[]; escolhida: string | null }) {
  const prefixo = useId();
  return (
    <nav className="lista-operacoes" aria-label="Lista de operações">
      {porFamilia(exemplos).map(([familia, itens]) => (
        <div key={familia}>
          <p className="familia-lista" id={`${prefixo}-${familia}`}>
            {FAMILIAS[familia]}
          </p>
          <ul aria-labelledby={`${prefixo}-${familia}`}>
            {itens.map((item) => (
              <li key={item.chave}>
                <Link
                  to={`/aprender/operacoes/${item.chave}`}
                  aria-current={item.chave === escolhida ? "page" : undefined}
                >
                  {capitalizar(item.nome)}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Operacao({
  exemplo,
  texto,
  comPerfil,
}: {
  exemplo: Exemplo;
  texto: TextoOperacao;
  comPerfil: boolean;
}) {
  const navegar = useNavigate();
  const idMotivo = useId();
  const artigo = MASCULINAS.has(exemplo.chave) ? "um" : "uma";
  return (
    <article className="operacao">
      <h2>{capitalizar(exemplo.nome)}</h2>
      <ul className="etiquetas" aria-label="Etiquetas">
        {[FAMILIAS[exemplo.familia], ...texto.etiquetas].map((etiqueta) => (
          <li key={etiqueta}>{etiqueta}</li>
        ))}
      </ul>
      <h3>O que é</h3>
      <p>
        <ComTermos texto={texto.oQueE} />
      </p>
      <h3>Quando usar</h3>
      <p>
        <ComTermos texto={texto.quandoUsar} />
      </p>
      <h3>Como montar</h3>
      <p>
        <ComTermos texto={texto.comoMontar} />
      </p>
      <h3>Exemplo</h3>
      <BlocoExemplo exemplo={exemplo} />
      <h3>O que pode dar errado</h3>
      <p>
        <ComTermos texto={texto.oQuePodeDarErrado} />
      </p>
      <h3>No app</h3>
      <p>
        <ComTermos texto={texto.noApp} />
      </p>
      <button
        type="button"
        disabled={!comPerfil}
        aria-describedby={comPerfil ? undefined : idMotivo}
        onClick={() => navegar(`/montador?modelo=${encodeURIComponent(exemplo.chave)}`)}
      >
        Montar {artigo} {exemplo.nome} no Montador
      </button>
      {!comPerfil && (
        <span className="secundario motivo-botao" id={idMotivo}>
          abra um perfil primeiro
        </span>
      )}
    </article>
  );
}

function fraseDaPerna(perna: Exemplo["pernas"][number]): string {
  const verbo = perna.lado === "compra" ? "compra" : "vende";
  const opcoes = `${formatarInteiro(perna.quantidade)} ${perna.tipo}s`;
  return `${verbo} ${opcoes} de strike ${reais(perna.strike)} a ${reais(perna.premio)}`;
}

// "R$ 45,00 (cai 10%)": o cenário diz de quanto o preço se mexe em relação ao de hoje.
function rotuloDoPreco(preco: number, spot: number): string {
  const pontos = formatarInteiro(Math.round((Math.abs(preco - spot) / spot) * 100));
  const variacao = preco === spot ? "fica" : `${preco < spot ? "cai" : "sobe"} ${pontos}%`;
  return `${reais(preco)} (${variacao})`;
}

function classeDoResultado(resultado: number): string | undefined {
  if (resultado === 0) return undefined;
  return resultado < 0 ? "baixa" : "alta";
}

function fraseDoResultado(resultado: number): string {
  if (resultado === 0) return "fica no zero a zero";
  return `${resultado < 0 ? "perde" : "ganha"} ${reais(Math.abs(resultado))}`;
}

const limite = (valor: number | null) => (valor === null ? "sem limite" : reais(valor));

function BlocoExemplo({ exemplo }: { exemplo: Exemplo }) {
  const premio = exemplo.premio_liquido;
  const fraseDoPremio = `${premio >= 0 ? "recebe" : "paga"} ${reais(Math.abs(premio))}`;
  return (
    <div className="exemplo-operacao">
      <div>
        <p className="secundario">exemplo, sem custos nem IR</p>
        <p>
          Com {ATIVO_DO_EXEMPLO} a {reais(exemplo.spot)}, você:
        </p>
        <ul>
          {exemplo.acoes > 0 && (
            <li>{`compra ${formatarInteiro(exemplo.acoes)} ações a ${reais(exemplo.spot)}`}</li>
          )}
          {exemplo.pernas.map((perna, i) => (
            <li key={i}>{fraseDaPerna(perna)}</li>
          ))}
        </ul>
        <p>
          Pelas opções, você{" "}
          <strong>{fraseDoPremio}</strong>.
        </p>
        <table className="cenarios">
          <caption>Resultado no vencimento, conforme o preço de {ATIVO_DO_EXEMPLO}</caption>
          <thead>
            <tr>
              <th scope="col">Preço de {ATIVO_DO_EXEMPLO}</th>
              <th scope="col">Resultado</th>
            </tr>
          </thead>
          <tbody>
            {exemplo.cenarios.map((cenario) => (
              <tr key={cenario.preco}>
                <th scope="row">{rotuloDoPreco(cenario.preco, exemplo.spot)}</th>
                <td className={classeDoResultado(cenario.resultado)}>
                  {fraseDoResultado(cenario.resultado)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul className="resumo-exemplo">
          {exemplo.empates.length > 0 && (
            <li>{`empata em ${exemplo.empates.map(reais).join(" e em ")}`}</li>
          )}
          <li>{`ganho máximo ${limite(exemplo.ganho_maximo)}`}</li>
          <li>{`perda máxima ${limite(exemplo.perda_maxima)}`}</li>
        </ul>
      </div>
      <GraficoExemplo exemplo={exemplo} ativo={ATIVO_DO_EXEMPLO} />
    </div>
  );
}
