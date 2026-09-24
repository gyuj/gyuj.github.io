"""
Display Receiver

Runs on a Raspberry Pi connected to an HDMI LCD display.
Listens for image data from the web app over WiFi and renders
it fullscreen on the connected display using pygame.

Usage:
    python receiver.py [--port 5000] [--width 1280] [--height 800]
"""

import argparse
import base64
import io
import logging
import os
import threading

from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 800

# pygame screen reference, initialized in main thread
screen = None
pygame_lock = threading.Lock()


def init_display(width, height, headless=False):
    """Initialize fullscreen pygame display."""
    global screen, DISPLAY_WIDTH, DISPLAY_HEIGHT
    DISPLAY_WIDTH = width
    DISPLAY_HEIGHT = height

    if headless:
        logger.info('Running in headless mode (no display)')
        return

    import pygame
    # Use the framebuffer on the Pi if no desktop environment
    if not os.environ.get('DISPLAY'):
        os.environ['SDL_VIDEODRIVER'] = 'kmsdrm'

    pygame.init()
    screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    screen.fill((0, 0, 0))
    pygame.display.flip()
    logger.info(f'Display initialized: {width}x{height} fullscreen')


def render_to_display(image):
    """Render a PIL Image to the HDMI display via pygame."""
    if screen is None:
        # Headless mode — save to file for verification
        image.save('/tmp/display_preview.png')
        logger.info('Headless mode: saved preview to /tmp/display_preview.png')
        return

    import pygame
    with pygame_lock:
        raw = image.convert('RGB').tobytes()
        surface = pygame.image.fromstring(raw, image.size, 'RGB')
        screen.blit(surface, (0, 0))
        pygame.display.flip()
    logger.info('Image rendered to display')


@app.route('/display', methods=['POST'])
def receive_image():
    """Receive an image from the web app and display it."""
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({'error': 'No image data'}), 400

        # Decode base64 PNG from data URL
        image_data = data['image']
        if ',' in image_data:
            image_data = image_data.split(',', 1)[1]

        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))

        # Resize to display dimensions if needed
        if image.size != (DISPLAY_WIDTH, DISPLAY_HEIGHT):
            image = image.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.LANCZOS)

        logger.info(f'Received image: {image.size}')
        render_to_display(image)

        return jsonify({'status': 'ok', 'size': list(image.size)})

    except Exception as e:
        logger.error(f'Error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/status', methods=['GET'])
def status():
    """Health check endpoint."""
    return jsonify({
        'status': 'running',
        'display': 'connected' if screen else 'headless',
        'resolution': [DISPLAY_WIDTH, DISPLAY_HEIGHT]
    })


def main():
    parser = argparse.ArgumentParser(description='Display Receiver')
    parser.add_argument('--port', type=int, default=5000, help='HTTP port (default: 5000)')
    parser.add_argument('--width', type=int, default=1280, help='Display width (default: 1280)')
    parser.add_argument('--height', type=int, default=800, help='Display height (default: 800)')
    parser.add_argument('--headless', action='store_true', help='Run without a display (for testing)')
    parser.add_argument('--host', default='0.0.0.0', help='Listen host (default: 0.0.0.0)')
    args = parser.parse_args()

    init_display(args.width, args.height, headless=args.headless)
    logger.info(f'Starting receiver on {args.host}:{args.port}')
    app.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
