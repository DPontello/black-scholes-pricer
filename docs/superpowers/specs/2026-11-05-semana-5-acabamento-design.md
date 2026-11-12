# Semana 5: acabamento para o teste com a mãe (desenho)

Data: 2026-11-05. Prazo do app: 2026-11-30 ([desenho geral](2026-10-28-app-opcoes-design.md), §7
e §8). O autor pediu para começar e fechar a semana 5 no mesmo dia ("começe a semana 5 para
finalizarmos hj") e, desde a parte 2 da semana 4, delega as decisões ("pode seguir com o melhor
jeito que vc definiria"). **Tudo o que está aqui como decisão é decisão minha**, para o autor
conferir ao ler.

## 1. Intenção

A semana 5 do desenho geral é "teste com a mãe do autor, acabamento, correções, documentação". O
critério de pronto 9 diz: "a mãe do autor consegue montar e registrar uma operação sozinha, num
teste de usabilidade". O teste quem faz é o autor, com ela. Esta semana prepara o terreno:

- tira do caminho do critério 9 o que trava uma pessoa leiga;
- dá ao app o ícone, que ficou para cá na semana 4 (ledger da semana 4, tasks 1 e 3);
- entrega o roteiro do teste;
- fecha a documentação.

### 1.1 Como os travamentos foram achados

Em 05/11 percorri o app como alguém que o abre pela primeira vez. Usei uma cópia isolada (config
e perfil em pasta temporária) com os arquivos reais da B3 de 30/10, numa tela de 1366 × 768. O
caminho testado foi:

1. criar perfil;
2. Book;
3. "Abrir no montador", ou o Modelo pronto;
4. "Registrar como executada";
5. Carteira.

O caminho funciona do começo ao fim. Os travamentos:

1. **Pasta de dados.** O perfil novo pede o caminho completo da pasta, digitado, e a pasta
   precisa existir. Para quem não sabe o que é um caminho como `C:\Users\...\OneDrive\...`, é
   uma parede logo na primeira tela.
2. **Montador.** O resultado só fica ao lado da cadeia a partir de 1780 px de largura (UX, §4.1).
   Abaixo disso, que é o caso de qualquer notebook, a montagem fica cerca de 1400 px abaixo do
   topo, depois da cadeia inteira. Isso vale para as pernas, o "Registrar como executada", o
   resumo e o gráfico. Escolher um Modelo pronto ou chegar pelo "Abrir no montador" do Book não
   muda nada na parte visível da tela: parece que o clique não fez nada.
3. **Preço com "R$".** Quem digita `R$ 1,30` no preço recebe "Preencha o preço de PETRW536.",
   embora tenha preenchido. `1.000,50` também falha.
4. **Série errada.** "PETRW999: série desconhecida no cadastro" não diz o que fazer.
5. **Book na primeira vez.** Depois de um COTAHIST novo, o Book fica uns 2 minutos em "Varrendo
   o fim de dia…" (histórico de vol sem cache), sem dizer que isso é normal.
6. **Sem ícone.**
   - Windows: o `.exe`, o instalador e o atalho têm o ícone padrão.
   - Linux: o atalho do menu aparece sem ícone.
   - Na janela do app, aparece o ícone genérico de página.

## 2. Objetivos (o que se constrói)

| | Entrega | Trava |
|---|---|---|
| A | Ícone do app em todos os lugares | 6 |
| B | Botão "Escolher pasta…" no perfil novo | 1 |
| C | Montador rola até a montagem quando ela chega de fora da cadeia | 2 |
| D | Campos de preço aceitam o que se digita no Brasil | 3 |
| E | Mensagens: série não encontrada e primeira varredura do Book | 4, 5 |
| F | Roteiro do teste de usabilidade com a ficha de anotação | critério 9 |
| G | Documentação de fechamento: o estado dos 9 critérios e o que falta com o autor | — |

## 3. Não-objetivos

- **Proventos e ajuste de strike.** O autor disse em 03/11: "podemos esquecer". O critério 5 fica
  pela metade (desenho da semana 4, §1).
- **O teste com a mãe em si**: é do autor. O que vier dele vira uma rodada de correções depois.
- **Versão 1.0.0, tag e merge na `master`.** Ficam para depois do teste no PC Windows (HANDOFF
  §8) e do teste com a mãe. O HANDOFF diz os passos.
- **Remover perfil da lista e apagar operação.** O app não tem essas funções. Para o teste, o
  roteiro usa um perfil "Teste" numa pasta separada. Depois, o autor tira a entrada da lista no
  `config.json` (o roteiro mostra como).
- **Seletor de pasta pelo navegador.** O navegador não entrega o caminho completo da pasta. Por
  isso, o seletor sai do servidor local, abaixo.

## 4. Anti-objetivos (fracasso mesmo funcionando)

- Mudar qualquer número: cálculo, preço, IR ou alerta. Esta semana é de caminho e de texto.
- Atrapalhar o fluxo perna a perna do autor. O "+" da cadeia **não** rola a tela.
- Um seletor de pasta que trave o app. Cancelar, fechar a janela ou demorar volta sem pasta, e
  digitar o caminho continua valendo.
- Gravar nos perfis reais durante as conferências: só pastas temporárias.

## 5. Decisões por item

### A. Ícone

- **Desenho:** o gráfico de resultado no vencimento de uma call comprada, num quadrado
  arredondado na cor do painel (`#171a21`, borda `#2f3542`). O trecho abaixo da linha do zero
  (cinza, meio transparente) é vermelho (`--baixa`, `#ef5350`); o de cima é verde (`--alta`,
  `#26a69a`). São as cores do tema e a mesma linguagem do gráfico do Montador. Lê-se em 16 px.
- **Fonte única:** `packaging/icone/painel-opcoes.svg`. Este é o conteúdo exato:

  ```svg
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
    <defs>
      <clipPath id="ganho"><rect x="0" y="0" width="256" height="150"/></clipPath>
      <clipPath id="perda"><rect x="0" y="150" width="256" height="106"/></clipPath>
    </defs>
    <rect x="8" y="8" width="240" height="240" rx="56" fill="#171a21" stroke="#2f3542" stroke-width="8"/>
    <line x1="40" y1="150" x2="216" y2="150" stroke="#9aa3b2" stroke-width="10" stroke-linecap="round" opacity="0.5"/>
    <polyline points="48,186 118,186 206,62" fill="none" stroke="#ef5350" stroke-width="26" stroke-linecap="round" stroke-linejoin="round" clip-path="url(#perda)"/>
    <polyline points="48,186 118,186 206,62" fill="none" stroke="#26a69a" stroke-width="26" stroke-linecap="round" stroke-linejoin="round" clip-path="url(#ganho)"/>
  </svg>
  ```

- **Gerados, no repositório** (o CI do Windows não tem ImageMagick):
  - `packaging/icone/painel-opcoes.ico`, com 16, 24, 32, 48, 64, 128 e 256 px;
  - `packaging/icone/painel-opcoes-256.png`;
  - `frontend/public/favicon.svg`, cópia byte a byte do SVG;
  - `frontend/public/icone-192.png`.
- **`scripts/gerar_icone.sh`** gera tudo a partir do SVG. É ferramenta de quem mexe no ícone:
  precisa do ImageMagick 7 com librsvg, e o CI não roda.
- **Um teste segura a coerência** entre os arquivos:
  - o `favicon.svg` é igual ao SVG de origem;
  - o `.ico` tem os sete tamanhos (lidos do cabeçalho ICO com `struct`);
  - os PNGs têm o tamanho do nome.
- **Onde entra:**
  - na tela: o `index.html` liga `favicon.svg` e `icone-192.png`. O Vite copia o `public/` para
    a raiz da tela, e a SPA já serve arquivos da raiz;
  - no Windows: o `icon=` do `painel.spec` e do `ponte.spec`; o `SetupIconFile` no
    `PainelOpcoes.iss`. Os atalhos e o "desinstalar" usam o ícone do `.exe`;
  - no Linux: o `instalar.sh` copia o SVG para
    `~/.local/share/icons/hicolor/scalable/apps/painel-opcoes.svg` e o PNG de 256 px para
    `.../256x256/apps/painel-opcoes.png`. O `.desktop` ganha `Icon=painel-opcoes`, e o
    `--simular` mostra as cópias. A pasta de ícones segue o padrão de `DIR_MENU`: uma variável
    `DIR_ICONES`, com padrão `$HOME/.local/share/icons`.
- **Fica de fora:** agrupar a janela com o atalho na doca do Linux (`StartupWMClass`). A janela é
  do navegador em modo `--app`, e a classe muda com o navegador e com a porta. No Windows, o
  Edge em `--app` usa o favicon na barra de tarefas. Isso entra na conferência do §8 do HANDOFF.

### B. Escolher pasta

- No formulário do perfil novo, ao lado do campo "Pasta de dados", entra o botão **"Escolher
  pasta…"**. Ele chama `POST /api/perfis/escolher-pasta`, que responde `{"pasta": "<caminho>"}`
  ou `{"pasta": null}` quando a pessoa cancela. O caminho escolhido vai para o campo, e ela ainda
  clica em "Criar perfil". O campo continua editável.
- **O servidor é local**, então quem abre a janela de escolha é ele, no sistema em que roda:
  - **Windows:** PowerShell (`powershell.exe -NoProfile -NonInteractive -STA -Command …`) com o
    `System.Windows.Forms.FolderBrowserDialog`:
    - um `Form` dono com `TopMost`, para a janela não abrir atrás do Edge;
    - `ShowNewFolderButton`;
    - a descrição "Escolha a pasta do perfil (pode ser uma pasta da nuvem ou de um pendrive)";
    - a saída em UTF-8, por causa de acentos como em "Mãe";
    - sem janela de console (`CREATE_NO_WINDOW`).
  - **Linux:** `kdialog --getexistingdirectory <home> --title …` ou `zenity --file-selection
    --directory --title=…`. Vale o primeiro que existir no PATH, nessa ordem.
  - **Sem nenhum dos dois:** HTTP 501 no formato de erro do app, com `erro` =
    `"SemSeletorDePasta"` e `mensagem` = "Este PC não tem como abrir a escolha de pasta. Digite o
    caminho completo da pasta." A tela mostra a mensagem.
  - **Volta sem pasta** (`null`) quando:
    - a saída vem vazia;
    - o código de saída não é 0 (cancelar);
    - passam 10 minutos sem resposta;
    - o processo falha (`OSError`).

    Uma única exceção: se o programa não existir, a resposta é o 501 acima.
- **Onde fica:** `adapters/inbound/web/folder_picker.py`, ao lado do `launch.py`. É coisa da
  área de trabalho local, como a janela do app, não do domínio. O padrão é o do
  `app_window_command`:
  - uma função pura monta o comando a partir do sistema e de um `which`, e os testes cobrem os
    três casos;
  - outra roda o comando com um `run` injetável.

  A rota fica no router de perfis, que recebe o seletor pronto da montagem do app. Nos testes,
  a montagem injeta um seletor falso.
- **Textos:** o passo 1 do "Comece aqui" (Aprender) e a frase de ajuda do perfil novo citam o
  botão.
- **Fica para o autor conferir no Windows** (HANDOFF §8): a janela abre na frente, e o caminho
  com acento volta inteiro. No Linux (KDE, com `kdialog`), também é ele quem confere, porque a
  janela abriria na tela dele no meio da sessão.

### C. Montador rola até a montagem

- **Quando rola:** quando a montagem recebe pernas vindas de fora da cadeia:
  - o Modelo pronto;
  - o `?modelo=` do Aprender;
  - o estado da rota ("Abrir no montador" do Book e "Rolar" dos Alertas);
  - abrir uma simulação salva.

  Nesses casos, se o topo da coluna do resultado estiver na metade de baixo da tela ou abaixo
  dela, a tela rola suave até ela (`block: "start"`).
- **Quando não rola:**
  - no "+" da cadeia;
  - ao editar a tabela de pernas;
  - quando o resultado já está à vista, como no lado a lado em tela larga.
- **Implementação sugerida:** uma `ref` na `.montador-resultado` e um contador de "chegou de
  fora", que cresce nos caminhos acima. Um efeito no contador mede e rola. O jsdom não tem
  `scrollIntoView`: os testes o substituem.

### D. Campos de preço

Todos os campos de preço, custo, stop e alvo passam por `numero()`, em
`componentes/CampoPreco.tsx`. A função passa a aceitar:

| Digitado | Lido |
|---|---|
| `1,30` · `1.30` · ` 1,30 ` | 1,30 |
| `R$ 1,30` · `R$1,30` · `r$ 1,30` · `1,30` com espaço que não quebra | 1,30 |
| `1.000,50` · `R$ 1.000,50` | 1000,50 |
| `1.000` · `12.500` | 1000 · 12500 (ponto com grupos de 3 dígitos é milhar) |
| `-1,30` | −1,30 |
| `0,5` · `,5` | 0,5 |
| vazio, `abc`, `1,3x`, `1,2,3`, `1.2.3` | não é número (`null`) |

- `1.000` hoje vira 1; passa a ser 1000. É a leitura de quem digita stop e alvo em reais.
- Ninguém digita preço de opção com ponto e três casas.
- O resto do `CampoPreco` não muda: ele guarda o texto digitado e devolve o número.

### E. Mensagens

- **Série não encontrada** (`adapters/outbound/b3files/loaded.py`, `option_terms`). A mensagem
  aparece no registro de operação:

  > "PETRW999: série não encontrada no Cadastro da B3. Confira o código na nota da corretora;
  > se a série for nova, importe o Cadastro mais recente em Arquivos B3."

  As outras "série desconhecida no cadastro" (diagnóstico de cotação do Tryd e do fim de dia)
  não mudam: não são para a pessoa digitar nada.
- **Book enquanto varre:**

  > "Varrendo o fim de dia… Na primeira vez depois de um arquivo novo da B3, pode levar alguns
  > minutos."

### F. Roteiro do teste com a mãe

O roteiro fica em `docs/teste-usabilidade.md`, em português e para o autor. Ele cobre:

- **Preparação** (pelo autor, antes):
  1. app instalado no PC dela;
  2. arquivos da semana importados;
  3. perfil **"Teste"** numa pasta separada, para não misturar com a carteira dela.

  O Tryd aberto ajuda, mas não é preciso: a tarefa é montar e registrar, não executar ordem. A
  "nota fictícia" fica preenchida e impressa (modelo no roteiro).
- **Regras do observador:**
  - não ajudar e não apontar;
  - se ela pedir ajuda, devolver "o que você tentaria?";
  - só ajudar depois de 3 minutos parada, e anotar que ajudou;
  - pedir que ela pense em voz alta;
  - anotar o tempo de cada tarefa.
- **Tarefas, ela sozinha:**
  1. abrir o app pelo atalho e entrar no perfil Teste;
  2. montar uma put coberta de PETR4 no vencimento mensal (pelo Book ou pelo Modelo pronto) e
     dizer quanto recebe agora e quanto pode perder no pior caso;
  3. registrar a operação como executada com os dados da nota fictícia;
  4. achar a operação na Carteira e dizer se está ganhando ou perdendo agora;
  5. (opcional) achar no Aprender o que é uma put coberta.
- **Critério 9:** as tarefas 2 e 3 sem ajuda.
- **Ficha de anotação:** uma tabela por tarefa, com:
  - conseguiu sozinha, com ajuda ou não conseguiu;
  - tempo;
  - onde hesitou;
  - o que ela disse.
- **Depois do teste:**
  - tirar o perfil Teste da lista (o caminho do `config.json` em cada sistema e o trecho a
    apagar);
  - trazer a ficha para uma rodada de correções (o que colar no Claude Code).

### G. Documentação de fechamento

- **README:**
  - a linha de estado;
  - uma linha sobre o ícone e o "Escolher pasta".
- **ROADMAP:** a linha da semana 5.
- **HANDOFF:**
  - §1: a linha da semana 5;
  - §8: ganha as conferências do ícone (atalho, barra de tarefas, instalador) e do "Escolher
    pasta" no Windows;
  - §11, nova: o que a semana 5 fez, a tabela dos **9 critérios de pronto** com o estado de cada
    um (feito e conferido, feito e falta o autor, ou fora por decisão) e os passos de fechamento
    depois dos testes do autor. Os passos de fechamento são:
    1. versão 1.0.0 no `pyproject.toml`;
    2. merge da `development` na `master`;
    3. tag `v1.0.0`, que gera o instalador.
- **`docs/superpowers/ledger-semana-5.md`:** as decisões deste desenho e as que aparecerem na
  construção, como `Ruling:`.

## 6. Restrições

- **Commit:** quem constrói não commita nem dá push; o autor commita. O plano não tem passos de
  commit.
- **Arquitetura:** domínio e aplicação continuam só com a stdlib, e o import-linter segura isso.
  O seletor de pasta é adaptador de entrada.
- **Gates:**
  - pytest com cobertura ≥ 95%;
  - mypy strict;
  - ruff (lint e formato);
  - import-linter;
  - `npm run verificar` e o `build`.
- **Estilo:** textos da tela em português do Brasil, no tom dos que já existem. Comentário só
  para um porquê não óbvio. Seguir o estilo do código em volta.
- **Arquivos da B3:** nada de download automático; as conferências usam os arquivos que já estão
  no disco, copiados para a pasta temporária.

## 7. Fica com o construtor

- Os nomes internos e a divisão em componentes.
- Como o router de perfis recebe o seletor de pasta.
- O formato exato dos testes.
- A ordem das tarefas, desde que o ícone e as correções C, D e E venham antes do seletor de
  pasta (B), o item com mais incerteza fora deste PC.

## 8. Conferência no fim

- Os gates da seção 6.
- O caminho do §1.1 de novo, no app isolado com os arquivos de 30/10:
  - o favicon é servido;
  - o Modelo pronto e o "Abrir no montador" levam a tela até a montagem;
  - `R$ 1,30` é aceito no registro;
  - a série errada mostra a mensagem nova;
  - o Book mostra o aviso da primeira varredura.
- O `instalar.sh` contra pastas temporárias (`DIR_APP`, `DIR_MENU` e `DIR_ICONES`): o ícone
  copiado e o `Icon=` no atalho.
- O `.ico` aberto pelo ImageMagick com os sete tamanhos.
