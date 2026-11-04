import { Fragment, useEffect, useState } from "react";

import { type ExercicioIr, lerIrMensal, type MesIr, type PecaIr } from "../api/carteira";
import { ErroApi } from "../api/cliente";
import { formatarData, formatarMes, formatarPreco, formatarReais } from "../formatacao";
import { Ajuda } from "./Ajuda";

const TIPOS: Record<PecaIr["tipo"], string> = { encerramento: "Encerramento", po: "Pó" };
const CATEGORIAS: Record<PecaIr["categoria"], string> = { comum: "Comum", day_trade: "Day trade" };

function sinal(valor: number): string {
  return valor > 0 ? "alta" : valor < 0 ? "baixa" : "";
}

function porTipo(comum: number, dayTrade: number): string {
  const partes = [
    comum > 0 ? `comum ${formatarReais(comum)}` : null,
    dayTrade > 0 ? `day trade ${formatarReais(dayTrade)}` : null,
  ].filter((parte) => parte !== null);
  return partes.length === 0 ? "—" : partes.join(" · ");
}

function prejuizo(mes: MesIr): string {
  return porTipo(mes.prejuizo_comum, mes.prejuizo_day_trade);
}

function base(mes: MesIr): string {
  return porTipo(mes.base_comum, mes.base_day_trade);
}

function aPagar(mes: MesIr): string {
  if (mes.ir_a_pagar > 0) {
    const valor = formatarReais(mes.ir_a_pagar);
    return mes.pagar_ate === null ? valor : `${valor} até ${formatarData(mes.pagar_ate)}`;
  }
  if (mes.ir_para_depois > 0) return "abaixo de R$ 10: soma com o IR dos próximos meses";
  return "—";
}

function Pecas({ pecas }: { pecas: PecaIr[] }) {
  return (
    <table className="tabela-operacoes">
      <thead>
        <tr>
          <th>Data</th>
          <th>Série</th>
          <th>Operação</th>
          <th>Tipo</th>
          <th>Categoria</th>
          <th className="num">Resultado</th>
        </tr>
      </thead>
      <tbody>
        {pecas.map((peca, i) => (
          <tr key={i}>
            <td>{formatarData(peca.data)}</td>
            <td>{peca.ticker}</td>
            <td>{peca.operacoes.join(", ")}</td>
            <td>{TIPOS[peca.tipo]}</td>
            <td>{CATEGORIAS[peca.categoria]}</td>
            <td className={`num ${sinal(peca.resultado)}`}>{formatarPreco(peca.resultado)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Exercicio({ exercicio }: { exercicio: ExercicioIr }) {
  return (
    <p className="secundario">
      {`Exercício ou atribuição de ${exercicio.ticker} (${exercicio.operacao}) em ${formatarData(exercicio.data)}: o prêmio vai para o preço da ação, e o resultado da ação fica fora desta conta (o app não apura o IR de ações).`}
    </p>
  );
}

function Detalhe({ mes }: { mes: MesIr }) {
  const aviso = mes.ir_para_depois > 0 ? " (abaixo de R$ 10: soma com o IR dos próximos meses)" : "";
  return (
    <>
      <p>{`Base: comum ${formatarReais(mes.base_comum)} (15%) · day trade ${formatarReais(mes.base_day_trade)} (20%)`}</p>
      {mes.ir_de_antes > 0 && (
        <p>
          {`IR do mês ${formatarReais(mes.ir_do_mes)} + ${formatarReais(mes.ir_de_antes)} de meses anteriores = ${formatarReais(mes.ir_a_pagar + mes.ir_para_depois)}${aviso}`}
        </p>
      )}
      <Pecas pecas={mes.pecas} />
      {mes.exercicios.map((exercicio, i) => (
        <Exercicio key={i} exercicio={exercicio} />
      ))}
    </>
  );
}

export function IrMensal() {
  const [meses, setMeses] = useState<MesIr[] | null>(null);
  const [abertos, setAbertos] = useState<ReadonlySet<string>>(new Set());
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    lerIrMensal()
      .then(setMeses)
      .catch((e: unknown) =>
        setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível calcular o IR mensal."),
      );
  }, []);

  function alternar(mes: string) {
    const novo = new Set(abertos);
    if (novo.has(mes)) novo.delete(mes);
    else novo.add(mes);
    setAbertos(novo);
  }

  return (
    <>
      <p className="secundario">
        Estimativa, só opções, sem IR retido na fonte e sem prejuízo de antes do app.{" "}
        <Ajuda id="ir-mensal" />
      </p>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      {meses !== null &&
        (meses.length === 0 ? (
          <p className="secundario">Nenhuma opção encerrada ou virada pó neste perfil ainda.</p>
        ) : (
          <table className="tabela-operacoes">
            <thead>
              <tr>
                <th>Mês</th>
                <th className="num">Comum</th>
                <th className="num">Day trade</th>
                <th>Prejuízo a compensar</th>
                <th>Base</th>
                <th className="num">IR do mês</th>
                <th>A pagar</th>
              </tr>
            </thead>
            <tbody>
              {meses.map((mes) => {
                const aberto = abertos.has(mes.mes);
                return (
                  <Fragment key={mes.mes}>
                    <tr>
                      <td>
                        <button
                          type="button"
                          className="link"
                          aria-expanded={aberto}
                          onClick={() => alternar(mes.mes)}
                        >
                          {aberto ? "▾" : "▸"} {formatarMes(mes.mes)}
                        </button>
                        {mes.exercicios.length > 0 && (
                          <>
                            {" "}
                            <span className="secundario">com exercício ou atribuição</span>
                          </>
                        )}
                      </td>
                      <td className={`num ${sinal(mes.comum)}`}>{formatarPreco(mes.comum)}</td>
                      <td className={`num ${sinal(mes.day_trade)}`}>{formatarPreco(mes.day_trade)}</td>
                      <td>{prejuizo(mes)}</td>
                      <td>{base(mes)}</td>
                      <td className="num">{formatarPreco(mes.ir_do_mes)}</td>
                      <td>{aPagar(mes)}</td>
                    </tr>
                    {aberto && (
                      <tr className="detalhe-operacao">
                        <td colSpan={7}>
                          <Detalhe mes={mes} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        ))}
    </>
  );
}
