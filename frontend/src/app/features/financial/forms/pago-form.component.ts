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

import { ApiClient } from '../../../core/api/api-client.service';
import type { ClientProfile } from '../../../core/api/api.models';
import { ToastService } from '../../../core/ui/toast.service';
import { IconComponent } from '../../../shared/icon.component';
import { ModalComponent } from '../../../shared/modal.component';
import { Membresia, MetodoPago, Pago } from '../financial.models';
import { FinancialService } from '../financial.service';
import { describirError } from './form-utils';

const CONCEPTOS: Array<{ valor: Pago['concepto']; etiqueta: string }> = [
  { valor: 'membresia', etiqueta: 'Membresía' },
  { valor: 'renovacion', etiqueta: 'Renovación' },
  { valor: 'matricula', etiqueta: 'Matrícula' },
  { valor: 'entrenamiento_personal', etiqueta: 'Entrenamiento personal' },
  { valor: 'plan_alimentacion', etiqueta: 'Plan de alimentación' },
  { valor: 'producto', etiqueta: 'Producto' },
  { valor: 'otro', etiqueta: 'Otro' },
];

@Component({
  selector: 'app-pago-form',
  standalone: true,
  imports: [ReactiveFormsModule, IconComponent, ModalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-modal
      [open]="open()"
      title="Registrar ingreso"
      subtitle="El pago queda registrado a tu nombre, con la fecha y hora actuales."
      (closed)="cerrar()"
    >
      @if (formError()) {
        <div class="notice notice--error" role="alert">
          <app-icon name="alert" [size]="18" />
          <span>{{ formError() }}</span>
        </div>
      }
      @if (catalogosListos() && metodos().length === 0) {
        <div class="notice notice--error" role="alert">
          <app-icon name="alert" [size]="18" />
          <span>
            No hay métodos de pago. Créalos antes de registrar ingresos
            (comando <code>sembrar_datos_financiero</code>).
          </span>
        </div>
      }

      <form [formGroup]="form" (ngSubmit)="guardar()" novalidate>
        <div class="form-grid">
          <div class="field field--full">
            <label for="pago-cliente">Cliente</label>
            <select id="pago-cliente" formControlName="cliente" (change)="cargarMembresias()">
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
            <label for="pago-concepto">Concepto</label>
            <select id="pago-concepto" formControlName="concepto">
              @for (concepto of conceptos; track concepto.valor) {
                <option [value]="concepto.valor">{{ concepto.etiqueta }}</option>
              }
            </select>
          </div>
          <div class="field">
            <label for="pago-membresia">Membresía (opcional)</label>
            <select id="pago-membresia" formControlName="membresia">
              <option [ngValue]="null">Sin membresía asociada</option>
              @for (membresia of membresias(); track membresia.id) {
                <option [ngValue]="membresia.id">{{ membresia.nombre }}</option>
              }
            </select>
          </div>
          <div class="field">
            <label for="pago-valor">Valor (COP)</label>
            <input id="pago-valor" type="number" min="1" step="any" formControlName="valor" />
            @if (form.controls.valor.touched && form.controls.valor.invalid) {
              <p class="field-error">Indica un valor mayor que cero.</p>
            }
          </div>
          <div class="field">
            <label for="pago-metodo">Método de pago</label>
            <select id="pago-metodo" formControlName="metodo_pago">
              <option [ngValue]="null">Selecciona un método</option>
              @for (metodo of metodos(); track metodo.id) {
                <option [ngValue]="metodo.id">{{ metodo.nombre }}</option>
              }
            </select>
            @if (form.controls.metodo_pago.touched && form.controls.metodo_pago.invalid) {
              <p class="field-error">Selecciona el método de pago.</p>
            }
          </div>
          <div class="field">
            <label for="pago-referencia">
              Referencia{{ referenciaObligatoria() ? '' : ' (opcional)' }}
            </label>
            <input id="pago-referencia" formControlName="referencia" placeholder="N.º de comprobante" />
            @if (referenciaFaltante()) {
              <p class="field-error">Este método de pago exige una referencia.</p>
            }
          </div>
          <div class="field">
            <label for="pago-estado">Estado</label>
            <select id="pago-estado" formControlName="estado">
              <option value="completado">Completado</option>
              <option value="pendiente">Pendiente</option>
            </select>
          </div>
          <div class="field field--full">
            <label for="pago-notas">Notas</label>
            <textarea id="pago-notas" formControlName="notas" rows="2"></textarea>
          </div>
        </div>

        <div class="form-actions">
          <button class="button button--secondary" type="button" (click)="cerrar()" [disabled]="saving()">
            Cancelar
          </button>
          <button class="button button--primary" type="submit" [disabled]="saving()">
            {{ saving() ? 'Guardando...' : 'Registrar ingreso' }}
          </button>
        </div>
      </form>
    </app-modal>
  `,
})
export class PagoFormComponent {
  private readonly api = inject(ApiClient);
  private readonly financial = inject(FinancialService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly toast = inject(ToastService);

  readonly open = input(false);
  readonly closed = output<void>();
  readonly saved = output<Pago>();

  protected readonly conceptos = CONCEPTOS;
  protected readonly clientes = signal<ClientProfile[]>([]);
  protected readonly metodos = signal<MetodoPago[]>([]);
  protected readonly membresias = signal<Membresia[]>([]);
  protected readonly catalogosListos = signal(false);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  private readonly metodoElegido = signal<number | null>(null);
  private readonly intentoGuardar = signal(false);
  private readonly referencia = signal('');

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [null as number | null, [Validators.required]],
    concepto: ['membresia' as Pago['concepto']],
    membresia: [null as number | null],
    valor: [null as number | null, [Validators.required, Validators.min(0.01)]],
    metodo_pago: [null as number | null, [Validators.required]],
    referencia: [''],
    estado: ['completado' as Pago['estado']],
    notas: [''],
  });

  protected readonly referenciaObligatoria = computed(() => {
    const id = this.metodoElegido();
    return this.metodos().some((metodo) => metodo.id === id && metodo.requiere_referencia);
  });

  protected readonly referenciaFaltante = computed(
    () => this.intentoGuardar() && this.referenciaObligatoria() && !this.referencia().trim(),
  );

  constructor() {
    this.form.controls.metodo_pago.valueChanges.subscribe((id) => this.metodoElegido.set(id));
    this.form.controls.referencia.valueChanges.subscribe((valor) => this.referencia.set(valor));
    effect(() => {
      if (this.open()) {
        this.preparar();
      }
    });
  }

  private preparar(): void {
    this.formError.set(null);
    this.intentoGuardar.set(false);
    this.membresias.set([]);
    this.form.reset({
      cliente: null,
      concepto: 'membresia',
      membresia: null,
      valor: null,
      metodo_pago: null,
      referencia: '',
      estado: 'completado',
      notas: '',
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
    this.financial.getAllMetodosPago().subscribe({
      next: (metodos) => {
        this.metodos.set(metodos.filter((metodo) => metodo.is_active));
        this.catalogosListos.set(true);
      },
      error: (error: unknown) => {
        this.formError.set(describirError(error, 'No se pudieron cargar los métodos de pago.'));
        this.catalogosListos.set(true);
      },
    });
  }

  protected cargarMembresias(): void {
    const cliente = this.form.controls.cliente.value;
    this.form.controls.membresia.setValue(null);
    this.membresias.set([]);
    if (cliente === null) {
      return;
    }
    this.financial.getMembresias({ cliente, page_size: 100 }).subscribe({
      next: (respuesta) => this.membresias.set(respuesta.results),
    });
  }

  protected cerrar(): void {
    if (!this.saving()) this.closed.emit();
  }

  protected guardar(): void {
    this.formError.set(null);
    this.intentoGuardar.set(true);
    if (this.form.invalid || this.referenciaFaltante()) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    this.saving.set(true);
    this.financial
      .createPago({
        cliente: raw.cliente as number,
        concepto: raw.concepto,
        membresia: raw.membresia,
        valor: String(raw.valor),
        metodo_pago: raw.metodo_pago as number,
        referencia: raw.referencia.trim() || null,
        estado: raw.estado,
        notas: raw.notas.trim() || null,
      })
      .subscribe({
        next: (pago) => {
          this.saving.set(false);
          this.toast.success('Ingreso registrado');
          this.saved.emit(pago);
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.formError.set(describirError(error, 'No se pudo registrar el ingreso.'));
        },
      });
  }
}
