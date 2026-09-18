---
version: 1
slug: "frontend-src-reporthub-vue"
primary_target: "frontend/src/ReportHub.vue"
related_targets: ["frontend/src/ApplicationShell.vue","frontend/src/styles/report-hub.css"]
---

# Report Hub Surface Brief

Mode: Operate. Scope: authenticated report management home at `frontend/src/ReportHub.vue`.

Audience and job: laboratory report staff repeatedly locate, assess, create, review, export, and audit reports. The primary task is to act on the report queue quickly; operational status and recoverable failures must be visible without opening each report.

Constraints: preserve backend contracts, permissions, existing report actions, creation dialog behavior, and Chinese terminology. Optimize for 1024px to 1440px desktop and laptop screens. No new dependency, decorative imagery, or invented data.

## Direction contract

THESIS: A disciplined report queue owns the screen; reject the dashboard default of oversized metric cards before the work.

OWN-WORLD: White work surfaces, cool gray structure, one precise blue accent, square-edged compact controls, quiet rules, and dense tabular rhythm.

STORY: Staff see urgent states, narrow the queue, select reports, and take the next action with minimal navigation.

FIRST VIEWPORT: A slim title/action bar, one-line status tabs, compact filters, and a table filling the remaining height; “新建报告” stays at the upper right.

FORM: Category-standard enterprise operations console, chosen from the user-pinned Feishu, DingTalk, and Amazon references; code-led.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
