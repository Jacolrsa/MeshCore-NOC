param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$branding = Join-Path $RepositoryRoot "branding"
$logo = Join-Path $branding "logo"
$icons = Join-Path $branding "icons"
$banner = Join-Path $branding "banner"
$docs = Join-Path $branding "docs"
$homeAssistantBrand = Join-Path $RepositoryRoot "custom_components\meshcore_noc\brand"
$docsImages = Join-Path $RepositoryRoot "docs\images"
foreach ($directory in ($logo, $icons, $banner, $docs)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
foreach ($directory in ($homeAssistantBrand, $docsImages)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$navy = "#0B1118"
$panel = "#15212B"
$white = "#F4F8FB"
$ink = "#13212B"
$muted = "#8293A1"
$blue = "#4DA3FF"
$green = "#36C96B"

function Write-Utf8 {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function New-IconSvg {
    param([string]$Background = "none")
    @"
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" role="img" aria-labelledby="title desc">
  <title id="title">MeshCore NOC icon</title>
  <desc id="desc">A connected mesh network inside a hexagonal operations frame.</desc>
  <defs>
    <linearGradient id="signal" x1="72" y1="72" x2="440" y2="440" gradientUnits="userSpaceOnUse">
      <stop stop-color="$blue"/>
      <stop offset="1" stop-color="$green"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="$Background"/>
  <path d="M256 58 420 153v190L256 438 92 343V153Z" fill="none" stroke="url(#signal)" stroke-width="28" stroke-linejoin="round"/>
  <g fill="none" stroke="$white" stroke-width="18" stroke-linecap="round">
    <path d="m256 256-91-66M256 256l91-66M256 256l91 78M256 256l-91 78"/>
  </g>
  <g fill="$panel" stroke="url(#signal)" stroke-width="18">
    <circle cx="256" cy="256" r="48"/>
    <circle cx="165" cy="190" r="30"/>
    <circle cx="347" cy="190" r="30"/>
    <circle cx="347" cy="334" r="30"/>
    <circle cx="165" cy="334" r="30"/>
  </g>
  <circle cx="256" cy="256" r="14" fill="$white"/>
</svg>
"@
}

function New-LogoSvg {
    param(
        [string]$TextColor,
        [bool]$Monochrome
    )
    $markStroke = if ($Monochrome) { $TextColor } else { "url(#signal)" }
    $nodeStroke = $markStroke
    $nodeFill = if ($Monochrome) { "#FFFFFF" } else { $panel }
    $secondaryText = if ($Monochrome) { $TextColor } else { $muted }
    @"
<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="360" viewBox="0 0 1400 360" role="img" aria-labelledby="title desc">
  <title id="title">MeshCore NOC</title>
  <desc id="desc">Network Operations Centre for MeshCore. Monitor, Analyse, Operate.</desc>
  <defs>
    <linearGradient id="signal" x1="30" y1="30" x2="330" y2="330" gradientUnits="userSpaceOnUse">
      <stop stop-color="$blue"/>
      <stop offset="1" stop-color="$green"/>
    </linearGradient>
  </defs>
  <g transform="translate(24 24)">
    <path d="M156 12 292 91v158l-136 79L20 249V91Z" fill="none" stroke="$markStroke" stroke-width="22" stroke-linejoin="round"/>
    <g fill="none" stroke="$TextColor" stroke-width="14" stroke-linecap="round">
      <path d="m156 170-70-49M156 170l70-49M156 170l70 64M156 170l-70 64"/>
    </g>
    <g fill="$nodeFill" stroke="$nodeStroke" stroke-width="14">
      <circle cx="156" cy="170" r="38"/><circle cx="86" cy="121" r="22"/>
      <circle cx="226" cy="121" r="22"/><circle cx="226" cy="234" r="22"/>
      <circle cx="86" cy="234" r="22"/>
    </g>
    <circle cx="156" cy="170" r="10" fill="$TextColor"/>
  </g>
  <g fill="$TextColor" font-family="Inter, Segoe UI, Arial, sans-serif">
    <text x="390" y="148" font-size="104" font-weight="750" letter-spacing="-2">MeshCore NOC</text>
    <text x="396" y="206" font-size="32" font-weight="600" letter-spacing="1">NETWORK OPERATIONS CENTRE FOR MESHCORE</text>
    <text x="396" y="260" font-size="27" font-weight="500" letter-spacing="4">MONITOR &#8226; ANALYSE &#8226; OPERATE</text>
    <text x="396" y="309" fill="$secondaryText" font-size="23" font-weight="500">Independent Community Project</text>
  </g>
</svg>
"@
}

function New-BannerSvg {
    param([bool]$Dark)
    $background = if ($Dark) { $navy } else { "#EDF4F8" }
    $surface = if ($Dark) { $panel } else { "#FFFFFF" }
    $text = if ($Dark) { $white } else { $ink }
    @"
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" viewBox="0 0 1280 640" role="img" aria-labelledby="title desc">
  <title id="title">MeshCore NOC</title>
  <desc id="desc">Network Operations Centre for MeshCore. Monitor, Analyse, Operate. Independent Community Project.</desc>
  <defs>
    <linearGradient id="signal" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="$blue"/><stop offset="1" stop-color="$green"/>
    </linearGradient>
    <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M48 0H0V48" fill="none" stroke="$muted" stroke-opacity=".12"/>
    </pattern>
  </defs>
  <rect width="1280" height="640" rx="32" fill="$background"/>
  <rect width="1280" height="640" rx="32" fill="url(#grid)"/>
  <g opacity=".25" stroke="url(#signal)" stroke-width="3">
    <path d="M70 128 250 70l170 125 185-90 160 100 190-110 250 125" fill="none"/>
    <path d="m62 490 195-95 172 84 176-127 175 105 180-80 242 116" fill="none"/>
  </g>
  <rect x="98" y="92" width="1084" height="456" rx="30" fill="$surface" stroke="$muted" stroke-opacity=".18"/>
  <g transform="translate(138 150)">
    <path d="M145 0 270 72v144l-125 72L20 216V72Z" fill="none" stroke="url(#signal)" stroke-width="22" stroke-linejoin="round"/>
    <g fill="none" stroke="$text" stroke-width="14" stroke-linecap="round">
      <path d="m145 144-64-46M145 144l64-46M145 144l64 55M145 144l-64 55"/>
    </g>
    <g fill="$surface" stroke="url(#signal)" stroke-width="14">
      <circle cx="145" cy="144" r="36"/><circle cx="81" cy="98" r="21"/>
      <circle cx="209" cy="98" r="21"/><circle cx="209" cy="199" r="21"/>
      <circle cx="81" cy="199" r="21"/>
    </g>
    <circle cx="145" cy="144" r="10" fill="$text"/>
  </g>
  <g fill="$text" font-family="Inter, Segoe UI, Arial, sans-serif">
    <text x="500" y="245" font-size="76" font-weight="750" letter-spacing="-2">MeshCore NOC</text>
    <text x="505" y="305" font-size="29" font-weight="600">Network Operations Centre for MeshCore</text>
    <rect x="505" y="345" width="500" height="3" rx="1.5" fill="url(#signal)"/>
    <text x="505" y="405" font-size="27" font-weight="600" letter-spacing="5">MONITOR &#8226; ANALYSE &#8226; OPERATE</text>
    <text x="505" y="458" fill="$muted" font-size="23" font-weight="500">Independent Community Project</text>
  </g>
</svg>
"@
}

Write-Utf8 (Join-Path $logo "meshcore_noc_logo_dark.svg") (New-LogoSvg -TextColor $white -Monochrome $false)
Write-Utf8 (Join-Path $logo "meshcore_noc_logo_light.svg") (New-LogoSvg -TextColor $ink -Monochrome $false)
Write-Utf8 (Join-Path $logo "meshcore_noc_logo_monochrome.svg") (New-LogoSvg -TextColor "#000000" -Monochrome $true)
Write-Utf8 (Join-Path $icons "github_avatar.svg") (New-IconSvg -Background $navy)
Write-Utf8 (Join-Path $icons "homeassistant_icon.svg") (New-IconSvg -Background $navy)

$darkBannerSvg = Join-Path $banner ".github_banner_dark.svg"
$lightBannerSvg = Join-Path $banner ".github_banner_light.svg"
Write-Utf8 $darkBannerSvg (New-BannerSvg -Dark $true)
Write-Utf8 $lightBannerSvg (New-BannerSvg -Dark $false)

function New-BrandBitmap {
    param(
        [int]$Width,
        [int]$Height,
        [bool]$Transparent
    )
    $format = if ($Transparent) {
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
    } else {
        [System.Drawing.Imaging.PixelFormat]::Format24bppRgb
    }
    $bitmap = [System.Drawing.Bitmap]::new($Width, $Height, $format)
    $bitmap.SetResolution(96, 96)
    return $bitmap
}

function Set-Quality {
    param([System.Drawing.Graphics]$Graphics)
    $Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $Graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
    $Graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
}

function Draw-Mark {
    param(
        [System.Drawing.Graphics]$Graphics,
        [float]$X,
        [float]$Y,
        [float]$Size,
        [System.Drawing.Color]$Surface
    )
    $scale = $Size / 512
    $points = @(
        [System.Drawing.PointF]::new($X + 256*$scale, $Y + 58*$scale),
        [System.Drawing.PointF]::new($X + 420*$scale, $Y + 153*$scale),
        [System.Drawing.PointF]::new($X + 420*$scale, $Y + 343*$scale),
        [System.Drawing.PointF]::new($X + 256*$scale, $Y + 438*$scale),
        [System.Drawing.PointF]::new($X + 92*$scale, $Y + 343*$scale),
        [System.Drawing.PointF]::new($X + 92*$scale, $Y + 153*$scale)
    )
    $accent = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($blue), 28*$scale)
    $accent.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
    $Graphics.DrawPolygon($accent, $points)
    $line = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($white), 18*$scale)
    $centres = @(@(256,256),@(165,190),@(347,190),@(347,334),@(165,334))
    foreach ($index in 1..4) {
        $Graphics.DrawLine($line, $X+256*$scale, $Y+256*$scale, $X+$centres[$index][0]*$scale, $Y+$centres[$index][1]*$scale)
    }
    $fill = [System.Drawing.SolidBrush]::new($Surface)
    foreach ($entry in @(@(256,256,48),@(165,190,30),@(347,190,30),@(347,334,30),@(165,334,30))) {
        $radius = $entry[2]*$scale
        $Graphics.FillEllipse($fill, $X+$entry[0]*$scale-$radius, $Y+$entry[1]*$scale-$radius, 2*$radius, 2*$radius)
        $Graphics.DrawEllipse($accent, $X+$entry[0]*$scale-$radius, $Y+$entry[1]*$scale-$radius, 2*$radius, 2*$radius)
    }
    $core = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($white))
    $Graphics.FillEllipse($core, $X+242*$scale, $Y+242*$scale, 28*$scale, 28*$scale)
    $accent.Dispose(); $line.Dispose(); $fill.Dispose(); $core.Dispose()
}

function Save-IconPng {
    param([string]$Path, [int]$Size)
    $bitmap = New-BrandBitmap -Width $Size -Height $Size -Transparent $true
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        Set-Quality $graphics
        $surface = [System.Drawing.ColorTranslator]::FromHtml($navy)
        $graphics.Clear($surface)
        Draw-Mark $graphics 0 0 $Size $surface
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graphics.Dispose(); $bitmap.Dispose()
    }
}

function Save-BannerPng {
    param([string]$Path, [bool]$Dark)
    $bitmap = New-BrandBitmap -Width 1280 -Height 640 -Transparent $false
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        Set-Quality $graphics
        $background = [System.Drawing.ColorTranslator]::FromHtml($(if ($Dark) {$navy} else {"#EDF4F8"}))
        $surface = [System.Drawing.ColorTranslator]::FromHtml($(if ($Dark) {$panel} else {"#FFFFFF"}))
        $text = [System.Drawing.ColorTranslator]::FromHtml($(if ($Dark) {$white} else {$ink}))
        $graphics.Clear($background)
        $panelBrush = [System.Drawing.SolidBrush]::new($surface)
        $graphics.FillRectangle($panelBrush, 98, 92, 1084, 456)
        Draw-Mark $graphics 138 150 290 $surface
        $titleFont = [System.Drawing.Font]::new("Segoe UI", 58, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $subtitleFont = [System.Drawing.Font]::new("Segoe UI", 28, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        $tagFont = [System.Drawing.Font]::new("Segoe UI", 25, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $smallFont = [System.Drawing.Font]::new("Segoe UI", 22, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        $textBrush = [System.Drawing.SolidBrush]::new($text)
        $mutedBrush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($muted))
        $accentBrush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($blue))
        $graphics.DrawString("MeshCore NOC", $titleFont, $textBrush, 500, 180)
        $graphics.DrawString("Network Operations Centre for MeshCore", $subtitleFont, $textBrush, 505, 278)
        $graphics.FillRectangle($accentBrush, 505, 345, 500, 4)
        $bullet = [char]0x2022
        $graphics.DrawString("MONITOR  $bullet  ANALYSE  $bullet  OPERATE", $tagFont, $textBrush, 505, 375)
        $graphics.DrawString("Independent Community Project", $smallFont, $mutedBrush, 505, 445)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
        foreach ($item in ($panelBrush,$titleFont,$subtitleFont,$tagFont,$smallFont,$textBrush,$mutedBrush,$accentBrush)) {$item.Dispose()}
    } finally {
        $graphics.Dispose(); $bitmap.Dispose()
    }
}

function Save-HomeAssistantLogo {
    param(
        [string]$Path,
        [int]$Width,
        [int]$Height,
        [bool]$Dark
    )
    $bitmap = New-BrandBitmap -Width $Width -Height $Height -Transparent $true
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        Set-Quality $graphics
        $surface = [System.Drawing.ColorTranslator]::FromHtml($(if ($Dark) {$navy} else {"#FFFFFF"}))
        $text = [System.Drawing.ColorTranslator]::FromHtml($(if ($Dark) {$white} else {$ink}))
        $graphics.Clear([System.Drawing.Color]::Transparent)
        Draw-Mark $graphics 0 0 $Height $surface
        $titleFont = [System.Drawing.Font]::new("Segoe UI", $Height * 0.42, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $subtitleFont = [System.Drawing.Font]::new("Segoe UI", $Height * 0.15, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        $textBrush = [System.Drawing.SolidBrush]::new($text)
        $mutedBrush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($muted))
        $textX = $Height * 1.08
        $graphics.DrawString("MeshCore NOC", $titleFont, $textBrush, $textX, $Height * 0.12)
        $graphics.DrawString("NETWORK OPERATIONS CENTRE", $subtitleFont, $mutedBrush, $textX + $Height * 0.03, $Height * 0.68)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
        foreach ($item in ($titleFont, $subtitleFont, $textBrush, $mutedBrush)) {$item.Dispose()}
    } finally {
        $graphics.Dispose(); $bitmap.Dispose()
    }
}

Save-IconPng (Join-Path $icons "github_avatar.png") 512
Save-IconPng (Join-Path $icons "homeassistant_icon.png") 256
Save-BannerPng (Join-Path $banner "github_banner_dark.png") $true
Save-BannerPng (Join-Path $banner "github_banner_light.png") $false

foreach ($variant in @(
    @("icon.png", 256),
    @("icon@2x.png", 512),
    @("dark_icon.png", 256),
    @("dark_icon@2x.png", 512)
)) {
    Save-IconPng (Join-Path $homeAssistantBrand $variant[0]) $variant[1]
}
Save-HomeAssistantLogo (Join-Path $homeAssistantBrand "logo.png") 1024 140 $false
Save-HomeAssistantLogo (Join-Path $homeAssistantBrand "logo@2x.png") 2048 280 $false
Save-HomeAssistantLogo (Join-Path $homeAssistantBrand "dark_logo.png") 1024 140 $true
Save-HomeAssistantLogo (Join-Path $homeAssistantBrand "dark_logo@2x.png") 2048 280 $true
Copy-Item -LiteralPath (Join-Path $banner "github_banner_dark.png") `
    -Destination (Join-Path $docsImages "github-social-preview.png") -Force

$faviconBitmap = New-BrandBitmap -Width 64 -Height 64 -Transparent $true
$faviconGraphics = [System.Drawing.Graphics]::FromImage($faviconBitmap)
try {
    Set-Quality $faviconGraphics
    $surface = [System.Drawing.ColorTranslator]::FromHtml($navy)
    $faviconGraphics.Clear($surface)
    Draw-Mark $faviconGraphics 0 0 64 $surface
    $handle = $faviconBitmap.GetHicon()
    $favicon = [System.Drawing.Icon]::FromHandle($handle)
    try {
        $stream = [System.IO.File]::Create((Join-Path $icons "favicon.ico"))
        try {$favicon.Save($stream)} finally {$stream.Dispose()}
    } finally {$favicon.Dispose()}
} finally {
    $faviconGraphics.Dispose(); $faviconBitmap.Dispose()
}

Remove-Item -LiteralPath $darkBannerSvg, $lightBannerSvg
Write-Output "Generated MeshCore NOC branding package."
