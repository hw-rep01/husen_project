"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Notice, Spinner } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { GAP_LABELS, MATERIAL_LABELS, formatDateTime } from "@/lib/format";
import type { GapAlert, Material } from "@/lib/types";

export function StaffPanel({ courseId }: { courseId: number }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <MaterialsCard courseId={courseId} />
      <GapsCard courseId={courseId} />
    </div>
  );
}

const MATERIAL_TONE = { pending: "amber", processing: "blue", ready: "green", failed: "red" } as const;

function MaterialsCard({ courseId }: { courseId: number }) {
  const [items, setItems] = useState<Material[] | null>(null);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await apiFetch<Material[]>(`/api/courses/${courseId}/materials`));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [courseId]);

  useEffect(() => {
    void load();
  }, [load]);

  // تحديث دوري طالما هناك ملزمة قيد المعالجة
  const hasPending = items?.some((m) => m.status === "pending" || m.status === "processing") ?? false;
  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [hasPending, load]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const form = new FormData();
    form.append("title", title);
    form.append("file", file);
    try {
      const res = await apiFetch<{ duplicate: boolean }>(`/api/courses/${courseId}/materials`, {
        method: "POST",
        form,
      });
      setNotice(res.duplicate ? "هذه النسخة مرفوعة مسبقاً وجاهزة." : "تم رفع الملزمة وجارٍ معالجتها.");
      setTitle("");
      setFile(null);
      event.currentTarget.reset();
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="ملازم المادة">
      <form onSubmit={upload} className="mb-5 space-y-3 border-b border-slate-100 pb-5">
        <Field label="عنوان الملزمة">
          <Input required minLength={3} maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="ملف PDF">
          <Input
            type="file"
            accept="application/pdf"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Field>
        {error && <ErrorText>{error}</ErrorText>}
        {notice && <Notice>{notice}</Notice>}
        <Button type="submit" disabled={busy || !file} className="w-full">
          {busy ? "جارٍ الرفع..." : "رفع الملزمة"}
        </Button>
      </form>

      {!items ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Empty>لم تُرفع أي ملزمة لهذه المادة.</Empty>
      ) : (
        <ul className="space-y-3">
          {items.map((m) => (
            <li key={m.id} className="rounded-lg border border-slate-200 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{m.title}</span>
                <Badge tone={MATERIAL_TONE[m.status]}>{MATERIAL_LABELS[m.status]}</Badge>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {m.page_count ? `${m.page_count} صفحة · ` : ""}
                {formatDateTime(m.created_at)}
              </div>
              {m.error_message && <p className="mt-2 text-xs text-red-600">{m.error_message}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function GapsCard({ courseId }: { courseId: number }) {
  const [alerts, setAlerts] = useState<GapAlert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setAlerts(await apiFetch<GapAlert[]>(`/api/courses/${courseId}/gaps`));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [courseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runRadar() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await apiFetch<{ scopes_processed: number; alerts_created: number; alerts_updated: number }>(
        `/api/courses/${courseId}/gaps/run`,
        { method: "POST" },
      );
      setNotice(`تم فحص ${res.scopes_processed} نطاقاً، وتنبيهات جديدة: ${res.alerts_created}.`);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function acknowledge(id: number) {
    try {
      await apiFetch(`/api/gaps/${id}/acknowledge`, { method: "POST" });
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <Card
      title="رادار الفجوات"
      actions={
        <Button variant="secondary" disabled={busy} onClick={() => void runRadar()}>
          {busy ? "جارٍ الفحص..." : "تشغيل الرادار الآن"}
        </Button>
      }
    >
      {error && <div className="mb-4"><ErrorText>{error}</ErrorText></div>}
      {notice && <div className="mb-4"><Notice>{notice}</Notice></div>}

      {!alerts ? (
        <Spinner />
      ) : alerts.length === 0 ? (
        <Empty>لا توجد موضوعات تتجاوز حد التنبيه حالياً.</Empty>
      ) : (
        <ul className="space-y-3">
          {alerts.map((a) => (
            <li key={a.id} className="rounded-lg border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">{a.topic_label}</span>
                <Badge tone={a.status === "open" ? "red" : a.status === "resolved" ? "green" : "slate"}>
                  {GAP_LABELS[a.status] ?? a.status}
                </Badge>
              </div>
              <p className="mt-2 text-sm leading-7 text-slate-700">{a.summary}</p>
              <div className="mt-2 text-xs text-slate-500">
                {Math.round(a.affected_ratio * 100)}% من طلاب الشعبة · {formatDateTime(a.created_at)}
              </div>
              {a.status === "open" && (
                <div className="mt-3">
                  <Button variant="secondary" onClick={() => void acknowledge(a.id)}>
                    تمت المراجعة
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}