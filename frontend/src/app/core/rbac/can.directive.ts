import {
  Directive,
  Input,
  TemplateRef,
  ViewContainerRef,
  effect,
  inject,
  signal,
} from '@angular/core';

import { AuthService } from '../auth/auth.service';

@Directive({
  selector: '[rbacCan]',
  standalone: true,
})
export class CanDirective {
  private readonly template = inject<TemplateRef<unknown>>(TemplateRef);
  private readonly viewContainer = inject(ViewContainerRef);
  private readonly auth = inject(AuthService);
  private readonly requirement = signal<string | string[] | null>(null);
  private readonly elseTemplate = signal<TemplateRef<unknown> | null>(null);
  private rendered: TemplateRef<unknown> | null = null;

  constructor() {
    effect(() => {
      const requirement = this.requirement();
      const allowed =
        requirement === null
          ? false
          : Array.isArray(requirement)
            ? this.auth.hasAny(requirement)
            : this.auth.hasPermission(requirement);
      this.render(allowed ? this.template : this.elseTemplate());
    });
  }

  @Input()
  set rbacCan(requirement: string | string[] | null | undefined) {
    this.requirement.set(requirement ?? null);
  }

  @Input()
  set rbacCanElse(template: TemplateRef<unknown> | null | undefined) {
    this.elseTemplate.set(template ?? null);
  }

  private render(template: TemplateRef<unknown> | null): void {
    if (template === this.rendered) {
      return;
    }
    this.viewContainer.clear();
    this.rendered = template;
    if (template) {
      this.viewContainer.createEmbeddedView(template);
    }
  }
}
