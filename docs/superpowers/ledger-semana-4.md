# Ledger — semana 4 (instalador, IR mensal e alertas)

Desenho: [`specs/2026-11-03-semana-4-instalador-ir-alertas-design.md`](specs/2026-11-03-semana-4-instalador-ir-alertas-design.md).
Parte 1, plano: [`plans/2026-11-03-semana-4-parte-1-instalador.md`](plans/2026-11-03-semana-4-parte-1-instalador.md).
Branch `feat/instalador`, a partir da `development` (`0c8e09b`).

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
