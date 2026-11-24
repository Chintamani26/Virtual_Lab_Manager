"use client";

import { useState } from "react";
import { Download, FileText, CheckCircle2, X } from "lucide-react";
import { Button, cx } from "./ui";
import { api } from "@/lib/api";
import type { ComplianceReport } from "@/lib/types";

interface AccreditationExportModalProps {
  open: boolean;
  onClose: () => void;
  compliance: ComplianceReport | null;
}

type ExportFormat = "csv" | "nba_dossier" | "naac_audit";

/**
 * Institutional accreditation & compliance export dialog for HODs.
 * Generates formatted compliance CSV or NBA / NAAC accreditation dossiers.
 */
export function AccreditationExportModal({
  open,
  onClose,
  compliance,
}: AccreditationExportModalProps) {
  const [format, setFormat] = useState<ExportFormat>("csv");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleExport() {
    setError(null);
    setDownloading(true);
    try {
      if (format === "csv") {
        const res = await api.complianceCsv();
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `compliance-report-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } else {
        // Generate structured accreditation summary dossier
        const dateStr = new Date().toISOString().slice(0, 10);
        const rows = compliance?.rows ?? [];
        const compliantCount = rows.filter((r) => r.status === "compliant").length;
        const atRiskCount = rows.filter((r) => r.status === "at_risk").length;
        const nonCompliantCount = rows.filter((r) => r.status === "non_compliant").length;
        const complianceRate = rows.length > 0 ? Math.round((compliantCount / rows.length) * 100) : 0;

        const content = [
          `========================================================================`,
          `ACCREDITATION AUDIT DOSSIER — ${format === "nba_dossier" ? "NBA CRITERION 4 & 5" : "NAAC CRITERION 2"}`,
          `Department: ${compliance?.department ?? "Engineering"}`,
          `Generated Date: ${dateStr}`,
          `Audit Compliance Rate: ${complianceRate}%`,
          `========================================================================`,
          ``,
          `1. SUMMARY OF PRACTICAL ASSESSMENTS`,
          `Total Published Labs: ${rows.length}`,
          `Compliant Labs (>=85% completion): ${compliantCount}`,
          `At-Risk Labs (60-84% completion): ${atRiskCount}`,
          `Non-Compliant Labs (<60% completion): ${nonCompliantCount}`,
          ``,
          `2. COURSE-WISE LAB ATTAINMENT MATRIX`,
          `Course | Practical Title | Faculty | Enrolled | Submitted | Pass % | Status`,
          `------------------------------------------------------------------------`,
          ...rows.map(
            (r) =>
              `${r.course_code.padEnd(8)} | ${r.practical_title.slice(0, 24).padEnd(24)} | ${(r.faculty_name ?? "—").slice(0, 14).padEnd(14)} | ${String(r.enrolled).padStart(4)} | ${String(r.submitted).padStart(4)} | ${String(r.avg_score_pct ? Math.round(r.avg_score_pct) + "%" : "—").padStart(6)} | ${r.status}`,
          ),
          ``,
          `3. QUALITY ASSURANCE CERTIFICATION`,
          `This document certifies that laboratory continuous evaluations and`,
          `rubric assessments were conducted in compliance with university standards.`,
          `Signed: Head of Department (${compliance?.department ?? "Engineering"})`,
          `========================================================================`,
        ].join("\n");

        const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${format}_audit_report_${dateStr}.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-lg rounded-xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Export Institutional Dossier</h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Department compliance audit for internal reviews and accreditation
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Select Report Format</p>

          <div className="grid gap-2.5">
            {[
              {
                id: "csv" as const,
                title: "Standard Compliance CSV",
                desc: "Complete tabular data with student submissions, due dates, and completion status",
                badge: "Spreadsheet",
              },
              {
                id: "nba_dossier" as const,
                title: "NBA Accreditation Dossier (Criteria 4 & 5)",
                desc: "Structured lab attainment matrix, faculty allocation, and continuous assessment evidence",
                badge: "Accreditation",
              },
              {
                id: "naac_audit" as const,
                title: "NAAC Teaching-Learning Audit (Criterion 2)",
                desc: "Course outcome lab completion records and student experimental learning verification",
                badge: "Accreditation",
              },
            ].map((opt) => (
              <label
                key={opt.id}
                onClick={() => setFormat(opt.id)}
                className={cx(
                  "flex items-start gap-3.5 rounded-lg border p-3.5 cursor-pointer transition-all",
                  format === opt.id
                    ? "border-indigo-600 bg-indigo-50/40 ring-1 ring-indigo-600"
                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/60",
                )}
              >
                <input
                  type="radio"
                  name="export_format"
                  className="mt-0.5 accent-indigo-600"
                  checked={format === opt.id}
                  onChange={() => setFormat(opt.id)}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-900">{opt.title}</span>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                      {opt.badge}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{opt.desc}</p>
                </div>
              </label>
            ))}
          </div>

          {error && <p className="text-xs text-rose-600">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-slate-100 bg-slate-50/50 px-6 py-3.5 rounded-b-xl">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={downloading}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" loading={downloading} onClick={handleExport}>
            <Download className="mr-1.5 h-4 w-4" />
            {format === "csv" ? "Download CSV" : "Generate Dossier"}
          </Button>
        </div>
      </div>
    </div>
  );
}
