# ForgeERP Design System & Frontend Handoff

**Document version:** 2.0

**Last source audit:** Current repository state

**Platform:** React 19, TypeScript, Vite 8, Tailwind CSS 4, custom CSS and custom React design-system primitives
**Primary sources:** `src/index.css`, `src/design-system.tsx`, `src/App.tsx`, and every page/panel file under `src/`

> **Verification vocabulary**
>
> - **Verified:** directly implemented in the current source.
> - **Static fixture:** hard-coded demonstration content in source; do not present it as production/backend data.
> - **Local preview:** state exists only in the current browser component and is not persisted.
> - **Backend unavailable:** the UI deliberately shows “Unavailable,” not `0`, an empty string, or fabricated records.
> - **Needs verification:** not established by source or an available design artifact.

## Table of contents

1. [Product-wide rules and source of truth](#1-product-wide-rules-and-source-of-truth)
2. [Design system reference](#2-design-system-reference)
3. [Application shell and layout](#3-application-shell-and-layout)
4. [Shared component specifications](#4-shared-component-specifications)
5. [Screen specifications](#5-screen-specifications)
   - Overview / AI Dashboard
   - Products, Add Product, Categories Tree
   - Product Details and its four tabs
   - Inventory and its four tabs
   - Sales and New Sale
   - Purchasing, New Purchase Order, and approval
   - Branches, Add/Edit Branch, enrollment token
   - Branch Device Enrollment
   - Employees and Add/Edit Employee
   - User Accounts & Access
   - AI Assistant and recommendation review
   - Design System / Handoff
6. [Forms and business rules](#6-forms-and-business-rules)
7. [AI and approval workflow](#7-ai-and-approval-workflow)
8. [Data availability and preview-state rules](#8-data-availability-and-preview-state-rules)
9. [Frontend implementation guidance](#9-frontend-implementation-guidance)
10. [Verification checklist](#10-verification-checklist)
11. [Open questions and unresolved details](#11-open-questions-and-unresolved-details)

---

## 1. Product-wide rules and source of truth

- The logged-in application user is always **Mahmoud Ragab** (`MR` avatar), Operations Manager.
- The source uses state-based navigation, not URL routing. `App.tsx` selects a page from the active sidebar label.
- Existing navigation groups: Workspace; Operations; Relationships; Organization & Identity; Analysis.
- AI may explain and recommend. An AI-proposed write action must pass through human review and explicit approval.
- The intended purchase flow is **AI insight → recommendation → human review → explicit approval → draft purchase order**.
- Never convert `Unavailable` to `0`. Zero is valid only when explicitly supplied by a data source.
- Static sales, purchasing, inventory, and product fixture arrays are prototype content. They are not evidence of backend endpoints.
- Local Branch, Employee, Category, and User Account records are component state only.
- Backend endpoints, persistence, authentication, focus management, localization, and mobile layouts are not established.

### Actual file organization

| Responsibility | Current source |
|---|---|
| App shell, navigation, Overview | `src/App.tsx` |
| Shared primitives and AI/approval components | `src/design-system.tsx` |
| Global tokens and component/page CSS | `src/index.css` |
| Products and Add Product | `src/ProductsPage.tsx` |
| Categories Tree | `src/CategoriesTreePanel.tsx` |
| Product Details | `src/ProductDetailsPage.tsx` |
| Inventory shell / Stock Overview | `src/InventoryPage.tsx` |
| Stock Balances & Batches | `src/StockBalancesBatchesTab.tsx` |
| Adjustment form / Ledger | `src/InventoryTransactionsTabs.tsx` |
| Sales / New Sale | `src/SalesPage.tsx` |
| Purchasing / New PO | `src/PurchasingPage.tsx` |
| Branches / Branch forms / token preview | `src/BranchesPage.tsx` |
| Branch first-run enrollment | `src/BranchEnrollmentPage.tsx` |
| Employees / Employee form | `src/EmployeesPage.tsx` |
| User accounts and access | `src/UserAccountsPage.tsx` |
| In-app handoff | `src/HandoffPage.tsx` |

---

## 2. Design system reference

### 2.1 Colors

| Role | HEX / source value | CSS token | Verified usage |
|---|---|---|---|
| Primary | `#2563EB` | `--color-primary` | Primary actions, links, actual chart series |
| Primary hover | `#1D4ED8` | `--color-primary-hover` | Primary button hover |
| Primary soft | `#EFF6FF` | `--color-primary-soft` | Product icons, avatars, selected identity surfaces |
| AI accent | `#6D5BD0` | `--color-ai` | AI buttons, forecast line, AI labels |
| AI soft | `#F2EFFF` | `--color-ai-soft` | AI notices and icon backgrounds |
| Success | `#15803D` | `--color-success` | Active/available/success states |
| Success soft | `#ECFDF3` | `--color-success-soft` | Success badges and banners |
| Warning | `#B45309` | `--color-warning` | Pending, locked, nearing expiry |
| Warning soft | `#FFF7ED` | `--color-warning-soft` | Warning surfaces |
| Danger | `#C2413B` | `--color-danger` | Error, rejection, stockout |
| Danger soft | `#FEF2F2` | `--color-danger-soft` | Error/risk surfaces |
| Information | `#0369A1` | `--color-info` | Data/source notices |
| Information soft | `#F0F9FF` | `--color-info-soft` | Informational surfaces |
| Canvas | `#F6F7F9` | `--color-background` | App background and subtle fills |
| Surface | `#FFFFFF` | `--color-surface` | Cards, inputs, panels, modals |
| Border | `#E2E6EC` | `--color-border` | Dividers, cards, tables |
| Strong border | `#CDD3DC` | `--color-border-strong` | Inputs, selects, secondary buttons |
| Primary text | `#172033` | `--color-text` | Titles and emphasized values |
| Secondary text | `#5E6879` | `--color-text-secondary` | Body and labels |
| Muted text | `#8B94A3` | `--color-text-muted` | Helper text, placeholders, unavailable values |
| Sidebar | `#101827` | `--color-sidebar` | Fixed navigation rail |
| Sidebar muted | `#9BA7BA` | `--color-sidebar-muted` | Sidebar secondary copy |

Verified literal colors that are not tokenized include sidebar active/hover fills, AI border tints, table hover, topbar translucency, and focus-ring alpha. Do not promote or reuse them without first defining a semantic role.

### 2.2 Interaction colors

- Primary hover: `#1D4ED8`.
- AI hover: literal `#5C4ABF`.
- Ghost hover: literal `#EDF0F4`.
- Input focus: primary border plus `0 0 0 3px rgba(37,99,235,.11)`.
- Disabled examples: pagination and form controls use opacity and `cursor: not-allowed`; disabled styling is not globally exhaustive.
- Selected tabs: white surface over background fill with `--shadow-sm`.
- Row hover: literal near-white blue (`#FAFCFF`).

### 2.3 Typography

Font import: Google **Inter**, weights 400/500/600/700; fallback `sans-serif`.

| Role | Size / weight / line height |
|---|---|
| Page title | 25px / 700 / 1.25; `-.035em` tracking |
| Token display | 25px (`--font-display`) |
| Metric value | 23px / 700; 20px at ≤1250px |
| Modal/title token | 15px / 700 (`--font-title`) |
| Card title | 13px / 700 |
| Body/control | 12px / 400–600 (`--font-body`) |
| Small body/table content | 10px / 400–700 (`--font-body-sm`) |
| Caption/badge/helper | 9px / 400–700 (`--font-caption`) |
| Table header/micro | 8px / 600 / uppercase |

Most line heights are normal. Explicit explanatory copy commonly uses 1.4–1.6. A complete typography line-height scale **Needs verification**.

### 2.4 Spacing, geometry, elevation

| Token | Value | Typical use |
|---|---:|---|
| `--space-1` | 4px | Tight metadata gap |
| `--space-2` | 8px | Inline/control gap |
| `--space-3` | 12px | Compact padding |
| `--space-4` | 16px | Standard section rhythm |
| `--space-5` | 20px | Modal/card groups |
| `--space-6` | 24px | Page/sidebar rhythm |
| `--space-8` | 32px | Desktop content padding |
| `--radius-sm` | 6px | Controls and compact notices |
| `--radius-md` | 10px | Menus and grouped panels |
| `--radius-lg` | 14px | Cards and modal shell |
| `--shadow-sm` | `0 1px 2px rgba(16,24,40,.04)` | Cards/selected tabs |
| `--shadow-md` | `0 8px 24px rgba(16,24,40,.10)` | Dropdown |
| `--shadow-lg` | `0 20px 48px rgba(16,24,40,.16)` | Modal and assistant |

- Standard border: 1px.
- Standard control minimum height: 36px.
- Icon button: 36×36px.
- Badge: min-height 22px, horizontal padding 8px.
- Product icon: 30×30px; large 40×40px.
- Icons: 16×16px default, 20×20px medium; stroke 1.8, rounded caps/joins.

---

## 3. Application shell and layout

### 3.1 Shell

- `app-shell`: flex, minimum viewport height.
- Sidebar: fixed left, 248px wide, full height, z-index 20, padding 24px 14px 16px.
- Main: left margin 248px, flexible width.
- Topbar: 66px height, 32px horizontal padding, bottom border, near-opaque white.
- Content: max-width 1440px, centered, padding 28px 32px 48px.
- Body minimum width: 1180px. The implementation is desktop-first.

### 3.2 Sidebar

Order: brand → branch switcher → grouped navigation → Settings → Mahmoud Ragab card. Navigation can scroll vertically. Active row uses a darker blue fill; AI Brain has a purple accent dot. `ForgeSidebar` receives `active`, `onChange`, and optional sections.

### 3.3 Page pattern

`page-heading` aligns title content left and actions right. Typical order: uppercase eyebrow, title/status row, description. Cards use white surface, 1px border, 14px radius and small shadow. Table cards usually include toolbar → result/meta row → horizontally scrollable table → pagination.

### 3.4 Responsive and overflow behavior

- Only verified breakpoint: ≤1250px changes content horizontal padding from 32px to 22px; metric card padding/value size also reduce.
- Tables use horizontal overflow wrappers where configured.
- Modals max at 92vh and scroll vertically.
- Assistant panel is fixed and independently scrollable.
- No mobile sidebar, mobile table, or small-screen stacking system is implemented. **Needs verification**.

---

## 4. Shared component specifications

| Component | API / variants | Appearance and behavior |
|---|---|---|
| `Button` | primary, secondary, ghost, danger, AI; icon; icon-only; native props | 36px min height, 6px radius, 12px/600. Icon-only requires `aria-label`. |
| `Input` | native input props plus `icon`, `suffix`, `className` | 36px shell; supports text, number, date, email, tel, URL and percent suffix compositions. |
| `Select` | native select props + string `options` | Native select in 36px shell with custom chevron. No rich option objects. |
| `Dropdown` | `trigger`, string `items` | 170px menu, medium shadow; current items only close menu and have no per-item callback. |
| `Badge` | neutral, success, warning, danger, info, AI; optional dot | Text always accompanies color. |
| `Card` / `CardHeader` | children; optional class; title/description/action | Shared surface shell and header composition. |
| Table primitives | `Table`, header/body/row/head/cell; numeric alignment | 8px uppercase header, 10px body, row border/hover. |
| `Tabs` | labels, active label, `onChange` | Ghost buttons in a subtle grouped background. |
| `Modal` | open, close, title, eyebrow, icon, footer, labelledBy | Centered dialog over scrim; close icon; scrollable; no verified focus trap/Escape handling. |
| `ForgeSidebar` | active/onChange/sections | Fixed dark navigation shell. |
| `InsightCard` | label/value/trend/icon/variant | Legacy KPI card used on some fixture-data screens. |
| `RiskIndicator` | low/medium/high | Maps success/warning/danger and writes the risk label. |
| `ForecastChart` | no props | Static fixture SVG used by Sales; not a data-driven chart API. |
| `AssistantChatPanel` | open/onClose/onApprove | 420px right drawer, scrim, offline template conversation. |
| `ApprovalModal` | open/onClose/onApprove/onReject?/estimatedTotal? | Human gate; current copy says approval creates a draft PO. |

### Shared patterns

- **Sortable table:** ghost `Button` inside `TableHead`; direction icon; filters reset page to 1.
- **Pagination:** 5-row pages on Products, Inventory Overview, Sales, Purchasing.
- **Skeleton:** 350ms prototype loading delay; 5 rows; 1.3s shimmer.
- **Empty state:** centered circular icon, title, helper, recovery action.
- **Unavailable state:** muted/italic “Unavailable” plus explanation; never use `0`.
- **Form sections:** numbered soft-AI square, title, helper; 2-column grids; inline errors directly below controls.
- **Not implemented:** shared textarea, tooltip component, toast service, data grid, route layer, focus trap, backend service abstraction.

---

## 5. Screen specifications

All navigation “routes” below are sidebar labels, not URLs.

### 5.1 Overview / AI Dashboard

**Purpose / entry:** Workspace → Overview; default active page.

**Order:** heading → AI Brain summary → demand/recommendation split → AI inventory health table.

**Layout:** summary is full width; main grid is `minmax(0,1.65fr) minmax(350px,1fr)` with 14px gap.

**Components and behavior**

- Heading: date, “Good morning, Mahmoud Ragab,” operational badge, description. No Export/New transaction/date-range controls.
- AI Brain summary: High Stock-out Risk, Products Needing Reorder, Pending AI Approvals. Values are em dashes with “Awaiting connected data.”
- Sales & Demand Forecast: product selector; blue actual and purple dashed forecast; explicitly “Illustrative UI · no live data.” No dashboard revenue/profit metric.
- AI Insights: example cards show product, unassessed risk, explanation, unavailable proposed quantity, and primary **Review Recommendation**.
- Review modal: product, unassessed risk, quantity, explanation. Approval remains disabled until quantity exists.
- Workflow notice: recommendation → review → approval → draft PO.
- AI inventory health columns: Product, Available, Forecast demand, Stock-out risk, Reorder recommendation. Backend-dependent cells are unavailable/unassessed.
- `View inventory` changes active navigation to Inventory.

**States/data:** summary and table are backend-unavailable. Recommendation cards are labeled examples. Chart is illustrative. Success banner only appears after a draft-producing callback.

**Accessibility:** chart has an accessible label; controls use labels; review dialog is labelled. Focus trap/Escape **Needs verification**.

### 5.2 Products List

**Purpose / entry:** Operations → Products.

**Order:** page heading/Add product → AI insight fixture banner → master-detail grid. Main pane contains product toolbar/table/pagination; right pane contains Categories Tree.

**Main toolbar:** search product/SKU, category filter, stock-status filter, More filters, Export dropdown. Search implementation also matches supplier. Result count and clear-filters row follow.

**Table columns:** Product, SKU, Category, Supplier, On hand, Reorder point, Unit price, Stock status, Actions. All named columns are sortable. Five rows/page. Product name opens Product Details. Actions dropdown lists view/edit/adjust/archive, but string dropdown items do not execute callbacks.

**States:** 350ms skeleton; filtered empty state; disabled pagination; fixture product data. Product behavior is unchanged by the Categories Tree.

### 5.3 Add Product form

**Container:** wider scrollable `Modal`; four numbered sections.

| Section / field | Type | Requirement / default | Validation and dependency |
|---|---|---|---|
| Basic / Product Name | text | Required; `e.g. Amoxicillin 500mg` | Required |
| Basic / SKU | text | Required; `e.g. AMX-500-20` | Required; unique against fixture SKUs |
| Basic / Generic Name | text | Required | Required |
| Basic / Brand Name | text | Required | Required |
| Basic / Barcode | text | Optional | Helper says unique; backend uniqueness not implemented |
| Basic / Product Image URL | URL | Optional | Valid URL if entered |
| Classification / Category | select | Required; defaults Antibiotics | Fixture options |
| Classification / Primary Supplier | select | Required; defaults MedSource Ltd. | Fixture options |
| Classification / Reorder Point | number | Required; min 0, integer | Non-negative whole number |
| Pricing / Unit Price | number | Required; min 0, step .01 | Non-negative number |
| Pricing / Tax Rate (%) | number with `%` suffix | Required; user enters `14`, not `.14` | 0–100; local saved draft stores `14 / 100 = .14` |
| Expiry / Lot Tracking Required | switch-style button | Existing value shown | Disabled while backend stock/movement status is unavailable; preview explanation shown |
| Expiry / Expiry Alert Days | number | Optional | If entered, non-negative integer |

**Actions:** Cancel resets/ closes. Create validates, normalizes tax to decimal in a local draft, then closes. No backend product is created.

### 5.4 Categories Tree

**Purpose/layout:** right-side detail card in Products master-detail layout.

**Data state:** no seeded categories. Empty state says backend category data unavailable. User-added categories are local only.

**Tree behavior:** root categories have `parentId=null`; recursive children; indentation caps visually at depth 3. Node shows icon, name, code, optional description, Edit icon.

**Add/Edit Category fields**

- Category Code: required; case-insensitive unique among local categories.
- Category Name: required.
- Description: optional.
- Parent Category: optional; `No parent category` default.
- Edit excludes the category itself from parent options and validates against self-parenting.
- Descendant-cycle prevention beyond self-parent is **Needs verification**.

### 5.5 Product Details

**Entry:** click product name in Products table. Internal component state; Back returns to Products list.

**Header:** Back, product name, stock-status badge, SKU/category context.

**Tabs:** Product Information; UOMs & Pricing; Branch Reorder Settings; AI Demand Forecast.

#### Product Information

Read-only 3-column grid. Verified fixture values: product, SKU, category, supplier, catalog unit price, existing reorder point. Barcode, generic name, brand, image URL, tax, lot tracking, and expiry alert are “Unavailable.” Reorder point explicitly says unit and branch unavailable.

#### UOMs & Pricing

Editable local-draft table columns: Unit code; Display name; Base unit; Conversion factor; Settings (Sellable/Purchasable); Sale unit price; Actions.

- No UOM records are seeded; preserve empty state.
- Add Unit adds a blank local row. First unit automatically becomes the only base unit with factor `1`.
- Setting another base clears base status on all others and forces selected factor to `1`.
- Deleting the current base promotes the first remaining unit and forces factor `1`.
- Unit code/name required inline.
- Non-base conversion factor required and >0.
- Base factor input disabled with “fixed at 1.”
- `usedInTransactions` also disables factor with transaction-lock copy. No backend usage records are seeded.
- Sellable/Purchasable are explicit Yes/No switch buttons.

#### Branch Reorder Settings

- Branch select: current workspace branch.
- Reorder Point, Suggested Reorder Quantity, Maximum Stock Quantity: number inputs, base-unit labels, initially blank.
- Maximum must be ≥ reorder point; inline error.
- Data notice: no branch values supplied; entries are unsaved local draft.

#### AI Demand Forecast

- Legend for historical actual versus forecast demand.
- Model badge: Unavailable.
- Seasonal indicator badge: Unavailable.
- Empty chart frame; no series values invented.
- Copy identifies missing history, forecast, model, Ramadan/flu-season indicators.

### 5.6 Inventory

**Entry:** Operations → Inventory.

**Tabs:** Stock Overview; Stock Balances & Batches (default); Stock Adjustments & Opening Balance; Inventory Ledger History. Adjust Stock heading action appears only on Stock Overview.

#### Stock Overview

Order: heading → four fixture KPI cards → AI intelligence fixture card → searchable/filterable stock table.

Filters: product/SKU search; category; stock status; location; More filters; Export. Columns: Product, SKU, Category, On hand, Available, Reserved, Reorder point, 30-day forecast, Stockout risk, Stock status, Actions. Sortable, 5 rows/page, skeleton and empty state.

This tab contains static fixture values and AI copy. Do not treat them as backend data.

#### Stock Balances & Batches

Top filters: branch; product/SKU search; storage location (`SELLABLE`, `QUARANTINE`, `DAMAGED`, `SCRAP`); expiry status.

Balance columns: expander; Product; On-hand quantity/base units; Available quantity/base units; Weighted average unit cost.

- Product identities are available from fixture catalog.
- Quantities/costs show “Unavailable · Not zero · not provided.”
- Expand button uses `aria-expanded`.
- Expanded batch columns: Batch number; Manufacturing date; Expiry date; Quality status.
- Supported quality statuses: `AVAILABLE`, `QUARANTINED`, `EXPIRED`, `RECALLED`.
- Batch sort is FEFO: ISO expiry ascending; missing expiry last.
- `nearingExpiry` uses warning background/badge.
- If backend says lot tracking is false, render one `NON-LOT` row.
- Current maps are empty; expanded state shows “Batch data unavailable.”
- No stock editing exists in this table.

#### Stock Adjustments & Opening Balance

Three numbered form sections; validation is local and **Validate entry** never posts.

| Field | Rules |
|---|---|
| Transaction Type | `OPENING_BALANCE`, `ADJUSTMENT_IN`, `ADJUSTMENT_OUT` |
| Reason Code | Required text |
| Notes | Optional text input |
| Product | Required fixture-product select |
| Storage Location | `SELLABLE`, `QUARANTINE`, `DAMAGED`, `SCRAP` |
| Unit | Required text; saved UOM unavailable |
| Quantity | Required number >0 |
| Batch Number / Expiry Date | Optional because lot status unavailable; if either is entered, the other becomes required |
| Unit Cost | Required non-negative for opening/inbound; cleared and disabled for `ADJUSTMENT_OUT` |

Success copy says validation passed and no transaction posted.

#### Inventory Ledger History

Read-only. Filters: From date, To date, transaction type, employee. Columns: Date & time, Transaction type, Product, Storage location, Quantity, Unit, Batch, Employee. Backend-unavailable notice and empty audit state; no records invented.

### 5.7 Sales

**Entry:** Operations → Sales. **Data:** static fixture.

Order: heading/date range/New sale → 4 KPI fixtures → revenue forecast + AI insights → table/pagination → New Sale modal.

Filters: invoice/customer search, payment status, sales status; More filters and Export. Columns: Invoice/Order ID, Date & Time, Customer, Items, Total Amount, Payment Method, Payment Status, Sales Status, Created By, Actions. Five rows/page; date defaults descending.

New Sale modal fields: Customer search, Sale location select, Add products search. Empty product composition area. Save as draft/Continue to checkout currently only close; backend behavior **Needs verification**.

### 5.8 Purchasing

**Entry:** Operations → Purchasing. **Data:** static fixture.

Order: optional success banner → heading/New PO → KPI fixtures → AI recommendation/intelligence split → table → New PO and approval modals.

Filters: PO/supplier search, order status, supplier, date range; More filters, Export. Columns: PO Number, Supplier, Order Date, Expected Delivery, Items, Total Amount, Status, Approval Status, Created By, Actions. Five rows/page.

New PO fields: Supplier, Expected delivery, Add products; empty composition. Footer actions only close.

AI recommendation opens `ApprovalModal`. **Known inconsistency:** Purchasing success copy says an approved PO was sent to a supplier, while the current approval component and product-wide rule say approval creates a draft only. Resolve before production; do not reproduce automatic supplier submission.

### 5.9 Branches

**Entry:** Operations → Branches.

Order: heading/Add Branch → local notice → search/status toolbar → backend-unavailable notice → result count → table → forms/modals.

Table: Branch Name, Branch Code, City, Status, Actions. Actions: Edit Branch; Generate Enrollment Token. No backend rows are seeded. Search name/code/city; status Active/Inactive.

#### Add/Edit Branch

- Branch Name: required, max 150.
- Branch Code: required, max 30, case-insensitive unique locally.
- Address Line 1: required.
- Address Line 2: optional.
- City: required.
- Region / Governorate: optional.
- Postal Code: optional.
- Country Code: exactly 2 characters, default `EG`, uppercased.
- Status: Active/Inactive; deactivation is soft; no delete.
- Notice: local-only. Backend creation should provision `SELLABLE`, `QUARANTINE`, `SCRAP` automatically; UI does not create them.

#### Enrollment Token preview modal

Clearly labelled “UI preview · Backend unavailable” and “Preview token · Not valid.” Shows branch, mock token, Copy, expiry time ten minutes from opening, and one-time-use warning. Clipboard failure has no dedicated error UI. No backend token is claimed.

### 5.10 Branch Device Enrollment

**Entry:** Operations → Branch Enrollment.

Centered card and four states:

1. **Unenrolled:** required token input, one-time notice, visible preview token, Activate & Start Sync.
2. **Activating:** spinner and disabled button; explicitly no backend request/sync.
3. **Success:** says a connected environment would sync Product catalog, Prices, Employee data, then normal login. Disclaimer says nothing activated/synced/redirected.
4. **Error:** any token except the preview token; invalid/expired copy and retry.

The 900ms transition is simulated and cleaned up on unmount. This is not real enrollment.

### 5.11 Employees

**Entry:** Organization & Identity → Employees.

No seeded records. Table columns: Employee Number, Full Name, Job Title, Home Branch, Phone, Hire Date, Status, Actions. Actions: Edit Employee; soft Activate/Deactivate.

#### Add/Edit Employee

- Home Branch: required select; current workspace branch is the only preview option.
- Employee Number: required; unique within selected branch among local records.
- Full Name, Job Title, Hire Date: required.
- Email: optional; format validation.
- Phone: optional.
- Status: Active/Inactive.
- Address: line1 required; line2 optional; city required; region/postal optional; country code exactly 2, default `EG`.
- All operations local-only; no deletion.

### 5.12 User Accounts & Access

**Entry:** Organization & Identity → User Accounts & Access.

Initial state preserves backend-unavailable empty table. Optional **Show locked account preview** reveals an explicitly non-backend row.

Table: Employee, Employee Number, Role, Branch Scope, Account Status, Actions. Actions: Edit; Reset Password; Revoke Active Sessions. Security actions show preview-only notice and never claim backend success.

Locked row: warning badge “Temporarily locked,” helper “Failed login attempts.” Preview row is labelled “UI preview · Not backend data.”

#### Create/Edit User Account

- Employee: required; options are eligible employees only (those without accounts). Current employee backend array is empty.
- One account per employee enforced locally.
- Role options exactly `Admin`, `Pharmacist`, `Cashier`.
- Admin scope options: `ALL`, `ASSIGNED`.
- Pharmacist/Cashier scope options: only `ASSIGNED`; role change forces ASSIGNED.
- ASSIGNED requires ≥1 permitted branch.
- Branches use button multi-select; current workspace branch is preview option.
- No password field. No backend account, password, role, or session operation occurs.

### 5.13 AI Assistant

Topbar **Ask Forge AI** opens 420px right drawer with scrim. Header status is **Offline guidance**. Purple context states internet assistant unavailable and template explanations remain possible. Conversation is static/template content; composer send has no submit behavior.

Recommendation says quantity must be confirmed from backend. Review purchase order opens `ApprovalModal`. Copy says explicit approval creates a draft only.

### 5.14 Recommendation Review and Approval

- Overview recommendation review uses a generic modal with product, risk, proposed quantity, explanation, and disabled approval when quantity is absent.
- `ApprovalModal` shows AI-proposed action, control notice, draft PO action, fixture product/details, reasoning and risk. Footer: Cancel, Reject, Approve & create draft.
- Human approval is mandatory. Automatic purchase execution is prohibited.
- Modal focus trap, Escape behavior, pending/error/retry states **Need verification**.

### 5.15 Design System & Frontend Handoff

**Entry:** Analysis → Design System. In-app summary of tokens, layouts, screens, components, AI patterns, implementation guidance and handoff tables. Download Markdown creates a Blob from this file and downloads `forgeerp-design-system.md`.

---

## 6. Forms and business rules

### Verified cross-form rules

- Required/optional labels are visible; invalid fields get danger border and inline error.
- Product tax is entered as percent and normalized to decimal in local saved draft.
- Product lot-tracking toggle must be locked when activity exists; current unavailable activity state locks conservatively.
- UOM: exactly one base when rows exist; base factor 1; all factors >0; used factors locked.
- Reorder maximum ≥ reorder point.
- Adjustment quantity >0; outbound unit cost disabled; inbound/opening cost required non-negative.
- Batch and expiry are paired when either is entered.
- Branch code unique locally; Employee number unique per branch; Category code unique locally; Employee has at most one account.
- Roles/scopes are constrained exactly as documented above.
- Enrollment tokens are temporary/one-time in copy; current tokens are mock preview values.

### Needs verification

- Server-side uniqueness and concurrency.
- Canonical money/quantity precision and rounding.
- Time zone/date formatting.
- Batch-required rule from actual product configuration.
- Token TTL and clipboard/error behavior.
- Whether Product Description is optional in backend schema.
- Save APIs, optimistic updates, rollback, and global notifications.

---

## 7. AI and approval workflow

1. Display signal/evidence and data availability.
2. Show recommendation as a proposal, never an executed action.
3. User selects Review Recommendation.
4. Review shows product, risk, explanation, quantity when available.
5. Missing required data disables approval.
6. Explicit approval creates a **draft** action only.
7. Any downstream submission/order execution requires a separate verified flow.

AI visual language: purple accent/soft background and sparkle icon. Semantic risk uses danger/warning/success only when risk is assessed. Unassessed risk uses neutral/warning text. Sources should be visible when known. Confidence must never be fabricated.

---

## 8. Data availability and preview-state rules

| Classification | Presentation | Examples |
|---|---|---|
| Static fixture | Existing hard-coded values; label in documentation, not necessarily UI | Products, legacy Inventory Overview, Sales, Purchasing |
| Local preview | Explicit local-only notice; resets on reload | Branches, Employees, Categories, Accounts |
| UI preview/mock | Prominent “Preview / Not valid / Not backend data” | Enrollment token, locked account row, enrollment setup |
| Backend unavailable | “Unavailable,” explanatory notice, no zeros | Balances, batches, ledger, demand forecast, AI summary |
| Actual zero | Only render numeric `0` when explicitly supplied | Fixture Salbutamol inventory is a fixture zero, not backend proof |

Never infer that an empty array means zero records. Never infer `AVAILABLE`, lot status, unit, quantity, cost, forecast, employee eligibility, or account lock from missing data.

---

## 9. Frontend implementation guidance

### Component hierarchy

```text
App
├─ ForgeSidebar
├─ Topbar
├─ active page
│  ├─ Page heading pattern
│  ├─ Card / toolbar / notices
│  ├─ Table primitives / forms / tabs
│  └─ local modal(s)
├─ AssistantChatPanel
└─ Approval / recommendation modal
```

- Reuse primitives from `design-system.tsx`; do not create page-specific raw buttons/inputs/selects.
- Keep page-specific state/presentation in page modules. Data integration should replace fixture/local arrays behind the same view model rather than rewriting markup.
- Keep data normalization at form boundary (example: tax percent → decimal).
- Use semantic CSS variables, spacing tokens and status colors.
- Preserve labels and `aria-label` for icon-only controls; use `aria-expanded`, `aria-checked`, `aria-pressed`, `aria-live` where already demonstrated.
- Add `aria-sort`, dialog focus trap/return, Escape dismissal, and reduced-motion support before production.
- Keep numeric columns right aligned.
- Preserve horizontal table overflow and modal vertical scrolling.
- Treat current 1180px minimum as the supported baseline; do not claim mobile support.

### Validation architecture

Current forms use controlled local state and `Partial<Record<keyof Form,string>>` errors. Clear a field error on edit; validate on primary action; render error immediately below. Backend validation must be merged without replacing client rules. Do not report success until the backend confirms it.

### Integration boundary

Recommended separation without changing visual components:

```text
page view → typed view model → form/state hook → service/repository → API
```

Keep fixture, local-preview and backend models distinct. Use explicit loading/error/unavailable states, not falsy coercion.

---

## 10. Verification checklist

- [ ] Mahmoud Ragab is the only logged-in identity.
- [ ] All `--color-*`, spacing, radius, font and shadow tokens match source.
- [ ] Sidebar 248px, topbar 66px, content max 1440px at supported desktop widths.
- [ ] Every implemented page/tab/modal above is represented.
- [ ] Products table/search/filter/pagination remain operational beside Categories Tree.
- [ ] Tax input shows percent; normalized draft stores decimal.
- [ ] UOM and reorder constraints are enforced.
- [ ] Balance table never edits quantities or substitutes unavailable with zero.
- [ ] FEFO and NON-LOT conditional logic remain intact.
- [ ] Adjustment OUT disables unit cost.
- [ ] Branch/employee/account uniqueness rules remain intact.
- [ ] Non-admin accounts can never select ALL.
- [ ] Password reset/session revoke/token actions remain preview-only without backend.
- [ ] AI recommendation cannot execute automatically.
- [ ] Empty, loading, error, disabled, preview and unavailable states are tested.
- [ ] Keyboard/focus/contrast checks are completed before release.

---

## 11. Open questions and unresolved details

1. Mobile/tablet designs and sidebar behavior.
2. URL routes, deep links and browser history.
3. Backend schemas/endpoints, persistence, authorization and concurrency.
4. Exact server validation, precision, currency and locale rules.
5. Modal/drawer focus trap, focus return and Escape behavior.
6. Dynamic chart library, tooltips, axes and confidence computation.
7. AI loading/error/retry and approval pending/error/retry.
8. Category descendant-cycle prevention.
9. Product barcode server uniqueness.
10. Real employee/branch directories for selectors.
11. Account lock duration and reset semantics.
12. Enrollment token TTL, format, copy failure and redemption flow.
13. Purchasing success copy conflicts with draft-only approval and must be corrected before production.
14. Static fixture values must be replaced or explicitly demo-labelled before production.
