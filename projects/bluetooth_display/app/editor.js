const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

// Display config
let DISPLAY_W = parseInt(document.getElementById('displayWidth').value);
let DISPLAY_H = parseInt(document.getElementById('displayHeight').value);
let scale = 1; // 1x default for larger resolution

// State
let mode = 'draw'; // draw | text | erase
let drawing = false;
let history = [];
let lastPos = null;

// Receiver config — change this to your Raspberry Pi's address
const RECEIVER_URL = 'http://raspberrypi.local:5000/display';

function initCanvas() {
  canvas.width = DISPLAY_W;
  canvas.height = DISPLAY_H;
  canvas.style.width = (DISPLAY_W * scale) + 'px';
  canvas.style.height = (DISPLAY_H * scale) + 'px';
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, DISPLAY_W, DISPLAY_H);
  history = [];
  saveState();
}

function saveState() {
  history.push(canvas.toDataURL());
  if (history.length > 50) history.shift();
}

function undo() {
  if (history.length > 1) {
    history.pop();
    const img = new Image();
    img.onload = () => {
      ctx.clearRect(0, 0, DISPLAY_W, DISPLAY_H);
      ctx.drawImage(img, 0, 0);
    };
    img.src = history[history.length - 1];
  }
}

function getCanvasPos(e) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (e.clientX - rect.left) * (DISPLAY_W / rect.width),
    y: (e.clientY - rect.top) * (DISPLAY_H / rect.height)
  };
}

// Drawing
canvas.addEventListener('mousedown', (e) => {
  const pos = getCanvasPos(e);

  if (mode === 'text') {
    const text = document.getElementById('textInput').value;
    if (!text) return;
    const size = parseInt(document.getElementById('fontSize').value);
    ctx.font = `${size}px sans-serif`;
    ctx.fillStyle = document.getElementById('colorPicker').value;
    ctx.fillText(text, pos.x, pos.y);
    saveState();
    return;
  }

  drawing = true;
  lastPos = pos;
});

canvas.addEventListener('mousemove', (e) => {
  if (!drawing) return;
  const pos = getCanvasPos(e);
  const brushW = parseInt(document.getElementById('brushSize').value);

  ctx.lineWidth = brushW;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  if (mode === 'erase') {
    ctx.globalCompositeOperation = 'destination-out';
  } else {
    ctx.globalCompositeOperation = 'source-over';
    ctx.strokeStyle = document.getElementById('colorPicker').value;
  }

  ctx.beginPath();
  ctx.moveTo(lastPos.x, lastPos.y);
  ctx.lineTo(pos.x, pos.y);
  ctx.stroke();

  lastPos = pos;
});

canvas.addEventListener('mouseup', () => {
  if (drawing) {
    drawing = false;
    ctx.globalCompositeOperation = 'source-over';
    saveState();
  }
});

canvas.addEventListener('mouseleave', () => {
  if (drawing) {
    drawing = false;
    ctx.globalCompositeOperation = 'source-over';
    saveState();
  }
});

// Touch support
canvas.addEventListener('touchstart', (e) => {
  e.preventDefault();
  const touch = e.touches[0];
  canvas.dispatchEvent(new MouseEvent('mousedown', { clientX: touch.clientX, clientY: touch.clientY }));
});
canvas.addEventListener('touchmove', (e) => {
  e.preventDefault();
  const touch = e.touches[0];
  canvas.dispatchEvent(new MouseEvent('mousemove', { clientX: touch.clientX, clientY: touch.clientY }));
});
canvas.addEventListener('touchend', (e) => {
  e.preventDefault();
  canvas.dispatchEvent(new MouseEvent('mouseup'));
});

// Image upload
document.getElementById('imageInput').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const img = new Image();
  img.onload = () => {
    ctx.drawImage(img, 0, 0, DISPLAY_W, DISPLAY_H);
    saveState();
  };
  img.src = URL.createObjectURL(file);
});

// Toolbar buttons
document.getElementById('btnDraw').addEventListener('click', () => setMode('draw'));
document.getElementById('btnText').addEventListener('click', () => setMode('text'));
document.getElementById('btnErase').addEventListener('click', () => setMode('erase'));
document.getElementById('btnUndo').addEventListener('click', undo);
document.getElementById('btnClear').addEventListener('click', () => {
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, DISPLAY_W, DISPLAY_H);
  saveState();
});

function setMode(m) {
  mode = m;
  document.querySelectorAll('.toolbar button').forEach(b => b.classList.remove('active'));
  const btnMap = { draw: 'btnDraw', text: 'btnText', erase: 'btnErase' };
  if (btnMap[m]) document.getElementById(btnMap[m]).classList.add('active');
  canvas.style.cursor = m === 'text' ? 'text' : 'crosshair';
}

// Apply display size
document.getElementById('btnApplySize').addEventListener('click', () => {
  DISPLAY_W = parseInt(document.getElementById('displayWidth').value);
  DISPLAY_H = parseInt(document.getElementById('displayHeight').value);
  initCanvas();
});

// Scale selector
document.getElementById('scaleSelect').addEventListener('change', (e) => {
  scale = parseInt(e.target.value);
  canvas.style.width = (DISPLAY_W * scale) + 'px';
  canvas.style.height = (DISPLAY_H * scale) + 'px';
});

// Download
document.getElementById('btnDownload').addEventListener('click', () => {
  const link = document.createElement('a');
  link.download = 'display_image.png';
  link.href = canvas.toDataURL('image/png');
  link.click();
});

// Send to display
document.getElementById('btnSend').addEventListener('click', async () => {
  const status = document.getElementById('status');

  // Get raw pixel data at native display resolution
  const imageData = canvas.toDataURL('image/png');

  try {
    status.className = '';
    status.style.display = 'block';
    status.textContent = 'Sending...';
    status.style.background = '#1a1a3e';
    status.style.color = '#a0c4ff';

    const response = await fetch(RECEIVER_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image: imageData,
        width: DISPLAY_W,
        height: DISPLAY_H
      })
    });

    if (response.ok) {
      status.className = 'success';
      status.textContent = 'Sent to display!';
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (err) {
    status.className = 'error';
    status.textContent = `Failed to send: ${err.message}. Is the receiver running?`;
  }
});

// Init
initCanvas();
