# MeshCore NOC brand guide

## Brand foundation

**Name:** MeshCore NOC

**Descriptor:** Network Operations Centre for MeshCore

**Tagline:** Monitor • Analyse • Operate

**Subtitle:** Independent Community Project

The identity combines a hexagonal operations frame with five connected nodes.
The central node represents the NOC; the surrounding nodes represent managed
MeshCore repeaters. The visual character is technical, calm, and operational.

## Colours

| Role | Name | Hex | RGB | Use |
| --- | --- | --- | --- | --- |
| Primary | Signal Blue | `#4DA3FF` | 77, 163, 255 | Mark, links, focus, primary actions |
| Secondary | Network Green | `#36C96B` | 54, 201, 107 | Healthy state, gradient endpoint |
| Background | Operations Navy | `#0B1118` | 11, 17, 24 | Dark banners and avatars |
| Surface | Console Slate | `#15212B` | 21, 33, 43 | Panels and icon interiors |
| Text | Signal White | `#F4F8FB` | 244, 248, 251 | Text on dark backgrounds |
| Text | Operations Ink | `#13212B` | 19, 33, 43 | Text on light backgrounds |
| Supporting | Telemetry Grey | `#8293A1` | 130, 147, 161 | Secondary text |
| Light background | Ice | `#EDF4F8` | 237, 244, 248 | Light banner surround |

Signal Blue and Network Green may form a linear gradient from upper-left to
lower-right. Do not substitute operational status colours for the core logo
colours.

## Typography

- **Preferred family:** Inter.
- **Repository-safe fallback:** Segoe UI, then Arial, then sans-serif.
- **Product name:** bold, title case, tight tracking.
- **Descriptor:** semibold; sentence case in prose and uppercase only in the
  supplied wordmarks.
- **Tagline:** semibold uppercase with generous tracking in artwork; title case
  in prose.
- **Body copy:** regular weight, normal tracking, concise operational language.

Do not use decorative, condensed, script, stencil, or pseudo-terminal fonts for
the primary identity.

## Logo variants

- `meshcore_noc_logo_dark.svg` is for dark backgrounds.
- `meshcore_noc_logo_light.svg` is for light backgrounds.
- `meshcore_noc_logo_monochrome.svg` is for one-colour reproduction, engraving,
  forms, or environments that cannot reproduce the primary palette.

Never recolour individual nodes, rotate the mark, alter the aspect ratio, add a
drop shadow, outline the wordmark, or rearrange the lockup.

## Minimum size

| Asset | Digital minimum | Print minimum |
| --- | ---: | ---: |
| Full logo lockup | 420 px wide | 70 mm wide |
| Standalone icon | 32 px square | 10 mm square |
| GitHub avatar | 128 px square recommended | Not applicable |
| Home Assistant icon | 128 px square recommended | Not applicable |

Below the full-logo minimum, use the standalone icon rather than removing or
compressing the text.

## Clear space

Use the diameter of the central node as the clear-space unit, **x**.

- Full logo: keep at least `1x` clear on every side.
- Standalone icon: keep at least `0.75x` clear on every side.
- No text, border, crop, badge, or other logo may enter the clear-space area.

The supplied canvases include safe internal spacing. Do not crop them to the
visible stroke.

## Light and dark usage

- Use the dark logo on Operations Navy, Console Slate, photographs with a dark
  overlay, or other backgrounds that maintain strong contrast.
- Use the light logo on white, Ice, or similarly quiet light surfaces.
- Use the monochrome logo for one-colour production only.
- Avoid mid-tone, noisy, or saturated backgrounds. If unavoidable, place the
  logo on a solid Navy or white holding panel.

Maintain readable contrast for surrounding text. Colour must not be the only
way operational status is communicated.

## Icon usage

The icon may be used independently for:

- GitHub organisation or repository avatars;
- Home Assistant integration presentation;
- browser and documentation favicons;
- social profile thumbnails; and
- small navigation surfaces.

Use the supplied square assets without adding letters, status dots,
notification badges, or rounded-mask artwork. Platforms may apply their own
circular or rounded-square crop; keep the complete hexagon inside the safe
area.

`github_avatar.*` is supplied at 512 px. `homeassistant_icon.*` is supplied at
256 px. `favicon.ico` is supplied at 64 px.

## Banner usage

The GitHub banners are 1280 × 640 pixels and retain a central safe area:

- use `github_banner_dark.png` as the default;
- use `github_banner_light.png` where a light surrounding interface is known;
- do not add release numbers, branch names, screenshots, or temporary notices
  to the master banner.

## Voice

Brand copy should be precise, calm, operator-focused, and transparent about
capabilities. Prefer “monitor,” “inspect,” “check,” and “manage” over inflated
claims. Clearly distinguish implemented features from roadmap items.

## Independence statement

Use this exact disclaimer in prominent project documentation:

> MeshCore NOC is an independent community-developed project for use with MeshCore
> networks. It is not affiliated with, endorsed by, sponsored by, or maintained by
> the MeshCore project or its developers. MeshCore is referenced solely to describe
> compatibility.

## Trademark safety

MeshCore NOC uses only its independent network-node and operations-frame
identity. Do not import, copy, trace, crop, recolour, redistribute, or recreate
the official MeshCore logo, stylised M, wordmark artwork, lettering geometry,
or font-derived logo treatment. The word “MeshCore” may appear as plain text
only where it names the compatible network technology or forms part of the
plain-text project name “MeshCore NOC”.

Third-party visual marks must never be used as MeshCore NOC interface glyphs,
integration artwork, avatars, banners, favicons, or documentation decoration.
