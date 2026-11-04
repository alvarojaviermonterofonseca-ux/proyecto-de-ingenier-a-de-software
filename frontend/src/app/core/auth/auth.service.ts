import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal, OnDestroy } from '@angular/core';
import { Observable, firstValueFrom, switchMap, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { CurrentUser, LoginResponse } from '../api/api.models';
import { SESSION_EXPIRED_EVENT, TokenStorage } from './token-storage.service';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly tokens = inject(TokenStorage);
  private readonly baseUrl = environment.apiBaseUrl.replace(/\/+$/, '');

  private readonly _user = signal<CurrentUser | null>(null);
  private readonly _permissions = signal<ReadonlySet<string>>(new Set());
  private readonly _restoring = signal(false);
  private readonly sessionExpiredHandler = () => this.clearSession();

  readonly user = this._user.asReadonly();
  readonly permissions = this._permissions.asReadonly();
  readonly restoring = this._restoring.asReadonly();
  readonly authenticated = computed(() => this._user() !== null);
  readonly roleName = computed(() => this._user()?.rol_detalle?.nombre ?? null);
  readonly isAdmin = computed(
    () =>
      this._user()?.es_administrador === true ||
      this.roleName() === 'administrador' ||
      (this._user()?.roles_efectivos ?? []).some((rol) => rol.nombre === 'administrador'),
  );

  constructor() {
    window.addEventListener(SESSION_EXPIRED_EVENT, this.sessionExpiredHandler);
  }

  ngOnDestroy(): void {
    window.removeEventListener(SESSION_EXPIRED_EVENT, this.sessionExpiredHandler);
  }

  login(correo: string, contrasena: string): Observable<CurrentUser> {
    return this.http
      .post<LoginResponse>(`${this.baseUrl}/login/`, { correo, contrasena })
      .pipe(
        tap((response) => this.tokens.save(response.token, response.expira_at)),
        switchMap(() => this.http.get<CurrentUser>(`${this.baseUrl}/me/`)),
        tap((user) => this.applyUser(user)),
      );
  }

  async restore(): Promise<boolean> {
    // Si ya hay usuario, verificar que el token no haya expirado
    if (this._user()) {
      const expiry = this.tokens.expiry;
      if (expiry && new Date(expiry).getTime() <= Date.now()) {
        this.clearSession();
        return false;
      }
      return true;
    }
    if (!this.tokens.token || this.tokens.isExpired()) {
      this.clearSession();
      return false;
    }
    this._restoring.set(true);
    try {
      const user = await firstValueFrom(
        this.http.get<CurrentUser>(`${this.baseUrl}/me/`),
      );
      this.applyUser(user);
      return true;
    } catch {
      this.clearSession();
      return false;
    } finally {
      this._restoring.set(false);
    }
  }

  refresh(): Observable<CurrentUser> {
    return this.http
      .get<CurrentUser>(`${this.baseUrl}/me/`)
      .pipe(tap((user) => this.applyUser(user)));
  }

  logout(): Observable<{ mensaje: string }> {
    return this.http
      .post<{ mensaje: string }>(`${this.baseUrl}/logout/`, {})
      .pipe(tap(() => this.clearSession()));
  }

  logoutAll(): Observable<{ mensaje: string; sesiones_revocadas: number }> {
    return this.http
      .post<{ mensaje: string; sesiones_revocadas: number }>(
        `${this.baseUrl}/logout/all/`,
        {},
      )
      .pipe(tap(() => this.clearSession()));
  }

  clearSession(): void {
    this.tokens.clear();
    this._user.set(null);
    this._permissions.set(new Set());
  }

  hasPermission(code: string): boolean {
    return this._permissions().has(code);
  }

  hasAny(codes: readonly string[]): boolean {
    return codes.length === 0 || codes.some((code) => this.hasPermission(code));
  }

  hasAll(codes: readonly string[]): boolean {
    return codes.every((code) => this.hasPermission(code));
  }

  private applyUser(user: CurrentUser): void {
    this._user.set(user);
    this._permissions.set(new Set(user.permisos_efectivos ?? user.permisos ?? []));
    const expiry = this.tokens.expiry;
    if (expiry && new Date(expiry).getTime() <= Date.now()) {
      this.clearSession();
    }
  }
}
