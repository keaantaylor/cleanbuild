import { DemoReport } from "@/components/site/demo-report";

export const metadata = {
  title: "Sample Health Check · TrueBind",
  description: "A real TrueBind Health Check of a synthetic 500-row claims bordereau: the verdict, the top fixes, the annotated workbook, the corrected copy and the query letter.",
};

export default function DemoPage() {
  return <DemoReport />;
}
