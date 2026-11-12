# options_ponte — ponte do Tryd

Processo separado do app que lê as cotações do **Tryd** por RTD (o mesmo mecanismo que o Excel
usa) e as entrega ao app por **TCP local** (`127.0.0.1:8766`), uma mensagem JSON por linha.
Roda no **Python do Windows** — nativo, ou dentro do **Wine** no Linux — porque o servidor RTD
do Tryd é COM. Só `rtd.py` usa o pywin32 (`pythoncom`, `win32com`); o resto do pacote é stdlib e
importa em qualquer sistema (só o `tryd7.py` importa `winreg` e `ctypes`, e dentro das funções; o
`vias.py` é só biblioteca padrão).

| Módulo | Papel |
|---|---|
| `protocolo.py` | mensagens (`assinar`, `cancelar`, `valor`, `status`, `ping`/`pong`, `encerrar`), `PROGID`, `CLSID`, porta/limite/campos padrão |
| `assinaturas.py` | ids dos tópicos assinados (limite de tópicos) |
| `servidor.py` | `Ponte` (estado, cache do último valor, heartbeat, sessão que segue o processo do Tryd) e `ServidorTcp` |
| `vias.py` | as duas vias RTD (`VIA_TRYD8`, `VIA_TRYD7`), os `CODIGOS_TRYD7` e `escolher_via`, que escolhe pelo registro (injetado) |
| `tryd7.py` | o Tryd 7 por dentro: pasta do Tryd, `StDde.ini`, porta do StDde, `registrar` e `desregistrar` |
| `rtd.py` | `SessaoRtdCom` (cliente RTD via COM, na via escolhida), `processos_tryd`, `diagnostico`, `autoteste` |
| `rtd_shim.idl` | `IRtdServer`/`IRTDUpdateEvent` com os IIDs e DISPIDs do Excel, para o Wine |

A ponte **não interpreta** o valor que o Tryd entrega: repassa com o tipo de origem
(`tipo_valor`: `float`, `int`, `str`, `none`, `outro`). Os zeros que o RTD manda antes da carga e
o texto de hora são tratados pelo app. A ponte só marca `"inicial": true` no `valor` que veio do
`ConnectData` (o zero de antes da carga) e que nenhuma atualização substituiu ainda; a chave só
aparece quando verdadeira.

## As duas vias

A ponte fala com duas versões do Tryd, cada uma com o seu servidor RTD
([desenho](../../docs/superpowers/specs/2026-11-12-ponte-tryd-7-design.md)):

| | Tryd 8 (e o Profit) | Tryd 7.x |
|---|---|---|
| Servidor | `RTDTrading.RtdServer`, CLSID `{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}` | `Tryd.RtdServer`, CLSID `{5209F8A0-88D3-4D20-870C-E0C44DE1C48D}` |
| Onde roda | fora do processo: `LocalServer32` = `tryd.exe` | dentro do processo: `InprocServer32` = `mscoree.dll`, que carrega o CLR v2 (.NET 3.5) e o `StRtd.dll` (`StRtd.Controlador.StRtdServer`, em `plugins\stDde\` na pasta do Tryd) |
| Criação | o ProgID e, se ele não resolver (`CO_E_CLASSSTRING`), o CLSID com `CLSCTX_LOCAL_SERVER` | direto pelo CLSID, com `CLSCTX_INPROC_SERVER`; depois, `QueryInterface` pelo IID do `IRtdServer` do Excel, e o ponteiro devolvido é o usado (se falhar, o `IDispatch` cru) |
| Tópico | `("PETR4_B_0", "ULT")` | `("COT", "PETR4", "ULT")`, pelos `CODIGOS_TRYD7` |
| Antes de criar | nada | o `StDde.exe` rodando e a porta dele (a do `plugins\stDde\StDde.ini`, `12002` se não achar) aceitando conexão |

O Profit usa o mesmo CLSID do `RTDTrading`. Num PC com o Tryd 7 e o Profit, esse CLSID aponta para
o `profitchart.exe`, e a ponte não o usa.

**A escolha** é refeita a cada abertura de sessão, pelo registro (`escolher_via`), nesta ordem:

1. o dono do `RTDTrading` é o `tryd.exe`: Tryd 8;
2. o `Tryd.RtdServer` está registrado na visão do processo da ponte (32 bits no app instalado):
   Tryd 7;
3. o `Tryd.RtdServer` está registrado só na outra visão: a sessão não abre, e o motivo manda rodar
   `registrar`;
4. o dono do `RTDTrading` é o `profitchart.exe`: a sessão não abre, e o motivo cita o Profit;
5. senão: a sessão não abre, e o motivo diz que nenhum servidor RTD do Tryd está registrado.

- O dono do `RTDTrading` é procurado na visão do processo e, se não houver, na outra: o servidor
  fora do processo é ativado atravessando as visões. O `Tryd.RtdServer` só conta na visão do
  processo, porque carrega dentro dele.
- Em cada visão, o valor é lido em `HKCR`, `HKCU\Software\Classes` e `HKLM\Software\Classes`, o
  primeiro que o tiver: no Wine o `HKCR` não enxerga o `HKCU`, onde o Tryd 8 se registra.
- A checagem "o COM abriu outro Tryd" segue valendo, mas só dispara na via do Tryd 8: a do Tryd 7
  é dentro do processo e não lança `tryd.exe` nenhum.
- A type library preferida é a primeira (a do `RTDTrading`, depois a do Excel) cujo `IRtdServer` e
  `IRTDUpdateEvent` tenham os IIDs do Excel (`{EC0E6191-DB51-11D3-8F3E-00C04F3651B8}` e
  `{A43788C1-D91B-11D3-8F39-00C04F3651B8}`), que são os do `tryd.exe` e do `StRtd`. Se nenhuma
  tiver, vale a primeira que carregou, e o `diagnostico` avisa (`[aviso] type library … usada por
  falta de outra: IIDs diferentes dos do Excel …`); a outra, de IIDs diferentes, sai como
  `não serviu`. Os IIDs da do `RTDTrading` ainda não foram medidos.
- O `QueryInterface` da via do Tryd 7 existe porque o `IDispatch` padrão de um servidor .NET pode
  ser o da interface de classe, com DISPIDs do CLR, e não o do `IRtdServer`, que a type library
  descreve; o Excel também pede o `IRtdServer` pelo IID. A via do Tryd 8 não faz isso.

**Sessão que não abre** não derruba a ponte: ela segue ouvindo, o `Status` fica `iniciando` com o
motivo, e ela tenta de novo (a cada 10 s). O motivo vai para o `ponte.log` (se houver `--log`) e,
pelo `Status`, para o `app.log` (`ponte: Tryd iniciando (N tópicos) <motivo>`); a tela do app não
o mostra. A type library que não carrega também vira motivo: o `servir` avisa no log e segue, em
vez de sair.

### Códigos de campo do Tryd 7 (palpite)

O app pede os campos pelos códigos do Tryd 8 (`CAMPOS_ATIVO` e `CAMPOS_OPCAO` em `protocolo.py`),
e a via do Tryd 7 os traduz pela tabela `CODIGOS_TRYD7` (`vias.py`), isolada para ser corrigida
sem mexer no resto. **Os códigos do Tryd 7.5.4 são palpite (os mesmos do Tryd 8): confirmar no
Tryd dela.**

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

Como confirmar, com o Tryd 7 aberto: no Tryd, na lista de cotações, "gerar link" (RTD ou DDE) em
cada coluna, e a tabela tem de bater com os códigos gerados; e `espiar` com um ativo e uma opção,
para ver o tipo e o formato de cada valor. O que falhar se corrige em `CODIGOS_TRYD7`.

## Comandos

```text
python -m options_ponte servir --porta 8766 [--limite 600] [--log ponte.log]
python -m options_ponte diagnostico
python -m options_ponte autoteste
python -m options_ponte espiar --porta 8766 --ativos PETR4,VALE3 --segundos 10 [--campos ULT,OCP,OVD]
python -m options_ponte registrar [--pasta "<pasta do tryd.exe>"]
python -m options_ponte desregistrar
```

No app instalado, o `PonteTryd.exe` (em `ponte\` dentro da pasta do app,
`%LOCALAPPDATA%\Programs\PainelOpcoes\ponte\`) aceita os mesmos comandos, no lugar de
`python -m options_ponte`.

- `servir`: sobe a ponte e escuta em `127.0.0.1`. Só pede o servidor RTD ao COM com um `tryd.exe`
  rodando (o Tryd **aberto e logado**, com o RTD ativado: *Arquivo > Ativar DDE e RTD*): com o Tryd
  fechado, o COM o abriria. Tryd aberto depois da ponte é conectado 20 s depois; Tryd fechado larga
  a sessão, e a ponte espera o usuário abri-lo de novo. Para encerrar, envie a mensagem `encerrar`
  (ver abaixo) ou use Ctrl+C.
  - `--log <arquivo>`: grava o log da ponte (nível INFO) nesse arquivo, recriado a cada execução,
    e cria a pasta dele se faltar. Só o **app instalado** o passa
    (`%APPDATA%\PainelOpcoes\logs\ponte.log`); no Wine ele não passa, porque o caminho seria do
    Linux. A ponte lançada pelo app não tem console (a saída vai para o nada), e o arquivo é o
    único rastro: o "ponte ouvindo em …", o motivo de cada sessão que não abre e o erro que
    derruba a ponte (`a ponte caiu com um erro não tratado`, com o traceback). Se o arquivo não
    abre, a ponte avisa no stderr e segue sem ele. Escrever no stdout ou no stderr, mesmo sem
    console, não derruba a ponte.
- `diagnostico`: só leitura. Mostra como a classe é achada (ProgID ou CLSID), o `LocalServer32`
  do Tryd e sua arquitetura, qual type library foi usada e se o Tryd está rodando. Depois mostra
  as duas vias e a que a ponte vai usar, nestas linhas (os `<…>` são o que varia):
  - o dono do `RTDTrading`:
    - `[ok] RTDTrading.RtdServer -> tryd.exe (Tryd 8)`;
    - `[aviso] RTDTrading.RtdServer aponta para o profitchart.exe: isso é o RTD do Profit, não do
      Tryd`;
    - `[aviso] RTDTrading.RtdServer aponta para <exe>, que não é o tryd.exe (Tryd 8)`;
    - `[info] RTDTrading.RtdServer não registrado`;
  - o `Tryd.RtdServer`, uma vez na visão de 64 e outra na de 32 bits:
    - `[ok] Tryd.RtdServer na visão de <64|32> bits: mscoree.dll, Class …, Assembly …,
      RuntimeVersion …, CodeBase …` e, se o arquivo do `CodeBase` existe, `[ok] StRtd.dll existe`;
    - `[falta] Tryd.RtdServer não registrado na visão de <64|32> bits`;
    - `[falta] o CodeBase aponta para um arquivo que não existe: <caminho>` ou
      `[falta] sem CodeBase: o registro não diz onde está o StRtd.dll`;
  - o .NET 3.5: `[ok] .NET 3.5 (CLR v2) instalado` ou
    `[falta] .NET 3.5 (CLR v2) não instalado: ative em "Ativar ou desativar recursos do Windows"`;
  - o StDde:
    - `[ok] StDde.exe rodando` ou `[falta] StDde.exe não está rodando (ative o DDE/RTD no Tryd)`;
    - `[ok] porta <N> do StDde respondendo` ou `[falta] porta <N> do StDde não responde`;
    - `[info] StDde.ini: REGISTROU=<valor>`, com o acréscimo
      `(o StDde não se registra sem administrador; o 'PonteTryd.exe registrar' resolve)` se o valor
      é `False`, ou `[info] StDde.ini: REGISTROU não encontrado` (sem a pasta do Tryd, com
      `(Tryd fechado: sem a pasta do INI)`);
  - a via: `[ok] a ponte vai usar: Tryd 8 (RTDTrading)` ou `Tryd 7 (Tryd.RtdServer)`, ou
    `[falta] nenhuma via: <o motivo>`.

  **O código de saída** (`1` se algo falta) só conta o que impede a via escolhida: a type library,
  sempre; a classe do `RTDTrading`, só se a via for a do Tryd 8 ou nenhuma; "nenhuma via"; e, com a
  via do Tryd 7, o `Tryd.RtdServer` na visão do processo, o `CodeBase`, o .NET 3.5, o `StDde.exe`
  e a porta dele. As linhas `[falta]` da outra visão aparecem, mas não contam; num PC com o Tryd 8,
  as do Tryd 7, do .NET e do StDde também aparecem e não contam, para o `diagnostico` não dar erro
  num Tryd 8 que funciona.
- `autoteste`: cliente RTD contra um servidor RTD **falso** (no mesmo processo e noutro), sem
  Tryd. A última linha é `AUTOTESTE OK` ou `AUTOTESTE FALHOU`. Leva uns 8 s.
- `espiar`: cliente **só stdlib**, roda em qualquer Python (inclusive o do Linux). Assina os
  ativos (campos padrão `ULT,OCP,OVD,NEG,VOL,FEC,HOR,DAT`), imprime cada linha que a ponte manda
  durante `--segundos`. **Não cancela** ao sair: os tópicos ficam assinados até a ponte encerrar
  (a ponte não conta referências, e um `cancelar` derrubaria os tópicos que o app assinou).
  Use poucos ativos: tópicos novos contam no limite da ponte até ela encerrar. Deve mostrar linhas
  `valor` e um `status` com `"tryd": "conectado"`.
- `registrar`: para o Tryd 7. O `StDde.exe` tenta registrar o `Tryd.RtdServer` em
  `HKEY_CLASSES_ROOT` e, sem administrador, falha (`REGISTROU=False` no `StDde.ini`). O comando
  faz o que o RegAsm faria, **sem administrador e só em `HKCU\Software\Classes`**, nas visões de
  64 e 32 bits: o ProgID `Tryd.RtdServer` e o CLSID `{5209F8A0-88D3-4D20-870C-E0C44DE1C48D}`, com
  `InprocServer32` = `mscoree.dll`, `ThreadingModel` `Both`, `Class`, `Assembly`,
  `RuntimeVersion` `v2.0.50727` e o `CodeBase` (`file:///` e o caminho do `StRtd.dll`). Imprime
  cada valor gravado.
  - **A pasta do Tryd** é a do `tryd.exe` em execução, ou `--pasta` (a pasta do `tryd.exe`, que
    tem `plugins\stDde\StRtd.dll`). Sem uma nem outra, ou sem o `StRtd.dll` lá, sai com erro (2).
  - **A versão e o `PublicKeyToken`** do `Assembly` são lidos do próprio `StRtd.dll`, pelo
    `System.Reflection.AssemblyName` do PowerShell. Se ele não responde, ou a saída não tem a cara
    esperada, sai com erro (1) sem gravar nada.
  - **Nunca toca** o `HKLM` nem as chaves do `RTDTrading` (do Tryd 8 e do Profit).
- `desregistrar`: desfaz o `registrar`. Apaga, em `HKCU` e nas duas visões, só o ProgID
  `Tryd.RtdServer` e o CLSID dele; chave que não existe não é erro.

Mensagem de encerramento, de qualquer cliente (a partir de `src/`):

```bash
python - <<'EOF'
import socket
from options_ponte.protocolo import Encerrar, codificar
socket.create_connection(("127.0.0.1", 8766)).sendall(codificar(Encerrar()))
EOF
```

## No Windows

1. Python 3.12 e `pip install pywin32` (de preferência num venv).
2. Com o Tryd aberto e logado, a partir de `src/`:

```text
python -m options_ponte diagnostico
python -m options_ponte autoteste
python -m options_ponte servir --porta 8766
```

Com o **Tryd 7**, rode antes `python -m options_ponte registrar` (uma vez, com o Tryd aberto) e
confira o `diagnostico`: ele deve dizer `a ponte vai usar: Tryd 7 (Tryd.RtdServer)`.

O Tryd 8 registra a classe em `HKCU\Software\Classes`. O RTD dele é um `LocalServer32` (o próprio
`tryd.exe`, fora do processo): não há exigência de bits entre o Python e o Tryd. (O Tryd 7 é
dentro do processo: ver "As duas vias".) A type library
`{EFCFBDCA-78A5-450B-8228-346C4F44D5B8}` do Tryd só está registrada para 32 bits (`win32`) e não
carregou no Python de 64 bits do Wine (`TYPE_E_LIBNOTREGISTERED`); ela é a do `RTDTrading` (a do
Tryd 8 e a do Profit). A ponte tenta essa e cai para a do Excel
(`{00020813-0000-0000-C000-000000000046}` 1.4, que vem com o Office); se a do `RTDTrading` tiver
IIDs diferentes dos do Excel, a do Excel passa na frente (ver "As duas vias"). O `diagnostico` diz
qual foi usada. Este roteiro do Windows nativo não foi medido na Task 8: só o
Wine foi.

## No Linux (Wine)

1. Ambiente (distrobox `tryd`, Wine, Python 3.12 do Windows, pywin32 e o shim da type library):

```bash
scripts/linux/preparar_ponte_wine.sh --verificar   # só confere
scripts/linux/preparar_ponte_wine.sh               # instala o que falta
```

   O Tryd em si é instalado à mão no mesmo prefixo (`wine tryd.exe`, login, *Ativar DDE e RTD*).

2. Comandos (a partir de `src/`; o `-m` acha o pacote pelo diretório atual):

```bash
cd src
distrobox enter tryd -- env WINEPREFIX=$HOME/.local/share/wineprefixes/tryd \
    WINEDEBUG=-all PYTHONIOENCODING=utf-8 \
    wine 'C:\Python312\python.exe' -m options_ponte autoteste      # ou diagnostico / servir
```

3. Noutro terminal, no Linux, com qualquer Python:

```bash
cd src && python -m options_ponte espiar --porta 8766 --ativos PETR4,VALE3 --segundos 10
```

O Wine **não resolve** o ProgID `RTDTrading.RtdServer` pelo nome (`CO_E_CLASSSTRING`): o Tryd o
registra só em `HKCU\Software\Classes`. A ponte tenta o ProgID e, se falhar com esse erro, cria
pelo CLSID `{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}` com `CLSCTX_LOCAL_SERVER`. A type library do
Excel não existe no Wine: o `rtd_shim.idl` (compilado com `widl` e registrado com
`RegisterTypeLib`) a substitui com só as duas interfaces.

## Cuidados

- **Não assine em excesso.** O limite padrão é 600 tópicos; o termo de uso do Tryd proíbe
  "flood". Para conferir à mão, `espiar` com poucos ativos.
- **`RefreshData` bloqueia** se o processo do Tryd travar sem fechar: o COM não tem prazo para a
  chamada e a ponte inteira espera (medido no Wine). O app percebe pela falta de mensagens
  (`PONTE_ATRASADA_S`/`PONTE_PERDIDA_S`). Tryd que fecha ou morre é detectado pelo `Heartbeat`,
  em até uns 5 s sem avisos.
- Depois de um `RefreshData` que falha, a ponte só tenta de novo passado 1 s.
- Dentro do distrobox, o `timeout` (SIGTERM) no processo do `distrobox enter` **não mata** o
  `wine python` lá dentro: a ponte seguiu viva e ocupando a porta. Encerre pela mensagem
  `encerrar`.
- Se a porta já estiver ocupada (outra ponte viva), `servir` recusa antes de abrir uma segunda
  sessão no Tryd e antes de abrir o `--log`: o `ponte.log` da ponte viva fica intacto, e o erro vai
  só ao stderr.
- Capturas reais do Tryd ou da B3 não entram no repositório.
