import { ChangeDetectionStrategy, Component } from '@angular/core';

import { environment } from '../../../environments/environment';
import { IconComponent } from '../../shared/icon.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-andromeda',
  standalone: true,
  imports: [IconComponent, PageHeaderComponent, StatusBadgeComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './andromeda.page.html',
  styleUrl: './andromeda.page.css',
})
export class AndromedaPage {
  protected readonly config = environment.andromeda;
  protected readonly available = this.config.apkUrl.trim().length > 0;

  protected readonly version = this.config.version || 'Sin publicar';
  protected readonly size = this.config.sizeMb > 0 ? `${this.config.sizeMb} MB` : '—';
  protected readonly updatedAt = this.config.updatedAt || '—';
  protected readonly minAndroid = `Android ${this.config.minAndroid} o superior`;
}
