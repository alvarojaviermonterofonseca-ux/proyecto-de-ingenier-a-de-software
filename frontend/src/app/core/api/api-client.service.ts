import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, of, switchMap } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { PaginatedResponse } from './api.models';

export type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue>;

@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiBaseUrl.replace(/\/+$/, '');

  get<T>(path: string, params: QueryParams = {}): Observable<T> {
    return this.http.get<T>(this.url(path), { params: this.params(params) });
  }

  getAll<T>(path: string, params: QueryParams = {}): Observable<T[]> {
    return this.fetchAll<T>(path, params, 1, []);
  }

  post<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(this.url(path), body);
  }

  put<T>(path: string, body: unknown): Observable<T> {
    return this.http.put<T>(this.url(path), body);
  }

  patch<T>(path: string, body: unknown): Observable<T> {
    return this.http.patch<T>(this.url(path), body);
  }

  delete<T = void>(path: string): Observable<T> {
    return this.http.delete<T>(this.url(path));
  }

  upload<T>(path: string, formData: FormData): Observable<T> {
    return this.http.post<T>(this.url(path), formData);
  }

  uploadPatch<T>(path: string, formData: FormData): Observable<T> {
    return this.http.patch<T>(this.url(path), formData);
  }

  blob(path: string): Observable<Blob> {
    return this.http.get(this.url(path), { responseType: 'blob' });
  }

  private fetchAll<T>(
    path: string,
    params: QueryParams,
    page: number,
    accumulated: T[],
  ): Observable<T[]> {
    return this.get<PaginatedResponse<T> | T[]>(path, { ...params, page }).pipe(
      switchMap((response) => {
        if (Array.isArray(response)) {
          return of([...accumulated, ...response]);
        }
        const results = [...accumulated, ...response.results];
        return response.next
          ? this.fetchAll<T>(path, params, page + 1, results)
          : of(results);
      }),
    );
  }

  private url(path: string): string {
    return `${this.baseUrl}/${path.replace(/^\/+/, '')}`;
  }

  private params(params: QueryParams): HttpParams {
    let httpParams = new HttpParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === null || value === undefined || value === '') {
        continue;
      }
      httpParams = httpParams.set(key, String(value));
    }
    return httpParams;
  }
}
