# AI Prophecy Court - Design Reference

## Visual system

- Direction: editorial-monocle, reinterpreted as an enchanted legal broadsheet.
- Background: warm parchment `oklch(94% 0.025 88)`.
- Surface: pale vellum `oklch(98% 0.012 88)`.
- Ink: near-black `oklch(18% 0.018 70)`.
- Muted ink: `oklch(43% 0.018 72)`.
- Border: aged rule `oklch(75% 0.035 82)`.
- Primary accent: acidic fungal green `oklch(72% 0.18 118)`.
- Detail accent: tarnished gold `oklch(62% 0.09 82)`.
- Display: Iowan Old Style / Charter / Georgia.
- Body: system sans.
- Metadata: JetBrains Mono / ui-monospace.
- Shape language: square editorial panels, clipped paper corners, engraved rules, wax-like seals. No generic rounded SaaS cards.
- Motion: one staged court-opening sequence, evidence stamp transitions, transcript cursor, and restrained audience-meter movement.

## Page A - Case Lobby

Reference composition: Sunday broadsheet front page crossed with a court docket.

- Narrow masthead with live court status and archive navigation.
- Hero claim occupies two-thirds of the first viewport as a sealed legal notice.
- Right rail holds the next session time, evidence count, and the primary "Convene the Court" action.
- Company and leader filters behave like indexed docket tabs.
- Recent evidence appears as tactile clipped documents, not a generic card grid.
- Responsive shift: the hero rail drops below the claim; docket filters become a horizontally scrollable tab strip; evidence becomes a single-column reading stack.

## Page B - Trial Chamber

Reference composition: courtroom proscenium crossed with a live intelligence terminal.

- Top bench contains the case number, timer, source integrity, and chamber controls.
- Three engraved characters occupy a narrow theatrical frieze: Judge Mycelia, Prosecutor Thorn, Witness 2030.
- Center column is the live cross-examination transcript and source evidence timeline.
- Left column holds the accused claim and source facts.
- Right column holds audience reaction, witness controls, and objections.
- The core 3-minute demo flow is explicit: open court, reveal evidence, call witness, challenge evidence, render verdict.
- Responsive shift: controls become a sticky bottom action bar; character frieze becomes horizontally scrollable; evidence timeline moves below transcript.

## Page C - Verdict Archive

Reference composition: rare-book folio wall crossed with collectible judicial certificates.

- Lead verdict is large and editorial; remaining verdicts form a dense archive wall.
- Every card carries a verdict seal, roast excerpt, credibility and hype measures, cited sources, and replay/share actions.
- Filters use archival index language: company, year, verdict class.
- No generic dashboard chart. Metrics are expressed as ruled scales, stamps, and annotated evidence counts.
- Responsive shift: archive wall becomes a one-column folio stack with actions pinned to each card footer.

## Evidence policy

- Real links are marked `VERIFIED SOURCE` and point directly to public X or LinkedIn pages.
- Synthetic transcript excerpts and future-witness testimony are marked `DEMO EVIDENCE`.
- Roasts target the public claim and corporate hype language, never personal traits.
- The featured trial uses a clearly labeled composite claim assembled for the demo from public AI timeline discourse.

## Product architecture

- Home: Live Roast Floor.
- Person detail: Individual Dossier.
- Experience: Trial Chamber.
- History: Verdict Archive.
- Core loop: claim appears, the AI court reacts live, the user inspects cited evidence, the user sends the claim to Trial Chamber, and a shareable verdict returns later.

## Primary page - Live Roast Floor

### Design read

A living court docket rather than a conventional dashboard or feed. The page combines the hierarchy of a Sunday broadsheet, the physicality of an evidence clerk's table, and the legibility of a realtime operations surface. Design dials: variance 7, motion 6, density 7.

### Reference composition

1. **Court masthead**
   - Full-width engraved rule with the APC seal at left and the product name set as a newspaper flag.
   - Court status and last evidence refresh sit in the same line as the issue metadata.
   - Search is a real expanding input, followed by text navigation to People and Verdict Archive.
   - On compact screens, the flag remains dominant while status and navigation wrap into two narrow ruled rows.

2. **Featured live case**
   - Occupies the strongest upper-left area at desktop, spanning roughly eight of twelve columns.
   - The claim is set as a large editorial quotation inside an asymmetric legal notice, with speaker, organization, date, and source labels above it.
   - Evidence confidence is shown as a ruled textual finding with a single fungal-green marker, never as a generic chart.
   - Judge Mycelia and Prosecutor Thorn exchange two short generated reactions in a compact transcript strip.
   - The main action, `Send to Trial`, is the only solid fungal-green control in the first viewport.
   - A clipped evidence thumbnail opens an evidence drawer with citation, excerpt, context note, and source link.

3. **Court pulse**
   - A near-black horizontal ribbon sits beside or directly below the lead case.
   - Four sequential AI stages are visible: ingesting evidence, checking context, composing objections, drafting a verdict.
   - One stage is active at a time with restrained cursor motion and descriptive output, making model work visibly load-bearing.
   - The active stage advances automatically and can also be selected manually.

4. **Live docket stream**
   - Presented as a ruled clerk's register, not individual rounded cards.
   - Each row contains speaker and organization, source and timestamp, claim excerpt, one concise court reaction, evidence status, and two actions.
   - A newly arrived row enters with a brief fungal-green wash and `NEW FILING` stamp, then settles into the register.
   - Selecting a row marks it with a left rule and updates the evidence drawer without navigating.

5. **The Accused rail**
   - A narrow indexed directory on the right at wide viewports.
   - Each leader entry shows organization, active claim count, and latest roast state.
   - Selecting a leader filters the docket; the dossier link is present but remains a non-destructive prototype route.
   - Below 1024px, the rail becomes a horizontal indexed strip above the docket.

6. **Filters**
   - Organization, person, source, evidence confidence, and roast status appear as compact legal index controls.
   - Filter changes update the docket count and empty state immediately.
   - `Clear filters` restores the complete register.
   - On mobile, filters open in a modal sheet with 44px minimum targets.

### Interaction-state contract

- **Default:** featured case, active AI pulse stage, complete docket, and accused rail are visible.
- **Loading:** featured case and docket use ruled skeletal text blocks matching final geometry. The loading state can be replayed from the court-status control.
- **Empty:** when filters return no claims, the register becomes a composed clerk notice with a clear-filter action.
- **Selected:** a docket filing receives a strong left rule, `SELECTED FILING` label, and synchronized evidence drawer content.
- **Evidence expanded:** a right-side evidence drawer opens on desktop and a bottom sheet opens on mobile. It includes source classification, confidence rationale, contextual excerpt, direct citation, and explicit `VERIFIED SOURCE` or `DEMO EVIDENCE` labeling.
- **Newly arrived:** a deterministic demo filing enters at the top of the register, announces itself through an aria-live region, and briefly carries a fungal wash and filing stamp.
- **Sent to trial:** the selected claim changes to `ON THE DOCKET`, the action disables, and a confirmation notice identifies Trial Chamber as the next step.
- **Search:** searches speaker, organization, claim, reaction, and source type while preserving active filters.
- **Responsive:** at 1180px the accused rail moves above the register; at 820px the lead case and pulse stack; below 640px metadata collapses into labelled pairs, docket rows become reading blocks, actions become a two-column footer, and the evidence panel becomes a bottom sheet.

### Motion contract

- Initial load stages the masthead rule, lead claim, pulse ribbon, then register rows.
- New filings use one short stamp-and-settle transition.
- Evidence expansion uses opacity and horizontal translation on desktop, vertical translation on mobile.
- The AI pulse cursor and stage marker are the only continuous motion.
- Every transition respects `prefers-reduced-motion`.

## Primary product page - Live Roast Floor

### Product role

The Live Roast Floor is the home surface and the beginning of the core loop:
claim appears, the AI court reacts, the user inspects cited evidence, and the
claim is sent to the Trial Chamber. It must feel like a living court docket,
not an analytics dashboard or social-media feed.

### Reference composition

Reference composition: a financial newspaper's breaking-news front page
overtaken by a procedural court clerk.

- A compact masthead spans the page with the court seal treatment, live court
  status, evidence refresh time, search, and links to People and Verdict
  Archive.
- A ruled filter bar sits directly below the masthead. Organization, person,
  source, evidence confidence, and roast status are real controls. On narrow
  screens they move into a modal filter sheet opened from one persistent
  button.
- The first reading field is an asymmetric 8/4 editorial grid. The featured
  live case occupies the dominant left field. Court Pulse occupies the right
  field as an active procedural log rather than a metric card.
- The featured case is typeset as a legal notice: case number and source status
  above a large claim, speaker and organization beneath, then two short court
  reactions. Evidence confidence is a ruled textual measure, never a generic
  chart. `Send to Trial` is the only filled primary action.
- Below the lead field, the page becomes a 9/3 docket-and-index grid. The live
  docket is a sequence of dense ruled records. `The Accused` is a compact
  indexed rail linking each tracked leader to an Individual Dossier.
- Docket records use no avatars or fake company marks. Identity is carried by
  names, organization labels, source metadata, and legal status language.
- The permitted visual vocabulary for this pass is CSS parchment grain,
  engraved rules, a CSS fungal-border rhythm, and Lucide line icons. Bespoke
  raster assets are omitted without placeholders.

### Docket record anatomy

Every record includes:

1. arrival state, timestamp, and source type;
2. speaker and organization;
3. concise public claim excerpt;
4. one generated court reaction;
5. evidence status and confidence;
6. `Inspect evidence` and `Send to Trial` actions.

The newest record receives a temporary fungal-green arrival rule and a
`NEWLY ENTERED` label. The selected record uses a stronger ink outline and
remains selected while its evidence drawer is open.

### Interaction-state contract

- **Default:** five realistic docket records span all tracked organizations.
  Search and filters update the visible docket and accused rail immediately.
- **Loading:** `Refresh evidence` replaces docket copy with ruled skeleton
  records. Court Pulse advances through ingesting, checking context, composing
  objections, and ready states before restoring content.
- **Empty:** an explicit clerk's notice replaces the docket when filters return
  no claims. `Clear filters` restores the full docket.
- **Selected:** clicking a docket record or `Inspect evidence` selects the
  claim, marks the row, and opens its evidence beneath the claim.
- **Evidence-expanded:** the drawer exposes citation label, source title,
  publication date, context note, confidence explanation, and a traceable
  external URL. Demo excerpts are visibly marked `DEMO EVIDENCE`.
- **Newly arrived:** `Simulate new claim` inserts a new record at the top,
  announces it through an ARIA live region, and gives it a brief arrival
  treatment.
- **Send to Trial:** opens a confirmation dialog summarizing the selected
  claim, evidence count, and court readiness. Confirmation changes the claim's
  status to `QUEUED FOR TRIAL` and updates Court Pulse.
- **Search:** matches speaker, organization, and claim text.
- **Filters:** organization, person, source, evidence confidence, and roast
  status can be combined. Active filters are summarized in the filter bar.
- **People navigation:** each accused entry provides a dossier link path. In
  this scoped pass it preserves the intended URL with a non-destructive notice
  that the dossier screen follows in a later pass.
- **Archive navigation:** preserves the intended archive path with the same
  scoped-page notice.

### Responsive contract

- **1440-1920:** max reading width 1560px; featured case and pulse use an 8/4
  grid, docket and accused rail use 9/3.
- **1024-1366:** featured case and pulse use 7/5; metadata compresses but all
  primary actions stay inline. The accused rail remains visible.
- **768-1023:** featured case and pulse stack; the docket remains full width;
  accused entries become a horizontal indexed strip.
- **600-767:** masthead navigation becomes compact text actions; filters move
  into the modal sheet; docket metadata wraps into two rows.
- **360-599:** navigation moves into a menu sheet, the claim scale uses
  `clamp()`, action groups stack, evidence drawers use a single reading column,
  and no horizontal scrolling is permitted.

### Motion and accessibility

- Initial court opening reveals masthead, featured claim, and docket in three
  restrained stages.
- New evidence and arrival states use opacity, a one-pixel rule sweep, and
  short vertical movement only.
- All motion is removed under `prefers-reduced-motion`.
- Every icon button has a text label or accessible name; focus states use a
  two-pixel ink outline with parchment offset.
- Dialogs trap interaction through the native `dialog` element and return
  focus to the invoking control.
