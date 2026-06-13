// Server-backed timer store. The running interval lives on the backend, so
// this store restores it on load and keeps a live tick for the elapsed display.

import { api } from '$lib/api';
import { intervalSeconds, liveTotals } from '$lib/time';
import type { DayTimer, Interval, Posture, PostureTotals } from '$lib/types';
import { todayISO } from '$lib/time';

export class TimerStore {
  running = $state<Interval | null>(null);
  intervals = $state<Interval[]>([]);
  date = $state<string>(todayISO());
  now = $state<number>(Date.now());
  loading = $state<boolean>(true);

  private ticker: ReturnType<typeof setInterval> | null = null;

  /** Elapsed seconds of the running interval (live). */
  get elapsed(): number {
    return this.running ? intervalSeconds(this.running, this.now) : 0;
  }

  /** Per-posture totals for the loaded day, including the live running interval. */
  get totals(): PostureTotals {
    return liveTotals(this.intervals, this.now);
  }

  startTicking() {
    if (this.ticker) return;
    this.ticker = setInterval(() => (this.now = Date.now()), 1000);
  }

  stopTicking() {
    if (this.ticker) clearInterval(this.ticker);
    this.ticker = null;
  }

  async load(date: string = todayISO()) {
    this.loading = true;
    this.date = date;
    const day: DayTimer = await api.dayTimer(date);
    this.intervals = day.intervals;
    // The running interval may belong to a different (today's) day; fetch it
    // explicitly so state restores even when viewing a past day.
    this.running = await api.currentTimer();
    this.now = Date.now();
    this.loading = false;
  }

  async switchTo(posture: Posture, label?: string) {
    this.running = await api.startTimer(posture, label);
    await this.refreshDay();
  }

  async stop() {
    await api.stopTimer();
    this.running = null;
    await this.refreshDay();
  }

  async editInterval(id: string, data: Partial<Interval>) {
    await api.patchInterval(id, data);
    await this.refreshDay();
    this.running = await api.currentTimer();
  }

  async deleteInterval(id: string) {
    await api.deleteInterval(id);
    await this.refreshDay();
    this.running = await api.currentTimer();
  }

  private async refreshDay() {
    const day = await api.dayTimer(this.date);
    this.intervals = day.intervals;
    this.now = Date.now();
  }
}
