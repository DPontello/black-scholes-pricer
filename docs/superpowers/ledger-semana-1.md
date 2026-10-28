# Ledger da execução — semana 1 do app (cópia de 2026-10-28)

> Cópia versionada do ledger do subagent-driven-development (o original fica em
> `.superpowers/sdd/`, que o git ignora). Os hashes "trees"/"foto" são fotos locais do
> working tree (objetos tree do git, não commits) e **não existem em outro clone**:
> o mapeamento tarefa → commit está em [`HANDOFF-2026-10-28.md`](HANDOFF-2026-10-28.md).
> Linhas `Ruling:` são decisões tomadas pelo controlador em nome do autor (com o custo
> se estiverem erradas); linhas `minor (deferred)` são pendências para a revisão final.

## Ledger original — plano: docs/superpowers/plans/2026-10-28-app-semana-1-base.md

Spec: docs/superpowers/specs/2026-10-28-app-opcoes-design.md
Workspace: .superpowers/sdd/2026-10-28-app-semana-1-base/
Foto inicial (tree, sem commit): S0 = 8f885730b2ada0a61fce6e5445a047bcab90cd94 (HEAD a845a3a, development)
Fotos: `bash snap.sh` (tree do working tree); pacotes: `bash pkg.sh TREE_A TREE_B SAIDA`.

## Decisões de processo

- Ruling: sem commits; cada tarefa é delimitada por fotos do working tree em objetos tree do git (write-tree num índice temporário), e o diff da revisão é entre duas fotos — o CLAUDE.md global do autor proíbe commit/push/merge — se errado: nenhum; o autor commita depois.
- Ruling: sem worktree e sem branch nova; o trabalho acontece no working tree da `development` (limpo no início, só com docs/superpowers novos) — commit/branch são do autor e mudanças não commitadas não se isolam por branch — se errado: o autor cria a feat/ antes de commitar.
- Ruling: implementers = subagent_type "implementer" (exigido pelo CLAUDE.md); revisores = "general-purpose". O Agent tool não aceita escolha de modelo; vale o da definição de cada tipo — se errado: custo maior nas revisões.

## Varredura pré-execução

| Par / tarefa | Produz → consome | Achado |
|---|---|---|
| T1 ↔ T4, T5 | `ERROR_STATUS` em web/errors.py, estendido | ok |
| T2 ↔ T3 | VOs e exceções de perfil | ok |
| T3 ↔ T4, T12, T13 | `ProfileUseCase` | ok |
| T5 ↔ T11 | `B3FileLibrary(root, clock)` | ok |
| T5 ↔ T12 | `cadastro_freshness` → `freshness`; faixa do COTAHIST → `cotahist_range` | **conflito**: T5 não expõe a primeira data do COTAHIST (só a última) — ver Ruling 1 |
| T6 ↔ T11 | `InstrumentInfo` com tipo/strike/vencimento; `realized_volatility` | ok |
| T7 ↔ T8, T9 | protocolo (inclui `Encerrar`), `SessaoRtd`, `Ponte`, `ServidorTcp` | ok |
| T9 ↔ T10, T11, T12 | `LiveBoard`, `RawValue`, `TrydBridgeClient`, `BridgeProcess`, `default_bridge_command` | ok |
| T10 ↔ T11 | `to_underlying_quote`, `to_option_quote` | ok |
| T11 ↔ T12 | `MarketPort` | ok (corrigido no plano antes da execução) |
| T12 ↔ T13 | `build_web_app`; T13 acrescenta o router de mercado | ok (corrigido no plano) |
| T12 ↔ T14 | `build_web_app(..., bridge=...)` | ok |
| T13 ↔ T16, T17 | endpoints e WS | ok |
| T15 ↔ T14 | `static/` gerado pelo build; T14 exige `index.html` | ok |
| T1 interno | Step 1 instala o extra antes de editar o pyproject | ordem: editar o pyproject antes de instalar — Ruling 2 |
| T2 interno | testes x VOs | ok |
| T3 interno | sequência do teste de trava | ok (conferida passo a passo) |
| T4 interno | ok | ok |
| T5 interno | datas 5/6 dias úteis | ok (conferidas no calendário empacotado: 5 e 6) |
| T6 interno | mensagem "mínimo 22" | ok (igual à do adapter atual) |
| T7–T10 internos | ok | ok |
| T11 interno | série da fixture sem `OptnStyle` | conferir na execução; se não houver, o teste cria uma linha no CSV da biblioteca de teste |
| T12, T13 internos | ok | ok |
| T14 interno | teste "sem static → código 2" pode achar o `static/` real do build local | Ruling 3 |
| T15–T17 internos | ok | ok |
| T18 | depende do autor (arquivos reais da B3, Tryd aberto) | ok |

- Ruling 1: `ImportedFile` ganha `first_date: date | None` (COTAHIST = menor pregão do arquivo; CADASTRO = None); `cotahist_range` = (menor `first_date`, maior `reference_date`) entre os COTAHIST importados — o plano pede `{"de", "ate"}` e T5 não dava como calcular "de" — se errado: campo a mais, removível.
- Ruling 2: na T1, editar o pyproject (extra `app`, httpx, versão) ANTES do `pip install -e ".[dev,app]"` — a ordem do plano não instalaria nada novo — se errado: nenhum.
- Ruling 3: na T14, o diretório estático vem de uma função `default_static_dir()` que o teste substitui (monkeypatch) por um caminho inexistente — senão o teste depende de o build ter rodado — se errado: nenhum.

## Progresso
Task 1: start (base tree S0=8f88573)
Task 1: implementer agent a6a70a36f46f4dcd2
Task 1: DONE_WITH_CONCERNS (warning de depreciação do httpx no TestClient)
- Ruling: dev usa `httpx2>=2.16` no lugar de `httpx>=0.27` — o Starlette 1.10 importa httpx2 primeiro e marca httpx como obsoleto; saída de teste deve ser limpa — se errado: troca de uma linha no pyproject.
Task 1: foto pós-implementação S1=f6476d9369fc1572605449e900acea20056ada46
Task 1: review 1 — spec ❌ (docs/openapi fora de /api), Important: /%00 → 500 no resolve()
Task 1: minor (deferred): falta teste do curinga da SPA com rota real (ordem dos routers)
Task 1: minor (deferred): ramos sem teste (index.html ausente → 404; /api sem barra)
Task 1: minor (deferred): erros não-domínio saem {"detail": ...} em inglês; 422 de validação pydantic tem corpo diferente do 422 de domínio — decidir na T4 (frontend distingue)
Task 1: minor (deferred): contrato stdlib-only não lista uvicorn, websockets, httpx2
Task 1: minor (deferred): README quickstart ainda `.[dev]` → T18 deve trocar para `.[dev,app]`
Task 1: minor (deferred): wheel do hatchling exclui web/static/ (gitignored) → empacotamento da semana 4 precisa de `artifacts`
Task 1: fix round 1 foto S1b=781388ced96805590d7ebc6e83a91d6ab384ce18
Task 1: fix round 1/5 (2 addressed, 0 open; trees f6476d9..781388c)
Task 1: minor (deferred): /api/docs e /api/redoc sem asserção própria
Task 1: complete (trees 8f88573..781388c, review clean)
Task 2: start (base tree 781388c)
Task 2: implementer agent ac88d7bd52c7425e8
Task 2: DONE, foto S2=60ca31fa0d6a5f5281b31f85a62a82bbb612a858
Task 2: review clean (0 Critical/Important)
Task 2: minor (deferred): predicado tz-aware em 3 lugares (market.py, chain.py, quotes.py) — helper compartilhado num refactor
Task 2: minor (deferred): ramo tzinfo com utcoffset None sem teste em test_quotes.py
Task 2: minor (deferred): teste redundante test_excecoes_de_perfil_sao_domain_error; mensagens de Profile sem asserção de texto
Task 2: minor (deferred): ProfileLockedError formata `since` no fuso do objeto — Task 3 deve construir com horário local (B3)
Task 2: minor (deferred): pickle de ProfileLockedError não reconstrói; testes de domínio importam B3_UTC_OFFSET de adapters
Task 2: complete (trees 781388c..60ca31f, review clean)
Task 3: start (base tree 60ca31f)
Task 3: implementer agent a6f8ea671e44c4294
Task 3: DONE_WITH_CONCERNS (fuso e CDI replicados com teste de amarração; extras defensivos), foto S3=6bbbea1f1b1834f91f1c948eb478ac25e960606d
Task 3: review 1 — Important: nome do perfil.json divergente do cadastro faz o serviço gravar na pasta de outro perfil e soltar a trava errada (reproduzido)
- Ruling: o Minor 3 da revisão (OSError solto: PermissionError/FileNotFoundError/IsADirectoryError na gravação/leitura/unlink) entra na rodada 1 como Important — é o Review Focus 3 do plano ("pasta indisponível → erro claro") e no Windows a nuvem segura arquivos — se errado: um embrulho de exceção a mais.
Task 3: minor (deferred): trava não é renovada com o app aberto >12 h; trava com `desde` no futuro nunca expira — avaliar heartbeat/renovação depois (semana 2+)
Task 3: minor (deferred): create checa nome pedido antes da adoção (DuplicateProfileError por nome irrelevante) — revisar mensagem na UI (T16)
Task 3: minor (deferred): trava ilegível descartada em silêncio (sem log); falta teste de "falha no save não troca o ativo"; InvalidDomainValueError usado para arquivo corrompido (T4 mapeia)
Task 3: fix round 1 foto S3b=08139e7f60a3e0d41a2a01eb6aa8a425307b9e96
Task 3: minor (deferred): OSError ao gravar o config.json da máquina continua solto
Task 3: fix round 1/5 (2 addressed, 0 open; trees 6bbbea1..08139e7)
Task 3: minor (deferred): release_lock levanta PermissionError cru se o config.json da máquina for ilegível (_read_entries sem embrulho) — T12 (lifespan) deve fechar o perfil sem derrubar o desligamento
Task 3: minor (deferred): docstring de ProfileFolderUnavailableError desatualizada (agora cobre permissão/arquivo em uso)
Task 3: complete (trees 60ca31f..08139e7, review clean)
- Ruling (T4): a API unifica o formato de erro: além de DomainError, RequestValidationError → 422 {"erro": "RequisicaoInvalida", "mensagem": <pt-BR>, "detalhes": [...]} e HTTPException do Starlette (404/405) → {"erro": "NaoEncontrado"|"MetodoNaoPermitido"|..., "mensagem": <pt-BR>} — minor deferido da T1; o frontend (T16) distingue um formato só e a mãe vê mensagem em português — se errado: só formato de corpo de erro.
Task 4: start (base tree 08139e7)
Task 4: implementer agent ad4bcb98cba1f9a30
Task 4: DONE, foto S4=12985605e13e0be1764db94684fcf5dc12245f34
- Ruling: aceitar `/api/perfis/{nome:path}/abrir` (nome livre no domínio pode ter "/") e corpo obrigatório em abrir (o plano descreve {"forcar": false}) — se errado: troca trivial.
Task 4: minor (deferred): OpenAPI ainda descreve o 422 no molde padrão do FastAPI (corpo real é o molde novo)
Task 4: review clean (0 Critical/Important, 6 Minor)
Task 4: minor (deferred → T12): ProfileService._active sem lock; endpoints def no threadpool + WS (T13) concorrentes — T12 põe threading.Lock no ProfileService
Task 4: minor (deferred): handler de HTTPException devolve corpo em 204/304 (falta guarda is_body_allowed_for_status_code)
Task 4: minor (deferred): HTTPException fora de 404/405 perde o detail → tarefas seguintes levantam DomainError/erros tipados, não HTTPException
Task 4: minor (deferred → T13): 500 inesperado sai texto puro, fora do formato único — handler de Exception
Task 4: minor (deferred): OpenAPI sem o molde novo de 422 nem 404/409; forcar aceita "yes"/1 (StrictBool); ramo de campo aninhado sem teste
Task 4: complete (trees 08139e7..1298560, review clean)
Task 5: start (base tree 1298560)
Task 5: implementer agent ab2a06879d1fc56c8
Task 5: DONE_WITH_CONCERNS, foto S5=7e94314c4eed4870c6554b02dded156040084d44
Task 5: minor (deferred → T12): cadastro_freshness propaga erro do calendário fora de 2024–2027 — status do mercado deve capturar e mostrar "data fora do calendário"
Task 5: minor (deferred → T12/T16): cadastro sem _AAAAMMDD no nome → frescor None igual a "sem cadastro" — status/tela deve distinguir via latest_cadastro()
Task 5: minor (deferred): upload sem limite de tamanho (app local; COTAHIST anual é grande)
Task 5: review clean (0 Critical/Important, 5 Minor)
Task 5: minor (deferred): motivo da recusa com trecho em inglês para csv.Error/zlib.error/EOFError (library.py ~301/309-315)
Task 5: minor (deferred): nome aceito pode virar OSError cru → 500 (limite em bytes, nomes reservados do Windows, maiúsculas)
Task 5: minor (deferred): temporário *.tmp colide com nome do usuário (x.csv.tmp)
Task 5: minor (deferred): janela entre os.replace e gravação do índice (órfão/metadados velhos); pastas vazias criadas na falha
Task 5: minor (deferred): ZIP truncado recebe "tipo não reconhecido" (UX); STALE_CADASTRO_BUSINESS_DAYS mora em library.py
Task 5: note (→ T12): root da biblioteca é config_dir/mercado (local); frescor: tratar data futura, fora do calendário e cadastro sem data
Task 5: complete (trees 1298560..7e94314, review clean)
Task 6: start (base tree 7e94314)
Task 6: implementer agent a4ab24edfb6db45be
Task 6: DONE, foto S6=7239199884b91ea0da720c8cfac8ee2c16a824e4
Task 6: review clean (0 Critical/Important, 6 Minor)
Task 6: minor (deferred → T18): "1,234" vira 1.234 (vírgula lida como decimal) — conferir separadores do ExrcPric no arquivo real; float() aceita "1_0"/"1e2" (regex estrita seria mais defensiva)
Task 6: minor (deferred): divergência só nos termos zera estilo → motivo "sem estilo de exercício" engana; window<2 validado com ValueError cru duplicado; closes com NaN → motivo "vol zero"
Task 6: minor (deferred): ramo indice>=len(celulas) sem teste; asserção redundante no último teste de test_instruments
Task 6: complete (trees 7e94314..7239199, review clean)
Task 7: start (base tree 7239199)
Task 7: implementer agent a8802427f21fb9664
Task 7: DONE_WITH_CONCERNS (reassinatura sem valor; servidor.py 355 linhas)
- Ruling: a ponte guarda o último Valor por tópico e o reemite quando um tópico já assinado é assinado de novo (reconexão do app, segundo cliente), sem chamar conectar — sem isso, após reconectar, série sem negócio novo fica sem valor e, pela regra de carga de 3 s (T9), viraria "book vazio" falso — se errado: memória proporcional aos tópicos (≤ 600).
Task 7: minor (deferred): options_ponte fora de coverage.source e do wheel (rtd.py da T8 não roda no Linux; decidir na semana 4)
Task 7: DONE (cache incluso), foto S7=5203d43ca45386d2f0cda71af67b64852eac2e7c
Task 7: review 1 — Important: codificar sem proteção em _difundir; str com surrogate solto (UnicodeEncodeError) derruba o laço e a sessão COM
- Ruling: o Minor 4 da revisão (falha de atualizar() consome o aviso sem nova tentativa → feed pode ficar parado parecendo ao vivo) sobe a Important — é o anti-objetivo "dado parado mostrado como ao vivo" da spec — se errado: um retry a mais por ciclo.
Task 7: minor (deferred): decodificar não cobre RecursionError (thread do cliente morre; ponte segue)
Task 7: minor (deferred): linha sem \n e fila de comandos sem teto; leitores nunca podados (Wine: shutdown não acorda recv)
Task 7: minor (deferred): Cancelar sem contagem de referência (app + espiar); várias falhas em _cancelar geram vários Status; testes tocam estado privado; decodificar não valida tipo_valor
Task 7: minor (deferred, exigido pelo plano): servidor.py junta sessão/Ponte/ServidorTcp (368 linhas) — dividir em ponte.py + servidor.py depois
Task 7: fix round 1 foto S7b=15d281965c12ff567cb78dadbc111ecf12b5c67c
Task 7: fix round 1/5 (2 addressed, 0 open; trees 5203d43..15d2819)
Task 7: minor (deferred): Status com motivo não codificável é descartado em silêncio (sanear motivo em _perdeu); warning por tick para ticker malformado de cliente; sendall(b"") quando tudo é descartado
Task 7: note (→ T8): retry de atualizar a cada volta sem espaçamento mínimo — medir no Wine se RefreshData bloqueia (Tryd pendurado) e considerar espaçamento (~1 s) após falha
Task 7: complete (trees 7239199..15d2819, review clean)
Task 8: start (base tree 15d2819)
Task 8: implementer agent a8ab5c134606eb760
Task 8: DONE_WITH_CONCERNS — ao vivo no Wine ok (autoteste OK; CLSID; typelib do Tryd não carrega no Wine → shim Excel 1.4; 133 valores/10 s; Encerrar rc 0); RefreshData bloqueia sem prazo com servidor pendurado (6,9 s medido)
- Ruling: `espiar` NÃO cancela os tópicos ao sair (a Ponte não conta referências; cancelar derrubaria os mesmos tickers do app, que mostraria valor parado como ao vivo) — se errado: tópicos do espiar ficam assinados até a ponte encerrar (≤ poucos tópicos).
- Ruling (→ T9): BridgeProcess.stop envia Encerrar e espera antes de terminate() (timeout no distrobox não mata o wine python); o app relança a ponte se o processo sair ou o Tryd ficar perdido por > PONTE_PERDIDA_S, com espera de 10 s entre tentativas — a ponte não reconecta ao Tryd sozinha — se errado: relançamentos a mais.
Task 8: minor (deferred): rtd.py com 632 linhas (único módulo com pywin32)
Task 8: DONE (espiar sem cancelar), foto S8=f00ff5337fcc3c538e6cc94c94abbc934e8e6758
Task 8: review clean (0 Critical/Important, 12 Minor)
Task 8: minor (deferred): rtd.py junta cliente/diagnóstico/autoteste (632 linhas); servidor-falso aparece no --help (==SUPPRESS==) e description com crases
Task 8: minor (deferred): _esperar órfão e nome enganoso em test_cli; servir sem teste do caminho feliz (Encerrar rc 0, KeyboardInterrupt, corrida de bind)
Task 8: minor (deferred): encerrar() engole exceção sem log; autoteste sem traceback e readline sem prazo; zip(strict=False) no RefreshData descarta divergência em silêncio
Task 8: minor (deferred): script: curl direto no destino (sem .part/hash), grep -q com pipefail, $USER com set -u, --verificar pode iniciar a caixa; docstring "só lê" do diagnostico
Task 8: minor (deferred): cabeçalho do rtd_shim.idl desatualizado; README sem __main__.py e sem orientação p/ Windows 64 bits sem Office; main trata comando desconhecido como espiar; spike tryd_poc.py duplicado/divergente
- Ruling (→ T9): constantes da ponte com fonte única em options_ponte/protocolo.py (PORTA_PONTE=8766, LIMITE_TOPICOS=600, CAMPOS_ATIVO, CAMPOS_OPCAO); __main__.py da ponte e adapters/outbound/tryd/settings.py importam de lá — Minor 8; o plano manda fonte única — se errado: só imports.
- Ruling (→ T9): BridgeProcess.start primeiro tenta falar com uma ponte já viva na porta (Ping→Pong) e a adota; só lança se não houver. stop: Encerrar → espera 3 s → terminate() → no Linux, se a porta ainda responder, `distrobox enter tryd -- pkill -f "options_ponte servir"` — timeout/terminate não matam o wine python e a 2ª ponte recusa a porta ocupada — se errado: comando extra de limpeza.
Task 8: note (→ T18): com o Tryd fechado, CoCreateInstance pode iniciar o tryd.exe (tela de login) — medir no ponta a ponta
Task 8: complete (trees 15d2819..f00ff53, review clean)
Task 9: start (base tree f00ff53)
Task 9: implementer agent a023b0b17c35435f9
Task 9: DONE_WITH_CONCERNS (pkill com "[o]ptions_ponte servir"; ponte adotada que cai não é relançada; app importa options_ponte mas o wheel não o inclui)
- Ruling: ensure_running relança quando NENHUMA ponte responde na porta, tenha sido adotada ou lançada por nós (mantém 10 s entre tentativas); stop() continua sem encerrar ponte adotada — o texto da decisão anterior deixava o app sem dados ao vivo até reiniciar se a ponte adotada caísse — se errado: uma ponte a mais lançada quando a adotada some.
Task 9: note (→ T12): start()/ensure_running podem bloquear até 2 s (Ping sem Pong) — chamar fora do event loop (threadpool/thread própria)
Task 9: minor (deferred → semana 4): pyproject packages só tem options_engine; app importa options_ponte.protocolo — wheel/instalador precisa incluir options_ponte
Task 9: DONE (relança adotada), foto S9=6191b93542ee5fe9ed6ee7b7d703ab206fb25cfd
Task 9: review 1 — Important: LiveBoard nunca reinicia "carregou" (cancelar+reassinar; reconexão à ponte relançada) → zeros iniciais do RTD passam como lado vazio
- Ruling: o Minor 4 (Status "iniciando" conta como CONECTADA) sobe a Important: "iniciando" → ATRASADA — a UI diria "ao vivo" sem dado nenhum (anti-objetivo da spec) — se errado: "Atrasado" por alguns segundos ao abrir.
Task 9: minor (deferred): BridgeProcess.start não idempotente (2ª chamada pode orfanar a ponte nossa)
Task 9: minor (deferred): ensure_running não relança processo nosso vivo e mudo (distrobox pendurado nunca recuperado); log de erro a cada 10 s se o distrobox não existir
Task 9: minor (deferred → T11/T12): tópicos vazam na ponte (registro global; Cancelar perdido sem conexão; ponte adotada com tópicos de app antigo pode estourar 600)
Task 9: minor (deferred): testes de thread-safety/"uma vez"/asserção negativa mais fracos do que parecem; sem wait() após terminate (zumbi); locks segurados durante bridge_responds (T12 fora do event loop)
Task 9: fix round 1 entregue (forget/reinício e iniciando→ATRASADA); implementer apontou defeito do plano: o 1º Valor é o zero inicial do ConnectData e já marca "carregado"
- Ruling: o protocolo ganha `Valor.inicial: bool` (default False); a Ponte marca True no valor do ConnectData e no reemitido do cache quando ele ainda é o do ConnectData (vira False quando um RefreshData atualiza o tópico); LiveBoard.apply guarda o valor inicial mas NÃO marca carregado — carregado = Valor não inicial depois da assinatura, ou TEMPO_CARGA_S — a regra do plano ("qualquer Valor") deixava os zeros de "carregando" passarem como lado vazio — se errado: série com valor inicial real espera até 3 s para aparecer.
Task 9: fix rounds 1+2 foto S9b=68090d11741bf5c40bf41f253661f79d79f2ee57
Task 9: fix round 2/5 (re-review: achados 2 e 3 ADDRESSED; 1 com furo N1 Important — Valor em trânsito após forget deixa _updated preso → reassinatura com zero inicial aparece carregada; reproduzido)
- Ruling: rodada 3 inclui, além do N1 (forget+mark_subscribed dos tickers novos em ensure_subscribed sob _conn_lock), (a) LiveBoard.apply descarta Valor de ticker não assinado (ponte difunde tópicos de espiar/instância antiga) e (b) RawValue ganha `initial: bool` (carga por campo visível à T10) — fecham a mesma classe de defeito (dado parado/zero como real) — se errado: um campo e um filtro a mais.
Task 9: minor (deferred): forget em toda reconexão (opção some por 3 s após queda de socket); health CONECTADA por ~2 s na reconexão antes do 1º Status; sem handshake de versão ponte×app
Task 9: fix round 3 foto S9c=878a94c5ead4480df68b23f46389c176db792bdf
Task 9: fix round 3/5 (N1 + RawValue.initial addressed, 0 open; trees 68090d1..878a94c)
Task 9: minor (deferred): janela residual A→vazio→A antes do Valor pré-Cancelar chegar (sem geração por assinatura; ms); ordem mark-antes-do-envio sem teste; teste de threads do board mais fraco; _log.debug sob a lock
Task 9: note (→ T10/T11): contrato novo — RawValue.initial por campo; apply descarta ticker não assinado; composição não precisa chamar mark_subscribed (plano atualizado)
Task 9: complete (trees f00ff53..878a94c, review clean after 3 rounds)
Task 10: start (base tree 878a94c)
Task 10: implementer agent a67bfeeba06a5273e
Task 10: DONE_WITH_CONCERNS (vazio+loaded → None; book cruzado no ativo → None; NEG/VOL lixo no ativo → None), foto S10=24e3d38716a351c8f923812e9d05c2bb7c487e24
- Ruling: aceitar as decisões conservadoras da T10 (na dúvida, sem cotação; nunca valor inventado) — coerente com a ADR-0003 e o anti-objetivo de número errado em silêncio — se errado: ativo some do painel em leilão/dado sujo.
Task 10: note (→ T11): fallback_time quando HOR/DAT ilegíveis — usar o relógio injetado no momento da leitura, e a origem continua rotulada pela fonte
Task 10: review clean (0 Critical/Important, 4 Minor)
Task 10: minor (deferred): NEG/VOL em texto "1.000" vira 1 (caminho praticamente inalcançável: RTD manda int/float)
Task 10: minor (deferred): kind tratado assimétrico (_text aceita kind "outro"; "none" com valor lido); docstrings sem exigir fallback_time tz-aware; teste com lógica condicional; sem teste de initial+loaded no ativo
Task 10: note (→ T11): warnings do ativo a cada chamada (book cruzado/lixo persistente) — deduplicar/limitar no polling
Task 10: complete (trees 878a94c..24e3d38, review clean)
Task 11: start (base tree 24e3d38)
Task 11: implementer agent a1a2ecc0b343b10ee
Task 11: DONE_WITH_CONCERNS, foto S11=1cbd1d65669cd74eab52bf2fd8e56109f06c5875
- Ruling: vínculo série↔ativo no ao vivo = UndrlygTckrSymb1 do cadastro; senão raiz única entre os ativos do COTAHIST; raiz dividida (PETR3/PETR4) sem UndrlygTckrSymb1 → rejeitada — o cadastro real da B3 deve trazer UndrlygTckrSymb1 para opções; a T18 confere no arquivo real e, se vier vazio, abre correção com a regra do ESPECI do adapter COTAHIST — se errado: opções de PETR4 rejeitadas no ao vivo até a correção.
- Ruling: aceitar spot de referência do watch = último fechamento do COTAHIST quando ainda não há ULT; biblioteca vazia não marca ticker como desconhecido; calendar não usado nesta task — sensatos e documentados — se errado: faixa de strikes inicial um pouco diferente.
Task 11: minor (deferred): séries sem estilo são assinadas (gastam tópicos) — filtrar na assinatura; cadastro lido duas vezes por mudança
Task 11: review 1 — Important 1: raiz dividida sem UndrlygTckrSymb1 → cadeia vazia sem motivo (reproduzido); Important 2: ponte de pé + Tryd fechado → saúde ATRASADA para sempre, fim de dia nunca entra (Review Focus 1)
- Ruling (Important 2): opção B — TrydBridgeClient.health() vira DESCONECTADA quando o último Status do Tryd é "perdido" (ou "iniciando") há mais de PONTE_PERDIDA_S (30 s) sem Status "conectado" depois; entre 0 e 30 s segue ATRASADA — falha curta continua "atrasado", Tryd fechado cai para o fim de dia rotulado, sem mistura por ativo — se errado: 30 s de "atrasado" antes do recuo.
Task 11: minor (deferred): OSError de leitura fica guardado no LibraryLoader até files() mudar; watch/get_quotes descartam motivo do loader sem log
Task 11: minor (deferred): regras duplicadas com o adapter COTAHIST (_END_OF_SESSION, _ou_none, raiz 4, janela 21, snapshot); séries sem estilo assinadas; latência de parse do anual no caminho quente; root da biblioteca via cadastro.path.parent.parent; dois LibraryLoader; feed.py 379 linhas; teste de threads fraco
Task 11: note (→ T12/T17): AO_VIVO não considera idade de DAT/HOR (mercado fechado mostra último negócio de ontem como ao vivo) — a tela deve mostrar data quando a hora não é de hoje; rótulo da cadeia vs TOCTOU de health() na T12
Task 11: fix round 1 interrompido por limite de uso (implementer parou antes dos testes de integração do FallbackMarket); retomado após o reset
Task 11: fix round 1 entregue (ambíguas → rejected_series; health DESCONECTADA após 30 s de perdido/iniciando), foto S11b=751c9fcb6e9bd52cf22d647dbba0544e5ef59986 — RE-REVIEW PENDENTE (pausa a pedido do autor para push e passagem de PC)
