"""Trademark-safety and local-brand regression tests."""

from pathlib import Path

from scripts.validate_branding import DISCLAIMER, EXPECTED, LEGACY_PATHS

ROOT = Path(__file__).resolve().parents[1]


def test_home_assistant_local_brand_assets_exist() -> None:
    """Home Assistant's discovered local-brand directory has all eight assets."""
    brand = ROOT / "custom_components" / "meshcore_noc" / "brand"
    assert set(EXPECTED) == {path.name for path in brand.glob("*.png")}


def test_legacy_visual_brand_assets_are_absent() -> None:
    """Official source artwork and its legacy generator are not redistributed."""
    assert all(not (ROOT / path).exists() for path in LEGACY_PATHS)


def test_readme_uses_only_independent_branding() -> None:
    """README banners come from the independent branding package."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "branding/banner/github_banner_dark.png" in readme
    assert "branding/banner/github_banner_light.png" in readme
    assert "brand/meshcore.png" not in readme
    assert "brand/meshcore.svg" not in readme
    assert DISCLAIMER in readme


def test_generator_does_not_reference_legacy_artwork() -> None:
    """The deterministic generator cannot recreate official MeshCore artwork."""
    generator = (ROOT / "scripts" / "generate_branding_package.ps1").read_text(
        encoding="utf-8"
    )
    assert "brand\\meshcore.png" not in generator
    assert "brand/meshcore.png" not in generator
    assert "meshcore.svg" not in generator


def test_svg_assets_have_accessible_titles() -> None:
    """Every shipped SVG has a title element for assistive technology."""
    import xml.etree.ElementTree as ET

    for path in (*ROOT.glob("branding/**/*.svg"), *ROOT.glob("docs/images/*.svg")):
        svg = ET.parse(path).getroot()
        title = svg.find("{http://www.w3.org/2000/svg}title")
        assert title is not None and title.text
