import { JsonPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { debounceTime, distinctUntilChanged } from 'rxjs';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { AuditEvent, PaginatedResponse } from '../../core/api/api.models';
import { RESOURCE_DEFINITIONS } from '../../core/rbac/permissions';
import { formatDateTime, humanize } from '../../core/utils/format';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-audit-page',
  standalone: true,
  imports: [
    JsonPipe,
    ReactiveFormsModule,
    IconComponent,
    PageHeaderComponent,
    PaginationComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './audit.page.html',
  styleUrl: './audit.page.css',
})
export class AuditPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly events = signal<AuditEvent[]>([]);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 25;
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly resources = RESOURCE_DEFINITIONS;

  protected readonly search = this.formBuilder.nonNullable.control('');
  protected readonly resourceFilter = this.formBuilder.nonNullable.control('');
  protected readonly actionFilter = this.formBuilder.nonNullable.control('');

  ngOnInit(): void {
    this.load();
    this.search.valueChanges
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.page.set(1);
        this.load();
      });
    this.resourceFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.page.set(1);
      this.load();
    });
    this.actionFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.page.set(1);
      this.load();
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .get<PaginatedResponse<AuditEvent>>('auditoria/', {
        page: this.page(),
        search: this.search.value.trim(),
        recurso: this.resourceFilter.value || null,
        accion: this.actionFilter.value || null,
      })
      .subscribe({
        next: (response) => {
          this.events.set(response.results);
          this.count.set(response.count);
          this.loading.set(false);
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.error.set(error instanceof ApiError ? error.message : 'No se pudo cargar la auditoría.');
        },
      });
  }

  protected changePage(page: number): void {
    this.page.set(page);
    this.load();
  }

  protected tone(accion: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
    if (accion.includes('crear')) return 'success';
    if (accion.includes('eliminar')) return 'danger';
    if (accion.includes('restaurar')) return 'info';
    if (accion.includes('permisos')) return 'warning';
    return 'neutral';
  }

  protected hasDetails(event: AuditEvent): boolean {
    return Object.keys(event.detalles ?? {}).length > 0;
  }

  protected formatDateTime = formatDateTime;
  protected humanize = humanize;
}
