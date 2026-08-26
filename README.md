# San Isidro Club — Ball in Play / Secuencias Largas

Dashboard de performance (Ball in Play, secuencias largas y clasificación
Verde/Rojo por jugada) para el plantel de San Isidro Club, Top 14 URBA.

**El sitio se reconstruye y publica solo.** Subís una planilla `.csv` nueva a
`data/`, GitHub Actions la procesa y el sitio en GitHub Pages queda
actualizado en 1–2 minutos. No hay que tocar HTML ni JS a mano.

---

## Cómo está armado el proyecto

```
.
├── data/                          ← una planilla .csv por partido (acá va lo nuevo)
├── assets/logos/                  ← escudo de SIC + escudos de rivales
├── template/dashboard_template.html   ← el dashboard (HTML/CSS/JS), sin datos
├── scripts/build_dashboard.py     ← procesa data/ + assets/logos/ y arma el HTML final
├── requirements.txt
└── .github/workflows/build-and-deploy.yml   ← automatización (GitHub Actions)
```

Cuando corre, `build_dashboard.py`:
1. Lee todos los `.csv` de `data/` (mismo formato que las planillas originales:
   Session Start Date, Event, Session Name, Session Start, Session End,
   Tag Description, Tag Notes, Tag Start, Tag End, Tag Duration (secs),
   Partido, Resultado, Rueda, Etapa).
2. Calcula todo lo que ves en el dashboard: Ball in Play por partido,
   secuencias >60s, clasificación Verde/Rojo por jugada (desde la columna
   *Tag Notes*), KPIs, correlaciones, distribución de duración, etc.
3. Toma los escudos de `assets/logos/`, los reduce a miniatura y los
   incrusta como base64 (así el sitio no depende de imágenes externas).
4. Inyecta todo eso en `template/dashboard_template.html` y escribe el
   resultado en `dist/index.html`.
5. GitHub Actions publica `dist/` en GitHub Pages.

`dist/` **no se versiona** (está en `.gitignore`): se genera de cero en cada
build, así el repo se mantiene liviano y `data/`/`assets/` son siempre la
única fuente de verdad.

---

## Puesta en marcha (una sola vez)

### 1. Crear el repositorio

- En GitHub: **New repository** → nombre sugerido `sic-ball-in-play-dashboard` → **Public**
  (GitHub Pages gratuito requiere repo público, salvo que tengas plan con Pages privado)
- No hace falta agregar README/gitignore desde la web, ya vienen en este proyecto

### 2. Subir este proyecto

Sin usar terminal (más simple para empezar):
- En el repo vacío → **uploading an existing file**
- Arrastrá **todo** el contenido de esta carpeta (respetando la estructura:
  `data/`, `assets/`, `template/`, `scripts/`, `.github/`, `requirements.txt`,
  `.gitignore`, `README.md`)
- Commit directo a `main`

O con terminal:
```bash
cd sic-ball-in-play-dashboard   # esta carpeta
git init
git add .
git commit -m "Proyecto inicial del dashboard"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/sic-ball-in-play-dashboard.git
git push -u origin main
```

### 3. Activar GitHub Pages con "GitHub Actions" como origen

- **Settings** → **Pages** (menú izquierdo)
- En "Build and deployment" → **Source: GitHub Actions** (⚠️ no "Deploy from a branch")
- No hace falta guardar nada más — el workflow ya está en `.github/workflows/`

### 4. Primer build

- Andá a la pestaña **Actions** del repo
- Deberías ver el workflow **"Build and deploy dashboard"** corriendo (se dispara
  solo con el push del paso 2). Si no arrancó, abrilo y usá **Run workflow**
- Cuando termine (1–2 min, ícono verde ✓), el sitio queda publicado en:
  `https://TU_USUARIO.github.io/sic-ball-in-play-dashboard/`

---

## Uso día a día: agregar un partido nuevo

1. Exportá la planilla del partido en el mismo formato de siempre (columnas
   Session Start Date, Tag Description, Tag Notes, Tag Start, Tag End,
   Tag Duration (secs), Partido, Resultado, Rueda, Etapa, etc.)
2. Subila a la carpeta `data/` del repo (drag & drop en GitHub web, o
   `git add data/TOP_14_2026_Fecha_20.csv && git commit -m "Fecha 20" && git push`)
3. Listo. El push dispara el workflow automáticamente, reconstruye el
   dashboard con el partido nuevo incluido, y en 1–2 minutos el sitio está
   actualizado — sin tocar nada más.

No hace falta que el nombre del archivo sea exactamente `Fecha_N.csv`: el
número de fecha se toma del campo **Session Name** dentro de la planilla
(ej. "Fecha 20"). El nombre del archivo es libre, pero es buena práctica
mantenerlo descriptivo.

## Agregar el escudo de un rival nuevo

1. Subí la imagen (`.png` o `.jpg`, fondo transparente si es posible) a `assets/logos/`
2. Nombrá el archivo con el mismo nombre que aparece en la columna **Partido**
   de la planilla (sin el " 2"/" 3" de segundos equipos). Los nombres ya
   usados son:

   | Partido en la planilla | Archivo esperado |
   |---|---|
   | Newman / Newman 2 | `Newman.png` |
   | Alumni / Alumni 2 | `Alumni.png` |
   | LPRC | `La_Plata.png` (o .jpg) |
   | LMRC / LMRC 2 | `Los_Matreros.png` |
   | Los Tilos | `Los_Tilos.png` (o .jpg) |
   | CUBA | `CUBA.png` |
   | BA | `BA.png` |
   | Champagnat / Champagnat 2 | `Champagnat.png` (o .jpg) |
   | CASI | `CASI.png` |
   | Hindu / Hindu 2 | `Hindu.png` |
   | Plaza | `Plaza.png` |
   | CRBV | `CRBV.png` (o .jpg) |
   | BAC / BAC 2 | `BAC.png` |
   | (San Isidro Club, header) | `SIC.png` |

   Si aparece un rival nuevo que no está en esta lista, agregá también una
   entrada en el diccionario `CLUB_KEY_MAP` al principio de
   `scripts/build_dashboard.py` mapeando el nombre exacto de la columna
   *Partido* al nombre de archivo que subiste.
3. Commit + push. El próximo build ya lo incluye. Si no subís logo para un
   club, el dashboard simplemente no muestra su escudo (no rompe nada).

---

## Probarlo en tu computadora antes de subir (opcional)

```bash
pip install -r requirements.txt
python scripts/build_dashboard.py
# abrí dist/index.html en el navegador
```

Esto es útil para revisar una planilla nueva o un logo antes de hacer push.

---

## El botón "Actualizar datos" dentro del dashboard

El dashboard también tiene un botón que permite cargar `.csv` sueltos desde
el navegador para una previsualización rápida. Esa carga es **solo local, en
la sesión de quien lo usa** — no modifica el repo ni el sitio publicado. Para
que un partido quede visible para todos de forma permanente, tiene que
subirse a `data/` siguiendo los pasos de arriba.

---

## Notas de datos (heredadas del análisis original)

- La duración de cada secuencia se toma de la columna **"Tag Duration (secs)"**
  (con Tag End − Tag Start solo como respaldo si esa celda está vacía). En
  algunas planillas hay timestamps de Start/End superpuestos entre filas
  consecutivas; calcular por diferencia en esos casos infla el Ball in Play,
  por eso se prioriza la columna de duración.
- La clasificación Verde/Rojo por jugada sale de la columna **Tag Notes**
  (ej. "Verde - Penal", "Rojo - Try"). Las secuencias sin esa etiqueta se
  muestran como "Sin clasificar", nunca se fuerza una categoría.
- La tipografía "Mark Pro" no está disponible en CDNs públicos por ser
  comercial; el dashboard usa Manrope + Inter como reemplazo visualmente
  cercano. Si conseguís los archivos `.woff2` con licencia, se pueden
  incorporar vía `@font-face` en el template.
