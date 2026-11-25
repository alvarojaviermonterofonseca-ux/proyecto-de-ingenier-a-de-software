import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { ToastService } from '../../../core/ui/toast.service';
import { formatCurrency, formatDateTime } from '../../../core/utils/format';
import { IconComponent } from '../../../shared/icon.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import type { ConfiguracionGimnasio } from '../financial.models';
import { describirError } from '../forms/form-utils';

/**
 * Datos del gimnasio y umbrales del centro de alertas.
 *
 * El servidor toma el gimnasio de la sesión: esta página nunca envía un id de
 * gimnasio. El código lo asigna la plataforma y aquí solo se muestra.
 */
@Component({
  selector: 'app-configuracion-page',
  standalone: true,
  imports: [ReactiveFormsModule, IconComponent, PageHeaderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-container fade-in">
      <app-page-header
        title="Configuración del gimnasio"
        subtitle="Datos de tu gimnasio y umbrales con los que se generan las alertas"
      />

      @if (loadError()) {
        <div class="notice notice--error" role="alert">
          <app-icon name="alert" [size]="18" />
          <span>{{ loadError() }}</span>
          <button type="button" class="link-button" (click)="cargar()">Reintentar</button>
        </div>
      } @else if (loading()) {
        <div class="card"><div class="card__body"><div class="skeleton skeleton-title"></div></div></div>
      } @else {
        <form [formGroup]="form" (ngSubmit)="guardar()" novalidate class="config-grid">
          <section class="card">
            <header class="card__header">
              <div class="card__header-content">
                <h2>Datos del gimnasio</h2>
                <p>Aparecen en los reportes y en la barra lateral.</p>
              </div>
            </header>
            <div class="card__body">
              <div class="codigo">
                <div>
                  <span class="codigo__label">Código para el registro de clientes</span>
                  <strong class="codigo__valor">{{ codigo() }}</strong>
                </div>
                <p>Compártelo con tus clientes: lo escriben al crear su cuenta para unirse a este gimnasio.</p>
              </div>
              <div class="form-grid">
                <div class="field field--full">
                  <label for="cfg-nombre">Nombre</label>
                  <input id="cfg-nombre" formControlName="nombre" [readonly]="!puedeEditar()" />
                  @if (form.controls.nombre.touched && form.controls.nombre.invalid) {
                    <p class="field-error">El nombre es obligatorio.</p>
                  }
                </div>
                <div class="field">
                  <label for="cfg-nit">NIT</label>
                  <input id="cfg-nit" formControlName="nit" [readonly]="!puedeEditar()" />
                </div>
                <div class="field">
                  <label for="cfg-ciudad">Ciudad</label>
                  <input id="cfg-ciudad" formControlName="ciudad" [readonly]="!puedeEditar()" />
                </div>
                <div class="field field--full">
                  <label for="cfg-direccion">Dirección</label>
                  <input id="cfg-direccion" formControlName="direccion" [readonly]="!puedeEditar()" />
                </div>
                <div class="field">
                  <label for="cfg-telefono">Teléfono</label>
                  <input id="cfg-telefono" type="tel" formControlName="telefono" [readonly]="!puedeEditar()" />
                </div>
                <div class="field">
                  <label for="cfg-correo">Correo</label>
                  <input id="cfg-correo" type="email" formControlName="correo" [readonly]="!puedeEditar()" />
                  @if (form.controls.correo.touched && form.controls.correo.invalid) {
                    <p class="field-error">Escribe un correo válido.</p>
                  }
                </div>
              </div>
            </div>
          </section>

          <section class="card">
            <header class="card__header">
              <div class="card__header-content">
                <h2>Centro de alertas</h2>
                <p>Cuándo avisarte. Los vencimientos, los gastos nuevos y los pagos pendientes siempre se avisan.</p>
              </div>
            </header>
            <div class="card__body">
              <div class="form-grid form-grid--1">
                <div class="field">
                  <label for="cfg-inactividad">Días sin asistir para alertar</label>
                  <input id="cfg-inactividad" type="number" min="1" max="365" step="1" formControlName="dias_inactividad_alerta" [readonly]="!puedeEditar()" />
                  <p class="field-hint">Solo para clientes con membresía vigente.</p>
                  @if (form.controls.dias_inactividad_alerta.touched && form.controls.dias_inactividad_alerta.invalid) {
                    <p class="field-error">Entre 1 y 365 días.</p>
                  }
                </div>
                <div class="field">
                  <label for="cfg-limite">Límite mensual de gastos (COP)</label>
                  <input id="cfg-limite" type="number" min="1" step="any" formControlName="limite_gastos_mensual" placeholder="Sin límite" [readonly]="!puedeEditar()" />
                  <p class="field-hint">
                    @if (limiteActual(); as limite) { Hoy: {{ formatCurrency(limite) }}. } Déjalo vacío para no alertar.
                  </p>
                  @if (form.controls.limite_gastos_mensual.touched && form.controls.limite_gastos_mensual.invalid) {
                    <p class="field-error">Debe ser mayor que cero.</p>
                  }
                </div>
                <div class="field">
                  <label for="cfg-caida">Caída de ingresos que se alerta (%)</label>
                  <input id="cfg-caida" type="number" min="1" max="100" step="1" formControlName="porcentaje_caida_ingresos" [readonly]="!puedeEditar()" />
                  <p class="field-hint">Compara el último mes cerrado con el anterior.</p>
                  @if (form.controls.porcentaje_caida_ingresos.touched && form.controls.porcentaje_caida_ingresos.invalid) {
                    <p class="field-error">Entre 1 y 100.</p>
                  }
                </div>
              </div>
            </div>
          </section>

          @if (puedeEditar()) {
            <div class="config-actions">
              @if (actualizado(); as fecha) {
                <span class="text-muted">Última modificación: {{ formatDateTime(fecha) }}</span>
              }
              <button class="button button--secondary" type="button" (click)="restablecer()" [disabled]="saving() || form.pristine">
                Descartar cambios
              </button>
              <button class="button button--primary" type="submit" [disabled]="saving() || form.pristine">
                {{ saving() ? 'Guardando...' : 'Guardar configuración' }}
              </button>
            </div>
          } @else {
            <p class="text-muted">Solo un administrador puede cambiar esta configuración.</p>
          }
        </form>
      }
    </div>
  `,
  styles: [`
    .page-container { display: flex; flex-direction: column; gap: 1.5rem; }
    .config-grid { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 1.5rem; align-items: start; }
    .form-grid--1 { grid-template-columns: 1fr; }
    .config-actions { grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 0.75rem; }
    .config-actions .text-muted { margin-right: auto; }
    .codigo { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem 1rem; margin-bottom: 1.25rem; padding: 0.85rem 1rem; border: 1px dashed var(--gc-border-strong); border-radius: var(--gc-radius); background: var(--gc-surface-2); }
    .codigo p { flex: 1 1 16rem; margin: 0; color: var(--gc-muted); font-size: 0.8rem; }
    .codigo__label { display: block; color: var(--gc-muted); font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
    .codigo__valor { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 1.05rem; }
    .field-hint { margin: 0; color: var(--gc-muted); font-size: 0.75rem; }
    .text-muted { color: var(--gc-muted); font-size: 0.85rem; }
    @media (max-width: 960px) { .config-grid { grid-template-columns: 1fr; } }
  `],
})
export class ConfiguracionPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly toast = inject(ToastService);

  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly codigo = signal('');
  protected readonly actualizado = signal<string | null>(null);
  protected readonly limiteActual = signal<string | null>(null);
  protected readonly formatCurrency = formatCurrency;
  protected readonly formatDateTime = formatDateTime;
  private original: ConfiguracionGimnasio | null = null;

  protected readonly form = this.formBuilder.group({
    nombre: ['', [Validators.required, Validators.maxLength(150)]],
    nit: [''],
    ciudad: [''],
    direccion: [''],
    telefono: [''],
    correo: ['', [Validators.email]],
    dias_inactividad_alerta: [15 as number | null, [Validators.required, Validators.min(1), Validators.max(365)]],
    limite_gastos_mensual: [null as number | null, [Validators.min(1)]],
    porcentaje_caida_ingresos: [30 as number | null, [Validators.required, Validators.min(1), Validators.max(100)]],
  });

  protected puedeEditar(): boolean {
    return this.auth.isAdmin();
  }

  ngOnInit(): void {
    this.cargar();
  }

  protected cargar(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.api.get<ConfiguracionGimnasio>('gimnasio/').subscribe({
      next: (config) => {
        this.aplicar(config);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.loadError.set(describirError(error, 'No se pudo cargar la configuración del gimnasio.'));
      },
    });
  }

  protected restablecer(): void {
    if (this.original) this.aplicar(this.original);
  }

  protected guardar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const texto = (valor: string | null) => (valor ?? '').trim() || null;
    this.saving.set(true);
    this.api
      .patch<ConfiguracionGimnasio>('gimnasio/', {
        nombre: (raw.nombre ?? '').trim(),
        nit: texto(raw.nit),
        ciudad: texto(raw.ciudad),
        direccion: texto(raw.direccion),
        telefono: texto(raw.telefono),
        correo: texto(raw.correo),
        dias_inactividad_alerta: raw.dias_inactividad_alerta,
        limite_gastos_mensual: raw.limite_gastos_mensual ? String(raw.limite_gastos_mensual) : null,
        porcentaje_caida_ingresos: raw.porcentaje_caida_ingresos,
      })
      .subscribe({
        next: (config) => {
          this.saving.set(false);
          this.aplicar(config);
          this.toast.success('Configuración guardada');
          // El nombre del gimnasio también se muestra en la barra lateral.
          this.auth.refresh().subscribe({ error: () => undefined });
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.toast.error('No se pudo guardar', describirError(error, 'Revisa los datos.'));
        },
      });
  }

  private aplicar(config: ConfiguracionGimnasio): void {
    this.original = config;
    this.codigo.set(config.codigo);
    this.actualizado.set(config.updated_at);
    this.limiteActual.set(config.limite_gastos_mensual);
    this.form.reset({
      nombre: config.nombre,
      nit: config.nit ?? '',
      ciudad: config.ciudad ?? '',
      direccion: config.direccion ?? '',
      telefono: config.telefono ?? '',
      correo: config.correo ?? '',
      dias_inactividad_alerta: config.dias_inactividad_alerta,
      limite_gastos_mensual: config.limite_gastos_mensual ? Number(config.limite_gastos_mensual) : null,
      porcentaje_caida_ingresos: config.porcentaje_caida_ingresos,
    });
  }
}
