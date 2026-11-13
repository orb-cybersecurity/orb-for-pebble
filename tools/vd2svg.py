#!/usr/bin/env python3
"""Convert an Android adaptive icon (background colour + VectorDrawable foreground) to SVG.

Usage: vd2svg.py FOREGROUND.xml BACKGROUND_COLOR OUT.svg [--circle]
Handles <vector>, <group> (translate/scale/rotate/pivot), <path> fill/stroke/alpha and
<clip-path>. Enough for launcher glyphs; not a general converter.
"""
import sys
import xml.etree.ElementTree as ET

A = "{http://schemas.android.com/apk/res/android}"


def color(v):
    if not v or v.startswith("@"):
        return None, 1.0
    v = v.lstrip("#")
    if len(v) == 8:
        return "#" + v[2:], int(v[:2], 16) / 255
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return "#" + v, 1.0


def group_transform(g):
    tx, ty = float(g.get(A + "translateX", 0)), float(g.get(A + "translateY", 0))
    sx, sy = float(g.get(A + "scaleX", 1)), float(g.get(A + "scaleY", 1))
    px, py = float(g.get(A + "pivotX", 0)), float(g.get(A + "pivotY", 0))
    rot = float(g.get(A + "rotation", 0))
    return (f"translate({tx + px} {ty + py}) rotate({rot}) scale({sx} {sy}) "
            f"translate({-px} {-py})")


def emit(node, out, ids):
    for ch in node:
        tag = ch.tag
        if tag == "group":
            out.append(f'<g transform="{group_transform(ch)}">')
            emit(ch, out, ids)
            out.append("</g>")
        elif tag == "clip-path":
            ids[0] += 1
            cid = f"c{ids[0]}"
            out.append(f'<clipPath id="{cid}"><path d="{ch.get(A + "pathData")}"/></clipPath>'
                       f'<g clip-path="url(#{cid})">')
            ids.append("close")
        elif tag == "path":
            d = ch.get(A + "pathData")
            fc, fa = color(ch.get(A + "fillColor"))
            sc, sa = color(ch.get(A + "strokeColor"))
            attrs = [f'd="{d}"', f'fill="{fc or "none"}"']
            if fc:
                attrs.append(f'fill-opacity="{fa * float(ch.get(A + "fillAlpha", 1))}"')
            if ch.get(A + "fillType") == "evenOdd":
                attrs.append('fill-rule="evenodd"')
            if sc:
                attrs += [f'stroke="{sc}"', f'stroke-width="{ch.get(A + "strokeWidth", 1)}"',
                          f'stroke-opacity="{sa * float(ch.get(A + "strokeAlpha", 1))}"',
                          f'stroke-linecap="{ch.get(A + "strokeLineCap", "butt")}"',
                          f'stroke-linejoin="{ch.get(A + "strokeLineJoin", "miter")}"']
            out.append(f"<path {' '.join(attrs)}/>")
    while ids[-1] == "close":
        ids.pop()
        out.append("</g>")


def main():
    fg, bg, dst = sys.argv[1:4]
    circle = "--circle" in sys.argv
    root = ET.parse(fg).getroot()
    vw, vh = float(root.get(A + "viewportWidth")), float(root.get(A + "viewportHeight"))
    body = []
    emit(root, body, [0])
    # Adaptive icon: 108x108 canvas, the launcher shows the inner 72x72 through a mask.
    mask = (f'<circle cx="54" cy="54" r="36"/>' if circle
            else '<rect x="18" y="18" width="72" height="72" rx="18"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="18 18 72 72" width="512" height="512">'
           f'<defs><clipPath id="m">{mask}</clipPath></defs><g clip-path="url(#m)">'
           f'<rect x="0" y="0" width="108" height="108" fill="{bg}"/>'
           f'<g transform="scale({108 / vw} {108 / vh})">{"".join(body)}</g></g></svg>')
    open(dst, "w").write(svg)


main()
