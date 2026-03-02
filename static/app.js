const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const analyzeBtn = document.getElementById('analyzeBtn');
const statusEl = document.getElementById('status');
const resultEl = document.getElementById('result');
const debugPanelEl = document.getElementById('debugPanel');
const referenceImageEl = document.getElementById('referenceImage');
const referencePlaceholderEl = document.getElementById('referencePlaceholder');
const debugWrapperEl = document.getElementById('debugWrapper');
const debugToggleBtn = document.getElementById('debugToggleBtn');
const liveFrameEl = document.getElementById('liveFrame');
const referenceFrameEl = document.getElementById('referenceFrame');
const referenceOpenBtn = document.getElementById('referenceOpenBtn');
const BRICKLINK_TAB_NAME = 'bricklinkTab';

let mediaStream = null;
let referenceImageClickUrl = null;
let debugCollapsed = false;

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
  if (referenceOpenBtn) referenceOpenBtn.hidden = true;
}

function renderReferenceImage(prediction) {
  const imageUrl = prediction?.bricklink_image_url || prediction?.image_url || null;
  const bricklinkUrl = prediction?.bricklink_url || null;
  const bricklinkType = prediction?.bricklink_type || null;

  if (bricklinkType === 'other') {
    resetReferenceImage('Not MiniFigure or MiniFigure Part');
    return;
  }

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
    if (referenceOpenBtn) referenceOpenBtn.hidden = false;
  } else {
    referenceImageClickUrl = null;
    referenceImageEl.classList.add('not-clickable');
    if (referenceOpenBtn) referenceOpenBtn.hidden = true;
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

  // If Brickognize / BrickLink identified a minifigure, render the minifigure price table
  if (prediction?.is_minifigure) {
    const details = prediction.minifigure_price_details || {};
    const last6 = details.last6 || { new: {}, used: {} };
    const current = details.current || { new: {}, used: {} };
    // Compact table: rows are Last 6 Months and Current; columns New / Used
    return `
      <article class="card">
        <div class="inline-metadata">
          <div class="meta-id"><strong>ID:</strong> ${prediction.bricklink_url ? `<a href="${prediction.bricklink_url}" target="${BRICKLINK_TAB_NAME}">${prediction.id || 'N/A'}</a>` : (prediction.id || 'N/A')}</div>
          <div class="meta-confidence"><strong>Confidence:</strong> ${prediction.score ? (prediction.score * 100).toFixed(1) + '%' : 'N/A'}</div>
          <div class="meta-ninjago"><strong>NINJAGO:</strong> ${prediction.minifigure_is_ninjago ? 'Yes' : 'No'}</div>
        </div>
        <p class="meta-name"><strong>Name:</strong> ${prediction.name || 'N/A'}</p>

        <table class="compact-prices">
          <thead>
            <tr>
              <th>Period</th>
              <th>New Avg</th>
              <th>Used Avg</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Last 6 Months</td>
              <td>${last6.new.avg ?? 'N/A'}</td>
              <td>${last6.used.avg ?? 'N/A'}</td>
            </tr>
            <tr>
              <td>Current Items</td>
              <td>${current.new.avg ?? 'N/A'}</td>
              <td>${current.used.avg ?? 'N/A'}</td>
            </tr>
          </tbody>
        </table>
      </article>
    `;
  }

  const minifigRows = minifigs
    .map((fig) => {
      const badge = fig.is_ninjago ? '<span class="badge">NINJAGO</span>' : '';
      const newPrice = fig.avg_new_price || 'N/A';
      const usedPrice = fig.avg_used_price || 'N/A';

      return `
        <tr>
          <td><a href="${fig.url}" target="${BRICKLINK_TAB_NAME}">${fig.id}</a></td>
          <td>${fig.name} ${badge}</td>
          <td>${newPrice}</td>
          <td>${usedPrice}</td>
        </tr>
      `;
    })
    .join('');

  const partNew = prediction.avg_new_price || 'N/A';
  const partUsed = prediction.avg_used_price || 'N/A';

  // Compact part view: show compact prices and the list of minifigures below
  const partDetails = prediction.part_price_details || {};
  const pLast6 = partDetails.last6 || {new:{}, used:{}};
  const pCurrent = partDetails.current || {new:{}, used:{}};

  return `
    <article class="card">
      <div class="inline-metadata">
        <div class="meta-id"><strong>ID:</strong> ${prediction.bricklink_url ? `<a href="${prediction.bricklink_url}" target="${BRICKLINK_TAB_NAME}">${prediction.id || 'N/A'}</a>` : (prediction.id || 'N/A')}</div>
        <div class="meta-confidence"><strong>Confidence:</strong> ${prediction.score ? (prediction.score * 100).toFixed(1) + '%' : 'N/A'}</div>
        <div class="meta-ninjago"><strong>NINJAGO:</strong> ${ninjago.is_in_any_ninjago_minifigure ? 'Yes' : 'No'}</div>
      </div>
      <p class="meta-name"><strong>Name:</strong> ${prediction.name || 'N/A'}</p>

      <table class="compact-prices">
        <thead>
          <tr>
            <th>Period</th>
            <th>New Avg</th>
            <th>Used Avg</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Last 6 Months</td>
            <td>${pLast6.new.avg ?? 'N/A'}</td>
            <td>${pLast6.used.avg ?? 'N/A'}</td>
          </tr>
          <tr>
            <td>Current Items</td>
            <td>${pCurrent.new.avg ?? partNew}</td>
            <td>${pCurrent.used.avg ?? partUsed}</td>
          </tr>
        </tbody>
      </table>
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

    const text = await response.text();
    let payload = null;
    try {
      payload = JSON.parse(text);
    } catch (err) {
      // Not JSON — show raw text in debug and surface an error
      setDebugPanel(text);
      setStatus('Analysis request failed: non-JSON response', true);
      resetReferenceImage('Reference image unavailable due to request error.');
      return;
    }

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
  window.open(referenceImageClickUrl, BRICKLINK_TAB_NAME);
});

function openReferenceUrl() {
  if (!referenceImageClickUrl) return;
  window.open(referenceImageClickUrl, BRICKLINK_TAB_NAME);
}

// clicking the whole live frame triggers analyze
if (liveFrameEl) {
  liveFrameEl.addEventListener('click', (ev) => {
    // If the click was on the overlay button itself, let the button handler run
    if (ev.target === analyzeBtn) return;
    analyzeCurrentFrame();
  });
}

// clicking the whole reference frame opens BrickLink when available
if (referenceFrameEl) {
  referenceFrameEl.addEventListener('click', (ev) => {
    if (ev.target === referenceOpenBtn) return;
    openReferenceUrl();
  });
}

if (referenceOpenBtn) {
  referenceOpenBtn.addEventListener('click', (ev) => {
    ev.stopPropagation();
    openReferenceUrl();
  });
}

function setDebugCollapse(collapsed) {
  debugCollapsed = collapsed;
  debugWrapperEl.classList.toggle('collapsed', collapsed);
  debugToggleBtn.textContent = collapsed ? 'Show details' : 'Hide details';
  debugToggleBtn.setAttribute('aria-expanded', String(!collapsed));
}

debugToggleBtn.addEventListener('click', () => {
  setDebugCollapse(!debugCollapsed);
});
setDebugCollapse(true);
analyzeBtn.addEventListener('click', analyzeCurrentFrame);
window.addEventListener('load', startCamera);
