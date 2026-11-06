import type { Role } from "./types";

export const ROLE_LABELS: Record<Role, string> = {
  student: "طالب",
  class_representative: "ممثل الشعبة",
  instructor: "أستاذ المادة",
  department_coordinator: "مقرر القسم",
  department_head: "رئيس القسم",
};

export interface NavItem {
  href: string;
  label: string;
}

export const NAV: Record<Role, NavItem[]> = {
  student: [
    { href: "/home", label: "الرئيسية" },
    { href: "/requests", label: "طلباتي" },
    { href: "/schedule", label: "الجدول" },
    { href: "/broadcasts", label: "التبليغات" },
  ],
  class_representative: [
    { href: "/home", label: "الرئيسية" },
    { href: "/requests", label: "طلبات الشعبة" },
    { href: "/schedule", label: "الجدول" },
    { href: "/broadcasts", label: "التبليغات" },
  ],
  instructor: [
    { href: "/home", label: "موادي" },
    { href: "/requests", label: "الوارد" },
    { href: "/schedule", label: "الجدول" },
    { href: "/broadcasts", label: "التبليغات" },
  ],
  department_coordinator: [
    { href: "/home", label: "الرئيسية" },
    { href: "/requests", label: "الوارد" },
    { href: "/schedule", label: "الجدول" },
    { href: "/broadcasts", label: "التبليغات" },
  ],
  department_head: [
    { href: "/home", label: "الرئيسية" },
    { href: "/requests", label: "الوارد" },
    { href: "/schedule", label: "الجدول" },
    { href: "/broadcasts", label: "التبليغات" },
  ],
};