# Design

Orb's look follows GrapheneOS's own apps (Camera, Auditor, PDF Viewer, App Store, Info), so
it sits naturally on a GrapheneOS phone. It borrows their style, not their identity: no
GrapheneOS logo, hexagon or wordmark, and Orb is not affiliated with GrapheneOS.

## Launcher icon

- A black glyph (`#000000`) on white (`#FFFFFF`), like GrapheneOS's app icons.
- The glyph: a sphere with a cyan-to-pink highlight (`#00D8FF` to `#FF4FC8`, along the
  arc). The colour is the one accent; it keeps the icon from reading as a camera lens.
- For Android's themed icons, a separate monochrome drawable has the highlight cut out of
  the sphere (even-odd fill), since the system tints that layer a single colour.
- Rounded, Material-style geometry; no shadows or other effects.

![Icon in a round mask, a squircle mask, and as a themed icon](icon-preview.png)

`make_icon.py` generates every icon asset from one geometry: the launcher foreground and
background, the status-bar icon and the 512x512 store icon (plus `orb-icon.svg`). Edit the
script, not the generated files, and run `python3 design/make_icon.py`.
`icon_candidates.py` and `render.sh` produced the three directions considered
(`candidates.png`: orb, orbit, watch); the orb was chosen.

## Colour, type and theme (reference)

GrapheneOS publishes a short branding note
([GrapheneOS/branding-extra](https://github.com/GrapheneOS/branding-extra)):

- Generally based on Material Design 3.
- Source colour `#0053a3`, with a Material 3 theme generated from it.
- Roboto where possible, Noto as fallback; Bold preferred over Regular for headings.

The in-app theme uses these: `design/theme.py` generates the Material 3 colour roles from
`#0053a3`, and its output is used in the overlay's `Theme.kt`.

## Tools

`tools/vd2svg.py` converts an Android adaptive icon (VectorDrawable foreground plus a
background colour) to SVG for previews.
