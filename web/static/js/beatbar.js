/**
 * web/static/js/beatbar.js - High-Performance Stylized Beatbar Canvas Component.
 * 
 * Performance & Mobile Optimizations:
 * - Pre-rendered GPU texture sprites for beats (zero shadowBlur/re-rasterization per frame).
 * - Binary search O(log N) beat window lookup (iterates only 5-15 visible beats instead of 2,000+).
 * - DPR capped at 1.75 to eliminate excessive mobile fill-rate on 120Hz Full HD+ screens.
 * - Software shadowBlur filters completely eliminated for steady 120 FPS on Android GPUs.
 * - Compact size scaling adapted to smaller beatbar dimensions.
 */

class HitParticle {
  constructor(x, y, color) {
    this.x = x;
    this.y = y;
    const angle = Math.random() * Math.PI * 2;
    const speed = 30 + Math.random() * 90;
    this.vx = Math.cos(angle) * speed;
    this.vy = Math.sin(angle) * speed - (8 + Math.random() * 20);
    this.life = 1.0;
    this.decay = 2.8 + Math.random() * 2.2;
    this.size = 2.0 + Math.random() * 2.5;
    this.color = color;
  }

  update(dt) {
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.vy += 50 * dt;
    this.life = Math.max(0.0, this.life - this.decay * dt);
    return this.life > 0.0;
  }
}

class Shockwave {
  constructor(x, y, maxRadius, color) {
    this.x = x;
    this.y = y;
    this.radius = 6.0;
    this.maxRadius = maxRadius;
    this.life = 1.0;
    this.decay = 3.5;
    this.color = color;
  }

  update(dt) {
    this.life = Math.max(0.0, this.life - this.decay * dt);
    const progress = 1.0 - this.life;
    this.radius = 6.0 + (this.maxRadius - 6.0) * Math.sqrt(progress);
    return this.life > 0.0;
  }
}

class BeatBarWidget {
  constructor(canvasElement, onSeekCallback, onBeatHitCallback) {
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext('2d', { alpha: true });
    this.onSeek = onSeekCallback || (() => {});
    this.onBeatHit = onBeatHitCallback || (() => {});

    // State
    this.currentTime = 0.0;
    this.duration = 1.0;
    this.beats = [];
    this.zones = [];
    this.settings = {
      lead_time: 1.5,
      scroll_direction: 'rtl',
      intense_zones_direction: 'ltr',
      screen_shake: true,
      timeline_fill_mode: 'left_to_right'
    };

    // Beat processing & animation state
    this._hitBeatsSet = new Set();
    this.targetPopScale = 1.0;
    this.shockwaves = [];
    this.particles = [];
    this._lastAnimTime = performance.now();

    // Interaction state
    this._isDraggingTimeline = false;

    // Track state ('all', 1, 2, or 3)
    this.activeTrack = 'all';

    // Skin & Theme configuration
    this.currentSkin = null;
    this.skinImages = {};
    this.skinLayout = {};
    this.skinHitConfig = {};

    // Palette
    this.palette = {
      primary: '#be2edd',
      accent: '#e056fd',
      target: '#9b51e0',
      glow: '#f368e0',
      panel_border: '#d434ef',
      timeline_fill: '#ffffff'
    };

    // Pre-rendered sprites for zero-cost GPU blitting
    this.beatSprite = null;
    this.burstSprite = null;
    this.track2Sprite = null;
    this.track3Sprite = null;

    // Sizing & Headroom padding for wings and effects
    this.barWidth = 0;
    this.barHeight = 0;
    this.padTop = 0;
    this.padBottom = 0;
    this.padLeft = 0;
    this.padRight = 0;
    this.dpr = 1.0;
    this.notchElement = document.getElementById('beatbar-notch') || null;

    this._setupEvents();
    this.resize();
  }

  _setupEvents() {
    window.addEventListener('resize', () => this.resize());

    // Timeline notch interaction
    const getParentRect = () => {
      const parent = this.canvas.parentElement;
      return parent ? parent.getBoundingClientRect() : this.canvas.getBoundingClientRect();
    };

    const handleStart = (clientX) => {
      const pRect = getParentRect();
      const x = clientX - pRect.left;
      const notchL = pRect.width * 0.28;
      const notchR = pRect.width * 0.72;
      this._isDraggingTimeline = true;
      this._seekFromNotchX(x, notchL, notchR);
    };

    const handleMove = (clientX) => {
      if (!this._isDraggingTimeline) return;
      const pRect = getParentRect();
      const x = clientX - pRect.left;
      const notchL = pRect.width * 0.28;
      const notchR = pRect.width * 0.72;
      this._seekFromNotchX(x, notchL, notchR);
    };

    const handleEnd = () => {
      this._isDraggingTimeline = false;
    };

    const target = this.notchElement || this.canvas;
    target.addEventListener('mousedown', (e) => {
      e.stopPropagation();
      handleStart(e.clientX);
    });
    window.addEventListener('mousemove', (e) => handleMove(e.clientX));
    window.addEventListener('mouseup', handleEnd);

    target.addEventListener('touchstart', (e) => {
      if (e.touches.length > 0) {
        e.stopPropagation();
        handleStart(e.touches[0].clientX);
      }
    }, { passive: false });

    window.addEventListener('touchmove', (e) => {
      if (this._isDraggingTimeline && e.touches.length > 0) {
        handleMove(e.touches[0].clientX);
      }
    }, { passive: true });

    window.addEventListener('touchend', handleEnd);
  }

  _seekFromNotchX(mouseX, notchL, notchR) {
    const progress = Math.max(0.0, Math.min(1.0, (mouseX - notchL) / (notchR - notchL)));
    const targetTime = progress * this.duration;
    this.onSeek(targetTime);
  }

  resize() {
    const parent = this.canvas.parentElement;
    if (!parent) return;
    const parentRect = parent.getBoundingClientRect();
    if (!parentRect.width || !parentRect.height) return;

    this.barWidth = parentRect.width;
    this.barHeight = parentRect.height;
    this.cssWidth = this.barWidth;
    this.cssHeight = this.barHeight;

    if (!this.notchElement) {
      this.notchElement = document.getElementById('beatbar-notch');
    }

    // Dynamic headroom calculation for wings (e.g. overwatch.beat with offset_y=-50 and scale=1.88)
    const layout = this.skinLayout || {};
    const offYL = Number(layout.wing_left?.offset_y) || 0.0;
    const offYR = Number(layout.wing_right?.offset_y) || 0.0;
    const minWingY = Math.min(0.0, (0.12 + Math.min(offYL, offYR) / 100.0) * this.barHeight);

    const offXL = Number(layout.wing_left?.offset_x) || 0.0;
    const offXR = Number(layout.wing_right?.offset_x) || 0.0;
    const scaleR = Number(layout.wing_right?.scale) || 1.0;
    const minWingX = Math.min(0.0, (0.045 + offXL / 1000.0) * this.barWidth);
    const maxWingX = Math.max(this.barWidth, (0.955 + offXR / 1000.0) * this.barWidth + this.barHeight * 0.65 * (scaleR - 1.0));

    this.padTop = Math.max(65, Math.round(this.barHeight * 1.35), Math.round(Math.abs(minWingY) + 30));
    this.padBottom = Math.max(20, Math.round(this.barHeight * 0.35));
    this.padLeft = Math.max(50, Math.round(this.barWidth * 0.08), Math.round(Math.abs(minWingX) + 30));
    this.padRight = Math.max(50, Math.round(this.barWidth * 0.08), Math.round(Math.max(0, maxWingX - this.barWidth) + 30));

    const totalCssWidth = this.barWidth + this.padLeft + this.padRight;
    const totalCssHeight = this.barHeight + this.padTop + this.padBottom;

    // Cap DPR to 1.75 on mobile to avoid fillrate choke on 120Hz screens
    const dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    this.dpr = dpr;

    this.canvas.style.position = 'absolute';
    this.canvas.style.left = (-this.padLeft) + 'px';
    this.canvas.style.top = (-this.padTop) + 'px';
    this.canvas.style.width = totalCssWidth + 'px';
    this.canvas.style.height = totalCssHeight + 'px';

    this.canvas.width = Math.round(totalCssWidth * dpr);
    this.canvas.height = Math.round(totalCssHeight * dpr);

    this._createCachedSprites();
  }

  _createCachedSprites() {
    // Generate pre-rendered beat sprite at 128x128
    const size = 128;
    const half = size / 2;

    const skinStyle = this.settings.beats_skin || 'custom';

    const makeSprite = (primary, accent, glowAura, customImg = null) => {
      const oc = document.createElement('canvas');
      oc.width = size;
      oc.height = size;
      const octx = oc.getContext('2d');

      // 1. Soft glowing aura via radial gradient (zero software blur needed)
      const aura = octx.createRadialGradient(half, half, half * 0.25, half, half, half * 0.95);
      aura.addColorStop(0.0, glowAura);
      aura.addColorStop(0.65, 'rgba(224, 86, 253, 0.2)');
      aura.addColorStop(1.0, 'rgba(224, 86, 253, 0.0)');
      octx.fillStyle = aura;
      octx.beginPath();
      octx.arc(half, half, half * 0.95, 0, Math.PI * 2);
      octx.fill();

      // Check if custom beat SVG image is loaded and ready (if skinStyle === 'custom')
      if (skinStyle === 'custom' && customImg && customImg.complete && customImg.naturalWidth > 0) {
        const pad = size * 0.16;
        octx.drawImage(customImg, pad, pad, size - pad * 2, size - pad * 2);
      } else if (skinStyle === 'orb') {
        // Radiant Energy Orb
        const r = half * 0.65;
        const grad = octx.createRadialGradient(half, half, 2, half, half, r);
        grad.addColorStop(0.0, '#ffffff');
        grad.addColorStop(0.4, accent);
        grad.addColorStop(0.85, primary);
        grad.addColorStop(1.0, 'transparent');
        octx.fillStyle = grad;
        octx.beginPath();
        octx.arc(half, half, r, 0, Math.PI * 2);
        octx.fill();

        octx.strokeStyle = '#ffffff';
        octx.lineWidth = 2.5;
        octx.beginPath();
        octx.arc(half, half, r * 0.85, 0, Math.PI * 2);
        octx.stroke();
      } else if (skinStyle === 'lane_bar') {
        // Colored Rhythm Bar / Pill
        const bw = half * 0.42;
        const bh = half * 0.85;
        const x = half - bw;
        const y = half - bh;
        const w = bw * 2;
        const h = bh * 2;
        const r = bw;

        octx.beginPath();
        octx.roundRect ? octx.roundRect(x, y, w, h, r) : octx.rect(x, y, w, h);
        const grad = octx.createLinearGradient(x, y, x + w, y);
        grad.addColorStop(0.0, primary);
        grad.addColorStop(0.5, '#ffffff');
        grad.addColorStop(1.0, accent);
        octx.fillStyle = grad;
        octx.fill();
        octx.strokeStyle = '#ffffff';
        octx.lineWidth = 2.0;
        octx.stroke();
      } else {
        // Fallback procedural diamond crest (or 'diamond' / 'crest')
        const dw = half * 0.88;
        const dh = half * 0.82;
        octx.beginPath();
        octx.moveTo(half, half - dh);
        octx.lineTo(half + dw, half);
        octx.lineTo(half, half + dh);
        octx.lineTo(half - dw, half);
        octx.closePath();

        const grad = octx.createRadialGradient(half, half, 2, half, half, dw);
        grad.addColorStop(0.0, '#ffffff');
        grad.addColorStop(0.35, accent);
        grad.addColorStop(1.0, primary);
        octx.fillStyle = grad;
        octx.fill();

        octx.strokeStyle = '#ffffff';
        octx.lineWidth = 2.5;
        octx.stroke();

        octx.beginPath();
        octx.moveTo(half, half - dh * 0.65);
        octx.lineTo(half, half + dh * 0.65);
        octx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
        octx.lineWidth = 1.8;
        octx.stroke();
      }

      return oc;
    };

    const beatImg = this.skinImages?.beat || null;
    this.beatSprite = makeSprite(this.palette.primary, this.palette.accent, this.palette.glow || 'rgba(243, 104, 224, 0.55)', beatImg);
    this.burstSprite = makeSprite('#ffa502', '#ffeaa7', 'rgba(255, 234, 167, 0.75)', beatImg);
    this.track2Sprite = makeSprite('#00f3ff', '#a0f9ff', 'rgba(0, 243, 255, 0.65)', beatImg);
    this.track3Sprite = makeSprite('#ffb300', '#ffe57f', 'rgba(255, 179, 0, 0.65)', beatImg);
  }

  setSkin(skinConfig) {
    if (!skinConfig) return;
    this.currentSkin = skinConfig;

    // 1. Update Palette
    if (skinConfig.palette) {
      this.palette = {
        primary: skinConfig.palette.primary || '#be2edd',
        accent: skinConfig.palette.accent || '#e056fd',
        target: skinConfig.palette.target || '#9b51e0',
        glow: skinConfig.palette.glow || '#f368e0',
        panel_border: skinConfig.palette.panel_border || '#d434ef',
        timeline_fill: skinConfig.palette.timeline_fill || '#ffffff'
      };
    }

    // 2. Update Layout & Hit settings
    this.skinLayout = skinConfig.layout || {};
    this.skinHitConfig = skinConfig.trigger_hit || {};

    // 3. Load Component Images
    const comps = skinConfig.components || {};
    this.skinImages = {};

    const roles = ['panel', 'wing_left', 'wing_right', 'target', 'target_hit', 'beat'];
    roles.forEach(role => {
      const url = comps[role];
      if (url) {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        // Ensure browser never serves stale disk-cached images for skins
        const bustUrl = url.includes('?') ? `${url}&_t=${Date.now()}` : `${url}?_t=${Date.now()}`;
        img.src = bustUrl;
        img.onload = () => {
          this.skinImages[role] = img;
          if (role === 'beat') {
            this._createCachedSprites();
          }
        };
      }
    });

    // Recreate sprites with new palette immediately
    this._createCachedSprites();
    this.resize();
  }

  setTrack(track) {
    // track can be 'all', 1, 2, or 3
    if (track === '1' || track === 1) this.activeTrack = 1;
    else if (track === '2' || track === 2) this.activeTrack = 2;
    else if (track === '3' || track === 3) this.activeTrack = 3;
    else this.activeTrack = 'all';

    this._hitBeatsSet.clear();
  }

  getBeatTrack(b) {
    if (b.track !== undefined && b.track !== null) {
      return Number(b.track);
    }
    const lane = b.lane !== undefined && b.lane !== null ? Number(b.lane) : 4;
    if (lane === 4 || lane === 0) return 1;
    if (lane === 1) return 2;
    if (lane === 2 || lane === 3) return 3;
    return 1;
  }

  _isBeatInActiveTrack(b) {
    if (this.activeTrack === 'all' || !this.activeTrack) return true;
    return this.getBeatTrack(b) === Number(this.activeTrack);
  }

  getTrackCounts() {
    let t1 = 0, t2 = 0, t3 = 0;
    for (const b of this.beats) {
      const t = this.getBeatTrack(b);
      if (t === 1) t1++;
      else if (t === 2) t2++;
      else if (t === 3) t3++;
    }
    return {
      all: this.beats.length,
      1: t1,
      2: t2,
      3: t3
    };
  }

  loadData(beats, zones, settings) {
    this.beats = beats || [];
    this.zones = zones || [];
    this.settings = { ...this.settings, ...(settings || {}) };
    this._hitBeatsSet.clear();
  }

  updateSettings(newSettings) {
    const oldSkin = this.settings.beats_skin;
    this.settings = { ...this.settings, ...(newSettings || {}) };
    if (newSettings && newSettings.beats_skin && newSettings.beats_skin !== oldSkin) {
      this._createCachedSprites();
    }
  }

  setDuration(sec) {
    this.duration = Math.max(0.1, Number(sec) || 1.0);
  }

  setTime(sec) {
    const oldTime = this.currentTime;
    this.currentTime = Math.max(0.0, Number(sec) || 0.0);

    // If seeking backward or major jump, reset hit tracking
    if (Math.abs(this.currentTime - oldTime) > 0.4) {
      this._hitBeatsSet.clear();
    }

    this._checkBeatHits(oldTime, this.currentTime);
  }

  // Binary search: finds index of first beat where beat.time >= targetTime
  _findFirstBeatIndex(targetTime) {
    let low = 0;
    let high = this.beats.length - 1;
    let result = this.beats.length;
    while (low <= high) {
      const mid = (low + high) >> 1;
      if (this.beats[mid].time >= targetTime) {
        result = mid;
        high = mid - 1;
      } else {
        low = mid + 1;
      }
    }
    return result;
  }

  _checkBeatHits(tPrev, tCurr) {
    if (!this.beats || this.beats.length === 0 || tCurr < tPrev) return;

    // Use binary search to check ONLY the beats in the hit interval
    const startIdx = this._findFirstBeatIndex(tPrev - 0.02);
    const windowEnd = tCurr + 0.03;

    for (let i = startIdx; i < this.beats.length; i++) {
      const b = this.beats[i];
      const bt = b.time;
      if (bt > windowEnd) break;

      // Filter by active track!
      if (!this._isBeatInActiveTrack(b)) continue;

      if (!this._hitBeatsSet.has(bt) && bt >= tPrev - 0.01) {
        this._hitBeatsSet.add(bt);
        const isIntenseOrBurst = Boolean(b.in_intense_zone || b.in_speedy_zone || b.is_burst);
        this._triggerHit(b, isIntenseOrBurst);
      }
    }

    // Keep set bounded so memory stays tiny
    if (this._hitBeatsSet.size > 200) {
      for (const t of this._hitBeatsSet) {
        if (t < tCurr - 2.0) this._hitBeatsSet.delete(t);
      }
    }
  }

  _triggerHit(beat, isIntenseOrBurst) {
    const W = this.barWidth || this.cssWidth;
    const H = this.barHeight || this.cssHeight;
    const centerX = W / 2.0;
    const centerY = H * 0.40;

    // Target scale pop from skin config or defaults
    const basePop = Number(this.skinHitConfig?.pop_scale) || 1.35;
    this.targetPopScale = isIntenseOrBurst ? Math.min(1.5, basePop * 1.08) : basePop;

    // Shockwave ring
    this.shockwaves.push(new Shockwave(centerX, centerY, H * 0.85, this.palette.glow));

    // Sparkling burst particles
    const pCount = isIntenseOrBurst ? 9 : 5;
    for (let i = 0; i < pCount; i++) {
      this.particles.push(new HitParticle(centerX, centerY, this.palette.glow));
    }

    // Emit hit event for screen shake
    this.onBeatHit(beat, isIntenseOrBurst);
  }

  getBeatDirection(b) {
    const bt = b.time;
    for (const z of this.zones) {
      if (z.start_time <= bt && bt <= z.end_time) {
        const ztype = (z.type || '').toLowerCase();
        if (['climax', 'edging', 'intense'].includes(ztype)) {
          return this.settings.intense_zones_direction || 'ltr';
        } else if (['speeding_up', 'speedy', 'fast'].includes(ztype)) {
          return 'both';
        } else if (['pause', 'slow'].includes(ztype)) {
          return 'rtl';
        }
      }
    }
    if (b.in_intense_zone || b.is_burst) {
      return this.settings.intense_zones_direction || 'ltr';
    }
    return this.settings.scroll_direction || 'rtl';
  }

  // ==========================================================================
  // RENDER LOOP (CALLED ON REQUEST ANIMATION FRAME)
  // ==========================================================================

  render() {
    const now = performance.now();
    const dt = Math.min(0.05, (now - this._lastAnimTime) / 1000.0);
    this._lastAnimTime = now;

    // Physics spring decay
    if (this.targetPopScale > 1.0) {
      this.targetPopScale = Math.max(1.0, this.targetPopScale - (this.targetPopScale - 1.0) * 14.0 * dt);
    }

    // Update shockwaves
    for (let i = this.shockwaves.length - 1; i >= 0; i--) {
      if (!this.shockwaves[i].update(dt)) {
        this.shockwaves.splice(i, 1);
      }
    }

    // Update particles
    for (let i = this.particles.length - 1; i >= 0; i--) {
      if (!this.particles[i].update(dt)) {
        this.particles.splice(i, 1);
      }
    }

    // Canvas drawing
    const ctx = this.ctx;
    const W = this.barWidth || this.cssWidth;
    const H = this.barHeight || this.cssHeight;
    const padL = this.padLeft || 0;
    const padT = this.padTop || 0;

    // Clear entire canvas buffer
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Apply DPR scale and translate origin to panel top-left
    const dpr = this.dpr || 1;
    ctx.scale(dpr, dpr);
    ctx.translate(padL, padT);

    // 1. Outer Angled Trapezoid Panel
    this._paintPanel(ctx, W, H);

    // 2. Wing Sigils at Left & Right
    this._paintWingSigils(ctx, W, H);

    // 3. Moving Approaching Beats (O(log N) indexed, GPU blitted)
    this._paintBeats(ctx, W, H);

    // 4. Central Target & Arrow Indicator
    this._paintTargetAndIndicator(ctx, W, H);

    // 5. Hit Visual Effects (Shockwaves & Particles)
    this._paintHitEffects(ctx);

    // 6. Secondary Timeline in Bottom Notch
    this._paintSmallTimeline(ctx, W, H);
  }

  // ==========================================================================
  // DRAWING METHODS (HIGH-PERFORMANCE ZERO SHADOWBLUR)
  // ==========================================================================

  _paintPanel(ctx, W, H) {
    const panelImg = this.skinImages?.panel;
    if (panelImg && panelImg.complete && panelImg.naturalWidth > 0) {
      ctx.drawImage(panelImg, 0, 0, W, H);
      return;
    }

    const x_left_wing_tip = W * 0.015;
    const y_top_wing = H * 0.10;
    const x_left_top = W * 0.045;
    const x_tab_l1 = W * 0.43;
    const x_tab_l2 = W * 0.445;
    const y_tab_top = H * 0.03;
    const x_tab_r2 = W * 0.555;
    const x_tab_r1 = W * 0.57;
    const x_right_top = W * 0.955;
    const x_right_wing_tip = W * 0.985;
    const y_bar_bottom = H * 0.76;
    const x_notch_r1 = W * 0.71;
    const x_notch_r2 = W * 0.70;
    const y_notch_bottom = H * 0.96;
    const x_notch_l2 = W * 0.30;
    const x_notch_l1 = W * 0.29;

    ctx.beginPath();
    ctx.moveTo(x_left_wing_tip, y_top_wing + H * 0.04);
    ctx.lineTo(x_left_top, y_top_wing);
    ctx.lineTo(x_tab_l1, y_top_wing);
    ctx.lineTo(x_tab_l2, y_tab_top);
    ctx.lineTo(x_tab_r2, y_tab_top);
    ctx.lineTo(x_tab_r1, y_top_wing);
    ctx.lineTo(x_right_top, y_top_wing);
    ctx.lineTo(x_right_wing_tip, y_top_wing + H * 0.04);
    ctx.lineTo(x_right_top, y_bar_bottom);
    ctx.lineTo(x_notch_r1, y_bar_bottom);
    ctx.lineTo(x_notch_r2, y_notch_bottom);
    ctx.lineTo(x_notch_l2, y_notch_bottom);
    ctx.lineTo(x_notch_l1, y_bar_bottom);
    ctx.lineTo(x_left_top, y_bar_bottom);
    ctx.closePath();

    // Metallic cyberpunk dark charcoal gradient
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0.0, '#24242c');
    grad.addColorStop(0.3, '#16161c');
    grad.addColorStop(0.7, '#0b0b10');
    grad.addColorStop(1.0, '#181820');
    ctx.fillStyle = grad;
    ctx.fill();

    // Border gradient
    const borderGrad = ctx.createLinearGradient(0, 0, W, 0);
    borderGrad.addColorStop(0.0, '#555562');
    borderGrad.addColorStop(0.2, this.palette.panel_border || '#d434ef');
    borderGrad.addColorStop(0.5, this.palette.glow || '#f368e0');
    borderGrad.addColorStop(0.8, this.palette.panel_border || '#d434ef');
    borderGrad.addColorStop(1.0, '#555562');
    ctx.strokeStyle = borderGrad;
    ctx.lineWidth = 1.8;
    ctx.stroke();

    // Top Rim Highlight
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 1.0;
    ctx.moveTo(W * 0.05, H * 0.12);
    ctx.lineTo(W * 0.43, H * 0.12);
    ctx.moveTo(W * 0.445, H * 0.05);
    ctx.lineTo(W * 0.555, H * 0.05);
    ctx.moveTo(W * 0.57, H * 0.12);
    ctx.lineTo(W * 0.95, H * 0.12);
    ctx.stroke();
  }

  _paintWingSigils(ctx, W, H) {
    const skinId = this.currentSkin?.id || '';
    const isClean = skinId === 'clean_template';
    const hasCustomWings = Boolean(this.skinImages?.wing_left || this.skinImages?.wing_right);
    if (isClean && !hasCustomWings) {
      return;
    }

    const layout = this.skinLayout || {};
    const scaleL = layout.wing_left?.scale || 1.0;
    const offXL = (layout.wing_left?.offset_x || 0.0) * (W / 1000.0);
    const offYL = (layout.wing_left?.offset_y || 0.0) * (H / 100.0);

    const scaleR = layout.wing_right?.scale || 1.0;
    const offXR = (layout.wing_right?.offset_x || 0.0) * (W / 1000.0);
    const offYR = (layout.wing_right?.offset_y || 0.0) * (H / 100.0);

    const baseW = H * 0.65;
    const baseH = H * 0.60;
    const baseY = H * 0.12;

    const imgL = this.skinImages?.wing_left;
    const imgR = this.skinImages?.wing_right;

    if (imgL && imgL.complete && imgL.naturalWidth > 0) {
      const wl = baseW * scaleL;
      const hl = baseH * scaleL;
      ctx.drawImage(imgL, W * 0.045 + offXL, baseY + offYL, wl, hl);
    } else {
      // Procedural left wing
      ctx.save();
      ctx.translate(W * 0.045 + baseW / 2 + offXL, baseY + baseH / 2 + offYL);
      ctx.beginPath();
      ctx.moveTo(-baseW * 0.45, -baseH * 0.2);
      ctx.lineTo(-baseW * 0.1, -baseH * 0.4);
      ctx.lineTo(baseW * 0.35, -baseH * 0.1);
      ctx.lineTo(baseW * 0.1, baseH * 0.35);
      ctx.lineTo(-baseW * 0.2, baseH * 0.1);
      ctx.closePath();
      ctx.fillStyle = 'rgba(155, 81, 224, 0.22)';
      ctx.fill();
      ctx.strokeStyle = this.palette.accent || 'rgba(224, 86, 253, 0.4)';
      ctx.lineWidth = 1.0;
      ctx.stroke();
      ctx.restore();
    }

    if (imgR && imgR.complete && imgR.naturalWidth > 0) {
      const wr = baseW * scaleR;
      const hr = baseH * scaleR;
      ctx.drawImage(imgR, W * 0.955 - wr + offXR, baseY + offYR, wr, hr);
    } else {
      // Procedural right wing (flipped)
      ctx.save();
      ctx.translate(W * 0.955 - baseW / 2 + offXR, baseY + baseH / 2 + offYR);
      ctx.scale(-1, 1);
      ctx.beginPath();
      ctx.moveTo(-baseW * 0.45, -baseH * 0.2);
      ctx.lineTo(-baseW * 0.1, -baseH * 0.4);
      ctx.lineTo(baseW * 0.35, -baseH * 0.1);
      ctx.lineTo(baseW * 0.1, baseH * 0.35);
      ctx.lineTo(-baseW * 0.2, baseH * 0.1);
      ctx.closePath();
      ctx.fillStyle = 'rgba(155, 81, 224, 0.22)';
      ctx.fill();
      ctx.strokeStyle = this.palette.accent || 'rgba(224, 86, 253, 0.4)';
      ctx.lineWidth = 1.0;
      ctx.stroke();
      ctx.restore();
    }
  }

  _paintBeats(ctx, W, H) {
    if (!this.beats || this.beats.length === 0 || !this.beatSprite) return;

    const leadTime = Number(this.settings.lead_time) || 1.5;
    const userScale = (Number(this.settings.beat_scale) || 100) / 100.0;
    const centerX = W / 2.0;
    const centerY = H * 0.42;
    const travelDistance = W * 0.43;
    const bw = H * 0.54 * userScale;
    const bh = H * 0.52 * userScale;
    const tNow = this.currentTime;

    const flipL = Boolean(this.skinLayout?.flip_left_beats);
    const flipR = Boolean(this.skinLayout?.flip_right_beats);

    // Binary search for visible window (checks only ~10 beats instead of 2000+)
    const startIdx = this._findFirstBeatIndex(tNow - 0.08);

    for (let i = startIdx; i < this.beats.length; i++) {
      const b = this.beats[i];
      const timeDiff = b.time - tNow;
      if (timeDiff > leadTime) break; // Beats are sorted by time, break early!

      // Filter by active track (all, 1, 2, or 3)
      if (!this._isBeatInActiveTrack(b)) continue;

      const normPos = timeDiff / leadTime;
      let alpha = 1.0;
      if (timeDiff < 0) {
        alpha = Math.max(0.0, 1.0 + timeDiff / 0.08);
      }

      const dirMode = this.getBeatDirection(b);

      if (dirMode === 'ltr') {
        const bx = centerX - normPos * travelDistance;
        const flip = bx < centerX ? flipL : flipR;
        this._drawSingleBeat(ctx, bx, centerY, bw, bh, b, alpha, flip);
      } else if (dirMode === 'both') {
        const bxRight = centerX + normPos * travelDistance;
        const bxLeft = centerX - normPos * travelDistance;
        this._drawSingleBeat(ctx, bxRight, centerY, bw, bh, b, alpha, flipR);
        this._drawSingleBeat(ctx, bxLeft, centerY, bw, bh, b, alpha, flipL);
      } else {
        const bx = centerX + normPos * travelDistance;
        const flip = bx > centerX ? flipR : flipL;
        this._drawSingleBeat(ctx, bx, centerY, bw, bh, b, alpha, flip);
      }
    }
  }

  _drawSingleBeat(ctx, bx, cy, bw, bh, beat, alpha, flip = false) {
    if (alpha <= 0.01) return;

    let sprite = this.beatSprite;
    if (beat.is_burst) {
      sprite = this.burstSprite;
    } else if (this.activeTrack === 'all') {
      const trk = this.getBeatTrack(beat);
      if (trk === 2 && this.track2Sprite) sprite = this.track2Sprite;
      else if (trk === 3 && this.track3Sprite) sprite = this.track3Sprite;
    }

    if (flip) {
      ctx.save();
      if (alpha < 0.99) ctx.globalAlpha = alpha;
      ctx.translate(bx, cy);
      ctx.scale(-1, 1);
      ctx.drawImage(sprite, -bw / 2, -bh / 2, bw, bh);
      ctx.restore();
    } else if (alpha < 0.99) {
      ctx.globalAlpha = alpha;
      ctx.drawImage(sprite, bx - bw / 2, cy - bh / 2, bw, bh);
      ctx.globalAlpha = 1.0;
    } else {
      ctx.drawImage(sprite, bx - bw / 2, cy - bh / 2, bw, bh);
    }
  }

  _paintTargetAndIndicator(ctx, W, H) {
    const centerX = W / 2.0;
    const centerY = H * 0.40;
    const scale = this.targetPopScale;

    const layout = this.skinLayout || {};
    const scaleT = Number(layout.target?.scale) || 1.0;
    const offXT = (Number(layout.target?.offset_x) || 0.0) * (W / 1000.0);
    const offYT = (Number(layout.target?.offset_y) || 0.0) * (H / 100.0);

    const tw = H * 0.85 * scale * scaleT;
    const th = H * 0.52 * scale * scaleT;
    const tx = centerX + offXT;
    const ty = centerY + offYT;

    ctx.save();
    ctx.translate(tx, ty);

    // Glowing aura when popped
    if (scale > 1.04) {
      ctx.beginPath();
      ctx.ellipse(0, 0, tw * 0.7, th * 0.7, 0, 0, Math.PI * 2);
      ctx.fillStyle = this.palette.glow || 'rgba(243, 104, 224, 0.4)';
      ctx.globalAlpha = Math.min(0.55, (scale - 1.0) * 1.5);
      ctx.fill();
      ctx.globalAlpha = 1.0;
    }

    const isHit = scale > 1.05;
    const targetHitImg = this.skinImages?.target_hit;
    const targetImg = this.skinImages?.target;

    const activeTargetImg = (isHit && targetHitImg && targetHitImg.complete && targetHitImg.naturalWidth > 0)
      ? targetHitImg
      : (targetImg && targetImg.complete && targetImg.naturalWidth > 0 ? targetImg : null);

    if (activeTargetImg) {
      ctx.drawImage(activeTargetImg, -tw / 2, -th / 2, tw, th);
    } else {
      // Target Diamond Outer
      ctx.beginPath();
      ctx.moveTo(0, -th / 2);
      ctx.lineTo(tw / 2, 0);
      ctx.lineTo(0, th / 2);
      ctx.lineTo(-tw / 2, 0);
      ctx.closePath();

      ctx.fillStyle = 'rgba(155, 81, 224, 0.45)';
      ctx.fill();
      ctx.strokeStyle = this.palette.glow || '#f368e0';
      ctx.lineWidth = 1.8;
      ctx.stroke();

      // Inner Target Crystal
      const inW = tw * 0.55;
      const inH = th * 0.55;
      ctx.beginPath();
      ctx.moveTo(0, -inH / 2);
      ctx.lineTo(inW / 2, 0);
      ctx.lineTo(0, inH / 2);
      ctx.lineTo(-inW / 2, 0);
      ctx.closePath();

      const inGrad = ctx.createLinearGradient(0, -inH / 2, 0, inH / 2);
      inGrad.addColorStop(0, '#ffffff');
      inGrad.addColorStop(0.5, this.palette.accent || '#e056fd');
      inGrad.addColorStop(1, this.palette.target || '#9b51e0');
      ctx.fillStyle = inGrad;
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.0;
      ctx.stroke();
    }

    ctx.restore();

    // Customizable Hit Indicator beneath Target
    const hitCfg = this.skinHitConfig || {};
    const showInd = hitCfg.show_indicator !== false;
    if (showInd) {
      const indStyle = hitCfg.indicator_style || 'triangle';
      const indColor = hitCfg.indicator_color || '#ffffff';
      const arrowY = H * 0.76 + offYT;
      const arrowH = H * 0.12 * scaleT;
      const arrowW = arrowH * 1.3;
      const indX = centerX + offXT;

      ctx.save();
      ctx.fillStyle = indColor;
      ctx.strokeStyle = this.palette.panel_border || '#d434ef';
      ctx.lineWidth = 1.0;

      if (indStyle === 'diamond') {
        const dh = arrowH * 1.08;
        const dw = dh * 0.76;
        ctx.beginPath();
        ctx.moveTo(indX, arrowY - dh);
        ctx.lineTo(indX + dw / 2.0, arrowY - dh / 2.0);
        ctx.lineTo(indX, arrowY);
        ctx.lineTo(indX - dw / 2.0, arrowY - dh / 2.0);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      } else if (indStyle === 'glow_bar') {
        const bw = arrowH * 2.2;
        const bh = arrowH * 0.4;
        ctx.beginPath();
        ctx.rect(indX - bw / 2.0, arrowY - bh, bw, bh);
        ctx.fill();
        ctx.strokeStyle = this.palette.glow || '#f368e0';
        ctx.stroke();
      } else if (indStyle !== 'hidden' && indStyle !== 'off') {
        // 'triangle'
        ctx.beginPath();
        ctx.moveTo(indX, arrowY - arrowH);
        ctx.lineTo(indX + arrowW / 2, arrowY);
        ctx.lineTo(indX - arrowW / 2, arrowY);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
      ctx.restore();
    }
  }

  _paintHitEffects(ctx) {
    // Shockwaves (lightweight alpha stroke, no shadowBlur)
    for (const sw of this.shockwaves) {
      ctx.beginPath();
      ctx.ellipse(sw.x, sw.y, sw.radius, sw.radius * 0.6, 0, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(243, 104, 224, ${sw.life * 0.85})`;
      ctx.lineWidth = 2.0 * sw.life + 0.8;
      ctx.stroke();
    }

    // Particles
    for (const p of this.particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, 255, 255, ${p.life * 0.85})`;
      ctx.fill();
    }
  }

  _paintSmallTimeline(ctx, W, H) {
    const notchL = W * 0.30;
    const notchR = W * 0.70;
    const notchW = notchR - notchL;
    const notchY = H * 0.80;
    const notchH = H * 0.14;

    // Track background
    ctx.fillStyle = '#101014';
    ctx.strokeStyle = '#333338';
    ctx.lineWidth = 1.0;
    this._roundRect(ctx, notchL, notchY, notchW, notchH, 2.5);
    ctx.fill();
    ctx.stroke();

    // Active progress
    const progress = Math.max(0.0, Math.min(1.0, this.currentTime / Math.max(0.1, this.duration)));
    const fillW = notchW * progress;

    if (fillW > 1.0) {
      const fillGrad = ctx.createLinearGradient(notchL, notchY, notchL + fillW, notchY);
      fillGrad.addColorStop(0.0, this.palette.primary);
      fillGrad.addColorStop(0.85, this.palette.accent);
      fillGrad.addColorStop(1.0, '#ffffff');

      ctx.fillStyle = fillGrad;
      this._roundRect(ctx, notchL, notchY, fillW, notchH, 2.5);
      ctx.fill();

      // White glowing tip line
      ctx.beginPath();
      ctx.moveTo(notchL + fillW, notchY);
      ctx.lineTo(notchL + fillW, notchY + notchH);
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.8;
      ctx.stroke();
    }
  }

  _roundRect(ctx, x, y, w, h, r) {
    if (w < 2 * r) r = w / 2;
    if (h < 2 * r) r = h / 2;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
}
