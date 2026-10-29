// A API manda números crus; só a tela formata. Ausente é "—", nunca zero.

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
const vol = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
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
const instante = new Intl.DateTimeFormat("pt-BR", {
  timeZone: FUSO_B3,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function formatarPreco(v: number | null): string {
  return v === null ? AUSENTE : preco.format(v);
}

// Recebe fração decimal: -0.0059 → "-0,59%".
export function formatarPercentual(v: number | null): string {
  return v === null ? AUSENTE : percentual.format(v).replace(/−/g, "-");
}

export function formatarVolume(v: number | null): string {
  if (v === null) return AUSENTE;
  const absoluto = Math.abs(v);
  if (absoluto >= 1e9) return `${umaCasa.format(v / 1e9)} bi`;
  if (absoluto >= 1e6) return `${umaCasa.format(v / 1e6)} mi`;
  if (absoluto >= 1e3) return `${umaCasa.format(v / 1e3)} mil`;
  return inteiro.format(v);
}

export function formatarVol(v: number | null): string {
  return v === null ? AUSENTE : vol.format(v);
}

export function formatarDelta(v: number | null): string {
  return v === null ? AUSENTE : preco.format(v).replace(/−/g, "-");
}

export function formatarInteiro(v: number | null): string {
  return v === null ? AUSENTE : inteiro.format(v);
}

// Sem passar por Date: "2026-11-19" não pode virar 18/11 no fuso local.
export function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

export function formatarInstante(iso: string): string {
  return instante.format(new Date(iso)).replace(",", "");
}

// Com DD/MM na frente quando não é de hoje: dado de ontem não se passa pelo de agora.
export function formatarHora(iso: string | null, agora: Date = new Date()): string {
  if (iso === null) return AUSENTE;
  const quando = new Date(iso);
  const hora = relogio.format(quando);
  return diaNaB3.format(quando) === diaNaB3.format(agora)
    ? hora
    : `${diaMes.format(quando)} ${hora}`;
}
