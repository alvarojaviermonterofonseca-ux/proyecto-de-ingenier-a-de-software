import { Injectable, signal } from '@angular/core';

export type ToastTone = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  message?: string;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private sequence = 0;
  private readonly _toasts = signal<Toast[]>([]);
  readonly toasts = this._toasts.asReadonly();

  success(title: string, message?: string): void {
    this.push('success', title, message);
  }

  error(title: string, message?: string): void {
    this.push('error', title, message);
  }

  info(title: string, message?: string): void {
    this.push('info', title, message);
  }

  warning(title: string, message?: string): void {
    this.push('warning', title, message);
  }

  dismiss(id: number): void {
    this._toasts.update((toasts) => toasts.filter((toast) => toast.id !== id));
  }

  private push(tone: ToastTone, title: string, message?: string): void {
    const toast: Toast = { id: ++this.sequence, tone, title, message };
    this._toasts.update((toasts) => [...toasts, toast]);
    window.setTimeout(() => this.dismiss(toast.id), 5200);
  }
}
