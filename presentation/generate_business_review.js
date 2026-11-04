// Independently authored Product and Commercial Review presentation.
// This file uses only new text and native PowerPoint shapes. It does not read
// the former Business Review deck, its template, its fonts, or its assets.
const pptxgen = require('pptxgenjs');

const output = process.argv[2];
if (!output) throw new Error('Usage: node generate_business_review.js OUTPUT.pptx');

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = '';
pptx.subject = 'Evidence-based product and commercial review';
pptx.title = 'DrillLoop Product and Commercial Review - Independent replacement';
pptx.company = '';
pptx.lang = 'en-US';
pptx.theme = {
  headFontFace: 'Noto Sans',
  bodyFontFace: 'Noto Sans',
  lang: 'en-US',
};
pptx.defineLayout({ name: 'DRILLLOOP_WIDE', width: 13.333, height: 7.5 });
pptx.layout = 'DRILLLOOP_WIDE';

const C = {
  paper: 'F6F4EF',
  card: 'FFFEFB',
  ink: '1D2A35',
  muted: '566571',
  line: 'D8D9D5',
  blue: '285F9E',
  bluePale: 'E6EEF7',
  green: '287568',
  greenPale: 'E4F0EA',
  rust: 'A95635',
  rustPale: 'F5E8E0',
  dark: '172A3A',
  white: 'FFFFFF',
};
const FONT = 'Noto Sans';
const W = 13.333;
const H = 7.5;

function addText(slide, value, x, y, w, h, options = {}) {
  slide.addText(value, {
    x, y, w, h,
    fontFace: FONT,
    fontSize: 13,
    color: C.ink,
    margin: 0,
    breakLine: false,
    fit: 'shrink',
    valign: 'mid',
    paraSpaceAfterPt: 0,
    ...options,
  });
}

function rect(slide, x, y, w, h, fill, line = fill, radius = 0.12) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, rectRadius: radius,
    fill: { color: fill },
    line: { color: line, width: 0.8 },
  });
}

function rule(slide, x, y, w, color = C.line, width = 1) {
  slide.addShape(pptx.ShapeType.line, { x, y, w, h: 0, line: { color, width } });
}

function standardSlide(section, number, title, subtitle) {
  const slide = pptx.addSlide();
  slide.background = { color: C.paper };
  addText(slide, 'DRILLLOOP  /  ' + section.toUpperCase(), 0.72, 0.25, 9.5, 0.25,
    { fontSize: 9, bold: true, charSpacing: 1.1, color: C.blue });
  addText(slide, String(number).padStart(2, '0'), 12.05, 0.23, 0.55, 0.28,
    { fontSize: 10, bold: true, color: C.muted, align: 'right' });
  rule(slide, 0.72, 0.62, 11.9, C.line, 0.8);
  addText(slide, title, 0.72, 0.83, 11.8, 0.58,
    { fontSize: 26, bold: true, color: C.ink, valign: 'mid' });
  addText(slide, subtitle, 0.74, 1.47, 11.75, 0.48,
    { fontSize: 12, color: C.muted, valign: 'top' });
  rule(slide, 0.72, 6.98, 11.9, C.line, 0.6);
  addText(slide, 'Product evidence and hypotheses  /  Not a deployment approval',
    0.74, 7.06, 10.7, 0.18, { fontSize: 8, color: C.muted });
  return slide;
}

function cardTitle(slide, title, x, y, w, color = C.ink) {
  addText(slide, title, x, y, w, 0.34, { fontSize: 15, bold: true, color });
}

function note(slide, text) {
  slide.addNotes(text);
}

// 1. Cover: a new editorial opening, built from typography and a single rule.
{
  const slide = pptx.addSlide();
  slide.background = { color: C.dark };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0.82, y: 0.9, w: 0.12, h: 5.65,
    fill: { color: '71B8A5' }, line: { color: '71B8A5', transparency: 100 },
  });
  addText(slide, 'DRILLLOOP  /  DECISION BRIEF', 1.25, 1.12, 7.2, 0.3,
    { fontSize: 10, bold: true, charSpacing: 1.3, color: 'A8D2C4' });
  addText(slide, 'Product and\ncommercial review', 1.22, 2.0, 10.5, 1.55,
    { fontSize: 36, bold: true, color: C.white, valign: 'mid', breakLine: false });
  addText(slide, 'A factual review of the working demo, its evidence limits, and the questions to answer next.',
    1.27, 3.92, 8.9, 0.82, { fontSize: 18, color: 'D5E0E5', valign: 'top' });
  rule(slide, 1.27, 5.12, 8.9, '54707F', 1);
  addText(slide, 'Current evidence: one fictional exercise fixture', 1.28, 5.38, 8.9, 0.35,
    { fontSize: 12, color: 'B8C7CF' });
  addText(slide, 'No customer, revenue, field-accuracy, or deployment claim is established.',
    1.28, 5.83, 9.8, 0.35, { fontSize: 12, color: 'B8C7CF' });
  addText(slide, 'Independent replacement presentation', 1.28, 6.76, 8.9, 0.25,
    { fontSize: 9, color: '92A7B2' });
  note(slide, 'This is an evidence-based product and commercial review for discussion. The local demo is a working prototype, and all packaged exercise evidence is fictional. The repository does not establish customers, revenue, measured evaluator time savings, real-world accuracy, or approval to deploy.');
}

// 2. Current state.
{
  const slide = standardSlide('Current state', 2, 'A working local demo; market proof is still open',
    'Separate what the repository demonstrates from the claims that still need outside evidence.');
  const items = [
    ['01', 'Local workflow', 'Exercise setup, evidence intake, source-linked review, corrective actions, and report export are implemented in the demo.', C.blue, C.bluePale],
    ['02', 'Evidence base', 'The packaged example is fictional. Current measured matching results come from one deliberately constructed fixture.', C.green, C.greenPale],
    ['03', 'Commercial status', 'No customer use, paid pilot, purchase decision, workload reduction, or willingness to pay is documented.', C.rust, C.rustPale],
  ];
  items.forEach((item, i) => {
    const x = 0.74 + i * 4.02;
    rect(slide, x, 2.25, 3.72, 2.7, C.card, C.line);
    rect(slide, x + 0.22, 2.5, 0.53, 0.46, item[4], item[4]);
    addText(slide, item[0], x + 0.22, 2.55, 0.53, 0.3, { fontSize: 11, bold: true, color: item[3], align: 'center' });
    cardTitle(slide, item[1], x + 0.22, 3.18, 3.22);
    addText(slide, item[2], x + 0.22, 3.65, 3.22, 1.0, { fontSize: 12, color: C.muted, valign: 'top', breakLine: false });
  });
  rect(slide, 0.74, 5.33, 11.78, 1.15, C.bluePale, C.bluePale);
  addText(slide, 'Review boundary', 1.02, 5.55, 1.85, 0.3, { fontSize: 12, bold: true, color: C.blue });
  addText(slide, 'A successful demo run is not evidence of customer demand, deployment readiness, or performance on unfamiliar records.',
    2.9, 5.47, 9.2, 0.55, { fontSize: 13, color: C.ink });
  note(slide, 'The README describes a functional local demo and explicitly labels the packaged hospital scenario fictional. The recorded synthetic fixture checks expected rows, labels, and source IDs; it is not an independent evaluation. There is no documented customer interview, paid pilot, user workload study, real-evidence validation, or production authorization.');
}

// 3. Original evidence-review trail diagram.
{
  const slide = standardSlide('Product workflow', 3, 'The product is a review trail, not an auto-approval system',
    'Each proposal should remain tied to its source and to a human decision.');
  const steps = [
    ['1', 'Source record', 'File plus row, line, page, or segment'],
    ['2', 'Observation', 'What the record says'],
    ['3', 'Proposed finding', 'Interpretation with uncertainty'],
    ['4', 'Human review', 'Authorized reviewer decides'],
    ['5', 'Closure proof', 'Reviewer checks completion evidence'],
  ];
  const x0 = 0.76, gap = 0.25, cw = 2.15;
  steps.forEach((s, i) => {
    const x = x0 + i * (cw + gap);
    rect(slide, x, 2.58, cw, 2.08, C.card, C.line);
    slide.addShape(pptx.ShapeType.ellipse, {
      x: x + 0.16, y: 2.78, w: 0.39, h: 0.39,
      fill: { color: i === 3 ? C.green : C.blue },
      line: { color: i === 3 ? C.green : C.blue, transparency: 100 },
    });
    addText(slide, s[0], x + 0.16, 2.83, 0.39, 0.25, { fontSize: 10, bold: true, color: C.white, align: 'center' });
    addText(slide, s[1], x + 0.17, 3.35, cw - 0.34, 0.36, { fontSize: 14, bold: true, color: C.ink });
    addText(slide, s[2], x + 0.17, 3.83, cw - 0.34, 0.55, { fontSize: 10, color: C.muted, valign: 'top' });
    if (i < steps.length - 1) {
      rule(slide, x + cw, 3.54, gap, C.blue, 1.5);
    }
  });
  rect(slide, 0.76, 5.15, 11.78, 1.0, C.greenPale, C.greenPale);
  addText(slide, 'Human gate', 1.02, 5.42, 1.45, 0.28, { fontSize: 12, bold: true, color: C.green });
  addText(slide, 'Drafts stay proposed until an authorized reviewer acts. An action stays open until closure evidence is reviewed.',
    2.57, 5.31, 9.3, 0.5, { fontSize: 13, color: C.ink });
  note(slide, 'The product design separates source wording from interpretation and leaves finding approval or rejection to a human reviewer. Source locators preserve filenames and row, line, page, or transcript-segment references. Corrective actions require an owner and acceptance criteria where applicable, and a reviewer checks completion evidence before closure.');
}

// 4. Capabilities grounded in the current product documentation.
{
  const slide = standardSlide('Product workflow', 4, 'What the current demo supports',
    'A bounded, local-first workflow over the evidence types described in the project documentation.');
  const rows = [
    ['A', 'Set up an exercise', 'Record objectives, targets, teams, and the review context.'],
    ['B', 'Bring in evidence', 'Import notes, CSV logs, JSON records, and selectable-text PDFs.'],
    ['C', 'Review proposals', 'Inspect linked source passages, conflicting times, and unknown details.'],
    ['D', 'Track follow-through', 'Assign action fields, record closure proof, and export a report.'],
  ];
  rows.forEach((r, i) => {
    const y = 2.16 + i * 0.91;
    rect(slide, 0.78, y, 11.7, 0.72, C.card, C.line);
    rect(slide, 0.96, y + 0.13, 0.46, 0.44, [C.bluePale, C.greenPale, C.rustPale, C.bluePale][i], [C.bluePale, C.greenPale, C.rustPale, C.bluePale][i]);
    addText(slide, r[0], 0.96, y + 0.17, 0.46, 0.3, { fontSize: 11, bold: true, color: [C.blue, C.green, C.rust, C.blue][i], align: 'center' });
    addText(slide, r[1], 1.68, y + 0.12, 2.6, 0.3, { fontSize: 13, bold: true });
    addText(slide, r[2], 4.25, y + 0.12, 7.86, 0.45, { fontSize: 11.5, color: C.muted });
  });
  addText(slide, 'The default analysis uses local deterministic rules; optional speech and writing-model paths are separate and were not part of the cited fixture result.',
    0.84, 6.05, 11.5, 0.5, { fontSize: 11, color: C.muted, valign: 'top' });
  note(slide, 'The project README documents TXT and Markdown notes, CSV event logs, JSON event or transcript records, and selectable-text PDFs. The application uses fixed local rules for its default analysis. Optional speech transcription and local text drafting have separate prerequisites and were not used in the reported benchmark.');
}

// 5. Narrow, accurately bounded synthetic results.
{
  const slide = standardSlide('Evidence', 5, 'The recorded fixture checks pipeline wiring',
    'All three counts refer to one closed fictional exercise dataset.');
  const metrics = [
    ['8 / 8', 'expected event-log rows found', 'Row-presence check'],
    ['5 / 5', 'expected finding labels proposed', 'Closed label set'],
    ['9 / 9', 'expected source IDs linked', 'ID-presence check'],
  ];
  metrics.forEach((m, i) => {
    const x = 0.82 + i * 4.0;
    rect(slide, x, 2.3, 3.65, 2.18, C.card, C.line);
    addText(slide, m[0], x + 0.24, 2.62, 3.15, 0.62,
      { fontSize: 30, bold: true, color: [C.blue, C.green, C.rust][i] });
    addText(slide, m[1], x + 0.24, 3.39, 3.15, 0.5, { fontSize: 12, bold: true, color: C.ink, valign: 'top' });
    addText(slide, m[2], x + 0.24, 4.02, 3.15, 0.22, { fontSize: 9, color: C.muted });
  });
  rect(slide, 0.82, 4.92, 11.65, 1.18, C.rustPale, C.rustPale);
  addText(slide, 'Limit', 1.1, 5.17, 0.75, 0.3, { fontSize: 12, bold: true, color: C.rust });
  addText(slide, 'A linked identifier does not prove that a source supports a claim. No unfamiliar exercise or representative evaluator study is included.',
    2.0, 5.08, 9.9, 0.55, { fontSize: 12, color: C.ink });
  note(slide, 'The project records a single synthetic fixture with 8 of 8 expected log rows, 5 of 5 expected finding codes, and 9 of 9 expected evidence IDs present. The fixture is closed and deliberately constructed for the implementation. Presence of a source ID is not semantic evidence that the source supports the interpretation; the numbers do not establish accuracy on unseen or real exercise records.');
}

// 6. Explicit evidence gaps.
{
  const slide = standardSlide('Evidence', 6, 'The next proof points are still unmeasured',
    'No numerical market or field-performance claim should be inferred from the demo.');
  const left = [
    'Use with permitted real exercise records',
    'Evaluator corrections and source-support judgments',
    'Preparation time compared with current practice',
  ];
  const right = [
    'Customer demand, buyer, and procurement route',
    'Willingness to pay, delivery cost, or revenue',
    'Real-audio transcription and unfamiliar-case performance',
  ];
  rect(slide, 0.82, 2.25, 5.55, 3.35, C.card, C.line);
  rect(slide, 6.65, 2.25, 5.55, 3.35, C.card, C.line);
  cardTitle(slide, 'Product evidence to collect', 1.1, 2.55, 4.9, C.blue);
  cardTitle(slide, 'Commercial evidence to collect', 6.93, 2.55, 4.9, C.rust);
  left.forEach((v, i) => {
    const y = 3.15 + i * 0.75;
    slide.addShape(pptx.ShapeType.ellipse, { x: 1.12, y: y + 0.07, w: 0.16, h: 0.16, fill: { color: C.blue }, line: { color: C.blue } });
    addText(slide, v, 1.42, y, 4.55, 0.5, { fontSize: 12, color: C.ink, valign: 'top' });
  });
  right.forEach((v, i) => {
    const y = 3.15 + i * 0.75;
    slide.addShape(pptx.ShapeType.ellipse, { x: 6.95, y: y + 0.07, w: 0.16, h: 0.16, fill: { color: C.rust }, line: { color: C.rust } });
    addText(slide, v, 7.25, y, 4.55, 0.5, { fontSize: 12, color: C.ink, valign: 'top' });
  });
  addText(slide, 'Treat each item as unknown until a permitted review produces evidence.',
    0.92, 5.95, 11.3, 0.35, { fontSize: 12, bold: true, color: C.muted });
  note(slide, 'The documented gaps include no permitted-real-record evaluation, evaluator workload timing, correction study, real-audio accuracy result, customer interview, paid pilot, or willingness-to-pay evidence. Treat each as unknown. Any future measurement needs a participant-approved data scope and a comparison method agreed before results are collected.');
}

// 7. User and buying roles.
{
  const slide = standardSlide('Market hypothesis', 7, 'A first user segment is proposed, not validated',
    'The product concept starts with hospital tabletop exercise review.');
  rect(slide, 0.86, 2.28, 5.3, 3.35, C.bluePale, C.bluePale);
  addText(slide, 'PROPOSED FIRST USER', 1.18, 2.62, 3.9, 0.28, { fontSize: 10, bold: true, charSpacing: 0.8, color: C.blue });
  addText(slide, 'Hospital preparedness\nevaluator', 1.18, 3.13, 4.45, 1.0, { fontSize: 24, bold: true, color: C.ink, valign: 'top' });
  addText(slide, 'Reviewing records from a tabletop exercise', 1.2, 4.55, 4.3, 0.48, { fontSize: 12, color: C.muted, valign: 'top' });
  const roles = [
    ['Report preparer', 'Evaluator or preparedness staff member is a likely role.'],
    ['Approver', 'Preparedness lead or exercise sponsor is a candidate.'],
    ['Budget owner', 'Unknown in the repository evidence.'],
    ['Procurement route', 'Unknown in the repository evidence.'],
  ];
  roles.forEach((r, i) => {
    const y = 2.34 + i * 0.8;
    rect(slide, 6.55, y, 5.65, 0.65, C.card, C.line);
    addText(slide, r[0], 6.82, y + 0.12, 1.8, 0.24, { fontSize: 10, bold: true, color: C.blue });
    addText(slide, r[1], 8.65, y + 0.09, 3.25, 0.42, { fontSize: 10, color: C.ink });
  });
  note(slide, 'The Idea Document names hospital preparedness evaluators reviewing tabletop exercises as the initial segment hypothesis. It describes a likely report preparer and candidate approver but explicitly says the budget owner and procurement path are unknown. Other sectors remain hypotheses, not established customer segments.');
}

// 8. Commercial hypotheses.
{
  const slide = standardSlide('Market hypothesis', 8, 'The commercial model has no validated inputs',
    'A per-exercise pilot fee is a question to investigate, not a price or offer.');
  const headers = [['Option', 0.96, 2.25], ['Current evidence', 4.04, 2.55], ['Question before modeling', 7.08, 4.7]];
  headers.forEach(([t, x, w]) => addText(slide, t, x, 2.3, w, 0.32, { fontSize: 11, bold: true, color: C.muted }));
  const rows = [
    ['Per-exercise pilot', 'First model to investigate; no price set', 'Who buys, what approval route applies, and what delivery work is required?'],
    ['Organization subscription', 'Later hypothesis; not priced', 'What exercise volume, support, renewal, and user roles would be needed?'],
    ['Private deployment', 'Later hypothesis; not costed', 'What hosting, identity, security, and operations requirements apply?'],
  ];
  rows.forEach((r, i) => {
    const y = 2.82 + i * 1.02;
    rect(slide, 0.84, y, 11.7, 0.82, C.card, C.line);
    addText(slide, r[0], 1.02, y + 0.14, 2.7, 0.5, { fontSize: 12, bold: true });
    addText(slide, r[1], 4.04, y + 0.12, 2.64, 0.52, { fontSize: 10.5, color: C.muted });
    addText(slide, r[2], 7.08, y + 0.1, 5.1, 0.56, { fontSize: 10.5, color: C.ink });
  });
  addText(slide, 'No price, customer volume, revenue, delivery cost, or staffing forecast is established.',
    0.92, 6.14, 11.3, 0.35, { fontSize: 12, bold: true, color: C.rust });
  note(slide, 'The Business Case identifies a per-exercise pilot fee as the first model to investigate and leaves its price unset. Annual subscriptions and private deployment are later hypotheses. No buyer, procurement route, customer volume, revenue, delivery cost, staffing plan, or willingness-to-pay measure is established; do not present a forecast as validated.');
}

// 9. Positioning without superiority claims.
{
  const slide = standardSlide('Market hypothesis', 9, 'Test the connected review trail against current practice',
    'The project materials recognize that reporting and follow-up workflows already exist.');
  rect(slide, 0.88, 2.34, 5.42, 2.62, C.card, C.line);
  cardTitle(slide, 'What is already familiar', 1.18, 2.68, 4.8, C.muted);
  addText(slide, 'After-action reporting and corrective-action tracking are established workflow categories.',
    1.18, 3.22, 4.55, 0.74, { fontSize: 16, color: C.ink, valign: 'top' });
  addText(slide, 'A report template alone is not a unique product claim.',
    1.18, 4.2, 4.55, 0.42, { fontSize: 11, color: C.muted });
  rect(slide, 6.72, 2.34, 5.42, 2.62, C.greenPale, C.greenPale);
  cardTitle(slide, 'What DrillLoop will test', 7.02, 2.68, 4.8, C.green);
  addText(slide, 'Source passage -> proposed finding -> reviewer decision -> checked closure evidence',
    7.02, 3.22, 4.55, 0.82, { fontSize: 16, bold: true, color: C.ink, valign: 'top' });
  addText(slide, 'Value and distinctiveness remain unvalidated.',
    7.02, 4.2, 4.55, 0.42, { fontSize: 11, color: C.muted });
  addText(slide, 'Compare both workflows on the same permitted records and ask evaluators where they correct or reject proposals.',
    1.0, 5.45, 11.1, 0.58, { fontSize: 13, color: C.ink });
  note(slide, 'The project materials recognize that after-action reporting and corrective-action workflows exist in other products. DrillLoop should not claim those categories are unique. Its differentiator hypothesis is that the source-to-claim-to-review-to-closure trail is useful; a paired workflow comparison is needed to test that hypothesis.');
}

// 10. Operating and safety boundary.
{
  const slide = standardSlide('Operating boundary', 10, 'The demo boundary is narrower than an approved service',
    'Keep data fictional or explicitly permitted until owners approve operational controls.');
  const blocks = [
    ['LOCAL-FIRST', 'The default deterministic path needs no cloud model API.'],
    ['SYNTHETIC', 'The packaged exercise records are fictional demonstration data.'],
    ['HUMAN REVIEW', 'Proposals are not approved findings; reviewers decide.'],
    ['NOT PRODUCTION', 'Identity, hosting, retention, and security operations still need owner approval.'],
  ];
  blocks.forEach((b, i) => {
    const x = 0.84 + (i % 2) * 5.95;
    const y = 2.3 + Math.floor(i / 2) * 1.53;
    rect(slide, x, y, 5.55, 1.18, C.card, C.line);
    addText(slide, b[0], x + 0.24, y + 0.21, 1.65, 0.3,
      { fontSize: 10, bold: true, charSpacing: 0.3, color: [C.blue, C.green, C.rust, C.blue][i] });
    addText(slide, b[1], x + 1.95, y + 0.16, 3.25, 0.72,
      { fontSize: 11.5, color: C.ink });
  });
  rect(slide, 0.84, 5.72, 11.5, 0.56, C.rustPale, C.rustPale);
  addText(slide, 'No staging or production approval is evidenced by this product review.',
    1.05, 5.84, 10.9, 0.28, { fontSize: 12, bold: true, color: C.rust, align: 'center' });
  note(slide, 'The repository describes a local-first demo with no required cloud model API in its default analysis path, and it labels the packaged evidence fictional. Human reviewers approve or reject findings and close actions. The available local implementation and rehearsals do not establish approved organizational staging or production operations; hosting, identity, data handling, scanner, monitoring, and service ownership remain separate decisions.');
}

// 11. Evidence plan.
{
  const slide = standardSlide('Next evidence', 11, 'A small discovery sequence can answer concrete questions',
    'Each step depends on participant permission and a defined evidence scope.');
  const phases = [
    ['01', 'Listen', 'Interview prospective evaluators; map users, approvers, current tools, and permitted records.'],
    ['02', 'Compare', 'Review the same approved records with current practice and DrillLoop.'],
    ['03', 'Measure', 'Record review time, corrections, citation support, and action-field completeness.'],
    ['04', 'Decide', 'Agree thresholds with participants before testing an unfamiliar exercise or proposing a pilot.'],
  ];
  phases.forEach((p, i) => {
    const y = 2.18 + i * 0.92;
    rect(slide, 0.88, y, 11.55, 0.72, C.card, C.line);
    addText(slide, p[0], 1.1, y + 0.13, 0.55, 0.36, { fontSize: 16, bold: true, color: [C.blue, C.green, C.rust, C.blue][i] });
    addText(slide, p[1], 1.92, y + 0.14, 1.32, 0.32, { fontSize: 13, bold: true });
    addText(slide, p[2], 3.36, y + 0.11, 8.65, 0.46, { fontSize: 11.2, color: C.muted });
  });
  addText(slide, 'This is a proposed learning plan, not a confirmed partner, schedule, or pilot commitment.',
    1.0, 6.12, 11.0, 0.36, { fontSize: 12, bold: true, color: C.muted });
  note(slide, 'The proposed sequence is to interview two or three prospective hospital preparedness evaluators, observe current work only with permission, then compare both workflows using the same permitted records. Measure time and reviewer corrections without assuming savings. If approved unfamiliar records become available, test generalization and agree thresholds with participants before the test. No partner, schedule, or pilot commitment is confirmed.');
}

// 12. Decision requested.
{
  const slide = standardSlide('Decision', 12, 'Authorize learning before asking for a pilot',
    'The immediate decision concerns discovery scope and evidence permissions.');
  rect(slide, 0.88, 2.35, 7.15, 3.55, C.bluePale, C.bluePale);
  addText(slide, 'REQUESTED DECISION', 1.22, 2.72, 4.2, 0.3,
    { fontSize: 10, bold: true, charSpacing: 0.8, color: C.blue });
  addText(slide, 'Decide whether to authorize discovery and design a paired review for the hospital tabletop use case.',
    1.22, 3.25, 6.25, 1.12, { fontSize: 22, bold: true, color: C.ink, valign: 'top' });
  addText(slide, 'First confirm participant roles, evidence permissions, and the comparison measures.',
    1.24, 4.82, 6.2, 0.55, { fontSize: 12, color: C.muted, valign: 'top' });
  rect(slide, 8.42, 2.35, 3.72, 3.55, C.card, C.line);
  cardTitle(slide, 'Not requested here', 8.72, 2.72, 3.1, C.rust);
  const out = ['Production deployment', 'Scale-up decision', 'Validated business case'];
  out.forEach((v, i) => addText(slide, v, 8.76, 3.35 + i * 0.62, 2.95, 0.36, { fontSize: 12, color: C.ink }));
  addText(slide, 'No response is implied; an owner must record the decision.',
    0.98, 6.19, 11.15, 0.32, { fontSize: 11, bold: true, color: C.muted });
  note(slide, 'The requested decision is whether to authorize discovery and design a paired review for the hospital tabletop use case. Before any real records are used, confirm participant consent and evidence permissions. This request does not seek production deployment, scale-up, a price approval, or confirmation of a validated business case. Record the owner decision explicitly; silence is not approval.');
}

if (pptx._slides.length !== 12) throw new Error(`Expected 12 slides; got ${pptx._slides.length}`);
pptx.writeFile({ fileName: output });
