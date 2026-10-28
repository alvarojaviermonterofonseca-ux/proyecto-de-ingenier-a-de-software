import { Injectable } from '@angular/core';

const TOKEN_KEY = 'gym_control_token';
const EXPIRY_KEY = 'gym_control_token_expiry';
const SESSION_EVENT = 'gym-control-session-expired';

@Injectable({ providedIn: 'root' })
export class TokenStorage {
  get token(): string | null {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  get expiry(): string | null {
    return sessionStorage.getItem(EXPIRY_KEY);
  }

  save(token: string, expiry: string): void {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(EXPIRY_KEY, expiry);
  }

  clear(): void {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(EXPIRY_KEY);
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
