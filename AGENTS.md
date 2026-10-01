# UI / UX Design

Before implementing or modifying UI, identify whether the screen is a public
marketing page or an in-product app screen. Apply each reference only to the
screen type and property it describes.

1. Read `/DESIGN.md` for visual styling: colors, typography, radius, shadows,
   spacing style, surfaces, buttons, and component appearance. Its public-site
   layout and example copy apply only to public marketing pages.
2. Read `design-system/household-budget-app/MASTER.md` for general UX guidance.
   Its product-demo page pattern applies only to public marketing pages.
3. For the dashboard, read
   `design-system/household-budget-app/pages/dashboard.md` and follow its
   content order, density, and dashboard-specific UX requirements.

For in-product screens, use the page-specific file for information hierarchy
and layout, `DESIGN.md` for visual properties, and `MASTER.md` for remaining
general guidance. Use ui-ux-pro-max for UX, information architecture,
accessibility, data visualization, and interaction guidance; `DESIGN.md` wins
on visual styling.

Before finishing a dashboard change, inspect the first visible content after
app navigation at desktop and phone widths. It must expose the selected period
and financial state or an action immediately. If a browser preview is
unavailable, inspect the rendered structure and report that limit.
