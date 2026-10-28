# options_ponte — ponte do Tryd

Processo separado do app que lê as cotações do **Tryd** por RTD (o mesmo mecanismo que o Excel
usa) e as entrega ao app por **TCP local** (`127.0.0.1:8766`), uma mensagem JSON por linha.
Roda no **Python do Windows** — nativo, ou dentro do **Wine** no Linux — porque o servidor RTD
do Tryd é COM. Só `rtd.py` usa o pywin32 (`pythoncom`, `win32com`); o resto do pacote é stdlib e
importa em qualquer sistema.

| Módulo | Papel |
|---|---|
| `protocolo.py` | mensagens (`assinar`, `cancelar`, `valor`, `status`, `ping`/`pong`, `encerrar`), `PROGID`, `CLSID` |
| `assinaturas.py` | ids dos tópicos assinados (limite de tópicos) |
| `servidor.py` | `Ponte` (estado, cache do último valor, heartbeat) e `ServidorTcp` |
| `rtd.py` | `SessaoRtdCom` (cliente RTD via COM), `diagnostico`, `autoteste` |
| `rtd_shim.idl` | `IRtdServer`/`IRTDUpdateEvent` com os IIDs e DISPIDs do Excel, para o Wine |

A ponte **não interpreta** o valor que o Tryd entrega: repassa com o tipo de origem
(`tipo_valor`: `float`, `int`, `str`, `none`, `outro`). Os zeros que o RTD manda antes da carga e
o texto de hora são tratados pelo app.

## Comandos

```text
python -m options_ponte servir --porta 8766 [--limite 600]
python -m options_ponte diagnostico
python -m options_ponte autoteste
python -m options_ponte espiar --porta 8766 --ativos PETR4,VALE3 --segundos 10 [--campos ULT,OCP,OVD]
```

- `servir`: sobe a ponte. Pede o servidor RTD ao COM (o Tryd precisa estar **aberto e logado**,
  com o RTD ativado: *Arquivo > Ativar DDE e RTD*) e escuta em `127.0.0.1`. Para encerrar, envie
  a mensagem `encerrar` (ver abaixo) ou use Ctrl+C.
- `diagnostico`: só leitura. Mostra como a classe é achada (ProgID ou CLSID), o `LocalServer32`
  do Tryd e sua arquitetura, qual type library foi usada e se o Tryd está rodando.
- `autoteste`: cliente RTD contra um servidor RTD **falso** (no mesmo processo e noutro), sem
  Tryd. A última linha é `AUTOTESTE OK` ou `AUTOTESTE FALHOU`. Leva uns 8 s.
- `espiar`: cliente **só stdlib**, roda em qualquer Python (inclusive o do Linux). Assina os
  ativos (campos padrão `ULT,OCP,OVD,NEG,VOL,FEC,HOR,DAT`), imprime cada linha que a ponte manda
  durante `--segundos`. **Não cancela** ao sair: os tópicos ficam assinados até a ponte encerrar
  (a ponte não conta referências, e um `cancelar` derrubaria os tópicos que o app assinou).
  Use poucos ativos: tópicos novos contam no limite da ponte até ela encerrar. Deve mostrar linhas
  `valor` e um `status` com `"tryd": "conectado"`.

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

O Tryd registra a classe em `HKCU\Software\Classes`. O RTD é um `LocalServer32` (o próprio
`tryd.exe`, fora do processo): não há exigência de bits entre o Python e o Tryd. A type library
`{EFCFBDCA-78A5-450B-8228-346C4F44D5B8}` do Tryd só está registrada para 32 bits (`win32`) e não
carregou no Python de 64 bits do Wine (`TYPE_E_LIBNOTREGISTERED`); a ponte tenta a do Tryd e cai
para a do Excel (`{00020813-0000-0000-C000-000000000046}` 1.4, que vem com o Office). O
`diagnostico` diz qual foi usada. Este roteiro do Windows nativo não foi medido na Task 8: só o
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
  sessão no Tryd.
- Capturas reais do Tryd ou da B3 não entram no repositório.
