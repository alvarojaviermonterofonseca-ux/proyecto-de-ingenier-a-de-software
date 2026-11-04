import { Injectable } from '@angular/core';

const TOKEN_KEY = 'gym_control_token';
const EXPIRY_KEY = 'gym_control_token_expiry';
const SESSION_EVENT = 'gym-control-session-expired';

function getStorage(): Storage | null {
  try {
    return sessionStorage;
  } catch {
    return null;
  }
}

@Injectable({ providedIn: 'root' })
export class TokenStorage {
  get token(): string | null {
    const storage = getStorage();
    return storage?.getItem(TOKEN_KEY) ?? null;
  }

  get expiry(): string | null {
    const storage = getStorage();
    return storage?.getItem(EXPIRY_KEY) ?? null;
  }

  save(token: string, expiry: string): void {
    const storage = getStorage();
    if (storage) {
      storage.setItem(TOKEN_KEY, token);
      storage.setItem(EXPIRY_KEY, expiry);
    }
  }

  clear(): void {
    const storage = getStorage();
    if (storage) {
      storage.removeItem(TOKEN_KEY);
      storage.removeItem(EXPIRY_KEY);
    }
  }

  isExpired(): boolean {
    const expiry = this.expiry;
    if (!expiry) {
      return false;
    }
    return new Date(expiry).getTime() <= Date.now();
  }

  notifyExpired(): void {
    window.dispatchEvent(new Event(SESSION_EVENT));
  }
}

export const SESSION_EXPIRED_EVENT = SESSION_EVENT;
