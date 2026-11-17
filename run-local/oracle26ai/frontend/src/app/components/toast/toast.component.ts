import { Component, inject } from '@angular/core';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-toasts',
  template: `
    <div class="toasts" aria-live="polite">
      @for (t of toast.toasts(); track t.id) {
        <div class="toast {{ t.kind }}" role="status">
          <span class="icon">{{ t.kind === 'success' ? '✓' : t.kind === 'error' ? '!' : 'i' }}</span>
          <span class="text">{{ t.text }}</span>
          <button type="button" aria-label="Close" (click)="toast.dismiss(t.id)">✕</button>
        </div>
      }
    </div>`,
  styles: [`
    .toasts { position: fixed; right: 20px; bottom: 20px; z-index: 100; display: flex; flex-direction: column; gap: 10px; max-width: 420px; }
    .toast { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 10px; background: #14213D; color: #fff;
      box-shadow: 0 8px 24px rgba(16, 24, 40, .25); font-size: 14px; animation: in .25s ease-out; }
    .toast.success .icon { background: #12a37f; } .toast.error .icon { background: #d64545; } .toast.info .icon { background: #2f5bea; }
    .icon { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; flex: none; }
    .text { flex: 1; }
    button { background: none; border: 0; color: #c9d3ea; cursor: pointer; font-size: 14px; }
    @keyframes in { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
  `],
})
export class ToastComponent {
  toast = inject(ToastService);
}
