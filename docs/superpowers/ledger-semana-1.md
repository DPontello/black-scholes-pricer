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

## Retomada em 2026-10-29 (Windows 11, outra máquina)

- Ruling: sem subagents nesta máquina (não há o tipo `implementer` nem a skill de SDD); o controlador implementa e revisa inline, tarefa a tarefa, mantendo a regra de não commitar — se errado: cada tarefa teve um revisor só; a revisão final da semana deve ser de outro revisor.
- Gates no Windows (Python 3.14.5, 1º uso fora do Linux): 1 falha só do Windows — `default_bridge_command` montava o `WINEPREFIX` com `str(Path)` (barras invertidas no Windows). Corrigido com `as_posix()`; 4500 passam.
Task 11: re-review — Important 1 (raiz dividida sem `UndrlygTckrSymb1`) ADDRESSED: ambíguas em `rejected_series`, os vencimentos contam as ambíguas, `watch` não as assina (test_serie_de_vinculo_ambiguo_sai_rejeitada_e_nao_cotada, test_cadeia_com_todas_as_series_ambiguas_..., test_watch_nao_assina_serie_cujo_ativo_objeto_e_ambiguo). Important 2 (ponte de pé com o Tryd fechado) ADDRESSED: `health()` DESCONECTADA após 30 s de iniciando/perdido sem `conectado` (testes do cliente e test_ponte_de_pe_com_o_tryd_fechado_recua_para_o_fim_de_dia_apos_30_s).
Task 11: minor (deferred): série sem ativo-objeto no cadastro, de raiz com um só ativo nos COTAHIST, é atribuída a qualquer ticker dessa raiz que o cadastro conheça (PETR3 só no cadastro receberia as séries de PETR4). Com COTAHIST real os dois aparecem e a série vira ambígua; corrigir guardando o dono da raiz em `_Row`.
Task 11: note (→ T18, Important a medir): Tryd fechado com o app aberto → a ponte marca perdido e segue de pé; ela não recria a sessão RTD, e o lançador só relança ponte que não responde → ao reabrir o Tryd, o app fica no fim de dia até ser reiniciado. A correção depende de medir se `CoCreateInstance` com o Tryd fechado abre o `tryd.exe` na tela de login (nota da T8): se abrir, relançar a ponte reabriria o Tryd sozinho a cada ciclo; se não abrir, a ponte pode recriar a sessão a cada ~10 s enquanto perdida (reassinando o registro), e o quadro esquece os valores na passagem perdido → conectado.
Task 11: complete (commit b2b9109 + correção do launcher no Windows, re-review clean)
Task 12: start (base: b2b9109 + working tree da retomada)
- Ruling: `CadastroFreshness` muda de `adapters/outbound/b3files/library.py` para `application/ports/outbound.py` (a biblioteca importa de lá e reexporta) — `MarketStatus` é da aplicação e a aplicação não importa adapters (import-linter) — se errado: só o lugar do tipo.
- Ruling: os tipos da tela (`WatchRow`, `SeriesRow`, `ExpiryBlock`, `ChainView`, `MarketStatus`) e `DEFAULT_CHAIN_EXPIRIES` moram em `application/ports/inbound.py`, junto do `MarketViewUseCase` que os devolve (o plano os punha em `market_view.py`; o port não deve importar o use case) — se errado: só imports.
- Ruling: `freshness` devolve `CadastroFreshness | str` e `MarketStatus` ganha `cadastro_reason` — minors da T5 (frescor None igual a "sem cadastro"; data fora do calendário) — a tela distingue "nenhum cadastro", "cadastro sem data no nome" e "data fora do calendário" — se errado: um campo a mais.
- Ruling: `ChainView` ganha `timestamp` (hora da cotação do ativo, que é a data de valoração) — nota da T11 (a tela mostra a data quando não é a de hoje) — se errado: um campo a mais.
- Ruling: `MarketViewService` sem `clock`: a data de valoração vem da cotação do ativo no fuso da B3, como no ranking (preço e tau do mesmo instante) — se errado: no pré-abertura o tau conta do último negócio de ontem, 1 du a mais.
- Ruling: rótulo da cadeia = a saúde MENOS fresca entre antes e depois do `get_chain` — nota da T11 (TOCTOU de `health()`); a cadeia não diz de onde veio — se errado: um dado ao vivo pode sair como "fim de dia" na virada, nunca o contrário.
- Ruling: `build_web_app` mora em `config/web_app.py`, não em `config/composition.py` — o `composition` e o CLI do painel não podem importar o FastAPI (extra `app`); um teste prende isso — se errado: só o nome do módulo.
- Ruling: `ProfileService` ganha `threading.RLock` (minor da T4 → T12) e o desligar do app isola cada passo e solta a trava do perfil mesmo com falha (minor da T3 → T12); a ponte sobe e é conferida numa thread própria, a cada 2 s (nota da T9: chamadas de até 2 s fora do laço de eventos).
Task 12: complete (inline; 24 testes do serviço, 11 do app montado, 1 da trava do serviço de perfis)
Task 13: start
- Ruling: o WebSocket manda `{"tipo": "cadeia", "ativo", "erro", "mensagem"}` quando a cadeia não sai (aguardando dados, desconhecido) e `{"tipo": "erro", "erro": "RequisicaoInvalida", ...}` para mensagem inválida do cliente, sem fechar a conexão; `cotacoes` leva `motivo` (sem perfil aberto: lista vazia e o motivo) — o plano não dizia o formato desses casos — se errado: formato de mensagem.
- Ruling: `GET /api/mercado/status` traz também `cadastro_motivo`, e a cadeia traz `hora` (mesmas razões da T12).
Task 13: complete (inline; 14 testes de REST e WebSocket)
Task 14: start
- Ruling: `launch.py` (adapter) só tem os auxiliares e o `serve`; quem chama `build_web_app` é o `__main__` (adapter não importa o composition root, pelo import-linter) — se errado: nenhum.
- Ruling: no Windows o Edge raramente está no `PATH`; `app_window_command` aceita `windows_paths` (Program Files e LOCALAPPDATA) além do `which` — sem isso a janela de app nunca abriria no Windows — se errado: um parâmetro a mais.
- Ruling: o XDG relativo é ignorado (especificação XDG) e testado como caminho POSIX (o teste também roda no Windows).
Task 14: smoke real no Windows 11 (APPDATA temporário, `--sem-janela`, ponte ligada, sem Tryd): `/api/saude` 200, status `fim_de_dia` com "nenhum Cadastro de Instrumentos importado", SPA servida, cotações sem perfil 404; a ponte tenta subir a cada ~10 s e sai com "pywin32 indisponível" (o `python` do PATH não tem pywin32) — Review Focus 1 confirmado ao vivo no Windows.
Task 14: note (→ semana 4): no Windows `default_bridge_command` usa o `python` do PATH; mais simples para a mãe é a ponte rodar no mesmo Python do app (`sys.executable`) com um extra `ponte = ["pywin32; sys_platform == 'win32'"]` — decidir com o instalador.
Task 14: complete (inline; 9 testes)
Task 14: note: tests/ponte/test_cli.py::test_espiar_assina_os_topicos_do_rtd_e_os_deixa_assinados falhou 1 vez sob carga (gates completos): conferia os tópicos antes do Ping/Pong que sincroniza com a fila da ponte; a ordem foi invertida.
Task 13: fix: `variacao_pct` saía em pontos percentuais; passa a decimal (CONVENTIONS: decimal em tudo; a T17 espera -0.0059 → "-0,59%").
Task 15: start
- Ruling: `@testing-library/dom` ^10.4 nas devDependencies (par obrigatório do `@testing-library/react` 16) e `src/testes/setup.ts` com `cleanup` e `vi.unstubAllGlobals` (sem os globais do Vitest o Testing Library não desmonta entre testes) — se errado: nenhum.
- Ruling: formatação ganha `formatarHora` (fuso da B3, com DD/MM quando não é de hoje — nota da T11), `formatarVol`, `formatarDelta` e `formatarInstante` — o plano só listava preço, percentual, volume, inteiro e data — se errado: funções a mais.
- Note: npm 11 bloqueia scripts de instalação; o `postinstall` do esbuild não rodou e não faz falta (o binário vem do `@esbuild/win32-x64`); build e testes rodam.
Task 15: complete (tsc estrito + Vitest; build gera `web/static/index.html`; job `frontend` no CI com Node 22)
Task 16: start
- Ruling: link do Cadastro de Instrumentos aponta para o Boletim Diário da B3 (página conferida em 2026-10-29; o arquivo fica em "Pesquisa por pregão", num iframe de arquivos.b3.com.br) — o plano não dava o endereço — se errado: um link.
- Ruling: sem perfil aberto, até `/arquivos` redireciona para `/perfis` (o plano diz "qualquer rota").
Task 16: complete (cliente da API com `ErroApi`; Perfis com a confirmação da trava; Arquivos B3 com arrastar, aviso de cadastro velho e motivo do status)
Task 17: start
- Ruling: o `useAoVivo` mora num componente que só existe com perfil aberto (`ComPerfil`); a cadeia é cancelada ao sair da tela de Mercado (`seguirCadeia(null)`), para não deixar tópicos assinados no Tryd — termos do Tryd ("flood") — se errado: nenhum.
- Ruling: hora de cada cotação mostra "(fim de dia)" / "(atrasado)" quando não é ao vivo; a cadeia mostra fonte e hora no cabeçalho — anti-objetivo "dado parado mostrado como ao vivo".
Task 17: complete (30 testes do frontend; build)
Task 17: ponta a ponta no Windows 11 (app real, `--sem-ponte`, APPDATA temporário, fixture sintética importada pela API): status `fim_de_dia` com cadastro de 3 du; cotações formatadas (-1,48%, 30,0 mi, "23/10 18:00:00 (fim de dia)"); cadeia de PETR4 pelo WebSocket com 2 abas, calls e puts espelhadas, IV ~30% (sigma da fixture), "—" nos lados ausentes e 7 rejeitadas. Bug achado e corrigido: "Importado em" mostrava a data UTC (29/10 às 01h UTC = 28/10 22h em São Paulo) → `formatarInstante`.
Task 11: note: test_ponte_de_pe_com_o_tryd_fechado_recua_para_o_fim_de_dia_apos_30_s falhava ~1 em 3 no Windows: a espera aceitava qualquer UnderlyingQuote, e a do fim de dia também é uma — o teste seguia antes de o Status "conectado" chegar. A espera passa a exigir a fonte AO_VIVO (10/10 depois). Defeito do teste, não do produto.

## 2026-10-29 (tarde): preparação da Task 18 e o minor da Task 11

Task 18: os Steps 1–3 dependem do Tryd ao vivo e dos arquivos reais da B3, baixados à mão (termos da B3 e CAPTCHA); o Step 4, documentação, já tinha saído no commit e302731 e na retomada (README).
- Ruling: a conferência do Step 3 vira o comando `python -m options_engine conferir-b3` (`adapters/outbound/b3files/conferencia.py`). Ele lê os arquivos com os MESMOS parsers do app (novos `raw_lines` no parser do COTAHIST e `raw_rows` no cadastro, só para diagnóstico) e dá ok/atenção/FALHA por premissa: TOTREG; domínios de `OptnStyle` e `OptnTp`; formato de `ExrcPric` (separador de milhar = falha, minor da T6) e de `XprtnDt`; `UndrlygTckrSymb1` nas opções; ESPECI (informativo); `PREEXE` × `ExrcPric`; `DATVEN` × `XprtnDt`; cadastro do mesmo pregão; `PEX` do Tryd × strike da B3. Sai com 1 se algo falhar — sem isso, conferir o arquivo real seria trabalho manual e sujeito a erro — se errado: um comando a mais no CLI.
Task 11: minor (deferred) FIXED: série sem ativo-objeto no cadastro passa a ser só do único ativo à vista da raiz nos COTAHIST (`_Row.owner`); VALE5 só no cadastro não recebe mais as séries de VALE3 (test_serie_sem_ativo_objeto_e_so_do_unico_ativo_da_raiz_nos_cotahist, que falhava antes).

## 2026-10-29 (madrugada): Task 18 ao vivo no Windows 11, com o Tryd 8.5.6.12

Pregão fechado (00:17). Ponte no Python 3.14 do `.venv-tryd` (pywin32 312); app com APPDATA e perfil temporários; sem arquivos reais da B3.
- `diagnostico` e `autoteste` da ponte: OK. No Windows nativo o ProgID resolve pelo nome e a type library do Tryd carrega.
- `espiar` e app: ULT, OCP, OVD, NEG, FEC, HOR e EST chegam como `""`; VOL traz o financeiro de ontem; DAT veio `10/28/2026` (formato regional do Windows em inglês).
- Bug: a tradução lia DAT sempre como dia/mês; `11/05/2026` num Windows em inglês viraria 11 de maio em silêncio (data de valoração errada). FIXED: quando dia e mês podem ser trocados, vale a leitura mais perto de hoje.
- Note (decisão do autor): fora do pregão o app mostra "Ao vivo (Tryd)" sem preço, com "Negócios 0", o volume de ontem e a hora de agora (o `fallback_time` da T10). É o anti-objetivo "dado parado como ao vivo". Opções: recuar para o fim de dia quando nenhum ativo tem preço ao vivo; ou tratar o ativo sem `ULT`/`OCP`/`OVD` como "aguardando dados" e não usar a hora de agora.
- Tryd fechado com o app aberto: "Atrasado" em 8 s e "Fim de dia" em 36 s (30 s após o Heartbeat detectar).
- Ponte nova com o Tryd fechado: o COM abriu o `tryd.exe` (já logado) em ~12 s e a sessão entregou dados; esse Tryd fechou quando a ponte encerrou. A ponte antiga seguiu "perdido" e o app no fim de dia: o Important da re-revisão da T11 está confirmado. A correção não pode só relançar a ponte, porque isso reabriria o Tryd que o usuário fechou; ver HANDOFF §6.
- O Tryd aberto pelo usuário sobrevive ao `encerrar` da ponte.
- Não testado: cadeia ao vivo e bid/ask contra a tela (pregão fechado e sem cadastro real); `conferir-b3` (sem arquivos reais).

## 2026-10-29: COTAHIST opcional e importação da pasta Downloads (branch feat/cotahist-opcional-e-downloads)

- Ruling: a cadeia ao vivo não exige mais o COTAHIST. A biblioteca carrega só com o cadastro; sem histórico, a vol do snapshot é a IV da série mais perto do dinheiro (a tela não a usa: IV e delta vêm de cada série). Sem cadastro, nada feito (séries e estilo vêm dele). O fim de dia continua exigindo o COTAHIST ("sem COTAHIST importado"). Sem COTAHIST, a raiz dividida (PETR3/PETR4) é detectada pelos ativos à vista do cadastro.
- Ruling: o app importa sozinho os arquivos da B3 baixados para a pasta Downloads (`DownloadsImporter`, varredura a cada 5 s numa thread do ciclo de vida). Só nomes `COTAHIST*.zip|txt` e `InstrumentsConsolidated*.csv`; importa quando o arquivo para de mudar entre duas passadas; não reimporta o que a biblioteca já tem de depois do download; recusado vira evento com o motivo e não é tentado de novo. A pasta vem do registro no Windows (Downloads movida) e do `user-dirs.dirs` no Linux ("Transferências"). `--sem-downloads` desliga. O download continua manual (termos da B3).
