export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "sdp_access_token";

/*
 * الرمز محفوظ في sessionStorage لا localStorage: كل تبويب يحتفظ بجلسته المستقلة.
 * localStorage مشترك بين كل تبويبات النطاق، فتسجيل دخول حساب في تبويب يستبدل رمز
 * الحساب الذي يستخدمه تبويب آخر، فتظهر أخطاء 403 غير مفهومة.
 */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const tokenStore = {
  get(): string | null {
    if (typeof window === "undefined") return null;
    return window.sessionStorage.getItem(TOKEN_KEY);
  },
  set(token: string): void {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  },
  clear(): void {
    if (typeof window !== "undefined") window.sessionStorage.removeItem(TOKEN_KEY);
  },
};

export function authHeaders(): Record<string, string> {
  const token = tokenStore.get();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type ApiInit = Omit<RequestInit, "body"> & { json?: unknown; form?: FormData };

function extractMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => (item as { msg?: string }).msg ?? "خطأ في البيانات").join("؛ ");
    }
  }
  return fallback;
}

export async function apiFetch<T>(path: string, { json, form, headers: extra, ...init }: ApiInit = {}): Promise<T> {
  const headers = new Headers(extra);
  for (const [key, value] of Object.entries(authHeaders())) headers.set(key, value);

  let body: BodyInit | undefined;
  if (form) {
    body = form;
  } else if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }

  const response = await fetch(`${API_URL}${path}`, { ...init, headers, body, cache: "no-store" });

  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/api/auth/login")) {
      tokenStore.clear();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.assign("/login");
      }
    }
    const data = await response.json().catch(() => null);
    throw new ApiError(response.status, extractMessage(data, response.statusText || "حدث خطأ غير متوقع"));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "حدث خطأ غير متوقع";
}