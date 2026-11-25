# Generar `frontend/public/models/anatomia-muscular.glb`

Fuente: BodyParts3D (CC BY-SA 2.1 JP), mallas STL del repositorio
https://github.com/Kevin-Mattheus-Moerman/BodyParts3D (`assets/BodyParts3D_data/stl`).

```bash
pip install trimesh fast-simplification numpy
# keep.txt: "<FMA id>\t<nombre inglés>" de las partes a usar (músculos, huesos, tendones)
python3 build.py <carpeta_stl> <parts_list_e.txt> keep.txt anatomia_raw.glb
npx gltfpack -i anatomia_raw.glb -o anatomia-muscular.glb -cc -kn -km -vp 14 -vn 10
```

`catalog.py` relaciona cada código de músculo de Gym Control Pro con las piezas
de BodyParts3D. Debe coincidir con `MUSCULOS` del backend y `MUSCLES` del frontend.
