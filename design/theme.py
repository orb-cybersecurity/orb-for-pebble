#!/usr/bin/env python3
"""Print the Material 3 light and dark colour roles for Orb's theme.

GrapheneOS publishes its branding as Material Design 3 from source colour #0053A3
(github.com/GrapheneOS/branding-extra, docs/res/material-theme.svg). This reproduces that theme
with Google's material-color-utilities (Apache-2.0; `pip install materialyoucolor`), using the
original Material Theme Builder scheme: primary chroma max(48, source), secondary 16, tertiary
24 at hue +60, neutrals 4 and 8. It matches GrapheneOS's published primary, error and neutral
roles exactly. Its secondary and tertiary roles differ from the published ones by one or two
units (an older HCT rounding), so the published values override them below.
The output was pasted into overlay/util/src/commonMain/kotlin/theme/Theme.kt.
"""
from materialyoucolor.hct import Hct
from materialyoucolor.palettes.tonal_palette import TonalPalette as TP

src = Hct.from_int(0xFF0053A3)
a1 = TP.from_hue_and_chroma(src.hue, max(48, src.chroma))
a2 = TP.from_hue_and_chroma(src.hue, 16)
a3 = TP.from_hue_and_chroma((src.hue + 60) % 360, 24)
n1 = TP.from_hue_and_chroma(src.hue, 4)
n2 = TP.from_hue_and_chroma(src.hue, 8)
er = TP.from_hue_and_chroma(25, 84)

TONES = {  # role: (palette, light tone, dark tone)
    "primary": (a1, 40, 80), "onPrimary": (a1, 100, 20),
    "primaryContainer": (a1, 90, 30), "onPrimaryContainer": (a1, 10, 90),
    "secondary": (a2, 40, 80), "onSecondary": (a2, 100, 20),
    "secondaryContainer": (a2, 90, 30), "onSecondaryContainer": (a2, 10, 90),
    "tertiary": (a3, 40, 80), "onTertiary": (a3, 100, 20),
    "tertiaryContainer": (a3, 90, 30), "onTertiaryContainer": (a3, 10, 90),
    "error": (er, 40, 80), "onError": (er, 100, 20),
    "errorContainer": (er, 90, 30), "onErrorContainer": (er, 10, 90),
    "background": (n1, 99, 10), "onBackground": (n1, 10, 90),
    "surface": (n1, 99, 10), "onSurface": (n1, 10, 90),
    "surfaceVariant": (n2, 90, 30), "onSurfaceVariant": (n2, 30, 80),
    "outline": (n2, 50, 60), "outlineVariant": (n2, 80, 30),
    "inverseSurface": (n1, 20, 90), "inverseOnSurface": (n1, 95, 20),
    "inversePrimary": (a1, 80, 40), "scrim": (n1, 0, 0),
    "surfaceDim": (n1, 87, 6), "surfaceBright": (n1, 98, 24),
    "surfaceContainerLowest": (n1, 100, 4), "surfaceContainerLow": (n1, 96, 10),
    "surfaceContainer": (n1, 94, 12), "surfaceContainerHigh": (n1, 92, 17),
    "surfaceContainerHighest": (n1, 90, 22),
}
# GrapheneOS's published values where the generator differs by rounding.
PUBLISHED = {
    "light": {"secondary": "#545F73", "secondaryContainer": "#D8E3FB",
              "onSecondaryContainer": "#111C2D", "tertiary": "#705577",
              "tertiaryContainer": "#FAD7FF", "onTertiaryContainer": "#291230"},
    "dark": {"secondary": "#BCC7DE", "onSecondary": "#263143", "secondaryContainer": "#3D475A",
             "onSecondaryContainer": "#D8E3FB", "tertiary": "#DDBBE3", "onTertiary": "#3F2747",
             "tertiaryContainer": "#573D5E", "onTertiaryContainer": "#FAD7FF"},
}

for mode, idx in (("light", 1), ("dark", 2)):
    print(f"// {mode}")
    for role, spec in TONES.items():
        value = PUBLISHED[mode].get(role) or "#%06X" % (spec[0].tone(spec[idx]) & 0xFFFFFF)
        print(f"    {role} = Color(0xFF{value[1:]}),")
