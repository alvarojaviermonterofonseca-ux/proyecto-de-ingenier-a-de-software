import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiError } from '../../core/api/api-error';
import { AuthService } from '../../core/auth/auth.service';
import { ThemeService } from '../../core/ui/theme.service';
import { ToastService } from '../../core/ui/toast.service';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './login.page.html',
  styleUrl: './login.page.css',
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly formBuilder = inject(FormBuilder);
  private readonly toast = inject(ToastService);
  protected readonly theme = inject(ThemeService);

  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly showPassword = signal(false);
  protected readonly expired = signal(this.route.snapshot.queryParamMap.get('expired') === '1');

  protected readonly form = this.formBuilder.nonNullable.group({
    correo: ['', [Validators.required, Validators.email]],
    contrasena: ['', [Validators.required]],
  });

  protected submit(): void {
    this.error.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.loading.set(true);
    const { correo, contrasena } = this.form.getRawValue();
    this.auth.login(correo.trim(), contrasena).subscribe({
      next: (user) => {
        this.loading.set(false);
        this.toast.success(`Bienvenido, ${user.nombre.split(' ')[0]}`);
        void this.router.navigateByUrl(this.returnUrl());
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(
          error instanceof ApiError
            ? error.message
            : 'No se pudo iniciar sesión. Verifica tu conexión.',
        );
      },
    });
  }

  protected togglePassword(): void {
    this.showPassword.update((visible) => !visible);
  }

  private returnUrl(): string {
    const value = this.route.snapshot.queryParamMap.get('returnUrl') ?? '/inicio';
    return value.startsWith('/') && !value.startsWith('//') ? value : '/inicio';
  }
}
