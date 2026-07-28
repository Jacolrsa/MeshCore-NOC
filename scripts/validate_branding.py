"""Validate MeshCore NOC local-brand PNG structure without third-party packages."""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXPECTED = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
    "logo.png": (1024, 140),
    "logo@2x.png": (2048, 280),
    "dark_icon.png": (256, 256),
    "dark_icon@2x.png": (512, 512),
    "dark_logo.png": (1024, 140),
    "dark_logo@2x.png": (2048, 280),
}
PACKAGE_PNGS = {
    "icons/github_avatar.png": (512, 512),
    "icons/homeassistant_icon.png": (256, 256),
    "banner/github_banner_dark.png": (1280, 640),
    "banner/github_banner_light.png": (1280, 640),
}
PACKAGE_SVGS = {
    "logo/meshcore_noc_logo_dark.svg": (1400, 360),
    "logo/meshcore_noc_logo_light.svg": (1400, 360),
    "logo/meshcore_noc_logo_monochrome.svg": (1400, 360),
    "icons/github_avatar.svg": (512, 512),
    "icons/homeassistant_icon.svg": (512, 512),
}
DISCLAIMER = (
    "> MeshCore NOC is an independent community-developed project for use with "
    "MeshCore\n> networks. It is not affiliated with, endorsed by, sponsored by, "
    "or maintained by\n> the MeshCore project or its developers. MeshCore is "
    "referenced solely to describe\n> compatibility."
)
LEGACY_PATHS = (
    "brand/meshcore.png",
    "brand/meshcore.svg",
    "scripts/generate_branding.ps1",
)


def read_png_header(path: Path) -> tuple[int, int, int]:
    """Return width, height, and PNG color type."""
    data = path.read_bytes()
    if data[:8] != PNG_SIGNATURE:
        raise ValueError(f"{path} is not a PNG")
    length = struct.unpack(">I", data[8:12])[0]
    if data[12:16] != b"IHDR" or length != 13:
        raise ValueError(f"{path} has an invalid IHDR")
    width, height, _, color_type = struct.unpack(">IIBB", data[16:26])
    return width, height, color_type


def validate_branding(root: Path) -> None:
    """Validate every supported local-brand derivative."""
    for relative_path in LEGACY_PATHS:
        if (root / relative_path).exists():
            raise ValueError(f"Legacy visual-brand asset still exists: {relative_path}")

    brand = root / "custom_components" / "meshcore_noc" / "brand"
    for name, dimensions in EXPECTED.items():
        path = brand / name
        if not path.is_file():
            raise ValueError(f"Missing {path}")
        width, height, color_type = read_png_header(path)
        if (width, height) != dimensions:
            raise ValueError(
                f"{name} is {width}x{height}; expected {dimensions[0]}x{dimensions[1]}"
            )
        if color_type not in (4, 6):
            raise ValueError(f"{name} does not retain an alpha channel")

    for base in ("icon", "logo", "dark_icon", "dark_logo"):
        normal = read_png_header(brand / f"{base}.png")
        double = read_png_header(brand / f"{base}@2x.png")
        if double[:2] != (normal[0] * 2, normal[1] * 2):
            raise ValueError(f"{base}@2x.png is not exactly double-sized")

    social = root / "docs" / "images" / "github-social-preview.png"
    width, height, _ = read_png_header(social)
    if (width, height) != (1280, 640):
        raise ValueError("GitHub social preview must be 1280x640")

    package = root / "branding"
    for relative_path, dimensions in PACKAGE_PNGS.items():
        path = package / relative_path
        if not path.is_file():
            raise ValueError(f"Missing branding package asset: {relative_path}")
        width, height, _ = read_png_header(path)
        if (width, height) != dimensions:
            raise ValueError(
                f"{relative_path} is {width}x{height}; "
                f"expected {dimensions[0]}x{dimensions[1]}"
            )

    for relative_path, dimensions in PACKAGE_SVGS.items():
        path = package / relative_path
        if not path.is_file():
            raise ValueError(f"Missing branding package asset: {relative_path}")
        root_element = ET.parse(path).getroot()
        if root_element.tag != "{http://www.w3.org/2000/svg}svg":
            raise ValueError(f"{relative_path} is not an SVG")
        if (
            int(root_element.attrib["width"]),
            int(root_element.attrib["height"]),
        ) != dimensions:
            raise ValueError(f"{relative_path} has unexpected dimensions")
        text = "".join(root_element.itertext())
        if "MeshCore NOC" not in text:
            raise ValueError(f"{relative_path} has no accessible MeshCore NOC title")

    favicon = package / "icons" / "favicon.ico"
    if favicon.read_bytes()[:6] != b"\x00\x00\x01\x00\x01\x00":
        raise ValueError("favicon.ico is not a single-image Windows icon")

    guide = package / "docs" / "BRAND_GUIDE.md"
    guide_text = guide.read_text(encoding="utf-8")
    for section in (
        "## Colours",
        "## Typography",
        "## Minimum size",
        "## Clear space",
        "## Light and dark usage",
        "## Icon usage",
    ):
        if section not in guide_text:
            raise ValueError(f"Brand guide is missing {section}")
    if DISCLAIMER not in guide_text:
        raise ValueError("Brand guide is missing the required independence disclaimer")

    readme = (root / "README.md").read_text(encoding="utf-8")
    if DISCLAIMER not in readme:
        raise ValueError("README is missing the required independence disclaimer")
    for image in (
        "branding/banner/github_banner_dark.png",
        "branding/banner/github_banner_light.png",
    ):
        if image not in readme:
            raise ValueError(f"README does not reference {image}")
    for legacy in ("brand/meshcore.png", "brand/meshcore.svg"):
        if legacy in readme:
            raise ValueError(f"README references legacy artwork: {legacy}")

    generator = (root / "scripts" / "generate_branding_package.ps1").read_text(
        encoding="utf-8"
    )
    for legacy in ("brand\\meshcore.png", "brand/meshcore.png", "meshcore.svg"):
        if legacy in generator:
            raise ValueError(f"Generator references legacy artwork: {legacy}")


if __name__ == "__main__":
    repository_root = Path(__file__).resolve().parents[1]
    validate_branding(repository_root)
    print("Branding validation passed.")
