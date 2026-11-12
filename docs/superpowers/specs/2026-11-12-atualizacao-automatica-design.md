# Atualização pelo app e versão nova a cada subida na master (desenho)

Data: 2026-11-12. Pedido do autor: "daria para fazer um novo release já, nesse release ia entrar
tudo, o instalador (eu quero que ele se atualize com base na master) e o resto".

Este desenho substitui a linha "Atualização automática do app (reinstala-se a versão nova)
**(decisão minha)**" dos não-objetivos do desenho geral
(`specs/2026-10-28-app-opcoes-design.md`, §3): aquela era decisão de quem escreveu, e o autor
agora pede a atualização.

As decisões da §2 são do autor (conversa de 12/11, com rascunhos no navegador). As marcadas
**(decisão minha)** são minhas, para o autor conferir ao ler.

## 1. Intenção e situação de hoje

O autor trabalha na `development`, testa e quer que **subir para a `master` seja publicar**: a
mãe dele abre o app no PC dela (Windows, instalado pelo instalador), vê que há versão nova,
clica e o app se atualiza sozinho.

Hoje, lido no código da `development` em 12/11 (`3eb89a8`):

1. **Não há release no GitHub.** O instalador só sai como artefato do job `Instalador`
   (`.github/workflows/instalador.yml`), em PR que mexe em `packaging/**`, em tag `v*` ou à mão.
   O último é de 05/11 (PR #14) e não tem os valores brutos (PR #16) nem o Montador simples
   (PR #17).
2. **O botão "Run workflow" não funciona:** o `instalador.yml` não existe na `master`.
3. **A `master` está 141 commits atrás da `development`** (`ba1003c`). As tags `v0.2.0`, `v0.3.0`
   e `v0.4.0` existem e `v0.4.0` está na `master`. O `pyproject.toml` diz `0.5.0.dev0`.
4. **O app nunca sai para a internet.** O único `urlopen` é para o próprio servidor local
   (`launch.py`).
5. **Atualizar já funciona por cima** (`PainelOpcoes.iss`): `AppId` fixo, `CloseApplications=yes`
   e dados fora da pasta do programa (`%APPDATA%\PainelOpcoes` e a pasta de cada perfil). No modo
   silencioso, o `[Run]` atual não reabre o app (`skipifsilent`).
6. **O repositório é público:** a API de releases do GitHub responde sem senha.

## 2. Decisões do autor

1. **Fluxo:** termina algo na `development`, testa e sobe para a `master`. Subir para a `master`
   é o que publica a versão nova; ele não roda mais nada.
2. **O aviso é uma janela ao abrir o app** (opção B dos rascunhos): "Versão nova do app: 0.5.1.
   Você está usando a 0.5.0. O que mudou: …", com os botões **Atualizar** e **Agora não**.
3. **"Agora não"** fecha a janela, e ela volta na próxima vez que ela abrir o app.
4. **"Atualizar"** baixa a versão nova, mostra o andamento, fecha o app, instala por cima sem
   perguntas e abre o app de novo. Perfis, carteiras, simulações e arquivos da B3 ficam como
   estavam.
5. **Confirmado na leitura de volta, "está certo":** o número da versão sobe sozinho; sem
   internet não aparece nada e o app abre normalmente; o "o que mudou" sai dos títulos dos PRs;
   neste PC Linux não há aviso (o app roda da pasta do código e se atualiza pelo git).
6. **Release já, com tudo o que está na `development`:** o instalador, os valores brutos, o
   Montador simples e esta atualização.

## 3. Objetivos (o que se constrói)

### A. Publicação a cada subida na `master` (CI)

- **Gatilho:** um workflow novo roda quando o `CI` termina com sucesso num push para a `master`
  (`workflow_run`), sobre o commit que o CI testou. Nada é publicado com teste vermelho
  **(decisão minha)**.
- **O que faz:** gera o instalador com os mesmos passos e testes de fumaça do `instalador.yml`
  (sem duplicar os passos: o construtor escolhe como reaproveitar). Depois cria o release
  `vX.Y.Z` no GitHub, marcado como o mais recente, com um único arquivo,
  `PainelOpcoes-X.Y.Z-setup.exe`, e as notas.
- **Número da versão (decisão minha):** os dois primeiros números vêm do `pyproject.toml`, que
  hoje diz `0.5.0.dev0`, então a linha é 0.5. O terceiro é o maior já publicado nessa linha mais
  1, ou 0 se ainda não há nenhum: a primeira versão é a `v0.5.0`, depois `v0.5.1`, `v0.5.2`.
  O job grava a versão calculada no `pyproject.toml` da sua própria cópia, antes do build e sem
  commit. Assim o `GET /api/saude`, o nome do instalador e a versão do arquivo dizem o mesmo
  número. Para a 1.0, o autor troca o `pyproject.toml` para `1.0.0`. Uma linha menor que a do
  último release faz o job falhar com uma mensagem clara.
- **Sem repetição:** se já existe release para esse mesmo commit, o job não publica outro.
- **Notas, o "o que mudou" (decisão minha):** saem das mensagens de merge
  `Merge pull request #N …` entre o release anterior e o commit publicado. Para o primeiro
  release, o ponto de partida é a tag `v0.4.0`. De cada mensagem entra a primeira linha do corpo,
  que é o título do PR, sem o prefixo `tipo(escopo): `. Ficam de fora:
  - os tipos `docs`, `test`, `ci` e `chore`, e o escopo `testes` (ex.: `fix(testes): …`);
  - o PR que leva a `development` para a `master` (`… from <dono>/development`), se ele existir;
  - os merges sem PR (`Merge branch 'development'`).

  Isso vale para qualquer jeito de subir: merge local, PR com merge ou fast-forward. Commits feitos
  direto na `master`, sem PR, não entram nas notas. O resultado é uma linha `- texto` por item, ou
  `- Ajustes internos` se não sobrar nenhum.
- **O autor pode editar o texto** do release no GitHub depois: o app lê as notas na hora em que
  confere.
- **O `instalador.yml` continua** gerando o instalador nos PRs que mexem no empacotamento.

### B. Instalador

- **Atualização silenciosa que reabre o app:** com o parâmetro `/RELANCAR=1`, o instalador
  silencioso abre `PainelOpcoes.exe --depois-de-atualizar` no fim. A instalação normal, com as
  telas, não muda.
- **Registro da atualização:** a atualização pelo app passa `/LOG=` para
  `%APPDATA%\PainelOpcoes\logs\atualizacao.log`, para dar para investigar uma falha
  **(decisão minha)**.

### C. Conferir se há versão nova (servidor)

- **`GET /api/versao`** devolve `{"atual": "0.5.0", "nova": null}` ou
  `{"atual": "0.5.0", "nova": {"versao": "0.5.1", "novidades": ["…"], "tamanho": 31457280}}`.
- **Só no app instalado no Windows** (executável do PyInstaller). Em qualquer outro caso, como
  neste PC ou rodando do código, `nova` é sempre `null` e nada sai para a rede.
- **Fonte:** `https://api.github.com/repos/DPontello/black-scholes-pricer/releases/latest`, sem
  token, com 5 s de limite. Qualquer falha (sem internet, GitHub fora, limite de consultas,
  resposta estranha) dá `nova: null` e uma linha no log, nunca erro na tela.
- **Quando há versão nova:** só se a versão do release for maior que a atual na comparação
  número a número (0.5.10 > 0.5.9) e o release tiver o arquivo
  `PainelOpcoes-<versão>-setup.exe`.
- **Resultado guardado por 30 min** no servidor **(decisão minha)**. A API sem token aceita
  60 consultas por hora, e o servidor fica de pé enquanto a janela abre e fecha.
- **Só biblioteca padrão** (`urllib`), como o `launch.py`. O extra `app` não ganha dependência.

### D. Atualizar (servidor)

- **`POST /api/versao/atualizar`** começa a atualização. Chamar de novo durante uma em
  andamento não começa outra.
- **`GET /api/versao/atualizar`** devolve
  `{"fase": "parado"|"baixando"|"instalando"|"erro", "baixado": n, "total": n, "mensagem": "…"}`.
- **Download:** vai para uma pasta temporária, por HTTPS e só do endereço do arquivo do release
  em `github.com/DPontello/black-scholes-pricer` (o redirecionamento para o servidor de arquivos
  do GitHub é aceito).
- **Conferência do arquivo:** o SHA-256 tem de bater com o campo `digest` do arquivo na API.
  Sem `digest`, confere o tamanho. Se não bater, a fase vira `erro` e o arquivo é apagado.
- **Instalação:** abre o instalador separado do app, com
  `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELANCAR=1 /LOG="…"`. A fase vira
  `instalando`, e o servidor se encerra pelo caminho normal, que solta a trava do perfil e para a
  ponte do Tryd.
- **Se o instalador não abrir,** a fase vira `erro` e o app continua aberto na versão atual.

### E. A janela do aviso (tela)

- **Ao abrir o app** (carregar a página), a tela consulta `GET /api/versao` uma vez. Se `nova`
  não for `null`, abre a janela da opção B, por cima de qualquer tela, inclusive da escolha de
  perfil.
- **Conteúdo:** título "Versão nova do app: 0.5.1", a linha "Você está usando a 0.5.0. O que
  mudou:" e até 5 itens, mais "e mais N" se houver mais **(decisão minha)**. Os botões são
  **Atualizar** (`botao-principal`) e **Agora não**.
- **"Agora não"** esconde a janela até a página carregar de novo. Fica só na memória da página,
  sem `localStorage`.
- **"Atualizar"** troca o conteúdo da janela:
  1. "Baixando a versão nova: 12 de 30 MB", com barra de andamento.
  2. Depois, "Instalando. O app fecha e abre de novo sozinho, em menos de um minuto."
  3. A tela consulta `/api/saude` até ele responder com a versão nova e então recarrega.
  4. Passados 2 minutos sem isso, mostra "Se o app não abrir sozinho, abra pelo atalho Painel
     de Opções."
- **Erro:** "Não deu para baixar a versão nova: <motivo>. O app continua na versão 0.5.0.", com
  **Tentar de novo** e **Fechar**.
- **Acessibilidade:** `role="dialog"`, `aria-modal`, foco em **Atualizar** e Esc equivale a
  "Agora não".

### F. Uma janela só depois de atualizar

- **Critério:** ela termina com **uma** janela do app aberta, já na versão nova.
- **Mecanismo sugerido (decisão minha):** o app aberto com `--depois-de-atualizar` não abre
  janela se a janela antiga voltar a falar com o servidor em até 15 s. Ela volta sozinha porque
  fica consultando `/api/saude`, e a porta padrão 8765 fica livre de novo quando o servidor
  antigo sai, então o endereço é o mesmo. Se ninguém voltar nesse tempo, ele abre uma janela
  nova. O construtor pode usar outro jeito, desde que o critério valha.

### G. Documentação

- **README, seção "Atualizar":** como a versão nova chega, a primeira instalação à mão (§8), e
  que no Linux continua sendo `git pull` + `scripts/linux/instalar.sh`.
- **HANDOFF, §13 "12/11: atualização pelo app":** o roteiro de teste no Windows (§8) e os
  critérios da §7.
- **ROADMAP:** um item.

## 4. Não-objetivos

- **Atualizar sem ela clicar,** ou baixar em segundo plano.
- **Conferir com o app já aberto:** só ao abrir.
- **Canal de testes (beta),** ou escolher a versão.
- **Voltar para uma versão anterior pelo app:** reinstala-se a anterior pela página de releases.
- **Aviso no Linux.**
- **Assinatura digital do instalador.** O arquivo baixado pelo app não ganha a marca de "veio da
  internet" que o navegador põe, então a atualização não passa pelo SmartScreen. A primeira
  instalação à mão continua passando, como explica o README.
- **Lista completa de mudanças dentro do app.**

## 5. Anti-objetivos (fracasso mesmo funcionando)

- **Perder dados** na atualização, ou deixar a trava do perfil presa.
- **Deixar a mãe sem app:** atualização que falha no meio e não diz o que fazer.
- **Aviso falso:** aparece sem versão nova, ou volta a cada clique na mesma abertura.
- **App que demora para abrir** ou trava sem internet.
- **Publicar versão** com teste vermelho.
- **Baixar e rodar executável** de qualquer lugar que não seja o release deste repositório.

## 6. Impacto

- **CI:** um workflow novo de publicação. O `instalador.yml` pode mudar para ser reaproveitado.
- **Empacotamento:** `packaging/windows/PainelOpcoes.iss` (o `[Run]` silencioso com
  `/RELANCAR`). O cálculo da versão e das notas vira um script Python testado (em `packaging/`
  ou `tools/`).
- **Servidor:**
  - um adaptador de saída para a API de releases e o download;
  - as rotas `/api/versao`;
  - o encerramento do servidor pedido pelo próprio app;
  - a opção `--depois-de-atualizar` em `options_engine app`.
- **Os contratos do import-linter continuam valendo:** domínio e aplicação só com a biblioteca
  padrão, camadas config → adapters → application → domain.
- **Tela:** a janela do aviso e um módulo novo em `frontend/src/api/`.
- **Rede:** o app passa a sair para a internet, só para `api.github.com` e para o download do
  release, só no app instalado no Windows, e só ao abrir e ao clicar em Atualizar.

## 7. Critérios de aceite

1. **Publicação:** um push na `master` com o CI verde publica o release `vX.Y.Z` como o mais
   recente, com `PainelOpcoes-X.Y.Z-setup.exe` e as notas, sem o autor rodar nada.
2. **A versão bate:** no app instalado, `GET /api/saude` diz `X.Y.Z`.
3. **O aviso:** com a `X.Y.Z` instalada e a `X.Y.Z+1` publicada, abrir o app mostra a janela com
   as notas. "Agora não" fecha, e a janela volta na próxima abertura.
4. **A atualização:** "Atualizar" mostra o andamento, fecha o app, instala e reabre na versão
   nova em menos de um minuto, numa conexão normal. Ela termina com uma janela só, na escolha de
   perfil, como em toda abertura do app, porque o perfil ativo só existe na memória do servidor.
   Ao escolher o perfil dela, os dados estão como antes, e a trava do perfil não impede a entrada
   **(decisão minha)**.
5. **Sem internet:** o app abre normalmente, sem janela e sem atraso perceptível.
6. **Linux e código:** nenhuma janela e nenhuma chamada de rede.
7. **Arquivo corrompido** (SHA-256 diferente): mensagem de erro, e nada é instalado.
8. **Gates:** ruff, mypy, import-linter, pytest com cobertura ≥ 95%, testes do frontend e build.

## 8. O release de agora (ordem)

1. **Este trabalho** numa branch, PR para a `development`, CI verde, merge.
2. **O autor sobe a `development` para a `master`.** O CI roda, e a publicação gera a `v0.5.0`
   com tudo o que está na `development`.
3. **Primeira instalação à mão:** o autor instala a `v0.5.0` no PC Windows dele, pela página de
   releases. A versão de 05/11 não sabe se atualizar, então essa primeira vez é à mão. O
   SmartScreen aparece, como diz o README.
4. **Primeiro teste de verdade da atualização:** o autor sobe qualquer mudança para a `master`
   (por exemplo, o HANDOFF), gera a `v0.5.1`, abre o app no Windows dele e confere os critérios
   3 e 4. Se a mudança for só documentação, as notas dizem "Ajustes internos".
5. **Só então** ele instala no PC da mãe a versão mais recente, à mão. Daí em diante, cada subida
   na `master` chega a ela pela janela.

## 9. Casos de teste (para quem constrói)

- **Versão:**
  - sem release na linha → `X.Y.0`;
  - com `X.Y.3` → `X.Y.4`;
  - release de outra linha não conta;
  - linha do `pyproject.toml` menor que a do último release → falha;
  - comparação numérica (0.5.10 > 0.5.9).
- **Notas:**
  - prefixo `tipo(escopo): ` tirado;
  - `docs`, `test`, `ci`, `chore` e escopo `testes` fora;
  - nenhuma sobrando → "Ajustes internos";
  - merge sem PR (`Merge branch 'development'`) ignorado;
  - PR `… from <dono>/development` ignorado;
  - primeiro release a partir de `v0.4.0`.
- **`GET /api/versao`:**
  - fora do app instalado, `nova` é `null` sem chamar a rede;
  - erro e tempo esgotado → `null`;
  - release igual ou mais velho → `null`;
  - release sem o arquivo → `null`;
  - a segunda consulta em 30 min usa o resultado guardado.
- **Atualizar:**
  - `digest` diferente → `erro` e o arquivo apagado;
  - endereço fora do GitHub do repositório → recusado;
  - o andamento conta os bytes;
  - os argumentos exatos do instalador;
  - o encerramento do servidor vem depois de abrir o instalador;
  - falha ao abrir o instalador → `erro`, e o servidor fica de pé.
- **Tela:**
  - a janela abre com `nova` e não abre com `null`;
  - "Agora não" esconde;
  - Atualizar → baixando → instalando → recarrega na versão nova;
  - erro com "Tentar de novo";
  - a mensagem dos 2 minutos;
  - Esc fecha.
- **Instalador:** `tests/packaging/test_instalador.py` confere o `[Run]` silencioso e o
  `/RELANCAR`.

## 10. Fica com quem constrói

- Nomes de módulos e em que camada cada peça fica (dentro dos contratos).
- Como o workflow de publicação reaproveita o do instalador.
- Como o servidor se encerra a pedido (o `uvicorn.Server` hoje é criado dentro de
  `launch.serve`).
- O mecanismo exato da §F, se o sugerido não funcionar com o Edge.
