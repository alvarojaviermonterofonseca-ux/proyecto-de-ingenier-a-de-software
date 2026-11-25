"""Convierte las mallas STL de BodyParts3D en un GLB optimizado para la web.

Uso: python3 -I build.py <carpeta_stl> <parts_list_e.txt> <keep.txt> <salida.glb>

- Cada músculo del catálogo queda como una malla propia por lado:
  ``M_<codigo>_<R|L|C>`` (por ejemplo ``M_pectoral_mayor_R``).
- El resto de músculos va junto en ``X_musculos``, los huesos en ``X_huesos``
  y tendones/cintillas en ``X_tendones`` (contexto anatómico, no seleccionable).
- Unidades: metros; eje Y hacia arriba; la cara anterior mira a +Z.
"""
import sys, re, os, json, math
from collections import defaultdict

import numpy as np
import trimesh
import fast_simplification

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

stl_dir, parts_file, keep_file, out = sys.argv[1:5]
BUDGET = {'M': 260_000, 'X_musculos': 120_000, 'X_huesos': 120_000, 'X_tendones': 6_000}
EXCLUIR = re.compile(r'hair|eyebrow|^skin$|pineal|geniculate|testis|prostate|taenia|fossa|gingiva|ear$|tooth|levator ani|pubococcygeus|puborectalis|iliococcygeus|coccygeus')
TENDON = re.compile(r'tendon|iliotibial tract|plantar ligament')

partes = [l.rstrip('\n').split('\t') for l in open(keep_file) if l.strip()]

def lado(nombre):
    if re.search(r'\bright\b', nombre):
        return 'R'
    if re.search(r'\bleft\b', nombre):
        return 'L'
    return 'C'

items = []  # (grupo, fma, nombre, mesh)
for fma, nombre in partes:
    if EXCLUIR.search(nombre):
        continue
    path = os.path.join(stl_dir, f'{fma}.stl')
    if not os.path.exists(path):
        print('falta', fma, nombre)
        continue
    code = catalog.clasificar(nombre)
    if code:
        grupo = f'M_{code}_{lado(nombre)}'
        clase = 'M'
    elif TENDON.search(nombre):
        grupo = clase = 'X_tendones'
    elif catalog.es_hueso(nombre):
        grupo = clase = 'X_huesos'
    else:
        grupo = clase = 'X_musculos'
    m = trimesh.load(path, force='mesh')
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.remove_unreferenced_vertices()
    items.append((grupo, clase, fma, nombre, m))

# En BodyParts3D los oblicuos incluyen su aponeurosis, que tapa por delante
# al recto abdominal. Se recorta la parte que cae sobre la proyección frontal
# del recto (del mismo lado) para que el recto quede visible y seleccionable.
def huella(m, celda=4.0):
    occ = set()
    for x, z in np.floor(m.vertices[:, [0, 2]] / celda).astype(int):
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                occ.add((x + dx, z + dz))
    return occ, celda

recto = {lado(n): m for g, c, f, n, m in items if 'rectus abdominis' in n}
huellas = {k: huella(v) for k, v in recto.items()}
for idx, (g, c, f, n, m) in enumerate(items):
    if re.search(r'(external|internal) oblique', n):
        occ, celda = huellas[lado(n)]
        cen = np.floor(m.triangles_center[:, [0, 2]] / celda).astype(int)
        quitar = np.array([(a, b) in occ for a, b in cen])
        frente = m.triangles_center[:, 1] < recto[lado(n)].centroid[1] + 25
        keep = ~(quitar & frente)
        m.update_faces(keep)
        m.remove_unreferenced_vertices()
        print('recorte', n, int((~keep).sum()), 'caras')

# Reparto de triángulos proporcional al área (con exponente < 1 para que las
# piezas pequeñas no queden demasiado toscas).
areas = defaultdict(float)
for g, c, f, n, m in items:
    areas[c] += m.area ** 0.8

# Orientación: BodyParts3D usa mm, Z arriba; la cara anterior está hacia -Y.
R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64)  # (x,y,z)->(x,z,-y)

grupos = defaultdict(list)
total = 0
for g, c, f, n, m in items:
    objetivo = max(120, int(BUDGET[c] * (m.area ** 0.8) / areas[c]))
    v, fa = m.vertices, m.faces
    if len(fa) > objetivo:
        ratio = 1 - objetivo / len(fa)
        v, fa = fast_simplification.simplify(v.astype(np.float32), fa.astype(np.int32), target_reduction=ratio)
    mm = trimesh.Trimesh(vertices=np.asarray(v, dtype=np.float64) @ R.T / 1000.0, faces=fa, process=True)
    mm.update_faces(mm.nondegenerate_faces())
    total += len(mm.faces)
    grupos[g].append(mm)
    print(f'{g:34s} {n[:48]:48s} {len(m.faces):7d} -> {len(mm.faces):6d}')

# Centrar: pies en y=0, eje del cuerpo en x=z=0.
todo = trimesh.util.concatenate([x for lst in grupos.values() for x in lst])
lo, hi = todo.bounds
centro = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])

escena = trimesh.Scene()
for g in sorted(grupos):
    malla = trimesh.util.concatenate(grupos[g])
    malla.apply_translation(-centro)
    malla.merge_vertices(merge_tex=True, merge_norm=True)
    _ = malla.vertex_normals
    malla.visual = trimesh.visual.ColorVisuals(malla)  # sin color por vértice
    escena.add_geometry(malla, node_name=g, geom_name=g)

escena.export(out, include_normals=True)
print('triangulos', total, 'mallas', len(grupos), 'altura', hi[1] - lo[1], 'MB', os.path.getsize(out) / 1e6)
json.dump(sorted(grupos), open(out + '.nodes.json', 'w'), indent=1)
