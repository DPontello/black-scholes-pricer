# Ponte do Tryd no PC da mãe: Tryd 7.5.4 (TrydSIM) com o Profit instalado (desenho)

Data: 2026-11-12. Origem: o diagnóstico do autor, feito num Windows 11 real (o PC da mãe): Tryd
7.5.4 TrydSIM, Office de 64 bits e o Profit também instalado. O ao vivo não chega à tela.

## 1. O que o autor achou (resumo do diagnóstico de 12/11)

1. **A ponte fala com o Profit.** O CLSID `{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}`
   (`RTDTrading.RtdServer`) tem `LocalServer32 = profitchart.exe` nesse PC, e os erros vinham de
   dentro dele ("Access violation ... in module 'profitchart.exe'").
2. **O RTD do Tryd 7.5.4 é outro:**
   - **Registro:** ProgID `Tryd.RtdServer`, CLSID `{5209F8A0-88D3-4D20-870C-E0C44DE1C48D}`.
   - **Classe .NET:** `StRtd.Controlador.StRtdServer`, assembly
     `StRtd, Version=1.13.0.0, Culture=neutral, PublicKeyToken=cad2126db594d9d0`, em
     `<pasta do Tryd>\plugins\stDde\StRtd.dll`. É AnyCPU, CLR v2.0.50727.
   - **Servidor dentro do processo:** `InprocServer32 = mscoree.dll`, `ThreadingModel=Both`. Ele
     implementa o `IRtdServer` do interop do Excel e conversa com o `StDde.exe` do Tryd por socket
     em `127.0.0.1:12002`. A porta está no `plugins\stDde\StDde.ini`, seção `[SOCKET_SERVER]`.
   - **Fórmula do Tryd:** `=RTD("tryd.rtdserver";;"COT";"<ATIVO>";"<CAMPO>")`, ou seja, três
     strings no `ConnectData`. O DDE equivalente é `=Stech|COT!PETR4.<CAMPO>`.
3. **O `StDde.exe` não consegue se registrar sem administrador.** Ele tenta `RegisterAssembly` em
   `HKEY_CLASSES_ROOT` e recebe `UnauthorizedAccessException`, e o `StDde.ini` fica com
   `REGISTROU=False`. O autor resolveu à mão gravando em `HKCU\Software\Classes` (ProgID e CLSID,
   nas visões de 64 bits e `Wow6432Node`), com `CodeBase=file:///.../StRtd.dll`.
4. **A ponte morre quando o Painel instalado a lança.** O `spawn_process` herda o stdout e o
   stderr de um app sem console. O primeiro `print(..., flush=True)` da ponte quebra, e o Painel
   relança a ponte a cada ~12 s, para sempre.
5. **O `servir` sai antes de abrir a porta** quando `rtd.carregar_tipos()` falha, e ninguém vê o
   motivo.
6. **O WebSocket `/api/ao-vivo` quebra** com `TypeError: Object of type date is not JSON
   serializable` (`market.py`, `_mandar`, `send_json`).

## 2. O que o projeto já tinha medido (e muda a leitura do item 1)

O spike de 28/10 (`docs/spikes/tryd-intraday.md`, ADR-0008) foi feito com o **Tryd PRO
8.5.6.12**. Nessa versão:

- **O `RTDTrading.RtdServer` é do próprio Tryd:** `LocalServer32 = tryd.exe`, fora do processo.
- **Tópico:** `("PETR4_B_0", "ULT")`.
- **O ProgID `tryd.rtdserver` não existe.**
- **No Windows 11 nativo (29/10):** o ProgID resolveu pelo nome, a type library `{EFCFBDCA…}`
  carregou e o `autoteste` passou.

Os códigos de campo (ULT, OCP, OVD, …) vêm do `DDEPreferences` do próprio Tryd.

**Conclusão:** o `RTDTrading.RtdServer` é a interface que o Tryd 8 e o Profit têm em comum, com o
mesmo CLSID. No PC da mãe, o Tryd 7.5.4 não tem esse servidor, e quem atende o CLSID é o Profit.
Trocar tudo para `Tryd.RtdServer` quebraria o Tryd 8.5, que é o do PC Windows do autor e o do
Wine.

## 3. Decisões

1. **A mãe fica no Tryd 7.5.4 TrydSIM** (resposta do autor, 12/11).
2. **A ponte ganha uma segunda via e escolhe sozinha qual usar.** **(decisão minha)** A escolha é
   refeita a cada abertura de sessão:
   - **Tryd 8:** o `RTDTrading.RtdServer`, se o dono do CLSID `{272D2E65…}` for o `tryd.exe`.
   - **Tryd 7:** o `Tryd.RtdServer`, se estiver registrado na visão do processo da ponte (32 bits
     no app instalado).
   - **Nenhuma das duas:** a sessão não abre, e o motivo diz o que fazer, citando o Profit quando
     é ele que está no CLSID.

   O caminho do Tryd 8 e do Wine não muda.
3. **A via do Tryd 7:**
   - **Criação:** pelo CLSID, com `CLSCTX_INPROC_SERVER`. O `mscoree` carrega o CLR v2 dentro da
     ponte.
   - **Tópico:** `("COT", ativo, código)`, pela tabela de campos da §4.
   - **Antes de criar:** o `StDde.exe` precisa estar rodando e a porta do `StDde.ini` (padrão
     12002) aceitando conexão.
   - **A checagem "o COM abriu outro Tryd"** vale só para a via do Tryd 8, que é fora do processo.
     Na via do Tryd 7 ela não dispara.
4. **Type library:** a de nome `TLB_TRYD` (`{EFCFBDCA…}`) passa a se chamar `TLB_RTDTRADING`,
   porque é a do RTDTrading, registrada tanto pelo Tryd 8 quanto pelo Profit. Uma biblioteca só
   serve se o `IRtdServer` e o `IRTDUpdateEvent` dela tiverem os IIDs do Excel
   (`{EC0E6191-DB51-11D3-8F3E-00C04F3651B8}` e `{A43788C1-D91B-11D3-8F39-00C04F3651B8}`), que é
   o que o `StRtd` implementa. **(decisão minha)**
5. **Comandos `registrar` e `desregistrar` na ponte**, sem administrador:
   - **Onde grava:** só em `HKCU\Software\Classes`, nas duas visões. As chaves são as do
     `Tryd.RtdServer` e do CLSID `{5209F8A0…}`.
   - **Pasta do Tryd:** vem do `tryd.exe` em execução ou de `--pasta`.
   - **Versão e PublicKeyToken:** são lidos do próprio `StRtd.dll`, pelo
     `System.Reflection.AssemblyName` do PowerShell **(decisão minha)**.
   - **O que nunca toca:** `HKLM` e as chaves do `RTDTrading`/Profit.
   - **`desregistrar`:** apaga só o que o `registrar` grava.
6. **`diagnostico`** passa a mostrar:
   - o dono do CLSID do RTDTrading. Se for o `profitchart.exe`, aparece
     `[aviso] RTDTrading.RtdServer aponta para o profitchart.exe: isso é o RTD do Profit, não do
     Tryd`;
   - o `Tryd.RtdServer` nas duas visões: `InprocServer32`, `Class`, `Assembly`,
     `RuntimeVersion`, e o `CodeBase` apontando para um arquivo que existe;
   - o .NET 3.5 (CLR v2);
   - o `StDde.exe` rodando, a porta do `StDde.ini` e o `REGISTROU`;
   - a via que a ponte vai usar.
7. **A ponte lançada escondida não herda nada do Painel:**
   - stdout e stderr vão para `DEVNULL`;
   - no app instalado, a ponte grava o próprio log em `%APPDATA%\PainelOpcoes\logs\ponte.log`
     (`--log`, truncado a cada execução);
   - os `print` de status não derrubam o processo se a escrita falhar.
8. **`servir` resiliente:** sem type library, ou com o servidor falhando, a ponte continua ouvindo
   e manda `Status(perdido, motivo)`. A `Ponte` já tenta abrir a sessão de novo a cada 10 s. O
   `servir` só deixa de sair na falha do `carregar_tipos`.
9. **WebSocket:** as mensagens passam por `jsonable_encoder` antes do `send_json`.
10. **Tradução dos valores:** não muda. O `translation.py` já lê vírgula decimal (`"52,51"`,
    `"1.234,5"`) e nunca faz de vazio ou zero um preço. O que o Tryd 7 manda de fato fica para a
    conferência (§4).

## 4. Tabela de campos

O app pede os campos pelos códigos do Tryd 8 (`CAMPOS_ATIVO` e `CAMPOS_OPCAO` em `protocolo.py`).
Na via do Tryd 7, a tabela `CODIGOS_TRYD7` traduz cada um. Ela fica isolada num módulo, para ser
corrigida sem mexer no resto.

| Campo do app | Tryd 8.5 (medido em 28/10) | Tryd 7.5.4 (palpite, **confirmar**) |
|---|---|---|
| Último preço | `ULT` (float) | `ULT` |
| Melhor oferta de compra | `OCP` (float) | `OCP` |
| Melhor oferta de venda | `OVD` (float) | `OVD` |
| Negócios | `NEG` (int) | `NEG` (pode vir como texto `"1.234"`: confirmar) |
| Volume (financeiro no 8.5) | `VOL` (float) | `VOL` (financeiro ou quantidade? confirmar) |
| Fechamento anterior (só ativo) | `FEC` | `FEC` |
| Hora | `HOR` (texto `"12:02:31"`) | `HOR` (confirmar o formato) |
| Data | `DAT` (texto `"28/10/2026"`) | `DAT` (confirmar o formato) |

**Como confirmar no PC dela:**
1. No Tryd, abra a lista de cotações e use "gerar link" (RTD ou DDE) em cada coluna. A tabela
   tem de bater com os códigos gerados.
2. Rode `PonteTryd.exe espiar PETR4` e uma opção, para ver o tipo e o formato de cada valor.

## 5. Não-objetivos

- **Instalar ou compilar a type library do shim** no app do Windows. Se o `diagnostico` mostrar
  que nenhuma biblioteca carrega no PC dela, vira tarefa nova.
- **Mexer no registro do Profit, ou gravar em `HKLM`.**
- **Mudar os campos que o app pede, ou a tradução dos valores**, antes da conferência da §4.
- **Atualizar o Tryd dela.**

## 6. Critérios de aceite

1. **No PC dela, depois do `PonteTryd.exe registrar`:**
   - o `diagnostico` mostra a via do Tryd 7, o aviso do Profit e o `StDde` respondendo;
   - o app mostra "Ao vivo" e cotações de PETR4 e das opções.
2. **No PC Windows do autor (Tryd 8.5) e no Wine:** a via escolhida é a do Tryd 8, e o
   comportamento é o de antes.
3. **Ponte lançada pelo app instalado:** sobe uma vez e fica de pé. O `logs\ponte.log` tem o
   "ponte ouvindo em …", e o `app.log` não tem relançamento em laço.
4. **Sem servidor RTD utilizável:** a ponte fica no ar e o app mostra o motivo.
5. **O `/api/ao-vivo`** não quebra com data na mensagem.
6. **Gates:**
   - ruff, mypy, import-linter;
   - pytest com cobertura ≥ 95%;
   - frontend e build;
   - os testes da ponte (`tests/ponte`).
