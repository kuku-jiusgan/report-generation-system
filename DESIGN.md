---
name: "报告自动生成系统"
description: "A restrained, high-density enterprise console for traceable laboratory report operations."
colors:
  operational-blue: "#1456d9"
  operational-blue-hover: "#2768df"
  operational-blue-active: "#0d46b5"
  focus-ring: "#7aa4ee"
  ink: "#182235"
  body-text: "#273247"
  secondary-text: "#657187"
  divider: "#dfe4ec"
  shell-ground: "#f5f6f8"
  surface: "#ffffff"
  surface-subtle: "#f8f9fb"
  surface-selected: "#eaf1ff"
  success-text: "#237804"
  warning-text: "#8a4600"
  danger-text: "#b42318"
  info-text: "#4b5563"
typography:
  page-title:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "22px"
    fontWeight: 650
    lineHeight: 1.35
    letterSpacing: "0"
  row-title:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.45
    letterSpacing: "0"
  body:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0"
  label:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0"
  metadata:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0"
rounded:
  status: "3px"
  control: "4px"
  action: "5px"
  brand: "6px"
  count: "9px"
  dialog: "12px"
spacing:
  xxs: "3px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "18px"
  xl: "24px"
  xxl: "28px"
components:
  button-primary:
    backgroundColor: "{colors.operational-blue}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.action}"
    padding: "0 15px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.operational-blue-hover}"
    textColor: "{colors.surface}"
    rounded: "{rounded.action}"
  icon-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary-text}"
    rounded: "{rounded.control}"
    height: "34px"
    width: "36px"
  input-compact:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.body-text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    height: "34px"
  navigation-item:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary-text}"
    typography: "{typography.label}"
    rounded: "{rounded.action}"
    height: "40px"
  navigation-item-active:
    backgroundColor: "{colors.surface-selected}"
    textColor: "{colors.operational-blue}"
    typography: "{typography.label}"
    rounded: "{rounded.action}"
    height: "40px"
  status-tab:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary-text}"
    typography: "{typography.body}"
    height: "49px"
  status-tag:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.info-text}"
    typography: "{typography.metadata}"
    rounded: "{rounded.status}"
    width: "72px"
  table-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.body-text}"
    typography: "{typography.body}"
    height: "52px"
  batch-action-bar:
    backgroundColor: "{colors.surface-selected}"
    textColor: "{colors.body-text}"
    typography: "{typography.body}"
    padding: "6px 24px"
    height: "45px"
---

# Design System: 报告自动生成系统

## Overview

**Creative North Star: "The Controlled Report Ledger"**

The Controlled Report Ledger treats every authenticated screen as an operational surface: quiet, information-dense, and anchored by a stable application shell. White work areas and cool-gray structure keep attention on report state, provenance, and the next permitted action; one precise blue accent supplies hierarchy without turning the interface into a brand spectacle.

This system is designed for repeated desktop work from 1024px through 1440px. It favors compact controls, explicit loading, error, and empty states, predictable columns, and visible keyboard focus. It rejects marketing composition, decorative AI imagery, gradients, oversized metrics, and ornamental card grids.

**Key Characteristics:**

- Full-height application shell with a stable navigation rail.
- Dense tabular workspaces that prioritize the next permitted action.
- Flat white surfaces separated by cool-gray rules and restrained tonal shifts.
- A single operational blue used for selection, focus, and primary commands.
- Explicit, text-backed states with accessible contrast and keyboard disclosure.

## Colors

The palette is deliberately narrow: one precise blue carries interaction, cool neutrals organize information, and semantic colors appear only when status requires them.

### Primary

- **Operational Blue** (`colors.operational-blue`): Primary commands, active navigation, selected tabs, and actionable links.
- **Operational Blue Hover** (`colors.operational-blue-hover`): Hover feedback for the primary command without adding a second accent family.
- **Operational Blue Active** (`colors.operational-blue-active`): Pressed controls and selected numeric counters.
- **Visible Focus Blue** (`colors.focus-ring`): Two-pixel keyboard focus outlines on interactive controls.

### Neutral

- **Ledger Ink** (`colors.ink`): Page headings and the strongest information hierarchy.
- **Operational Text** (`colors.body-text`): Table data and everyday working copy.
- **Secondary Slate** (`colors.secondary-text`): Supporting descriptions, report metadata, and footer totals; it must remain legible at compact sizes.
- **Quiet Divider** (`colors.divider`): One-pixel structural rules between shell, toolbar, table, and footer regions.
- **Shell Ground** (`colors.shell-ground`): Background visible around the white application work surface.
- **Work Surface** (`colors.surface`): The primary canvas for navigation, headers, filters, and data tables.
- **Subtle Utility Surface** (`colors.surface-subtle`): Filter bars and low-emphasis utility regions.
- **Selected Surface** (`colors.surface-selected`): Active navigation and selected operational states.

### Semantic

- **Success Text** (`colors.success-text`): Completed or successful status labels.
- **Warning Text** (`colors.warning-text`): In-progress, review, or caution states.
- **Danger Text** (`colors.danger-text`): Failure and destructive states.
- **Information Text** (`colors.info-text`): Neutral lifecycle states.

**The One Blue Rule.** Operational Blue is the only general-purpose accent; semantic colors communicate status and never become decorative accents.

**The Contrast Pair Rule.** Compact status text must maintain at least 4.5:1 contrast against its light status surface, and every status must retain a written label rather than relying on color alone.

## Typography

**Display Font:** Inter (with PingFang SC, Microsoft YaHei, and sans-serif fallbacks)

**Body Font:** Inter (with PingFang SC, Microsoft YaHei, and sans-serif fallbacks)

**Character:** The typography is neutral, compact, and office-oriented. Weight and spacing establish hierarchy; oversized display type and expressive letter spacing have no role in authenticated work surfaces.

### Hierarchy

- **Page Title** (650, `typography.page-title`): One compact title per workspace, paired with a short supporting line only when it improves orientation.
- **Row Title** (600, `typography.row-title`): The scannable primary identifier in dense report rows.
- **Body** (400, `typography.body`): Table values, filter content, and operational copy.
- **Label** (600, `typography.label`): Column headings, navigation labels, tabs, and command text.
- **Metadata** (400, `typography.metadata`): Report numbers, source namespaces, secondary navigation descriptions, usernames, and queue totals.

**The Compact Legibility Rule.** Secondary operational text never drops below the metadata role, and Chinese labels keep normal letter spacing instead of artificial tracking.

**The Numeric Stability Rule.** Counts and totals use tabular numerals so changing data does not shift surrounding controls.

## Layout

The authenticated application is a full-height grid. Its navigation rail is 220px when expanded and 64px when compact; at 1180px and below it compacts automatically so the working data remains dominant. The content region always uses `minmax(0, 1fr)` behavior and suppresses document-level overflow.

Report-index surfaces use a vertical operations stack: a 78px title bar, a 49px status strip, a compact filter band, a flexing table region, and a 35px totals footer. The queue fills the remaining first viewport instead of sitting below metric cards or decorative summaries. The fixed right action column is 184px, keeping the next report action visible while data columns adapt.

The default horizontal gutter is 24px and tightens to 18px below 1100px. Queue behavior is driven by its available container width: core columns remain below 1000px, the experiment column returns at 1160px, and wide desktops restore the complete working set. Filters wrap into two rows at a 980px container width without causing horizontal page overflow.

**The Queue-First Rule.** On report-index surfaces, status, filters, and the working queue consume the first viewport; summary cards never displace the reports themselves.

**The Fixed Action Rule.** Dense operational tables keep the primary row action visible at the right edge while lower-priority data columns yield first.

## Elevation & Depth

The system is flat by default. White and cool-gray tonal layers, one-pixel dividers, row hover fills, and the active navigation inset establish depth without floating panels. Shadows are reserved for true overlays such as drawers; normal page sections and queue regions remain flush with the application frame.

### Shadow Vocabulary

- **Active Navigation Inset** (`box-shadow: inset 2px 0 #1456d9`): Anchors the selected module to the left navigation edge.
- **Structural Drawer Shadow** (`box-shadow: -10px 0 30px rgba(28, 57, 92, 0.12)`): Separates an overlay drawer from the workspace beneath it.

**The Flat-by-Default Rule.** Resting work surfaces use borders and tonal shifts; shadows are reserved for overlays or explicit selected-state structure.

## Shapes

The form language is compact and nearly square. Status tags use a 3px radius, inputs and utility controls use 4px, primary actions and navigation items use 5px, and the brand mark uses 6px. Count badges may use a 9px capsule because their width changes with data; circular geometry is limited to avatars and familiar status markers. Dialogs retain the platform's 12px radius, but cards must not inherit that softer silhouette by default.

Borders are one pixel and quiet. Form does not depend on decorative clipping, oversized pills, or nested rounded containers.

**The Radius Follows Function Rule.** Dense controls stay close to square; only compact counters, avatars, and platform dialogs receive more curvature.

## Components

### Buttons

- **Shape:** Compact, stable action geometry with gently squared corners (`rounded.action`).
- **Primary:** Operational Blue with white text, 36px high, and 15px horizontal padding; reserve it for the page's clearest next action.
- **Hover / Focus:** Hover shifts within the same blue family; keyboard focus uses a visible two-pixel focus ring, and active state deepens the blue.
- **Secondary / Ghost:** White or transparent controls use cool-gray text and borders, turning blue only on hover or focus.

### Inputs / Fields

- **Style:** White 34px controls with a quiet border, 4px corners, and body-sized text inside a subtle filter band.
- **Focus:** Border and ring feedback use the operational blue family without changing control dimensions.
- **Error / Disabled:** Errors include readable Chinese text; disabled state remains visually distinct and never masquerades as loading.

### Navigation

The desktop rail uses 40px items with a 44px compact hit area. Default items are neutral, hover adds a quiet gray-blue fill, and the active item combines Operational Blue text, a selected surface, and a two-pixel inset marker. At compact width, descriptive text collapses while icon tooltips preserve discoverability and keyboard focus remains visible.

### Chips

- **Style:** Lifecycle tags are at least 72px wide, centered, and paired with an explicit text label.
- **State:** Success, warning, danger, primary, and information labels use accessible dark foregrounds on restrained light surfaces; color never carries the state alone.

### Cards / Containers

- **Corner Style:** Operational page sections are unframed and flush; repeated data lives in table rows rather than cards.
- **Background:** White work surfaces sit directly against the cool shell ground, with subtle utility bands where grouping is needed.
- **Shadow Strategy:** No shadow at rest; see Elevation & Depth for overlay exceptions.
- **Border:** One-pixel dividers define regions without boxing every section.
- **Internal Padding:** Main horizontal regions use the large 24px gutter and compact internal gaps from the 4px to 12px spacing steps.

### Status Strip

Status filters are a single 49px horizontal band, not dashboard metrics. Each option combines a label with a stable numeric counter; the active option uses blue text and a two-pixel underline, while failures may use the danger text treatment only when their count is nonzero.

### Report Queue

The report queue is the signature work component. Rows are 52px high, headers are 38px high, report titles lead each row, and report number plus source namespaces sit immediately beneath as secondary metadata. Long titles truncate visually but disclose their full value on hover and keyboard focus. Selection, loading, retained-data refresh errors, initial-load errors, no-results, and truly empty states are all explicit.

### Tooltips

Tooltips restore information hidden by compact layouts: collapsed navigation labels, unfamiliar icon actions, and truncated report titles. They must activate for keyboard focus as well as pointer hover and never replace an accessible control name.

## Do's and Don'ts

### Do:

- **Do** keep report workspaces dense enough that the queue occupies the remaining first viewport.
- **Do** preserve a single blue primary accent and use semantic colors only for labeled status or risk.
- **Do** keep loading, success, retained-data error, initial error, filtered-empty, and true-empty states explicit.
- **Do** maintain visible keyboard focus and at least 4.5:1 contrast for compact status and supporting text.
- **Do** adapt by hiding lower-priority columns before allowing horizontal page overflow.
- **Do** keep permissions, source namespaces, auditability, and backend data authoritative in the UI.

### Don't:

- **Don't** place metric cards, promotional summaries, or decorative containers above the operational queue.
- **Don't** use gradients, glowing effects, decorative AI imagery, or atmospheric color blobs.
- **Don't** introduce a second general-purpose accent or turn semantic status colors into decoration.
- **Don't** nest cards inside cards or make page sections look like floating marketing panels.
- **Don't** hide full truncated values from keyboard users or communicate status by color alone.
- **Don't** enlarge headings, radii, or spacing until routine office work becomes sparse or scroll-heavy.
