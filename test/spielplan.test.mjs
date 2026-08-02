import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const VISUALIZE = path.join(REPO_ROOT, 'visualize_spiele.py');

let failures = 0;
function check(cond, label) {
  if (cond) {
    console.log(`  ok  ${label}`);
  } else {
    failures++;
    console.error(`FAIL  ${label}`);
  }
}
function section(name) {
  console.log(`\n# ${name}`);
}

function fmtDate(offsetDays) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
}

function csvRow(fields) {
  const q = (s) => (/,|;|"|\n/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  return fields.map(q).join(',');
}

const g = (offset, time, h, a, w, p, id) => ({
  datum: fmtDate(offset),
  time,
  h,
  a,
  w,
  p,
  l: `https://www.bfv.de/spiele/xyz/${id}`,
  quelle: 'https://www.bfv.de/mannschaften/tsv-gilching-argelsried/0000000000000000000000',
});

const U15 = 'TSV Gilching/Argelsried U15';
const U17 = 'TSV Gilching/Argelsried U17';
const fileA = [
  g(-12, '10:00', U15, 'FC Mustermann 1', 'U15 Kreis', 'Sportpark Gilching | Platz 1', 'a1'),
  g(-2, '', U15, 'FC Mustermann 2', 'U15 Kreis', 'Sportpark Gilching | Platz 2', 'a2'),
  g(0, '18:00', U15, 'FC Mustermann 1', 'U15 Kreis', 'Sportpark Gilching | Platz 1', 'a3'),
  g(3, '14:00', U15, 'FC Mustermann 2', 'U15 Kreis', 'Sportpark Gilching | Platz 1', 'a4'),
  g(3, '16:00', 'FC Mustermann 1', U15, 'U15 Kreis', 'Auswärts | Kunstrasen', 'a5'),
  g(6, '', U15, 'FC Sonntag', 'U15 Kreis', 'Sportpark Gilching | Platz 2', 'a6'),
  g(10, '22:00', U15, 'FC Semi; Kolon, Komma \\ Team', 'U15 Kreis', 'Sportpark Gilching | Platz 1', 'a7'),
];
const fileB = [
  g(20, '11:00', 'SV Beispiel', U17, 'U17 Kreis', 'Beispielhalle', 'b1'),
  g(25, '13:00', U17, 'SV Anderer', 'U17 Kreis', 'Sportpark Gilching | Platz 3', 'b2'),
];
const GAMES = [...fileA, ...fileB];

const HEADER = 'Wettbewerb,Datum,Uhrzeit,Heim,Gast,Spielort,Link,Quelle';
function csvFor(games) {
  const rows = games.map((x) => csvRow([x.w, x.datum, x.time, x.h, x.a, x.p, x.l, x.quelle]));
  return [HEADER, ...rows].join('\n') + '\n';
}

console.log('Generating HTML via visualize_spiele.py …');
let renderedHtml = '';
let js = '';
{
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'spielplan-test-'));
  try {
    fs.copyFileSync(VISUALIZE, path.join(tmp, 'visualize_spiele.py'));
    fs.writeFileSync(path.join(tmp, 'tsv-a_spiele_web.csv'), csvFor(fileA), 'utf8');
    fs.writeFileSync(path.join(tmp, 'tsv-b_spiele_web.csv'), csvFor(fileB), 'utf8');
    execFileSync('python3', ['visualize_spiele.py'], { cwd: tmp, stdio: 'pipe' });
    renderedHtml = fs.readFileSync(path.join(tmp, 'spielplan.html'), 'utf8');
    const m = renderedHtml.match(/<script>([\s\S]*?)<\/script>/);
    if (!m) throw new Error('no <script> block found in generated HTML');
    js = m[1];
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}
const clubTeams = [U15, U17];

class FakeClassList {
  constructor() {
    this.set = new Set();
  }
  add(...n) {
    n.forEach((x) => this.set.add(x));
  }
  remove(...n) {
    n.forEach((x) => this.set.delete(x));
  }
  contains(n) {
    return this.set.has(n);
  }
}
class FakeStyle {
  constructor() {
    this.display = '';
  }
}
class FakeElement {
  constructor(tag = 'div') {
    this.tag = tag;
    this.style = new FakeStyle();
    this.classList = new FakeClassList();
    this.dataset = {};
    this.checked = false;
    this.value = '';
    this.textContent = '';
    this.innerHTML = '';
    this.href = '';
    this.download = '';
    this.parentNode = null;
    this.listeners = {};
    this.children = [];
  }
  addEventListener(type, fn) {
    (this.listeners[type] ??= []).push(fn);
  }
  click() {}
  remove() {
    if (this.parentNode) {
      this.parentNode.children = this.parentNode.children.filter((c) => c !== this);
    }
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
}

function parseSections(html) {
  const sections = [];
  const sectionRe = /<section class="day" data-datum="([^"]+)"[\s\S]*?(?:<div class="(day-header[^"]*)"[\s\S]*?>[\s\S]*?<span class="badge"[^>]*>[\s\S]*?<\/span>)?[\s\S]*?<tbody>([\s\S]*?)<\/tbody>/g;
  let sm;
  while ((sm = sectionRe.exec(html))) {
    const sectionEl = new FakeElement('section');
    sectionEl.dataset.datum = sm[1];
    const header = new FakeElement('div');
    header.classList.add('day-header');
    if (sm[2]) sm[2].split(' ').forEach((c) => c && header.classList.add(c));
    const badge = new FakeElement('span');
    badge.classList.add('badge');
    const trRe = /<tr[^>]*data-heim="([^"]*)"[^>]*data-gast="([^"]*)"[^>]*>/g;
    let tm;
    const trs = [];
    while ((tm = trRe.exec(sm[3]))) {
      const tr = new FakeElement('tr');
      tr.dataset.heim = tm[1];
      tr.dataset.gast = tm[2];
      trs.push(tr);
    }
    sectionEl.trs = trs;
    sectionEl.querySelectorAll = () => trs;
    sectionEl.querySelector = (sel) => (sel === '.day-header' ? header : badge);
    sections.push(sectionEl);
  }
  return sections;
}

function buildScenario(opts = {}) {
  const sections = parseSections(renderedHtml);
  const allCheck = new FakeElement('input');
  allCheck.id = 'allTeams';
  allCheck.checked = true;
  const hidePast = new FakeElement('input');
  hidePast.id = 'hidePast';
  hidePast.checked = true;
  const summary = new FakeElement('div');
  summary.id = 'summary';
  summary.innerHTML = 'Fake summary';
  const icsBtn = new FakeElement('button');
  icsBtn.id = 'icsExport';
  const els = new Map([
    ['summary', summary],
    ['allTeams', allCheck],
    ['hidePast', hidePast],
    ['icsExport', icsBtn],
  ]);
  const teamChecks = clubTeams.map((t) => {
    const c = new FakeElement('input');
    c.value = t;
    c.checked = false;
    return c;
  });

  const body = { children: [] };
  body.lastChild = null;
  body.appendChild = function (child) {
    this.children.push(child);
    this.lastChild = child;
    return child;
  };
  body.removeChild = function () {};

  let alertMsg = null;
  let capturedBlob = null;
  const document = {
    getElementById: (id) => els.get(id),
    querySelectorAll: (sel) => (sel === 'input[data-team]' ? teamChecks : sel === '.day' ? sections : []),
    createElement: (tag) => new FakeElement(tag),
    body,
  };
  const blobFactory = class {
    constructor(parts, blobOpts) {
      this.parts = parts;
      this.type = blobOpts && blobOpts.type;
    }
    text() {
      return Promise.resolve(this.parts.join(''));
    }
  };
  const sandbox = {
    document,
    window: { location: { search: opts.search || '' } },
    URLSearchParams,
    Blob: blobFactory,
    URL: {
      createObjectURL: (b) => {
        capturedBlob = b;
        return 'blob:fake';
      },
    },
    alert: (m) => {
      alertMsg = m;
    },
    console,
  };
  const ctx = vm.createContext(sandbox);
  vm.runInContext(js, ctx);
  vm.runInContext(
    'globalThis.__dayKey = dayKey; globalThis.__selectedTeams = selectedTeams;' +
      'globalThis.__icsDate = icsDate; globalThis.__icsEscape = icsEscape;' +
      'globalThis.__icsFold = icsFold; globalThis.__icsEnd = icsEnd;',
    ctx,
  );
  return {
    ctx,
    allCheck,
    hidePast,
    teamChecks,
    sections,
    summary,
    icsBtn,
    body,
    get alert() {
      return alertMsg;
    },
    get blob() {
      return capturedBlob;
    },
  };
}

function fire(el, type) {
  (el.listeners[type] ?? []).forEach((fn) => fn());
}

section('Hide-Past (default on)');
{
  const s = buildScenario();
  check(s.hidePast.checked === true, 'hidePast default checked');
  const byOffset = (off) => s.sections.find((sec) => sec.dataset.datum === fmtDate(off));
  check(byOffset(-12).style.display === 'none', 'past day (-12d) hidden');
  check(byOffset(-2).style.display === 'none', 'past day (-2d) hidden');
  check(byOffset(0).style.display === '', 'today shown');
  check(byOffset(3).style.display === '', 'future hot day shown');
  check(byOffset(20).style.display === '', 'future day (20d) shown');
}

section('dayKey across month boundaries (YYYYMMDD)');
{
  const s = buildScenario();
  check(s.ctx.__dayKey('01.08.2026') > s.ctx.__dayKey('31.07.2026'), '01.08 > 31.07');
  check(s.ctx.__dayKey('01.02.2026') > s.ctx.__dayKey('31.01.2026'), '01.02 > 31.01');
  check(s.ctx.__dayKey('31.12.2026') < s.ctx.__dayKey('01.01.2027'), '31.12.2026 < 01.01.2027');
}

section('Team filter: single selection');
{
  const s = buildScenario();
  s.teamChecks[0].checked = true;
  fire(s.teamChecks[0], 'change');
  check(s.allCheck.checked === false, 'allTeams unchecked when team selected');
  const day3 = s.sections.find((sec) => sec.dataset.datum === fmtDate(3));
  const day20 = s.sections.find((sec) => sec.dataset.datum === fmtDate(20));
  const u15Only = day3.trs.filter((tr) => tr.dataset.heim === U15 || tr.dataset.gast === U15);
  check(u15Only.every((tr) => tr.style.display === ''), 'U15 rows visible');
  check(
    day3.trs.filter((tr) => tr.dataset.heim !== U15 && tr.dataset.gast !== U15).every((tr) => tr.style.display === 'none'),
    'other team rows hidden',
  );
  check(day20.style.display === 'none', 'day without U15 hidden');
}

section('Team filter: multi selection');
{
  const s = buildScenario();
  s.teamChecks.forEach((c) => (c.checked = true));
  fire(s.teamChecks[0], 'change');
  const day20 = s.sections.find((sec) => sec.dataset.datum === fmtDate(20));
  check(day20.style.display === '', 'day with U17 shown');
  check(day20.trs.every((tr) => tr.style.display === ''), 'all rows of multi-selected teams visible');
}

section('All teams checkbox');
{
  const s = buildScenario();
  s.teamChecks[0].checked = true;
  fire(s.teamChecks[0], 'change');
  s.allCheck.checked = true;
  fire(s.allCheck, 'change');
  check(s.teamChecks.every((c) => c.checked === true), 'all team checks re-checked');
  const day3 = s.sections.find((sec) => sec.dataset.datum === fmtDate(3));
  check(day3.trs.every((tr) => tr.style.display === ''), 'all rows visible');
}

section('URL preselect (?team=A&team=B)');
{
  const q = (t) => encodeURIComponent(t).replace(/%20/g, '+');
  const s = buildScenario({ search: `?team=${q(U15)}&team=${q(U17)}` });
  check(s.allCheck.checked === false, 'allTeams disabled');
  check(s.teamChecks.every((c) => c.checked === true), 'both teams preselected');
  const s2 = buildScenario({ search: `?team=${q(U15)}` });
  check(s2.teamChecks[0].checked === true && s2.teamChecks[1].checked === false, 'single team preselected');
  check(s2.allCheck.checked === false, 'allTeams disabled (single)');
}

section('Hot day badge');
{
  const s = buildScenario();
  s.allCheck.checked = false;
  fire(s.allCheck, 'change');
  const day3 = s.sections.find((sec) => sec.dataset.datum === fmtDate(3));
  const header = day3.querySelector('.day-header');
  const badge = day3.querySelector('.badge');
  check(header.classList.contains('hot'), 'hot day header has class');
  check(badge.style.display === '', 'badge shown');
  check(badge.textContent.includes('2 Spiele'), 'badge text counts visible games');
}

function icsEndExpected(d, t) {
  const [hh, mm] = t.split(':').map(Number);
  let total = hh * 60 + mm + 120;
  const extra = Math.floor(total / 1440);
  total %= 1440;
  const [dd, mo, yy] = d.split('.').map(Number);
  const dt = new Date(Date.UTC(yy, mo - 1, dd + extra));
  return `${dt.toISOString().slice(0, 10).replace(/-/g, '')}T${String(Math.floor(total / 60)).padStart(2, '0')}${String(total % 60).padStart(2, '0')}00`;
}

function todayKey() {
  const tk = new Date();
  return `${tk.getFullYear()}${String(tk.getMonth() + 1).padStart(2, '0')}${String(tk.getDate()).padStart(2, '0')}`;
}

section('.ics export (all teams, hide past)');
{
  const s = buildScenario();
  fire(s.icsBtn, 'click');
  check(s.body.lastChild !== null, 'download anchor created');
  check(s.body.lastChild.download === 'spielplan_alle.ics', 'filename spielplan_alle.ics');
  const txt = s.blob.parts.join('');
  check(txt.startsWith('BEGIN:VCALENDAR'), 'starts with BEGIN:VCALENDAR');
  check(txt.includes('VERSION:2.0'), 'VERSION:2.0');
  check(txt.includes('BEGIN:VTIMEZONE') && txt.includes('TZID:Europe/Berlin'), 'VTIMEZONE + TZID');
  check(txt.endsWith('END:VCALENDAR'), 'ends with END:VCALENDAR');
  const vevents = (txt.match(/BEGIN:VEVENT/g) || []).length;
  const futureCount = GAMES.filter((x) => x.datum.split('.').reverse().join('') >= todayKey()).length;
  check(vevents === futureCount, `VEVENT count ${vevents} == future games ${futureCount}`);
  const chunks = txt.split('\r\n');
  check(chunks.every((c) => c.length <= 73), 'all folded lines <= 73 chars');
  check(txt.includes('DTSTART;VALUE=DATE:'), 'all-day event uses VALUE=DATE');
  const late = GAMES.find((x) => x.time === '22:00');
  const lateDk = late.datum.split('.').reverse().join('');
  check(txt.includes(`DTSTART;TZID=Europe/Berlin:${lateDk}T220000`), 'late game DTSTART');
  const lateDend = icsEndExpected(late.datum, '22:00');
  check(txt.includes(`DTEND;TZID=Europe/Berlin:${lateDend}`), `late game DTEND rolls over (${lateDend})`);
  check(
    txt.includes('SUMMARY:TSV Gilching/Argelsried U15 - FC Semi\\; Kolon\\, Komma \\\\ Team'),
    'ics escaping of ; , \\ in SUMMARY',
  );
}

section('.ics export (single team slug)');
{
  const s = buildScenario();
  s.teamChecks[0].checked = true;
  fire(s.teamChecks[0], 'change');
  fire(s.icsBtn, 'click');
  check(s.body.lastChild.download === 'spielplan_tsv-gilching-argelsried-u15.ics', 'slug filename for single team');
}

console.log(failures ? `\n${failures} test(s) FAILED` : '\nAll tests passed.');
process.exit(failures ? 1 : 0);
