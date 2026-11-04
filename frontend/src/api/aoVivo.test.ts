import { expect, test } from "vitest";

import { aplicar, type EstadoAoVivo } from "./aoVivo";

const VAZIO: EstadoAoVivo = {
  conectado: true,
  status: null,
  cotacoes: [],
  motivoCotacoes: null,
  cadeia: null,
  cadeiaIndisponivel: null,
  carteira: null,
  carteiraIndisponivel: null,
  alertas: null,
  alertasIndisponiveis: null,
};

test("status e cotações do app entram no estado", () => {
  const comStatus = aplicar(VAZIO, {
    tipo: "status",
    fonte: "fim_de_dia",
    cadastro: null,
    cadastro_motivo: "nenhum Cadastro de Instrumentos importado",
    cotahist: null,
  });
  expect(comStatus.status?.fonte).toBe("fim_de_dia");
  expect(comStatus.status).not.toHaveProperty("tipo");
  const comCotacoes = aplicar(comStatus, { tipo: "cotacoes", dados: [], motivo: "nenhum perfil" });
  expect(comCotacoes.motivoCotacoes).toBe("nenhum perfil");
});

test("cadeia que não sai troca a cadeia anterior pelo motivo, e a que sai limpa o motivo", () => {
  const cadeia = {
    ativo: "PETR4",
    spot: 30,
    fonte: "ao_vivo" as const,
    hora: "2026-10-28T13:05:09-03:00",
    vencimentos: [],
    disponiveis: [],
    rejeitadas: [],
  };
  const comCadeia = aplicar(VAZIO, { tipo: "cadeia", dados: cadeia });
  const semCadeia = aplicar(comCadeia, {
    tipo: "cadeia",
    ativo: "PETR4",
    erro: "UnderlyingUnavailableError",
    mensagem: "PETR4: ponte do Tryd desconectada",
  });
  expect(semCadeia.cadeia).toBeNull();
  expect(semCadeia.cadeiaIndisponivel?.mensagem).toBe("PETR4: ponte do Tryd desconectada");
  expect(aplicar(semCadeia, { tipo: "cadeia", dados: cadeia }).cadeiaIndisponivel).toBeNull();
});

test("erro de pedido do próprio frontend não mexe no estado", () => {
  expect(aplicar(VAZIO, { tipo: "erro", erro: "RequisicaoInvalida", mensagem: "x" })).toBe(VAZIO);
});

test("a carteira do ao vivo entra no estado, e o motivo dela a substitui", () => {
  const dados = {
    fonte: "fim_de_dia" as const,
    operacoes: [],
    totais: [],
    avisos: [],
    ilegiveis: [],
  };
  const comCarteira = aplicar(VAZIO, { tipo: "carteira", dados });
  expect(comCarteira.carteira).toEqual(dados);
  const semPasta = aplicar(comCarteira, {
    tipo: "carteira",
    erro: "ProfileFolderUnavailableError",
    mensagem: "pasta do perfil fora do ar",
  });
  expect(semPasta.carteira).toBeNull();
  expect(semPasta.carteiraIndisponivel?.mensagem).toBe("pasta do perfil fora do ar");
  expect(aplicar(semPasta, { tipo: "carteira", dados }).carteiraIndisponivel).toBeNull();
});

test("alertas que não saem trocam a lista pelo motivo, e os que saem limpam o motivo", () => {
  const lista = { fonte: "ao_vivo" as const, alertas: [], dispensados: 1 };
  const comAlertas = aplicar(VAZIO, { tipo: "alertas", dados: lista });
  expect(comAlertas.alertas).toEqual(lista);
  const semAlertas = aplicar(comAlertas, {
    tipo: "alertas",
    erro: "NoActiveProfileError",
    mensagem: "nenhum perfil aberto",
  });
  expect(semAlertas.alertas).toBeNull();
  expect(semAlertas.alertasIndisponiveis?.mensagem).toBe("nenhum perfil aberto");
  expect(aplicar(semAlertas, { tipo: "alertas", dados: lista }).alertasIndisponiveis).toBeNull();
});
