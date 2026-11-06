"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Notice, Spinner } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Quiz, QuizListItem } from "@/lib/types";

const QUIZ_TONE = { draft: "amber", published: "green", closed: "slate" } as const;
const QUIZ_LABEL = { draft: "مسودة", published: "منشور", closed: "مغلق" } as const;

export function QuizzesPanel({ courseId, canManage }: { courseId: number; canManage: boolean }) {
  const [quizzes, setQuizzes] = useState<QuizListItem[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [count, setCount] = useState(5);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setQuizzes(await apiFetch<QuizListItem[]>(`/api/courses/${courseId}/quizzes`));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [courseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const quiz = await apiFetch<Quiz>(`/api/courses/${courseId}/quizzes`, {
        method: "POST",
        json: { title, question_count: count },
      });
      setTitle("");
      setSelected(quiz.id);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="الكويزات" className="lg:col-span-1">
        {error && <div className="mb-4"><ErrorText>{error}</ErrorText></div>}

        {canManage && (
          <form onSubmit={generate} className="mb-5 space-y-3 border-b border-slate-100 pb-5">
            <Field label="عنوان الكويز">
              <Input required minLength={3} maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Field label="عدد الأسئلة (1 إلى 20)">
              <Input
                type="number"
                min={1}
                max={20}
                required
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </Field>
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "جارٍ توليد الأسئلة من الملزمة..." : "توليد كويز"}
            </Button>
          </form>
        )}

        {!quizzes ? (
          <Spinner />
        ) : quizzes.length === 0 ? (
          <Empty>لا توجد كويزات بعد.</Empty>
        ) : (
          <ul className="space-y-2">
            {quizzes.map((q) => (
              <li key={q.id}>
                <button
                  onClick={() => setSelected(q.id)}
                  className={`w-full rounded-lg border p-3 text-start ${
                    selected === q.id ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{q.title}</span>
                    <Badge tone={QUIZ_TONE[q.status as keyof typeof QUIZ_TONE] ?? "slate"}>
                      {QUIZ_LABEL[q.status as keyof typeof QUIZ_LABEL] ?? q.status}
                    </Badge>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {q.question_count} سؤالاً
                    {q.closes_at ? ` · يغلق ${formatDateTime(q.closes_at)}` : ""}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="lg:col-span-2">
        {selected === null ? (
          <Card>
            <Empty>اختر كويزاً لعرضه.</Empty>
          </Card>
        ) : (
          <QuizDetail
            key={selected}
            quizId={selected}
            canManage={canManage}
            onChanged={() => void load()}
          />
        )}
      </div>
    </div>
  );
}

function QuizDetail({
  quizId,
  canManage,
  onChanged,
}: {
  quizId: number;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [result, setResult] = useState<{ score: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [opensAt, setOpensAt] = useState("");
  const [closesAt, setClosesAt] = useState("");

  const load = useCallback(async () => {
    try {
      setQuiz(await apiFetch<Quiz>(`/api/quizzes/${quizId}`));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [quizId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      const toIso = (value: string) => (value ? new Date(value).toISOString() : null);
      const updated = await apiFetch<Quiz>(`/api/quizzes/${quizId}/publish`, {
        method: "POST",
        json: { opens_at: toIso(opensAt), closes_at: toIso(closesAt) },
      });
      setQuiz(updated);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function submitAnswers() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch<{ attempt_id: number; score: number }>(
        `/api/quizzes/${quizId}/attempts`,
        { method: "POST", json: { answers } },
      );
      setResult(response);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (error && !quiz) return <Card><ErrorText>{error}</ErrorText></Card>;
  if (!quiz) return <Card><Spinner /></Card>;

  const allAnswered = quiz.questions.every((q) => answers[q.id] !== undefined);
  const canAnswer = !canManage && quiz.status === "published" && !result;

  return (
    <Card
      title={quiz.title}
      actions={
        <Badge tone={QUIZ_TONE[quiz.status as keyof typeof QUIZ_TONE] ?? "slate"}>
          {QUIZ_LABEL[quiz.status as keyof typeof QUIZ_LABEL] ?? quiz.status}
        </Badge>
      }
    >
      {error && <div className="mb-4"><ErrorText>{error}</ErrorText></div>}

      {canManage && quiz.status === "draft" && (
        <div className="mb-5 grid gap-3 rounded-lg bg-amber-50 p-4 sm:grid-cols-3">
          <Field label="يفتح في (اختياري)">
            <Input type="datetime-local" value={opensAt} onChange={(e) => setOpensAt(e.target.value)} />
          </Field>
          <Field label="يغلق في (اختياري)">
            <Input type="datetime-local" value={closesAt} onChange={(e) => setClosesAt(e.target.value)} />
          </Field>
          <div className="flex items-end">
            <Button disabled={busy || quiz.questions.length === 0} onClick={() => void publish()} className="w-full">
              نشر الكويز
            </Button>
          </div>
        </div>
      )}

      {result && <div className="mb-5"><Notice>تم تسجيل إجابتك. درجتك: {result.score}%</Notice></div>}

      <ol className="space-y-6">
        {quiz.questions.map((q, i) => (
          <li key={q.id} className="space-y-2">
            <p className="font-medium">
              {i + 1}. {q.question_text}
            </p>
            <div className="space-y-1.5">
              {q.options.map((option, idx) => {
                const isCorrect = canManage && q.correct_option_index === idx;
                return (
                  <label
                    key={idx}
                    className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-sm ${
                      isCorrect ? "border-emerald-400 bg-emerald-50" : "border-slate-200"
                    }`}
                  >
                    {canManage ? (
                      <span className="w-4 text-center text-emerald-600">{isCorrect ? "✓" : ""}</span>
                    ) : (
                      <input
                        type="radio"
                        name={`q-${q.id}`}
                        disabled={!canAnswer}
                        checked={answers[q.id] === idx}
                        onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: idx }))}
                      />
                    )}
                    <span>{option}</span>
                  </label>
                );
              })}
            </div>
            {canManage && q.explanation && (
              <p className="whitespace-pre-line text-xs leading-6 text-slate-500">{q.explanation}</p>
            )}
          </li>
        ))}
      </ol>

      {canAnswer && (
        <Button className="mt-6 w-full" disabled={!allAnswered || busy} onClick={() => void submitAnswers()}>
          إرسال الإجابات
        </Button>
      )}
    </Card>
  );
}