// Thin typed wrapper over the backend REST API. All calls go through /api/v1,
// which Vite (dev) or the Node adapter origin (prod) proxies to the backend.

import type {
  ConditionDetail,
  ConditionNote,
  ConversationDetail,
  ConversationSummary,
  DailyEntry,
  DailyEntrySummary,
  DailyStatPoint,
  DayTimer,
  DayTingling,
  DocumentMeta,
  Exercise,
  ExerciseLog,
  Interval,
  LlmSettings,
  LlmSettingsIn,
  Note,
  PainInstance,
  PatientProfile,
  Posture,
  SessionDetail,
  TinglingInterval,
  WeeklyDraft,
  WeeklySummary
} from './types';

const BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...init
  });
  if (!res.ok) {
    // A 401 on a non-auth call means the session expired mid-use — bounce to
    // login. Auth endpoints (/auth/me) handle their own 401 and must not loop.
    if (res.status === 401 && typeof window !== 'undefined' && !path.startsWith('/auth')) {
      window.location.href = '/login';
    }
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface CurrentUser {
  email: string;
  name: string | null;
}

export interface AuthConfig {
  mode: 'none' | 'password' | 'google';
  allow_registration: boolean;
}

export const api = {
  // Auth
  me: () =>
    request<CurrentUser>('/auth/me').catch((e: Error) => {
      if (e.message.startsWith('401')) return null;
      throw e;
    }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  authConfig: () => request<AuthConfig>('/auth/config'),
  register: (email: string, password: string, name?: string) =>
    request<{ ok: boolean }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name })
    }),
  login: (email: string, password: string) =>
    request<{ ok: boolean }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    }),

  // Entries
  listEntries: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set('from', from);
    if (to) q.set('to', to);
    return request<DailyEntrySummary[]>(`/entries?${q}`);
  },
  getEntry: (date: string) =>
    request<DailyEntry | null>(`/entries/${date}`).catch((e: Error) => {
      if (e.message.startsWith('404')) return null;
      throw e;
    }),
  upsertEntry: (date: string, data: Partial<DailyEntry>) =>
    request<DailyEntry>(`/entries/${date}`, { method: 'PUT', body: JSON.stringify(data) }),
  addPainEvent: (
    date: string,
    data: {
      pain_level?: number;
      context?: string;
      occurred_at?: string;
      instance_ids?: string[];
    }
  ) => request(`/entries/${date}/pain-events`, { method: 'POST', body: JSON.stringify(data) }),
  deletePainEvent: (id: string) => request(`/pain-events/${id}`, { method: 'DELETE' }),
  addNote: (date: string, data: { body: string; occurred_at?: string }) =>
    request<Note>(`/entries/${date}/notes`, { method: 'POST', body: JSON.stringify(data) }),
  updateNote: (id: string, data: { body?: string; occurred_at?: string }) =>
    request<Note>(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteNote: (id: string) => request(`/notes/${id}`, { method: 'DELETE' }),

  // Exercises & sessions
  listExercises: () => request<Exercise[]>('/exercises'),
  createExercise: (name: string) =>
    request<Exercise>('/exercises', { method: 'POST', body: JSON.stringify({ name }) }),
  patchExercise: (id: string, data: Partial<Exercise>) =>
    request<Exercise>(`/exercises/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  createSession: (date: string, data: Partial<SessionDetail>) =>
    request<SessionDetail>(`/entries/${date}/session`, {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  updateSession: (id: string, data: Partial<SessionDetail>) =>
    request<SessionDetail>(`/sessions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  sessionsForDate: (date: string) => request<SessionDetail[]>(`/entries/${date}/sessions`),
  deleteSession: (id: string) => request<void>(`/sessions/${id}`, { method: 'DELETE' }),
  latestSession: () => request<SessionDetail | null>('/sessions/latest'),
  progression: (exerciseId: string) =>
    request<Record<string, unknown>[]>(`/exercises/${exerciseId}/progression`),
  lastLogs: () => request<Record<string, Partial<ExerciseLog>>>('/exercises/last-logs'),

  // Pain instances
  listPainInstances: () => request<PainInstance[]>('/pain-instances'),
  createPainInstance: (data: { name: string; body_region?: string; background?: string }) =>
    request<PainInstance>('/pain-instances', { method: 'POST', body: JSON.stringify(data) }),
  patchPainInstance: (id: string, data: Partial<PainInstance>) =>
    request<PainInstance>(`/pain-instances/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    }),

  // Timer
  startTimer: (posture: Posture, label?: string) =>
    request<Interval>('/timer/start', { method: 'POST', body: JSON.stringify({ posture, label }) }),
  stopTimer: () => request<Interval | null>('/timer/stop', { method: 'POST' }),
  currentTimer: () => request<Interval | null>('/timer/current'),
  dayTimer: (date: string) => request<DayTimer>(`/timer/day/${date}`),
  patchInterval: (id: string, data: Partial<Interval>) =>
    request<Interval>(`/timer/intervals/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteInterval: (id: string) => request(`/timer/intervals/${id}`, { method: 'DELETE' }),

  // Tingling timer
  startTingling: (level: number) =>
    request<TinglingInterval>('/tingling/start', {
      method: 'POST',
      body: JSON.stringify({ level })
    }),
  stopTingling: () => request<TinglingInterval | null>('/tingling/stop', { method: 'POST' }),
  currentTingling: () => request<TinglingInterval | null>('/tingling/current'),
  tinglingDay: (date: string) => request<DayTingling>(`/tingling/day/${date}`),
  deleteTinglingInterval: (id: string) =>
    request(`/tingling/intervals/${id}`, { method: 'DELETE' }),

  // Stats & weekly
  dailyStats: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set('from', from);
    if (to) q.set('to', to);
    return request<DailyStatPoint[]>(`/stats/daily?${q}`);
  },
  listWeeks: () => request<WeeklySummary[]>('/weeks'),
  getWeek: (weekStart: string) => request<WeeklySummary>(`/weeks/${weekStart}`),
  saveWeek: (
    weekStart: string,
    data: {
      overall_status?: string;
      key_observations?: string;
      trend_vs_last_week?: string;
      next_steps?: string;
    }
  ) => request<WeeklySummary>(`/weeks/${weekStart}`, { method: 'PUT', body: JSON.stringify(data) }),

  // AI
  getLlmSettings: () => request<LlmSettings>('/ai/settings'),
  saveLlmSettings: (data: LlmSettingsIn) =>
    request<LlmSettings>('/ai/settings', { method: 'PUT', body: JSON.stringify(data) }),
  listConversations: () => request<ConversationSummary[]>('/ai/conversations'),
  createConversation: () => request<ConversationSummary>('/ai/conversations', { method: 'POST' }),
  getConversation: (id: string) => request<ConversationDetail>(`/ai/conversations/${id}`),
  deleteConversation: (id: string) => request(`/ai/conversations/${id}`, { method: 'DELETE' }),
  weeklyDraft: (weekStart: string) =>
    request<WeeklyDraft>(`/ai/weekly-draft/${weekStart}`, { method: 'POST' }),

  // Records
  getProfile: () => request<PatientProfile>('/profile'),
  saveProfile: (data: Partial<PatientProfile>) =>
    request<PatientProfile>('/profile', { method: 'PUT', body: JSON.stringify(data) }),
  getCondition: (id: string) => request<ConditionDetail>(`/pain-instances/${id}`),
  addConditionNote: (id: string, data: { body: string; occurred_at?: string }) =>
    request<ConditionNote>(`/pain-instances/${id}/notes`, {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  updateConditionNote: (noteId: string, data: { body?: string; occurred_at?: string }) =>
    request<ConditionNote>(`/condition-notes/${noteId}`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    }),
  deleteConditionNote: (noteId: string) =>
    request(`/condition-notes/${noteId}`, { method: 'DELETE' }),
  listDocuments: (params?: { owner_type?: string; instance_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.owner_type) q.set('owner_type', params.owner_type);
    if (params?.instance_id) q.set('instance_id', params.instance_id);
    return request<DocumentMeta[]>(`/documents?${q}`);
  },
  uploadDocument: async (form: FormData) => {
    const res = await fetch('/api/v1/documents', {
      method: 'POST',
      credentials: 'include',
      body: form
    });
    if (!res.ok) throw new Error(`${res.status}: ${(await res.json()).detail}`);
    return (await res.json()) as DocumentMeta;
  },
  updateDocument: (id: string, data: { title?: string; notes?: string }) =>
    request<DocumentMeta>(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteDocument: (id: string) => request(`/documents/${id}`, { method: 'DELETE' }),
  documentDownloadUrl: (id: string) => `/api/v1/documents/${id}/download`,

  // Import
  importXlsx: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/import/xlsx`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`${res.status}: ${(await res.json()).detail}`);
    return res.json();
  }
};
