import { API_URL, authHeaders } from "./api";
import type { ScheduleChange } from "./types";

export type StreamStatus = "connecting" | "live" | "offline";

interface SseBlock {
  event: string;
  data: string;
}

function parseBlock(raw: string): SseBlock | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

/**
 * يشترك في بث تغييرات الجدول عبر fetch (EventSource لا يرسل ترويسة Authorization).
 * يعيد الاتصال تلقائياً بآخر معرّف استلمه، فلا تضيع أي تغييرات.
 * يعيد دالة لإلغاء الاشتراك.
 */
export function subscribeSchedule(
  onChange: (change: ScheduleChange) => void,
  onStatus?: (status: StreamStatus) => void,
): () => void {
  let lastId = -1;
  let stopped = false;
  const controller = new AbortController();
  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  async function connect(): Promise<void> {
    while (!stopped) {
      try {
        onStatus?.("connecting");
        const response = await fetch(`${API_URL}/api/schedule/stream?after_id=${lastId}`, {
          headers: authHeaders(),
          signal: controller.signal,
          cache: "no-store",
        });
        if (response.status === 401) {
          onStatus?.("offline");
          return;
        }
        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

        onStatus?.("live");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!stopped) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let end = buffer.indexOf("\n\n");
          while (end !== -1) {
            const block = parseBlock(buffer.slice(0, end));
            buffer = buffer.slice(end + 2);
            if (block?.event === "schedule_change") {
              const change = JSON.parse(block.data) as ScheduleChange;
              lastId = Math.max(lastId, change.id);
              onChange(change);
            }
            end = buffer.indexOf("\n\n");
          }
        }
      } catch {
        if (stopped) return;
        onStatus?.("offline");
        await sleep(3000);
      }
    }
  }

  void connect();

  return () => {
    stopped = true;
    controller.abort();
  };
}