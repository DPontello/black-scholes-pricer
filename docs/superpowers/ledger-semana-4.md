# Ledger — semana 4 (instalador, IR mensal e alertas)

Desenho: [`specs/2026-11-03-semana-4-instalador-ir-alertas-design.md`](specs/2026-11-03-semana-4-instalador-ir-alertas-design.md).
Parte 1, plano: [`plans/2026-11-03-semana-4-parte-1-instalador.md`](plans/2026-11-03-semana-4-parte-1-instalador.md).
Branch `feat/instalador`, a partir da `development` (`0c8e09b`), com as Tasks 1 a 5 (PR #10). As
Tasks 6 e 7 seguem na `feat/instalador-linux`, a partir da `development` (`eeb4186`).
Parte 2, plano: [`plans/2026-11-04-semana-4-parte-2-ir-mensal.md`](plans/2026-11-04-semana-4-parte-2-ir-mensal.md),
na branch `feat/ir-mensal`, a partir da `development` local (`785d324`).
Parte 3, plano: [`plans/2026-11-04-semana-4-parte-3-alertas.md`](plans/2026-11-04-semana-4-parte-3-alertas.md),
na branch `feat/alertas`, a partir da `development` (`057167d`).

## 2026-11-03: Task 1 — caminhos do app empacotado (ponte, tela e log)

- `default_bridge_command(..., frozen_dir=)`: no app instalado, a ponte é `<pasta do programa>\ponte\PonteTryd.exe servir --porta N`, com o diretório de trabalho na pasta `ponte`.
- `default_static_dir(meipass)`: no app instalado, a tela fica em `<_MEIPASS>\static`.
- `log_handler(config_dir)`: `logs/app.log` rotativo (5 MB, 3 arquivos) na pasta de configuração. `console_log(config_dir)`: `logs/console.log` só da última execução, para a saída e os erros sem tratamento (o executável não tem console).
- `build_web_app(..., frozen_dir=)` repassa a pasta do programa ao comando da ponte. Fora do executável, nada muda (teste).
- Ruling: o executável é detectado só na borda (`__main__._instalado`, por `sys.frozen` e `sys._MEIPASS`), e as funções recebem os caminhos como parâmetro, para seguirem testáveis sem PyInstaller.
- Ruling: com `frozen_dir`, o comando é o do `.exe` qualquer que seja o sistema: o app só é empacotado para o Windows; no Linux ele roda pelo venv do `instalar.sh` (Task 6).
- Ruling: a saída padrão só é redirecionada para o `console.log` quando está ausente (`None`, o caso do executável sem console); o log do `logging` vai sempre para o `app.log` no app instalado.
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/web/test_launch.py`, `tests/adapters/tryd/test_launcher.py` e `tests/config/test_web_app.py` (63 testes).

## 2026-11-03: Task 2 — "já está aberto" só abre a janela

- `GET /api/saude` ganhou `"app": "painel-de-opcoes"` (`launch.APP_ID`), a assinatura do app na porta.
- `launch.already_running(port, fetch)`: `True` só quando a porta responde com essa assinatura; sem resposta, com outro serviço, com JSON sem o campo ou ilegível, `False` (prazo de 1 s).
- Comando `app`: com o app já aberto na porta pedida (a padrão, 8765, ou a de `--porta`), imprime o endereço, abre a janela nele (ou nada, com `--sem-janela`) e sai com 0, sem montar o servidor nem tocar na trava do perfil.
- Ruling: só a porta pedida é consultada, não as 20 seguintes que o `find_free_port` tenta. O app que caiu numa porta seguinte (8765 ocupada por outro programa) não é achado, e o segundo clique sobe outro; a trava do perfil continua avisando. Se errado: consultar também as seguintes, ao custo de até 20 s com tudo ocupado.
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/web`, `tests/adapters/tryd/test_launcher.py` e `tests/config/test_web_app.py` (180 testes).

## 2026-11-03: Task 3 — executáveis com PyInstaller

- `packaging/windows/painel.py` (o `PainelOpcoes.exe` sem argumentos, ou só com opções, é o comando `app`; `conferir-b3` passa como está), `ponte.py`, `painel.spec`, `ponte.spec` e `requirements-build.txt` (PyInstaller 6.11.1 e pywin32 308, versões exatas).
- `painel.spec`: `onedir`, sem console; leva a tela em `static`, o calendário e a tabela de custos em `options_engine/adapters/outbound/data` (lidos por `importlib.resources`) e os metadados do pacote (a versão do `GET /api/saude`).
- `ponte.spec`: `onedir`, **de console**, com os módulos do pywin32 que a ponte importa por `importlib` (um teste confere que o spec tem todos os que o `rtd.py` importa).
- Bug evitado: o autoteste da ponte sobe o servidor falso com `<executável> -m options_ponte servidor-falso`; na ponte instalada o executável já é a ponte, e o `-m` quebraria. `comando_servidor_falso(..., frozen=)` tira o `-m options_ponte`.
- Ruling: a ponte é programa de console (para `diagnostico` e `autoteste` mostrarem o resultado no Windows), e o app a sobe com `CREATE_NO_WINDOW` (`spawn_process`), para a mãe do autor não ver janela preta. No Linux a flag não existe e vale 0.
- Ruling: a pasta `packaging/` não é pacote Python: o nome sombrearia o `packaging` do pip e do pytest. Os testes carregam os pontos de entrada pelo caminho.
- Ruling: sem ícone por enquanto (o repositório não tem um); o Windows usa o ícone padrão. Fica para o acabamento da semana 5.
- **Conferido de verdade no Linux:** o `painel.spec` gerou o app com o PyInstaller 6.11.1 (46 MB). O binário serviu a tela, o `GET /api/saude` com a versão e o `"app"`, os exemplos do Aprender e o `app.log` na pasta de configuração; o segundo processo achou o primeiro e saiu com 0. O `ponte.spec` (32 bits, pywin32) só se confere no job Windows (Task 5).
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/packaging`, `tests/ponte` e `tests/adapters/tryd` (671 testes).

## 2026-11-03: Task 4 — Inno Setup

- `packaging/windows/PainelOpcoes.iss`: instalação por usuário (`PrivilegesRequired=lowest`) em `%LOCALAPPDATA%\Programs\PainelOpcoes`, `AppId` fixo (`B68E5C59-…`), atalhos no menu Iniciar e na área de trabalho, "abrir o Painel de Opções" no fim, desinstalador em português (`BrazilianPortuguese.isl`, que vem com o Inno Setup 6). O build passa `Versao`, `VersaoNome`, `Origem` e `Saida` por `/D`.
- `packaging/windows/versao.py`: a versão do `pyproject.toml` inteira (`0.5.0.dev0`, no nome do instalador) e só com números (`0.5.0`, a que o Inno Setup aceita na versão do arquivo).
- Ruling: atualizar por cima apaga antes `{app}\_internal` e `{app}\ponte` (`[InstallDelete]`), para não sobrar biblioteca da versão antiga; nada fora de `{app}` é apagado, nem na atualização nem na desinstalação (teste no `.iss`). Os dados ficam em `%APPDATA%\PainelOpcoes` e na pasta de cada perfil.
- Ruling: `CloseApplications=yes` fecha o app aberto antes de trocar os arquivos.
- Ruling: sem página de escolher pasta (`DisableDirPage=yes`): uma pergunta a menos para a mãe do autor.
- O `.iss` só compila no job Windows (Task 5); aqui, os testes leem o script.
- Checagens: ruff, ruff format, mypy, import-linter e `tests/packaging` (19 testes).

## 2026-11-04: Task 5 — job do GitHub Actions

- `.github/workflows/instalador.yml` (`windows-latest`, PowerShell): build da tela; Python 3.12 **x64** e o PyInstaller do app; fumaça do app (o `GET /api/saude` com `"app": "painel-de-opcoes"`, a tela com `<div id="raiz"` e o segundo processo saindo com 0); Python 3.12 **x86** e o PyInstaller da ponte; fumaça da ponte (`PonteTryd.exe --help`); autoteste da ponte; Inno Setup (instala pelo `choco` se o runner não tiver); o instalador como artefato `PainelOpcoes-<versão>-setup`.
- Ruling: o autoteste da ponte roda com `continue-on-error`: ele precisa da type library do Tryd ou do Excel, que o runner pode não ter. Falhando no runner, ele vira item manual no PC Windows do autor (Task 7). O `--help` é a fumaça obrigatória da ponte.
- Ruling: além de `workflow_dispatch` e tag `v*`, o job roda em pull request que mexe em `packaging/**`, no próprio workflow ou em `src/options_ponte/**`. O GitHub só mostra o "Run workflow" de um arquivo que já está na branch padrão (`master`), que só recebe a `development` no fechamento de versão; sem o gatilho de PR, o instalador não poderia ser testado antes disso.
- YAML conferido com o PyYAML (12 passos). O job em si só roda no GitHub.

## 2026-11-04: Task 5 — primeira rodada do job (PR #10): build da tela quebrado no Windows

- Falha: `"Operacoes" is not exported by "src/aprender/operacoes.ts"` no `vite build` do job. O Windows não diferencia maiúsculas: com `Operacoes.tsx` e `operacoes.ts` na mesma pasta, o import `../aprender/Operacoes` (sem extensão) achou o `.ts`. O mesmo valia para `Termos.tsx` e `termos.ts`. O defeito já estava na `development` (o `operacoes.ts` veio da aba Aprender, tasks 1 a 3) e também quebraria o `npm run build` no PC Windows do autor; no Linux não aparece.
- FIXED: `operacoes.ts` → `textosOperacoes.ts` e `termos.ts` → `glossario.ts`, com os imports. `tests/packaging/test_nomes_windows.py` impede módulo da tela que difira de outro só por maiúsculas (falha com os nomes antigos, passa com os novos).
- Checagens: frontend `verificar` (194 testes) e `build`; ruff, mypy e `tests/packaging` (20 testes).

## 2026-11-04: Task 6 — instalação no Linux

- `scripts/linux/instalar.sh`:
  - confere o Python 3.12+ (`PYTHON`, padrão `python3`) e o `node`/`npm` antes de gravar qualquer coisa;
  - cria (ou reaproveita) o venv em `~/.local/share/painel-opcoes/venv` e roda `pip install -e "<repo>[app]"`;
  - compila a tela (`npm ci` e `npm run build`);
  - grava `~/.local/share/applications/painel-opcoes.desktop` a partir de `scripts/linux/painel-opcoes.desktop.in`;
  - no fim, lembra o `preparar_ponte_wine.sh --verificar`;
  - `--simular` mostra cada passo com os caminhos reais e não grava nada.
- Ruling: `pip install -e` no lugar do `pip install "<repo>[app]"` do plano. Conferido com `pip wheel`: o pacote só leva `options_engine`, sem o `options_ponte` (que o `web_app` importa e a ponte roda do `src/`) e sem a tela compilada (`static/` está no `.gitignore`, e o hatchling a deixa fora). Se errado: a instalação depende de a pasta do repositório ficar onde está; atualizar é `git pull` e rodar o script de novo.
- Ruling: o script só lembra o `preparar_ponte_wine.sh --verificar`, sem rodá-lo, porque entrar no distrobox é lento.
- Ruling: o `.desktop` não tem `Icon=`, como na Task 3; o ícone fica para a semana 5.
- O `Exec` segue a spec do Desktop Entry: aspas e escapes para caminhos com espaço ou caractere reservado, e `%` vira `%%`. Conferido com o GLib (`GKeyFile` e `shell_parse_argv`) e com o `desktop-file-validate`.
- Revisão da task aprovada, sem achados críticos ou importantes. Ficaram para depois:
  - o teste de ferramenta ausente não distingue `node` de `npm`;
  - falta teste de regressão para `\`, `"` e crase no `Exec`;
  - o `.desktop` não é gravado de forma atômica;
  - o `npm ci` refaz o `node_modules` a cada execução.
- Checagens: `tests/scripts` (19) e `tests/packaging` (20); `bash -n`; ruff; ruff format; mypy. O `shellcheck` não está instalado neste PC.

## 2026-11-04: Task 7 — conferência e documentação (parcial)

- **Gate completo verde** neste PC (Linux), na árvore com a Task 6:
  - ruff, ruff format (308 arquivos), mypy strict (304) e import-linter (3 contratos);
  - pytest com 5252 testes e cobertura de 98,39%;
  - frontend: `verificar` com 194 testes, e `build`.
- **`instalar.sh` do zero neste PC:**
  - saiu com 0, e o `desktop-file-validate` aceitou o `.desktop`;
  - o venv (Python 3.14.8) importa `options_engine` e `options_ponte` de `<repo>/src`;
  - `gtk-launch painel-opcoes` subiu o app (`GET /api/saude` ok) e a ponte no distrobox;
  - o segundo `gtk-launch` imprimiu "já está aberto" e não subiu outro servidor.
- **Documentação:**
  - README: a seção "Instalar" (Windows: instalar, SmartScreen, abrir duas vezes, atualizar, desinstalar e log; Linux: `instalar.sh`) e os links da semana 4;
  - ROADMAP: a melhoria de UX e a semana 4;
  - HANDOFF de 02/11: a tabela do §1, o item 5 do §6 e o §8, com o roteiro do PC Windows.
- **Falta, no PC Windows do autor:** o Step 2 (o roteiro do §8 do HANDOFF, com o `PonteTryd.exe diagnostico`).
- Ruling: as Tasks 6 e 7 ficam na branch `feat/instalador-linux`, em vez de reabrir a `feat/instalador`, que já estava mergeada. Se errado, só muda o nome.
- **Revisão final da branch:** nenhum achado crítico; um importante e sete menores, todos corrigidos. A re-revisão confirmou as correções.
  - Importante: o README dizia que o job roda "à mão", mas o "Run workflow" só aparece depois que o workflow chegar à `master`. Também não dizia que o artefato baixa como `.zip` e exige login. Passou a dizer, e o HANDOFF §8 aponta o artefato da execução do PR #10.
  - Menores no texto:
    - o segundo clique "não sobe outro programa e só abre a janela";
    - o estado do atalho deste PC;
    - os pré-requisitos e como ver um erro no Linux;
    - o Windows de 64 bits;
    - o cabeçalho deste ledger;
    - "o Windows ainda a conferir" na linha de status.
  - FIXED no `instalar.sh`: um venv cuja pasta existe mas cujo Python não roda (link quebrado depois de trocar a versão do Python) é refeito com `venv --clear`, também no `--simular`. Antes, o script parava com um "Errno 2" obscuro. Ganhou dois testes.
  - FIXED no teste de ferramenta ausente: agora afirma `não achei o {node|npm}`.
- Ficaram para depois:
  - o cabeçalho do `instalar.sh` não cita o caso de refazer o venv;
  - o script não confere a versão do Node (o README pede 22+ para rodar do código).

## 2026-11-04: parte 2 — IR mensal das opções (Tasks 1 a 4 e conferência)

- **As três perguntas do §3.3 do desenho:** o autor delegou ("pode seguir com o melhor jeito que
  você definiria"). Ficou o que a Receita faz; o desenho registra as respostas.
  - Ruling: preço médio por série no perfil, e não por operação da Carteira — é como a Receita e o
    informe da corretora apuram — custo se errado: com a mesma série em duas operações, as peças
    não batem uma a uma com o "Realizado" de cada operação (o total bate).
  - Ruling: custos dentro do preço (compra soma, venda desconta), com os custos reais do evento
    ou os da tabela pela mesma função da Carteira (`event_costs`) — custo se errado: o resultado
    de uma operação aberta com encerramento parcial difere do "Realizado" da Carteira, que já
    desconta todo o custo de abertura.
- **Task 1 (peças por série):** `domain/portfolio/income_tax.py`, `tax_records`. Day trade pelo
  menor entre o comprado e o vendido no dia, pelos médios do dia; a sobra entra na posição comum;
  pó a preço zero; exercício e atribuição viram nota.
  - Ruling: no teste de propriedade, o pó cai só no último dia — uma série vencida não negocia
    depois do vencimento, e `process_expiries` grava o pó na data do vencimento — custo se errado:
    a propriedade cobre menos.
  - Ruling: pó, exercício e atribuição só tiram o que existe do lado da perna na posição da série e
    nunca levantam erro (com outra operação já tendo casado a diferença, a soma ainda bate com a
    Carteira).
- **Task 2 (meses):** `monthly_tax`, com 15% e 20%, prejuízo por tipo, IR de cada tipo arredondado
  a centavos e o mínimo de R$ 10 comparado depois de arredondar.
- **Task 3 (serviço e rota):** `PortfolioService.income_tax()` e `GET /api/carteira/ir-mensal`, o
  mês mais recente primeiro.
  - Ruling: `income_tax()` não roda o vencimento (como `history()`); a Carteira carrega
    `/api/carteira`, que grava o pó, antes de a aba poder ser clicada — custo se errado: um pó não
    gravado só aparece no IR depois de abrir a Carteira.
- **Task 4 (aba):** `IrMensal.tsx`, a terceira aba da Carteira, o termo `ir-mensal` e a frase na
  tela Telas.
- **Revisão final da branch:** nenhum achado crítico; três importantes e sete menores, corrigidos
  numa rodada; a re-revisão confirmou.
  - FIXED (importante): o detalhe do mês mostrava "= R$ 0,00" quando o IR acumulado continuava
    abaixo de R$ 10; agora mostra o total (por exemplo, R$ 3,00 + R$ 5,60 = R$ 8,60) e o aviso.
  - FIXED (importante): a linha do mês ganhou a coluna Base (o desenho §3.4 a pedia; o plano a
    tinha deixado só no detalhe) e a marca "com exercício ou atribuição" ao lado do mês (§3.2).
  - Ruling: os textos mudaram em relação ao plano — "abaixo de R$ 10: soma com o IR dos próximos
    meses" (antes "soma no mês seguinte", que enganava quando o mês seguinte não tem negociação) e
    a nota de exercício ("o prêmio vai para o preço da ação, e o resultado da ação fica fora desta
    conta (o app não apura o IR de ações)"), que também vale para a call vendida atribuída. O
    plano ficou com os textos antigos, como histórico.
  - FIXED (menores): a aba recarrega quando a Carteira recarrega; o glossário diz que o preço médio
    é por série; o "pagar até" de novembro de 2027 (borda do calendário) sai 30/12/2027 em vez de
    "—"; testes a mais (série compartilhada com pó nas duas pernas, comum antes do day trade no
    mesmo dia, IR pendente atravessando mês vazio e acumulando até passar de R$ 10, abatimento
    parcial, day trade abatendo day trade) e docstrings de `tax_records` e `monthly_tax`.
  - FIXED (conferência na tela): "R$" e o valor não quebram mais de linha (espaço que não quebra).
- Ficaram para depois:
  - sem perfil aberto, o aviso aparece duas vezes (no topo da Carteira e na aba);
  - cada recarga da Carteira remonta a aba, e os meses abertos voltam fechados;
  - `sinal()` ganhou mais uma cópia (já havia três).

## 2026-11-04: parte 3 (alertas) — enquetes e plano

- Respostas do autor (§4.3 do desenho): padrões de **5 dias úteis e 2%**; stop e alvo em **todas**
  as operações, também a só de ações; comparados com o **resultado total** (realizado com custos +
  não realizado pelo preço de zerar).
- Conflito achado: o desenho pedia abrir no Montador "o encerramento das pernas atuais e a mesma
  estrutura no vencimento seguinte", mas o domínio recusa dois vencimentos numa estrutura
  (`strategy.py`, decisão nº 6). Autor: **faixa no Montador** com o custo de zerar e o caixa
  líquido; o encerramento segue pelo Encerrar da Carteira.
- Ruling: a sugestão de rolagem não é um alerta à parte; é o botão **Rolar** dos alertas de
  vencimento próximo e de risco de exercício da operação com perna vendida (mesmas condições do
  §4.1). Motivo: o mesmo gatilho geraria dois itens por perna ("alerta demais", §5). Custo se
  errado: virar um tipo a mais no `AlertKind` e uma linha na tela.
- Ruling: dispensado some até o alerta deixar de valer numa avaliação **determinada**; sem preço de
  zerar ou sem spot, o dispensado fica (o Tryd piscando não faz o alerta voltar).
- Ruling: vencimento seguinte da rolagem = o próximo mensal quando o atual é mensal; o próximo
  qualquer quando é semanal. Quantidades proporcionais à primeira perna de opção aberta.

## 2026-11-04: parte 3, Task 1 — regras dos alertas no domínio

- `domain/alerts/model.py`: `AlertSettings` (5 du e 2% por padrão; dias de 0 a 60, distância de 0 a
  20%), `AlertKind` na ordem de gravidade, `OperationSnapshot`, `AfterExpiry`, `Alert` e
  `Evaluation` (alertas + chaves indeterminadas).
- `domain/alerts/rules.py`: `evaluate(operações, avisos, spots, dias_úteis, limites)`.
- Mudança em relação ao plano: o `OperationSnapshot` leva o `stop_loss` e o `target` (antes viriam
  da `Operation`, que só os ganha na Task 2). Assim a Task 1 não depende da 2, e o domínio dos
  alertas recebe só o que usa. Também nasceu o `AfterExpiry` no domínio, porque o domínio não pode
  importar o `ExpiryNotice` da aplicação (import-linter).
- Ruling: a perna com aviso de depois do vencimento (registrar exercício, aguardando fechamento)
  só tem o aviso; o vencimento próximo e o risco de exercício dela não se repetem.
- Ruling: aviso de uma operação que não está entre as abertas é erro (`InvalidDomainValueError`),
  não é ignorado: a perna do aviso está aberta por definição.
- Ruling: borda inclusiva nos dois limites: dispara com `du == dias`, com `spot == strike·(1 − d)`
  na call (`strike·(1 + d)` na put), com `total == −stop` e com `total == alvo`.
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/alerts` e
  `tests/portfolio` (108 testes; 27 novos, um deles com hypothesis).

## 2026-11-04: parte 3, Task 2 — modelo, stop e alvo na operação

- `Operation` ganhou `template`, `stop_loss` e `target` (opcionais, no fim, com padrão `None`);
  stop e alvo precisam ser finitos e maiores que zero. `with_events` e `apply_exercise` os mantêm
  (usam `replace`).
- JSON da operação: `"modelo"`, `"stop"` e `"alvo"` só são gravados quando existem; a `versao`
  continua 1, e o arquivo de antes segue igual ao ser regravado (teste). Stop inválido no arquivo
  deixa a operação ilegível, como os outros campos.
- `RegisterOperation` e `POST /api/carteira/operacoes` levam `modelo`, `stop` e `alvo`;
  `OperacaoOut` os devolve; rota nova `PUT /api/carteira/operacoes/{id}/limites` (`null` apaga;
  operação desconhecida dá 404; stop ≤ 0 dá 422).
- O helper `_custos` da gravação virou `_numero_opcional` (agora lê também o stop e o alvo).
- Ruling: o `modelo` é gravado como veio, mesmo se o catálogo não o tiver; só a rolagem o ignora
  (Task 5). Motivo: o catálogo pode mudar depois do registro.
- Risco anotado: um app de versão anterior que regrave a operação (um encerramento feito nele)
  apaga o stop, o alvo e o modelo, porque não os conhece. Só acontece com dois PCs em versões
  diferentes no mesmo perfil.
- Falha que já existia neste PC Windows, sem relação com a Task 2:
  `tests/web/test_launch.py::test_comando_app_instalado_usa_a_tela_a_ponte_e_o_log_de_dentro_do_executavel`
  (o `app.log` não aparece). Falha igual no commit `5d366ca`, conferido numa cópia limpa. Fica
  para investigar à parte.
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/portfolio`,
  `tests/adapters/storage`, `tests/application`, `tests/web`, `tests/alerts` e `tests/config`
  (627 passando; 15 testes novos).

## 2026-11-04: parte 3, Task 3 — limites dos alertas no perfil

- `Profile` ganhou `alerts: AlertSettings | None` e a propriedade `alert_settings` (5 du e 2%
  quando `None`), como o `book`.
- `perfil.json`: campo opcional `"alertas": {"dias_vencimento", "distancia_strike"}`, gravado só
  depois que o usuário muda os limites; tipo errado ou valor fora da faixa deixa o perfil ilegível
  com o caminho e o campo, como o `book`.
- `ProfileUseCase.set_alert_settings`; `PerfilOut.alertas`; rota `PUT /api/perfil/alertas`
  (fora da faixa dá 422 de domínio e não grava; sem perfil aberto, 404).
- Três testes antigos da API de perfis comparavam o perfil inteiro: ganharam o `ALERTAS_PADRAO`.
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/adapters/storage`,
  `tests/application`, `tests/web`, `tests/alerts`, `tests/config` e `tests/domain` (1033
  passando; 14 testes novos). A única falha é a do `test_launch`, a mesma de antes (Task 2).

## 2026-11-04: parte 3, Task 4 — `AlertService` e os dispensados

- `application/ports/alerts.py`: `AlertsView` (alertas visíveis, quantos dispensados, fonte) e
  `AlertUseCase` (`evaluate(view, notices)`, `dismiss`, `restore_all`).
- Porta `DismissedAlertsRepository` (`load`, `save`) em `ports/outbound.py`.
- `application/use_cases/alerts.py`: `AlertService(dismissed_for, settings_for, clock, tz,
  market=, calendar=)`. O total é `realizado + não realizado` (`fsum`); o spot só dos ativos com
  opção vendida aberta (`last`, senão `previous_close`); "hoje" pelo fuso da B3; vencimento que o
  calendário recusa vira `None` (indeterminado).
- Dispensados: mantém só `dispensados ∩ (ativos ∪ indeterminados)` e grava só quando muda (o
  WebSocket avalia a cada ciclo).
- `adapters/outbound/storage/dismissed_alerts.py`: `alertas.json` na pasta do perfil
  (`{"versao": 1, "dispensados": [...]}`, ordenado, escrita atômica). Ilegível é lido como vazio e
  nunca sobrescrito (`UnreadableRecordError` no `save`); pasta fora do ar no `save` dá
  `ProfileFolderUnavailableError`.
- Ruling: o `AlertService` recebe `settings_for` (uma função) em vez do `ProfileUseCase` inteiro:
  só precisa dos limites, e o teste fica sem perfil falso.
- Ruling: sem log quando o `alertas.json` está ilegível; o aviso chega ao usuário quando ele tenta
  dispensar (422 com o caminho). Custo se errado: um arquivo quebrado passa despercebido até o
  primeiro "Dispensar".
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/application`,
  `tests/adapters/storage` e `tests/alerts` (394 passando; 21 testes novos).

## 2026-11-04: parte 3, Task 5 — rolagem

- `RollSuggestion` e `RollUseCase` em `application/ports/alerts.py`; `RollService` em
  `application/use_cases/roll.py`, com `open_operations` (a Carteira marcada) e `suggest` (o
  `StrategyBuilderService.suggest`) injetados como funções.
- Vencimento atual: o mais próximo entre as opções vendidas abertas. Seguinte, pela cadeia do ativo
  (`list_expiries`): o próximo mensal se a vendida é mensal; o próximo qualquer se é semanal.
- Estrutura nova: `suggest(ativo, modelo, seguinte)` com as quantidades multiplicadas por
  `round(opções abertas / opções sugeridas)` (no mínimo 1); sem modelo, modelo fora do catálogo
  ou sem vencimento seguinte, `request = None`.
- Caixa de zerar: comprada recebe o bid, vendida paga o ask, pelas marcas da Carteira; `None` se
  alguma perna de opção está sem preço de zerar.
- Ruling: a ação do modelo (venda coberta, put protetora, collar) entra como **da carteira**
  quando a operação já tem ação comprada aberta, para a rolagem não sugerir comprar as ações de
  novo. Custo se errado: o Montador mostraria a compra da ação junto da opção nova.
- Ruling: a escala usa a soma das quantidades de opção (abertas ÷ sugeridas), não a primeira perna:
  dá o mesmo nas estruturas 1×1 e segue certo na borboleta (1×2×1). Operação com pernas
  desiguais (encerramento parcial de uma perna) arredonda para o inteiro mais perto.
- Ruling: erro da cadeia (ativo sem cadeia) sobe como está; a rota vira o 404/422 de sempre.
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/application` e
  `tests/alerts` (287 passando; 13 testes novos).

## 2026-11-04: parte 3, Task 6 — rotas e WebSocket

- `adapters/inbound/web/portfolio.py`: `carteira_atual` deu lugar a `ler_carteira` (vencimento +
  carteira aberta, devolve `CarteiraLida` com a visão e os avisos) e `carteira_out` (pública). A
  rota `GET /api/carteira` e o WebSocket usam as duas.
- `adapters/inbound/web/alerts.py`: `GET /api/alertas`, `POST /api/alertas/{chave}/dispensar`
  (204), `POST /api/alertas/restaurar` (204) e `GET /api/alertas/rolagem/{operacao_id}`; o
  `pedido` da rolagem sai pelo `pedido_out` do Montador (o mesmo formato que o Book manda).
- WebSocket: mensagem `alertas`, da mesma leitura da carteira (uma consulta de mercado para as
  duas), enviada só quando muda. Sem perfil aberto ou pasta fora do ar, a mensagem leva o erro,
  como a da carteira.
- `config/web_app.py`: `AlertService` (dispensados em `JsonDismissedAlerts` na pasta do perfil,
  limites de `profiles.active().alert_settings`) e `RollService` (`portfolio.open_operations` e
  `builder.suggest`, o do mercado ao vivo).
- Ruling: a rolagem usa o `builder` do mercado ao vivo (com recuo para o fim de dia), não o
  `book_builder` só de fim de dia: a sugestão é para agir no pregão.
- Checagens: ruff, ruff format, mypy, import-linter e as suítes `tests/web`, `tests/config`,
  `tests/application`, `tests/alerts` e `tests/adapters/storage` (9 testes novos). A única falha é
  a do `test_launch`, a mesma de antes (Task 2).

## 2026-11-04: parte 3, Task 7 — aba Alertas e a contagem no menu

- `api/alertas.ts` (tipos e as quatro rotas), `LimitesAlertas` e `definirLimitesAlertas` em
  `api/cliente.ts` (o `Perfil` ganhou `alertas`), mensagem `alertas` no `aoVivo.ts`.
- `paginas/Alertas.tsx`: grupos por operação na ordem do primeiro alerta (a lista já vem por
  gravidade), uma frase por alerta com **Dispensar**, e por operação **Abrir na Carteira** e
  **Rolar** (quando algum alerta dela pode rolar); "Mostrar dispensados (N)" restaura todos; os
  limites no fim da página (dias úteis e % do strike, gravados em fração). Rótulo "pelo fim de dia
  (B3)" (ou "com preços atrasados") quando a fonte não é ao vivo.
- Menu: "Alertas (N)" com os alertas não dispensados, pelo WebSocket; sem alertas, só "Alertas".
- Carteira: `?operacao=<id>` abre a operação e a rola para a vista (`id="operacao-<id>"` na linha).
- `formatarReais` foi para `formatacao.ts` (era o `reais()` do IR mensal) e serve as duas telas;
  o `sinal()` ficou como estava.
- `paginas/EmBreve.tsx` e o CSS `.em-breve` saíram: Alertas era a última área "em breve".
- Ruling: Rolar navega ao Montador com `state: { pedido, rolagem }`, como o Book (`pedido`); a
  faixa que usa a `rolagem` é a Task 8. Até lá o Montador abre só o pedido.
- Ruling: o "?" do glossário nos alertas fica para a Task 8, junto dos termos novos (sem termo, o
  link levaria a um termo que não existe).
- Checagens: `npm run verificar` (tsc + 225 testes; 13 novos).
