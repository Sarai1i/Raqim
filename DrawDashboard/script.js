/**
 * script.js
 * Random Draw Dashboard — Main Application Logic
 *
 * Sections:
 *  1. State Management
 *  2. LocalStorage Helpers
 *  3. Wheel Drawing Engine
 *  4. Spin Animation Engine
 *  5. Draw Logic
 *  6. Result & History UI
 *  7. Confetti Engine
 *  8. Sound Engine
 *  9. Side Panel
 * 10. Dark Mode
 * 11. Fullscreen
 * 12. CSV Export
 * 13. History Search & Clear
 * 14. Keyboard Accessibility
 * 15. Initialization
 */

/* ══════════════════════════════════════════════════════════
   1. STATE MANAGEMENT
══════════════════════════════════════════════════════════ */

const State = {
  people:           [],   // full list (from config or localStorage)
  games:            [],   // full list
  remainingPeople:  [],   // items not yet drawn
  remainingGames:   [],   // items not yet drawn
  history:          [],   // [{person, game, time}]
  isSpinning:       false,
  soundEnabled:     true,
  darkMode:         false,
  fullscreen:       false,

  // Current rotation angles for each wheel (in radians)
  peopleAngle:      0,
  gamesAngle:       0,
};

/* ══════════════════════════════════════════════════════════
   2. LOCALSTORAGE HELPERS
══════════════════════════════════════════════════════════ */

const Storage = {
  save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* quota */ }
  },
  load(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw !== null ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  },
  remove(key) {
    try { localStorage.removeItem(key); } catch (e) { /* noop */ }
  }
};

function persistState() {
  Storage.save(CONFIG.storageKeys.people,    State.people);
  Storage.save(CONFIG.storageKeys.games,     State.games);
  Storage.save(CONFIG.storageKeys.history,   State.history);
  Storage.save(CONFIG.storageKeys.sound,     State.soundEnabled);
  Storage.save(CONFIG.storageKeys.darkMode,  State.darkMode);
  Storage.save(CONFIG.storageKeys.remaining, {
    people: State.remainingPeople,
    games:  State.remainingGames
  });
}

function loadState() {
  State.people   = Storage.load(CONFIG.storageKeys.people,  CONFIG.defaultPeople);
  State.games    = Storage.load(CONFIG.storageKeys.games,   CONFIG.defaultGames);
  State.history  = Storage.load(CONFIG.storageKeys.history, []);
  State.soundEnabled = Storage.load(CONFIG.storageKeys.sound, true);
  State.darkMode     = Storage.load(CONFIG.storageKeys.darkMode, false);

  const rem = Storage.load(CONFIG.storageKeys.remaining, null);
  if (rem && rem.people && rem.games) {
    State.remainingPeople = rem.people;
    State.remainingGames  = rem.games;
  } else {
    State.remainingPeople = [...State.people];
    State.remainingGames  = [...State.games];
  }
}

/* ══════════════════════════════════════════════════════════
   3. WHEEL DRAWING ENGINE
══════════════════════════════════════════════════════════ */

/**
 * Draw a wheel on a canvas element.
 * @param {HTMLCanvasElement} canvas
 * @param {string[]} items  - labels for each sector
 * @param {number}   angle  - current rotation offset in radians
 */
function drawWheel(canvas, items, angle) {
  const ctx    = canvas.getContext('2d');
  const size   = canvas.width;
  const cx     = size / 2;
  const cy     = size / 2;
  const radius = size / 2 - 2;

  ctx.clearRect(0, 0, size, size);

  if (!items || items.length === 0) {
    // Draw empty state
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = getComputedStyle(document.documentElement)
      .getPropertyValue('--color-surface-3').trim() || '#E8F0EB';
    ctx.fill();
    ctx.fillStyle = getComputedStyle(document.documentElement)
      .getPropertyValue('--color-text-muted').trim() || '#8AA898';
    ctx.font = `bold ${size * 0.07}px Tajawal, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('لا توجد عناصر', cx, cy);
    return;
  }

  const n         = items.length;
  const sliceAngle = (Math.PI * 2) / n;
  const colors    = CONFIG.wheelColors;

  // ── Draw sectors ──────────────────────────────────────────
  for (let i = 0; i < n; i++) {
    const startAngle = angle + i * sliceAngle - Math.PI / 2;
    const endAngle   = startAngle + sliceAngle;

    // Sector fill
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, startAngle, endAngle);
    ctx.closePath();
    ctx.fillStyle = colors[i % colors.length];
    ctx.fill();

    // Sector border
    ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.lineWidth   = 1.5;
    ctx.stroke();
  }

  // ── Draw labels ───────────────────────────────────────────
  ctx.save();
  for (let i = 0; i < n; i++) {
    const midAngle = angle + i * sliceAngle - Math.PI / 2 + sliceAngle / 2;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(midAngle);

    // Text position along radius
    const textRadius = radius * 0.62;
    ctx.translate(textRadius, 0);

    // Rotate text to be readable from center outward (RTL-friendly)
    ctx.rotate(Math.PI / 2);

    const label     = items[i];
    const maxWidth  = radius * 0.52;
    const fontSize  = Math.max(10, Math.min(size * 0.042, 16));

    ctx.font        = `600 ${fontSize}px Tajawal, sans-serif`;
    ctx.fillStyle   = '#FFFFFF';
    ctx.textAlign   = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor  = 'rgba(0,0,0,0.4)';
    ctx.shadowBlur   = 3;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 1;

    // Truncate long labels
    let displayText = label;
    while (ctx.measureText(displayText).width > maxWidth && displayText.length > 2) {
      displayText = displayText.slice(0, -1);
    }
    if (displayText !== label) displayText += '…';

    ctx.fillText(displayText, 0, 0);
    ctx.restore();
  }
  ctx.restore();

  // ── Outer ring ────────────────────────────────────────────
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(255,255,255,0.5)';
  ctx.lineWidth   = 3;
  ctx.stroke();
}

/**
 * Resize a canvas to match its CSS display size (for crisp rendering on HiDPI).
 */
function resizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr  = window.devicePixelRatio || 1;
  const size = Math.round(Math.min(rect.width, rect.height) * dpr);
  if (canvas.width !== size || canvas.height !== size) {
    canvas.width  = size;
    canvas.height = size;
  }
}

/* ══════════════════════════════════════════════════════════
   4. SPIN ANIMATION ENGINE
══════════════════════════════════════════════════════════ */

/**
 * Easing function: ease-out cubic with a long tail for realistic deceleration.
 */
function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * Custom easing: ease-out quart for even more dramatic deceleration.
 */
function easeOutQuart(t) {
  return 1 - Math.pow(1 - t, 4);
}

/**
 * Spin a wheel to land on a specific item index.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {string[]}          items       - current items on wheel
 * @param {number}            targetIndex - index to land on
 * @param {number}            startAngle  - current rotation (radians)
 * @param {number}            duration    - animation duration (ms)
 * @returns {Promise<number>} resolves with final angle when done
 */
function spinWheel(canvas, items, targetIndex, startAngle, duration) {
  return new Promise((resolve) => {
    const n          = items.length;
    const sliceAngle = (Math.PI * 2) / n;

    // The pointer is at the top (12 o'clock = -π/2).
    // We want the center of targetIndex sector to be at the top.
    // Sector i center is at: startAngle + i*sliceAngle + sliceAngle/2 - π/2
    // We need that to equal -π/2 (mod 2π), so:
    // targetAngle = -(targetIndex * sliceAngle + sliceAngle / 2)
    const targetSectorCenter = -(targetIndex * sliceAngle + sliceAngle / 2);

    // Add full rotations for visual effect
    const extraRotations = CONFIG.spinMinRotations +
      Math.random() * (CONFIG.spinMaxRotations - CONFIG.spinMinRotations);
    const totalRotation = extraRotations * Math.PI * 2 +
      ((targetSectorCenter - startAngle) % (Math.PI * 2) +
        Math.PI * 2) % (Math.PI * 2);

    const endAngle = startAngle + totalRotation;

    let startTime = null;

    function frame(timestamp) {
      if (!startTime) startTime = timestamp;
      const elapsed  = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased    = easeOutQuart(progress);

      const currentAngle = startAngle + (endAngle - startAngle) * eased;

      resizeCanvas(canvas);
      drawWheel(canvas, items, currentAngle);

      if (progress < 1) {
        requestAnimationFrame(frame);
      } else {
        // Normalize final angle to [0, 2π)
        const finalAngle = ((endAngle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
        resolve(finalAngle);
      }
    }

    requestAnimationFrame(frame);
  });
}

/* ══════════════════════════════════════════════════════════
   5. DRAW LOGIC
══════════════════════════════════════════════════════════ */

/**
 * Pick a random index from an array.
 */
function pickRandom(arr) {
  return Math.floor(Math.random() * arr.length);
}

/**
 * Main draw action: spin both wheels and reveal results.
 */
async function startDraw() {
  if (State.isSpinning) return;

  const { remainingPeople, remainingGames } = State;

  if (remainingPeople.length === 0 || remainingGames.length === 0) {
    showEndBanner();
    return;
  }

  State.isSpinning = true;
  setDrawButtonState('spinning');
  clearResultCards();

  // Pick random targets
  const personIndex = pickRandom(remainingPeople);
  const gameIndex   = pickRandom(remainingGames);
  const chosenPerson = remainingPeople[personIndex];
  const chosenGame   = remainingGames[gameIndex];

  // Duration with slight variance between wheels for realism
  const baseDuration = CONFIG.spinMinDuration +
    Math.random() * (CONFIG.spinMaxDuration - CONFIG.spinMinDuration);
  const peopleDuration = baseDuration;
  const gamesDuration  = baseDuration + (Math.random() - 0.5) * 800;

  // Play spin sound
  if (State.soundEnabled) Sound.playSpinStart();

  // Add spinning class for visual pulse
  DOM.peopleCanvas.classList.add('spinning');
  DOM.gamesCanvas.classList.add('spinning');

  // Spin both wheels simultaneously
  const [finalPeopleAngle, finalGamesAngle] = await Promise.all([
    spinWheel(DOM.peopleCanvas, remainingPeople, personIndex, State.peopleAngle, peopleDuration),
    spinWheel(DOM.gamesCanvas,  remainingGames,  gameIndex,   State.gamesAngle,  gamesDuration)
  ]);

  // Remove spinning class
  DOM.peopleCanvas.classList.remove('spinning');
  DOM.gamesCanvas.classList.remove('spinning');

  // Update angles
  State.peopleAngle = finalPeopleAngle;
  State.gamesAngle  = finalGamesAngle;

  // Remove drawn items
  State.remainingPeople.splice(personIndex, 1);
  State.remainingGames.splice(gameIndex, 1);

  // Update badges
  updateRemainingBadges();

  // Record in history
  const entry = {
    person: chosenPerson,
    game:   chosenGame,
    time:   new Date().toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' })
  };
  State.history.unshift(entry);

  // Persist
  persistState();

  // Redraw wheels with updated remaining lists
  redrawWheels();

  // Show results
  showResults(chosenPerson, chosenGame);

  // Confetti
  if (State.soundEnabled) Sound.playWin();
  Confetti.burst();

  // Render history
  renderHistory();

  State.isSpinning = false;
  setDrawButtonState('idle');

  // Check if all done
  if (State.remainingPeople.length === 0 || State.remainingGames.length === 0) {
    setTimeout(showEndBanner, 1200);
  }
}

/* ══════════════════════════════════════════════════════════
   6. RESULT & HISTORY UI
══════════════════════════════════════════════════════════ */

function showResults(person, game) {
  DOM.personResult.textContent = person;
  DOM.gameResult.textContent   = game;
  DOM.personResultCard.classList.add('has-result');
  DOM.gameResultCard.classList.add('has-result');
}

function clearResultCards() {
  DOM.personResult.textContent = '—';
  DOM.gameResult.textContent   = '—';
  DOM.personResultCard.classList.remove('has-result');
  DOM.gameResultCard.classList.remove('has-result');
}

function setDrawButtonState(state) {
  if (state === 'spinning') {
    DOM.drawBtn.disabled = true;
    DOM.drawBtnText.textContent = 'جارٍ السحب...';
  } else {
    DOM.drawBtn.disabled = false;
    DOM.drawBtnText.textContent = 'بدء السحب';
  }
}

function updateRemainingBadges() {
  DOM.peopleRemaining.textContent = State.remainingPeople.length;
  DOM.gamesRemaining.textContent  = State.remainingGames.length;
}

function showEndBanner() {
  DOM.endBanner.hidden = false;
  DOM.drawBtn.disabled = true;
  DOM.endBanner.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function hideEndBanner() {
  DOM.endBanner.hidden = true;
  DOM.drawBtn.disabled = false;
}

/**
 * Render the history table, optionally filtered by a search term.
 */
function renderHistory(filter = '') {
  const tbody = DOM.historyBody;
  tbody.innerHTML = '';

  const term = filter.trim().toLowerCase();
  const rows = term
    ? State.history.filter(e =>
        e.person.toLowerCase().includes(term) ||
        e.game.toLowerCase().includes(term)
      )
    : State.history;

  if (rows.length === 0) {
    DOM.historyEmpty.style.display = 'block';
    DOM.historyTable.style.display = 'none';
    return;
  }

  DOM.historyEmpty.style.display = 'none';
  DOM.historyTable.style.display = 'table';

  rows.forEach((entry, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${State.history.indexOf(entry) + 1}</td>
      <td>${escapeHtml(entry.person)}</td>
      <td>${escapeHtml(entry.game)}</td>
      <td>${escapeHtml(entry.time)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ══════════════════════════════════════════════════════════
   7. CONFETTI ENGINE
══════════════════════════════════════════════════════════ */

const Confetti = (() => {
  const canvas  = document.getElementById('confettiCanvas');
  const ctx     = canvas.getContext('2d');
  let particles = [];
  let animId    = null;

  const COLORS = [
    '#006C35', '#0F8A4B', '#1AA35C', '#FFD700',
    '#FFFFFF', '#3DC97F', '#52D98F', '#B2DFDB'
  ];

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  function createParticle(x, y) {
    return {
      x, y,
      vx:     (Math.random() - 0.5) * 12,
      vy:     -(Math.random() * 14 + 6),
      size:   Math.random() * 8 + 4,
      color:  COLORS[Math.floor(Math.random() * COLORS.length)],
      rotation: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.2,
      gravity: 0.35,
      drag:    0.98,
      alpha:   1,
      shape:   Math.random() > 0.5 ? 'rect' : 'circle'
    };
  }

  function burst() {
    resize();
    particles = [];
    const cx = canvas.width / 2;
    const cy = canvas.height * 0.4;
    for (let i = 0; i < 160; i++) {
      particles.push(createParticle(
        cx + (Math.random() - 0.5) * 200,
        cy + (Math.random() - 0.5) * 100
      ));
    }
    if (animId) cancelAnimationFrame(animId);
    animate();
  }

  function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles = particles.filter(p => p.alpha > 0.02);

    particles.forEach(p => {
      p.vy += p.gravity;
      p.vx *= p.drag;
      p.vy *= p.drag;
      p.x  += p.vx;
      p.y  += p.vy;
      p.rotation += p.rotSpeed;
      if (p.y > canvas.height * 0.7) p.alpha -= 0.025;

      ctx.save();
      ctx.globalAlpha = p.alpha;
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation);
      ctx.fillStyle = p.color;

      if (p.shape === 'rect') {
        ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
      } else {
        ctx.beginPath();
        ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    });

    if (particles.length > 0) {
      animId = requestAnimationFrame(animate);
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  }

  window.addEventListener('resize', resize);
  resize();

  return { burst };
})();

/* ══════════════════════════════════════════════════════════
   8. SOUND ENGINE
══════════════════════════════════════════════════════════ */

const Sound = (() => {
  let ctx = null;

  function getCtx() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    return ctx;
  }

  function playTone(frequency, type, duration, gainValue = 0.3, delay = 0) {
    try {
      const ac  = getCtx();
      const osc = ac.createOscillator();
      const gain = ac.createGain();

      osc.connect(gain);
      gain.connect(ac.destination);

      osc.type      = type;
      osc.frequency.setValueAtTime(frequency, ac.currentTime + delay);
      gain.gain.setValueAtTime(gainValue, ac.currentTime + delay);
      gain.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + delay + duration);

      osc.start(ac.currentTime + delay);
      osc.stop(ac.currentTime + delay + duration);
    } catch (e) { /* AudioContext not available */ }
  }

  function playSpinStart() {
    // Rising sweep
    try {
      const ac   = getCtx();
      const osc  = ac.createOscillator();
      const gain = ac.createGain();
      osc.connect(gain);
      gain.connect(ac.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(200, ac.currentTime);
      osc.frequency.exponentialRampToValueAtTime(600, ac.currentTime + 0.3);
      gain.gain.setValueAtTime(0.2, ac.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.4);
      osc.start(ac.currentTime);
      osc.stop(ac.currentTime + 0.4);
    } catch (e) { /* noop */ }
  }

  function playWin() {
    // Triumphant chord
    const notes = [523, 659, 784, 1047];
    notes.forEach((freq, i) => {
      playTone(freq, 'sine', 0.5, 0.25, i * 0.08);
    });
  }

  return { playSpinStart, playWin };
})();

/* ══════════════════════════════════════════════════════════
   9. SIDE PANEL
══════════════════════════════════════════════════════════ */

function openPanel() {
  // Populate textareas
  DOM.peopleEditor.value = State.people.join('\n');
  DOM.gamesEditor.value  = State.games.join('\n');
  updatePanelCounts();

  DOM.sidePanel.classList.add('open');
  DOM.panelOverlay.classList.add('active');
  DOM.panelOverlay.setAttribute('aria-hidden', 'false');
  DOM.sidePanel.setAttribute('aria-hidden', 'false');
  DOM.closePanelBtn.focus();
}

function closePanel() {
  DOM.sidePanel.classList.remove('open');
  DOM.panelOverlay.classList.remove('active');
  DOM.panelOverlay.setAttribute('aria-hidden', 'true');
  DOM.sidePanel.setAttribute('aria-hidden', 'true');
  DOM.editListsBtn.focus();
}

function updatePanelCounts() {
  const pCount = DOM.peopleEditor.value.split('\n').filter(l => l.trim()).length;
  const gCount = DOM.gamesEditor.value.split('\n').filter(l => l.trim()).length;
  DOM.peopleCount.textContent = pCount;
  DOM.gamesCount.textContent  = gCount;
}

function savePanelChanges() {
  const newPeople = DOM.peopleEditor.value
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.length > 0);
  const newGames = DOM.gamesEditor.value
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.length > 0);

  if (newPeople.length === 0 || newGames.length === 0) {
    alert('يجب أن تحتوي كل قائمة على عنصر واحد على الأقل.');
    return;
  }

  State.people  = newPeople;
  State.games   = newGames;

  // Reset remaining to full new lists
  State.remainingPeople = [...newPeople];
  State.remainingGames  = [...newGames];

  // Reset angles
  State.peopleAngle = 0;
  State.gamesAngle  = 0;

  persistState();
  updateRemainingBadges();
  redrawWheels();
  hideEndBanner();
  clearResultCards();
  renderHistory();
  closePanel();
}

function resetLists() {
  if (!confirm('هل تريد إعادة تعيين القوائم إلى القيم الافتراضية؟')) return;
  State.people  = [...CONFIG.defaultPeople];
  State.games   = [...CONFIG.defaultGames];
  State.remainingPeople = [...State.people];
  State.remainingGames  = [...State.games];
  State.peopleAngle = 0;
  State.gamesAngle  = 0;
  persistState();
  updateRemainingBadges();
  redrawWheels();
  hideEndBanner();
  clearResultCards();
  DOM.peopleEditor.value = State.people.join('\n');
  DOM.gamesEditor.value  = State.games.join('\n');
  updatePanelCounts();
}

/* ══════════════════════════════════════════════════════════
   10. DARK MODE
══════════════════════════════════════════════════════════ */

function applyDarkMode(dark) {
  document.getElementById('appBody').classList.toggle('dark-mode', dark);
  DOM.moonIcon.style.display = dark ? 'none'  : 'block';
  DOM.sunIcon.style.display  = dark ? 'block' : 'none';
  // Redraw wheels to pick up new CSS variable colors
  redrawWheels();
}

function toggleDarkMode() {
  State.darkMode = !State.darkMode;
  applyDarkMode(State.darkMode);
  persistState();
}

/* ══════════════════════════════════════════════════════════
   11. FULLSCREEN
══════════════════════════════════════════════════════════ */

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}

function onFullscreenChange() {
  const isFs = !!document.fullscreenElement;
  DOM.fullscreenEnterIcon.style.display = isFs ? 'none'  : 'block';
  DOM.fullscreenExitIcon.style.display  = isFs ? 'block' : 'none';
}

/* ══════════════════════════════════════════════════════════
   12. CSV EXPORT
══════════════════════════════════════════════════════════ */

function exportCSV() {
  if (State.history.length === 0) {
    alert('لا توجد نتائج للتصدير بعد.');
    return;
  }

  const BOM  = '\uFEFF'; // UTF-8 BOM for Arabic in Excel
  const rows = [['#', 'الشخص', 'اللعبة', 'الوقت']];
  State.history.forEach((e, i) => {
    rows.push([i + 1, e.person, e.game, e.time]);
  });

  const csv = BOM + rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `سجل_السحب_${new Date().toLocaleDateString('ar-SA').replace(/\//g, '-')}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/* ══════════════════════════════════════════════════════════
   13. HISTORY SEARCH & CLEAR
══════════════════════════════════════════════════════════ */

function clearHistory() {
  if (!confirm('هل تريد مسح سجل السحب بالكامل؟')) return;
  State.history = [];
  persistState();
  renderHistory();
}

/* ══════════════════════════════════════════════════════════
   14. RESET DRAW
══════════════════════════════════════════════════════════ */

function resetDraw() {
  if (!confirm('هل تريد إعادة تعيين السحب؟ سيتم استعادة جميع الأسماء والألعاب.')) return;
  State.remainingPeople = [...State.people];
  State.remainingGames  = [...State.games];
  State.peopleAngle     = 0;
  State.gamesAngle      = 0;
  persistState();
  updateRemainingBadges();
  redrawWheels();
  hideEndBanner();
  clearResultCards();
}

/* ══════════════════════════════════════════════════════════
   DOM REFERENCES
══════════════════════════════════════════════════════════ */

const DOM = {};

function cacheDOM() {
  DOM.peopleCanvas      = document.getElementById('peopleCanvas');
  DOM.gamesCanvas       = document.getElementById('gamesCanvas');
  DOM.drawBtn           = document.getElementById('drawBtn');
  DOM.drawBtnText       = document.getElementById('drawBtnText');
  DOM.resetDrawBtn      = document.getElementById('resetDrawBtn');
  DOM.endBanner         = document.getElementById('endBanner');
  DOM.endResetBtn       = document.getElementById('endResetBtn');
  DOM.personResult      = document.getElementById('personResult');
  DOM.gameResult        = document.getElementById('gameResult');
  DOM.personResultCard  = document.getElementById('personResultCard');
  DOM.gameResultCard    = document.getElementById('gameResultCard');
  DOM.peopleRemaining   = document.getElementById('peopleRemaining');
  DOM.gamesRemaining    = document.getElementById('gamesRemaining');
  DOM.historyBody       = document.getElementById('historyBody');
  DOM.historyTable      = document.getElementById('historyTable');
  DOM.historyEmpty      = document.getElementById('historyEmpty');
  DOM.historySearch     = document.getElementById('historySearch');
  DOM.clearHistoryBtn   = document.getElementById('clearHistoryBtn');
  DOM.editListsBtn      = document.getElementById('editListsBtn');
  DOM.sidePanel         = document.getElementById('sidePanel');
  DOM.panelOverlay      = document.getElementById('panelOverlay');
  DOM.closePanelBtn     = document.getElementById('closePanelBtn');
  DOM.peopleEditor      = document.getElementById('peopleEditor');
  DOM.gamesEditor       = document.getElementById('gamesEditor');
  DOM.peopleCount       = document.getElementById('peopleCount');
  DOM.gamesCount        = document.getElementById('gamesCount');
  DOM.savePanelBtn      = document.getElementById('savePanelBtn');
  DOM.resetListsBtn     = document.getElementById('resetListsBtn');
  DOM.soundBtn          = document.getElementById('soundBtn');
  DOM.soundOnIcon       = document.getElementById('soundOnIcon');
  DOM.soundOffIcon      = document.getElementById('soundOffIcon');
  DOM.darkModeBtn       = document.getElementById('darkModeBtn');
  DOM.moonIcon          = document.getElementById('moonIcon');
  DOM.sunIcon           = document.getElementById('sunIcon');
  DOM.fullscreenBtn     = document.getElementById('fullscreenBtn');
  DOM.fullscreenEnterIcon = document.getElementById('fullscreenEnterIcon');
  DOM.fullscreenExitIcon  = document.getElementById('fullscreenExitIcon');
  DOM.exportBtn         = document.getElementById('exportBtn');
}

/* ══════════════════════════════════════════════════════════
   WHEEL REDRAW HELPER
══════════════════════════════════════════════════════════ */

function redrawWheels() {
  resizeCanvas(DOM.peopleCanvas);
  resizeCanvas(DOM.gamesCanvas);
  drawWheel(DOM.peopleCanvas, State.remainingPeople, State.peopleAngle);
  drawWheel(DOM.gamesCanvas,  State.remainingGames,  State.gamesAngle);
}

/* ══════════════════════════════════════════════════════════
   SOUND TOGGLE
══════════════════════════════════════════════════════════ */

function toggleSound() {
  State.soundEnabled = !State.soundEnabled;
  DOM.soundOnIcon.style.display  = State.soundEnabled ? 'block' : 'none';
  DOM.soundOffIcon.style.display = State.soundEnabled ? 'none'  : 'block';
  persistState();
}

/* ══════════════════════════════════════════════════════════
   15. INITIALIZATION
══════════════════════════════════════════════════════════ */

function bindEvents() {
  // Draw
  DOM.drawBtn.addEventListener('click', startDraw);
  DOM.resetDrawBtn.addEventListener('click', resetDraw);
  DOM.endResetBtn.addEventListener('click', () => { resetDraw(); hideEndBanner(); });

  // Panel
  DOM.editListsBtn.addEventListener('click', openPanel);
  DOM.closePanelBtn.addEventListener('click', closePanel);
  DOM.panelOverlay.addEventListener('click', closePanel);
  DOM.savePanelBtn.addEventListener('click', savePanelChanges);
  DOM.resetListsBtn.addEventListener('click', resetLists);
  DOM.peopleEditor.addEventListener('input', updatePanelCounts);
  DOM.gamesEditor.addEventListener('input', updatePanelCounts);

  // Toolbar
  DOM.soundBtn.addEventListener('click', toggleSound);
  DOM.darkModeBtn.addEventListener('click', toggleDarkMode);
  DOM.fullscreenBtn.addEventListener('click', toggleFullscreen);
  DOM.exportBtn.addEventListener('click', exportCSV);

  // History
  DOM.historySearch.addEventListener('input', (e) => renderHistory(e.target.value));
  DOM.clearHistoryBtn.addEventListener('click', clearHistory);

  // Fullscreen change
  document.addEventListener('fullscreenchange', onFullscreenChange);

  // Resize: redraw wheels on window resize
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(redrawWheels, 100);
  });

  // Keyboard: Escape closes panel
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && DOM.sidePanel.classList.contains('open')) {
      closePanel();
    }
    // Space / Enter on draw button
    if ((e.key === ' ' || e.key === 'Enter') && document.activeElement === DOM.drawBtn) {
      e.preventDefault();
      startDraw();
    }
  });
}

function init() {
  cacheDOM();
  loadState();
  applyDarkMode(State.darkMode);

  // Sound icon initial state
  DOM.soundOnIcon.style.display  = State.soundEnabled ? 'block' : 'none';
  DOM.soundOffIcon.style.display = State.soundEnabled ? 'none'  : 'block';

  // Initial wheel draw (after layout paint)
  requestAnimationFrame(() => {
    redrawWheels();
  });

  updateRemainingBadges();
  renderHistory();
  bindEvents();

  // If already exhausted on load
  if (State.remainingPeople.length === 0 || State.remainingGames.length === 0) {
    showEndBanner();
  }
}

// Start when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
