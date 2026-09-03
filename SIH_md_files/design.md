# design.md — Visual Design System

**Project:** Marg (SIH26127)
**Version:** 1.0
**Applies to:** `frontend/` only
**Companion docs:** `appflow.md`, `rules.md`

---

## 1. What This Interface Is

A traffic control-room console, used on a desk monitor during a shift, showing several live camera feeds and a city map at once. The person using it is scanning for something, under time pressure, with a supervisor nearby. It is not a marketing site, not a dashboard product, and not a consumer app.

That determines every decision below:

- **Dark by default.** Control rooms are dimly lit and the screen sits beside live video. A light interface next to dark video feeds forces constant pupil adjustment across an eight-hour shift.
- **Dense.** Information per screen matters more than breathing room. Generous whitespace is correct for a landing page and wrong here — it means fewer camera tiles and less of the timeline visible.
- **Quiet.** The video feeds and the map carry the colour. If the interface competes with them, the operator's eye has nowhere to rest. Chrome is neutral; colour is reserved for meaning.
- **Evidential.** Every number is a claim someone may have to defend. Data is typeset to be read precisely, not to look impressive.

---

## 2. Aesthetic Direction

**Concept: Registration.**

The palette is taken from the visual system of Indian vehicles and roads — the surfaces this software actually looks at. Number plates in India carry a fixed colour code: black on white for private vehicles, black on yellow for commercial, white on green for electric. Highway direction signage is white on green; warnings are black on amber. This is a real, legible, already-standardised colour language belonging to the exact domain the product operates in.

Using it means the accent colour is not an arbitrary brand choice. Green means confirmed and is also the primary interactive colour, because green already means "go" and "verified" to anyone who has driven on an Indian road. Amber means uncertain, because it already does. Oxide red means rejected. An operator reads the interface's colour before reading its text, and reads it correctly on the first try.

**Three principles:**

1. **Colour carries state, never decoration.** If an element is coloured, the colour means something a user can name. Neutral is the default for everything else.
2. **The evidence panel is where boldness is spent.** It is the screen that makes the system trustworthy, so it gets the largest images, the clearest typography, and the most deliberate layout. Everything around it stays plain.
3. **Absence is shown, not hidden.** No plate read, no crop available, no edges configured — each has a designed state. A blank space communicates a bug; a stated absence communicates a fact.

---

## 3. Prohibited — Strict

These are hard rules. A pull request violating any of them is rejected regardless of how it looks.

**Colour**
- No purple, violet, indigo, or magenta anywhere in the interface. Not as an accent, not in a chart scale, not in a hover state.
- No gradients as decoration. The only permitted gradient is a functional one: a linear fade over a camera tile's lower edge so overlay text stays legible against arbitrary video.
- No neon or fluorescent values. Nothing above roughly 70% saturation.
- No glow effects, no coloured drop shadows, no `box-shadow` used to make an element appear lit.
- **No terracotta or warm-clay accent** near `#D97757`. It is currently the single most recognisable signature of AI-generated design and it will be read as one.
- No cream or warm off-white background near `#F4F1EA`, for the same reason.

**Surfaces**
- No glassmorphism. No `backdrop-filter: blur()` on panels, cards, or navigation.
- No translucent frosted overlays. Modal scrims are flat, opaque black at fixed alpha.
- Exactly one shadow token exists in the system, used only for elements that float above the page (dialogs, dropdowns, toasts). Cards, panels, and table rows are separated by borders, not shadows.

**Type**
- No decorative, rounded, geometric-display, or "friendly tech" typefaces.
- No all-caps labels, including tracked-out eyebrow labels above headings. Sentence case throughout.
- No single word in a heading given a different colour or weight for emphasis.
- No monospace for *labels*. Monospace is reserved for data values — plates, IDs, timestamps, scores — where character alignment is functional. This distinction is enforced in review.

**Content**
- No emojis. Not in the UI, not in toasts, not in empty states, not in commit messages, not in code comments.
- No sparkle, robot, brain, rocket, or lightning iconography. Icons are literal: camera, map pin, clock, check, alert triangle.
- No arrow appended to button or link text ("View details →"). The button already indicates it is a button.
- No meta strings joined with middle dots ("Camera 3 · 10:14 · Confirmed"). Use table cells or explicit labels.

**Motion**
- No entrance animation on page or section load. Content appears.
- No hover transition on every card and row. Hover feedback is an instant background change, not a transform or a fade.
- Motion is permitted only where it shows a change the user caused: a dialog opening, a panel expanding, a trajectory the user pressed play on, a tile border flashing when a new sighting arrives at that camera.
- All motion respects `prefers-reduced-motion: reduce`, which disables trajectory playback animation entirely and replaces it with instant state changes.

---

## 4. Colour Tokens

Defined once in `frontend/src/styles/tokens.css` as CSS custom properties and consumed through Tailwind's theme. No component declares a raw hex value.

### Surfaces

| Token | Value | Use |
|---|---|---|
| `--surface-base` | `#0E1012` | Application background |
| `--surface-raised` | `#171A1D` | Panels, sidebar, table headers |
| `--surface-overlay` | `#1F2327` | Dialogs, dropdowns, popovers, toasts |
| `--surface-sunken` | `#0A0C0D` | Video tile backgrounds, code and log blocks |
| `--surface-hover` | `#22262A` | Row and control hover |
| `--surface-active` | `#2A2F34` | Pressed state |

### Borders

| Token | Value | Use |
|---|---|---|
| `--border-subtle` | `#24282C` | Table row dividers, internal separators |
| `--border-default` | `#31363B` | Panel edges, input borders, card outlines |
| `--border-strong` | `#454C53` | Focused inputs, active tile outline |

### Text

| Token | Value | On base | Use |
|---|---|---|---|
| `--text-primary` | `#E7EAEC` | 15.8:1 | Body, values, headings |
| `--text-secondary` | `#9AA2A9` | 7.2:1 | Labels, column headers, metadata |
| `--text-muted` | `#6C747B` | 4.1:1 | Disabled, placeholder — **never for body text** |
| `--text-inverse` | `#0E1012` | — | Text on filled accent or amber |

`--text-muted` is below the 4.5:1 body threshold. It is permitted only for text that is decorative or genuinely disabled, where WCAG exempts it. Every other use is a bug.

### Accent — sign green

| Token | Value | Use |
|---|---|---|
| `--accent` | `#2E7D5B` | Primary buttons, active nav, links |
| `--accent-hover` | `#379269` | Hover |
| `--accent-active` | `#256647` | Pressed |
| `--accent-tint` | `rgba(46,125,91,0.14)` | Selected row background, badge fill |
| `--accent-text` | `#5FBF8F` | Accent-coloured text on dark — 6.9:1 |

`--accent` at `#2E7D5B` gives 3.4:1 against `--surface-base`, which satisfies the 3:1 non-text requirement for a filled button. Accent-coloured *text* uses `--accent-text`, which is lightened to clear 4.5:1. Two tokens exist for this reason; do not substitute one for the other.

### Status

Every status colour is paired with a text label and an icon. Colour never carries meaning alone (NFR-A3).

| Token | Value | Meaning | Icon |
|---|---|---|---|
| `--status-confirmed` | `#2E7D5B` | Operator-confirmed, or plate-exact | check |
| `--status-probable` | `#6E7A85` | Auto-matched above threshold | circle-dot |
| `--status-ambiguous` | `#C9902F` | Within ambiguity margin, needs review | alert-triangle |
| `--status-rejected` | `#A6483A` | Failed the gate, or operator-rejected | x-circle |
| `--status-offline` | `#4A5157` | Worker not running | power-off |

Tints for badge backgrounds are the same hues at 0.14 alpha.

`#A6483A` is a dark oxide red — the colour of rusted metal and old road paint, not a warm clay. It sits well below the AI-tell terracotta in both lightness and saturation, which is deliberate.

### Trajectory colours — map only

Consecutive vehicles on the map need distinguishable colours. This scale is muted on purpose: saturated lines over a basemap are illegible and look like a heat map.

| Index | Value |
|---|---|
| 1 | `#4E8FBF` steel blue |
| 2 | `#C9902F` amber |
| 3 | `#5A9E7A` sage |
| 4 | `#B0673F` burnt orange |
| 5 | `#7C8BA1` slate |
| 6 | `#A6483A` oxide |

Assigned deterministically by hashing the vehicle UUID, so the same vehicle keeps its colour across renders and across page reloads. A colour that changes on refresh is worse than no colour.

None of these are purple. If a seventh is ever needed, the scale cycles rather than extending into violet.

### Detection overlay — on video

Drawn on the camera tile canvas over live frames.

| Element | Value | Notes |
|---|---|---|
| Bounding box | `#5FBF8F` | 2 px, no fill |
| Box, plate detected | `#C9902F` | 2 px, marks a plate-read candidate |
| Track ID label | `#E7EAEC` on `rgba(14,16,18,0.82)` | Solid backing plate, never translucent blur |
| Plate region | `#E7EAEC` | 1 px dashed |

---

## 5. Typography

### Families

| Role | Family | Weights | Why |
|---|---|---|---|
| Interface | **Inter** (variable) | 400, 500, 600 | Chosen for legibility at 12–13 px in dense tables, and for true tabular numerals. In this interface most type is small data in columns; a display-oriented face would be the wrong tool. |
| Data | **JetBrains Mono** | 400, 500 | Plates, UUIDs, timestamps, scores. Fixed advance width means digits align down a column and a plate's character count is visible at a glance. |

**Both fonts are self-hosted** in `frontend/public/fonts/` as woff2 and declared with `@font-face`. No Google Fonts link, no CDN. Requirement D-6 says the demo runs offline, and a font that fails to load takes the layout with it.

`font-feature-settings: "tnum" 1, "cv05" 1;` is set on Inter globally. Tabular numerals stop numbers jittering as they update in the live feed; `cv05` gives the lowercase l a tail, which matters when plate-adjacent text mixes `l`, `1`, and `I`.

### Scale

Small, because the content is dense. The base is 14 px, not 16 px — this is a data application, not a reading surface.

| Token | Size / line-height | Weight | Use |
|---|---|---|---|
| `--text-xs` | 11px / 16px | 500 | Table column headers, badge text, axis labels |
| `--text-sm` | 12px / 18px | 400 | Metadata, timestamps, helper text |
| `--text-base` | 14px / 21px | 400 | Body, table cells, form inputs |
| `--text-md` | 16px / 24px | 500 | Panel headings, dialog titles |
| `--text-lg` | 20px / 28px | 600 | Page titles |
| `--text-xl` | 28px / 36px | 600 | Login screen, single-metric displays |
| `--text-data` | 13px / 18px | 500 | Mono: plates, IDs, scores |
| `--text-data-lg` | 18px / 24px | 500 | Mono: the primary plate in the evidence panel |

Six sizes and one data pair. Anything not on this scale does not get used.

### Rules

- Sentence case for every heading, label, and button. No title case, no all caps.
- Body and prose lines cap at 72 characters (`max-width: 65ch`). Table cells are exempt.
- Letter-spacing is left at the font's default everywhere. No tracked-out labels.
- Emphasis is weight (500 or 600) or the secondary text colour. Never italics — italic Inter at 12 px is hard to read on a dark background.
- Numbers that will be compared — scores, confidences, elapsed times — are always mono and always right-aligned.

---

## 6. Spacing and Layout

### Scale

4 px base. Only these values.

| Token | Value | Typical use |
|---|---|---|
| `--space-1` | 4px | Icon-to-label gap |
| `--space-2` | 8px | Inside badges and compact buttons |
| `--space-3` | 12px | Table cell padding, form field gaps |
| `--space-4` | 16px | Panel padding, section gaps |
| `--space-6` | 24px | Major section separation |
| `--space-8` | 32px | Page margins |
| `--space-12` | 48px | Empty-state vertical centring |

### Radii

Small. Large radii read as consumer software; this is an instrument.

| Token | Value | Use |
|---|---|---|
| `--radius-sm` | 2px | Badges, tags, small indicators |
| `--radius-md` | 4px | Buttons, inputs, cards, panels, video tiles |
| `--radius-lg` | 6px | Dialogs and popovers only |

No `border-radius: 9999px`. No pill buttons.

### Elevation

One shadow token, and it is only for elements genuinely floating above the page.

```css
--shadow-overlay: 0 8px 24px rgba(0, 0, 0, 0.48), 0 2px 6px rgba(0, 0, 0, 0.32);
```

Panels, cards, and rows use borders. A card with a shadow on a dark background is a card with a smudge under it.

### Application shell

```
┌──────────────────────────────────────────────────────────────┐
│ TopBar 48px    Marg    [live ●]   [search]        [user ▾]   │
├────────┬─────────────────────────────────────────────────────┤
│ Side   │                                                      │
│ 200px  │  Page content                                        │
│        │                                                      │
│ Live   │                                                      │
│ Search │                                                      │
│ Review │                                                      │
│ Cameras│                                                      │
│        │                                                      │
└────────┴─────────────────────────────────────────────────────┘
```

Sidebar collapses to 56 px icons below 1280 px. Below 1024 px it becomes a drawer. The application targets 1440 px and above; a control-room console does not need a phone layout, and pretending otherwise wastes days. Below 768 px, render a message stating the minimum supported width rather than a broken layout.

### Live wall grid

Camera tiles are 16:9 and fill the available width:

| Camera count | Grid |
|---|---|
| 1–2 | 2 columns |
| 3–4 | 2 columns |
| 5–9 | 3 columns |
| 10+ | 4 columns |

The event feed is a fixed 360 px right column, scrollable independently.

### Trajectory detail

```
┌───────────────────────────────────┬──────────────────────┐
│                                   │  Evidence            │
│   Map                             │                      │
│   (fills, min 520px tall)         │  ┌────────────────┐  │
│                                   │  │  best shot     │  │
│                                   │  │                │  │
├───────────────────────────────────┤  └────────────────┘  │
│  ▶ ❙❙  1× 2× 4×  ├──────●──────┤  │  plate crop        │
├───────────────────────────────────┤  BR01AB1234  0.87    │
│  Timeline                         │                      │
│  ① CAM-01  10:14:02   plate       │  Match explanation   │
│  ② CAM-03  10:20:54   visual      │  visual      0.87    │
│  ③ CAM-04  10:28:11   visual  ⚠   │  plate         —     │
│                                   │  temporal    0.91    │
│                                   │  ─────────────────   │
│                                   │  fused       0.88    │
│                                   │                      │
│                                   │  Also considered     │
│                                   │  #A47F  0.84         │
│                                   │  rejected: too fast  │
│                                   │                      │
│                                   │  [Confirm] [Reject]  │
└───────────────────────────────────┴──────────────────────┘
                                       380px fixed
```

Evidence is a fixed 380 px column. The map takes the remaining width. The evidence column never collapses — it is the reason the screen exists, and hiding it behind a toggle at narrow widths would hide the system's justification.

The timeline numbers its entries because the content genuinely is a chronological sequence. This is the only place numbered markers appear.

---

## 7. Component Rules

### Buttons

| Variant | Fill | Text | Border | Use |
|---|---|---|---|---|
| Primary | `--accent` | `--text-inverse` | none | One per screen region. Confirm, save, sign in. |
| Secondary | transparent | `--text-primary` | `--border-default` | Cancel, secondary actions |
| Ghost | transparent | `--text-secondary` | none | Toolbar and icon actions |
| Danger | transparent | `--status-rejected` | `--status-rejected` | Reject, delete, reset |

Height 32 px default, 28 px compact, 40 px on the login screen. Padding `--space-3` horizontal. Label is a verb naming exactly what happens, and the same verb is used in the resulting toast: a button reading "Confirm link" produces "Link confirmed."

Danger buttons are outlined, not filled. A filled red button draws the eye to the destructive option on every screen it appears on.

### Inputs

Background `--surface-sunken`, border `--border-default`, radius `--radius-md`, height 32 px. Focus swaps the border to `--border-strong` and adds `box-shadow: 0 0 0 2px var(--accent-tint)`. No glow, no colour shift on the fill.

Plate inputs use JetBrains Mono, uppercase-transform as typed, and show a structural-validity indicator that never blocks submission. Non-standard plates are common in the real world and must remain searchable.

### Badges

Height 20 px, radius `--radius-sm`, `--text-xs` at weight 500, tinted background at 0.14 alpha, solid text in the status hue, 12 px icon on the left. Always icon plus text; a bare colour dot is not a badge.

### Tables

Header row `--surface-raised`, `--text-xs`, `--text-secondary`, sentence case, sticky. Rows 36 px, divided by `--border-subtle`. Hover `--surface-hover`. Selected `--accent-tint` with a 2 px left border in `--accent`.

No zebra striping. Alternating row colours fight with status tints and add a second visual rhythm competing with the one that carries meaning.

Numeric columns right-aligned and mono. Plate columns mono. Everything else left-aligned in Inter.

### Camera tiles

Video fills a 16:9 frame with `--surface-sunken` behind it and a `--border-default` outline. The camera name sits bottom-left over a 48 px linear fade from `rgba(14,16,18,0.85)` to transparent — the one permitted gradient, and it exists because video content behind text is unpredictable.

A new sighting flashes the tile border to `--accent` for 600 ms, then eases back. This is the only ambient motion in the interface, and it exists because it directs attention to where something happened, which is the operator's core task.

Offline tiles render the last frame at 35% opacity with a centred status badge.

### Map

Basemap tiles are served from `frontend/public/tiles/`. Leaflet's default marker icons are replaced with SVG pins in the token palette — the default blue-and-white pin is a strong visual signature of a Leaflet demo.

Camera markers: 24 px pin, `--surface-overlay` fill, `--border-strong` outline, camera icon inside. Active camera swaps the fill to `--accent`. Sequence numbers on a trajectory are rendered inside the pin.

Polylines: 3 px confirmed, 2 px probable, 2 px dashed `6 4` ambiguous. Colour comes from the trajectory scale, keyed to the vehicle. A 1 px `rgba(14,16,18,0.6)` casing sits under every line so it stays legible over light and dark basemap regions.

### Empty states

Centred within the panel, `--space-12` vertical padding, maximum 420 px wide. One 24 px icon in `--text-muted`. One `--text-md` line stating the situation. One `--text-sm` line in `--text-secondary` explaining what to do. One primary button if there is an action the current role can take.

No illustrations. No apologies. State the fact, offer the next step.

### Toasts

Bottom-right, `--surface-overlay`, `--shadow-overlay`, `--radius-lg`, 320 px wide. Auto-dismiss after 5 s except for errors, which persist until dismissed. A 3 px left border in the relevant status colour. Maximum three stacked; older ones drop.

Error toasts include the `request_id` in mono with a copy button. That ID is what lets a teammate find the matching server log line in ten seconds instead of ten minutes.

---

## 8. Accessibility Requirements

Non-negotiable, verified in Phase 4 (`implementationplan.md`).

- **Contrast.** Body text ≥ 4.5:1, large text and UI boundaries ≥ 3:1. Every token pair in this document has been chosen against `--surface-base` and is listed with its ratio where it is close to the line.
- **Focus.** Every interactive element shows `outline: 2px solid var(--accent-text); outline-offset: 2px` on `:focus-visible`. Focus outlines are never removed. If a custom control suppresses the default, it draws its own.
- **Keyboard.** Full operation without a mouse. Tab order follows visual order. Dialogs trap focus while open and return it to the trigger on close. Escape closes any overlay.
- **Colour independence.** Every status has an icon and a text label. The trajectory is available as a chronological table via a toggle on the detail page, so route information does not require reading a colour-coded map.
- **Motion.** `prefers-reduced-motion: reduce` disables trajectory playback animation, the tile flash, and all transitions. Playback controls are replaced by a step-through control that jumps between sightings.
- **Semantics.** Native elements first. `<button>` for actions, `<a>` for navigation, `<table>` for tabular data. ARIA is added only where a native element cannot express the pattern.
- **Live regions.** The event feed is `aria-live="polite"` with `aria-relevant="additions"`, so a screen reader announces new sightings without re-reading the list.
- **Images.** Every crop has alt text naming what it shows: "Vehicle sighting at Camera 3, 10:14:02".

---

## 9. Self-Critique Checklist

Run before merging any UI work.

- [ ] No purple, violet, indigo, or magenta in any file.
- [ ] No gradient except the camera-tile text fade.
- [ ] No `backdrop-filter` anywhere.
- [ ] No shadow on anything that is not a dialog, dropdown, or toast.
- [ ] No emoji in any source file, string, or comment.
- [ ] No all-caps or tracked-out label.
- [ ] No monospace used for a label rather than a data value.
- [ ] No arrow character appended to button or link text.
- [ ] No entrance animation on load; no hover transform on cards or rows.
- [ ] Every raw hex replaced by a token.
- [ ] Every status colour paired with an icon and a text label.
- [ ] Every interactive element has a visible focus ring.
- [ ] `prefers-reduced-motion` honoured.
- [ ] Every empty state states the situation and offers the next action.
- [ ] Every button label is a verb matching its resulting toast.

Then, per the frontend-design skill: look at the screen and remove one thing. Density is the goal, but density earned by cutting is different from density caused by adding.
