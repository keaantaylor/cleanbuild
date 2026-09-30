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
        { h: "How long we keep it", p: ["Workspace data is kept for the life of your contract plus the retention period you set. Uploaded files are kept for the retention period your organisation sets (90 days by default). Audit trail entries are retained so the chain stays verifiable."] },
        { h: "Your rights", p: ["You can request access, correction, deletion or export of your personal data at privacy@truebind.ie. You may also complain to the Data Protection Commission (dataprotection.ie)."] },
      ]}
    />
  );
}
