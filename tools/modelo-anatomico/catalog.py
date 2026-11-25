"""Catálogo de músculos detallados y reglas para mapear partes de BodyParts3D."""
import re

# code, etiqueta, grupo (código antiguo), vista principal, regex sobre el nombre inglés
CATALOGO = [
    # Cuello
    ('esternocleidomastoideo', 'Esternocleidomastoideo', 'cuello', 'front', r'sternocleidomastoid'),
    # Torso
    ('pectoral_mayor', 'Pectoral mayor', 'pecho', 'front', r'pectoralis major'),
    ('pectoral_menor', 'Pectoral menor', 'pecho', 'front', r'pectoralis minor'),
    ('recto_abdominal', 'Recto abdominal', 'abdomen', 'front', r'rectus abdominis'),
    ('oblicuo_externo', 'Oblicuo externo', 'oblicuos', 'front', r'external oblique'),
    ('oblicuo_interno', 'Oblicuo interno', 'oblicuos', 'front', r'internal oblique'),
    ('serrato_anterior', 'Serrato anterior', 'oblicuos', 'front', r'serratus anterior'),
    ('intercostales', 'Intercostales', 'pecho', 'front', r'(external|internal|innermost) intercostal'),
    # Espalda
    ('trapecio', 'Trapecio', 'trapecio', 'back', r'part of (left|right) trapezius'),
    ('dorsal_ancho', 'Dorsal ancho', 'dorsales', 'back', r'latissimus dorsi'),
    ('romboides', 'Romboides', 'dorsales', 'back', r'rhomboid'),
    ('redondo_mayor', 'Redondo mayor', 'dorsales', 'back', r'teres major'),
    ('redondo_menor', 'Redondo menor', 'dorsales', 'back', r'teres minor'),
    ('infraespinoso', 'Infraespinoso', 'dorsales', 'back', r'infraspinatus'),
    ('erectores_espinales', 'Erectores espinales', 'lumbares', 'back', r'iliocostalis|longissimus (thoracis|cervicis)|spinalis (thoracis|cervicis)'),
    # Hombros
    ('deltoides_anterior', 'Deltoides anterior', 'hombros', 'front', r'clavicular part of (left|right) deltoid'),
    ('deltoides_lateral', 'Deltoides lateral', 'hombros', 'both', r'acromial part of (left|right) deltoid'),
    ('deltoides_posterior', 'Deltoides posterior', 'hombros', 'back', r'spinal part of (left|right) deltoid'),
    # Brazos
    ('biceps_braquial', 'Bíceps braquial', 'biceps', 'front', r'biceps brachii'),
    ('braquial', 'Braquial', 'biceps', 'front', r'(left|right) brachialis$'),
    ('triceps_braquial', 'Tríceps braquial', 'triceps', 'back', r'triceps brachii|anconeus'),
    ('braquiorradial', 'Braquiorradial', 'antebrazos', 'front', r'brachioradialis'),
    ('flexores_antebrazo', 'Flexores del antebrazo', 'antebrazos', 'front',
     r'flexor carpi|flexor digitorum superficialis|flexor digitorum profundus|palmaris longus|pronator teres|flexor pollicis longus'),
    ('extensores_antebrazo', 'Extensores del antebrazo', 'antebrazos', 'back',
     r'extensor carpi|(left|right) extensor digitorum$|(left|right) extensor digiti minimi$|extensor indicis|extensor pollicis|abductor pollicis longus'),
    # Glúteos
    ('gluteo_mayor', 'Glúteo mayor', 'gluteos', 'back', r'gluteus maximus'),
    ('gluteo_medio', 'Glúteo medio', 'gluteos', 'back', r'gluteus medius'),
    ('gluteo_menor', 'Glúteo menor', 'gluteos', 'back', r'gluteus minimus'),
    # Piernas
    ('recto_femoral', 'Recto femoral', 'cuadriceps', 'front', r'rectus femoris'),
    ('vasto_lateral', 'Vasto lateral', 'cuadriceps', 'front', r'vastus lateralis'),
    ('vasto_medial', 'Vasto medial', 'cuadriceps', 'front', r'vastus medialis'),
    ('vasto_intermedio', 'Vasto intermedio', 'cuadriceps', 'front', r'vastus intermedius'),
    ('biceps_femoral', 'Bíceps femoral', 'isquiotibiales', 'back', r'biceps femoris'),
    ('semitendinoso', 'Semitendinoso', 'isquiotibiales', 'back', r'semitendinosus'),
    ('semimembranoso', 'Semimembranoso', 'isquiotibiales', 'back', r'semimembranosus'),
    ('aductores', 'Aductores', 'aductores', 'front', r'(left|right) adductor (longus|brevis|magnus|minimus)|(left|right) gracilis|(left|right) pectineus'),
    ('sartorio', 'Sartorio', 'cuadriceps', 'front', r'sartorius'),
    ('gastrocnemio', 'Gastrocnemio', 'pantorrillas', 'back', r'gastrocnemius'),
    ('soleo', 'Sóleo', 'pantorrillas', 'back', r'(left|right) soleus'),
    ('tibial_anterior', 'Tibial anterior', 'pantorrillas', 'front', r'tibialis anterior'),
]

REGLAS = [(c, re.compile(rx)) for c, _l, _g, _s, rx in CATALOGO]


def clasificar(nombre: str) -> str | None:
    for code, rx in REGLAS:
        if rx.search(nombre):
            return code
    return None


HUESO = re.compile(
    r'bone|rib$|phalan|vertebra|atlas$|axis$|sacrum|coccyx|clavicle|scapula|humerus|radius|ulna$|'
    r'scaphoid|lunate|triquetral|pisiform|trapezium|trapezoid|capitate|hamate|femur|tibia$|fibula$|'
    r'patella|talus|calcaneus$|cuneiform|cuboid|navicular|sesamoid|mandible|maxilla|manubrium|'
    r'body of sternum|xiphoid|cartilage|disk|concha|vomer|ethmoid|hip bone|nasal cartilages'
)


def es_hueso(nombre: str) -> bool:
    return bool(HUESO.search(nombre))
