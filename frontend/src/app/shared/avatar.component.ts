import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { initials } from '../core/utils/format';

@Component({
  selector: 'app-avatar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="avatar" [style.width.px]="size()" [style.height.px]="size()">{{ text() }}</span>`,
  styles: [
    `
      .avatar {
        display: inline-grid;
        place-items: center;
        flex: none;
        border-radius: 50%;
        color: #eaffd0;
        background: linear-gradient(145deg, #1b6b47, #0e3d29);
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.02em;
      }
    `,
  ],
})
export class AvatarComponent {
  readonly name = input('');
  readonly size = input(38);
  readonly text = computed(() => initials(this.name()));
}
