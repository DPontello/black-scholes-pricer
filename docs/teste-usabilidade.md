# Teste de usabilidade com a mãe do autor

Roteiro para o critério de pronto 9 do [desenho do app](superpowers/specs/2026-10-28-app-opcoes-design.md):
"a mãe do autor consegue montar e registrar uma operação sozinha, num teste de usabilidade". Quem
conduz é o autor; leva uns 40 minutos. O que importa não é ela acertar: é ver **onde ela trava**,
para corrigir o app depois.

## 1. Preparação (o autor, antes de chamá-la)

1. **App instalado no PC dela**, pelo instalador do Windows (HANDOFF §8) ou pelo
   `scripts/linux/instalar.sh`. Abra uma vez pelo atalho e confira que a janela aparece. Em
   "Novo perfil", clique em "Escolher pasta…" e confira que a janela de escolha abre **na
   frente** do app; depois cancele. Se ela abrir atrás ou não abrir, anote: é um defeito a
   corrigir, e no teste ela vai precisar digitar o caminho.
2. **Arquivos da semana importados**: o `pesquisa-pregao.zip` e o COTAHIST anual na pasta
   Downloads; em Arquivos B3, os dois aparecem como importados. Abra o Book uma vez antes do
   teste: a primeira varredura depois de um arquivo novo leva alguns minutos e não deve contar
   no tempo dela.
3. **Perfil "Teste" numa pasta separada**, para a operação de mentira não entrar na carteira nem
   no IR mensal dela. Crie uma pasta vazia, por exemplo "Teste do app" na Área de Trabalho. Não
   crie o perfil: criar o perfil é a tarefa 1.
4. **Tryd:** aberto ajuda (preços ao vivo), mas não é preciso. A tarefa é montar e registrar,
   não mandar ordem. Com o Tryd fechado, o topo da tela mostra "Fim de dia (B3)", e tudo
   funciona com os preços do último pregão.
5. **A nota fictícia preenchida e impressa** (modelo na seção 5). Na hora de preencher:
   - no Montador, escolha PETR4 e o Modelo pronto "put coberta" no vencimento mensal;
   - anote a série que ele escolher;
   - no preço, ponha um valor alguns centavos diferente do que o Montador mostra. Assim ela
     precisa trocar o preço ao registrar, como faria com uma nota de verdade.
6. Feche o app antes de ela chegar, para ela começar pelo atalho.

## 2. Regras para quem observa

- **Não ajude e não aponte.** Nada de "é ali em cima" nem de olhar para o lugar certo.
- Se ela perguntar, devolva: **"O que você tentaria?"**
- Peça para ela **pensar em voz alta**: o que está procurando, o que espera que aconteça.
- **Só ajude depois de 3 minutos parada** na mesma coisa. Quando ajudar, anote em que ponto e o
  que disse, e siga para a próxima tarefa.
- **Anote o tempo** de cada tarefa (do fim da leitura do enunciado até ela dizer "pronto").
- Se ela errar e não perceber, não corrija: anote. O erro silencioso é o achado mais valioso.

## 3. Tarefas (leia uma por vez, em voz alta)

| # | Enunciado para ela | Pronto quando |
|---|---|---|
| 1 | "Abra o Painel de Opções e crie um perfil chamado Teste, na pasta Teste do app da Área de Trabalho." | O perfil Teste está aberto ("Perfil: Teste" no canto de cima). Caminho esperado: atalho → "Novo perfil" → "Escolher pasta…" → "Criar perfil" → "Abrir". |
| 2 | "Monte uma put coberta de PETR4, no vencimento do mês. Depois me diga quanto você recebe agora e quanto pode perder no pior caso." | Ela diz os dois valores da frase do resumo ("Você recebe R$ … agora; no pior caso perde R$ …"). Pode ir pelo Book ("Abrir no montador") ou pelo Montador ("Modelo pronto"). |
| 3 | "Agora finja que você executou essa operação na corretora, com os dados desta nota. Registre no app." (entregue a nota) | A operação aparece na Carteira, em "Abertas", com a série, a quantidade e o preço da nota. Caminho esperado: "Registrar como executada" → trocar o preço → "Registrar". |
| 4 | "Na Carteira, me diga se essa operação está ganhando ou perdendo agora." | Ela lê o "Não realizado" (ou a soma com o "Realizado") e diz ganhando ou perdendo. |
| 5 (opcional) | "Ache no app uma explicação do que é uma put coberta." | Ela abre Aprender → "Operações" (ou "Comece aqui") e acha a put coberta. |

**Critério 9 cumprido:** as tarefas 2 e 3 feitas sem ajuda. As outras mostram onde mais vale
melhorar.

## 4. Ficha de anotação

Copie uma linha por tarefa.

| Tarefa | Sozinha, com ajuda ou não conseguiu | Tempo | Onde hesitou (tela e botão) | O que ela disse |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

No fim, pergunte e anote:

- "O que foi mais difícil?"
- "Teve alguma palavra que você não entendeu?"
- "Você usaria isso para acompanhar as suas operações?"

## 5. Nota fictícia (modelo para imprimir)

```
NOTA DE CORRETAGEM (FICTÍCIA, SÓ PARA O TESTE)

Data do pregão: ____/____/______
Ativo:          PETR4
Operação:       VENDA de opção de venda (put)
Série:          ______________
Quantidade:     100
Preço:          R$ ______
Custos:         (deixe em branco: o app estima)
```

## 6. Depois do teste

### Tirar o perfil Teste da lista

O app não tem "remover perfil". Com o app **fechado**, abra o `config.json` deste PC:

- Windows: `%APPDATA%\PainelOpcoes\config.json`, que você pode colar na barra do Explorador;
- Linux: `~/.config/painel-opcoes/config.json`.

Dentro de `"perfis"`, apague o bloco do Teste, sem deixar vírgula sobrando:

```json
{
  "versao": 1,
  "perfis": [
    { "nome": "Mãe", "pasta": "C:\\Users\\...\\OneDrive\\Painel de Opções" },
    { "nome": "Teste", "pasta": "C:\\Users\\...\\Desktop\\Teste do app" }
  ]
}
```

O bloco do Teste é a última linha da lista; a vírgula do fim da linha de cima também sai. Depois,
apague a pasta "Teste do app".

### Rodada de correções

Cole no Claude Code, com a ficha preenchida:

> Fiz o teste de usabilidade com a minha mãe, seguindo o `docs/teste-usabilidade.md`. Segue a
> ficha: [cole a tabela e as respostas]. Leia o roteiro e a ficha e proponha as correções,
> começando pelo que a fez travar ou errar sem perceber.
