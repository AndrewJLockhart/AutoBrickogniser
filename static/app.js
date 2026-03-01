const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const analyzeBtn = document.getElementById('analyzeBtn');
const statusEl = document.getElementById('status');
const resultEl = document.getElementById('result');
const debugPanelEl = document.getElementById('debugPanel');
const referenceImageEl = document.getElementById('referenceImage');
const referencePlaceholderEl = document.getElementById('referencePlaceholder');

let mediaStream = null;
let referenceImageClickUrl = null;

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.className = isError ? 'error' : '';
}

function clearResults() {
  resultEl.innerHTML = '';
}

function setDebugPanel(text) {
  debugPanelEl.textContent = text;
}

function resetReferenceImage(message = 'No detected piece yet.') {
  referenceImageEl.hidden = true;
  referenceImageEl.removeAttribute('src');
  referenceImageClickUrl = null;
  referenceImageEl.classList.add('not-clickable');
  referencePlaceholderEl.hidden = false;
  referencePlaceholderEl.textContent = message;
}

function renderReferenceImage(prediction) {
  const imageUrl = prediction?.bricklink_image_url || prediction?.image_url || null;
  const bricklinkUrl = prediction?.bricklink_url || null;

  if (!imageUrl) {
    resetReferenceImage('No reference image available for this match.');
    return;
  }

  referenceImageEl.src = imageUrl;
  referenceImageEl.hidden = false;
  referencePlaceholderEl.hidden = true;

  if (bricklinkUrl) {
    referenceImageClickUrl = bricklinkUrl;
    referenceImageEl.classList.remove('not-clickable');
  } else {
    referenceImageClickUrl = null;
    referenceImageEl.classList.add('not-clickable');
  }
}

function renderBrickognizeDebug(payload) {
  const brickognizeRaw = payload?.brickognize?.raw_response || payload?.raw || null;
  const brickognizeAttempts = payload?.brickognize?.attempts || payload?.brickognize_attempts || [];

  const debugPayload = {
    attempts: brickognizeAttempts,
    raw_response: brickognizeRaw,
  };

  setDebugPanel(JSON.stringify(debugPayload, null, 2));
}

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus(
      'Camera API is unavailable in this browser context. Open http://127.0.0.1:5000 in Chrome/Edge/Firefox (outside VS Code Simple Browser).',
      true,
    );
    return;
  }

  if (mediaStream) {
    return;
  }

  try {
    const preferredConstraints = {
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    };

    const fallbackConstraints = {
      video: true,
      audio: false,
    };

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia(preferredConstraints);
    } catch {
      mediaStream = await navigator.mediaDevices.getUserMedia(fallbackConstraints);
    }

    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.srcObject = mediaStream;

    try {
      await video.play();
    } catch {
      // Some browsers still start rendering after metadata events.
    }

    analyzeBtn.disabled = true;
    setStatus('Starting camera...');

    const onReady = () => {
      analyzeBtn.disabled = false;
      setStatus('Camera ready. Position the piece and tap the analyze icon.');
      video.removeEventListener('loadeddata', onReady);
    };

    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0) {
      onReady();
    } else {
      video.addEventListener('loadeddata', onReady);
    }
  } catch (error) {
    const message = String(error?.message || error || 'Unknown camera error');

    if (error?.name === 'NotAllowedError') {
      setStatus('Camera permission denied. Allow camera access in your browser and try again.', true);
      return;
    }

    if (error?.name === 'NotFoundError') {
      setStatus('No camera device was found. Connect a webcam and try again.', true);
      return;
    }

    if (error?.name === 'NotReadableError') {
      setStatus('Camera is busy in another app. Close other apps using the camera and try again.', true);
      return;
    }

    setStatus(`Failed to start camera: ${message}`, true);
  }
}

function captureFrameAsBlob() {
  const width = video.videoWidth || 1280;
  const height = video.videoHeight || 720;

  canvas.width = width;
  canvas.height = height;

  const context = canvas.getContext('2d');
  context.drawImage(video, 0, 0, width, height);

  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.92);
  });
}

function buildPredictionHtml(data) {
  const prediction = data.prediction;
  const ninjago = data.ninjago;
  const minifigs = data.minifigures || [];

  const minifigRows = minifigs
    .map((fig) => {
      const badge = fig.is_ninjago ? '<span class="badge">NINJAGO</span>' : '';
      const newPrice = fig.avg_new_price || 'N/A';
      const usedPrice = fig.avg_used_price || 'N/A';

      return `
        <tr>
          <td><a href="${fig.url}" target="_blank" rel="noopener noreferrer">${fig.id}</a></td>
          <td>${fig.name} ${badge}</td>
          <td>${newPrice}</td>
          <td>${usedPrice}</td>
        </tr>
      `;
    })
    .join('');

  const partNew = prediction.avg_new_price || 'N/A';
  const partUsed = prediction.avg_used_price || 'N/A';

  return `
    <article class="card">
      <h3>Detected Piece</h3>
      <p><strong>ID:</strong> ${prediction.id || 'N/A'}</p>
      <p><strong>Name:</strong> ${prediction.name || 'N/A'}</p>
      <p><strong>Confidence:</strong> ${prediction.score ? (prediction.score * 100).toFixed(1) + '%' : 'N/A'}</p>
      <p><strong>Part of any NINJAGO minifigure:</strong> ${ninjago.is_in_any_ninjago_minifigure ? 'Yes' : 'No'}</p>
      <p><strong>Detected Piece Avg Price:</strong> New ${partNew} / Used ${partUsed}</p>
      ${prediction.bricklink_url ? `<p><a href="${prediction.bricklink_url}" target="_blank" rel="noopener noreferrer">Open on BrickLink</a></p>` : ''}
    </article>

    <article class="card">
      <h3>Minifigures containing this piece (${minifigs.length})</h3>
      ${
        minifigs.length
          ? `
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Avg New</th>
              <th>Avg Used</th>
            </tr>
          </thead>
          <tbody>${minifigRows}</tbody>
        </table>
      `
          : '<p>No related minifigures found.</p>'
      }
    </article>
  `;
}

async function analyzeCurrentFrame() {
  clearResults();

  if (!video.srcObject || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || video.videoWidth === 0) {
    setStatus('Video is not ready yet. Wait a moment after starting camera, then try again.', true);
    return;
  }

  setStatus('Capturing frame and sending to Brickognize...');
  setDebugPanel('Running analysis...');
  resetReferenceImage('Running analysis...');

  const blob = await captureFrameAsBlob();
  if (!blob) {
    setStatus('Failed to capture an image from camera.', true);
    return;
  }

  const formData = new FormData();
  formData.append('image', blob, 'capture.jpg');

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      body: formData,
    });

    const payload = await response.json();
    renderBrickognizeDebug(payload);

    if (!response.ok) {
      const tips = payload?.details?.tips || [];
      const attempts = payload?.details?.attempts || [];
      const attemptSummary = attempts
        .map((a) => {
          if (!a.ok) {
            return `${a.endpoint}: request failed`;
          }
          return `${a.endpoint}: ${a.items_count || 0} candidates`;
        })
        .join(' | ');

      setStatus(payload.error || 'Analysis failed.', true);
      resetReferenceImage('No Match in the box');

      if (tips.length || attemptSummary) {
        resultEl.innerHTML = `
          <article class="card">
            <h3>No Match Diagnostics</h3>
            ${attemptSummary ? `<p><strong>API attempts:</strong> ${attemptSummary}</p>` : ''}
            ${
              tips.length
                ? `<ul>${tips.map((tip) => `<li>${tip}</li>`).join('')}</ul>`
                : ''
            }
          </article>
        `;
      }
      return;
    }

    resultEl.innerHTML = buildPredictionHtml(payload);
    renderReferenceImage(payload.prediction);
    setStatus('Analysis complete.');
  } catch (error) {
    setDebugPanel(
      JSON.stringify(
        {
          error: 'Network/request error while calling /api/analyze',
          message: String(error?.message || error || 'Unknown error'),
        },
        null,
        2,
      ),
    );
    resetReferenceImage('Reference image unavailable due to request error.');
    setStatus(`Analysis request failed: ${error.message}`, true);
  }
}

resetReferenceImage();
referenceImageEl.addEventListener('click', () => {
  if (!referenceImageClickUrl) {
    return;
  }
  window.open(referenceImageClickUrl, '_blank', 'noopener,noreferrer');
});
analyzeBtn.addEventListener('click', analyzeCurrentFrame);
window.addEventListener('load', startCamera);
