# Ledger — semana 5 (acabamento para o teste com a mãe)

Desenho: [`specs/2026-11-05-semana-5-acabamento-design.md`](specs/2026-11-05-semana-5-acabamento-design.md).
Plano: [`plans/2026-11-05-semana-5-acabamento.md`](plans/2026-11-05-semana-5-acabamento.md).
Branch `feat/semana-5-acabamento`, a partir da `development` (`aea061b`). O autor delegou as
decisões ("pode seguir com o melhor jeito que vc definiria") e pediu para fechar a semana em
05/11: todas as linhas `Ruling:` abaixo são decisões minhas, para o autor conferir.

## 2026-11-05: o caminho de quem abre o app pela primeira vez

- Percorri o app numa cópia isolada (HOME temporário, perfil "Mãe" numa pasta temporária, os
  arquivos reais da B3 de 30/10 copiados para a pasta Downloads de mentira), numa tela de
  1366 × 768, pelo Chrome headless. O caminho do critério 9 funciona do começo ao fim:
  1. perfil novo;
  2. Book;
  3. "Abrir no montador" ou o Modelo pronto "put coberta";
  4. "Registrar como executada";
  5. Carteira.
- Os seis travamentos achados são o §1.1 do desenho:
  - a pasta digitada;
  - a montagem fora da tela;
  - o preço com "R$";
  - a série errada;
  - a primeira varredura do Book;
  - a falta de ícone.
- Ruling: o teste com a mãe usa um perfil "Teste" numa pasta separada. O app não tem "remover
  perfil" nem "apagar operação", e a operação de mentira não pode entrar na carteira nem no IR
  mensal dela. Se errado: um perfil a mais na lista, que o roteiro ensina a tirar pelo
  `config.json`.
- Ruling: proventos e ajuste de strike seguem fora ("podemos esquecer", autor, 03/11). O critério 5
  fica pela metade.

## Task 1 — ícone do app

- O desenho é o gráfico de resultado de uma call comprada, num quadrado arredondado da cor do
  painel. O trecho abaixo da linha do zero é vermelho (`#ef5350`) e o de cima é verde
  (`#26a69a`). A fonte única é `packaging/icone/painel-opcoes.svg`.
- `scripts/gerar_icone.sh` (ImageMagick 7 com librsvg) gera os derivados, que ficam no
  repositório:
  - `packaging/icone/painel-opcoes.ico`, com os tamanhos 16, 24, 32, 48, 64, 128 e 256;
  - `packaging/icone/painel-opcoes-256.png`;
  - `frontend/public/favicon.svg`;
  - `frontend/public/icone-192.png`.
- Onde o ícone entra:
  - na tela: as duas `<link rel="icon">` no `index.html`;
  - no Windows: o `icon=` do `painel.spec` e do `ponte.spec`, e o `SetupIconFile` do `.iss`;
  - no Linux: o `instalar.sh` copia o SVG e o PNG para `~/.local/share/icons/hicolor/...`
    (`DIR_ICONES`), e o `.desktop` ganha `Icon=painel-opcoes`.
- `tests/packaging/test_icone.py` confere:
  - o `favicon.svg` é igual ao SVG de origem;
  - os sete tamanhos do `.ico`, lidos do cabeçalho com `struct`;
  - o tamanho dos PNGs;
  - as `<link>`;
  - o `icon=` dos dois `.spec`.

  Os testes do `instalar.sh` conferem o `--simular`, as cópias de verdade num HOME temporário e
  o `Icon=` no atalho.
- Ruling: os PNGs saem em 8 bits e sem os chunks de data (`-depth 8 -define
  png:exclude-chunks=date,time`). Assim duas rodadas do script dão arquivos byte a byte iguais,
  e os PNGs ficaram três vezes menores. Se errado: nenhum, o desenho é o mesmo.
- Ruling: o `.ico` fica com ~353 KB, porque o ImageMagick grava as entradas em BMP. Aceito: o
  instalador tem 22 MB.
- Ruling: sem `StartupWMClass` no `.desktop`. A janela é do navegador em `--app`, e a classe muda
  com o navegador e com a porta. Se errado: no Linux a janela aberta pode aparecer na doca com o
  ícone do navegador.

## Task 2 — campos de preço e mensagens

- `numero()` (`componentes/CampoPreco.tsx`) passou a ler o que se digita no Brasil. Ele lê `R$` no
  começo, espaços (inclusive o que não quebra), vírgula decimal e ponto de milhar. Também lê
  ponto decimal quando não há grupos de três dígitos, e o sinal de menos. Exemplos:
  - `R$ 1,30` é 1,30;
  - `1.000,50` é 1000,50;
  - `1.000` é 1000;
  - `1.30` é 1,30.

  Todos os campos de preço, custo, stop e alvo passam por ele.
- Ruling: o ponto de milhar exige o primeiro grupo sem zero à esquerda. `0.500` é 0,5 (ninguém
  escreve quinhentos como 0.500), e `0.500,50` não é número. Se errado: `0.500` digitado como
  quinhentos vira 0,5.
- O registro com a série errada agora diz: "PETRW999: série não encontrada no Cadastro da B3.
  Confira o código na nota da corretora; se a série for nova, importe o Cadastro mais recente em
  Arquivos B3." As outras "série desconhecida no cadastro" (diagnóstico de cotação do Tryd e do
  fim de dia) ficaram como estavam.
- O Book, enquanto varre, diz: "Varrendo o fim de dia… Na primeira vez depois de um arquivo novo
  da B3, pode levar alguns minutos."

## Task 3 — Montador rola até a montagem

- A tela rola suave até a coluna do resultado (`block: "start"`) quando a montagem recebe pernas
  de fora da cadeia e o topo do resultado está na metade de baixo da tela ou abaixo dela. Isso
  vale para:
  - o Modelo pronto e o `?modelo=`;
  - o "Abrir no montador" do Book e o "Rolar" dos Alertas;
  - abrir uma simulação salva.

  O "+" da cadeia e a tabela de pernas não rolam.
- Ruling: o contador de chegadas começa em 0, não em 1 com o pedido do Book, como o plano dizia. O
  efeito da troca de ativo já conta o pedido pendente do Book, e começar em 1 rolava duas vezes.
  O teste do Book cobre.
- Ruling: a rolagem espera a resposta da análise (ou o erro) daquele pedido, em vez de rolar
  quando as pernas chegam. Isso não estava no plano. A conferência no app real (1366 × 768)
  mostrou que, antes da análise, a página ainda era baixa e o navegador parava a rolagem no fim
  dela (scrollY 781): o resumo "Você recebe R$ … agora" ficava abaixo da dobra.
  - Agora o Modelo pronto leva o resultado ao topo (scrollY 1402), com o resumo à vista. O
    "Abrir no montador" do Book faz o mesmo (scrollY 1116).
  - A marca guarda o pedido que chegou: um "+" ou uma edição antes da resposta cancela a
    rolagem.
  - Se errado: nenhum.
- Fica para depois (só no `npm run dev`, anterior a esta semana): no StrictMode, o efeito da troca
  de ativo roda duas vezes na montagem. A segunda vez apaga o pedido vindo do Book ou dos Alertas.
  O app compilado não tem o problema.

## Task 4 — "Escolher pasta…" no perfil novo

- No formulário do perfil novo, ao lado do campo "Pasta de dados", entrou o botão "Escolher
  pasta…". Ele chama `POST /api/perfis/escolher-pasta`, que responde `{"pasta": <caminho>}` ou
  `{"pasta": null}` (cancelou). Sem seletor no PC, a resposta é 501 com a mensagem "Este PC não
  tem como abrir a escolha de pasta. Digite o caminho completo da pasta.".
- Quem abre a janela é o servidor, que é local (`adapters/inbound/web/folder_picker.py`):
  - no Windows, o PowerShell com o `FolderBrowserDialog`, dono `TopMost` e sem console;
  - no Linux, o `kdialog` ou o `zenity`.

  Cancelar, dar erro ou passar 10 minutos dá `null`, e o campo continua editável.
- Ruling: a saída do PowerShell vai em UTF-8 sem BOM (`New-Object System.Text.UTF8Encoding
  $false`), e um BOM no começo é descartado por segurança. Se errado: nenhum; sem isso, o caminho
  chegaria com um caractere invisível na frente e o perfil não acharia a pasta.
- O passo 1 do "Comece aqui" e a frase de ajuda dos perfis citam o botão.
- Falta: o autor conferir no Windows (a janela abre na frente e o caminho com acento volta inteiro)
  e no KDE deste PC.

## Task 5 — roteiro do teste

- [`docs/teste-usabilidade.md`](../teste-usabilidade.md) traz:
  - a preparação;
  - as regras de quem observa;
  - as cinco tarefas com o "pronto quando";
  - o critério 9, que são as tarefas 2 e 3 sem ajuda;
  - a ficha de anotação;
  - a nota fictícia;
  - como tirar o perfil Teste da lista e o texto da rodada de correções.

## Revisão final da branch e a rodada de correções

A revisão final da branch inteira saiu "pronta com correções": nenhum achado crítico e dois
importantes. A rodada única de correções fez:

- **seletor de pasta:** uma saída que não seja UTF-8 válido volta sem pasta (`{"pasta": null}`),
  sem derrubar o app com erro 500. Isso importa no Windows, com caminho acentuado;
- **teste da montagem do app:** `build_web_app` liga o seletor na rota, e sem seletor a rota
  responde 501;
- **uma janela de escolha por vez:** enquanto uma está aberta, um segundo pedido (outra aba, por
  exemplo) volta na hora sem pasta;
- **simulação reaberta:** abrir de novo a mesma simulação salva rola uma vez, na hora certa;
- **ícone em tamanhos pequenos:** as entradas de 16 a 64 px do `.ico` passaram a 32 bits com
  transparência suave, e os cantos não serrilham mais na barra de tarefas. O `.ico` tem 372 KB;
- **este ledger:** ganhou a decisão da rolagem depois da análise e a seção de gates.

## Gates (05/11, árvore final)

- pytest com 5430 testes e cobertura de 98,49%;
- mypy strict (327 arquivos), ruff check e ruff format sem achados;
- import-linter com 3 contratos mantidos;
- frontend (`verificar`) com 273 testes;
- build da tela ok, com `favicon.svg` e `icone-192.png` na raiz.

## Fica para depois (anotado nas revisões, sem bloquear)

- `5,` e `1.` (separador no fim) deixaram de ser lidos como 5 e 1, e o registro diz "Preencha o
  preço". Se a mãe tropeçar nisso no teste, aceitar o separador no fim.
- O seletor de pasta que falha (código de saída diferente de 0) parece igual a cancelar, sem
  mensagem. O roteiro pede para o autor conferir a janela antes do teste.
- Se no Windows o acento vier estragado mesmo com UTF-8, a saída é o PowerShell devolver o
  caminho em Base64.
