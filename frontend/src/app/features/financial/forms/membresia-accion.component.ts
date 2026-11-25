import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ToastService } from '../../../core/ui/toast.service';
import { formatDate } from '../../../core/utils/format';
import { IconComponent } from '../../../shared/icon.component';
import { ModalComponent } from '../../../shared/modal.component';
import { Membresia } from '../financial.models';
import { FinancialService } from '../financial.service';
import { describirError, sumarDias, sumarMeses } from './form-utils';
import { TIPOS_MEMBRESIA } from './membresia-form.component';

export interface AccionMembresia {
  tipo: 'renovar' | 'congelar';
  membresia: Membresia;
}

/** Diálogo para renovar (por meses) o congelar (por días) una membresía. */
@Component({
  selector: 'app-membresia-accion',
  standalone: true,
  imports: [ReactiveFormsModule, IconComponent, ModalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-modal
      [open]="accion() !== null"
      [title]="esRenovacion() ? 'Renovar membresía' : 'Congelar membresía'"
      [subtitle]="subtitulo()"
      size="narrow"
      (closed)="cerrar()"
    >
      @if (formError()) {
        <div class="notice notice--error" role="alert">
          <app-icon name="alert" [size]="18" />
          <span>{{ formError() }}</span>
        </div>
      }

      <form [formGroup]="form" (ngSubmit)="guardar()" novalidate>
        <div class="form-grid">
          @if (esRenovacion()) {
            <div class="field field--full">
              <label for="accion-tipo">Tipo</label>
              <select id="accion-tipo" formControlName="tipo" (change)="alCambiarTipo()">
                @for (tipo of tipos; track tipo.valor) {
                  <option [value]="tipo.valor">{{ tipo.etiqueta }}</option>
                }
              </select>
            </div>
          }
          <div class="field field--full">
            <label for="accion-cantidad">{{ esRenovacion() ? 'Meses a sumar' : 'Días a congelar' }}</label>
            <input
              id="accion-cantidad"
              type="number"
              min="1"
              [max]="esRenovacion() ? 120 : 365"
              step="1"
              formControlName="cantidad"
            />
            @if (form.controls.cantidad.touched && form.controls.cantidad.invalid) {
              <p class="field-error">
                Indica un número entero entre 1 y {{ esRenovacion() ? 120 : 365 }}.
              </p>
            }
          </div>
        </div>
        @if (nuevaFechaFin(); as fecha) {
          <p class="text-muted">Nuevo vencimiento: {{ formatDate(fecha) }}</p>
        }

        <div class="form-actions">
          <button class="button button--secondary" type="button" (click)="cerrar()" [disabled]="saving()">
            Cancelar
          </button>
          <button class="button button--primary" type="submit" [disabled]="saving()">
            {{ saving() ? 'Guardando...' : esRenovacion() ? 'Renovar' : 'Congelar' }}
          </button>
        </div>
      </form>
    </app-modal>
  `,
})
export class MembresiaAccionComponent {
  private readonly financial = inject(FinancialService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly toast = inject(ToastService);

  readonly accion = input<AccionMembresia | null>(null);
  readonly closed = output<void>();
  readonly saved = output<Membresia>();

  protected readonly tipos = TIPOS_MEMBRESIA;
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  private readonly cantidad = signal<number | null>(1);

  protected readonly form = this.formBuilder.nonNullable.group({
    tipo: ['mensual' as Membresia['tipo']],
    cantidad: [
      1 as number | null,
      [Validators.required, Validators.min(1), Validators.max(365), Validators.pattern(/^\d+$/)],
    ],
  });

  protected readonly esRenovacion = computed(() => this.accion()?.tipo === 'renovar');

  protected readonly subtitulo = computed(() => {
    const accion = this.accion();
    if (!accion) {
      return '';
    }
    const base = `${accion.membresia.cliente_detalle.nombre} · vence el ${formatDate(accion.membresia.fecha_fin)}`;
    return accion.tipo === 'congelar'
      ? `${base}. El vencimiento se corre los días congelados.`
      : base;
  });

  protected readonly nuevaFechaFin = computed(() => {
    const accion = this.accion();
    const cantidad = this.cantidad();
    if (!accion || !cantidad || cantidad < 1 || !Number.isInteger(cantidad)) {
      return null;
    }
    return accion.tipo === 'renovar'
      ? sumarMeses(accion.membresia.fecha_fin, cantidad)
      : sumarDias(accion.membresia.fecha_fin, cantidad);
  });

  protected readonly formatDate = formatDate;

  constructor() {
    this.form.controls.cantidad.valueChanges.subscribe((valor) => this.cantidad.set(valor));
    effect(() => {
      const accion = this.accion();
      if (!accion) {
        return;
      }
      this.formError.set(null);
      const tipo = this.tipos.find((item) => item.valor === accion.membresia.tipo);
      this.form.reset({
        tipo: accion.membresia.tipo,
        cantidad: accion.tipo === 'renovar' ? tipo?.meses || 1 : 7,
      });
    });
  }

  protected alCambiarTipo(): void {
    const tipo = this.tipos.find((item) => item.valor === this.form.controls.tipo.value);
    if (tipo?.meses) {
      this.form.controls.cantidad.setValue(tipo.meses);
    }
  }

  protected cerrar(): void {
    if (!this.saving()) this.closed.emit();
  }

  protected guardar(): void {
    const accion = this.accion();
    this.formError.set(null);
    const raw = this.form.getRawValue();
    const limite = accion?.tipo === 'renovar' ? 120 : 365;
    if (!accion || this.form.invalid || raw.cantidad === null || raw.cantidad > limite) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    const peticion =
      accion.tipo === 'renovar'
        ? this.financial.renovarMembresia(accion.membresia.id, raw.tipo, raw.cantidad)
        : this.financial.congelarMembresia(accion.membresia.id, raw.cantidad);
    peticion.subscribe({
      next: (membresia) => {
        this.saving.set(false);
        this.toast.success(accion.tipo === 'renovar' ? 'Membresía renovada' : 'Membresía congelada');
        this.saved.emit(membresia);
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(describirError(error, 'No se pudo completar la operación.'));
      },
    });
  }
}
