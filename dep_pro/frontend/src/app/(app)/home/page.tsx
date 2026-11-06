"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/roles";
import type { Course, NotificationItem } from "@/lib/types";
import { Card, Empty, ErrorText, Spinner } from "@/components/ui";

export default function HomePage() {
  const { user } = useAuth();
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [notes, setNotes] = useState<NotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<Course[]>("/api/courses"),
      apiFetch<NotificationItem[]>("/api/notifications/mine"),
    ])
      .then(([c, n]) => {
        setCourses(c);
        setNotes(n);
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  if (!user) return null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">مرحباً، {user.full_name}</h1>
        <p className="text-slate-500">{ROLE_LABELS[user.role]}</p>
      </header>

      {error && <ErrorText>{error}</ErrorText>}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="موادي">
          {!courses ? (
            <Spinner />
          ) : courses.length === 0 ? (
            <Empty>لا توجد مواد مرتبطة بحسابك في الفصل الحالي.</Empty>
          ) : (
            <ul className="divide-y divide-slate-100">
              {courses.map((course) => (
                <li key={course.id}>
                  <Link
                    href={`/courses/${course.id}`}
                    className="flex items-center justify-between py-3 hover:text-brand-600"
                  >
                    <span className="font-medium">{course.name_ar}</span>
                    <span className="text-sm text-slate-400">{course.code}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="الإشعارات">
          {!notes ? (
            <Spinner />
          ) : notes.length === 0 ? (
            <Empty>لا توجد إشعارات حتى الآن.</Empty>
          ) : (
            <ul className="space-y-3">
              {notes.slice(0, 20).map((n) => (
                <li key={n.id} className="rounded-lg bg-slate-50 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-medium">{n.title}</span>
                    {n.sent_at && (
                      <span className="shrink-0 text-xs text-slate-400">{formatDateTime(n.sent_at)}</span>
                    )}
                  </div>
                  <p className="mt-1 whitespace-pre-line text-sm text-slate-600">{n.body}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}