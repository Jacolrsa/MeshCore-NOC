# MH-101 — MeshCore NOC Design System

| Field | Value |
| --- | --- |
| Status | Active design guidance |
| Revision | 1.0 |
| Baseline | Alpha5.2 dashboard palette and Home Assistant theming |

## Design principles

1. **Operational first.** State and action outrank decoration.
2. **Consistent semantics.** A status has one meaning across headers, KPIs,
   cards, alerts, and charts.
3. **Honest uncertainty.** Unknown is not healthy, offline, or zero.
4. **Readable at distance.** Use concise labels, strong hierarchy, and
   sufficient contrast.
5. **Native context.** Integrate with Home Assistant’s theme and interaction
   patterns while maintaining a recognisable NOC identity.
6. **Restrained motion.** Movement may confirm change, never demand attention
   continuously.

## Semantic tokens

Alpha5.2 currently defines these CSS variables in the dashboard card:

```css
--noc-background: #101418;
--noc-panel: #1a2128;
--noc-panel-alt: #202832;
--noc-border: rgba(255, 255, 255, 0.10);
--noc-text-primary: #f3f6f8;
--noc-text-secondary: #aab5bf;
--noc-healthy: #36c96b;
--noc-warning: #f6c344;
--noc-degraded: #ff8b3d;
--noc-critical: #e53935;
--noc-unknown: #7b8791;
--noc-accent: #4da3ff;
--noc-radius: 12px;
```

These values document the existing dashboard; they are not a requirement to
override Home Assistant globally. New UI surfaces should expose semantic
tokens and map them to the active Home Assistant theme where practical.

## Status colour semantics

| State | Meaning | Current token |
| --- | --- | --- |
| Healthy | Operating normally; telemetry is current | `--noc-healthy` |
| Warning | Attention may soon be required | `--noc-warning` |
| Degraded | Service or telemetry quality is materially reduced | `--noc-degraded` |
| Critical | Offline, failed, or requires prompt action | `--noc-critical` |
| Unknown | Insufficient or unavailable evidence | `--noc-unknown` |

Never use green merely because an error is absent. Do not represent Unknown as
healthy. Always pair status colour with text, an icon, or a distinct indicator.

## Typography hierarchy

- **Mission title:** largest page text; compact line height.
- **Network state / KPI value:** bold, high contrast, readable at distance.
- **Card title:** concise, one line where possible.
- **Metric label:** smaller uppercase or semibold text with modest tracking.
- **Supporting metadata:** secondary colour; never below a comfortably readable
  size on the target display.

Use the Home Assistant body font or `system-ui`; do not load external fonts.
Numeric telemetry should use stable alignment where comparisons matter.

## Spacing scale

Use a four-pixel base rhythm:

| Token | Size | Typical use |
| --- | ---: | --- |
| `space-1` | 4 px | tight icon or badge separation |
| `space-2` | 8 px | compact grid gaps |
| `space-3` | 12 px | card padding |
| `space-4` | 16 px | section padding |
| `space-5` | 24 px | major separation |
| `space-6` | 32 px | exceptional page-level spacing |

Alpha5.2 uses compact responsive gaps and padding to keep the operations view
compact. Avoid large decorative whitespace that pushes active conditions below
the fold.

## Border radius

- Standard cards and panels: `--noc-radius`, currently 12 px.
- Status badges and battery tracks: pill radius (`999px`).
- Nested elements should not have a larger radius than their parent.
- Do not mix many radius styles in one view.

## Card hierarchy

1. **Mission panel:** page identity and overall condition.
2. **KPI card:** one fleet-level fact.
3. **Managed-device card:** one device’s current operational state.
4. **Alert card:** one actionable abnormal condition.
5. **Historical card:** supporting Level 3 context.

Use border, background tone, and status edge treatment to distinguish levels.
Avoid applying heavy shadows to every nested element.

## Icon usage

- Use Material Design Icons already available in Home Assistant.
- Use one clear icon per label where it improves scanning.
- Keep the same icon for the same concept.
- Do not use icons as the sole status label.
- Do not use or redraw Home Assistant or official MeshCore logos as interface
  glyphs. Use the independent MeshCore NOC network-node mark where branding is
  required.
- Decorative icons must not compete with alert indicators.

## Battery-bar behaviour

- Clamp display width to 0–100%.
- Show the numeric percentage next to the bar.
- Use Unknown styling and an empty bar when the value is unavailable.
- Transition fill width subtly when a valid value changes.
- Do not infer charging state; Alpha5.2 does not implement charging detection.
- Dashboard alerting currently treats battery below 15% as active. Card colour
  currently becomes critical below 15% and warning below 30%.

## Status indicators

A status indicator should contain at least two of:

- semantic colour;
- text label;
- icon;
- dot, border, or shape.

The current dashboard uses a coloured dot in the overall state, labelled
badges, and a coloured left border on managed-device cards.

## Alert severity

| Severity | Presentation | Expected operator response |
| --- | --- | --- |
| Healthy | Low-emphasis positive state | None |
| Warning | Yellow, labelled | Observe or schedule attention |
| Degraded | Orange, labelled | Investigate |
| Critical | Red, prominent, labelled | Act promptly |
| Unknown | Grey, labelled | Verify source data |

Alpha5.2 dashboard alerts are a binary active list derived from device state.
Acknowledgement, escalation, and persistent severity records are planned
capabilities, not current behaviour.

## Chart styling

- Use calibrated units and meaningful titles.
- Keep grid lines and axes secondary to the data.
- Use the same semantic colours as current-state views where status is encoded.
- Avoid more simultaneous series than can be distinguished at TV distance.
- State the time range in the chart title.
- Provide a clear Recorder-disabled or no-data explanation.
- Never smooth a line in a way that obscures real telemetry changes.

## Animation rules

Permitted:

- subtle status heartbeat;
- battery fill transitions;
- graph redraw transitions.

Not permitted:

- flashing panels;
- bouncing cards;
- distracting decorative movement;
- motion that is the only indication of state.

Animation should be short, stop at rest, and be disabled or reduced when the
user requests reduced motion. Alpha5.2 does not rely on animation.

## Dark-theme rules

The NOC surface is dark-first. Maintain:

- clear separation between background, panel, and alternate panel;
- high-contrast primary text;
- quieter but readable secondary text;
- restrained borders;
- sufficient contrast for every semantic status; and
- compatibility with Home Assistant dialogs and controls.

Do not hard-code dark text onto semantic status colours without checking
contrast. Theme mappings must retain semantic meaning when users customise
Home Assistant colours.

## Accessibility and contrast

- Target WCAG 2.1 AA for text and essential graphics.
- Test status pairs against both panel backgrounds.
- Preserve labels when colour perception is reduced.
- Do not communicate battery condition only through fill colour.
- Keep visible focus rings.
- Use semantic headings and logical DOM order.
- Ensure text remains readable at 200% zoom.

## Responsive behaviour

- Preserve information order when columns collapse.
- Keep overall state before supporting KPIs.
- Avoid horizontal scrolling.
- Prefer fewer columns over unreadably narrow cards.
- On mobile, allow vertical scrolling and keep alert labels intact.
- Do not hide critical status merely to fit the target canvas.

## Correct usage

- A red left edge, alert icon, and “Offline” label identify a critical device.
- An unavailable battery shows “Unknown” or an em dash and a grey indicator.
- A KPI uses one concise label and one dominant value.
- A history graph title includes both metric and time range.
- A healthy empty-alert panel says “No active alerts” with low emphasis.

## Incorrect usage

- Showing a missing battery as `0%`.
- Using green for an entity whose source state is unknown.
- Making a whole panel flash to show a stale reading.
- Using different colours for “Critical” on the header and device card.
- Hiding a status behind hover or a future popup.
- Loading a decorative web font or external image dependency.
- Adding gradients, glow, or motion that reduces operational clarity.
