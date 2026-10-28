import { Injectable, signal } from '@angular/core';

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'danger' | 'primary';
}

export interface ConfirmState extends ConfirmOptions {
  open: boolean;
}

@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private resolver: ((value: boolean) => void) | null = null;
  private readonly _state = signal<ConfirmState>({
    open: false,
    title: '',
    message: '',
  });

  readonly state = this._state.asReadonly();

  confirm(options: ConfirmOptions): Promise<boolean> {
    this.resolve(false);
    this._state.set({ ...options, open: true });
    return new Promise<boolean>((resolve) => {
      this.resolver = resolve;
    });
  }

  accept(): void {
    this.close(true);
  }

  cancel(): void {
    this.close(false);
  }

  private close(value: boolean): void {
    this._state.update((state) => ({ ...state, open: false }));
    const resolver = this.resolver;
    this.resolver = null;
    resolver?.(value);
  }

  private resolve(value: boolean): void {
    const resolver = this.resolver;
    this.resolver = null;
    resolver?.(value);
  }
}
