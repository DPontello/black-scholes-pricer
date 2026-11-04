#!/usr/bin/env bash
# Instala o Painel de Opções neste PC (Linux): cria o ambiente Python em
# ~/.local/share/painel-opcoes/venv, compila a tela (frontend) e põe o atalho "Painel de Opções"
# no menu de aplicativos (~/.local/share/applications/painel-opcoes.desktop). Não usa sudo.
#
# A instalação continua apontando para esta pasta do repositório (pip install -e): para atualizar,
# rode `git pull` e este script de novo. Se a pasta mudar de lugar, rode o script da pasta nova.
#
# Idempotente: se o ambiente já existe, ele é reaproveitado.
#
#   scripts/linux/instalar.sh            instala
#   scripts/linux/instalar.sh --simular  só mostra o que faria (confere Python e Node, não grava nada)
#
# Precisa de Python 3.12+ e de Node.js com npm. A ponte do Tryd (distrobox) é preparada à parte,
# por preparar_ponte_wine.sh.
#
# Variáveis: PYTHON (python3), DIR_APP ($HOME/.local/share/painel-opcoes),
# DIR_MENU ($HOME/.local/share/applications).

set -euo pipefail

PYTHON="${PYTHON:-python3}"
DIR_APP="${DIR_APP:-$HOME/.local/share/painel-opcoes}"
DIR_MENU="${DIR_MENU:-$HOME/.local/share/applications}"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$DIR_APP/venv"
MODELO="$RAIZ/scripts/linux/painel-opcoes.desktop.in"
ATALHO="$DIR_MENU/painel-opcoes.desktop"

uso() {
    sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

SIMULAR=0
case "${1:-}" in
    "") ;;
    --simular) SIMULAR=1 ;;
    -h | --help) uso; exit 0 ;;
    *) uso >&2; exit 2 ;;
esac

ok() { printf '[ok]    %s\n' "$1"; }
info() { printf '[....]  %s\n' "$1"; }
erro() { printf '[erro]  %s\n' "$1" >&2; exit 1; }

# --- conferências (rodam também em --simular) ----------------------------------------------

conferir_python() {
    command -v "$PYTHON" >/dev/null 2>&1 ||
        erro "não achei o Python ($PYTHON). Instale o Python 3.12 ou mais novo, ou aponte um com PYTHON=/caminho/do/python3.12"
    local versao
    versao="$("$PYTHON" --version 2>&1 || true)"
    [[ $versao =~ ^Python\ ([0-9]+)\.([0-9]+) ]] ||
        erro "não consegui ler a versão do Python ($PYTHON): $versao"
    if ((BASH_REMATCH[1] < 3 || (BASH_REMATCH[1] == 3 && BASH_REMATCH[2] < 12))); then
        erro "o app precisa do Python 3.12 ou mais novo, e $PYTHON é o ${versao#Python }. Instale um mais novo, ou aponte um com PYTHON=/caminho/do/python3.12"
    fi
    ok "$versao ($PYTHON)"
}

conferir_node() {
    local ferramenta
    for ferramenta in node npm; do
        command -v "$ferramenta" >/dev/null 2>&1 ||
            erro "não achei o $ferramenta, que compila a tela. Instale o Node.js (pacotes nodejs e npm) e rode de novo."
    done
    ok "Node.js e npm"
}

# --- execução: mostra o comando e, fora de --simular, roda ----------------------------------

mostrar() {
    local texto="" arg
    for arg in "$@"; do
        [[ $arg =~ ^[A-Za-z0-9_./:=@%+,-]+$ ]] || arg="\"$arg\""
        texto+=" $arg"
    done
    printf '        $%s\n' "$texto"
}

executar() {
    mostrar "$@"
    ((SIMULAR)) || "$@"
}

# --- atalho ---------------------------------------------------------------------------------

# Argumento do Exec pela spec do Desktop Entry: o que tem caractere reservado vai entre aspas
# duplas, com `\`, `"`, `` ` `` e `$` escapados (a barra do escape vale em dobro, porque o
# arquivo também tem o seu escape de texto, e a própria `\` vira quatro); `%` vira `%%`.
arg_exec() {
    local arg="${1//\%/%%}" reservados=$' \t"\'\\<>~|&;$*?#()`'
    if [[ $arg == *["$reservados"]* ]]; then
        arg="$(printf '%s' "$arg" | sed -e 's/\\/\\\\\\\\/g' -e 's/["`$]/\\\\&/g')"
        arg="\"$arg\""
    fi
    printf '%s' "$arg"
}

gerar_atalho() {
    local modelo python
    modelo="$(<"$MODELO")"
    python="$(arg_exec "$VENV/bin/python")"
    printf '%s\n' "${modelo//@PYTHON@/"$python"}"
}

instalar_atalho() {
    if ((SIMULAR)); then
        local linha
        while IFS= read -r linha; do
            printf '        | %s\n' "$linha"
        done < <(gerar_atalho)
    else
        mkdir -p "$DIR_MENU"
        gerar_atalho >"$ATALHO"
    fi
}

# --- roteiro --------------------------------------------------------------------------------

if ((SIMULAR)); then
    printf 'Simulação: só mostra o que seria feito; nada é instalado nem gravado.\n\n'
fi

conferir_python
conferir_node
echo

info "Ambiente Python em $VENV"
if "$VENV/bin/python" --version >/dev/null 2>&1; then
    printf '        (já existe: será reaproveitado)\n'
elif [[ -d $VENV ]]; then
    # sobra de um Python que saiu do PC (link quebrado) ou de uma criação interrompida
    printf '        (existe, mas o Python dele não roda: será refeito)\n'
    executar "$PYTHON" -m venv --clear "$VENV"
else
    executar "$PYTHON" -m venv "$VENV"
fi

# -e: o pacote só leva options_engine; options_ponte e a tela compilada ficam em src/ desta pasta
info "App e dependências (apontando para $RAIZ)"
executar "$VENV/bin/python" -m pip install -e "$RAIZ[app]"

info "Tela (frontend)"
executar npm --prefix "$RAIZ/frontend" ci
executar npm --prefix "$RAIZ/frontend" run build

info "Atalho no menu de aplicativos: $ATALHO"
instalar_atalho

echo
if ((SIMULAR)); then
    echo "Simulação terminada: nada foi instalado. Rode sem --simular para instalar."
else
    echo "Pronto: \"Painel de Opções\" já aparece no menu de aplicativos."
    echo "Para atualizar: git pull e rode este script de novo."
fi
echo "Lembrete: a ponte do Tryd roda no distrobox. Para conferir o ambiente dela:"
echo "    $RAIZ/scripts/linux/preparar_ponte_wine.sh --verificar"
