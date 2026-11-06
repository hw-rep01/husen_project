"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Notice, Select, Spinner, Textarea } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import type { Broadcast, Course, Reader } from "@/lib/types";

const POSTERS = new Set(["instructor", "department_coordinator", "department_head"]);

export default function BroadcastsPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<Broadcast[] | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [readers, setReaders] = useState<{ broadcastId: number; list: Reader[] } | null>(null);
  const [acknowledged, setAcknowledged] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [pinned, setPinned] = useState(false);
  const [courseId, setCourseId] = useState("");

  const canPost = !!user && POSTERS.has(user.role);
  const isStudent = !!user && !canPost;
  const scope = user?.role === "instructor" ? "course" : "department";

  const load = useCallback(async () => {
    try {
      setItems(await apiFetch<Broadcast[]>("/api/broadcasts"));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
    if (user?.role === "instructor") {
      apiFetch<Course[]>("/api/courses")
        .then(setCourses)
        .catch(() => setCourses([]));
    }
  }, [load, user]);

  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch("/api/broadcasts", {
        method: "POST",
        json: {
          scope,
          course_id: scope === "course" ? Number(courseId) : null,
          title,
          body,
          is_pinned: pinned,
        },
      });
      setTitle("");
      setBody("");
      setPinned(false);
      setNotice("تم نشر التبليغ وإشعار المستهدفين.");
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function markRead(id: number) {
    try {
      await apiFetch(`/api/broadcasts/${id}/read`, { method: "POST" });
      setAcknowledged((prev) => new Set(prev).add(id));
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function showReaders(id: number) {
    try {
      const list = await apiFetch<Reader[]>(`/api/broadcasts/${id}/readers`);
      setReaders({ broadcastId: id, list });
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  if (!user) return null;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {canPost && (
        <Card title="نشر تبليغ">
          <form onSubmit={publish} className="space-y-4">
            <Field label="النطاق">
              <Input readOnly value={scope === "course" ? "تبليغ للمادة" : "تبليغ للقسم كاملاً"} />
            </Field>
            {scope === "course" && (
              <Field label="المادة">
                <Select required value={courseId} onChange={(e) => setCourseId(e.target.value)}>
                  <option value="">اختر المادة</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name_ar}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field label="العنوان">
              <Input required minLength={3} maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Field label="نص التبليغ">
              <Textarea
                required
                minLength={5}
                maxLength={5000}
                rows={5}
                value={body}
                onChange={(e) => setBody(e.target.value)}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />
              تثبيت التبليغ في أعلى القائمة
            </label>
            {error && <ErrorText>{error}</ErrorText>}
            {notice && <Notice>{notice}</Notice>}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "جارٍ النشر..." : "نشر"}
            </Button>
          </form>
        </Card>
      )}

      <Card title="التبليغات" className={canPost ? "lg:col-span-2" : "lg:col-span-3"}>
        {!canPost && error && <div className="mb-4"><ErrorText>{error}</ErrorText></div>}
        {!items ? (
          <Spinner />
        ) : items.length === 0 ? (
          <Empty>لا توجد تبليغات.</Empty>
        ) : (
          <ul className="space-y-4">
            {items.map((b) => (
              <li key={b.id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {b.is_pinned && <Badge tone="amber">مثبّت</Badge>}
                    <h3 className="font-semibold">{b.title}</h3>
                  </div>
                  <span className="text-xs text-slate-500">{formatDateTime(b.created_at)}</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">{b.channel_name}</p>
                <p className="mt-3 whitespace-pre-line text-sm leading-7 text-slate-700">{b.body}</p>

                <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
                  <span className="text-slate-500">
                    قرأه {b.seen_count} من {b.audience_count}
                  </span>
                  {isStudent &&
                    (acknowledged.has(b.id) ? (
                      <Badge tone="green">تم الاطلاع</Badge>
                    ) : (
                      <Button variant="secondary" onClick={() => void markRead(b.id)}>
                        تم الاطلاع
                      </Button>
                    ))}
                  {canPost && (
                    <Button variant="ghost" onClick={() => void showReaders(b.id)}>
                      من قرأ؟
                    </Button>
                  )}
                </div>

                {readers?.broadcastId === b.id && (
                  <div className="mt-4 rounded-lg bg-slate-50 p-3">
                    {readers.list.length === 0 ? (
                      <p className="text-sm text-slate-500">لم يقرأ أحد التبليغ بعد.</p>
                    ) : (
                      <ul className="grid gap-1 text-sm sm:grid-cols-2">
                        {readers.list.map((r, i) => (
                          <li key={i} className="flex justify-between gap-2">
                            <span>{r.full_name}</span>
                            <span className="text-xs text-slate-400">{formatDateTime(r.read_at)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}