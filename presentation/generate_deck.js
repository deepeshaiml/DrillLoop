const pptxgen = require('pptxgenjs');
const path = require('path');

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'DrillLoop';
pptx.subject = 'Evidence-backed emergency exercise evaluation';
pptx.title = 'DrillLoop | Eureka Pitch';
pptx.company = 'DrillLoop';
pptx.lang = 'en-US';
pptx.theme = {
  headFontFace: 'Aptos Display', bodyFontFace: 'Aptos', lang: 'en-US'
};
pptx.defineSlideMaster({
  title: 'BASE',
  background: { color: 'F7FAFA' },
  objects: [
    { line: { x: 0.55, y: 7.12, w: 12.22, h: 0, line: { color: 'DCE7E8', width: 0.8 } } },
    { text: { text: 'DRILLLOOP  /  EUREKA', options: { x: 0.58, y: 7.19, w: 4, h: 0.16, fontFace: 'Aptos', fontSize: 7, bold: true, color: '0D8F89', margin: 0 } } },
    { text: { text: 'SYNTHETIC DEMONSTRATION  ·  OCT 2026', options: { x: 8.15, y: 7.19, w: 4.6, h: 0.16, fontFace: 'Aptos', fontSize: 7, color: '6C808B', align: 'right', margin: 0 } } },
  ],
  slideNumber: { x: 12.87, y: 7.17, w: 0.2, h: 0.18, color: '6C808B', fontFace: 'Aptos', fontSize: 7 }
});

const C = { navy: '173747', ink: '253E4D', teal: '0D8F89', mint: 'E5F4F2', pale: 'EFF5F5', sand: 'FFF4E2', amber: 'C78324', red: 'B85A53', muted: '6C808B', line: 'DCE7E8', white: 'FFFFFF', green: '368576', dark: '102B39' };
const W = 13.333, H = 7.5;
const ROOT = path.resolve(__dirname, '..');
const IMG = (name) => path.join(ROOT, 'assets', name);

function txt(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, { x, y, w, h, fontFace: 'Aptos', fontSize: 13, color: C.ink, margin: 0, breakLine: false, valign: 'mid', fit: 'shrink', ...opts });
}
function box(slide, x, y, w, h, fill = C.white, line = C.line, radius = true) {
  slide.addShape(radius ? pptx.ShapeType.roundRect : pptx.ShapeType.rect, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: line, width: 0.9 }, radius: 0.12 });
}
function line(slide, x1, y1, x2, y2, color = C.line, width = 1.2, dash) {
  slide.addShape(pptx.ShapeType.line, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color, width, ...(dash ? { dashType: 'dash' } : {}) } });
}
function dot(slide, x, y, d, color) {
  slide.addShape(pptx.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color }, line: { color, transparency: 100 } });
}
function pill(slide, label, x, y, w, color = C.mint, textColor = C.teal) {
  slide.addShape(pptx.ShapeType.roundRect, { x, y, w, h: 0.29, rectRadius: 0.12, fill: { color }, line: { color, transparency: 100 } });
  txt(slide, label, x + 0.08, y + 0.015, w - 0.16, 0.24, { fontSize: 8.5, bold: true, color: textColor, align: 'center' });
}
function header(slide, kicker, title, subtitle) {
  txt(slide, kicker.toUpperCase(), 0.65, 0.36, 11.8, 0.24, { fontSize: 9, bold: true, color: C.teal, charSpacing: 1.2 });
  txt(slide, title, 0.65, 0.70, 12.0, 0.52, { fontSize: 26, bold: true, color: C.navy, fontFace: 'Aptos Display' });
  if (subtitle) txt(slide, subtitle, 0.67, 1.24, 11.9, 0.34, { fontSize: 11.3, color: C.muted });
}
function addNotes(slide, text) { slide.addNotes(text); }
function addImageFit(slide, file, x, y, w, h) {
  const ratio = 1600 / 1100;
  let iw = w, ih = w / ratio;
  if (ih > h) { ih = h; iw = h * ratio; }
  slide.addImage({ path: file, x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih });
}
function cardTitle(slide, title, x, y, w) {
  txt(slide, title, x, y, w, 0.32, { fontSize: 14, bold: true, color: C.navy });
}

// 1 — Opening
{
  const s = pptx.addSlide();
  s.background = { color: C.dark };
  s.addShape(pptx.ShapeType.rect, { x: 8.3, y: 0, w: 5.033, h: 7.5, fill: { color: '143C4A' }, line: { color: '143C4A' } });
  s.addShape(pptx.ShapeType.ellipse, { x: 8.85, y: 1.05, w: 3.65, h: 3.65, fill: { color: '0D8F89', transparency: 26 }, line: { color: '0D8F89', transparency: 100 } });
  s.addShape(pptx.ShapeType.ellipse, { x: 9.65, y: 1.82, w: 2.1, h: 2.1, fill: { color: C.dark }, line: { color: '8ED5CC', width: 1.2 } });
  txt(s, 'D', 10.32, 2.31, 0.75, 0.78, { fontFace: 'Aptos Display', fontSize: 45, bold: true, color: C.white, align: 'center' });
  txt(s, 'EUREKA  /  PUBLIC SAFETY INTELLIGENCE', 0.85, 0.82, 6.9, 0.28, { fontSize: 9.5, bold: true, color: '71C6BD', charSpacing: 1.2 });
  txt(s, 'DrillLoop', 0.82, 1.42, 7, 0.95, { fontFace: 'Aptos Display', fontSize: 46, bold: true, color: C.white });
  txt(s, 'Evidence-Linked Exercise Review and Action Closure', 0.86, 2.65, 7.0, 1.3, { fontFace: 'Aptos Display', fontSize: 25, bold: true, color: 'D7E7E8', breakLine: false, valign: 'top' });
  txt(s, 'For hospital preparedness evaluators · synthetic demo', 0.87, 4.2, 6.5, 0.48, { fontSize: 14, color: 'B5C9CD' });
  pill(s, 'WORKING MVP', 0.88, 5.36, 1.45, '21505C', 'A6E0D8');
  txt(s, 'Fictional hospital prolonged power outage · 27 October 2026', 0.88, 6.66, 7.0, 0.25, { fontSize: 9, color: '99B2B9' });
  txt(s, 'Evidence', 8.9, 5.26, 1.35, 0.28, { fontSize: 11, bold: true, color: C.white, align: 'center' });
  txt(s, 'Review', 10.25, 4.25, 1.05, 0.28, { fontSize: 11, bold: true, color: C.white, align: 'center' });
  txt(s, 'Improve', 11.05, 5.24, 1.0, 0.28, { fontSize: 11, bold: true, color: C.white, align: 'center' });
  line(s, 9.8, 4.58, 9.35, 5.1, '79BCB9', 1.2);
  line(s, 11.16, 4.52, 11.55, 5.1, '79BCB9', 1.2);
  txt(s, 'The claim stays connected to its source and its reviewer decision.', 8.9, 6.16, 3.75, 0.58, { fontSize: 12, color: 'C2D4D6', align: 'center' });
  addNotes(s, 'Open with the proposed first use case: hospital preparedness evaluators reviewing an exercise. DrillLoop makes a reviewable path from exercise records to a proposed finding and then to a corrective action whose closure needs evidence. The interface and hospital outage records are synthetic. This is a working local MVP, not a certified emergency management product.');
}

// 2 — Problem
{
  const s = pptx.addSlide('BASE');
  header(s, 'The problem', 'The exercise ends. The evidence work begins.', 'Evaluation is a reconciliation job across files, clocks, objectives, and people.');
  const xs = [0.7, 4.55, 8.4];
  const titles = ['Evidence is scattered', 'Timelines disagree', 'Actions lose momentum'];
  const bodies = [
    'Evaluator notes, control-room logs, transcripts, and reports use different formats and detail.',
    'Missing times, conflicting statements, and recognition errors can make event order look more certain than it is.',
    'Findings become difficult to assign, review, and verify after the report is written.'
  ];
  const nums = ['01', '02', '03'];
  for (let i=0;i<3;i++) {
    box(s, xs[i], 2.05, 3.55, 2.35);
    pill(s, nums[i], xs[i]+0.24, 2.28, 0.5, C.mint, C.teal);
    cardTitle(s, titles[i], xs[i]+0.25, 2.85, 3.0);
    txt(s, bodies[i], xs[i]+0.25, 3.34, 3.02, 0.77, { fontSize: 12, color: C.muted, valign: 'top', breakLine: false });
  }
  box(s, 0.7, 4.85, 11.25, 1.22, C.navy, C.navy);
  txt(s, 'What teams need', 0.98, 5.07, 1.65, 0.25, { fontSize: 10, bold: true, color: '85D4CA' });
  txt(s, 'A review trail that shows what the evidence says, what the evaluator concludes, and who verifies the improvement.', 2.82, 5.02, 8.6, 0.62, { fontSize: 17, bold: true, color: C.white });
  txt(s, 'The amount of time saved and the size of the gap vary by organization; neither has been measured yet.', 0.76, 6.36, 11.0, 0.25, { fontSize: 9, color: C.muted, italic: true });
  addNotes(s, 'Explain this as workflow friction rather than a quantified market statistic. Evaluators reconcile multiple evidence sources, resolve timestamps and contradictory notes, map performance to objectives, then turn gaps into accountable actions. The MVP is aimed at this traceability and follow-through gap. We have not measured actual preparation time or correction workload with evaluators.');
}

// 3 — Product UI overview
{
  const s = pptx.addSlide('BASE');
  header(s, 'The product', 'One review workspace for the whole exercise', 'Follow evidence through to an after-action report and improvement plan (AAR/IP).');
  box(s, 0.72, 1.83, 8.65, 4.92, C.white, C.line);
  addImageFit(s, IMG('DrillLoop_Demo_Overview.png'), 0.82, 1.92, 8.45, 4.72);
  txt(s, 'SYNTHETIC HOSPITAL EXERCISE', 9.77, 2.0, 2.5, 0.25, { fontSize: 8.5, bold: true, color: C.teal, charSpacing: 0.8 });
  txt(s, 'The screen keeps together:', 9.77, 2.4, 2.85, 0.44, { fontSize: 16, bold: true, color: C.navy, valign: 'top' });
  const items = [['Exercise plan', 'Objectives and milestones'], ['Evidence', 'File and source locator'], ['Timeline', 'Known, missing, and conflicting times'], ['Review', 'Proposed vs approved status']];
  items.forEach((it,i) => {
    dot(s, 9.81, 3.12+i*0.75, 0.13, C.teal);
    txt(s, it[0], 10.08, 3.05+i*0.75, 2.3, 0.25, { fontSize: 11, bold: true, color: C.ink });
    txt(s, it[1], 10.08, 3.34+i*0.75, 2.42, 0.25, { fontSize: 9.1, color: C.muted });
  });
  txt(s, 'Screenshot captured from the running app. All exercise content is fictional.', 0.78, 6.83, 8.5, 0.18, { fontSize: 8, color: C.muted, italic: true });
  addNotes(s, 'Show that this is a live application rather than a slide-only concept. The overview page includes the selected exercise, its targets, source files, timeline, findings, actions, and report export. An after-action report and improvement plan (AAR/IP) is a report of what happened and a list of improvements to track. The captured interface uses fictional data only. The website is built with React and TypeScript; FastAPI is the server interface.');
}

// 4 — Scenario timeline
{
  const s = pptx.addSlide('BASE');
  header(s, 'Demo scenario', 'A power outage with evidence that does not all agree', 'Hospital HOSP-PO-2026-01 · Night Shift: Extended Power Loss · fictional exercise.');
  const y = 3.23;
  line(s, 1.1, y, 12.25, y, 'B8CDCF', 2.2);
  const events = [
    { x: 1.25, time: '09:02', title: 'Utility power lost', detail: 'Primary supply failure', tone: C.red },
    { x: 3.45, time: '09:03', title: 'Radio request', detail: 'ICU acknowledgement pending', tone: C.amber },
    { x: 5.83, time: '09:06', title: 'Backup stabilized', detail: '4 min after outage · objective: 60 sec', tone: C.red },
    { x: 8.25, time: '09:10 / 09:11', title: 'Acknowledgement recorded', detail: 'Log and evaluator note conflict', tone: C.amber },
    { x: 10.85, time: '09:18', title: 'Procedure complete', detail: 'Cold-chain relocation logged', tone: C.green },
  ];
  events.forEach((e,i) => {
    dot(s, e.x, y-0.12, 0.24, e.tone);
    const top = i % 2 === 0 ? 1.91 : 3.75;
    const cardY = top;
    box(s, e.x-0.58, cardY, i===3?2.18:1.95, 1.0, C.white, C.line);
    txt(s, e.time, e.x-0.44, cardY+0.12, i===3?1.9:1.65, 0.23, { fontSize: 9, bold: true, color: e.tone });
    txt(s, e.title, e.x-0.44, cardY+0.38, i===3?1.9:1.65, 0.24, { fontSize: 10, bold: true, color: C.navy });
    txt(s, e.detail, e.x-0.44, cardY+0.65, i===3?1.9:1.65, 0.25, { fontSize: 8, color: C.muted, valign: 'top' });
    line(s, e.x, i%2===0?cardY+1.0:cardY, e.x, i%2===0?y-0.12:y+0.12, 'C4D4D6', 0.8);
  });
  box(s, 0.75, 5.38, 11.9, 0.83, C.sand, 'EBD9B9');
  txt(s, 'Uncertainty stays visible', 0.98, 5.57, 2.1, 0.25, { fontSize: 11, bold: true, color: '946A2E' });
  txt(s, '09:10 vs 09:11 is unresolved. “Generator lagged a bit” has no time or measure, so it is not ordered as a confirmed event.', 3.12, 5.51, 9.05, 0.43, { fontSize: 11, color: C.ink });
  addNotes(s, 'Walk through the fictional timeline. Power is lost at 09:02. The radio request begins at 09:03 and the log records acknowledgement at 09:10. The exercise target for unit acknowledgement is three minutes, so about seven minutes is late. Another evaluator says 09:11; the app shows both times and does not choose one. Backup circuits stabilize at 09:06, beyond the one-minute power objective. At 09:18 the ICU team completes the cold-chain procedure, which means moving temperature-sensitive medicines to safe storage and recording how they were handled. A vague debrief phrase has no timestamp or measure and is not promoted to a confirmed event.');
}

// 5 — Evidence-linked findings
{
  const s = pptx.addSlide('BASE');
  header(s, 'From evidence to a finding', 'Open the source behind every draft', 'See what the record says, what it may mean, and where a reviewer can check it.');
  box(s, 0.72, 1.83, 7.95, 4.92, C.white, C.line);
  addImageFit(s, IMG('DrillLoop_Demo_Findings.png'), 0.82, 1.92, 7.75, 4.72);
  txt(s, 'DRAFT FINDING', 9.02, 2.06, 2.65, 0.23, { fontSize: 8.5, bold: true, color: C.teal, charSpacing: 0.8 });
  txt(s, 'Delayed ICU acknowledgement', 9.02, 2.42, 3.15, 0.5, { fontSize: 17, bold: true, color: C.navy, valign: 'top' });
  box(s, 9.02, 3.18, 3.13, 1.23, C.pale, C.line);
  txt(s, 'WHAT IT MAY MEAN', 9.2, 3.36, 1.55, 0.2, { fontSize: 8, bold: true, color: C.muted });
  txt(s, 'About 7 minutes observed; exercise target is 3 minutes.', 9.2, 3.66, 2.66, 0.52, { fontSize: 10.2, color: C.ink, valign: 'top' });
  txt(s, 'SUPPORTING RECORDS', 9.02, 4.72, 2.4, 0.2, { fontSize: 8, bold: true, color: C.muted });
  pill(s, 'CSV rows 4–5', 9.02, 5.05, 1.42, C.mint, C.teal);
  pill(s, 'Note line 9', 10.58, 5.05, 1.42, C.mint, C.teal);
  txt(s, 'DRAFT  /  awaiting evaluator', 9.04, 5.71, 2.7, 0.28, { fontSize: 9, bold: true, color: C.amber });
  txt(s, 'The response-time discrepancy cites the independent event log; the low-confidence “too minutes” transcript phrase remains uncertain.', 9.02, 6.14, 3.15, 0.55, { fontSize: 9.2, color: C.muted, valign: 'top' });
  txt(s, 'No finding is approved by the model. Reviewer decision remains explicit.', 0.79, 6.83, 8.9, 0.18, { fontSize: 8, color: C.muted, italic: true });
  addNotes(s, 'A finding is an evaluator’s conclusion about performance against an exercise target. Here the target is acknowledgement within three minutes, while the records say it took about seven. The actual evidence sources are control_room_log.csv rows 4–5 and evaluator_notes.txt line 9, where the separate 09:11 report appears. The system should display those records separately; the discrepancy remains unresolved. Speech-to-text (also called automatic speech recognition or ASR) produced the fictional low-confidence “too minutes” error. The response-time finding instead relies on the independent event log. All findings begin as proposals and an authorized evaluator must approve or reject them.');
}

// 6 — Controlled pipeline
{
  const s = pptx.addSlide('BASE');
  header(s, 'AI workflow', 'A fixed pipeline keeps the evidence path inspectable', 'The MVP uses deterministic extraction for the demo fixture. Optional local models stay behind defined boundaries.');
  const steps = [
    ['01', 'Collect files', 'Notes · spreadsheets\ntranscripts · readable PDFs'],
    ['02', 'Record details', 'Keep exact file location\nand known / unknown time'],
    ['03', 'Compare', 'Compare recorded events\nwith exercise targets'],
    ['04', 'Link evidence', 'Show the exact source\nbehind every proposal'],
    ['05', 'Human review', 'A person decides\napprove / reject'],
  ];
  const start=0.78, sw=2.16, gap=0.33;
  steps.forEach((st,i)=>{
    const x=start+i*(sw+gap);
    box(s,x,2.15,sw,1.52, i===4?C.navy:C.white, i===4?C.navy:C.line);
    pill(s,st[0],x+0.17,2.33,0.47,i===4?'21505C':C.mint,i===4?'A6E0D8':C.teal);
    txt(s,st[1],x+0.18,2.77,1.82,0.28,{fontSize:15,bold:true,color:i===4?C.white:C.navy});
    txt(s,st[2],x+0.18,3.13,1.82,0.42,{fontSize:9.2,color:i===4?'C2D4D6':C.muted,valign:'top'});
    if(i<4) { line(s,x+sw+0.04,2.91,x+sw+gap-0.06,2.91,C.teal,1.5); }
  });
  box(s,0.78,4.18,5.72,1.38,C.mint,'D1E9E6');
  txt(s,'OPTIONAL LOCAL SPEECH-TO-TEXT',1.02,4.4,2.9,0.21,{fontSize:8.5,bold:true,color:C.teal});
  txt(s,'faster-whisper can turn audio into draft text when installed. Demo transcript is pre-written; speakers are not identified.',1.02,4.77,5.08,0.48,{fontSize:10.3,color:C.ink,valign:'top'});
  box(s,6.78,4.18,5.72,1.38,C.sand,'EBD9B9');
  txt(s,'OPTIONAL LOCAL WRITING MODEL',7.02,4.4,2.8,0.21,{fontSize:8.5,bold:true,color:'946A2E'});
  txt(s,'Ollama may reword an action draft only. It cannot create a finding, change a source link, or make a reviewer decision.',7.02,4.77,5.08,0.48,{fontSize:10.3,color:C.ink,valign:'top'});
  txt(s,'Same evidence + same rules produce a repeatable draft. The evaluator still decides.',0.85,6.15,9.5,0.28,{fontSize:11,bold:true,color:C.navy});
  addNotes(s, 'This is a fixed workflow: the same evidence is processed by the same explicit rules, which makes the demo repeatable and easier to inspect. CSV means a spreadsheet-like file; JSON is a structured text file. A vector database is a separate search system for finding similar text; this tiny example does not need one. Speech-to-text (automatic speech recognition, or ASR) turns audio into a draft transcript; the demo transcript was typed in advance. A large language model (LLM) can draft or reword text, but the optional Ollama model can only rewrite an action after rules have created it. Neither optional path was used for the reported results.');
}

// 7 — Corrective action
{
  const s = pptx.addSlide('BASE');
  header(s, 'Corrective action management', 'A finding stays open until its improvement is checked', 'Every action needs an owner, a due date, a clear test for completion, and reviewer confirmation.');
  box(s,0.72,1.84,8.0,4.92,C.white,C.line);
  addImageFit(s,IMG('DrillLoop_Demo_Actions.png'),0.82,1.93,7.8,4.72);
  const stages=[['Proposed','Finding awaiting review'],['Assigned','Owner + due date'],['In progress','Acceptance criteria'],['Closure review','Attach completion proof'],['Closed','Reviewer confirms']];
  stages.forEach((st,i)=>{
    const y=2.0+i*0.82;
    dot(s,9.18,y+0.07,0.18,i===4?C.green:C.teal);
    if(i<4) line(s,9.27,y+0.25,9.27,y+0.82,'BFD2D3',1.4);
    txt(s,st[0],9.56,y,2.45,0.25,{fontSize:11,bold:true,color:C.navy});
    txt(s,st[1],9.56,y+0.29,2.75,0.25,{fontSize:9.2,color:C.muted});
  });
  box(s,9.02,6.18,3.15,0.54,C.sand,'EBD9B9');
  txt(s,'Missing owner stays unassigned.',9.2,6.31,2.8,0.22,{fontSize:9,bold:true,color:'946A2E'});
  addNotes(s, 'A corrective action is a task intended to improve the next exercise. Its “acceptance criteria” are the test for deciding whether the task is done—for example, three timed drills where all units acknowledge within three minutes. The action is linked to its finding and source records. One sample action has no named owner; the app leaves it blank rather than inventing a person. A reviewer must approve the linked finding and later check completion evidence before closure.');
}

// 8 — Competitive landscape
{
  const s = pptx.addSlide('BASE');
  header(s,'Market context','The category already has AAR and action-tracking tools','DrillLoop should validate a focused workflow advantage instead of claiming report generation is unique.');
  const rows=[
    ['FEMA exercise guidance','Exercise planning and evaluation steps','Use familiar structure; no claim of certification.'],
    ['Veoci','Publicly describes AAR reports, timestamps, transcripts, and corrective actions','Direct competitor; compare source-level review and closure in customer demos.'],
    ['D4H','Emergency-team readiness, incident, personnel, and equipment workflows','Adjacent incumbent; confirm evaluation evidence workflow depth.'],
    ['DrillLoop hypothesis','Exact source observation → human decision → closure evidence','Potential niche; uniqueness and willingness to pay remain unvalidated.'],
  ];
  const x=[0.78,3.0,7.7], widths=[2.1,4.45,4.55];
  const heads=['OPTION / CONTEXT','PUBLICLY VISIBLE SCOPE','IMPLICATION TO TEST'];
  heads.forEach((h,i)=>{txt(s,h,x[i],1.94,widths[i],0.25,{fontSize:8,bold:true,color:C.teal,charSpacing:0.7});});
  rows.forEach((r,ri)=>{
    const y=2.35+ri*0.92;
    box(s,0.72,y,11.85,0.79,ri===3?C.mint:C.white,ri===3?'C9E4E0':C.line);
    txt(s,r[0],0.92,y+0.13,1.9,0.5,{fontSize:10.4,bold:true,color:C.navy,valign:'top'});
    txt(s,r[1],3.05,y+0.11,4.2,0.56,{fontSize:9.4,color:C.ink,valign:'top'});
    txt(s,r[2],7.73,y+0.11,4.52,0.56,{fontSize:9.3,color:C.muted,valign:'top'});
  });
  txt(s,'Sources: FEMA exercise guidance · Veoci after-action reporting · D4H team readiness. Public pages, not a scored teardown.',0.82,6.3,11.5,0.28,{fontSize:8.5,color:C.muted,italic:true});
  addNotes(s, 'HSEEP is FEMA’s Homeland Security Exercise and Evaluation Program. It provides a recognized way to plan and evaluate exercises; DrillLoop borrows some concepts but is not FEMA-certified. Veoci publicly markets after-action reporting, timestamps, transcripts, and corrective-action follow-up. D4H serves emergency response readiness and related workflows. Report writing by itself is not a unique claim. DrillLoop’s hypothesis is the source-to-review-to-closure trail, and that must be tested with buyers who already use these tools. Sources: https://www.fema.gov/sites/default/files/2020-04/Homeland-Security-Exercise-and-Evaluation-Program-Doctrine-2020-Revision-2-2-25.pdf ; https://veoci.com/emergency-management/after-action-reporting/ ; https://www.d4h.com/team-readiness-software');
}

// 9 — Buyer and wedge
{
  const s = pptx.addSlide('BASE');
  header(s,'Customer wedge','Start with a hospital exercise review','This is a proposed first use case; no pilot partner or buyer has been confirmed.');
  box(s,0.78,2.0,3.5,3.45,C.navy,C.navy);
  pill(s,'FIRST PILOT HYPOTHESIS',1.08,2.3,1.95,'21505C','A6E0D8');
  txt(s,'Hospital\ntabletop review',1.08,2.92,2.8,0.93,{fontSize:22,bold:true,color:C.white,valign:'top',fontFace:'Aptos Display'});
  txt(s,'Initial segment hypothesis. The included outage exercise is synthetic; no hospital partner is confirmed.',1.08,4.17,2.75,0.82,{fontSize:10.5,color:'C2D4D6',valign:'top'});
  const roles=[
    ['Report preparer','Exercise evaluator / preparedness staff (candidate user).'],
    ['Report approver','Preparedness lead or exercise sponsor (candidate).'],
    ['Budget owner','Not identified; role to validate in discovery.'],
  ];
  roles.forEach((r,i)=>{
    const y=2.02+i*1.1;
    box(s,4.78,y,3.56,0.9,C.white,C.line);
    txt(s,r[0],5.02,y+0.15,2.9,0.23,{fontSize:12,bold:true,color:C.navy});
    txt(s,r[1],5.02,y+0.46,3.02,0.25,{fontSize:9,color:C.muted});
  });
  txt(s,'Roles to validate',8.92,2.03,3.4,0.29,{fontSize:13,bold:true,color:C.navy});
  const roleChecks=[['1','Who prepares the AAR/IP?'],['2','Who approves findings?'],['3','Who controls the budget?']];
  roleChecks.forEach((r,i)=>{
    const y=2.55+i*0.95;
    box(s,8.9,y,3.55,0.76,C.pale,C.line);
    pill(s,r[0],9.08,y+0.2,0.35,C.mint,C.teal);
    txt(s,r[1],9.58,y+0.17,2.55,0.4,{fontSize:10.4,bold:true,color:C.ink});
  });
  box(s,4.78,5.55,7.67,0.71,C.sand,'EBD9B9');
  txt(s,'No interviews or purchasing-path validation are recorded yet.',5.02,5.78,7.12,0.25,{fontSize:11,bold:true,color:'805E2B'});
  addNotes(s, 'The hospital tabletop review is the proposed initial use case, not a confirmed customer or pilot. The candidate user is an exercise evaluator or preparedness staff member. A preparedness lead or exercise sponsor may approve the report; the actual buyer and budget owner are unknown. Discovery needs to identify who prepares the report, approves findings, owns the budget, and controls access to exercise data. No customer interviews or purchasing-path validation are recorded.');
}

// 10 — Commercial model
{
  const s = pptx.addSlide('BASE');
  header(s,'Commercial hypothesis','Start with a per-exercise pilot fee','This is the first model to validate; no price, buyer demand, or revenue has been established.');
  box(s,0.82,2.0,3.65,3.85,C.navy,C.navy);
  pill(s,'FIRST MODEL TO TEST',1.12,2.34,1.9,'21505C','A6E0D8');
  txt(s,'Per-exercise\npilot fee',1.12,2.96,2.95,0.9,{fontSize:27,bold:true,color:C.white,fontFace:'Aptos Display',valign:'top'});
  txt(s,'Price to be set with the prospective buyer after delivery effort and procurement path are understood.',1.12,4.27,2.98,0.86,{fontSize:11,color:'C2D4D6',valign:'top'});
  const valueChecks=[
    ['BUYER','Who owns the budget and approves an exercise-level purchase?'],
    ['VALUE','Does evidence lookup, review, or action follow-up improve on the current process?'],
    ['DELIVERY','What setup, security, support, and evidence-handling work does each exercise require?'],
  ];
  valueChecks.forEach((r,i)=>{
    const y=2.02+i*1.22;
    box(s,4.92,y,7.42,1.0,C.white,C.line);
    txt(s,r[0],5.18,y+0.17,1.1,0.2,{fontSize:8.5,bold:true,color:C.teal,charSpacing:.8});
    txt(s,r[1],6.32,y+0.14,5.62,0.68,{fontSize:12,bold:true,color:C.navy,valign:'top'});
  });
  box(s,4.92,5.82,7.42,.66,C.sand,'EBD9B9');
  txt(s,'Annual plans and private deployment remain later hypotheses.',5.18,6.02,6.85,.24,{fontSize:10.5,bold:true,color:'805E2B'});
  addNotes(s, 'The proposed first commercial model is a per-exercise pilot fee. No price or willingness-to-pay evidence exists, so the pitch does not present an assumed quote as a selected price. Discovery should identify the user, approver, budget owner, procurement path, and actual delivery costs. Annual organizational plans, private deployment, templates, and support are possible later models if pilot evidence and buyers support them. The separate Business Case contains illustrative price and staffing assumptions; they are not market rates, a forecast, or revenue.');
}

// 11 — Architecture
{
  const s = pptx.addSlide('BASE');
  header(s,'Technical foundation','Simple local app, with a person at the review gate','The demo can run without a cloud AI service; optional models stay on the computer.');
  const topY=2.06;
  const cols=[
    {x:.78,w:2.26,title:'Website screen',desc:'Exercise setup\nEvidence review\nAction tracking\nReact + TypeScript',fill:C.white},
    {x:3.42,w:2.5,title:'Application service',desc:'Checks uploaded files\nApplies review rules\nFastAPI + Pydantic',fill:C.white},
    {x:6.31,w:2.34,title:'Saved records',desc:'SQLite for the demo\nPostgreSQL for deployment\nSQLAlchemy database tools',fill:C.white},
    {x:9.04,w:3.22,title:'Reports + optional local AI',desc:'PDF report: ReportLab\nSpeech-to-text: faster-whisper\nAction wording: Ollama',fill:C.mint},
  ];
  cols.forEach((c,i)=>{
    box(s,c.x,topY,c.w,1.57,c.fill,C.line);
    txt(s,c.title,c.x+.17,topY+.25,c.w-.34,.3,{fontSize:12,bold:true,color:C.navy,align:'center'});
    txt(s,c.desc,c.x+.17,topY+.72,c.w-.34,.62,{fontSize:9,color:C.muted,align:'center',valign:'top'});
    if(i<3) line(s,c.x+c.w+.04,topY+.79,cols[i+1].x-.07,topY+.79,C.teal,1.5);
  });
  box(s,0.82,4.18,7.45,1.52,C.navy,C.navy);
  txt(s,'TRACEABLE RECORD',1.1,4.42,2.2,.24,{fontSize:9,bold:true,color:'85D4CA',charSpacing:.5});
  txt(s,'Original file + file-change checksum + extracted quote + location + reviewer decision + completion proof',1.1,4.86,6.65,.49,{fontSize:13,bold:true,color:C.white,valign:'top'});
  box(s,8.72,4.18,3.56,1.52,C.sand,'EBD9B9');
  txt(s,'DEMO SECURITY BOUNDARY',8.96,4.42,2.9,.24,{fontSize:8.5,bold:true,color:'946A2E'});
  txt(s,'Shared demo key; no named accounts, tenant separation, retention controls, or security assessment.',8.96,4.82,3.0,.65,{fontSize:9.2,color:C.ink,valign:'top'});
  txt(s,'Exact library versions and licenses are listed in the Technical Design.',0.86,6.25,11.5,.3,{fontSize:10,bold:true,color:C.navy});
  addNotes(s, 'The website is built with React and TypeScript. FastAPI is the web service, and Pydantic checks the data sent to it. SQLAlchemy is the database access library. SQLite stores the local demo; PostgreSQL is available through Docker Compose. Uploaded source bytes and extracted text are stored in the configured database. The demo has a shared reviewer key, but no named-user RBAC, tenant isolation, retention/deletion controls, or security assessment. The default workflow makes no cloud model call. faster-whisper runs locally with a staged model; optional Ollama is configured as a local/private service for action wording only. Neither optional path was benchmarked. The Technical Design lists versions and licenses.');
}

// 12 — Evaluation
{
  const s = pptx.addSlide('BASE');
  header(s,'Technical evaluation','The sample passed its checks; new exercises still need testing','Scores use one fictional exercise built for this demo. They do not measure evaluator agreement or general accuracy.');
  const metrics=[['Event records','8 / 8','All labeled rows found'],['Finding labels','5 / 5','All expected labels found'],['Source links','9 / 9','Expected record IDs linked'],['Recorded times','8 / 8','One disagreement shown']];
  metrics.forEach((m,i)=>{
    const x=.8+i*3.05;
    box(s,x,2.0,2.72,1.4,C.white,C.line);
    txt(s,m[0].toUpperCase(),x+.2,2.22,2.3,.2,{fontSize:8,bold:true,color:C.teal,charSpacing:.7});
    txt(s,m[1],x+.2,2.54,2.3,.43,{fontSize:24,bold:true,color:C.navy,fontFace:'Aptos Display'});
    txt(s,m[2],x+.2,3.05,2.3,.22,{fontSize:9,color:C.muted});
  });
  box(s,.82,3.86,5.78,1.55,C.mint,'C9E4E0');
  txt(s,'Measured',1.08,4.1,1.35,.24,{fontSize:12,bold:true,color:C.teal});
  txt(s,'Rule request latency p50 4.61 ms · p95 9.13 ms\nPeak process RSS 78.2 MB · no model loaded',1.08,4.51,5.15,.58,{fontSize:10.2,color:C.ink,valign:'top'});
  box(s,6.88,3.86,5.58,1.55,C.sand,'EBD9B9');
  txt(s,'Not measured',7.14,4.1,1.8,.24,{fontSize:12,bold:true,color:'946A2E'});
  txt(s,'Unseen-exercise errors · reviewer edits · semantic citation quality\nASR WER/latency · local LLM quality and latency',7.14,4.51,4.95,.58,{fontSize:9.8,color:C.ink,valign:'top'});
  txt(s,'Precision and recall were 100% because rules and labels used the same small scenario; they do not establish performance on an unfamiliar exercise.',0.88,5.68,11.2,.48,{fontSize:9.3,color:C.navy});
  txt(s,'31 / 32 action fields were filled; one owner is intentionally missing. No evaluator study was run.',0.88,6.19,11.3,.3,{fontSize:9.5,bold:true,color:C.navy});
  txt(s,'12 local test calls · no AI model loaded · results apply to this synthetic fixture only.',0.88,6.58,11.0,.23,{fontSize:8.5,color:C.muted,italic:true});
  addNotes(s, 'The benchmark used the one fictional exercise included with the project. Precision and recall were 100 percent on this closed sample, but the rules were written for these same labels. Nine of nine source-record IDs were present; that does not prove each source semantically supports the conclusion. The timeline matched eight explicit log times and displayed one disagreement. Action fields were 31 of 32 complete because an owner is intentionally missing. Request time and process memory exclude model inference. No real evaluator, unfamiliar-exercise test, speech-to-text accuracy test, or local LLM comparison was run. A next evaluation should use evaluator-labeled evidence from an exercise not used to write the rules and report both missed and incorrect findings.');
}

// 13 — Pilot ask
{
  const s = pptx.addSlide();
  s.background = { color: C.dark };
  s.addShape(pptx.ShapeType.rect,{x:0,y:0,w:W,h:H,fill:{color:C.dark},line:{color:C.dark}});
  txt(s,'THE NEXT PROOF POINT',.85,.76,6,.25,{fontSize:9,bold:true,color:'71C6BD',charSpacing:1.4});
  txt(s,'Pilot the review trail.',.82,1.25,8.4,.72,{fontFace:'Aptos Display',fontSize:36,bold:true,color:C.white});
  txt(s,'Compare the current process and DrillLoop on the same permitted hospital exercise records, then test an unfamiliar exercise.',.86,2.18,8.8,.63,{fontSize:15,color:'C2D4D6',valign:'top'});
  const asks=[
    ['2–3 users','Prospective hospital-preparedness interviews (proposed)'],
    ['Paired review','Same permitted records: existing process and DrillLoop'],
    ['Measure','Time · misses · corrections · citations · action fields'],
  ];
  asks.forEach((a,i)=>{
    const x=.88+i*3.97;
    box(s,x,3.42,3.5,1.35,'183B48','315764');
    txt(s,a[0],x+.22,3.66,2.95,.35,{fontSize:20,bold:true,color:'85D4CA',fontFace:'Aptos Display'});
    txt(s,a[1],x+.22,4.12,3.05,.42,{fontSize:10.3,color:'D0DFE1',valign:'top'});
  });
  txt(s,'Partner-defined success thresholds.',.9,5.53,7,.35,{fontSize:16,bold:true,color:C.white});
  txt(s,'No pilot partner, interviews, baseline, or performance targets are confirmed.',.9,6.03,9.0,.3,{fontSize:11,color:'B8CCCF'});
  txt(s,'DrillLoop · Fictional demo · Uses selected FEMA exercise guidance; not certified',.9,7.02,8,.18,{fontSize:8,color:'99B2B9'});
  addNotes(s, 'This is a proposed discovery and pilot sequence, not a confirmed project commitment. First interview two or three prospective hospital-preparedness users and observe one current review with permission. If a partner agrees, compare existing practice and DrillLoop on the same permitted records. Ask the partner to set thresholds before the trial for report time, reviewer corrections, citation accuracy, and action-field completeness. Then use evaluator-labeled evidence from an unfamiliar exercise and report missed and incorrect findings. Select one relevant alternative with the partner for a comparable source-location, reviewer-decision, and closure-evidence workflow. No pilot partner, access, schedule, or thresholds are currently confirmed.');
}

pptx.writeFile({ fileName: path.join(ROOT, 'DrillLoop_Pitch_Deck.pptx') })
  .then(() => console.log('Generated 13-slide DrillLoop_Pitch_Deck.pptx with speaker notes.'))
  .catch((error) => { console.error(error); process.exitCode = 1; });
