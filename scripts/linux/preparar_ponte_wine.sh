#!/usr/bin/env bash
# Prepara, no Linux, o ambiente em que a ponte do Tryd roda: distrobox `tryd` (Fedora), Wine,
# Python 3.12 do Windows em C:\Python312, pywin32 e o shim da type library do Excel
# (src/options_ponte/rtd_shim.idl, compilado com widl e registrado com RegisterTypeLib).
#
# Idempotente: cada passo confere o que já existe e só faz o que falta.
#
#   scripts/linux/preparar_ponte_wine.sh              confere e instala o que falta
#   scripts/linux/preparar_ponte_wine.sh --verificar  só confere (não instala nada); sai com 1 se falta algo
#
# O Tryd em si (instalador, login, "Ativar DDE e RTD") continua manual: este script não o toca.
#
# Variáveis: CAIXA (tryd), IMAGEM (fedora:44), WINEPREFIX_TRYD ($HOME/.local/share/wineprefixes/tryd),
# PYTHON_INSTALADOR (caminho do instalador do Python; baixado se não existir), PYWIN32_VERSAO (312).

set -euo pipefail

CAIXA="${CAIXA:-tryd}"
IMAGEM="${IMAGEM:-registry.fedoraproject.org/fedora:44}"
PREFIXO="${WINEPREFIX_TRYD:-$HOME/.local/share/wineprefixes/tryd}"
PYTHON_VERSAO="3.12.10"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSAO}/python-${PYTHON_VERSAO}-amd64.exe"
PYTHON_INSTALADOR="${PYTHON_INSTALADOR:-$HOME/Downloads/python-windows/python-${PYTHON_VERSAO}-amd64.exe}"
PYWIN32_VERSAO="${PYWIN32_VERSAO:-312}"
TLB_EXCEL="{00020813-0000-0000-C000-000000000046}"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IDL="$RAIZ/src/options_ponte/rtd_shim.idl"
DIR_SHIM="$PREFIXO/drive_c/rtd-shim"
TRYD_EXE="$PREFIXO/drive_c/users/$USER/AppData/Roaming/Tryd/Tryd/tryd.exe"

uso() {
    sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

VERIFICAR=0
case "${1:-}" in
    "") ;;
    --verificar) VERIFICAR=1 ;;
    -h | --help) uso; exit 0 ;;
    *) uso >&2; exit 2 ;;
esac

FALTAS=0
ok() { printf '[ok]    %s\n' "$1"; }
falta() { printf '[falta] %s\n' "$1"; FALTAS=$((FALTAS + 1)); }
info() { printf '[....]  %s\n' "$1"; }

# --- atalhos para rodar dentro da caixa e dentro do Wine -----------------------------------

na_caixa() { distrobox enter "$CAIXA" -- "$@"; }
wine_py() {
    na_caixa env WINEPREFIX="$PREFIXO" WINEDEBUG=-all PYTHONIOENCODING=utf-8 \
        wine 'C:\Python312\python.exe' "$@"
}

# --- conferências (devolvem 0/1, nunca abortam) e instalações ------------------------------

checar_distrobox() { command -v distrobox >/dev/null 2>&1; }
instalar_distrobox() {
    echo "instale o distrobox e o podman pelo gerenciador de pacotes (ex.: sudo dnf install distrobox podman)" >&2
    return 1
}

checar_caixa() {
    checar_distrobox && distrobox list 2>/dev/null |
        awk -F'|' -v nome="$CAIXA" '{ gsub(/ /, "", $2) } $2 == nome { achou = 1 } END { exit !achou }'
}
instalar_caixa() { distrobox create --yes --name "$CAIXA" --image "$IMAGEM"; }

# wine-devel traz o widl, que compila o .idl do shim
checar_pacotes() { checar_caixa && na_caixa rpm -q wine-core wine-devel >/dev/null 2>&1; }
instalar_pacotes() { na_caixa sudo dnf install -y --setopt=install_weak_deps=False wine wine-devel; }

checar_prefixo() { [[ -f "$PREFIXO/system.reg" ]]; }
instalar_prefixo() {
    mkdir -p "$(dirname "$PREFIXO")"
    # mscoree/mshtml desligados: o wineboot não pergunta por Mono/Gecko, que a ponte não usa
    na_caixa env WINEPREFIX="$PREFIXO" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml=" wineboot --init
}

checar_python() {
    checar_prefixo && [[ -f "$PREFIXO/drive_c/Python312/python.exe" ]] &&
        wine_py --version 2>&1 | grep -q '^Python 3\.12\.'
}
instalar_python() {
    if [[ ! -f "$PYTHON_INSTALADOR" ]]; then
        mkdir -p "$(dirname "$PYTHON_INSTALADOR")"
        curl -fL --output "$PYTHON_INSTALADOR" "$PYTHON_URL"
    fi
    na_caixa env WINEPREFIX="$PREFIXO" WINEDEBUG=-all wine "$PYTHON_INSTALADOR" /quiet \
        InstallAllUsers=1 'TargetDir=C:\Python312' Include_launcher=0 Include_test=0 \
        Include_doc=0 PrependPath=0
}

checar_pywin32() {
    checar_python && wine_py -c "import pythoncom, win32com.client" >/dev/null 2>&1
}
instalar_pywin32() { wine_py -m pip install "pywin32==$PYWIN32_VERSAO"; }

# A ponte pede IRtdServer/IRTDUpdateEvent à type library do Excel (que o Wine não tem): o shim
# usa o mesmo LIBID, versão, IIDs e DISPIDs. Compilado com widl e registrado em HKLM do prefixo.
checar_shim() {
    checar_pywin32 && wine_py -c \
        "import pythoncom; pythoncom.LoadRegTypeLib('$TLB_EXCEL', 1, 4, 0)" >/dev/null 2>&1
}
instalar_shim() {
    mkdir -p "$DIR_SHIM"
    cp "$IDL" "$DIR_SHIM/rtd_shim.idl"
    na_caixa bash -c 'cd "$1" && widl -m64 -t -o rtd_shim.tlb rtd_shim.idl' _ "$DIR_SHIM"
    wine_py -c "import pythoncom; t = pythoncom.LoadTypeLib(r'C:\\rtd-shim\\rtd_shim.tlb'); pythoncom.RegisterTypeLib(t, r'C:\\rtd-shim\\rtd_shim.tlb')"
}

# --- roteiro -------------------------------------------------------------------------------

passo() {
    local descricao="$1" checar="$2" instalar="$3"
    if "$checar"; then
        ok "$descricao"
        return 0
    fi
    if ((VERIFICAR)); then
        falta "$descricao"
        return 0
    fi
    info "instalando: $descricao"
    "$instalar"
    if "$checar"; then
        ok "$descricao"
    else
        falta "$descricao (a instalação terminou, mas a conferência ainda falha)"
    fi
}

passo "distrobox instalado" checar_distrobox instalar_distrobox
passo "caixa '$CAIXA' ($IMAGEM)" checar_caixa instalar_caixa
passo "Wine e widl na caixa (wine-core, wine-devel)" checar_pacotes instalar_pacotes
passo "prefixo do Wine em $PREFIXO" checar_prefixo instalar_prefixo
passo "Python $PYTHON_VERSAO do Windows em C:\\Python312" checar_python instalar_python
passo "pywin32 $PYWIN32_VERSAO no Python do Wine" checar_pywin32 instalar_pywin32
passo "type library do Excel 1.4 (shim de src/options_ponte/rtd_shim.idl)" checar_shim instalar_shim

if [[ -f "$TRYD_EXE" ]]; then
    ok "Tryd instalado no prefixo"
else
    printf '[aviso] Tryd não instalado em %s (instalação manual: wine tryd.exe; depois, no Tryd: Arquivo > Ativar DDE e RTD)\n' "$PREFIXO"
fi

if ((FALTAS)); then
    if ((VERIFICAR)); then
        printf '\nFaltam %d item(ns). Rode sem --verificar para instalar.\n' "$FALTAS"
    else
        printf '\nFicaram %d item(ns) pendente(s).\n' "$FALTAS"
    fi
    exit 1
fi
printf '\nAmbiente pronto. Teste: (cd src && distrobox enter %s -- env WINEPREFIX=%s WINEDEBUG=-all wine %s -m options_ponte autoteste)\n' \
    "$CAIXA" "$PREFIXO" "'C:\\Python312\\python.exe'"
