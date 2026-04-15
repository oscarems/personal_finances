# Design System - Personal Finances

## Overview

This document describes the design system implemented in the Personal Finances app. All UI components use Tailwind CSS (CDN) with custom extensions defined in `base.html`.

---

## Color Palette

### Core Colors

| Color | Use | HEX |
|-------|-----|-----|
| **Primary (Blue)** | Primary actions, links, interactive elements | `#2563EB` (600) |
| **Success (Green)** | Income, confirmations, positive states | `#059669` (600) |
| **Danger (Red)** | Expenses, alerts, debts | `#DC2626` (600) |
| **Warning (Orange)** | Warnings, items requiring attention | `#EA580C` (600) |
| **Accent (Purple)** | Highlighted elements, special charts | `#9333EA` (600) |
| **Neutral (Gray)** | Text, backgrounds, neutral elements | `#374151` (700) |

### Gradients

- **Primary Gradient**: `from-primary-500 to-primary-700`
- **Success Gradient**: `from-success-500 to-success-700`
- **Accent Gradient**: `from-accent-500 to-accent-700`
- **Danger Gradient**: `from-danger-50 to-danger-100` (for backgrounds)

---

## Typography

### Primary Font
- **Family**: Inter (Google Fonts)
- **Weights**: 300, 400, 500, 600, 700, 800
- **Characteristics**: Modern, professional, highly legible

### Type Scale

| Element | Tailwind Classes | Use |
|---------|-----------------|-----|
| **Page Title** | `text-4xl font-bold text-neutral-900 tracking-tight` | Page headings |
| **Section Title** | `text-2xl font-bold text-neutral-900` | Section headings |
| **Subtitle** | `text-xl font-bold text-neutral-800` | Card subtitles |
| **Body** | `text-base text-neutral-600` | General text |
| **Labels** | `text-sm font-bold text-neutral-700 uppercase tracking-wide` | Form labels |
| **Small** | `text-xs text-neutral-500` | Secondary text |

---

## Components

### Buttons

```css
.btn-primary    /* Primary actions — Blue */
.btn-success    /* Positive actions — Green */
.btn-danger     /* Destructive actions — Red */
.btn-secondary  /* Secondary actions — Gray */
```

**Properties:**
- Padding: `px-5 py-2.5`
- Border radius: `rounded-button` (8px)
- Smooth transitions
- Hover and active states
- Subtle shadows

### Cards

```css
.card                    /* Plain white card */
.card-gradient-primary   /* Blue gradient card */
.card-gradient-success   /* Green gradient card */
.card-gradient-accent    /* Purple gradient card */
```

**Properties:**
- Border radius: `rounded-card` (12px)
- Shadows: `shadow-soft` (default), `shadow-medium` (hover)
- Smooth hover transitions

### Inputs

```css
.input-field    /* Standard form input */
```

**Properties:**
- Padding: `px-4 py-2.5`
- Border: `border-neutral-300`
- Focus: Primary blue ring
- Border radius: `rounded-button` (8px)
- Disabled state with gray background

### Badges

```css
.badge          /* Base badge */
.badge-success  /* Green badge */
.badge-danger   /* Red badge */
.badge-warning  /* Orange badge */
.badge-primary  /* Blue badge */
```

### Alerts

```css
.alert          /* Base alert */
.alert-success  /* Green alert */
.alert-danger   /* Red alert */
.alert-warning  /* Orange alert */
.alert-info     /* Blue alert */
```

**Properties:**
- 4px left border
- Soft 50-tone background
- Padding: `p-4`
- Border radius: `rounded-lg`

---

## Iconography

The app uses emojis as the primary icon system:

- **Size**: `text-xl` to `text-3xl` depending on context
- **Presentation**: Wrapped in divs with a colored background and border-radius
- **Consistency**: Specific icons per section

### Icon Mapping

| Section | Icon | Context |
|---------|------|---------|
| Dashboard | 📊 | General overview |
| Budget | 💰 | Budget management |
| Transactions | 📝 | Transaction list |
| Accounts | 🏦 | Account management |
| Debts | 💳 | Debt tracking |
| Net Worth | 🏛️ | Patrimonio dashboard |
| Reports | 📈 | Analytics and charts |
| Emergency Fund | 🆘 | Emergency fund tracking |

---

## Section-Specific Styles

### Sidebar

- **Background**: Dark gray gradient (`from-neutral-900 to-neutral-800`)
- **Logo**: Gradient background with shadow
- **Navigation**: Items with hover and active states
- **Grouping**: Categorized sections (Main, Management, Tools)

### Dashboard

- Cards with gradients for key metrics
- Representative icons per metric
- Subtle section dividers

### Budget

- Summary banner cards with distinct gradients
- Collapsible group headers
- Visual status states for categories
- Progress bars with semantic colors
- Modals with backdrop blur and elevated shadows

### Charts (Chart.js)

- **Font**: Inter
- **Colors**: Design system palette
- **Tooltips**: Dark background with border radius
- **Legends**: Consistent with the design

---

## Animations and Transitions

### Global Transition

```css
--transition-smooth: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
```

### Animated Elements

- **Buttons**: Hover and active states
- **Cards**: Elevation on hover
- **Nav Items**: Background and color on hover
- **Progress Bars**: Width with cubic-bezier easing
- **Modals**: Fade in/out with backdrop blur

---

## Spacing System

### Grid and Layout

- **Container**: `mx-auto px-8 py-8`
- **Grid gaps**: `gap-6` (24px) for main grids
- **Vertical spacing**: `space-y-6` between sections

### Padding and Margin

- **Cards**: `p-6` to `p-8`
- **Modals**: `p-8`
- **Inputs**: `px-4 py-2.5`
- **Buttons**: `px-5 py-2.5`

---

## Shadow System

```css
--shadow-soft: 0 2px 8px rgba(0, 0, 0, 0.08);
--shadow-medium: 0 4px 16px rgba(0, 0, 0, 0.12);
--shadow-strong: 0 8px 24px rgba(0, 0, 0, 0.16);
```

| Context | Shadow |
|---------|--------|
| Cards (default) | `shadow-soft` |
| Cards (hover) | `shadow-medium` |
| Modals | `shadow-strong` |
| Buttons | `shadow-sm` (default), `shadow-md` (hover) |

---

## Responsive Design

### Breakpoints (Tailwind defaults)

- **sm**: 640px
- **md**: 768px
- **lg**: 1024px
- **xl**: 1280px

### Common Patterns

- Grids: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`
- Flexbox: `flex-col lg:flex-row`
- Spacing: `gap-4 md:gap-6`

---

## Accessibility

- **Contrast**: All text meets WCAG AA standards
- **Focus states**: Visible rings on all interactive elements
- **Touch targets**: Minimum 44×44px for interactive elements
- **Semantic hierarchy**: Correct heading levels used throughout

---

## Technical Implementation

### Tailwind Configuration

Tailwind CSS is loaded via CDN with inline custom configuration in `base.html`:

```javascript
tailwind.config = {
    theme: {
        extend: {
            colors: { /* custom colors */ },
            fontFamily: { sans: ['Inter', ...] },
            boxShadow: { /* custom shadows */ },
            borderRadius: { /* custom radii */ }
        }
    }
}
```

### Custom CSS

Reusable component classes are defined in the `<style>` block of `base.html`:
- Button classes (`.btn-*`)
- Card classes (`.card*`)
- Input class (`.input-field`)
- Badge classes (`.badge*`)
- Alert classes (`.alert*`)

---

**Version**: 1.1.0
**Last updated**: 2026-04
