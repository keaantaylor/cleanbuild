import { InfoPage } from "@/components/site/info-page";

export const metadata = { title: "Security · TrueBind" };

// Every statement here must be true of the running service today. When hosting,
// sub-processors or certifications change, change this page in the same release.
export default function Security() {
  return (
    <InfoPage
      kicker="Security"
      title="What happens to your file, exactly."
      intro="TrueBind reads your bordereau and never edits it. This page says where your data is, who can see it, how long we keep it and what we have not done yet."
      sections={[
        { h: "Your file is never changed", p: ["Every upload is fingerprinted (SHA-256) on arrival and stored as received. Checks run on a parsed copy. The annotated workbook we give back is your own file with colours and notes added; your values are untouched. The corrected copy changes only formatting (for example “Euro” to EUR) and lists every change on a Change Log sheet."] },
        { h: "Where your data is", p: ["The application and its database run in the United States (US-East, Virginia) on Render, and the website on Vercel. Data travels over HTTPS (TLS). If your organisation needs data kept in the EU or UK, tell us before you upload and we will confirm the options in writing."] },
        { h: "How long we keep it", p: ["By default, the uploaded file, its rows and its findings are permanently deleted 30 days after upload. Each organisation can choose a period from 1 to 365 days, and deleting a report removes its data at once. The audit trail keeps only the file name, its fingerprint and what was done. Copies can remain in our hosting provider’s database backups until those expire."] },
        { h: "Anonymising names", p: ["An organisation can switch on “Anonymise insured names”. Names are then replaced by a stable code (for example “Insured 7F3A21”) in everything we keep, including exports, while duplicate and month-on-month checks still work."] },
        { h: "AI", p: ["The checks themselves are rules, not AI. If AI-assisted column mapping is switched on, it receives only column headers and masked value shapes (for example “Xxxxx Xxx” or “9999-99-99”), never cell values, and only from an EU or UK region. It is off unless configured, and every AI suggestion is confirmed by a person."] },
        { h: "Who can see it", p: ["Only members of your organisation, under roles (Owner, Admin, Analyst, Viewer, Sender). Each organisation’s data is separated in the database by row-level security. Two-step verification and single sign-on (Microsoft Entra ID or any OpenID Connect provider) are available, and an owner can require two-step verification for everyone."] },
        { h: "A tamper-evident audit trail", p: ["Every action, by a person or the system, is written as a chained entry that includes the hash of the one before it, so a later edit or deletion is detected. Anyone in your organisation can verify the chain from the Audit trail."] },
        { h: "Who else handles data", p: ["Render (application and database hosting, USA), Vercel (website, USA), and, only if you use them, Stripe (billing) and our email provider (sending exports you ask us to email). We do not sell or share data, and we do not use it to train AI models."] },
        { h: "What we have not done yet", p: ["We do not yet hold ISO 27001 or SOC 2 certification and have not yet commissioned an independent penetration test. A data processing agreement is available on request."] },
        { h: "Reporting a vulnerability", p: ["Email security@truebind.ie. We acknowledge within one working day."] },
      ]}
    />
  );
}
