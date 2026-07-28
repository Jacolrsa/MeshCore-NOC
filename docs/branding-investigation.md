# Home Assistant local-brand investigation

## Finding

Home Assistant Core 2026.3 and newer supports local brand images for any
discovered custom integration. Installation through HACS is not required.
There is no manifest branding key and no extra metadata to add.

Core discovers `brand` as a top-level item beside the custom integration's
`manifest.json`. Its Brands system integration checks the local directory
before its disk/CDN cache. The frontend obtains a temporary token through the
`brands/access_token` WebSocket command and requests:

```text
/api/brands/integration/meshcore_noc/icon.png?token=...
/api/brands/integration/meshcore_noc/logo.png?token=...
```

The repository path, domain, filenames, PNG encoding, icon dimensions, alpha
channel, and 2× scaling match that implementation. The current 1024×140 and
2048×280 logos meet the documented minimum and use only the independent
MeshCore NOC network-node identity. Core does not reject images by dimension,
so an invalid size alone does not explain an `icon.png` placeholder.

## Why “icon not available” appears

The Brands endpoint returns a generic placeholder when neither a discovered
local file nor a CDN image is available. Therefore the message is evidence
that the image was not served through the local-brand path, not evidence that
the PNG failed to render.

For MeshCore NOC, a valid local `icon.png` will be returned when all of these
are true:

- Core and frontend are 2026.3 or newer.
- The final path is
  `/config/custom_components/meshcore_noc/brand/icon.png`.
- Core was fully restarted after the `brand` directory was added.
- Home Assistant is not running in safe or recovery mode.
- The request uses a valid authenticated session or Brands token.

Before 2026.3, Core has no local Brands API implementation for custom
integrations. The frontend uses the public Brands CDN, where `meshcore_noc`
has no published image, so the placeholder is expected and repository-local
files cannot fix it.

## Definitive live test

Create a temporary long-lived Home Assistant access token in the user profile.
Do not paste it into an issue or commit it. From a trusted machine run:

```sh
export HA_URL="http://homeassistant.local:8123"
export HA_TOKEN="temporary-long-lived-token"

curl --fail-with-body --output meshcore-noc-icon.png \
  --header "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/brands/integration/meshcore_noc/icon.png?placeholder=no"

file meshcore-noc-icon.png
```

Interpret the result:

- `200` with a 256×256 PNG proves Core discovered and served the local brand.
  Any remaining UI problem is frontend version/state or browser/app cache.
- `404` on Core 2026.3+ proves Core did not discover the local brand directory.
  Recheck the exact path, safe mode, and perform a full restart.
- `404` because the route or `brands/access_token` command is absent proves
  that Core does not include 2026.3 local-brand support.
- `401` or `403` means authentication failed; it says nothing about the image.

The same test can use `logo.png`, `dark_icon.png`, or another supported
filename. In browser developer tools, filter the Network panel for
`/api/brands/integration/meshcore_noc/` and inspect the request status.

Remove the temporary access token after testing. No permanent debug logging is
needed or added by MeshCore NOC.

## Cache behavior

Core checks discovered local assets before its Brands disk/CDN cache, so
deleting the Brands cache is not a valid fix for a correctly discovered local
file. A full Home Assistant restart is required when the directory is first
added because custom-integration metadata is cached in memory. After the API
test returns the correct PNG, reload the frontend, hard-refresh the browser,
or clear the companion-app frontend cache.
