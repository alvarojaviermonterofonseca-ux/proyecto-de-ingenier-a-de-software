/**
 * Catálogo de músculos: mismos códigos que ``MUSCULOS`` en el backend.
 *
 * Hay dos niveles:
 * - músculos detallados (pectoral mayor, vasto lateral…), que corresponden a
 *   mallas del modelo anatómico 3D y son los que se marcan ahora;
 * - grupos musculares (pecho, cuádriceps…), los códigos de antes. Se siguen
 *   aceptando para no romper rutinas y ejercicios ya guardados: un grupo
 *   equivale a todos sus músculos detallados.
 */
export type MuscleSide = 'front' | 'back' | 'both';

export type BodyRegion = 'Cuello' | 'Torso' | 'Espalda' | 'Hombros' | 'Brazos' | 'Glúteos' | 'Piernas';

export const BODY_REGIONS: readonly BodyRegion[] = ['Torso', 'Espalda', 'Hombros', 'Brazos', 'Glúteos', 'Piernas', 'Cuello'];

export interface MuscleGroup {
  code: string;
  label: string;
  region: BodyRegion;
  side: MuscleSide;
}

export interface Muscle {
  code: string;
  label: string;
  /** Grupo muscular (código antiguo) al que pertenece. */
  group: string;
  region: BodyRegion;
  /** Lado donde se ve mejor, para girar el cuerpo al elegirlo. */
  side: MuscleSide;
  /** Queda debajo de otros músculos: conviene verlo aislado. */
  deep?: boolean;
}

export const MUSCLE_GROUPS: readonly MuscleGroup[] = [
  { code: 'cuello', label: 'Cuello', region: 'Cuello', side: 'front' },
  { code: 'trapecio', label: 'Trapecio', region: 'Espalda', side: 'back' },
  { code: 'hombros', label: 'Hombros', region: 'Hombros', side: 'both' },
  { code: 'pecho', label: 'Pecho', region: 'Torso', side: 'front' },
  { code: 'biceps', label: 'Bíceps', region: 'Brazos', side: 'front' },
  { code: 'triceps', label: 'Tríceps', region: 'Brazos', side: 'back' },
  { code: 'antebrazos', label: 'Antebrazos', region: 'Brazos', side: 'both' },
  { code: 'abdomen', label: 'Abdomen', region: 'Torso', side: 'front' },
  { code: 'oblicuos', label: 'Oblicuos', region: 'Torso', side: 'front' },
  { code: 'dorsales', label: 'Dorsales', region: 'Espalda', side: 'back' },
  { code: 'lumbares', label: 'Lumbares', region: 'Espalda', side: 'back' },
  { code: 'gluteos', label: 'Glúteos', region: 'Glúteos', side: 'back' },
  { code: 'cuadriceps', label: 'Cuádriceps', region: 'Piernas', side: 'front' },
  { code: 'isquiotibiales', label: 'Isquiotibiales', region: 'Piernas', side: 'back' },
  { code: 'aductores', label: 'Aductores', region: 'Piernas', side: 'front' },
  { code: 'pantorrillas', label: 'Pantorrillas', region: 'Piernas', side: 'back' },
];

export const MUSCLES: readonly Muscle[] = [
  // Torso
  { code: 'pectoral_mayor', label: 'Pectoral mayor', group: 'pecho', region: 'Torso', side: 'front' },
  { code: 'pectoral_menor', label: 'Pectoral menor', group: 'pecho', region: 'Torso', side: 'front', deep: true },
  { code: 'recto_abdominal', label: 'Recto abdominal', group: 'abdomen', region: 'Torso', side: 'front' },
  { code: 'oblicuo_externo', label: 'Oblicuo externo', group: 'oblicuos', region: 'Torso', side: 'front' },
  { code: 'oblicuo_interno', label: 'Oblicuo interno', group: 'oblicuos', region: 'Torso', side: 'front', deep: true },
  { code: 'serrato_anterior', label: 'Serrato anterior', group: 'oblicuos', region: 'Torso', side: 'front' },
  { code: 'intercostales', label: 'Intercostales', group: 'pecho', region: 'Torso', side: 'front', deep: true },
  // Espalda
  { code: 'trapecio', label: 'Trapecio', group: 'trapecio', region: 'Espalda', side: 'back' },
  { code: 'dorsal_ancho', label: 'Dorsal ancho', group: 'dorsales', region: 'Espalda', side: 'back' },
  { code: 'romboides', label: 'Romboides', group: 'dorsales', region: 'Espalda', side: 'back', deep: true },
  { code: 'redondo_mayor', label: 'Redondo mayor', group: 'dorsales', region: 'Espalda', side: 'back' },
  { code: 'redondo_menor', label: 'Redondo menor', group: 'dorsales', region: 'Espalda', side: 'back' },
  { code: 'infraespinoso', label: 'Infraespinoso', group: 'dorsales', region: 'Espalda', side: 'back' },
  { code: 'erectores_espinales', label: 'Erectores espinales', group: 'lumbares', region: 'Espalda', side: 'back', deep: true },
  // Hombros
  { code: 'deltoides_anterior', label: 'Deltoides anterior', group: 'hombros', region: 'Hombros', side: 'front' },
  { code: 'deltoides_lateral', label: 'Deltoides lateral', group: 'hombros', region: 'Hombros', side: 'both' },
  { code: 'deltoides_posterior', label: 'Deltoides posterior', group: 'hombros', region: 'Hombros', side: 'back' },
  // Brazos
  { code: 'biceps_braquial', label: 'Bíceps braquial', group: 'biceps', region: 'Brazos', side: 'front' },
  { code: 'braquial', label: 'Braquial', group: 'biceps', region: 'Brazos', side: 'front' },
  { code: 'triceps_braquial', label: 'Tríceps braquial', group: 'triceps', region: 'Brazos', side: 'back' },
  { code: 'braquiorradial', label: 'Braquiorradial', group: 'antebrazos', region: 'Brazos', side: 'front' },
  { code: 'flexores_antebrazo', label: 'Flexores del antebrazo', group: 'antebrazos', region: 'Brazos', side: 'front' },
  { code: 'extensores_antebrazo', label: 'Extensores del antebrazo', group: 'antebrazos', region: 'Brazos', side: 'back' },
  // Glúteos
  { code: 'gluteo_mayor', label: 'Glúteo mayor', group: 'gluteos', region: 'Glúteos', side: 'back' },
  { code: 'gluteo_medio', label: 'Glúteo medio', group: 'gluteos', region: 'Glúteos', side: 'back' },
  { code: 'gluteo_menor', label: 'Glúteo menor', group: 'gluteos', region: 'Glúteos', side: 'back', deep: true },
  // Piernas
  { code: 'recto_femoral', label: 'Recto femoral', group: 'cuadriceps', region: 'Piernas', side: 'front' },
  { code: 'vasto_lateral', label: 'Vasto lateral', group: 'cuadriceps', region: 'Piernas', side: 'front' },
  { code: 'vasto_medial', label: 'Vasto medial', group: 'cuadriceps', region: 'Piernas', side: 'front' },
  { code: 'vasto_intermedio', label: 'Vasto intermedio', group: 'cuadriceps', region: 'Piernas', side: 'front', deep: true },
  { code: 'sartorio', label: 'Sartorio', group: 'cuadriceps', region: 'Piernas', side: 'front' },
  { code: 'aductores', label: 'Aductores', group: 'aductores', region: 'Piernas', side: 'front' },
  { code: 'biceps_femoral', label: 'Bíceps femoral', group: 'isquiotibiales', region: 'Piernas', side: 'back' },
  { code: 'semitendinoso', label: 'Semitendinoso', group: 'isquiotibiales', region: 'Piernas', side: 'back' },
  { code: 'semimembranoso', label: 'Semimembranoso', group: 'isquiotibiales', region: 'Piernas', side: 'back' },
  { code: 'gastrocnemio', label: 'Gastrocnemio', group: 'pantorrillas', region: 'Piernas', side: 'back' },
  { code: 'soleo', label: 'Sóleo', group: 'pantorrillas', region: 'Piernas', side: 'back' },
  { code: 'tibial_anterior', label: 'Tibial anterior', group: 'pantorrillas', region: 'Piernas', side: 'front' },
  // Cuello
  { code: 'esternocleidomastoideo', label: 'Esternocleidomastoideo', group: 'cuello', region: 'Cuello', side: 'front' },
];

const MUSCLE_BY_CODE = new Map(MUSCLES.map((muscle) => [muscle.code, muscle]));
const GROUP_BY_CODE = new Map(MUSCLE_GROUPS.map((group) => [group.code, group]));
const GROUP_MEMBERS = new Map<string, string[]>(
  MUSCLE_GROUPS.map((group) => [group.code, MUSCLES.filter((muscle) => muscle.group === group.code).map((m) => m.code)]),
);

export function findMuscle(code: string): Muscle | undefined {
  return MUSCLE_BY_CODE.get(code);
}

export function findGroup(code: string): MuscleGroup | undefined {
  return GROUP_BY_CODE.get(code);
}

/** ``true`` si el código es un grupo antiguo y no un músculo detallado. */
export function isGroupCode(code: string): boolean {
  return GROUP_BY_CODE.has(code) && !MUSCLE_BY_CODE.has(code);
}

export function muscleLabel(code: string): string {
  return MUSCLE_BY_CODE.get(code)?.label ?? GROUP_BY_CODE.get(code)?.label ?? code;
}

export function muscleList(codes: readonly string[] | null | undefined): string {
  return (codes ?? []).map(muscleLabel).join(' · ');
}

export function muscleRegion(code: string): BodyRegion | undefined {
  return MUSCLE_BY_CODE.get(code)?.region ?? GROUP_BY_CODE.get(code)?.region;
}

export function muscleSide(code: string): MuscleSide {
  return MUSCLE_BY_CODE.get(code)?.side ?? GROUP_BY_CODE.get(code)?.side ?? 'front';
}

/** Músculos detallados que representa una lista (los grupos se expanden). */
export function expandMuscles(codes: readonly string[] | null | undefined): Set<string> {
  const out = new Set<string>();
  for (const code of codes ?? []) {
    if (MUSCLE_BY_CODE.has(code)) out.add(code);
    else for (const member of GROUP_MEMBERS.get(code) ?? []) out.add(member);
  }
  return out;
}

/** ``true`` si la lista trabaja el músculo o grupo ``filter``. */
export function matchesMuscle(codes: readonly string[] | null | undefined, filter: string): boolean {
  const wanted = expandMuscles([filter]);
  for (const code of expandMuscles(codes)) if (wanted.has(code)) return true;
  return false;
}

/**
 * Marca o desmarca un músculo detallado. Si estaba marcado solo a través de su
 * grupo antiguo, el grupo se cambia por el resto de sus músculos.
 */
export function toggleMuscle(selected: readonly string[], code: string): string[] {
  if (selected.includes(code)) return selected.filter((item) => item !== code);
  const muscle = MUSCLE_BY_CODE.get(code);
  if (muscle && selected.includes(muscle.group) && isGroupCode(muscle.group)) {
    const rest = (GROUP_MEMBERS.get(muscle.group) ?? []).filter((member) => member !== code && !selected.includes(member));
    return [...selected.filter((item) => item !== muscle.group), ...rest];
  }
  return [...selected, code];
}

export type WeekDayCode = 'lunes' | 'martes' | 'miercoles' | 'jueves' | 'viernes' | 'sabado' | 'domingo';

export const WEEK_DAYS: readonly { value: WeekDayCode; label: string; short: string }[] = [
  { value: 'lunes', label: 'Lunes', short: 'Lun' },
  { value: 'martes', label: 'Martes', short: 'Mar' },
  { value: 'miercoles', label: 'Miércoles', short: 'Mié' },
  { value: 'jueves', label: 'Jueves', short: 'Jue' },
  { value: 'viernes', label: 'Viernes', short: 'Vie' },
  { value: 'sabado', label: 'Sábado', short: 'Sáb' },
  { value: 'domingo', label: 'Domingo', short: 'Dom' },
];

/** Día de hoy en el formato de la API (la semana empieza el lunes). */
export function todayCode(): WeekDayCode {
  return WEEK_DAYS[(new Date().getDay() + 6) % 7].value;
}

/** Convierte una URL absoluta de la API en la ruta que usa ``ApiClient``. */
export function apiPath(url: string | null | undefined): string | null {
  if (!url) return null;
  const match = /\/api(?:\/v1)?\/(.+)$/.exec(url);
  return match ? match[1] : null;
}
