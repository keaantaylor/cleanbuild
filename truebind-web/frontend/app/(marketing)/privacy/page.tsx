import { InfoPage } from "@/components/site/info-page";

export const metadata = { title: "Privacy · TrueBind" };

export default function Privacy() {
  return (
    <InfoPage
      kicker="Privacy"
      title="Privacy notice"
      intro="TrueBind is operated from Ireland and processes personal data under the GDPR. This notice explains what we collect and why."
      sections={[
        { h: "Who we are", p: ["TrueBind (truebind.ie) is the data processor for bordereau data our customers upload, and the controller for account and website data. Contact: privacy@truebind.ie."] },
        { h: "What we process", p: ["Account data: name, work email, company and role. Bordereau data: the claims records in files you upload, which may include insured names and claim details. Website data: essential cookies only; no advertising trackers."] },
        { h: "How long we keep it", p: ["Workspace data is kept for the life of your contract plus the retention period you set. Uploaded files, their rows and findings are permanently deleted after the retention period your organisation sets (30 days by default), or at once when you delete a report. Audit trail entries (file name, fingerprint and actions only) are retained so the chain stays verifiable. Copies can remain in our hosting provider’s backups until they expire."] },
        { h: "Where it is processed", p: ["Our application and database run in the United States (Render, US-East) and our website on Vercel. Transfers outside the EEA rely on our providers’ Standard Contractual Clauses. See the Security page for the full list of providers."] },
        { h: "Your rights", p: ["You can request access, correction, deletion or export of your personal data at privacy@truebind.ie. You may also complain to the Data Protection Commission (dataprotection.ie)."] },
      ]}
    />
  );
}
