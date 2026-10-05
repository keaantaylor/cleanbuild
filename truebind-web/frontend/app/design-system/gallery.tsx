"use client";

import { DownloadSimple, PencilSimple, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import {
  AuditEntry,
  Avatar,
  Banner,
  Button,
  ButtonLink,
  ChainStatus,
  Checkbox,
  Chip,
  CountBadge,
  CoverageBar,
  DataTable,
  Drawer,
  EmptyState,
  ErrorPanel,
  EvidenceCard,
  Eyebrow,
  Field,
  FileChip,
  Input,
  Kbd,
  LoadingBlock,
  Logo,
  Menu,
  Modal,
  PageHeader,
  Panel,
  Popover,
  SearchCommand,
  Select,
  SheetGrid,
  Skeleton,
  StatusPill,
  Stepper,
  Tabs,
  Tag,
  Textarea,
  Timeline,
  Tooltip,
  TwoLine,
  VerdictStrip,
  type Column,
} from "@/components/ds";
import { useUi } from "@/lib/ui";
import s from "./gallery.module.css";

type Theme = "light" | "dark";

// Sample data, from the landing mockup (Harbour MGA, Kestrel TPA). Not a customer.
interface SampleFinding {
  id: string;
  status: string;
  label: string;
  code: string;
  submission: string;
  claim: string;
  amount: number;
  age: string;
}
const FINDINGS: SampleFinding[] = [
  { id: "1", status: "FAIL", label: "Incurred doesn't add up", code: "CR0035M", submission: "Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx", claim: "HBR-0008", amount: 15000, age: "2 h" },
  { id: "2", status: "FAIL", label: "Over settlement authority", code: "BND_OVER_AUTHORITY", submission: "Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx", claim: "HBR-0006", amount: 49898, age: "2 h" },
  { id: "3", status: "REVIEW", label: "Same row sent twice", code: "DUP_EXACT", submission: "bdx_0826.csv", claim: "KT-22817", amount: 49898, age: "1 d" },
  { id: "4", status: "REVIEW", label: "Loss date missing", code: "CR0012M", submission: "Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx", claim: "HBR-0011", amount: 2000, age: "2 h" },
  { id: "5", status: "NOT_EVALUABLE", label: "Payments not checked", code: "PAY_NOT_CONFIGURED", submission: "Norland Aug.xlsx", claim: "NC/3391", amount: 38980, age: "3 d" },
];
const money = (n: number) => `£${n.toLocaleString("en-GB", { minimumFractionDigits: 2 })}`;

const COLUMNS: Column<SampleFinding>[] = [
  { key: "status", header: "Status", type: "status", render: (r) => <StatusPill status={r.status} />, sortValue: (r) => r.status, key3: true, width: 130 },
  { key: "finding", header: "Finding", type: "twoLine", render: (r) => <TwoLine label={r.label} code={r.code} />, sortValue: (r) => r.label, key3: true },
  { key: "submission", header: "Submission", render: (r) => <span style={{ color: "var(--text-2)" }}>{r.submission}</span> },
  { key: "claim", header: "Claim", type: "code", render: (r) => r.claim, sortValue: (r) => r.claim },
  { key: "amount", header: "Amount", type: "numeric", render: (r) => money(r.amount), sortValue: (r) => r.amount, key3: true },
  { key: "age", header: "Age", render: (r) => r.age },
];

const TOKENS = ["bg", "bg-subtle", "bg-muted", "surface", "border", "border-strong", "text", "text-2", "text-3", "brand", "brand-subtle", "highlight", "band", "danger", "danger-bg", "warning", "warning-bg", "success", "success-bg", "neutral", "neutral-bg"];

function Section({ id, title, note, children }: { id: string; title: string; note?: string; children: React.ReactNode }) {
  return (
    <section id={id} className={s.section} aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className={s.sectionTitle}>{title}</h2>
      {note && <p className={s.note}>{note}</p>}
      {children}
    </section>
  );
}

export function DesignSystemGallery({ initialTheme = "light" }: { initialTheme?: Theme }) {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [tab, setTab] = useState("findings");
  const [seg, setSeg] = useState("all");
  const [step, setStep] = useState(2);
  const [modal, setModal] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [search, setSearch] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const { toast } = useUi();

  const switchTheme = (t: string) => {
    setTheme(t as Theme);
    const u = new URL(window.location.href);
    u.searchParams.set("theme", t);
    window.history.replaceState(null, "", u);
  };

  return (
    <div className={s.page} data-theme={theme}>
      <header className={s.head}>
        <Logo size={24} />
        <div className={s.row}>
          <span className={s.label}>Design system · Sample data</span>
          <Tabs label="Theme" variant="segmented" idBase="theme" value={theme} onChange={switchTheme} items={[{ id: "light", label: "Light (app)" }, { id: "dark", label: "Dark (marketing)" }]} />
        </div>
      </header>

      <div className={s.wrap}>
        <Section id="colour" title="Colour" note="Every value lives in styles/tokens.css. Colour carries meaning (status, highlight, the brand blue); hierarchy comes from type and space.">
          <div className={s.swatches}>
            {TOKENS.map((t) => (
              <div key={t} className={s.swatch}>
                <div className={s.swatchColor} style={{ background: `var(--${t})` }} />
                <span>--{t}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section id="type" title="Type" note="Inter for interface and headings, IBM Plex Mono for codes, cell values and hashes. Numbers are tabular.">
          <div className={s.type}>
            {[64, 56, 44, 32, 24, 20, 16, 14, 13, 12].map((n) => (
              <div key={n} className={s.typeRow}>
                <span>{n}px</span>
                <span style={{ fontSize: n, fontWeight: n >= 32 ? 500 : n === 24 ? 600 : 400, letterSpacing: n >= 44 ? "-0.03em" : n >= 24 ? "-0.02em" : 0, lineHeight: 1.15 }}>
                  Clean claims data
                </span>
              </div>
            ))}
            <div className={s.typeRow}>
              <span>mono</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>HBR-0004 · 24,500.00 · 9f2c41e07a</span>
            </div>
          </div>
          <div className={s.marketingSample}>
            <Eyebrow>Claims bordereaux integrity</Eyebrow>
            <h3 className={s.h1Marketing}>Clean claims data.</h3>
            <p className={s.sub}>Marketing heading on the 4px grid, 56px desktop and 40px on phones.</p>
          </div>
        </Section>

        <Section id="buttons" title="Buttons" note="One primary per view. Outline is the marketing style from the mockup.">
          <div className={s.row}>
            <Button variant="primary">Confirm mapping</Button>
            <Button>Export</Button>
            <Button variant="ghost">Cancel</Button>
            <Button variant="danger">Remove member</Button>
            <Button variant="outline" size={40}>Run a Bordereau Health Check</Button>
            <Button variant="outlineQuiet" size={40}>See TrueBind in action</Button>
          </div>
          <div className={s.row}>
            {([28, 32, 36, 40, 48] as const).map((n) => (
              <Button key={n} size={n}>Size {n}</Button>
            ))}
          </div>
          <div className={s.row}>
            <Button variant="primary" loading>Confirm mapping</Button>
            <Button disabled>Disabled</Button>
            <Button iconOnly aria-label="Download"><DownloadSimple size={16} /></Button>
            <ButtonLink href="#buttons" variant="secondary">A link as a button</ButtonLink>
          </div>
        </Section>

        <Section id="chips" title="Chips and status" note="Every status goes through statusMeta(): the word carries the meaning, colour only repeats it.">
          <div className={s.row}>
            {["FAIL", "REVIEW", "PASS", "NOT_EVALUABLE", "PARTIAL", "MAPPED_BY_ALIAS", "MAPPED_BY_MEMORY", "MAPPED_BY_AI", "UNMAPPED"].map((c) => (
              <StatusPill key={c} status={c} />
            ))}
          </div>
          <div className={s.row}>
            <Chip tone="brand">Processing</Chip>
            <Tag>Beta</Tag>
            <Tag>Sample</Tag>
            <CountBadge n={4} />
            <CountBadge n={23} strong />
            <Kbd>⌘K</Kbd>
            <Avatar name="Molly Byrne" />
            <FileChip name="Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx" meta="Harbour MGA · 1,284 rows" />
          </div>
        </Section>

        <Section id="forms" title="Fields">
          <div className={s.grid3}>
            <Field label="Work email" help="We send the sign-in link here.">
              <Input type="email" placeholder="name@company.com" />
            </Field>
            <Field label="Password" error="That password doesn't match this email. Try again or reset it.">
              <Input type="password" defaultValue="hunter22" />
            </Field>
            <Field label="Sender" optional>
              <Select defaultValue="">
                <option value="" disabled>Choose a sender</option>
                <option>Harbour MGA</option>
                <option>Kestrel TPA</option>
              </Select>
            </Field>
            <Field label="Reason" help="Recorded in the audit trail.">
              <Textarea placeholder="Why is this value accepted as reported?" />
            </Field>
            <Field label="Claim reference">
              <Input mono defaultValue="HBR-0004" />
            </Field>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <Checkbox label="Require two-step verification for everyone" defaultChecked />
              <Checkbox label="Disabled option" disabled />
            </div>
          </div>
        </Section>

        <Section id="tabs" title="Tabs">
          <Tabs label="Report sections" value={tab} onChange={setTab} items={[{ id: "findings", label: "Findings", count: 23 }, { id: "claims", label: "Claims", count: 1284 }, { id: "mapping", label: "Mapping" }, { id: "reconciliation", label: "Reconciliation" }, { id: "evidence", label: "Evidence" }]} />
          <Tabs label="Saved views" variant="segmented" idBase="views" value={seg} onChange={setSeg} items={[{ id: "all", label: "All" }, { id: "review", label: "Needs review" }, { id: "incomplete", label: "Incomplete" }, { id: "clean", label: "Clean" }]} />
        </Section>

        <Section id="layout" title="Page header, panels and states">
          <PageHeader title="Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx" meta="Harbour MGA · Property binder 2026 · received 3 Sep 2026 · 1,284 rows" actions={<><Button>Export</Button><Button variant="primary">Review breaches</Button></>} />
          <div className={s.grid2}>
            <Panel title="Needs a decision" sub="Most severe first" actions={<Button variant="ghost" size={28}>View all</Button>}>
              <LoadingBlock label="Loading findings" rows={4} />
            </Panel>
            <Panel title="Recent submissions" flush>
              <EmptyState title="No submissions yet" body="Upload a bordereau and TrueBind maps, validates and reconciles it. You confirm the mapping before anything is checked." action={<Button variant="primary">New submission</Button>} />
            </Panel>
          </div>
          <ErrorPanel title="The workbook couldn't be read" body="Sheet 'Claims', row 4: the header row has two columns called 'Paid'. Rename one in the file and upload it again." reference="req_7f3a9c21" action={<Button size={28}>Upload a new file</Button>} />
          <Banner tone="warning">Binder checks are in beta. Confirm results against the binding authority wording before issuing any breach notice.</Banner>
          <Banner tone="info">Sample data. Nothing here is a real submission.</Banner>
          <div className={s.row}>
            <Skeleton w={120} />
            <Skeleton w={200} />
            <Skeleton w={64} h={22} />
          </div>
        </Section>

        <Section id="table" title="Data table" note="Sort by any header, select rows, move with ↑/↓, Enter opens, Space selects. Phones show 3 key columns per card.">
          <div className={s.row}>
            <Button size={28} onClick={() => setLoading((l) => !l)}>{loading ? "Show rows" : "Show loading"}</Button>
            <span className={s.label}>{selected.size} selected</span>
          </div>
          <Panel flush>
            <DataTable
              caption="Sample findings"
              columns={COLUMNS}
              rows={FINDINGS}
              rowId={(r) => r.id}
              rowLabel={(r) => `${r.label}, ${r.claim}`}
              selectable
              selected={selected}
              onSelectedChange={setSelected}
              loading={loading}
              onOpen={(r) => toast(`Would open ${r.claim}`, "info")}
            />
          </Panel>
          <Panel flush>
            <DataTable caption="Empty" columns={COLUMNS} rows={[]} rowId={(r) => r.id} empty={<EmptyState title="Nothing needs a decision" body="Every open finding has been decided. New ones appear here as submissions are processed." />} />
          </Panel>
        </Section>

        <Section id="sheet" title="Sheet grid" note="Values exactly as received. Flagged cells explain themselves on hover or focus.">
          <SheetGrid
            label="Sample: Harbour MGA claims sheet"
            title="Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx"
            formula={{ ref: "A4", value: "Clm No." }}
            headerRow={4}
            headers={["Clm No.", "Bdx Mth", "DOL", "Insured", "Paid £", "Resv", "Total Inc"]}
            rows={[
              { n: 5, cells: ["HBR-0004", "Jul-26", "12/05/2026", "Atlas Freight Ltd", "18,400.00", "6,100.00", "24,500.00"] },
              { n: 6, cells: ["HBR-0006", "Jul-26", "19/05/2026", "Kestrel Farms", "12,812.00", "36,896.00", "49,898.00"] },
              { n: 7, cells: ["HBR-0008", "Jul-26", "04/06/2026", "Bexley Dental", "9,800.00", "4,200.00", { v: "15,000.00", state: "error", note: "Paid 9,800.00 + reserve 4,200.00 = 14,000.00, not 15,000.00" }] },
              { n: 8, cells: ["HBR-0011", "Jul-26", { v: "", state: "warn", note: "Date of loss is missing; it's a required field" }, "Ferris & Lane", "1,120.00", "880.00", "2,000.00"] },
              { n: 9, cells: [{ v: "HBR-0006", state: "warn", note: "Same claim as row 6 with the same values" }, "Jul-26", "19/05/2026", "Kestrel Farms", "12,812.00", "36,896.00", "49,898.00"] },
            ]}
            tabs={["Claims", "Reserves", "Movements"]}
          />
        </Section>

        <Section id="verdict" title="Verdict strip and coverage" note="The component itself withholds the grade when a report is incomplete and caps it at 3 while breaches are open.">
          <VerdictStrip
            state="ISSUES_OPEN"
            title="2 breaches open. Not ready to accept."
            sentence="Incurred doesn't add up on HBR-0008, and HBR-0006 is over the settlement authority."
            metrics={[
              { label: "Claims assessed", value: "1,284 / 1,284", caption: "Every source row reconciles" },
              { label: "Total incurred", value: "£2,418,920.50", caption: "GBP only" },
              { kind: "grade", grade: 5 },
            ]}
          />
          <VerdictStrip
            state="INCOMPLETE"
            title="Grade withheld. 4 required fields not mapped."
            sentence="Map them to check every claim, or process anyway and the report says what wasn't assessed."
            reasons={["Date of loss not mapped", "Claim status not mapped", "Currency not mapped", "Reporting period not mapped"]}
            metrics={[
              { label: "Claims assessed", value: "0 / 412", caption: "Waiting on the mapping" },
              { label: "Total incurred", value: "Not assessed" },
              { kind: "grade", grade: 4 },
            ]}
          />
          <VerdictStrip state="CLEAN" title="No open findings. Ready to accept." sentence="Every check ran on every claim." metrics={[{ label: "Claims assessed", value: "96 / 96" }, { label: "Total incurred", value: "€310,004.00" }, { kind: "grade", grade: 5 }]} />
          <Panel>
            <CoverageBar value={{ checked: 1259, flagged: 23, unmapped: 1, notAssessed: 2 }} />
            <p className={s.note} style={{ marginTop: 16 }}>Sample: Harbour MGA · Claims Aug-26 · 1,284 rows</p>
          </Panel>
        </Section>

        <Section id="pipeline" title="Pipeline, timeline and evidence">
          <Stepper current={step} onSelect={setStep} label="Pipeline (interactive)" />
          <Stepper current={3} compact label="Checks run" states={["done", "done", "done", "active", "upcoming", "upcoming"]} />
          <Stepper current={2} compact label="Failed run" states={["done", "done", "failed", "upcoming", "upcoming", "upcoming"]} />
          <Timeline
            steps={[
              { title: "Map", body: "Columns matched to Lloyd's CRS v5.2 by alias rules first. AI only proposes headers the rules can't place, never cell values.", children: <EvidenceCard lines={[{ tone: "success", text: "Clm No. → claim_reference" }, { tone: "success", text: "LOSS_DT → date_of_loss" }, { tone: "neutral", text: "Adj Notes → unmapped" }]} /> },
              { title: "Validate", body: "Arithmetic, required data, dates and formats checked on every row.", children: <EvidenceCard lines={[{ tone: "danger", text: "row 5 · incurred 39,171.00 ≠ 37,671.00" }, { tone: "danger", text: "row 9 · insured name missing" }, { tone: "warning", text: "row 26 · 03/04/2026 ambiguous" }]} /> },
              { title: "Reconcile", body: "Exact resubmissions kept apart from legitimate claim development.", children: <EvidenceCard lines={[{ tone: "danger", text: "HBR-0006 · rows 7 & 22 · exact" }, { tone: "success", text: "HBR-0019 · Jul → Aug · development" }]} /> },
            ]}
          />
          <Panel title="Audit trail" actions={<ChainStatus intact entries={116} />}>
            <AuditEntry seq={113} action="Mapping v3 confirmed" actor="molly" when="14:02" whenTitle="3 Sep 2026, 14:02" hash="9f2c41e07a8b55d2c0e9a1f6b3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f6" />
            <AuditEntry seq={112} action="Workbook read, mapping proposed" actor="system" when="13:58" hash="1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f809" />
          </Panel>
        </Section>

        <Section id="overlays" title="Overlays" note="Modal and drawer are native dialogs: focus is trapped, Esc closes, focus returns to the button that opened them.">
          <div className={s.row}>
            <Button onClick={() => setModal(true)}>Open modal</Button>
            <Button onClick={() => setDrawer(true)}>Open drawer</Button>
            <Button onClick={() => setSearch(true)}>Open ⌘K</Button>
            <Menu
              label="Row actions"
              align="start"
              items={[{ label: "Edit", icon: PencilSimple, onSelect: () => toast("Edit", "info") }, { label: "Download", icon: DownloadSimple, onSelect: () => toast("Download", "info") }, { kind: "separator" }, { label: "Delete", icon: Trash, danger: true, onSelect: () => toast("Deleted", "warn") }]}
              trigger={({ props }) => <Button {...props} aria-haspopup="menu">Menu</Button>}
            />
            <Popover label="Filter" align="start" trigger={({ props }) => <Button {...props}>Popover</Button>}>
              {() => <div style={{ padding: 14, fontSize: 13, color: "var(--text-2)" }}>Anchored panel. Esc or an outside click closes it.</div>}
            </Popover>
            <Tooltip content="Paid plus reserve should equal incurred.">
              <Button variant="ghost">Tooltip</Button>
            </Tooltip>
            <Button onClick={() => toast("Mapping confirmed. Validation started.", "ok")}>Toast</Button>
            <Button onClick={() => toast("That file is password-protected. Remove the password and upload it again.", "err")}>Error toast</Button>
          </div>
        </Section>
      </div>

      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title="Process without 4 required fields?"
        description="The report will be marked incomplete and no grade will be shown."
        footer={<><Button variant="ghost" onClick={() => setModal(false)}>Cancel</Button><Button variant="primary" onClick={() => setModal(false)}>Process anyway</Button></>}
      >
        Date of loss, claim status, currency and reporting period aren&rsquo;t mapped. Checks that need them are listed as not assessed.
      </Modal>
      <Drawer open={drawer} onClose={() => setDrawer(false)} title="Incurred doesn't add up" meta={<><StatusPill status="FAIL" /> <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>CR0035M</span></>}>
        <p style={{ marginTop: 0, color: "var(--text-2)", fontSize: 14 }}>Claims · row 7 · Total Inc</p>
        <p style={{ fontSize: 14 }}>Paid 9,800.00 plus reserve 4,200.00 is 14,000.00, but the file says 15,000.00, a difference of 1,000.00.</p>
      </Drawer>
      <SearchCommand
        open={search}
        onClose={() => setSearch(false)}
        items={[
          { id: "a", group: "Pages", label: "Home", run: () => undefined },
          { id: "b", group: "Pages", label: "Submissions", run: () => undefined },
          { id: "c", group: "Submissions", label: "Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx", hint: "Harbour MGA · Sample", run: () => undefined },
        ]}
      />
    </div>
  );
}
