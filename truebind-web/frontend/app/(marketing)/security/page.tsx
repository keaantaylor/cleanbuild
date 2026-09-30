import { InfoPage } from "@/components/site/info-page";

export const metadata = { title: "Security · TrueBind" };

export default function Security() {
  return (
    <InfoPage
      kicker="Security"
      title="Your source data is evidence. We treat it that way."
      intro="TrueBind reads bordereaux, it never rewrites them. Everything we do to your data is recorded in a hash-chained audit trail you can verify."
      sections={[
        { h: "Source files are read-only", p: ["Every uploaded file is fingerprinted with SHA-256 on arrival. Mapping, validation and reconciliation work on a parsed copy; the original bytes are never modified.", "Reports cite the source hash, so anyone receiving one can confirm it describes the file they hold."] },
        { h: "A tamper-evident audit trail", p: ["Every action — by a person or the system — is written as a chained entry. Each entry includes the hash of the one before it, so any later edit or deletion breaks the chain and is detected by verification, which anyone in your organisation can run from the Audit trail."] },
        { h: "Hosting and access", p: ["Data is hosted in the EU and encrypted in transit and at rest. Access is role-based — Owner, Admin, Analyst, Viewer and Sender — with two-step verification and single sign-on (Microsoft Entra ID or any OpenID Connect provider).", "Each organisation sets how long uploaded files are kept; the default is 90 days."] },
        { h: "Reporting a vulnerability", p: ["Email security@truebind.ie. We acknowledge within one working day."] },
      ]}
    />
  );
}
