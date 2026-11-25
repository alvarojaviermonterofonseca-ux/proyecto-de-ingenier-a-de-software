import { Injectable, inject, signal } from '@angular/core';

import { ApiClient } from '../api/api-client.service';

/**
 * Descarga con autenticación las imágenes privadas de ejercicios y las
 * guarda como ``blob:`` en memoria para no pedirlas otra vez.
 */
@Injectable({ providedIn: 'root' })
export class ExerciseImagesService {
  private readonly api = inject(ApiClient);
  private readonly urls = signal<Record<string, string>>({});
  private readonly pending = new Set<string>();

  /** URL lista para ``<img>``; vacía mientras carga o si no hay imagen. */
  url(key: string | null): string | null {
    return key ? this.urls()[key] ?? null : null;
  }

  /**
   * Pide la imagen de ``path`` (ruta de la API) bajo la clave ``key``.
   * La clave incluye la fecha de actualización para refrescar al cambiarla.
   */
  load(key: string, path: string): void {
    if (this.urls()[key] || this.pending.has(key)) return;
    this.pending.add(key);
    this.api.blob(path).subscribe({
      next: (blob) => {
        this.pending.delete(key);
        this.urls.update((urls) => ({ ...urls, [key]: URL.createObjectURL(blob) }));
      },
      error: () => this.pending.delete(key),
    });
  }
}
