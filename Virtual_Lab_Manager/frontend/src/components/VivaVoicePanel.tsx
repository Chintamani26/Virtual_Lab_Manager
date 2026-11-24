"use client";

import { useState } from "react";
import { Eye, EyeOff, Award, CheckCircle } from "lucide-react";
import { Button, cx } from "./ui";

interface VivaItem {
  question: string;
  answer: string;
}

interface VivaVoicePanelProps {
  questions: VivaItem[];
  topic: string;
}

/**
 * Interactive Viva Voce assessment panel for instructors.
 * Features answer reveal toggles, per-question score counters (0–5),
 * and live oral examination evaluation tracking.
 */
export function VivaVoicePanel({ questions, topic }: VivaVoicePanelProps) {
  const [showAnswers, setShowAnswers] = useState(true);
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});
  const [scores, setScores] = useState<Record<number, number>>({});
  const [copied, setCopied] = useState(false);

  if (!questions || questions.length === 0) return null;

  const totalScore = Object.values(scores).reduce((a, b) => a + b, 0);
  const maxPossible = questions.length * 5;

  function toggleQuestion(idx: number) {
    setRevealed((prev) => ({ ...prev, [idx]: !prev[idx] }));
  }

  function setQuestionScore(idx: number, score: number) {
    setScores((prev) => ({ ...prev, [idx]: score }));
  }

  function copyVivaNotes() {
    const summary = [
      `Viva Voce Assessment: ${topic}`,
      `Date: ${new Date().toLocaleDateString()}`,
      `Total Score: ${totalScore} / ${maxPossible}`,
      `-----------------------------------------`,
      ...questions.map((q, i) => `Q${i + 1}: ${q.question}\nScore: ${scores[i] ?? 0}/5`),
    ].join("\n");
    navigator.clipboard.writeText(summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white overflow-hidden shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/75 px-5 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
            <span>Interactive Viva Voce Examination</span>
            <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 border border-indigo-200">
              {questions.length} Questions
            </span>
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Conduct oral examinations with quick answer reference and rubric scoring
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowAnswers((prev) => !prev)}
            className="text-xs"
          >
            {showAnswers ? (
              <>
                <EyeOff className="mr-1.5 h-3.5 w-3.5" /> Hide All Answers
              </>
            ) : (
              <>
                <Eye className="mr-1.5 h-3.5 w-3.5" /> Show All Answers
              </>
            )}
          </Button>

          {Object.keys(scores).length > 0 && (
            <Button size="sm" variant="secondary" onClick={copyVivaNotes} className="text-xs">
              <CheckCircle className="mr-1.5 h-3.5 w-3.5" />
              {copied ? "Copied Summary!" : "Copy Viva Score"}
            </Button>
          )}
        </div>
      </div>

      <div className="divide-y divide-slate-100 p-2">
        {questions.map((v, i) => {
          const isAnswerVisible = showAnswers || !!revealed[i];
          const currentScore = scores[i] ?? null;

          return (
            <div key={i} className="p-3.5 hover:bg-slate-50/40 rounded-md transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">
                    <span className="font-mono text-xs text-indigo-600 mr-2">Q{i + 1}.</span>
                    {v.question}
                  </p>

                  {isAnswerVisible && (
                    <div className="mt-2.5 rounded bg-slate-50 border border-slate-100 p-2.5 text-xs text-slate-700 leading-relaxed">
                      <span className="font-semibold text-slate-500 uppercase tracking-wider block text-[10px] mb-1">
                        Expected Concept Answer:
                      </span>
                      {v.answer}
                    </div>
                  )}

                  {!showAnswers && (
                    <button
                      type="button"
                      onClick={() => toggleQuestion(i)}
                      className="mt-1.5 text-xs text-indigo-600 hover:text-indigo-500"
                    >
                      {revealed[i] ? "Hide answer" : "Show answer"}
                    </button>
                  )}
                </div>

                {/* Score selector 0-5 */}
                <div className="shrink-0 flex items-center gap-1">
                  <span className="text-xs text-slate-400 mr-1 hidden sm:inline">Score:</span>
                  {[1, 2, 3, 4, 5].map((pts) => (
                    <button
                      key={pts}
                      type="button"
                      onClick={() => setQuestionScore(i, currentScore === pts ? 0 : pts)}
                      className={cx(
                        "h-7 w-7 rounded text-xs font-mono font-medium transition-colors",
                        currentScore === pts
                          ? "bg-indigo-600 text-white shadow-sm"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                      )}
                    >
                      {pts}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {Object.keys(scores).length > 0 && (
        <div className="border-t border-slate-100 bg-slate-50 px-5 py-3 flex items-center justify-between text-xs">
          <span className="text-slate-500">Graded {Object.keys(scores).length} of {questions.length} questions</span>
          <span className="font-medium text-slate-900 flex items-center gap-1.5">
            <Award className="h-4 w-4 text-indigo-600" />
            Total Viva Score: <strong className="font-mono text-indigo-600 text-sm">{totalScore} / {maxPossible}</strong>
          </span>
        </div>
      )}
    </section>
  );
}
