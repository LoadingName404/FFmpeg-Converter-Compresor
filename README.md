# Discord Video Compressor

Herramienta personal para comprimir y convertir videos antes de enviarlos por Discord.
No está pensada para uso público — la comparto por si alguien la quiere descargar y adaptar a su setup.

## Por qué existe

Saco clips de Steam seguido y siempre terminaba corriendo comandos de ffmpeg a mano para comprimir al límite de Discord:

- **10 MB** en servidores normales
- **50 MB** con Nitro básico
- **100 MB** en servidores mejorados
- **500 MB** con Nitro completo

Hacer eso a mano cada vez era tedioso, así que hice este automatizador con UI en el navegador.

El modo **Convertir** lo agregué por la cámara — tengo una Sony HandyCam DCR-SX45 del 2011 que graba en formatos legacy que Discord ni siquiera puede previsualizar. El modo convierte esos videos a MP4 moderno.

## Los perfiles de equipo

Cada máquina tiene su propio archivo JSON en la carpeta [`profiles/`](profiles/). Al arrancar, el servidor los carga automáticamente. Para agregar un PC nuevo, creá un archivo nuevo en esa carpeta siguiendo el mismo formato:

```json
{
  "id": "mi-pc",
  "name": "Mi PC",
  "icon": "🖥️",
  "sub": "Ryzen 7 5800X · RTX 3060",
  "os": "windows",
  "cpu": "Ryzen 7 5800X (8C/16T)",
  "hwEncoders": ["h264_nvenc", "hevc_nvenc"],
  "swEncoders": ["libx264", "libx265"],
  "threads": 16
}
```

Los valores de `hwEncoders` y `swEncoders` tienen que coincidir con los IDs de encoders definidos en `index.html`.

| Perfil | Specs |
|---|---|
| Desktop | i5-10400F · GT 1030 · 16 GB · Windows 10 (CPU encoding, NVENC no disponible en esta GPU) |
| Laptop | ASUS VivoBook 14 · Ryzen 5 7520U · Radeon integrado · 16 GB · Windows 11 |
| ThinkCentre | i5-8400T · iGPU Intel (QSV) · 16 GB · Ubuntu Server |

## Características

- **Modo Comprimir** — calcula el bitrate exacto para que el video entre en el límite de tamaño configurado, con encoding de dos pasadas para máxima precisión
- **Modo Convertir** — convierte video legacy (HandyCam, DVD, VHS capturado) a MP4 con calidad constante (CRF)
- **Encoders de hardware** — NVENC (Nvidia), AMF (AMD), Quick Sync (Intel) además de libx264/libx265 por CPU
- **Cola de trabajos** — procesa múltiples archivos en secuencia con progreso en tiempo real
- **Explorador de archivos** integrado, con soporte de unidades en Windows
- **Detección automática** de video entrelazado (480i, 1080i) con deinterlace yadif/bwdif
- **Corrección de SAR** para videos con píxeles no cuadrados (formato HandyCam, DVD anamórfico)
- **Log rotativo** en `compressor.log` con visor integrado en la UI

## Requisitos

- Python 3.10+
- [ffmpeg y ffprobe](https://ffmpeg.org/download.html) en el PATH

## Instalación

```bash
git clone https://github.com/LoadingName404/discord-compressor
cd discord-compressor
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

pip install flask
```

## Uso

```bash
python main.py
```

Abre `http://localhost:5000` en el navegador.

1. Navega al archivo desde el explorador lateral
2. Selecciona uno o más videos
3. Elige el modo (**Comprimir** o **Convertir**) y tu perfil de equipo
4. Hacé clic en **Agregar a cola** — el output se guarda como `nombre_discord.mp4` en la misma carpeta

## Encoders soportados

| Encoder | Tipo | Notas |
|---|---|---|
| `libx264` | CPU | Dos pasadas, máxima precisión de bitrate |
| `libx265` | CPU | ~30% mejor compresión que H.264 |
| `h264_nvenc` | GPU Nvidia | Ultra rápido, requiere driver reciente |
| `h264_amf` / `hevc_amf` | GPU AMD | APUs y discretas Radeon |
| `h264_qsv` / `hevc_qsv` | iGPU Intel | Quick Sync, Gen 6+ |

## Estructura

```
discord-compressor/
├── main.py               # Servidor Flask + worker ffmpeg
├── compressor.log        # Log rotativo (generado al correr)
├── profiles/
│   ├── desktop.json      # Perfil Desktop
│   ├── laptop.json       # Perfil Laptop
│   └── thinkcentre.json  # Perfil ThinkCentre
└── static/
    └── index.html        # UI completa (JS vanilla, sin dependencias de build)
```
