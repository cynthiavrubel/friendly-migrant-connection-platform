# Friendly Design System

## Design Philosophy

Friendly should feel:

- Modern
- Minimalist
- Welcoming
- Calm
- Trustworthy
- Clean
- Accessible

The interface should help users feel comfortable and confident from the moment they arrive.

The design should never feel cluttered, childish or overwhelming.

## Color Palette

Background
#F8FAFC

Cards
#FFFFFF

Primary
#2563EB

Primary Hover
#1D4ED8

Text
#1F2937

Secondary Text
#6B7280

Borders
#E5E7EB

Success
#10B981

## Typography

Font Family

Inter

Heading Weight

700

Body Weight

400

Buttons

600

## Border Radius

Buttons

16px

Cards

16px

Inputs

12px

## Shadows

Cards

Soft shadow

Hover

Slightly stronger shadow

No dramatic shadows.

## Spacing

Small

8px

Medium

16px

Large

32px

Extra Large

64px

## Buttons

Primary

Blue background

White text

Rounded corners

Subtle hover animation

Secondary

White background

Blue border


## Cards

White background

Rounded corners

Soft shadow

Comfortable padding

Simple icon

Short heading

Short description

## Motion

Buttons

200ms transition

Cards

Lift slightly on hover

No bouncing

No spinning

No flashy animations
Blue text

## Responsive Layout Rules

Friendly pages use `static/css/layout.css` as the shared responsive contract.

- Use `.friendly-container` for standard pages and add `.friendly-container--wide` for layouts such as Discover.
- Horizontal gutters come from `--page-gutter`; do not duplicate fixed page padding in feature stylesheets.
- Build fluidly with `width: 100%`, `max-width`, and `min-width: 0`. Fixed widths require a clear component-level reason.
- Use `.friendly-card`, `.friendly-grid`, `.friendly-stack`, `.responsive-form-grid`, and `.friendly-chip-list` before creating page-specific layout rules.
- Breakpoints are mobile through 480px, small/tablet from 481â€“767px, tablet from 768â€“1023px, and desktop from 1024px.
- Authenticated pages use `.app-header` and `.app-nav`. Navigation wraps onto a deliberate second row at mobile widths; labels must never be clipped.
- Multi-column grids collapse when their content no longer fits. Forms and controls must remain touch-friendly and inside their parent at 320px.
- Long names, cities, languages, filenames, and intentions must wrap or truncate intentionally without widening the document.
- Document-level horizontal overflow is a release-blocking regression. Internal scrolling is reserved for bounded controls such as long option lists.
- Every new page must pass the standard viewport matrix: 320, 360, 375, 390, 412, 480, 768, 1024, 1280, and 1440px; test 1920px when practical.
