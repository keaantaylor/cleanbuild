import { InfoPage } from "@/components/site/info-page";

export const metadata = { title: "Lloyd’s CRS v5.2 · TrueBind" };

export default function Crs() {
  return (
    <InfoPage
      kicker="Ruleset"
      title="Lloyd’s Coverholder Reporting Standards v5.2"
      intro="TrueBind maps every sender’s columns to the Lloyd’s CRS v5.2 claims fields and validates each row against the standard’s required data, formats and arithmetic."
      sections={[
        { h: "What we map", p: ["Claim reference, reporting period, insured name, dates of loss and notification, paid to date, reserve, fees, total incurred, claim status and the rest of the CRS claims set. Alias rules place known headers first; AI only proposes headers the rules can’t place, never cell values, and a person confirms before validation runs."] },
        { h: "What we check", p: ["Required fields (for example CR0035M insured name), total incurred against paid + reserve + fees (CR0092M), date order and ambiguous date formats, negative reserves, and exact resubmissions versus claim development across periods."] },
        { h: "What we say we didn’t check", p: ["Columns with no CRS field are reported as unmapped, not interpreted. Checks outside the ruleset - reserve adequacy, sanctions screening - are reported as not assessed. Every Health Check lists them."] },
      ]}
    />
  );
}
