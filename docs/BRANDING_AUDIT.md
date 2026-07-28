# Branding and trademark-safety audit

## Outcome

MeshCore NOC now uses only its independently designed operations-frame and
connected-network-node identity. The official MeshCore stylised M, official
wordmark artwork, and every derivative generated from that artwork have been
removed or replaced.

## Legacy assets found

| Path | Finding | Action | Replacement |
| --- | --- | --- | --- |
| `brand/meshcore.png` | Unchanged upstream MeshCore wordmark source | Deleted | None; third-party source artwork is no longer stored |
| `brand/meshcore.svg` | Unchanged upstream MeshCore vector artwork | Deleted | None; third-party source artwork is no longer stored |
| `brand/README.md` | Provenance and checksums for redistributed official artwork | Deleted | This audit and the independent brand guide |
| `scripts/generate_branding.ps1` | Cropped the official wordmark and stylised M into local assets | Deleted | `scripts/generate_branding_package.ps1` |
| `custom_components/meshcore_noc/brand/*.png` | Eight official-art derivatives | Replaced in place | Independent NOC icon and logo at required 1×/2× sizes |
| `docs/images/github-social-preview.png` | Generated using the old wordmark derivative | Replaced | Independent dark GitHub banner |
| `scripts/validate_branding.py` | Enforced upstream and derivative hashes | Replaced | Structural and trademark-safety validation |

## Home Assistant branding

Home Assistant Core 2026.3+ discovers local custom-integration artwork at:

`custom_components/meshcore_noc/brand/`

The implementation requires `icon.png`, `icon@2x.png`, `logo.png`,
`logo@2x.png`, and their `dark_` variants. All eight files now contain the
independent MeshCore NOC identity. No manifest branding key is required.

## Independent assets retained

The SVG logos, avatar, Home Assistant icon, favicon, GitHub banners, dashboard
text header, and documentation banner use generic mesh-network geometry,
communications links, and NOC wording. They contain no copied MeshCore mark or
lettering geometry.

## Plain-text compatibility references

Plain-text “MeshCore” remains in the project name, integration dependency,
repository URLs, entity descriptions, installation guidance, and operational
documentation. These references identify the compatible network technology and
are necessary to explain what the integration supports. They are text, not
third-party visual branding.

## Generator confirmation

`scripts/generate_branding_package.ps1` constructs all artwork from independent
hexagonal operations-frame and network-node geometry. It has no dependency on
an upstream image, font-derived logo file, embedded base64 image, or legacy
asset path, and it generates the Home Assistant local assets directly.

## Independence statement

> MeshCore NOC is an independent community-developed project for use with MeshCore
> networks. It is not affiliated with, endorsed by, sponsored by, or maintained by
> the MeshCore project or its developers. MeshCore is referenced solely to describe
> compatibility.
