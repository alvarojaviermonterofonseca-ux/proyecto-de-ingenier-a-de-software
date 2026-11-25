import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  NgZone,
  OnDestroy,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';

import type * as THREE_NS from 'three';
import type { OrbitControls as OrbitControlsType } from 'three/examples/jsm/controls/OrbitControls.js';

import { expandMuscles, findMuscle, muscleLabel, muscleSide } from '../core/training/muscles';

/*
 * Visor anatómico 3D (Three.js).
 *
 * Carga un modelo anatómico real (BodyParts3D, © Life Science Integrated
 * Database Center, CC BY-SA 2.1 JP) convertido a GLB: cada músculo del
 * catálogo es una malla con nombre ``M_<código>_<R|L|C>``; huesos, tendones y
 * el resto de músculos van como contexto (``X_*``). Los músculos marcados se
 * pintan en rojo; el resto conserva el aspecto de atlas (gris claro).
 *
 * Three.js se carga bajo demanda (import dinámico), así no pesa en el resto
 * de la aplicación.
 */

type Three = typeof THREE_NS;

interface AnatomyAsset {
  THREE: Three;
  OrbitControls: typeof OrbitControlsType;
  RoomEnvironment: typeof import('three/examples/jsm/environments/RoomEnvironment.js').RoomEnvironment;
  scene: THREE_NS.Group;
  acceleratedRaycast: THREE_NS.Mesh['raycast'];
}

export const ANATOMY_MODEL_URL = 'models/anatomia-muscular.glb';

let assetPromise: Promise<AnatomyAsset> | null = null;

/** Descarga Three.js y el modelo una sola vez para toda la aplicación. */
function loadAnatomy(): Promise<AnatomyAsset> {
  assetPromise ??= (async () => {
    const [THREE, gltf, meshopt, orbit, room, bvh] = await Promise.all([
      import('three'),
      import('three/examples/jsm/loaders/GLTFLoader.js'),
      import('three/examples/jsm/libs/meshopt_decoder.module.js'),
      import('three/examples/jsm/controls/OrbitControls.js'),
      import('three/examples/jsm/environments/RoomEnvironment.js'),
      import('three-mesh-bvh'),
    ]);
    const loader = new gltf.GLTFLoader();
    loader.setMeshoptDecoder(meshopt.MeshoptDecoder);
    const url = new URL(ANATOMY_MODEL_URL, document.baseURI).href;
    const result = await loader.loadAsync(url);
    result.scene.traverse((object) => {
      const mesh = object as THREE_NS.Mesh;
      if (!mesh.isMesh) return;
      // Árbol de volúmenes para que señalar un músculo sea instantáneo.
      (mesh.geometry as THREE_NS.BufferGeometry & { computeBoundsTree: () => void }).computeBoundsTree =
        bvh.computeBoundsTree as never;
      (mesh.geometry as unknown as { computeBoundsTree: () => void }).computeBoundsTree();
    });
    return {
      THREE,
      OrbitControls: orbit.OrbitControls,
      RoomEnvironment: room.RoomEnvironment,
      scene: result.scene,
      acceleratedRaycast: bvh.acceleratedRaycast as THREE_NS.Mesh['raycast'],
    };
  })();
  assetPromise.catch(() => (assetPromise = null));
  return assetPromise;
}

interface MeshInfo {
  /** Código del músculo del catálogo, o ``null`` si es contexto (hueso, tendón…). */
  code: string | null;
  side: 'R' | 'L' | 'C';
  kind: 'muscle' | 'other' | 'bone' | 'tendon';
}

const SIDE_LABEL = { R: ' derecho', L: ' izquierdo', C: '' } as const;
const RED = '#d32f2f';

@Component({
  selector: 'app-body-3d',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="body3d">
      <div class="body3d__stage" #stage [style.height.px]="height()">
        <canvas
          #canvas
          class="body3d__canvas"
          [class.is-interactive]="interactive()"
          role="img"
          [attr.aria-label]="ariaLabel()"
          tabindex="0"
          (pointerdown)="onPointerDown($event)"
          (pointerup)="onPointerUp($event)"
          (pointerleave)="onPointerLeave()"
          (keydown.arrowleft)="nudge(-0.4)"
          (keydown.arrowright)="nudge(0.4)"
        ></canvas>

        @if (status() === 'loading') {
          <div class="body3d__state">
            <span class="body3d__spinner" aria-hidden="true"></span>
            Cargando modelo anatómico… {{ progressText() }}
          </div>
        } @else if (status() === 'error') {
          <div class="body3d__state body3d__state--error">
            No se pudo cargar el modelo 3D.
            <button type="button" (click)="retry()">Reintentar</button>
          </div>
        } @else if (status() === 'unsupported') {
          <div class="body3d__state">Tu navegador no permite gráficos 3D. Los músculos marcados aparecen en la lista.</div>
        }

        @if (tooltip(); as tip) {
          <span class="body3d__tooltip" [class.is-on]="tip.selected">
            {{ tip.text }}{{ tip.selected ? ' · seleccionado' : '' }}
          </span>
        }

        <div class="body3d__zoom" aria-label="Zoom">
          <button type="button" (click)="zoom(0.8)" aria-label="Acercar">+</button>
          <button type="button" (click)="zoom(1.25)" aria-label="Alejar">−</button>
          <button type="button" (click)="resetView()" aria-label="Restablecer vista" title="Restablecer vista">⟲</button>
        </div>
      </div>

      <div class="body3d__controls">
        <button type="button" (click)="turnTo('front')" [class.is-active]="facing() === 'front'">Frente</button>
        <button type="button" (click)="turnTo('back')" [class.is-active]="facing() === 'back'">Espalda</button>
        <button type="button" (click)="toggleSpin()" [class.is-active]="spinning()" [attr.aria-pressed]="spinning()">
          {{ spinning() ? 'Detener' : 'Girar 360°' }}
        </button>
        <button
          type="button"
          (click)="isolated.set(!isolated())"
          [class.is-active]="isolated()"
          [attr.aria-pressed]="isolated()"
          [disabled]="!highlighted().size"
          title="Muestra solo los músculos seleccionados"
        >
          {{ isolated() ? 'Ver todo' : 'Ver aislado' }}
        </button>
      </div>
      <p class="body3d__hint">
        Arrastra para girar · rueda o pellizca para zoom{{ interactive() ? ' · toca un músculo para marcarlo' : ' · toca un músculo para ver su nombre' }}
      </p>
      <p class="body3d__credit">
        Modelo: <a href="https://lifesciencedb.jp/bp3d/" target="_blank" rel="noopener">BodyParts3D</a>, © 2008 Life Science
        Integrated Database Center (CC BY-SA 2.1 JP)
      </p>
    </div>
  `,
  styles: [
    `
      :host { display: block; }
      .body3d { position: relative; width: 100%; user-select: none; }
      .body3d__stage {
        position: relative; border-radius: 1.1rem; overflow: hidden;
        background: radial-gradient(circle at 50% 38%, #1c2129 0%, #0a0b0d 75%);
      }
      :host-context(html[data-theme='light']) .body3d__stage {
        background: radial-gradient(circle at 50% 40%, #ffffff 0%, #eceef1 55%, #d9dde3 100%);
      }
      .body3d__canvas { width: 100%; height: 100%; display: block; cursor: grab; touch-action: none; outline: none; }
      .body3d__canvas:active { cursor: grabbing; }
      .body3d__canvas:focus-visible { box-shadow: inset 0 0 0 3px rgba(163, 230, 53, 0.5); }
      .body3d__state {
        position: absolute; inset: 0; display: flex; flex-direction: column; gap: 0.6rem; align-items: center;
        justify-content: center; text-align: center; padding: 1rem; color: #94a3b8; font-size: 0.85rem;
      }
      .body3d__state button {
        border: 1px solid #64748b; background: transparent; color: inherit; border-radius: 999px;
        padding: 0.3rem 0.9rem; cursor: pointer; font: inherit;
      }
      .body3d__spinner {
        width: 1.6rem; height: 1.6rem; border-radius: 50%; border: 3px solid rgba(148, 163, 184, 0.3);
        border-top-color: #e2e8f0; animation: body3d-spin 0.9s linear infinite;
      }
      @keyframes body3d-spin { to { transform: rotate(360deg); } }
      .body3d__tooltip {
        position: absolute; top: 0.6rem; left: 50%; transform: translateX(-50%); max-width: calc(100% - 5.5rem);
        overflow: hidden; text-overflow: ellipsis; padding: 0.25rem 0.7rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600;
        background: rgba(15, 23, 42, 0.9); color: #f1f5f9; pointer-events: none; white-space: nowrap;
        border: 1px solid rgba(148, 163, 184, 0.3);
      }
      .body3d__tooltip.is-on { background: ${RED}; border-color: ${RED}; color: #fff; }
      .body3d__zoom {
        position: absolute; right: 0.6rem; top: 0.6rem; display: flex; flex-direction: column; gap: 0.3rem;
      }
      .body3d__zoom button {
        width: 2rem; height: 2rem; border-radius: 0.6rem; border: 1px solid rgba(148, 163, 184, 0.35);
        background: rgba(15, 23, 42, 0.7); color: #e2e8f0; font-size: 1rem; line-height: 1; cursor: pointer;
      }
      :host-context(html[data-theme='light']) .body3d__zoom button { background: rgba(255, 255, 255, 0.85); color: #0f172a; }
      .body3d__controls {
        display: flex; flex-wrap: wrap; justify-content: center; gap: 0.3rem; margin: 0.5rem auto 0; width: fit-content;
        max-width: 100%; background: rgba(15, 23, 42, 0.75); padding: 0.25rem; border-radius: 999px;
      }
      .body3d__controls button {
        border: 0; background: transparent; color: #cbd5e1; font: inherit; font-size: 0.75rem;
        padding: 0.3rem 0.75rem; border-radius: 999px; cursor: pointer;
      }
      .body3d__controls button:disabled { opacity: 0.4; cursor: default; }
      .body3d__controls button.is-active { background: #a3e635; color: #0f172a; font-weight: 600; }
      .body3d__hint { margin: 0.35rem 0 0; text-align: center; font-size: 0.7rem; color: var(--gc-muted, #94a3b8); }
      .body3d__credit { margin: 0.15rem 0 0; text-align: center; font-size: 0.6rem; color: var(--gc-muted, #94a3b8); opacity: 0.75; }
      .body3d__credit a { color: inherit; }
    `,
  ],
})
export class Body3dComponent implements AfterViewInit, OnDestroy {
  /** Músculos marcados (detallados o grupos antiguos); se pintan en rojo. */
  readonly selected = input<readonly string[]>([]);
  /** Si es ``true``, tocar un músculo emite ``toggled``. */
  readonly interactive = input(false);
  readonly height = input(420);
  readonly autoSpin = input(false);
  readonly toggled = output<string>();

  protected readonly status = signal<'loading' | 'ready' | 'error' | 'unsupported'>('loading');
  protected readonly progressText = signal('');
  protected readonly facing = signal<'front' | 'back' | null>('front');
  protected readonly spinning = signal(false);
  protected readonly isolated = signal(false);
  protected readonly tooltip = signal<{ text: string; selected: boolean } | null>(null);
  protected readonly highlighted = computed(() => expandMuscles(this.selected()));
  protected readonly ariaLabel = computed(() => {
    const names = [...this.highlighted()].map(muscleLabel);
    return names.length ? `Modelo anatómico 3D. Músculos marcados: ${names.join(', ')}` : 'Modelo anatómico 3D sin músculos marcados';
  });

  private readonly canvasRef = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private readonly stageRef = viewChild.required<ElementRef<HTMLDivElement>>('stage');
  private readonly zone = inject(NgZone);

  private THREE?: Three;
  private renderer?: THREE_NS.WebGLRenderer;
  private scene?: THREE_NS.Scene;
  private camera?: THREE_NS.PerspectiveCamera;
  private controls?: OrbitControlsType;
  private model?: THREE_NS.Object3D;
  private raycaster?: THREE_NS.Raycaster;
  private readonly info = new Map<THREE_NS.Object3D, MeshInfo>();
  private materials: Record<string, THREE_NS.MeshStandardMaterial> = {};
  private hoverCode: string | null = null;
  private frame = 0;
  private needsRender = false;
  private destroyed = false;
  private resizeObserver?: ResizeObserver;
  private turnTarget: number | null = null;
  private zoomTarget: number | null = null;
  private down: { x: number; y: number; t: number } | null = null;
  private lastMove: PointerEvent | null = null;
  private tooltipTimer = 0;
  private stickyUntil = 0;
  private readonly onMove = (event: PointerEvent) => {
    this.lastMove = event;
    this.requestRender();
  };

  constructor() {
    effect(() => {
      this.highlighted();
      this.isolated();
      this.applyMaterials();
    });
    effect(() => {
      if (!this.highlighted().size && this.isolated()) this.isolated.set(false);
    });
    effect(() => {
      const spin = this.autoSpin();
      if (spin) this.setSpin(true);
    });
  }

  ngAfterViewInit(): void {
    this.init();
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    cancelAnimationFrame(this.frame);
    clearTimeout(this.tooltipTimer);
    this.resizeObserver?.disconnect();
    this.canvasRef().nativeElement.removeEventListener('pointermove', this.onMove);
    this.controls?.dispose();
    Object.values(this.materials).forEach((material) => material.dispose());
    this.scene?.environment?.dispose();
    this.renderer?.dispose();
  }

  /** Gira el cuerpo hacia el lado donde mejor se ve ``code``. */
  showMuscle(code: string): void {
    const side = muscleSide(code);
    if (side === 'front' || side === 'back') this.turnTo(side);
  }

  protected retry(): void {
    this.status.set('loading');
    this.init();
  }

  private async init(): Promise<void> {
    const canvas = this.canvasRef().nativeElement;
    let asset: AnatomyAsset;
    try {
      asset = await loadAnatomy();
    } catch {
      if (!this.destroyed) this.status.set('error');
      return;
    }
    if (this.destroyed || this.renderer) return;
    const THREE = (this.THREE = asset.THREE);

    let renderer: THREE_NS.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
    } catch {
      this.status.set('unsupported');
      return;
    }
    this.renderer = renderer;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.setClearColor(0x000000, 0);

    const scene = (this.scene = new THREE.Scene());
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new asset.RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 0.25;
    pmrem.dispose();

    // Iluminación de atlas: luz principal arriba-izquierda, relleno suave y contraluz.
    const key = new THREE.DirectionalLight(0xffffff, 2.4);
    key.position.set(-1.6, 2.4, 2.6);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    fill.position.set(2, 0.5, 1.5);
    const rim = new THREE.DirectionalLight(0xffffff, 1.0);
    rim.position.set(-2, 1.5, -2.5);
    const back = new THREE.DirectionalLight(0xffffff, 1.2);
    back.position.set(1.6, 2.2, -2.6);
    scene.add(key, fill, rim, back, new THREE.HemisphereLight(0xffffff, 0x303030, 0.35));

    this.materials = {
      muscle: new THREE.MeshStandardMaterial({ color: '#c9c5be', roughness: 0.62, metalness: 0 }),
      other: new THREE.MeshStandardMaterial({ color: '#bcb7af', roughness: 0.66, metalness: 0 }),
      bone: new THREE.MeshStandardMaterial({ color: '#e6dfcf', roughness: 0.45, metalness: 0 }),
      tendon: new THREE.MeshStandardMaterial({ color: '#efece6', roughness: 0.35, metalness: 0 }),
      selected: new THREE.MeshStandardMaterial({ color: RED, roughness: 0.45, metalness: 0, emissive: '#5a0000' }),
      hover: new THREE.MeshStandardMaterial({ color: '#e3a3a3', roughness: 0.55, metalness: 0, emissive: '#2a0505' }),
      selectedHover: new THREE.MeshStandardMaterial({ color: '#ef4444', roughness: 0.4, metalness: 0, emissive: '#7f1010' }),
      ghost: new THREE.MeshStandardMaterial({
        color: '#9aa3ad', roughness: 0.7, transparent: true, opacity: 0.1, depthWrite: false,
      }),
    };

    const model = (this.model = asset.scene.clone(true));
    model.traverse((object) => {
      const mesh = object as THREE_NS.Mesh;
      if (!mesh.isMesh) return;
      mesh.raycast = asset.acceleratedRaycast;
      this.info.set(mesh, this.describe(mesh));
    });
    scene.add(model);

    const camera = (this.camera = new THREE.PerspectiveCamera(30, 1, 0.02, 30));
    const controls = (this.controls = new asset.OrbitControls(camera, canvas));
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.rotateSpeed = 0.8;
    controls.minDistance = 0.35;
    controls.maxDistance = 6.5;
    controls.screenSpacePanning = true;
    controls.autoRotateSpeed = 4;
    controls.addEventListener('change', () => {
      this.requestRender();
      this.updateFacing();
    });
    controls.addEventListener('start', () => {
      this.turnTarget = null;
      this.zoomTarget = null;
      this.hideTooltip();
    });

    this.raycaster = new THREE.Raycaster();
    (this.raycaster as THREE_NS.Raycaster & { firstHitOnly: boolean }).firstHitOnly = true;

    this.resetView();
    this.applyMaterials();
    this.status.set('ready');

    this.zone.runOutsideAngular(() => {
      canvas.addEventListener('pointermove', this.onMove);
      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(this.stageRef().nativeElement);
      this.resize();
    });
    if (this.autoSpin()) this.setSpin(true);
  }

  private describe(mesh: THREE_NS.Object3D): MeshInfo {
    const name = mesh.parent?.name || mesh.name;
    const match = /^M_(.+)_([RLC])$/.exec(name);
    if (match && findMuscle(match[1])) return { code: match[1], side: match[2] as MeshInfo['side'], kind: 'muscle' };
    if (name.includes('huesos')) return { code: null, side: 'C', kind: 'bone' };
    if (name.includes('tendones')) return { code: null, side: 'C', kind: 'tendon' };
    return { code: null, side: 'C', kind: 'other' };
  }

  private applyMaterials(): void {
    if (!this.model || !this.materials['muscle']) return;
    const selected = this.highlighted();
    const isolate = this.isolated() && selected.size > 0;
    for (const [mesh, meta] of this.info) {
      const target = mesh as THREE_NS.Mesh;
      const on = !!meta.code && selected.has(meta.code);
      const hover = !!meta.code && meta.code === this.hoverCode;
      let material: THREE_NS.Material;
      if (on) material = hover ? this.materials['selectedHover'] : this.materials['selected'];
      else if (isolate) material = this.materials['ghost'];
      else if (hover) material = this.materials['hover'];
      else material = this.materials[meta.kind === 'muscle' ? 'muscle' : meta.kind];
      target.material = material;
      target.renderOrder = isolate && !on ? 1 : 0;
    }
    this.requestRender();
  }

  private resize(): void {
    if (!this.renderer || !this.camera) return;
    const stage = this.stageRef().nativeElement;
    const width = Math.max(1, stage.clientWidth);
    const height = Math.max(1, stage.clientHeight);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  private requestRender(): void {
    if (this.needsRender || this.destroyed) return;
    this.needsRender = true;
    this.zone.runOutsideAngular(() => (this.frame = requestAnimationFrame(() => this.tick())));
  }

  private tick(): void {
    this.needsRender = false;
    if (!this.renderer || !this.scene || !this.camera || !this.controls) return;
    let animating = this.controls.autoRotate;

    if (this.turnTarget !== null) {
      const current = this.controls.getAzimuthalAngle();
      let delta = this.turnTarget - current;
      delta = Math.atan2(Math.sin(delta), Math.cos(delta));
      if (Math.abs(delta) < 0.003) this.turnTarget = null;
      else {
        this.rotateAzimuth(delta * 0.16);
        animating = true;
      }
    }
    if (this.zoomTarget !== null) {
      const offset = this.camera.position.clone().sub(this.controls.target);
      const distance = offset.length();
      const next = distance + (this.zoomTarget - distance) * 0.2;
      if (Math.abs(this.zoomTarget - distance) < 0.002) this.zoomTarget = null;
      else animating = true;
      this.camera.position.copy(this.controls.target).add(offset.setLength(next));
    }

    const moved = this.controls.update();
    this.renderer.render(this.scene, this.camera);
    if (this.lastMove) this.hover(this.lastMove);
    if (animating || moved) this.requestRender();
  }

  private rotateAzimuth(angle: number): void {
    if (!this.camera || !this.controls || !this.THREE) return;
    const offset = this.camera.position.clone().sub(this.controls.target);
    offset.applyAxisAngle(new this.THREE.Vector3(0, 1, 0), angle);
    this.camera.position.copy(this.controls.target).add(offset);
  }

  private updateFacing(): void {
    if (!this.controls) return;
    const azimuth = Math.abs(this.controls.getAzimuthalAngle());
    const next = azimuth < 0.35 ? 'front' : azimuth > Math.PI - 0.35 ? 'back' : null;
    if (next !== this.facing()) this.zone.run(() => this.facing.set(next));
  }

  protected turnTo(side: 'front' | 'back'): void {
    this.setSpin(false);
    this.turnTarget = side === 'front' ? 0 : Math.PI;
    this.requestRender();
  }

  protected nudge(angle: number): void {
    this.setSpin(false);
    this.rotateAzimuth(angle);
    this.controls?.update();
    this.requestRender();
  }

  protected toggleSpin(): void {
    this.setSpin(!this.spinning());
  }

  private setSpin(on: boolean): void {
    this.spinning.set(on);
    if (this.controls) this.controls.autoRotate = on;
    if (on) this.turnTarget = null;
    this.requestRender();
  }

  protected zoom(factor: number): void {
    if (!this.camera || !this.controls) return;
    const distance = this.camera.position.distanceTo(this.controls.target);
    this.zoomTarget = Math.min(this.controls.maxDistance, Math.max(this.controls.minDistance, distance * factor));
    this.requestRender();
  }

  protected resetView(): void {
    if (!this.camera || !this.controls) return;
    this.setSpin(false);
    this.turnTarget = null;
    this.zoomTarget = null;
    this.controls.target.set(0, 0.86, 0);
    const azimuth = this.facing() === 'back' ? Math.PI : 0;
    this.camera.position.set(Math.sin(azimuth) * 3.3, 0.92, Math.cos(azimuth) * 3.3);
    this.controls.update();
    this.requestRender();
  }

  // --- Señalar músculos ---------------------------------------------------

  private pick(event: { clientX: number; clientY: number }): THREE_NS.Intersection | null {
    if (!this.camera || !this.raycaster || !this.model || !this.THREE) return null;
    const rect = this.canvasRef().nativeElement.getBoundingClientRect();
    const pointer = new this.THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(pointer, this.camera);
    const isolate = this.isolated() && this.highlighted().size > 0;
    const targets = [...this.info.keys()].filter((mesh) => {
      if (!isolate) return true;
      const code = this.info.get(mesh)?.code;
      return !!code && this.highlighted().has(code);
    });
    const hits = this.raycaster.intersectObjects(targets, false);
    return hits[0] ?? null;
  }

  private hover(event: PointerEvent): void {
    this.lastMove = null;
    if (event.buttons || event.pointerType === 'touch') return;
    const hit = this.pick(event);
    const meta = hit ? this.info.get(hit.object) : undefined;
    const code = meta?.code ?? null;
    if (code !== this.hoverCode) {
      this.hoverCode = code;
      this.applyMaterials();
    }
    if (performance.now() < this.stickyUntil) return;
    if (meta?.code) this.showTooltip(meta, false);
    else if (this.tooltip()) this.hideTooltip();
    this.canvasRef().nativeElement.style.cursor = meta?.code && this.interactive() ? 'pointer' : '';
  }

  private showTooltip(meta: MeshInfo, sticky: boolean): void {
    if (!meta.code) return;
    const text = `${muscleLabel(meta.code)}${SIDE_LABEL[meta.side]}`;
    const selected = this.highlighted().has(meta.code);
    this.zone.run(() => this.tooltip.set({ text, selected }));
    clearTimeout(this.tooltipTimer);
    if (sticky) {
      this.stickyUntil = performance.now() + 2600;
      this.tooltipTimer = window.setTimeout(() => this.zone.run(() => this.tooltip.set(null)), 2600);
    }
  }

  private hideTooltip(): void {
    if (this.tooltip()) this.zone.run(() => this.tooltip.set(null));
  }

  protected onPointerDown(event: PointerEvent): void {
    this.down = { x: event.clientX, y: event.clientY, t: performance.now() };
    if (this.spinning()) this.setSpin(false);
  }

  protected onPointerUp(event: PointerEvent): void {
    const start = this.down;
    this.down = null;
    if (!start) return;
    const moved = Math.hypot(event.clientX - start.x, event.clientY - start.y);
    if (moved > 6 || performance.now() - start.t > 600) return;
    const hit = this.pick(event);
    const meta = hit ? this.info.get(hit.object) : undefined;
    if (!meta?.code) {
      this.hideTooltip();
      return;
    }
    if (this.interactive()) {
      const wasOn = this.highlighted().has(meta.code);
      this.toggled.emit(meta.code);
      this.showTooltip(meta, true);
      this.tooltip.update((tip) => (tip ? { ...tip, selected: !wasOn } : tip));
    } else {
      this.showTooltip(meta, true);
    }
  }

  protected onPointerLeave(): void {
    this.lastMove = null;
    if (this.hoverCode) {
      this.hoverCode = null;
      this.applyMaterials();
    }
    if (performance.now() >= this.stickyUntil) this.hideTooltip();
  }
}
