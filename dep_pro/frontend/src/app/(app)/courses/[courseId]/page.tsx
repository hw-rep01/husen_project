"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AssistantPanel } from "@/components/course/AssistantPanel";
import { QuizzesPanel } from "@/components/course/QuizzesPanel";
import { StaffPanel } from "@/components/course/StaffPanel";
import { Card, Empty, ErrorText, Spinner } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Course } from "@/lib/types";

type Tab = "assistant" | "quizzes" | "staff";

export default function CoursePage() {
  const params = useParams<{ courseId: string }>();
  const courseId = Number(params.courseId);
  const { user } = useAuth();
  const [course, setCourse] = useState<Course | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("assistant");

  useEffect(() => {
    apiFetch<Course[]>("/api/courses")
      .then((list) => setCourse(list.find((c) => c.id === courseId) ?? null))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoaded(true));
  }, [courseId]);

  if (!user) return null;
  if (!loaded) return <Spinner />;
  if (!course) {
    return <Empty>المادة غير موجودة أو لا تملك صلاحية الوصول إليها.</Empty>;
  }

  const isInstructor = user.role === "instructor";
  const tabs: { key: Tab; label: string; show: boolean }[] = [
    { key: "assistant", label: "المساعد الذكي", show: true },
    { key: "quizzes", label: "الكويزات", show: true },
    { key: "staff", label: "إدارة المادة", show: isInstructor },
  ];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">{course.name_ar}</h1>
        <p className="text-sm text-slate-500">{course.code}</p>
      </header>

      {error && <ErrorText>{error}</ErrorText>}

      <nav className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        {tabs
          .filter((t) => t.show)
          .map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${
                tab === t.key ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {t.label}
            </button>
          ))}
      </nav>

      {tab === "assistant" && <AssistantPanel courseId={courseId} />}
      {tab === "quizzes" && <QuizzesPanel courseId={courseId} canManage={isInstructor} />}
      {tab === "staff" && isInstructor && <StaffPanel courseId={courseId} />}

      {!isInstructor && tab === "quizzes" && (
        <Card>
          <p className="text-sm text-slate-500">
            يظهر لك الكويز بعد نشره من أستاذ المادة، ويمكنك أداؤه مرة واحدة.
          </p>
        </Card>
      )}
    </div>
  );
}