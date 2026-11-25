import {
  ChangeDetectionStrategy,
  Component,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../../core/api/api-client.service';
import type { ClientProfile } from '../../../core/api/api.models';
import { ToastService } from '../../../core/ui/toast.service';
import { todayInput } from '../../../core/utils/format';
import { IconComponent } from '../../../shared/icon.component';
import { ModalComponent } from '../../../shared/modal.component';
import { Membresia } from '../financial.models';
import { FinancialService } from '../financial.service';
import { describirError, sumarDias, sumarMeses } from './form-utils';

interface TipoMembresia {
  valor: Membresia['tipo'];
  etiqueta: string;
  /** Meses de vigencia; `null` cuando la fecha de fin se define a mano. */
  meses: number | null;
}

export const TIPOS_MEMBRESIA: TipoMembresia[] = [
  { valor: 'mensual', etiqueta: 'Mensual', meses: 1 },
  { valor: 'trimestral', etiqueta: 'Trimestral', meses: 3 },
  { valor: 'semestral', etiqueta: 'Semestral', meses: 6 },
  { valor: 'anual', etiqueta: 'Anual', meses: 12 },
  { valor: 'visita', etiqueta: 'Visita única', meses: 0 },
  { valor: 'personalizada', etiqueta: 'Personalizada', meses: null },
];

@Component({
  selector: 'app-membresia-form',
  standalone: true,
  imports: [ReactiveFormsModule, IconComponent, ModalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-modal
      [open]="open()"
      title="Nueva membresía"
      subtitle="El estado se calcula solo a partir de las fechas."
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
          <div class="field field--full">
            <label for="membresia-cliente">Cliente</label>
            <select id="membresia-cliente" formControlName="cliente">
              <option [ngValue]="null">Selecciona un cliente</option>
              @for (cliente of clientes(); track cliente.usuario) {
                <option [ngValue]="cliente.usuario">
                  {{ cliente.usuario_detalle.nombre }} · {{ cliente.usuario_detalle.correo }}
                </option>
              }
            </select>
            @if (form.controls.cliente.touched && form.controls.cliente.invalid) {
              <p class="field-error">Selecciona el cliente.</p>
            }
          </div>
          <div class="field">
            <label for="membresia-tipo">Tipo</label>
            <select id="membresia-tipo" formControlName="tipo" (change)="alCambiarTipo()">
              @for (tipo of tipos; track tipo.valor) {
                <option [value]="tipo.valor">{{ tipo.etiqueta }}</option>
              }
            </select>
          </div>
          <div class="field">
            <label for="membresia-nombre">Nombre</label>
            <input id="membresia-nombre" formControlName="nombre" placeholder="Ej. Mensual estándar" />
            @if (form.controls.nombre.touched && form.controls.nombre.invalid) {
              <p class="field-error">El nombre es obligatorio.</p>
            }
          </div>
          <div class="field">
            <label for="membresia-inicio">Fecha de inicio</label>
            <input id="membresia-inicio" type="date" formControlName="fecha_inicio" (change)="recalcularFin()" />
            @if (form.controls.fecha_inicio.touched && form.controls.fecha_inicio.invalid) {
              <p class="field-error">La fecha de inicio es obligatoria.</p>
            }
          </div>
          <div class="field">
            <label for="membresia-fin">Fecha de fin</label>
            <input id="membresia-fin" type="date" formControlName="fecha_fin" />
            @if (form.controls.fecha_fin.touched && form.controls.fecha_fin.invalid) {
              <p class="field-error">La fecha de fin es obligatoria.</p>
            }
            @if (fechasInvertidas()) {
              <p class="field-error">No puede ser anterior a la fecha de inicio.</p>
            }
          </div>
          <div class="field">
            <label for="membresia-precio">Precio (COP)</label>
            <input id="membresia-precio" type="number" min="0" step="any" formControlName="precio" />
            @if (form.controls.precio.touched && form.controls.precio.invalid) {
              <p class="field-error">Indica el precio (cero o más).</p>
            }
          </div>
          <div class="field">
            <label class="checkbox" for="membresia-auto">
              <input id="membresia-auto" type="checkbox" formControlName="renovacion_automatica" />
              Renovación automática
            </label>
          </div>
          <div class="field field--full">
            <label for="membresia-observaciones">Observaciones</label>
            <textarea id="membresia-observaciones" formControlName="observaciones" rows="2"></textarea>
          </div>
        </div>

        <div class="form-actions">
          <button class="button button--secondary" type="button" (click)="cerrar()" [disabled]="saving()">
            Cancelar
          </button>
          <button class="button button--primary" type="submit" [disabled]="saving()">
            {{ saving() ? 'Guardando...' : 'Crear membresía' }}
          </button>
        </div>
      </form>
    </app-modal>
  `,
})
export class MembresiaFormComponent {
  private readonly api = inject(ApiClient);
  private readonly financial = inject(FinancialService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly toast = inject(ToastService);

  readonly open = input(false);
  readonly closed = output<void>();
  readonly saved = output<Membresia>();

  protected readonly tipos = TIPOS_MEMBRESIA;
  protected readonly clientes = signal<ClientProfile[]>([]);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly fechasInvertidas = signal(false);

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [null as number | null, [Validators.required]],
    tipo: ['mensual' as Membresia['tipo']],
    nombre: ['Membresía mensual', [Validators.required]],
    fecha_inicio: [todayInput(), [Validators.required]],
    fecha_fin: [sumarDias(sumarMeses(todayInput(), 1), -1), [Validators.required]],
    precio: [null as number | null, [Validators.required, Validators.min(0)]],
    renovacion_automatica: [false],
    observaciones: [''],
  });

  constructor() {
    effect(() => {
      if (this.open()) {
        this.preparar();
      }
    });
  }

  private preparar(): void {
    this.formError.set(null);
    this.fechasInvertidas.set(false);
    const hoy = todayInput();
    this.form.reset({
      cliente: null,
      tipo: 'mensual',
      nombre: 'Membresía mensual',
      fecha_inicio: hoy,
      fecha_fin: sumarDias(sumarMeses(hoy, 1), -1),
      precio: null,
      renovacion_automatica: false,
      observaciones: '',
    });
    this.api.getAll<ClientProfile>('clientes/', { is_active: true }).subscribe({
      next: (clientes) =>
        this.clientes.set(
          [...clientes].sort((a, b) =>
            a.usuario_detalle.nombre.localeCompare(b.usuario_detalle.nombre, 'es'),
          ),
        ),
      error: (error: unknown) =>
        this.formError.set(describirError(error, 'No se pudieron cargar los clientes.')),
    });
  }

  protected alCambiarTipo(): void {
    const tipo = this.tipos.find((item) => item.valor === this.form.controls.tipo.value);
    if (tipo) {
      this.form.controls.nombre.setValue(`Membresía ${tipo.etiqueta.toLowerCase()}`);
    }
    this.recalcularFin();
  }

  /** Propone la fecha de fin según el tipo; en "personalizada" no la toca. */
  protected recalcularFin(): void {
    const tipo = this.tipos.find((item) => item.valor === this.form.controls.tipo.value);
    const inicio = this.form.controls.fecha_inicio.value;
    if (!tipo || tipo.meses === null || !inicio) {
      return;
    }
    const fin = tipo.meses === 0 ? inicio : sumarDias(sumarMeses(inicio, tipo.meses), -1);
    this.form.controls.fecha_fin.setValue(fin);
  }

  protected cerrar(): void {
    if (!this.saving()) this.closed.emit();
  }

  protected guardar(): void {
    this.formError.set(null);
    const raw = this.form.getRawValue();
    const invertidas = Boolean(raw.fecha_inicio && raw.fecha_fin && raw.fecha_fin < raw.fecha_inicio);
    this.fechasInvertidas.set(invertidas);
    if (this.form.invalid || invertidas) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.financial
      .createMembresia({
        cliente: raw.cliente as number,
        tipo: raw.tipo,
        nombre: raw.nombre.trim(),
        fecha_inicio: raw.fecha_inicio,
        fecha_fin: raw.fecha_fin,
        precio: String(raw.precio),
        renovacion_automatica: raw.renovacion_automatica,
        observaciones: raw.observaciones.trim() || null,
      })
      .subscribe({
        next: (membresia) => {
          this.saving.set(false);
          this.toast.success('Membresía creada');
          this.saved.emit(membresia);
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.formError.set(describirError(error, 'No se pudo crear la membresía.'));
        },
      });
  }
}
