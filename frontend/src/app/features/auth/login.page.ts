import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiError } from '../../core/api/api-error';
import { AuthService } from '../../core/auth/auth.service';
import { ThemeService } from '../../core/ui/theme.service';
import { ToastService } from '../../core/ui/toast.service';
import { IconComponent } from '../../shared/icon.component';

type AuthMode = 'login' | 'registro';

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

  protected readonly mode = signal<AuthMode>('login');
  protected readonly registering = signal(false);
  protected readonly registerError = signal<string | null>(null);
  protected readonly showRegisterPassword = signal(false);

  protected readonly form = this.formBuilder.nonNullable.group({
    correo: ['', [Validators.required, Validators.email]],
    contrasena: ['', [Validators.required]],
  });

  private readonly passwordsMatch = (group: AbstractControl): ValidationErrors | null => {
    const contrasena = group.get('contrasena')?.value;
    const confirmar = group.get('confirmar')?.value;
    return contrasena === confirmar ? null : { passwordsMismatch: true };
  };

  protected readonly registerForm = this.formBuilder.nonNullable.group(
    {
      nombre: ['', [Validators.required, Validators.minLength(2)]],
      correo: ['', [Validators.required, Validators.email]],
      telefono: [''],
      gimnasio: ['', [Validators.maxLength(50)]],
      contrasena: ['', [Validators.required, Validators.minLength(8)]],
      confirmar: ['', [Validators.required]],
    },
    { validators: this.passwordsMatch },
  );

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

  protected submitRegister(): void {
    this.registerError.set(null);
    if (this.registerForm.invalid) {
      this.registerForm.markAllAsTouched();
      return;
    }
    this.registering.set(true);
    const { nombre, correo, telefono, gimnasio, contrasena } = this.registerForm.getRawValue();
    const codigoGimnasio = gimnasio.trim().toLowerCase();
    this.auth.register({
      nombre: nombre.trim(),
      correo: correo.trim(),
      contrasena,
      telefono: telefono.trim() || null,
      ...(codigoGimnasio ? { gimnasio: codigoGimnasio } : {}),
    }).subscribe({
      next: (user) => {
        this.registering.set(false);
        this.toast.success(`Cuenta creada. Bienvenido, ${user.nombre.split(' ')[0]}`);
        void this.router.navigateByUrl('/inicio');
      },
      error: (error: unknown) => {
        this.registering.set(false);
        this.registerError.set(this.registrationMessage(error));
      },
    });
  }

  protected openRegister(): void {
    this.error.set(null);
    this.registerError.set(null);
    this.mode.set('registro');
  }

  protected openLogin(): void {
    this.registerError.set(null);
    this.showRegisterPassword.set(false);
    this.registerForm.reset();
    this.mode.set('login');
  }

  protected togglePassword(): void {
    this.showPassword.update((visible) => !visible);
  }

  protected toggleRegisterPassword(): void {
    this.showRegisterPassword.update((visible) => !visible);
  }

  private registrationMessage(error: unknown): string {
    if (!(error instanceof ApiError)) {
      return 'No se pudo crear la cuenta. Verifica tu conexión.';
    }
    const details = Object.values(error.fieldErrors()).filter(Boolean);
    return details.length ? details.join(' ') : error.message;
  }

  private returnUrl(): string {
    const value = this.route.snapshot.queryParamMap.get('returnUrl') ?? '/inicio';
    return value.startsWith('/') && !value.startsWith('//') ? value : '/inicio';
  }
}
