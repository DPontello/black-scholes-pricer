# App de opções — semana 4: instalador, IR mensal e alertas — desenho (2026-11-03)

> Semana 4 do [desenho geral](2026-10-28-app-opcoes-design.md) (§7 e §8). As decisões marcadas
> **(autor, 03/11)** vieram das enquetes de 03/11; o resto é decisão de quem escreveu, revisável.
> Público: o autor e a mãe dele, pouco técnica.

## 1. Escopo e ordem

Três partes, cada uma numa branch a partir da `development`, entregue sozinha para o autor testar
logo o que fica pronto, nesta ordem **(autor, 03/11: instalador primeiro)**:

1. **Instalador** do Windows (`.exe`) e script de instalação do Linux (§2).
2. **IR mensal estimado** das opções (§3).
3. **Alertas**: vencimento próximo, risco de exercício, stop e alvo, sugestão de rolagem (§4).

**Fora da semana 4:**

- **Proventos, calendário de proventos e ajuste de strike** **(autor, 03/11: "podemos esquecer o
  calendário por enquanto")**. Com eles sai o alerta de exercício antecipado perto da data-com.
  O critério de pronto 5 do desenho geral fica pela metade (alertas e vencimentos sim; proventos e
  ajuste não) até o autor decidir a fonte dos proventos.
- IR de ações, isenção de R$ 20 mil, IR retido na fonte e prejuízo anterior ao app (§3).
- Notificação fora do app (e-mail, celular, som com o app fechado).
- Assinatura de código do instalador.

## 2. Parte 1 — instalador

### 2.1 O que o usuário vê

- **Windows:** baixa `PainelOpcoes-<versão>-setup.exe`, dá dois cliques, passa pelo aviso do
  SmartScreen ("Mais informações" → "Executar assim mesmo", explicado no README) e ganha o atalho
  **Painel de Opções** na área de trabalho e no menu Iniciar. O atalho abre a janela do app (Edge
  `--app`, como hoje). Não pede senha de administrador.
- **Atualizar:** instalar a versão nova por cima. Perfis, carteiras, simulações e arquivos da B3
  ficam onde estão (`%APPDATA%\PainelOpcoes` e a pasta de cada perfil), fora da pasta do programa.
- **Desinstalar:** pelo "Adicionar ou remover programas". Os dados não são apagados.
- **Abrir duas vezes:** o segundo clique no atalho não sobe outro servidor: só abre a janela do que
  já está rodando (decisão de quem escreveu: a mãe do autor vai clicar duas vezes).
- **Linux (este PC):** `scripts/linux/instalar.sh` cria o ambiente, compila a tela e põe o atalho
  no menu de aplicativos. A ponte continua no distrobox `tryd` montado por
  `preparar_ponte_wine.sh`.

### 2.2 Como (decisões de quem escreveu)

- **Dois executáveis, os dois com PyInstaller em modo pasta (`onedir`):**
  - `PainelOpcoes.exe`: o app (FastAPI, uvicorn, `options_engine`) com a tela compilada dentro,
    Python 3.12 de **64 bits**, sem janela de console;
  - `ponte\PonteTryd.exe`: a ponte (`options_ponte` com pywin32), Python 3.12 de **32 bits**.
    Motivo: a type library do Tryd só está registrada para 32 bits; num Python de 64 bits a ponte
    cai para a type library do Excel, que o PC da mãe pode não ter (README da ponte). Com 32 bits
    ela usa a do próprio Tryd. Premissa a confirmar no teste no Windows (§2.4): o roteiro nativo
    do Windows nunca foi medido, só o Wine.
- **No código:**
  - `default_bridge_command` ganha o caso do executável: com `sys.frozen`, o comando é
    `<pasta do app>\ponte\PonteTryd.exe servir --porta N`, sem `python` no PATH;
  - `default_static_dir` acha a tela dentro do executável (`sys._MEIPASS`);
  - sem console, o log vai para `%APPDATA%\PainelOpcoes\logs\app.log` (rotativo, uns 5 MB);
  - "já está aberto": se a porta do app responde ao `GET /api/saude` com a assinatura do app, o
    segundo processo só abre a janela nessa porta e sai;
  - os dois pontos de entrada do PyInstaller ficam em `packaging/windows/`; as dependências de
    build (PyInstaller, pywin32) ficam num `requirements-build.txt` lá, fora do `pyproject`: o
    núcleo segue sem dependências.
- **Inno Setup** (`packaging/windows/PainelOpcoes.iss`): instalação por usuário
  (`PrivilegesRequired=lowest`, em `%LOCALAPPDATA%\Programs\PainelOpcoes`), `AppId` fixo para a
  versão nova instalar por cima, atalhos, desinstalador e a versão lida do `pyproject.toml`.
- **GitHub Actions** (`.github/workflows/instalador.yml`, `windows-latest`): roda à mão
  (`workflow_dispatch`) e em tag `v*`. Compila a tela, gera os dois executáveis, roda os testes de
  fumaça e o Inno Setup, e publica o instalador como artefato. O CI de hoje (`ci.yml`) não muda.
- **Testes de fumaça no CI:** `PainelOpcoes.exe app --sem-janela --sem-ponte --porta N` responde ao
  `GET /api/saude` e serve a tela; `PonteTryd.exe autoteste` termina com `AUTOTESTE OK` (o servidor
  RTD falso, sem Tryd). Se o autoteste não rodar no runner (registro COM), ele vira passo manual
  do §2.4, anotado no ledger.

### 2.3 Riscos

- **Ponte de 32 bits não acha o Tryd** no Windows nativo: o `PonteTryd.exe diagnostico` diz qual
  type library e qual classe foram usadas; se falhar, a alternativa é registrar o
  `rtd_shim.idl` compilado, como no Wine.
- **Antivírus** marca executável do PyInstaller sem assinatura: o README explica; assinar fica
  fora.
- **Tamanho:** uns 60 a 90 MB instalado. Aceitável para um app de desktop.

### 2.4 Critérios de pronto da parte 1

1. O CI gera `PainelOpcoes-<versão>-setup.exe` num `workflow_dispatch`, com os testes de fumaça
   verdes.
2. Num PC Windows do autor: instalar sem administrador; o atalho abre a janela; escolher perfil;
   cotações ao vivo com o Tryd aberto; fim de dia rotulado com o Tryd fechado; segundo clique no
   atalho só abre a janela; instalar a mesma versão por cima mantém perfis e carteira;
   desinstalar mantém os dados.
3. No Linux deste PC: `instalar.sh` do zero; o atalho do menu abre o app com a ponte do distrobox.
4. README com instalação, SmartScreen e atualização.
5. Gates de sempre verdes.

## 3. Parte 2 — IR mensal estimado das opções

### 3.1 Regras (decisões do autor)

- **Só opções**, **sem isenção** **(autor, 03/11)**. A perna de ação fica fora da apuração.
- **Sem prejuízo anterior ao app**: a compensação começa do zero, com as operações registradas
  **(autor, 03/11)**.
- **Sem IR retido na fonte** (o "dedo-duro") **(autor, 03/11)**.
- Do desenho geral: operação comum a **15%** e day trade a **20%**, com o prejuízo compensado
  **dentro de cada categoria**, de um mês para os seguintes; day trade é compra e venda da mesma
  série no mesmo dia, pela data registrada nas execuções. Sempre rotulado **estimativa**, nunca
  cálculo fiscal.

### 3.2 O que entra no mês

- O resultado de uma perna de opção entra no mês do evento que o **realiza**: o encerramento
  (`Close`) e o pó (`Expired`), com os custos reais digitados ou os da tabela, como no resultado
  realizado da Carteira.
- **Exercício e atribuição não geram resultado de opção**: pela regra que a Carteira já segue
  (IN RFB 1.585/2015, art. 60), o prêmio vai para o preço da ação. Como a ação está fora da
  apuração, esse prêmio só aparece quando a ação for vendida, e o app não o tributa. A tela diz
  isso ao lado do mês em que houve exercício ou atribuição.

### 3.3 A confirmar com o autor no início da parte 2

Regras que o código vai obrigar a escolher e que mudam o número; vão em enquete antes de codar:

1. **Day trade parcial:** comprou 200 e vendeu 100 da mesma série no mesmo dia. Proposta: 100 são
   day trade, ao preço daquele dia; o resto segue em operação comum, pelo preço médio.
2. **DARF mínimo de R$ 10:** IR do mês abaixo de R$ 10 passa para o mês seguinte, como a Receita
   faz. Proposta: sim.
3. **Vencimento do DARF:** mostrar "pagar até o último dia útil do mês seguinte". Proposta: sim.

### 3.4 Tela

Na Carteira, aba **IR mensal**: uma linha por mês com resultado comum, resultado day trade,
prejuízo a compensar de cada categoria, base, IR estimado e "pagar até"; ao abrir o mês, as pernas
que o compõem. Rótulo fixo: "estimativa, só opções, sem IR retido na fonte e sem prejuízo de antes
do app". O glossário ganha o termo `ir-mensal`.

## 4. Parte 3 — alertas

### 4.1 Os quatro alertas **(autor, 03/11: todos)**

| Alerta | Quando dispara | Ação no alerta |
|---|---|---|
| Vencimento próximo | perna de opção aberta a **5 dias úteis** ou menos do vencimento | abrir a operação na Carteira |
| Risco de exercício | opção **vendida** dentro do dinheiro, ou a menos de **2%** do strike, a 5 du ou menos do vencimento | abrir na Carteira; rolar (abaixo) |
| Stop e alvo | resultado da operação pelo **preço de zerar** chega ao stop (perda em R$) ou ao alvo (ganho em R$) **(autor, 03/11: em R$)** | abrir na Carteira; encerrar |
| Sugestão de rolagem | operação com perna vendida em risco de exercício, ou a 5 du ou menos do vencimento | abrir no Montador o encerramento das pernas atuais e a **mesma estrutura no vencimento seguinte**, com os strikes do modelo pronto e os preços do momento **(autor, 03/11)** |

- Os limites (5 du, 2%) são os padrões e ficam editáveis no perfil (decisão de quem escreveu, como
  manda o §9 do desenho geral). O stop e o alvo são opcionais, por operação, no registro e na
  própria operação.
- O alerta de exercício perto da data-com fica fora, com os proventos (§1).

### 4.2 Como (decisões de quem escreveu)

- **Regras puras no domínio** (`domain/alerts/`): recebem a carteira, as marcas e o calendário e
  devolvem os alertas, sem I/O. A Carteira já tem os avisos de depois do vencimento ("registre o
  exercício", "aguardando o fechamento"); eles passam a aparecer também na aba Alertas.
- **Avaliação:** ao abrir a aba e a cada atualização da carteira ao vivo (o mesmo WebSocket da
  Carteira). Com o Tryd fechado, pelo fim de dia, rotulado.
- **Tela:** a aba Alertas (hoje "em breve") lista os alertas por gravidade, com a ação de cada um;
  o menu mostra a contagem. Um alerta pode ser **dispensado** até mudar de estado (por exemplo,
  stop dispensado volta se o resultado piorar outra vez depois de melhorar).
- **Rolagem:** usa o catálogo de modelos do Montador; operação que não veio de um modelo recebe
  "abrir no Montador o vencimento seguinte" sem strikes sugeridos.
- O glossário ganha `rolagem`, `stop-e-alvo` e `risco-de-exercicio`.

### 4.3 A confirmar com o autor no início da parte 3

1. Os padrões de 5 dias úteis e 2% do strike.
2. Se o stop e o alvo valem também para a operação só de ações.

## 5. Riscos (anti-objetivos)

- **Instalador que não abre no PC da mãe** e ninguém percebe: o critério 2 do §2.4 é no PC
  Windows real, não só no CI.
- **IR que parece cálculo fiscal:** o rótulo de estimativa e o que fica de fora estão sempre na
  tela (§3.4).
- **Alerta demais:** limites editáveis e dispensar até mudar de estado (§4.2).
- **Rolagem que parece ordem:** o app só abre no Montador; nada é enviado.

## 6. Critérios de pronto da semana

1. Os do §2.4.
2. IR mensal das opções com as regras do §3, conferido à mão em dois meses de exemplo (um com day
   trade e um com prejuízo compensado).
3. Os quatro alertas do §4, cada um com teste das regras e da tela.
4. Gates: pytest com cobertura, mypy, ruff, ruff format, import-linter; frontend `verificar` e
   `build`.
