"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { UnitCard, Timeline } from "@/components/requests/UnitCard";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Notice,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CATEGORY_LABELS, STATUS_LABELS, STATUS_TONE, formatDateTime } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/roles";
import type { Course, Role, RequestItem, UnitView } from "@/lib/types";

export default function RequestsPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "student") return <StudentRequests />;
  if (user.role === "class_representative") return <RepresentativeInbox />;
  return <StaffInbox role={user.role} />;
}

function StudentRequests() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [items, setItems] = useState<RequestItem[] | null>(null);
  const [courseId, setCourseId] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [openTimeline, setOpenTimeline] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await apiFetch<RequestItem[]>("/api/requests/mine"));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
    apiFetch<Course[]>("/api/courses")
      .then(setCourses)
      .catch(() => setCourses([]));
  }, [load]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch("/api/requests", {
        method: "POST",
        json: { course_id: courseId ? Number(courseId) : null, subject, body },
      });
      setSubject("");
      setBody("");
      setCourseId("");
      setNotice("تم إرسال طلبك إلى ممثل شعبتك.");
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="طلب جديد">
        <form onSubmit={submit} className="space-y-4">
          <Field label="المادة (اتركها فارغة للطلبات الإدارية)">
            <Select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              <option value="">طلب إداري عام</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name_ar}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="عنوان الطلب">
            <Input
              required
              minLength={3}
              maxLength={255}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </Field>
          <Field label="التفاصيل">
            <Textarea
              required
              minLength={10}
              maxLength={5000}
              rows={5}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </Field>
          {error && <ErrorText>{error}</ErrorText>}
          {notice && <Notice>{notice}</Notice>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "جارٍ الإرسال..." : "إرسال"}
          </Button>
        </form>
      </Card>

      <Card title="طلباتي" className="lg:col-span-2">
        {!items ? (
          <Spinner />
        ) : items.length === 0 ? (
          <Empty>لم تقدّم أي طلب بعد.</Empty>
        ) : (
          <ul className="space-y-3">
            {items.map((r) => (
              <li key={r.id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold">{r.subject}</div>
                    <div className="text-xs text-slate-500">{formatDateTime(r.created_at)}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {r.category && <Badge tone="blue">{CATEGORY_LABELS[r.category]}</Badge>}
                    <Badge tone={STATUS_TONE[r.status] ?? "slate"}>
                      {STATUS_LABELS[r.status] ?? r.status}
                    </Badge>
                  </div>
                </div>
                <p className="mt-2 text-xs text-slate-600">
                  المرحلة الحالية: {ROLE_LABELS[r.current_stage]}
                </p>
                <button
                  className="mt-2 text-xs text-brand-600 hover:underline"
                  onClick={() => setOpenTimeline(openTimeline === r.id ? null : r.id)}
                >
                  {openTimeline === r.id ? "إخفاء السجل" : "عرض السجل الزمني"}
                </button>
                {openTimeline === r.id && <Timeline requestId={r.id} />}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function RepresentativeInbox() {
  const [units, setUnits] = useState<UnitView[] | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setUnits(await apiFetch<UnitView[]>("/api/requests/section"));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
    apiFetch<Course[]>("/api/courses")
      .then(setCourses)
      .catch(() => setCourses([]));
  }, [load]);

  async function consolidate() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await apiFetch<{ batches_created: number }>("/api/sections/consolidate", { method: "POST" });
      setNotice(`تم إنشاء ${res.batches_created} بطاقة موحدة جديدة.`);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="طلبات الشعبة"
      actions={
        <Button variant="secondary" disabled={busy} onClick={() => void consolidate()}>
          دمج شامل للشعبة
        </Button>
      }
    >
      {error && <div className="mb-4"><ErrorText>{error}</ErrorText></div>}
      {notice && <div className="mb-4"><Notice>{notice}</Notice></div>}
      {!units ? (
        <Spinner />
      ) : units.length === 0 ? (
        <Empty>لا توجد طلبات في الشعبة.</Empty>
      ) : (
        <ul className="space-y-4">
          {units.map((u) => (
            <li key={`${u.kind}-${u.id}`}>
              <UnitCard
                unit={u}
                role="class_representative"
                courses={courses}
                onChanged={() => void load()}
              />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function StaffInbox({ role }: { role: Role }) {
  const [units, setUnits] = useState<UnitView[] | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setUnits(await apiFetch<UnitView[]>("/api/requests/inbox"));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
    apiFetch<Course[]>("/api/courses")
      .then(setCourses)
      .catch(() => setCourses([]));
  }, [load]);

  return (
    <Card title="الوارد">
      {error && <div className="mb-4"><ErrorText>{error}</ErrorText></div>}
      {!units ? (
        <Spinner />
      ) : units.length === 0 ? (
        <Empty>لا توجد طلبات بانتظار {ROLE_LABELS[role]}.</Empty>
      ) : (
        <ul className="space-y-4">
          {units.map((u) => (
            <li key={`${u.kind}-${u.id}`}>
              <UnitCard unit={u} role={role} courses={courses} onChanged={() => void load()} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}