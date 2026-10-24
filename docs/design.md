# Overhead: design system

Decided Saturday Oct 24. The product is named **Overhead**. Brand and live map use a warm editorial style (warm
black, off-white, a serif display face, one coral accent); the market page borrows Kalshi's mechanics in our palette,
so it reads as one product. Dark is the default; light mode is supported. Every web surface (Convex map, Spacetime market, landing)
takes its tokens from here. The Jira app uses Atlassian's own UI Kit and is exempt.

## Color tokens

Define once on `:root`, reference by name, never raw hex in components.

| Token | Dark (default) | Light | Use |
|---|---|---|---|
| `--bg` | `#151412` | `#F7F5F1` | Page |
| `--surface` | `#1C1B19` | `#FFFFFF` | Cards |
| `--surface-2` | `#252421` | `#EEEBE5` | Raised rows, inputs |
| `--text` | `#F7F5F1` | `#151412` | Body text |
| `--text-muted` | `#A29D94` | `#6B665E` | Secondary text, captions |
| `--hairline` | `rgba(247,245,241,0.12)` | `rgba(21,20,18,0.10)` | Dividers (never on rounded elements) |
| `--accent` | `#E96457` | `#C94F3B` | Brand only: the name, primary buttons, focus ring. Never in data |
| `--yes` / `--free` | `#28CC95` | `#178A63` | Market Yes, free parking spaces, good state |
| `--no` / `--critical` | `#FF454D` | `#C92A33` | Market No, critical alerts |
| `--warning` | `#FDB414` | `#A86F00` | Low-confidence frames, warnings |
| `--taken` | `#5C5852` | `#B8B2A8` | Occupied spaces (muted, not red, so red keeps meaning "danger") |

Contrast: body text on `--bg` and `--surface` must pass WCAG AA in both themes.

## Type

| Role | Face | Notes |
|---|---|---|
| Display | `Charter, "Bitstream Charter", "Charis SIL", Georgia, serif` (Charis SIL from Google Fonts as the web fallback) | The name "Overhead.", page titles, big numbers on the landing. Bold for the name, regular for headlines. Used sparingly |
| UI | Manrope (Google Fonts), 400/500/600/700 | Everything interactive and all running text in the apps |
| Data | Manrope with `font-variant-numeric: tabular-nums` | Counts, prices, odds, volumes |
| Caption | IBM Plex Mono 400/500 | Timestamps, frame ids, "updated 4 s ago", tiny labels |

Scale (px): 12, 14, 16, 20, 24, 32, 48, and 96+ for the landing name. Running text near 65 characters wide;
`text-wrap: balance` on headings.

## Shape, space, motion

- Radii: pills `999px` (buttons, odds), cards `16px`, small chips `8px`. Never a visible colored border on a rounded
  element: use fill, shadow, or an inset ring (`box-shadow: inset 0 0 0 1.5px var(--yes)`) for Kalshi-style odds pills.
- Spacing scale: 4, 8, 12, 16, 24, 32, 48. Layout uses grid/flex `gap`, not per-element margins. 16 px phone gutters.
- Shadows: one soft elevation `0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.25)` (dark), lighter in light mode.
- Motion: one moment only, spaces fading free/taken as frames arrive (200 ms). Odds bars ease 300 ms. Respect
  `prefers-reduced-motion`.
- Icons: Phosphor (`@phosphor-icons/react`), regular weight. No emoji.

## Surfaces

**Live (the thesis).** The aerial frame large at the top, with an SVG overlay: free spaces glow `--free`, taken spaces
`--taken`, zones outlined faintly. Under it, a counts strip (cars, people on beach, people in water, frame confidence,
"updated 3 s ago" in Plex Mono). Low confidence is shown, not hidden: a `--warning` chip "Frame unreliable: tilted 18
degrees". Then lot cards: name, occupancy bar, current price large in tabular Manrope, sparkline, and "Why did the
price change?" expanding the decision log.

**Markets (Kalshi mechanics).** A card per market:
- category eyebrow in caps (e.g. "PARKING · LOT A"), a Plex Mono close time;
- the question as a heading ("40 or more cars in Lot A at 5:00 PM?");
- two rows, Yes and No: label, a thin progress line under it in `--yes` / `--no`, "pays 1.6x", and the probability in
  an inset-ring pill on the right;
- volume in play credits and a "Why" line (where Kalshi shows News): the market agent's one-sentence reasoning, or the
  settlement explanation with the observed value and frame count once settled.
Buying opens a bottom sheet: Yes/No toggle, amount, cost and payout computed live, one primary button.

**Alerts.** Each alert: severity chip, the Claude-written text, its uncertainty line, the frame thumbnail, and two
buttons, Confirm (accent) and Dismiss. Confirmed alerts go to the patrol's Jira.

**Navigation.** Under 768 px: bottom tab bar (Live, Markets, Alerts). From 768 px up: the same three as a top bar with
"Overhead." in Charter on the left. Every app switches at the same 768 px breakpoint (Tailwind `md`).

**Landing (if time).** "Overhead." huge in bold Charter over a dimmed live frame, one sentence ("A camera that stays
over one place for hours, so a beach, a parking lot and a market can see what's happening now."), and two pills:
Live view, Markets.

## Writing

Name things the way users say them (spaces, prices, alerts, markets). Buttons say what happens ("Buy Yes for 120",
"Confirm alert"). Empty states say what to do next. No em dashes.
