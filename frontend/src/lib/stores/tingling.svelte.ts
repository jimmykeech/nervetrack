// Independent tingling timer store: the running interval lives on the backend;
// this restores it on load and keeps a live tick for the elapsed display.
import { api } from '$lib/api';
import type { TinglingInterval } from '$lib/types';
import { intervalSeconds, todayISO } from '$lib/time';

export class TinglingTimerStore {
  running = $state<TinglingInterval | null>(null);
  intervals = $state<TinglingInterval[]>([]);
  date = $state<string>(todayISO());
  now = $state<number>(Date.now());

  private ticker: ReturnType<typeof setInterval> | null = null;

  get elapsed(): number {
    return this.running ? intervalSeconds(this.running, this.now) : 0;
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
    this.date = date;
    const day = await api.tinglingDay(date);
    this.intervals = day.intervals;
    this.running = await api.currentTingling();
    this.now = Date.now();
  }

  async start(level: number) {
    this.running = await api.startTingling(level);
    await this.refresh();
  }

  async stop() {
    await api.stopTingling();
    this.running = null;
    await this.refresh();
  }

  async remove(id: string) {
    await api.deleteTinglingInterval(id);
    await this.refresh();
    this.running = await api.currentTingling();
  }

  private async refresh() {
    const day = await api.tinglingDay(this.date);
    this.intervals = day.intervals;
    this.now = Date.now();
  }
}
