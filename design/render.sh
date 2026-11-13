#!/bin/sh
# Render each candidate as: GrapheneOS-style (black on white), themed icon (dark), on a
# circle and a squircle mask, at launcher size. Output: candidates.png
set -eu
cd "$(dirname "$0")"
python3 icon_candidates.py
row() { # name fg bg mask
  name=$1; fg=$2; bg=$3; mask=$4; out=$5
  fill=$(cat "$name.path")
  extra=""
  [ -f "$name-stroke.path" ] && extra="<path d=\"$(cat "$name-stroke.path")\" fill=\"none\" stroke=\"$fg\" stroke-width=\"4.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/>"
  if [ "$mask" = circle ]; then m='<circle cx="54" cy="54" r="36"/>'; else m='<rect x="18" y="18" width="72" height="72" rx="20"/>'; fi
  cat > "$out.svg" <<SVG
<svg xmlns="http://www.w3.org/2000/svg" viewBox="18 18 72 72" width="160" height="160"><defs><clipPath id="m">$m</clipPath></defs><g clip-path="url(#m)"><rect width="108" height="108" fill="$bg"/><path d="$fill" fill="$fg" fill-rule="evenodd"/>$extra</g></svg>
SVG
  magick -background none -density 96 "$out.svg" "$out.png"
}
set --
for n in a-orb b-orbit c-watch; do
  row $n '#000000' '#FFFFFF' circle "r-$n-1"
  row $n '#000000' '#FFFFFF' squircle "r-$n-2"
  row $n '#CBE2FF' '#2D3034' circle "r-$n-3"
  magick -background none "r-$n-1.png" "r-$n-2.png" "r-$n-3.png" +smush 20 "row-$n.png"
done
magick -background '#d9dde3' row-a-orb.png row-b-orbit.png row-c-watch.png -smush 24 \
  -bordercolor '#d9dde3' -border 24 candidates.png
rm -f r-*.svg r-*.png row-*.png
