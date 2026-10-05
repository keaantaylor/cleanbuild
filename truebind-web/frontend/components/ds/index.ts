// TrueBind design system. Import from "@/components/ds"; read this file, not the components.
//
// Button, ButtonLink ............ primary | secondary | ghost | danger | outline | outlineQuiet; sizes 28/32/36/40/48; loading
// Chip, StatusPill, Tag, CountBadge   StatusPill maps codes through lib/statusMeta
// Panel, PageHeader, Eyebrow, Code, TwoLine, Kbd, Avatar, FileChip, Logo, Mark
// Skeleton, LoadingBlock, EmptyState, ErrorPanel, Banner, NotAvailable
// Field, Input, Textarea, Select, Checkbox
// Tabs (+ tabPanelProps) ........ line | segmented, roving focus
// Modal, Drawer, Popover, Menu, Tooltip   native <dialog>; focus returns to the opener
// Toaster ....................... bottom-right; set --toast-offset above sticky footers
// DataTable ..................... sort, select, ↑↓/Enter/Space, skeleton, empty, phone cards
// SheetGrid ..................... spreadsheet excerpt with flagged cells
// VerdictStrip, CoverageBar ..... grade withheld when INCOMPLETE, capped at 3 when issues open
// Stepper, Timeline, EvidenceCard, AuditEntry, ChainStatus, PIPELINE
// SearchCommand ................. ⌘K palette

export { Button, ButtonLink, buttonClass } from "./Button";
export type { ButtonSize, ButtonVariant } from "./Button";
export { Chip, CountBadge, StatusPill, Tag } from "./Chip";
export {
  Avatar,
  Banner,
  Code,
  EmptyState,
  ErrorPanel,
  Eyebrow,
  FileChip,
  Kbd,
  LoadingBlock,
  Logo,
  Mark,
  NotAvailable,
  PageHeader,
  Panel,
  Skeleton,
  TwoLine,
} from "./Primitives";
export { Checkbox, Field, Input, Select, Textarea } from "./Field";
export { Tabs, tabPanelProps } from "./Tabs";
export type { TabItem } from "./Tabs";
export { Drawer, Menu, Modal, Popover, Tooltip } from "./Overlay";
export type { MenuEntry } from "./Overlay";
export { Toaster } from "./Toast";
export { DataTable } from "./DataTable";
export type { Column, ColumnType } from "./DataTable";
export { SheetGrid } from "./SheetGrid";
export type { Cell, CellState, SheetRow } from "./SheetGrid";
export { CoverageBar, VerdictStrip } from "./Verdict";
export type { Coverage, VerdictMetric, VerdictState } from "./Verdict";
export { AuditEntry, ChainStatus, EvidenceCard, PIPELINE, Stepper, Timeline } from "./Pipeline";
export type { EvidenceLine, StepState, TimelineStep } from "./Pipeline";
export { SearchCommand } from "./SearchCommand";
export type { CommandItem } from "./SearchCommand";
