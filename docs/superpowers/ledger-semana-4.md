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
