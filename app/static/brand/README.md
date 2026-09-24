# Brand assets

Logos and fonts used by the chat page, copied unmodified from their owners'
official sources.

The **logos are trademarks** of CData Software and Render and are **not**
covered by this repository's MIT license. Use them only to refer to those
companies, per their brand guidelines. The **fonts** are licensed separately
under the SIL Open Font License; see `fonts/*-OFL.txt`.

| File | Source |
| --- | --- |
| `cdata-logotype-white.svg` | CData brand kit (Feb 2026); for the navy header |
| `cdata-logotype-depth.svg` | CData brand kit; logotype in Depth, for light backgrounds |
| `cdata-logotype-clarity.svg` | CData brand kit; logotype in Clarity, for dark backgrounds |
| `cdata-favicon.svg` | CData brand kit; the tab icon |
| `render-mark.svg` | Render, `https://render.com/brand/render_1105076560.svg` |
| `fonts/DMSans-Variable.ttf`, `fonts/DMMono-Regular.ttf` | CData brand kit; DM Sans and DM Mono, SIL OFL 1.1 |

CData's display typeface, Grafier, is commercially licensed and deliberately
not included.

## How the page applies the brand

Colours are from the CData Brand Guidelines (Feb 2026):

| Name | Hex | Used for |
| --- | --- | --- |
| Clarity | `#F1EEE9` | Page background (light); text (dark) |
| Depth | `#15151C` | Text (light); page background (dark) |
| Agility | `#FFE500` | Accent only: Send button (with Depth text), header rule, focus rings |
| Resolve | `#002660` | Header, your messages (white text), links |
| Balance | `#B5B9BC` | Secondary text on the navy header |

Following the kit's rules: yellow is never used for text or with white;
navy fills take white text; small secondary text is Gray 8 `#5E5D60` or
darker; outlines are Gray 4 `#C0BEBB`. The test suite checks the page's text
contrast meets WCAG AA in both light and dark mode.
