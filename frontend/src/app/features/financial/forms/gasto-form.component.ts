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

import { ToastService } from '../../../core/ui/toast.service';
import { todayInput } from '../../../core/utils/format';
import { IconComponent } from '../../../shared/icon.component';
import { ModalComponent } from '../../../shared/modal.component';
import { CategoriaGasto, Gasto, MetodoPago } from '../financial.models';
import { FinancialService } from '../financial.service';
import { describirError } from './form-utils';

@Component({
  selector: 'app-gasto-form',
  standalone: true,
  imports: [ReactiveFormsModule, IconComponent, ModalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-modal
      [open]="open()"
      [title]="gasto() ? 'Editar gasto' : 'Nuevo gasto'"
      [subtitle]="gasto() ? 'Los cambios quedan en la auditoría.' : 'Queda registrado a tu nombre.'"
      (closed)="cerrar()"
    >
      @if (formError()) {
        <div class="notice notice--error" role="alert">
          <app-icon name="alert" [size]="18" />
          <span>{{ formError() }}</span>
        </div>
      }
      @if (catalogosListos() && (categorias().length === 0 || metodos().length === 0)) {
        <div class="notice notice--error" role="alert">
          <app-icon name="alert" [size]="18" />
          <span>
            Faltan categorías de gasto o métodos de pago. Créalos antes de registrar gastos
            (comando <code>sembrar_datos_financiero</code>).
          </span>
        </div>
      }

      <form [formGroup]="form" (ngSubmit)="guardar()" novalidate>
        <div class="form-grid">
          <div class="field field--full">
            <label for="gasto-descripcion">Descripción</label>
            <input id="gasto-descripcion" formControlName="descripcion" placeholder="Ej. Arriendo de noviembre" />
            @if (form.controls.descripcion.touched && form.controls.descripcion.invalid) {
              <p class="field-error">La descripción es obligatoria.</p>
            }
          </div>
          <div class="field">
            <label for="gasto-categoria">Categoría</label>
            <select id="gasto-categoria" formControlName="categoria">
              <option [ngValue]="null">Selecciona una categoría</option>
              @for (categoria of categorias(); track categoria.id) {
                <option [ngValue]="categoria.id">{{ categoria.nombre }}</option>
              }
            </select>
            @if (form.controls.categoria.touched && form.controls.categoria.invalid) {
              <p class="field-error">Selecciona la categoría.</p>
            }
          </div>
          <div class="field">
            <label for="gasto-valor">Valor (COP)</label>
            <input id="gasto-valor" type="number" min="1" step="any" formControlName="valor" />
            @if (form.controls.valor.touched && form.controls.valor.invalid) {
              <p class="field-error">Indica un valor mayor que cero.</p>
            }
          </div>
          <div class="field">
            <label for="gasto-fecha">Fecha</label>
            <input id="gasto-fecha" type="date" formControlName="fecha" />
            @if (form.controls.fecha.touched && form.controls.fecha.invalid) {
              <p class="field-error">La fecha es obligatoria.</p>
            }
          </div>
          <div class="field">
            <label for="gasto-metodo">Método de pago</label>
            <select id="gasto-metodo" formControlName="metodo_pago">
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
            <label for="gasto-referencia">Referencia</label>
            <input id="gasto-referencia" formControlName="referencia" placeholder="N.º de factura o comprobante" />
          </div>
          <div class="field">
            <label for="gasto-estado">Estado</label>
            <select id="gasto-estado" formControlName="estado">
              <option value="registrado">Registrado</option>
              <option value="aprobado">Aprobado</option>
              <option value="pagado">Pagado</option>
              @if (gasto()) {
                <option value="cancelado">Cancelado (anulado)</option>
              }
            </select>
          </div>
          <div class="field field--full">
            <label for="gasto-observaciones">Observaciones</label>
            <textarea id="gasto-observaciones" formControlName="observaciones" rows="2"></textarea>
          </div>
        </div>

        <div class="form-actions">
          <button class="button button--secondary" type="button" (click)="cerrar()" [disabled]="saving()">
            Cancelar
          </button>
          <button class="button button--primary" type="submit" [disabled]="saving()">
            {{ saving() ? 'Guardando...' : (gasto() ? 'Guardar cambios' : 'Registrar gasto') }}
          </button>
        </div>
      </form>
    </app-modal>
  `,
})
export class GastoFormComponent {
  private readonly financial = inject(FinancialService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly toast = inject(ToastService);

  readonly open = input(false);
  /** Gasto a editar; ``null`` abre el formulario de registro. */
  readonly gasto = input<Gasto | null>(null);
  readonly closed = output<void>();
  readonly saved = output<Gasto>();

  protected readonly categorias = signal<CategoriaGasto[]>([]);
  protected readonly metodos = signal<MetodoPago[]>([]);
  protected readonly catalogosListos = signal(false);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

  protected readonly form = this.formBuilder.nonNullable.group({
    descripcion: ['', [Validators.required]],
    categoria: [null as number | null, [Validators.required]],
    valor: [null as number | null, [Validators.required, Validators.min(0.01)]],
    fecha: [todayInput(), [Validators.required]],
    metodo_pago: [null as number | null, [Validators.required]],
    referencia: [''],
    estado: ['registrado' as Gasto['estado']],
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
    const actual = this.gasto();
    this.form.reset({
      descripcion: actual?.descripcion ?? '',
      categoria: actual?.categoria ?? null,
      valor: actual ? Number(actual.valor) : null,
      fecha: actual?.fecha ?? todayInput(),
      metodo_pago: actual?.metodo_pago ?? null,
      referencia: actual?.referencia ?? '',
      estado: actual?.estado ?? 'registrado',
      observaciones: actual?.observaciones ?? '',
    });
    let pendientes = 2;
    const listo = () => {
      pendientes -= 1;
      if (pendientes === 0) this.catalogosListos.set(true);
    };
    this.financial.getAllCategoriasGasto().subscribe({
      next: (categorias) => {
        const actual = this.gasto();
        this.categorias.set(
          categorias.filter((categoria) => categoria.is_active || categoria.id === actual?.categoria),
        );
        listo();
      },
      error: (error: unknown) => {
        this.formError.set(describirError(error, 'No se pudieron cargar las categorías.'));
        listo();
      },
    });
    this.financial.getAllMetodosPago().subscribe({
      next: (metodos) => {
        const actual = this.gasto();
        this.metodos.set(metodos.filter((metodo) => metodo.is_active || metodo.id === actual?.metodo_pago));
        listo();
      },
      error: (error: unknown) => {
        this.formError.set(describirError(error, 'No se pudieron cargar los métodos de pago.'));
        listo();
      },
    });
  }

  protected cerrar(): void {
    if (!this.saving()) this.closed.emit();
  }

  protected guardar(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const datos: Partial<Gasto> = {
      descripcion: raw.descripcion.trim(),
      categoria: raw.categoria as number,
      valor: String(raw.valor),
      fecha: raw.fecha,
      metodo_pago: raw.metodo_pago as number,
      referencia: raw.referencia.trim() || null,
      estado: raw.estado,
      observaciones: raw.observaciones.trim() || null,
    };
    const actual = this.gasto();
    const peticion = actual
      ? this.financial.updateGasto(actual.id, datos)
      : this.financial.createGasto(datos);
    this.saving.set(true);
    peticion.subscribe({
      next: (gasto) => {
        this.saving.set(false);
        this.toast.success(actual ? 'Gasto actualizado' : 'Gasto registrado');
        this.saved.emit(gasto);
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(
          describirError(error, actual ? 'No se pudo actualizar el gasto.' : 'No se pudo registrar el gasto.'),
        );
      },
    });
  }
}
