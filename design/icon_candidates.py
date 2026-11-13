#!/usr/bin/env python3
"""Orb launcher glyph candidates in the GrapheneOS app-icon style: one solid black shape on
white, detail as cut-outs (even-odd), rounded ends. Coordinates are in the 108x108 adaptive-icon
canvas; the launcher shows the middle 72x72. Writes <name>.path (pathData) per candidate."""
import math

C = 54.0


def P(a, r, cx=C, cy=C):
    return cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))


def circle(cx, cy, r):
    return (f"M{cx - r:.2f},{cy:.2f} a{r:.2f},{r:.2f} 0 1,0 {2 * r:.2f},0 "
            f"a{r:.2f},{r:.2f} 0 1,0 {-2 * r:.2f},0 Z")


def band(a0, a1, r_out, r_in, cx=C, cy=C):
    """Arc band from angle a0 to a1 (degrees, y down) with round caps."""
    cap = (r_out - r_in) / 2
    large = 1 if (a1 - a0) % 360 > 180 else 0
    x1, y1 = P(a0, r_out, cx, cy); x2, y2 = P(a1, r_out, cx, cy)
    x3, y3 = P(a1, r_in, cx, cy); x4, y4 = P(a0, r_in, cx, cy)
    return (f"M{x1:.2f},{y1:.2f} A{r_out},{r_out} 0 {large},1 {x2:.2f},{y2:.2f} "
            f"A{cap},{cap} 0 0,1 {x3:.2f},{y3:.2f} A{r_in},{r_in} 0 {large},0 {x4:.2f},{y4:.2f} "
            f"A{cap},{cap} 0 0,1 {x1:.2f},{y1:.2f} Z")


def rrect(x, y, w, h, r):
    return (f"M{x + r},{y} H{x + w - r} A{r},{r} 0 0,1 {x + w},{y + r} V{y + h - r} "
            f"A{r},{r} 0 0,1 {x + w - r},{y + h} H{x + r} A{r},{r} 0 0,1 {x},{y + h - r} "
            f"V{y + r} A{r},{r} 0 0,1 {x + r},{y} Z")


cands = {}

# A. Orb: a solid sphere with its highlight cut out.
cands["a-orb"] = circle(C, C, 22) + " " + band(196, 254, 17.5, 12.5)

# B. Orbit: smaller sphere, a ring passing behind it (broken where it meets the sphere),
#    and a satellite on the ring: the watch, held in the phone's orbit.
def ring_segments(rx, ry, tilt, gap_r, width):
    segs, cur = [], []
    for i in range(0, 721):
        t = math.radians(i / 2)
        x, y = rx * math.cos(t), ry * math.sin(t)
        c, s = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
        px, py = C + x * c - y * s, C + x * s + y * c
        if math.hypot(px - C, py - C) > gap_r:
            cur.append((px, py))
        elif cur:
            segs.append(cur); cur = []
    if cur:
        segs.append(cur)
    # merge wrap-around
    if len(segs) > 1 and math.dist(segs[0][0], segs[-1][-1]) < 1:
        segs[0] = segs.pop() + segs[0]
    return segs
B_SEGS = ring_segments(31, 10.5, -22, 21, 4.5)
cands["b-orbit"] = circle(C, C, 15.5)
cands["b-orbit-stroke"] = " ".join(
    "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in s[::6] + [s[-1]]) for s in B_SEGS)
sx, sy = P(-62, 0, 0, 0)
# satellite on the ring at parameter angle -50 deg
t = math.radians(-50); x, y = 31 * math.cos(t), 10.5 * math.sin(t)
c, s = math.cos(math.radians(-22)), math.sin(math.radians(-22))
cands["b-orbit"] += " " + circle(C + x * c - y * s, C + x * s + y * c, 4.2)

# C. Watch: a rounded watch body with straps, a round screen cut out, and an orb inside it.
cands["c-watch"] = (rrect(40, 22, 28, 12, 3) + " " + rrect(40, 74, 28, 12, 3) + " "
                    + rrect(33, 30, 42, 48, 11) + " " + circle(C, C, 14) + " "
                    + circle(C, C, 8.5))

for k, v in cands.items():
    open(f"{k}.path", "w").write(v)
