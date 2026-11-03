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
