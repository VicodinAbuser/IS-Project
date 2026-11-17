import { Injectable, signal } from '@angular/core';

export interface Toast { id: number; text: string; kind: 'success' | 'error' | 'info'; }

/** Short pop-up messages ("Order #12: delivery updated to Delivered") shown in the corner for a few seconds. */
@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);
  private next = 1;

  success(text: string) { this.show(text, 'success'); }
  error(text: string) { this.show(text, 'error', 6000); }
  info(text: string) { this.show(text, 'info'); }

  dismiss(id: number) { this.toasts.update(list => list.filter(t => t.id !== id)); }

  private show(text: string, kind: Toast['kind'], ms = 4000) {
    const id = this.next++;
    this.toasts.update(list => [...list.slice(-3), { id, text, kind }]);   // at most 4 on screen
    setTimeout(() => this.dismiss(id), ms);
  }
}
