import type { ExceptionRow } from "@/lib/types";
import { Table, type Column } from "@/components/ui/Table";
import { SeverityBadge } from "@/components/ui/statusBadges";
import { formatCurrency } from "@/lib/formatters";

export function ExceptionsTable({ rows, onSelect }: { rows: ExceptionRow[]; onSelect: (row: ExceptionRow) => void }) {
  const columns: Column<ExceptionRow>[] = [
    { key: "claim_ref", header: "Claim ref", render: (r) => r.claim_reference ?? "—" },
    { key: "sheet", header: "Sheet · row", render: (r) => `${r.sheet_name ?? "—"} · ${r.row_index + 1}` },
    { key: "exception", header: "Exception", render: (r) => (
      <div>
        <SeverityBadge severity={r.severity} /> <span>{r.message}</span>
      </div>
    ) },
    { key: "amount", header: "Amount", render: (r) => formatCurrency(r.amount), align: "right" },
  ];

  return <Table columns={columns} rows={rows} onRowClick={onSelect} rowKey={(r) => r.validation_result_id} />;
}
