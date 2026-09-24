# Wireless Display

A wireless display system that lets you design and send custom color images, text, and drawings to an HDMI LCD screen via a Raspberry Pi over WiFi.

## Overview

```
[ Web App (Canvas Editor) ] --(WiFi / HTTP)--> [ Raspberry Pi ] --(HDMI)--> [ 10.1" LCD ]
```

### Components

1. **Web App** (`app/`) - Browser-based canvas editor for composing display content
   - Upload images matched to the display's pixel dimensions (1280x800)
   - Add text overlays with custom fonts, sizes, and colors
   - Draw freehand on the canvas
   - Send the composed image over WiFi to the receiver

2. **Receiver** (`receiver/`) - Python service running on a Raspberry Pi
   - Listens for incoming image data over local WiFi (HTTP)
   - Renders received images fullscreen via pygame on the HDMI display

## Hardware

| Part | Est. Cost |
|------|-----------|
| Raspberry Pi Zero 2 W | ~$15 |
| 10.1" HDMI IPS LCD (1280x800) | ~$55 |
| MicroSD card (16GB) | ~$5 |
| USB-C power supply | ~$8 |
| Mini HDMI to HDMI cable | ~$5 |
| **Total** | **~$88** |

## Quick Start

### App
```bash
cd app
# Open index.html in any browser — no build tools needed
```

### Receiver (on the Raspberry Pi)
```bash
cd receiver
pip install -r requirements.txt

# With display connected
python receiver.py

# For testing without a display
python receiver.py --headless
```

### Configuration

- **Display resolution**: adjust `--width` and `--height` flags on receiver, and match in the app's settings bar
- **Pi address**: update `RECEIVER_URL` in `app/editor.js` to your Pi's IP (e.g., `http://192.168.1.42:5000/display`)

## Status

In progress
