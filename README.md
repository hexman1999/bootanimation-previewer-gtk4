# Boot Animation Previewer

A GTK4/Libadwaita application for previewing and exporting Android `bootanimation.zip` files.

## Features

- **Preview** boot animations at original or device-mapped resolution
- **Playback** with play/pause, stop, frame-by-frame navigation, and seekbar
- **Speed control** — 0.5x, 1.0x, 1.5x, 2.0x
- **Loop** entire animation or control per-part repeat count
- **Export** to MP4 or GIF at any device preset resolution
- **Device presets** for common phone, tablet, smartwatch, and foldable resolutions
- **Custom viewport dimensions** (100–8000 px)
- **File info dialog** with copy path and show-in-folder
- **Player status bar** showing current part and frame

## Dependencies

- Python 3.10+
- GTK4 / Libadwaita (via `PyGObject`)
- `pycairo`
- `opencv-python`
- `numpy`
- `ffmpeg` (required only for GIF export)

### Install system dependencies (Ubuntu/Debian)

```bash
sudo apt install libgtk-4-dev libadwaita-1-dev libgraphene-1.0-0 ffmpeg
```

### Install Python packages

```bash
pip install -r requirements.txt
```

## Usage

```bash
python3 previewer.py
```

### Interface

<img width="1130" height="800" alt="image" src="https://github.com/user-attachments/assets/315aff56-eb99-4763-b2a9-db6b3e45fc10" />


| Control | Location | Description |
|---------|----------|-------------|
| **Open Animation** | Header bar | Load a `bootanimation.zip` file |
| **Export** | Header bar | Export as MP4 or GIF at selected resolution |
| **Info** | Header bar | Show animation metadata (filename, path, resolution, FPS, parts, frames) |
| **Device Presets** | Header bar dropdown | Choose preview resolution preset |
| **Play/Pause** | Control bar | Toggle playback |
| **Stop** | Control bar | Stop and reset to first frame |
| **Previous / Next** | Control bar | Step through frames |
| **Loop** | Control bar | Toggle entire-animation looping |
| **Speed** | Control bar dropdown | Adjust playback speed |
| **Seekbar** | Below canvas | Drag to seek through the animation |
| **Status info** | Control bar toggle | Show/hide current part and frame number |
| **Repetitions** | Control bar spin button | Default loop count for parts with `count=0` in `desc.txt` |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `O` | Open Animation |
| `E` | Export |
| `I` | File Info |
| `Space` | Play / Pause |
| `S` | Stop |
| `A` / `←` | Previous Frame |
| `D` / `→` | Next Frame |
| `L` | Toggle Loop |
| `T` | Toggle Player Status |

## Input Format

Standard Android boot animation ZIP files with:

- `desc.txt` — descriptor file (format: `width height fps` header, then `type count pause path` part entries)
- Frame images — PNG or JPG per part directory
- Optional `trim.txt` per part for sub-frame trimming

## Export Output

- **MP4** — rendered via OpenCV H.264 video writer
- **GIF** — rendered through ffmpeg with palette generation and Bayer dithering

Export resolution is determined by the currently selected device preset.

## License

MIT
