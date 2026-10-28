import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

const ICONS: Record<string, readonly string[]> = {
  home: ['M3 10.5 12 3l9 7.5', 'M5 9.5V21h14V9.5', 'M9 21v-6h6v6'],
  users: [
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2',
    'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
    'M22 21v-2a4 4 0 0 0-3-3.87',
    'M16 3.13a4 4 0 0 1 0 7.75',
  ],
  user: ['M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2', 'M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8'],
  'user-plus': ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8', 'M19 8v6', 'M16 11h6'],
  'arrow-right': ['M5 12h14', 'm12 5 7 7-7 7'],
  shield: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10', 'm9 12 2 2 4-4'],
  audit: ['M9 3h6l1 3h3v15H5V6h3l1-3Z', 'M9 12h6', 'M9 16h4'],
  dumbbell: [
    'M6 7v10',
    'M18 7v10',
    'M3 9v6',
    'M21 9v6',
    'M6 12h12',
  ],
  calendar: ['M8 2v4', 'M16 2v4', 'M3 9h18', 'M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2Z'],
  clipboard: ['M9 4H7a2 2 0 0 0-2 2v14h14V6a2 2 0 0 0-2-2h-2', 'M9 4a3 3 0 0 1 6 0', 'M9 12h6', 'M9 16h4'],
  apple: ['M12 8c-4 0-6 3-6 6 0 4 3 7 6 7s6-3 6-7c0-3-2-6-6-6Z', 'M12 8c0-3 2-5 4-5', 'M9 4c1 1 2 1 3 0'],
  salad: ['M4 11h16', 'M5 11a7 7 0 0 0 14 0', 'M12 4v7', 'M8 5c1 1 2 1 3-1', 'M15 5c1 2 3 2 3 0'],
  camera: ['M4 7h3l2-3h6l2 3h3v12H4V7Z', 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8'],
  bell: ['M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9', 'M10 21h4'],
  history: ['M3 12a9 9 0 1 0 3-6.7L3 8', 'M3 3v5h5', 'M12 7v5l4 2'],
  logout: ['M9 21H5V3h4', 'M16 17l5-5-5-5', 'M21 12H9'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  close: ['M18 6 6 18', 'M6 6l12 12'],
  search: ['M21 21l-4.35-4.35', 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16'],
  plus: ['M12 5v14', 'M5 12h14'],
  edit: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z'],
  trash: ['M3 6h18', 'M8 6V4h8v2', 'M19 6l-1 15H6L5 6', 'M10 11v6', 'M14 11v6'],
  'chevron-left': ['m15 18-6-6 6-6'],
  'chevron-right': ['m9 18 6-6-6-6'],
  'chevron-down': ['m6 9 6 6 6-6'],
  check: ['m5 12 4 4L19 6'],
  alert: ['M12 9v4', 'M12 17h.01', 'M10.3 3.9 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z'],
  eye: ['M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6'],
  'eye-off': ['M3 3l18 18', 'M10.6 10.6a2 2 0 0 0 2.8 2.8', 'M9.9 5.2A10.6 10.6 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-2.1 2.9', 'M6.6 6.6A17.5 17.5 0 0 0 2 12s3.5 7 10 7a10.5 10.5 0 0 0 4.4-1'],
  upload: ['M12 16V4', 'm7 9 5-5 5 5', 'M4 20h16'],
  download: ['M12 4v12', 'm7 11 5 5 5-5', 'M4 20h16'],
  sun: ['M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10', 'M12 1v2', 'M12 21v2', 'M4.2 4.2l1.4 1.4', 'M18.4 18.4l1.4 1.4', 'M1 12h2', 'M21 12h2', 'M4.2 19.8l1.4-1.4', 'M18.4 5.6l1.4-1.4'],
  moon: ['M21 12.8A8.5 8.5 0 1 1 11.2 3 6.5 6.5 0 0 0 21 12.8Z'],
  lock: ['M5 11h14v10H5V11Z', 'M8 11V7a4 4 0 0 1 8 0v4'],
  mail: ['M3 5h18v14H3V5Z', 'm3 6 9 7 9-7'],
  phone: ['M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.9a2 2 0 0 1-.5 2.1L8 10a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.9.6 2.9.7a2 2 0 0 1 1.7 2Z'],
  filter: ['M4 5h16', 'M7 12h10', 'M10 19h4'],
  refresh: ['M21 12a9 9 0 0 1-15 6.7L3 16', 'M3 12a9 9 0 0 1 15-6.7L21 8', 'M3 21v-5h5', 'M21 3v5h-5'],
  'arrow-left': ['M19 12H5', 'm12 19-7-7 7-7'],
  clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20', 'M12 6v6l4 2'],
  activity: ['M3 12h4l3-8 4 16 3-8h4'],
  target: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20', 'M12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12', 'M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4'],
  file: ['M6 2h8l4 4v16H6V2Z', 'M14 2v5h5', 'M9 13h6', 'M9 17h5'],
  external: ['M14 3h7v7', 'M10 14 21 3', 'M21 14v7H3V3h7'],
  settings: ['M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7', 'M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2 3.4-.2-.1a1.7 1.7 0 0 0-1.9.3 1.7 1.7 0 0 0-.8 1.5V22h-4v-.2a1.7 1.7 0 0 0-.8-1.5 1.7 1.7 0 0 0-1.9-.3l-.2.1-2-3.4.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-.8H4v-4h.2a1.7 1.7 0 0 0 1.5-.8 1.7 1.7 0 0 0-.3-1.9l-.1-.1 2-3.4.2.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 .8-1.5V2h4v.2a1.7 1.7 0 0 0 .8 1.5 1.7 1.7 0 0 0 1.9-.3l.2-.1 2 3.4-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5.8h.2v4h-.2a1.7 1.7 0 0 0-1.5.8Z'],
  more: ['M5 12h.01', 'M12 12h.01', 'M19 12h.01'],
  sparkles: ['m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z', 'M19 17l.9 2.1L22 20l-2.1.9L19 23l-.9-2.1L16 20l2.1-.9L19 17Z'],
  scale: ['M12 3v18', 'M5 7h14', 'M5 7l-3 6h6L5 7Z', 'M19 7l-3 6h6l-3-6Z'],
  ruler: ['M3 17 17 3l4 4L7 21l-4-4Z', 'm7 13 2 2', 'm10 10 2 2', 'm13 7 2 2'],
};

export type IconName = keyof typeof ICONS;

@Component({
  selector: 'app-icon',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      xmlns="http://www.w3.org/2000/svg"
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      [attr.stroke-width]="strokeWidth()"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      @for (path of paths(); track path) {
        <path [attr.d]="path" />
      }
    </svg>
  `,
  styles: [':host { display: inline-flex; flex: none; }'],
})
export class IconComponent {
  readonly name = input.required<string>();
  readonly size = input(20);
  readonly strokeWidth = input(1.8);
  readonly paths = computed(() => ICONS[this.name()] ?? ICONS['alert']);
}
