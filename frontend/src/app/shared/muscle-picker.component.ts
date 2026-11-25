import { ChangeDetectionStrategy, Component, computed, input, output, viewChild } from '@angular/core';

import {
  BODY_REGIONS,
  MUSCLES,
  expandMuscles,
  isGroupCode,
  muscleLabel,
  muscleRegion,
  toggleMuscle,
} from '../core/training/muscles';
import { Body3dComponent } from './body-3d.component';

/**
 * Selector de músculos: lista de músculos por zona del cuerpo y modelo
 * anatómico 3D sincronizados. Se marca un músculo tocándolo en cualquiera de
 * los dos. Los grupos antiguos (p. ej. "Pecho") que traigan datos guardados se
 * muestran también para poder quitarlos.
 */
@Component({
  selector: 'app-muscle-picker',
  standalone: true,
  imports: [Body3dComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="picker" [class.picker--compact]="compact()" [class.picker--list]="!showBody()">
      <div class="picker__list" role="group" [attr.aria-label]="label()">
        @for (region of regions(); track region.name) {
          <div class="region">
            <p class="region__title">{{ region.name }}</p>
            <div class="region__chips">
              @for (group of region.groups; track group) {
                <button type="button" class="chip chip--on chip--group" [attr.aria-pressed]="true" (click)="remove(group)"
                  title="Grupo guardado antes; tócalo para quitarlo">
                  <span class="chip__check" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                  </span>
                  {{ groupLabel(group) }} (grupo)
                </button>
              }
              @for (muscle of region.muscles; track muscle.code) {
                <button
                  type="button"
                  class="chip"
                  [class.chip--on]="lit().has(muscle.code)"
                  [attr.aria-pressed]="lit().has(muscle.code)"
                  (click)="toggle(muscle.code)"
                >
                  <span class="chip__check" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                  </span>
                  {{ muscle.label }}
                </button>
              }
            </div>
          </div>
        }
      </div>
      @if (showBody()) {
        <div class="picker__body">
          <app-body-3d [selected]="selected()" [interactive]="true" [height]="compact() ? 380 : 460" (toggled)="toggle($event)" />
        </div>
      }
    </div>
  `,
  styles: [
    `
      :host { display: block; container-type: inline-size; }
      .picker { display: grid; grid-template-columns: minmax(0, 1fr) minmax(240px, 320px); gap: 1rem; align-items: start;
        background: #0b0f14; border-radius: 1.25rem; padding: 1rem; }
      .picker__list { display: grid; gap: 0.75rem; align-content: start; max-height: 560px; overflow: auto; padding-right: 0.25rem; }
      .picker--list .picker__list { max-height: none; }
      .region__title { margin: 0 0 0.35rem; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em;
        text-transform: uppercase; color: #94a3b8; }
      .region__chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
      .chip { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.35rem 0.8rem 0.35rem 0.4rem;
        border-radius: 999px; border: 1.5px solid #3f4651; background: transparent; color: #e2e8f0;
        font: inherit; font-size: 0.8rem; cursor: pointer; transition: border-color 0.15s, color 0.15s; }
      .chip:hover { border-color: #64748b; }
      .chip__check { width: 1.15rem; height: 1.15rem; border-radius: 999px; border: 1.5px solid #64748b;
        display: inline-flex; align-items: center; justify-content: center; color: transparent; flex: none; }
      .chip__check svg { width: 0.75rem; height: 0.75rem; }
      .chip--on { border-color: #a3e635; color: #f7fee7; }
      .chip--on .chip__check { background: #a3e635; border-color: #a3e635; color: #0b0f14; }
      .chip--group { border-style: dashed; }
      .chip:focus-visible { outline: 2px solid #a3e635; outline-offset: 2px; }
      .picker--list { grid-template-columns: 1fr; }
      @container (max-width: 620px) { .picker { grid-template-columns: 1fr; } .picker__list { max-height: none; } }
    `,
  ],
})
export class MusclePickerComponent {
  readonly selected = input<readonly string[]>([]);
  readonly label = input('Músculos que se entrenan');
  readonly compact = input(false);
  /** Oculta el cuerpo cuando la página ya muestra uno al lado. */
  readonly showBody = input(true);
  readonly selectedChange = output<string[]>();

  private readonly body = viewChild(Body3dComponent);

  /** Músculos detallados encendidos (incluye los que vienen de un grupo). */
  protected readonly lit = computed(() => expandMuscles(this.selected()));

  protected readonly regions = computed(() => {
    const groups = this.selected().filter(isGroupCode);
    return BODY_REGIONS.map((name) => ({
      name,
      muscles: MUSCLES.filter((muscle) => muscle.region === name),
      groups: groups.filter((code) => muscleRegion(code) === name),
    }));
  });

  protected groupLabel(code: string): string {
    return muscleLabel(code);
  }

  protected toggle(code: string): void {
    const current = this.selected();
    const next = toggleMuscle(current, code);
    if (next.includes(code) && !current.includes(code)) this.body()?.showMuscle(code);
    this.selectedChange.emit(next);
  }

  protected remove(code: string): void {
    this.selectedChange.emit(this.selected().filter((item) => item !== code));
  }
}
