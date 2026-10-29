// Formatação de exibição em pt-BR. A API manda números crus; só a tela formata
// (decisão nº 8: conversão de exibição só na apresentação). Ausente é "—", nunca zero.

const AUSENTE = "—";
const FUSO_B3 = "America/Sao_Paulo";

const preco = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const percentual = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const umaCasa = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const relogio = new Intl.DateTimeFormat("pt-BR", {
  timeZone: FUSO_B3,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});
const diaMes = new Intl.DateTimeFormat("pt-BR", {
  timeZone: FUSO_B3,
  day: "2-digit",
  month: "2-digit",
});
const diaNaB3 = new Intl.DateTimeFormat("en-CA", { timeZone: FUSO_B3 }); // AAAA-MM-DD

/** Preço com duas casas: 1.234,50. */
export function formatarPreco(v: number | null): string {
  return v === null ? AUSENTE : preco.format(v);
}

/** Fração decimal como percentual com sinal: -0.0059 → "-0,59%". */
export function formatarPercentual(v: number | null): string {
  return v === null ? AUSENTE : percentual.format(v).replace(/−/g, "-");
}

/** Volume financeiro curto: 679,6 mi; 1,3 bi; 48,4 mil. */
export function formatarVolume(v: number | null): string {
  if (v === null) return AUSENTE;
  const absoluto = Math.abs(v);
  if (absoluto >= 1e9) return `${umaCasa.format(v / 1e9)} bi`;
  if (absoluto >= 1e6) return `${umaCasa.format(v / 1e6)} mi`;
  if (absoluto >= 1e3) return `${umaCasa.format(v / 1e3)} mil`;
  return inteiro.format(v);
}

/** Inteiro com separador de milhar: 22.704. */
export function formatarInteiro(v: number | null): string {
  return v === null ? AUSENTE : inteiro.format(v);
}

/** Data ISO (AAAA-MM-DD) como DD/MM/AAAA, sem passar por fuso. */
export function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

/** Hora da observação no fuso da B3; com DD/MM na frente quando não é de hoje. */
export function formatarHora(iso: string | null, agora: Date = new Date()): string {
  if (iso === null) return AUSENTE;
  const quando = new Date(iso);
  const hora = relogio.format(quando);
  return diaNaB3.format(quando) === diaNaB3.format(agora)
    ? hora
    : `${diaMes.format(quando)} ${hora}`;
}
