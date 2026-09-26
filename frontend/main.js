// ============================================================================
// Tawashir — shared front-end behavior (no framework, no build step)
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  initGrain();
  initWaveBackdrop();
  initMobileMenu();
  initStatsCounter();
  initScrollReveal();
  initStory();
  initQR();
});

/**
 * Film grain: a small noise tile made once and used as a CSS background.
 * The browser's GPU moves it, so it costs almost nothing per frame.
 */
function initGrain() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  const img = g.createImageData(128, 128);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = Math.random() < 0.5 ? 0 : 255;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = Math.random() * 22;
  }
  g.putImageData(img, 0, 0);
  document.documentElement.style.setProperty('--grain', `url(${c.toDataURL()})`);
}

/**
 * Animated canvas backdrop: pastel sky, drifting code characters, and three
 * layers of sand-dune waves that roll continuously.
 *
 * Why it's smooth:
 *  - the sky is painted once (on resize) and just copied each frame
 *  - characters are only redrawn a few cells at a time
 *  - no shadowBlur / blend modes (those were the slow parts)
 *  - it pauses automatically when you scroll past the hero
 */
function initWaveBackdrop() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d', { alpha: false });
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const DPR = Math.min(window.devicePixelRatio || 1, 1.25);

  const sky = document.createElement('canvas');
  const skyCtx = sky.getContext('2d');
  const glyphs = document.createElement('canvas');
  const gCtx = glyphs.getContext('2d');

  const CHARS = '0086S$#8GO9';
  let W = 0, H = 0, cols = 0, rows = 0, cellW = 15, cellH = 24, glyphH = 0;
  let duneGrads = [];

  // Each wave layer: base height, hill, [amplitude, frequency, speed] waves, colours, rim
  function layers() {
    const narrow = W < 720;
    return [
      { // back — big central hill that the headline sits on
        base: narrow ? 0.40 : 0.46, hill: narrow ? 0.12 : 0.15, hillW: narrow ? 0.7 : 0.3,
        waves: [[0.014, 1.3, 0.09], [0.007, 3.1, -0.14]],
        stops: [[0, '#6b4867'], [0.16, '#2c1a28'], [0.5, '#0d070b'], [1, '#000']],
        rim: 'rgba(255,196,210,0.55)',
      },
      { // middle
        base: 0.58, hill: 0, hillW: 1,
        waves: [[0.035, 0.9, -0.07], [0.012, 2.4, 0.16]],
        stops: [[0, '#8a5467'], [0.14, '#3b2030'], [0.5, '#0a0508'], [1, '#000']],
        rim: 'rgba(255,180,190,0.45)',
      },
      { // front
        base: 0.70, hill: 0, hillW: 1,
        waves: [[0.05, 0.7, 0.06], [0.014, 2.0, -0.18]],
        stops: [[0, '#b0707a'], [0.1, '#6e3d4c'], [0.34, '#1c0f15'], [0.7, '#000']],
        rim: 'rgba(255,176,166,0.7)',
      },
    ];
  }
  let LAYERS = [];

  function paintSky() {
    const g = skyCtx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, '#aeaad6');
    g.addColorStop(0.2, '#c7b6dc');
    g.addColorStop(0.36, '#e3b9cf');
    g.addColorStop(0.47, '#e9a9a8');
    g.addColorStop(0.62, '#3a2230');
    g.addColorStop(1, '#000');
    skyCtx.fillStyle = g;
    skyCtx.fillRect(0, 0, W, H);
    const glow = skyCtx.createRadialGradient(W * 0.5, H * 0.42, 0, W * 0.5, H * 0.42, W * 0.55);
    glow.addColorStop(0, 'rgba(255,214,200,0.45)');
    glow.addColorStop(1, 'rgba(255,214,200,0)');
    skyCtx.fillStyle = glow;
    skyCtx.fillRect(0, 0, W, H);
  }

  function drawCell(c, r) {
    const x = c * cellW, y = r * cellH;
    gCtx.clearRect(x, y, cellW, cellH);
    if (Math.random() < 0.45) return; // leave gaps
    const fade = 1 - r / rows;
    gCtx.fillStyle = `rgba(255,255,255,${(0.12 + Math.random() * 0.32) * fade})`;
    gCtx.fillText(CHARS[(Math.random() * CHARS.length) | 0], x, y);
  }

  function paintGlyphs() {
    gCtx.clearRect(0, 0, W, glyphH);
    gCtx.font = `${W < 720 ? 13 : 18}px "Courier New", monospace`;
    gCtx.textBaseline = 'top';
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) drawCell(c, r);
  }

  function resize() {
    W = window.innerWidth;
    H = canvas.parentElement.clientHeight || window.innerHeight;
    for (const cv of [canvas, sky]) { cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR); }
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    skyCtx.setTransform(DPR, 0, 0, DPR, 0, 0);

    cellW = W < 720 ? 11 : 15;
    cellH = W < 720 ? 18 : 24;
    glyphH = H * 0.6;
    cols = Math.ceil(W / cellW);
    rows = Math.ceil(glyphH / cellH);
    glyphs.width = Math.round(W * DPR);
    glyphs.height = Math.round(glyphH * DPR);
    gCtx.setTransform(DPR, 0, 0, DPR, 0, 0);

    LAYERS = layers();
    // gradients are fixed per layer, so build them once
    duneGrads = LAYERS.map((L) => {
      const top = H * (L.base - L.hill - 0.06);
      const g = ctx.createLinearGradient(0, top, 0, top + H * 0.45);
      L.stops.forEach(([s, col]) => g.addColorStop(s, col));
      return g;
    });

    paintSky();
    paintGlyphs();
    if (reduced) frame(0);
  }

  function yAt(L, x, t) {
    const hump = L.hill ? L.hill * Math.exp(-Math.pow((x - 0.5) / L.hillW, 2)) : 0;
    let y = L.base - hump;
    for (const [amp, freq, speed] of L.waves) {
      y += amp * Math.sin(Math.PI * 2 * (x * freq + t * speed));
    }
    return y * H;
  }

  const STEP = 5;
  function tracePath(L, t) {
    ctx.beginPath();
    ctx.moveTo(0, yAt(L, 0, t));
    for (let px = STEP; px <= W + STEP; px += STEP) ctx.lineTo(px, yAt(L, px / W, t));
  }

  let lastGlyph = 0;
  function frame(time) {
    const t = time / 1000;

    ctx.drawImage(sky, 0, 0, W, H);

    // swap a handful of characters ~12 times a second
    if (time - lastGlyph > 80) {
      gCtx.font = `${W < 720 ? 13 : 18}px "Courier New", monospace`;
      gCtx.textBaseline = 'top';
      const n = Math.max(8, (cols * rows * 0.012) | 0);
      for (let i = 0; i < n; i++) drawCell((Math.random() * cols) | 0, (Math.random() * rows) | 0);
      lastGlyph = time;
    }
    // characters drift upward very slowly
    const drift = reduced ? 0 : (t * 6) % cellH;
    ctx.drawImage(glyphs, 0, -drift, W, glyphH);
    ctx.drawImage(glyphs, 0, glyphH - drift, W, glyphH);

    LAYERS.forEach((L, i) => {
      // body
      tracePath(L, t);
      ctx.lineTo(W, H);
      ctx.lineTo(0, H);
      ctx.closePath();
      ctx.fillStyle = duneGrads[i];
      ctx.fill();
      // soft glow + crisp rim (two strokes instead of an expensive blur)
      tracePath(L, t);
      ctx.strokeStyle = L.rim.replace(/[\d.]+\)$/, '0.12)');
      ctx.lineWidth = 10;
      ctx.stroke();
      ctx.strokeStyle = L.rim;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
  }

  // ---- run loop that pauses when the hero is off-screen
  let running = false;
  let rafId = 0;
  function loop(time) {
    frame(time);
    if (running) rafId = requestAnimationFrame(loop);
  }
  function start() { if (!running && !reduced) { running = true; rafId = requestAnimationFrame(loop); } }
  function stop() { running = false; cancelAnimationFrame(rafId); }

  window.addEventListener('resize', resize);
  resize();

  if (reduced) return;
  const io = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()), { threshold: 0 });
  io.observe(canvas.parentElement);
  start();
}

function initMobileMenu() {
  const burger = document.getElementById('burger');
  const overlay = document.getElementById('mobile-overlay');
  if (!burger || !overlay) return;

  function open() {
    burger.classList.add('open');
    burger.setAttribute('aria-expanded', 'true');
    overlay.hidden = false;
    document.body.classList.add('menu-open');
  }
  function close() {
    burger.classList.remove('open');
    burger.setAttribute('aria-expanded', 'false');
    overlay.hidden = true;
    document.body.classList.remove('menu-open');
  }

  burger.addEventListener('click', () => (overlay.hidden ? open() : close()));
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  overlay.querySelectorAll('a').forEach((a) => a.addEventListener('click', close));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  window.addEventListener('resize', () => { if (window.innerWidth > 720) close(); });
}

function initScrollReveal() {
  const els = document.querySelectorAll('.reveal-onscroll');
  if (!els.length) return;
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in-view');
        } else {
          // fade back out when it leaves, so every slide animates in again
          entry.target.classList.remove('in-view');
        }
      });
    },
    { threshold: 0.2 }
  );
  els.forEach((el) => io.observe(el));
}

/**
 * "How it works" story: the side rail highlights whichever step is in the
 * middle of the screen, and the thin line fills as you scroll through.
 */
function initStory() {
  const story = document.getElementById('story');
  if (!story) return;
  const steps = [...story.querySelectorAll('.story-step')];
  const links = [...story.querySelectorAll('.rail-link')];
  const fill = document.getElementById('rail-fill');

  function setActive(id) {
    links.forEach((a) => {
      const on = a.getAttribute('href') === '#' + id;
      a.classList.toggle('active', on);
      // keep the active chip visible on mobile's horizontal bar
      if (on && window.innerWidth <= 900) {
        a.parentElement.scrollTo({ left: a.offsetLeft - 16, behavior: 'smooth' });
      }
    });
    steps.forEach((s) => s.classList.toggle('is-active', s.id === id));
  }

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => { if (e.isIntersecting) setActive(e.target.id); });
    },
    { rootMargin: '-45% 0px -50% 0px' }
  );
  steps.forEach((s) => io.observe(s));

  // progress line
  let ticking = false;
  function updateFill() {
    const r = story.getBoundingClientRect();
    const total = r.height - window.innerHeight * 0.5;
    const done = Math.min(Math.max((window.innerHeight * 0.5 - r.top) / total, 0), 1);
    if (fill) fill.style.transform = `scaleY(${done})`;
    ticking = false;
  }
  window.addEventListener('scroll', () => {
    if (!ticking) { ticking = true; requestAnimationFrame(updateFill); }
  }, { passive: true });
  updateFill();

  // clicking a step glides to that slide
  links.forEach((a) =>
    a.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelector(a.getAttribute('href')).scrollIntoView({ behavior: 'smooth', block: 'start' });
    })
  );
}

/** Draws a sample (not scannable) QR-style pattern into any .qr element. */
function initQR() {
  document.querySelectorAll('.qr').forEach((el) => {
    const N = 21;
    let seed = [...(el.dataset.seed || 'tawashir')].reduce((a, c) => a * 31 + c.charCodeAt(0), 7) >>> 0;
    const rand = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
    const finder = (x, y) => {
      for (const [fx, fy] of [[0, 0], [N - 7, 0], [0, N - 7]]) {
        const dx = x - fx, dy = y - fy;
        if (dx >= 0 && dx < 7 && dy >= 0 && dy < 7) {
          const edge = dx === 0 || dx === 6 || dy === 0 || dy === 6;
          const core = dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4;
          return edge || core ? 1 : 0;
        }
      }
      return -1;
    };
    let rects = '';
    for (let y = 0; y < N; y++) {
      for (let x = 0; x < N; x++) {
        const f = finder(x, y);
        const on = f === -1 ? rand() > 0.52 : f === 1;
        if (on) rects += `<rect x="${x}" y="${y}" width="1" height="1"/>`;
      }
    }
    el.innerHTML = `<svg viewBox="-1 -1 ${N + 2} ${N + 2}" shape-rendering="crispEdges"><rect x="-1" y="-1" width="${N + 2}" height="${N + 2}" fill="#fff"/><g fill="#141016">${rects}</g></svg>`;
  });
}

/** Count-up animation for the stats footer, easeOutCubic, fires once. */
function initStatsCounter() {
  const stats = document.querySelectorAll('.stat[data-target]');
  if (!stats.length) return;

  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

  function animate(el, i) {
    const target = parseFloat(el.dataset.target);
    const decimals = parseInt(el.dataset.decimals || '0', 10);
    const suffix = el.dataset.suffix || '';
    const valueEl = el.querySelector('.stat-value');
    const duration = 1500 + i * 80;
    const start = performance.now() + 480 + i * 90;

    function tick(now) {
      const elapsed = now - start;
      if (elapsed < 0) { requestAnimationFrame(tick); return; }
      const progress = Math.min(elapsed / duration, 1);
      const value = target * easeOutCubic(progress);
      valueEl.textContent = value.toFixed(decimals) + suffix;
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          stats.forEach((el, i) => animate(el, i));
          io.disconnect();
        }
      });
    },
    { threshold: 0.25 }
  );
  io.observe(stats[0]);
}