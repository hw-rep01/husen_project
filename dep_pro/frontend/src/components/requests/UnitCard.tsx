"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Empty, ErrorText, Input, Select, Spinner } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { ACTION_LABELS, CATEGORY_LABELS, STATUS_LABELS, STATUS_TONE, formatDateTime } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/roles";
import type { Course, EventItem, Role, UnitView } from "@/lib/types";

const TERMINAL = new Set(["approved", "rejected", "resolved", "closed"]);

/** مرآة للقواعد على الواجهة لإظهار الأزرار المناسبة فقط. الخادم هو المرجع الفعلي. */
export function availableActions(unit: UnitView, role: Role) {
  const result = { classify: false, forward: false, decide: false, refresh: false };
  if (TERMINAL.has(unit.status)) return result;

  const atMyStage = unit.current_stage === role;

  if (role === "class_representative" && atMyStage) {
    result.classify = unit.kind === "request" && unit.category === null;
    result.refresh = unit.kind === "batch";
    result.forward = unit.category !== null;
    return result;
  }

  if (!atMyStage || unit.category === null) return result;

  if (role === "instructor") {
    result.decide = unit.category === "academic";
  } else if (role === "department_coordinator") {
    result.forward = unit.category === "administrative";
    result.decide = unit.category === "administrative";
  } else if (role === "department_head") {
    result.decide = true;
  }
  return result;
}

export function UnitCard({
  unit,
  role,
  courses,
  onChanged,
}: {
  unit: UnitView;
  role: Role;
  courses: Course[];
  onChanged: () => void;
}) {
  const actions = availableActions(unit, role);
  const [note, setNote] = useState("");
  const [courseId, setCourseId] = useState<string>(unit.course_id ? String(unit.course_id) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTimeline, setShowTimeline] = useState(false);

  const basePath = unit.kind === "batch" ? `/api/batches/${unit.id}` : `/api/requests/${unit.id}`;
  const needsCourse = role === "class_representative" && unit.category === "academic" && actions.forward;

  async function call(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(path, { method: "POST", json: body });
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function decide(action: "approve" | "reject" | "resolve") {
    void call(`${basePath}/actions`, { action, note: note.trim() || null });
  }

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <h3 className="font-semibold">{unit.title}</h3>
          <p className="text-xs text-slate-500">
            {formatDateTime(unit.created_at)}
            {unit.kind === "batch" ? ` · بطاقة موحدة لـ ${unit.request_count} طلباً متشابهاً` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {unit.category && <Badge tone="blue">{CATEGORY_LABELS[unit.category]}</Badge>}
          <Badge tone={STATUS_TONE[unit.status] ?? "slate"}>{STATUS_LABELS[unit.status] ?? unit.status}</Badge>
          <Badge>{ROLE_LABELS[unit.current_stage]}</Badge>
        </div>
      </header>

      <p className="mt-3 whitespace-pre-line text-sm leading-7 text-slate-700">{unit.summary}</p>

      {actions.classify && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-600">صنّف الطلب:</span>
          <Button variant="secondary" disabled={busy} onClick={() => void call(`/api/requests/${unit.id}/classify`, { category: "academic" })}>
            أكاديمي
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => void call(`/api/requests/${unit.id}/classify`, { category: "administrative" })}>
            إداري
          </Button>
        </div>
      )}

      {(actions.forward || actions.decide) && (
        <div className="mt-4 space-y-3">
          {needsCourse && (
            <Select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              <option value="">اختر المادة قبل الإحالة</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name_ar}
                </option>
              ))}
            </Select>
          )}
          <Input
            placeholder="ملاحظة (اختيارية)"
            maxLength={1000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            {actions.forward && (
              <Button
                disabled={busy || (needsCourse && !courseId)}
                onClick={() =>
                  void call(`${basePath}/actions`, {
                    action: "forward",
                    course_id: courseId ? Number(courseId) : null,
                    note: note.trim() || null,
                  })
                }
              >
                إحالة للجهة التالية
              </Button>
            )}
            {actions.decide && (
              <>
                <Button variant="secondary" disabled={busy} onClick={() => decide("approve")}>
                  موافقة
                </Button>
                <Button variant="danger" disabled={busy} onClick={() => decide("reject")}>
                  رفض
                </Button>
                <Button variant="secondary" disabled={busy} onClick={() => decide("resolve")}>
                  تمت المعالجة
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        {actions.refresh && (
          <button
            className="text-brand-600 hover:underline disabled:opacity-50"
            disabled={busy}
            onClick={() => void call(`/api/batches/${unit.id}/refresh-summary`)}
          >
            إعادة تلخيص البطاقة
          </button>
        )}
        {unit.kind === "request" && (
          <button className="text-brand-600 hover:underline" onClick={() => setShowTimeline((s) => !s)}>
            {showTimeline ? "إخفاء السجل" : "السجل الزمني"}
          </button>
        )}
      </div>

      {showTimeline && unit.kind === "request" && <Timeline requestId={unit.id} />}
      {error && <div className="mt-3"><ErrorText>{error}</ErrorText></div>}
    </article>
  );
}

export function Timeline({ requestId }: { requestId: number }) {
  const [events, setEvents] = useState<EventItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<EventItem[]>(`/api/requests/${requestId}/timeline`)
      .then(setEvents)
      .catch((e) => setError(errorMessage(e)));
  }, [requestId]);

  if (error) return <ErrorText>{error}</ErrorText>;
  if (!events) return <Spinner />;
  if (events.length === 0) return <Empty>لا توجد حركات بعد.</Empty>;

  return (
    <ol className="mt-3 space-y-3 border-s-2 border-brand-100 ps-4 text-sm">
      {events.map((e, i) => (
        <li key={i}>
          <div className="font-medium">
            {ACTION_LABELS[e.action] ?? e.action}
            {e.to_stage ? ` ← ${ROLE_LABELS[e.to_stage]}` : ""}
          </div>
          {e.note && <div className="text-slate-600">{e.note}</div>}
          <div className="text-xs text-slate-400">{formatDateTime(e.created_at)}</div>
        </li>
      ))}
    </ol>
  );
}