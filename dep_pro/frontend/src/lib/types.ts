export type Role =
  | "student"
  | "class_representative"
  | "instructor"
  | "department_coordinator"
  | "department_head";

export type Stage = Role;
export type RequestCategory = "academic" | "administrative";

export interface Me {
  id: number;
  full_name: string;
  email: string;
  role: Role;
  section_id: number | null;
  department_id: number | null;
}

export interface Course {
  id: number;
  code: string;
  name_ar: string;
  department_id: number;
}

export interface Room {
  id: number;
  code: string;
  name: string | null;
  capacity: number;
  is_available: boolean;
}

export interface NotificationItem {
  id: number;
  notification_type: string;
  title: string;
  body: string;
  lecture_occurrence_id: number | null;
  sent_at: string | null;
}

export interface UnitView {
  kind: "request" | "batch";
  id: number;
  section_id: number;
  category: RequestCategory | null;
  course_id: number | null;
  title: string;
  summary: string;
  request_count: number;
  status: string;
  current_stage: Stage;
  created_at: string;
}

export interface RequestItem {
  id: number;
  course_id: number | null;
  subject: string;
  body: string;
  category: RequestCategory | null;
  classification_confidence: number | null;
  status: string;
  current_stage: Stage;
  batch_id: number | null;
  created_at: string;
}

export interface EventItem {
  action: string;
  from_stage: Stage | null;
  to_stage: Stage | null;
  actor_user_id: number | null;
  note: string | null;
  created_at: string;
}

export type SlotType = "regular" | "makeup" | "postponed" | "cancelled";

export interface Occurrence {
  id: number;
  enrollment_id: number;
  section_id: number;
  course_id: number;
  course_code: string;
  course_name: string;
  occurrence_date: string;
  starts_at: string;
  ends_at: string;
  room_id: number | null;
  room_code: string | null;
  slot_type: SlotType;
  is_cancelled: boolean;
  note: string | null;
  version: number;
}

export interface MakeupSuggestion {
  id: number;
  enrollment_id: number;
  suggested_date: string;
  starts_at: string;
  ends_at: string;
  room_id: number;
  room_code: string;
  score: number;
  is_accepted: boolean;
}

export type ChangeType =
  | "room_change"
  | "time_change"
  | "postponement"
  | "cancellation"
  | "makeup_added";

export interface ScheduleChange {
  id: number;
  occurrence_id: number;
  change_type: ChangeType;
  changed_by_user_id: number | null;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

export interface Broadcast {
  id: number;
  channel_id: number;
  channel_name: string;
  scope: "department" | "course";
  title: string;
  body: string;
  is_pinned: boolean;
  audience_count: number;
  seen_count: number;
  created_at: string;
}

export interface Reader {
  full_name: string;
  read_at: string;
}

export interface Source {
  chunk_id: number;
  material_title: string;
  page_number: number | null;
  similarity: number;
  excerpt: string;
}

export interface AnswerResult {
  answer: string;
  grounded: boolean;
  question_id: number | null;
  sources: Source[];
}

export type QuizStatus = "draft" | "published" | "closed";

export interface QuizListItem {
  id: number;
  title: string;
  status: QuizStatus;
  question_count: number;
  opens_at: string | null;
  closes_at: string | null;
}

export interface QuizQuestion {
  id: number;
  position: number;
  question_type: "mcq" | "true_false";
  question_text: string;
  options: string[];
  correct_option_index?: number | null;
  explanation?: string | null;
}

export interface Quiz {
  id: number;
  course_id: number;
  title: string;
  status: QuizStatus;
  opens_at: string | null;
  closes_at: string | null;
  questions: QuizQuestion[];
}

export type MaterialStatus = "pending" | "processing" | "ready" | "failed";

export interface Material {
  id: number;
  title: string;
  status: MaterialStatus;
  page_count: number | null;
  error_message: string | null;
  created_at: string;
}

export interface GapAlert {
  id: number;
  course_id: number;
  section_id: number;
  topic_label: string;
  distinct_student_count: number;
  section_student_total: number;
  affected_ratio: number;
  summary: string;
  status: "open" | "acknowledged" | "resolved";
  created_at: string;
}