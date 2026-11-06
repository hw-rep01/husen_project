"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { apiFetch, errorMessage } from "@/lib/api";
import { subscribeSchedule, type StreamStatus } from "@/lib/stream";
import { CHANGE_LABELS, SLOT_LABELS, formatDateTime, formatDayIso, formatTime, todayIsoDay } from "@/lib/format";
import type { MakeupSuggestion, Occurrence, Room, ScheduleChange } from "@/lib/types";
import { Badge, Button, Card, Empty, ErrorText, Input, Notice, Select, Spinner } from "@/components/ui";

const EDIT_ROLES = new Set(["instructor", "department_coordinator", "department_head"]);

export default function SchedulePage() {
  const { user } = useAuth();
  const [day, setDay] = useState(todayIsoDay());
  const [rows, setRows] = useState<Occurrence[] | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [feed, setFeed] = useState<ScheduleChange[]>([]);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // نحتفظ بمرجع لآخر دالة تحميل كي لا نعيد الاشتراك في البث عند تغيير اليوم
  const loadRef = useRef<() => Promise<void>>(async () => {});
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await apiFetch<Occurrence[]>(`/api/schedule/week?day=${day}`));
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [day]);

  loadRef.current = load;

  useEffect(() => {
    void load();
  }, [load]);

  const canEdit = !!user && EDIT_ROLES.has(user.role);

  useEffect(() => {
    if (!canEdit) return;
    apiFetch<Room[]>("/api/rooms")
      .then(setRooms)
      .catch(() => setRooms([]));
  }, [canEdit]);

  useEffect(() => {
    if (!user) return;
    const stop = subscribeSchedule((change) => {
      setFeed((prev) => [change, ...prev].slice(0, 30));
      if (debounce.current) clearTimeout(debounce.current);
      debounce.current = setTimeout(() => void loadRef.current(), 400);
    }, setStatus);
    return () => {
      stop();
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [user]);

  if (!user) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">الجدول الأسبوعي</h1>
        <div className="flex items-center gap-4">
          <StatusDot status={status} />
          <Input type="date" className="w-auto" value={day} onChange={(e) => setDay(e.target.value)} />
        </div>
      </div>

      {error && <ErrorText>{error}</ErrorText>}
      {notice && <Notice>{notice}</Notice>}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="المحاضرات" className="lg:col-span-2">
          {!rows ? (
            <Spinner />
          ) : rows.length === 0 ? (
            <Empty>لا توجد محاضرات في هذا الأسبوع.</Empty>
          ) : (
            <div className="space-y-6">
              {groupByDay(rows).map(([d, items]) => (
                <div key={d}>
                  <h3 className="mb-2 text-sm font-semibold text-brand-700">{formatDayIso(d)}</h3>
                  <ul className="space-y-3">
                    {items.map((row) => (
                      <OccurrenceRow
                        key={row.id}
                        row={row}
                        canEdit={canEdit}
                        rooms={rooms}
                        onDone={(message) => {
                          setNotice(message);
                          void load();
                        }}
                        onError={setError}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="تحديثات مباشرة">
          {feed.length === 0 ? (
            <Empty>ستظهر هنا التغييرات فور حدوثها.</Empty>
          ) : (
            <ul className="space-y-2 text-sm">
              {feed.map((c) => (
                <li key={c.id} className="rounded-lg bg-slate-50 p-3">
                  <div className="font-medium">{CHANGE_LABELS[c.change_type]}</div>
                  <div className="text-xs text-slate-500">
                    محاضرة #{c.occurrence_id} · {formatDateTime(c.created_at)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: StreamStatus }) {
  const map = {
    live: ["bg-emerald-500", "مباشر"],
    connecting: ["bg-amber-400", "جارٍ الاتصال"],
    offline: ["bg-red-500", "غير متصل"],
  } as const;
  const [color, label] = map[status];
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-600">
      <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}

function groupByDay(rows: Occurrence[]): [string, Occurrence[]][] {
  const map = new Map<string, Occurrence[]>();
  for (const row of rows) {
    const list = map.get(row.occurrence_date) ?? [];
    list.push(row);
    map.set(row.occurrence_date, list);
  }
  return [...map.entries()];
}

function OccurrenceRow({
  row,
  canEdit,
  rooms,
  onDone,
  onError,
}: {
  row: Occurrence;
  canEdit: boolean;
  rooms: Room[];
  onDone: (message: string) => void;
  onError: (message: string) => void;
}) {
  const [roomId, setRoomId] = useState(row.room_id ? String(row.room_id) : "");
  const [suggestions, setSuggestions] = useState<MakeupSuggestion[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    try {
      await action();
      onDone(message);
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const editable = canEdit && !row.is_cancelled;
  const cancelled = row.is_cancelled;

  return (
    <li className={`rounded-lg border p-4 ${cancelled ? "border-amber-200 bg-amber-50/60" : "border-slate-200 bg-white"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-semibold">{row.course_name}</div>
          <div className="text-sm text-slate-500">
            {formatTime(row.starts_at)} – {formatTime(row.ends_at)} · القاعة {row.room_code ?? "غير محددة"}
          </div>
        </div>
        <Badge tone={cancelled ? "amber" : row.slot_type === "makeup" ? "green" : "slate"}>
          {SLOT_LABELS[row.slot_type]}
        </Badge>
      </div>

      {editable && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Select className="w-auto" value={roomId} onChange={(e) => setRoomId(e.target.value)}>
            <option value="">اختر القاعة</option>
            {rooms.map((r) => (
              <option key={r.id} value={r.id}>
                {r.code}
              </option>
            ))}
          </Select>
          <Button
            variant="secondary"
            disabled={busy || !roomId}
            onClick={() =>
              run(
                () =>
                  apiFetch(`/api/schedule/occurrences/${row.id}/room`, {
                    method: "POST",
                    json: { room_id: Number(roomId) },
                  }),
                "تم تغيير القاعة",
              )
            }
          >
            تغيير القاعة
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => {
              if (confirm("تأجيل هذه المحاضرة؟")) {
                void run(
                  () =>
                    apiFetch(`/api/schedule/occurrences/${row.id}/cancel`, {
                      method: "POST",
                      json: { as_postponement: true },
                    }),
                  "تم تأجيل المحاضرة",
                );
              }
            }}
          >
            تأجيل
          </Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => {
              if (confirm("إلغاء هذه المحاضرة نهائياً؟")) {
                void run(
                  () =>
                    apiFetch(`/api/schedule/occurrences/${row.id}/cancel`, {
                      method: "POST",
                      json: { as_postponement: false },
                    }),
                  "تم إلغاء المحاضرة",
                );
              }
            }}
          >
            إلغاء
          </Button>
        </div>
      )}

      {cancelled && canEdit && (
        <div className="mt-3 space-y-3">
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const list = await apiFetch<MakeupSuggestion[]>("/api/schedule/makeup/suggest", {
                  method: "POST",
                  json: {
                    enrollment_id: row.enrollment_id,
                    from_date: row.occurrence_date,
                    days_ahead: 14,
                    limit: 5,
                  },
                });
                setSuggestions(list);
              }, "تم توليد الاقتراحات")
            }
          >
            اقترح موعداً تعويضياً
          </Button>

          {suggestions &&
            (suggestions.length === 0 ? (
              <p className="text-sm text-slate-500">لا توجد أوقات فارغة بلا تعارض خلال 14 يوماً.</p>
            ) : (
              <ul className="space-y-2">
                {suggestions.map((s) => (
                  <li
                    key={s.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white p-3 text-sm ring-1 ring-slate-200"
                  >
                    <span>
                      {formatDayIso(s.suggested_date)} · {formatTime(s.starts_at)} – {formatTime(s.ends_at)} · {s.room_code}
                    </span>
                    <Button
                      disabled={busy || s.is_accepted}
                      onClick={() =>
                        run(async () => {
                          await apiFetch(`/api/schedule/makeup/suggestions/${s.id}/accept`, { method: "POST" });
                          setSuggestions(null);
                        }, "تم اعتماد المحاضرة التعويضية")
                      }
                    >
                      {s.is_accepted ? "معتمد" : "اعتماد"}
                    </Button>
                  </li>
                ))}
              </ul>
            ))}
        </div>
      )}
    </li>
  );
}