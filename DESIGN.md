---
summary: "Offline incident-map design contract for desktop continuity; review is not restart permission."
read_when:
  - "You edit the isolated desktop-continuity map_preview renderer."
version: alpha
name: Niri Desktop Continuity
description: A private offline map of the work that must survive maintenance.
colors:
  primary: "#D9E5DA"
  secondary: "#A8BAB5"
  tertiary: "#F5C875"
  neutral: "#101D22"
  surface: "#192C32"
  on-surface: "#EAF0E8"
  muted: "#456268"
  success: "#8ED7C3"
  warning: "#F5C875"
  error: "#FFAF9F"
typography:
  display:
    fontFamily: Georgia, serif
    fontSize: 48px
    fontWeight: 400
    lineHeight: 1.1
  h1:
    fontFamily: Georgia, serif
    fontSize: 32px
    fontWeight: 400
    lineHeight: 1.2
  body-md:
    fontFamily: "DejaVu Sans", sans-serif
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  label-caps:
    fontFamily: "DejaVu Sans Mono", monospace
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
rounded:
  sm: 4px
  md: 8px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
components:
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.sm}"
    padding: 16px
  alert-warning:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.warning}"
    padding: 16px
---

## Overview

Niri Desktop Continuity is a night-chart of the operator's mental workspace. It is a review artifact,
not a live remote-control panel and not a backup of process memory. No network resources,
JavaScript, thumbnails, terminal output, browser contents, or executable approval buttons.

## Visual direction

Surveyor's ledger: ink-blue drafting surface, pale mineral text, amber admission warnings.
Serif headings frame a precise monospaced map. Workspace rows preserve vertical order;
columns run horizontally with tiles grouped inside them. Floating windows have a separate row.

## Colors

Use the front-matter palette. Amber always means caution, not successful recovery. Teal may
mark selected scope or a measured predicate, never unverified application state.

## Typography

Georgia headlines, DejaVu Sans body, DejaVu Sans Mono coordinates and identifiers. Local font
fallbacks only. Full identifiers remain available as text even if a compact tile label truncates.

## Layout

Read top to bottom: capture timestamp and privacy; admission warning; current map; desired map
when supplied; process/version/scope ledger; limitations. Horizontal overflow is explicit, not
silently dropped. SVG is a schematic, not a screenshot or pixel-perfect viewport reconstruction.

## Elevation and Depth

Thin drafting borders, generous gutters, no shadows or gradients. Stable static output is more
important than animation during a recovery incident.

## Shapes

Small-radius cards and square coordinate labels. No decorative circular gauges.

## Components

A workspace header gives stable ID, current index, output and window count. Column headers
show position, not guessed application tab state. Admission has text status plus blockers;
status must not rely on color. HTML has a full private inventory; SVG includes every window.

## Do's and Don'ts

- Do HTML/XML-escape all observed strings and remove invalid XML control characters.
- Do preserve exact digests in the textual approval panel.
- Do label unavailable geometry, versions, output readiness and native state as unknown.
- Do default to redacted window labels; included titles remain private local data.
- Don't infer hidden Ghostty tabs from compositor windows or title heuristics.
- Don't auto-open the operator's browser or restart any process.
