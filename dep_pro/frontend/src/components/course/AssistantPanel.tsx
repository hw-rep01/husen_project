"use client";

import { FormEvent, useState } from "react";
import { apiFetch, errorMessage } from "@/lib/api";
import type { AnswerResult } from "@/lib/types";
import { Badge, Button, Card, Empty, ErrorText, Input, Textarea } from "@/components/ui";

type Mode = "ask" | "summary";

export function AssistantPanel({ courseId }: { courseId: number }) {
  const [mode, setMode] = useState<Mode>("ask");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnswerResult | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response =
        mode === "ask"
          ? await apiFetch<AnswerResult>(`/api/courses/${courseId}/ask`, {
              method: "POST",
              json: { question: text },
            })
          : await apiFetch<AnswerResult>(`/api/courses/${courseId}/summary`, {
              method: "POST",
              json: { topic: text },
            });
      setResult(response);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card
        title="المساعد الذكي"
        className="lg:col-span-2"
        actions={
          <div className="flex gap-2">
            <Button variant={mode === "ask" ? "primary" : "secondary"} onClick={() => setMode("ask")}>
              سؤال
            </Button>
            <Button variant={mode === "summary" ? "primary" : "secondary"} onClick={() => setMode("summary")}>
              تلخيص موضوع
            </Button>
          </div>
        }
      >
        <form onSubmit={submit} className="space-y-4">
          {mode === "ask" ? (
            <Textarea
              required
              minLength={3}
              maxLength={2000}
              rows={3}
              placeholder="اكتب سؤالك من منهج المادة..."
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          ) : (
            <Input
              required
              minLength={2}
              maxLength={300}
              placeholder="اسم الموضوع المراد تلخيصه"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          )}
          {error && <ErrorText>{error}</ErrorText>}
          <Button type="submit" disabled={busy}>
            {busy ? "جارٍ البحث في الملزمة..." : mode === "ask" ? "إرسال السؤال" : "لخّص"}
          </Button>
        </form>

        {result && (
          <div className="mt-6 space-y-3 border-t border-slate-100 pt-6">
            <div>
              {result.grounded ? <Badge tone="green">مستند إلى الملزمة</Badge> : <Badge tone="amber">غير متوفر في الملزمة</Badge>}
            </div>
            <p className="whitespace-pre-line text-sm leading-8 text-slate-800">{result.answer}</p>
          </div>
        )}
      </Card>

      <Card title="المصادر">
        {!result ? (
          <Empty>ستظهر مقاطع الملزمة التي اعتمد عليها المساعد.</Empty>
        ) : result.sources.length === 0 ? (
          <Empty>لا توجد مصادر لهذه الإجابة.</Empty>
        ) : (
          <ul className="space-y-3 text-sm">
            {result.sources.map((s) => (
              <li key={s.chunk_id} className="rounded-lg bg-slate-50 p-3">
                <div className="mb-1 text-xs font-medium text-brand-700">
                  {s.material_title}
                  {s.page_number ? ` · صفحة ${s.page_number}` : ""}
                </div>
                <p className="text-xs leading-6 text-slate-600">{s.excerpt}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}