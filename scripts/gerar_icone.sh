#!/usr/bin/env bash
# Gera o ícone do app a partir de packaging/icone/painel-opcoes.svg, a fonte única: o .ico do
# Windows, os PNGs e a cópia do SVG que a tela serve como favicon. Os gerados ficam no repositório.
#
# É ferramenta de quem mexe no ícone: precisa do ImageMagick 7 (magick) com librsvg, e o CI não roda.
#
#   scripts/gerar_icone.sh

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ICONE="$RAIZ/packaging/icone"
PUBLIC="$RAIZ/frontend/public"
SVG="$ICONE/painel-opcoes.svg"

command -v magick >/dev/null 2>&1 || {
    echo "[erro]  não achei o magick. Instale o ImageMagick 7 (com librsvg) e rode de novo." >&2
    exit 1
}

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

# densidade alta: o SVG é rasterizado grande e depois reduzido, para as bordas ficarem lisas
# 8 bits e sem os chunks de data: o PNG sai igual a cada rodada, sem ruído no git
gerar_png() {
    magick -background none -density 384 "$SVG" -resize "${1}x${1}" -depth 8 \
        -define png:exclude-chunks=date,time "$2"
}

pngs_do_ico=()
for tamanho in 16 24 32 48 64 128 256; do
    gerar_png "$tamanho" "$TEMP/p$tamanho.png"
    pngs_do_ico+=("$TEMP/p$tamanho.png")
done
gerar_png 192 "$TEMP/p192.png"

mkdir -p "$PUBLIC"
# TrueColorAlpha: sem isso o ImageMagick grava as entradas pequenas em paleta de 8 bits com máscara
# de 1 bit, e as bordas arredondadas ficam serrilhadas na barra de tarefas do Windows
magick "${pngs_do_ico[@]}" -type TrueColorAlpha "$ICONE/painel-opcoes.ico"
cp "$TEMP/p256.png" "$ICONE/painel-opcoes-256.png"
cp "$TEMP/p192.png" "$PUBLIC/icone-192.png"
cp "$SVG" "$PUBLIC/favicon.svg"

echo "[ok]    ícone gerado em $ICONE e em $PUBLIC"
