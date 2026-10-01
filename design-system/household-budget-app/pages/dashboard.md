# Dashboard Page Overrides

> **PROJECT:** Household Budget App
> **Generated:** 2026-10-01 17:41:47
> **Page Type:** Dashboard / Data View

> ⚠️ **IMPORTANT:** Rules in this file **override** the Master file (`design-system/MASTER.md`).
> Only deviations from the Master are documented here. For all other rules, refer to the Master.

---

## Page-Specific Rules

### Layout Overrides

- **Max Width:** 1400px or full-width
- **Grid:** 12-column grid for data flexibility
- **First visible content:** Open with the selected month and its financial
  summary directly after app navigation. Keep the month control with the data
  it changes. The first content region should let a user read their financial
  state or take the primary recording action immediately.

### Spacing Overrides

- **Content Density:** High — optimize for information display

### Content Rules

- Use concise Japanese labels that name the data or action on each card.
- Place sample-data labeling and its removal control beside the transaction
  data, where their meaning is clear.
- Reserve editorial introductions, motivational copy, and product-demo
  sequences for public marketing pages.
- **Completion check:** At phone and desktop widths, the first visible content
  after app navigation is the period and financial summary, with no introductory
  section between them.

### Typography Overrides

- Use the typography in `DESIGN.md` for this in-product screen.

### Color Overrides

- Use the palette and surfaces in `DESIGN.md` for this in-product screen.

### Component Overrides

- Avoid: Single row actions only
- Avoid: Icon buttons without labels
- Avoid: Auto-play high-resolution loops without pause or captions

---

## Page-Specific Components

- No unique components for this page

---

## Recommendations

- Effects: Hover tooltips, chart zoom on click, row highlighting on hover, smooth filter animations, data loading spinners
- Data Entry: Allow multi-select and bulk edit
- Accessibility: Add aria-label for icon-only buttons
- Sustainability: Prefer click-to-play; provide pause and captions; stop off-screen and honor reduced motion
