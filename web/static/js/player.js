/**
 * web/static/js/player.js - Video Player & Beatbar Synchronizer.
 * 
 * Manages:
 * - HTML5 video streaming with hardware acceleration and byte range seeking.
 * - High-precision 60-120 FPS requestAnimationFrame render loop with the Beatbar.
 * - Screen shake camera punch zoom on beat hits.
 * - Timeline scrubber with zone markers and the iconic white square knob.
 * - Vertical sound changing popup slider.
 * - 2.5s idle inactivity collapse leaving only video and floating beatbar.
 * - Android touch gestures: double tap left/right to skip 5s, tap to toggle UI.
 * - Keyboard shortcuts (Space, Arrows, M, S, F, N, Esc).
 */

class WebPlayer {
  constructor(app) {
    this.app = app;
    this.video = document.getElementById('media-video');
    this.videoContainer = document.getElementById('video-transform-container');
    this.canvas = document.getElementById('beatbar-canvas');
    this.playerUi = document.querySelector('.player-ui');
    this.beatbarContainer = document.querySelector('.beatbar-container');

    // UI Elements
    this.btnPlayPause = document.getElementById('btn-play-pause');
    this.iconPlayPause = document.getElementById('icon-play-pause');
    this.btnBackLibrary = document.getElementById('btn-back-library');
    this.btnNextVideo = document.getElementById('btn-next-video');
    this.playerTitle = document.getElementById('player-video-title');
    this.playerLevelName = document.getElementById('player-level-name');
    this.btnFullscreen = document.getElementById('btn-fullscreen');
    this.iconFullscreen = document.getElementById('icon-fullscreen');
    this.btnSound = document.getElementById('btn-sound');
    this.soundPopup = document.getElementById('sound-popup');
    this.soundSliderTrack = document.getElementById('sound-slider-track');
    this.soundSliderFill = document.getElementById('sound-slider-fill');
    this.soundSliderThumb = document.getElementById('sound-slider-thumb');
    this.soundPct = document.getElementById('sound-pct');
    this.btnSpeed = document.getElementById('btn-speed');
    this.btnShake = document.getElementById('btn-shake');
    this.btnLoop = document.getElementById('btn-loop');
    this.scrubberContainer = document.getElementById('scrubber-container');
    this.scrubberTrack = document.getElementById('scrubber-track');
    this.scrubberFill = document.getElementById('scrubber-fill');
    this.scrubberKnob = document.getElementById('scrubber-knob');
    this.scrubberKnobIcon = document.getElementById('scrubber-knob-icon');
    this.scrubberTooltip = document.getElementById('scrubber-tooltip');
    this.timeDisplay = document.getElementById('player-time-display');
    this.autoplayOverlay = document.getElementById('autoplay-overlay');
    this.btnBigPlay = document.getElementById('btn-big-play');
    this.btnSkipCredits = document.getElementById('btn-skip-credits');
    this.activeCreditsZone = null;

    // Flash overlay
    this.flashOverlay = document.getElementById('player-flash-overlay');
    this.flashAlpha = 0.0;

    // Touch gesture elements
    this.touchLayer = document.querySelector('.touch-gesture-layer');
    this.touchLeft = document.querySelector('.touch-left');
    this.touchRight = document.querySelector('.touch-right');
    this.rippleLeft = this.touchLeft.querySelector('.seek-ripple');
    this.rippleRight = this.touchRight.querySelector('.seek-ripple');

    // State
    this.currentVideoMeta = null;
    this.playlist = [];
    this.playlistIndex = -1;
    this.speeds = [0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0];
    this.currentSpeedIdx = 3; // 1.0x
    this.screenShakeEnabled = true;
    this.currentZoom = 1.0;
    this.isDraggingScrubber = false;
    this.isDraggingSound = false;
    this.levels = [];
    this.levelMode = 'ramp_within_level';
    this.currentLevel = 1;
    this.currentDifficulty = 'Normal';

    // Inactivity timer (2.5 seconds default, configurable)
    this.inactivityTimeout = null;
    this.isUserActive = true;

    // Double tap detector
    this._lastTapLeft = 0;
    this._lastTapRight = 0;
    this._tapLeftTimer = null;
    this._tapRightTimer = null;

    // Continuous clock interpolation for 60-120 FPS on Android
    this._clockTime = 0.0;
    this._lastPerfTime = performance.now();
    this._lastScrubberUpdateTime = 0;

    // Skin Customization & Track Switcher Elements
    this.btnSkinSelector = document.getElementById('btn-skin-selector');
    this.activeSkinBadge = document.getElementById('active-skin-badge');
    this.modalSkinPicker = document.getElementById('modal-skin-picker');
    this.skinsGrid = document.getElementById('skins-grid');
    this.btnLibSkin = document.getElementById('btn-lib-skin');
    this.trackSelectorGroup = document.getElementById('track-selector-group');
    this.trackBtns = document.querySelectorAll('.track-btn');

    this.availableSkins = [];
    this.currentSkinId = localStorage.getItem('beatmake_active_skin') || 'cyber_wings';
    this.currentTrack = localStorage.getItem('beatmake_active_track') || 'all';

    // Initialize Beatbar Widget
    this.beatbar = new BeatBarWidget(
      this.canvas,
      (targetTime) => this.seek(targetTime),
      (beat, isIntenseOrBurst) => this._onBeatHit(beat, isIntenseOrBurst)
    );

    // Initialize Extended Player Settings
    this._initSettings();

    this._bindEvents();
    this._startAnimLoop();
  }

  _bindEvents() {
    // Video events
    this.video.addEventListener('loadedmetadata', () => {
      this.beatbar.setDuration(this.video.duration);
      this._updateTimeDisplay();
      this._renderScrubberZones(this.beatbar.zones);
      this._renderScrubberChapters(this.levels);
    });

    this.video.addEventListener('timeupdate', () => {
      if (!this.isDraggingScrubber) {
        this._updateScrubber(this.video.currentTime);
      }
      this._updateTimeDisplay();
    });

    this.video.addEventListener('play', () => {
      this._updatePlayPauseUI(true);
      this._resetInactivityTimer();
      this.autoplayOverlay.classList.remove('active');
    });

    this.video.addEventListener('pause', () => {
      this._updatePlayPauseUI(false);
      this._showControls();
    });

    this.video.addEventListener('ended', () => {
      if (!this.video.loop && this.playlist.length > 1) {
        this.playNext();
      }
    });

    // Play / Pause Buttons
    this.btnPlayPause.addEventListener('click', () => this.togglePlayPause());
    this.scrubberKnob.addEventListener('click', (e) => {
      e.stopPropagation();
      this.togglePlayPause();
    });
    this.btnBigPlay.addEventListener('click', () => {
      this.video.play().catch(e => console.log('Autoplay error:', e));
    });

    // Back to library
    this.btnBackLibrary.addEventListener('click', () => {
      this.video.pause();
      this.app.showView('library');
    });

    // Next Video
    this.btnNextVideo.addEventListener('click', () => this.playNext());

    // Fullscreen
    this.btnFullscreen.addEventListener('click', () => this.toggleFullscreen());
    document.addEventListener('fullscreenchange', () => this._onFullscreenChange());
    document.addEventListener('webkitfullscreenchange', () => this._onFullscreenChange());

    // Sound / Volume
    this.btnSound.addEventListener('click', (e) => {
      e.stopPropagation();
      this.soundPopup.classList.toggle('active');
    });

    document.addEventListener('click', (e) => {
      if (!this.soundPopup.contains(e.target) && e.target !== this.btnSound) {
        this.soundPopup.classList.remove('active');
      }
    });

    this._setupSoundSlider();

    // Speed restore & toggle
    const savedSpeed = parseFloat(localStorage.getItem('beatmake_player_speed')) || 1.0;
    const spdIdx = this.speeds.indexOf(savedSpeed);
    if (spdIdx >= 0) {
      this.currentSpeedIdx = spdIdx;
      this.video.playbackRate = savedSpeed;
      this.btnSpeed.textContent = `${savedSpeed}x`;
    }
    this.btnSpeed.addEventListener('click', () => {
      this.currentSpeedIdx = (this.currentSpeedIdx + 1) % this.speeds.length;
      const spd = this.speeds[this.currentSpeedIdx];
      this.video.playbackRate = spd;
      this.btnSpeed.textContent = `${spd}x`;
      localStorage.setItem('beatmake_player_speed', spd);
    });

    // Screen Shake restore & toggle
    const savedShake = localStorage.getItem('beatmake_screen_shake');
    if (savedShake !== null) {
      this.screenShakeEnabled = savedShake !== 'false';
      this.btnShake.classList.toggle('active', this.screenShakeEnabled);
    }
    this.btnShake.addEventListener('click', () => {
      this.screenShakeEnabled = !this.screenShakeEnabled;
      this.btnShake.classList.toggle('active', this.screenShakeEnabled);
      localStorage.setItem('beatmake_screen_shake', this.screenShakeEnabled);
      if (!this.screenShakeEnabled) {
        this.currentZoom = 1.0;
        this.videoContainer.style.transform = 'scale(1)';
      }
    });

    // Loop restore & toggle
    const savedLoop = localStorage.getItem('beatmake_player_loop');
    if (savedLoop !== null) {
      this.video.loop = savedLoop === 'true';
      this.btnLoop.classList.toggle('active', this.video.loop);
    }
    this.btnLoop.addEventListener('click', () => {
      this.video.loop = !this.video.loop;
      this.btnLoop.classList.toggle('active', this.video.loop);
      localStorage.setItem('beatmake_player_loop', this.video.loop);
    });

    // Scrubber interaction
    this._setupScrubber();

    // Inactivity & Tap UI Toggle
    this._setupInactivityAndGestures();

    // Skip Credits interaction
    if (this.btnSkipCredits) {
      this.btnSkipCredits.addEventListener('click', (e) => {
        e.stopPropagation();
        if (this.activeCreditsZone) {
          const endT = this.activeCreditsZone.end_time || 0;
          this.seek(endT);
          this.btnSkipCredits.style.display = 'none';
          this.activeCreditsZone = null;
        }
      });
    }

    // Keyboard Shortcuts
    this._setupKeyboard();

    // Skin Picker Triggers
    if (this.btnSkinSelector) {
      this.btnSkinSelector.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openSkinModal();
      });
    }
    if (this.btnLibSkin) {
      this.btnLibSkin.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openSkinModal();
      });
    }

    // Track Switcher Buttons
    this.trackBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.setTrack(btn.dataset.track);
      });
    });

    // Close skin modal if backdrop clicked
    if (this.modalSkinPicker) {
      this.modalSkinPicker.addEventListener('click', (e) => {
        if (e.target === this.modalSkinPicker) {
          this.closeSkinModal();
        }
      });
    }

    // Load available skins from server and initialize track
    this.loadSkins();
    this.setTrack(this.currentTrack);
  }

  // ==========================================================================
  // PLAYBACK CONTROL
  // ==========================================================================

  async loadVideo(videoMeta, playlist = []) {
    this.currentVideoMeta = videoMeta;
    this.playlist = playlist.length > 0 ? playlist : [videoMeta];
    this.playlistIndex = this.playlist.findIndex(v => v.id === videoMeta.id);

    // Update title
    this.playerTitle.textContent = videoMeta.title;

    // Load beatmap data from server
    try {
      const resp = await fetch(`/api/beats/${encodeURIComponent(videoMeta.filename)}`);
      if (resp.ok) {
        const beatData = await resp.json();
        this.beatbar.loadData(beatData.beats, beatData.zones, beatData.settings);
        this.levels = beatData.levels || [];
        this.levelMode = beatData.level_mode || 'ramp_within_level';
        this.currentLevel = beatData.level || 1;
        this.currentDifficulty = beatData.difficulty || 'Normal';
        this._renderScrubberZones(beatData.zones);
        this._renderScrubberChapters(this.levels);
        this._updateLevelDisplay(0.0);
        this._updateTrackCounts();
      } else {
        this.beatbar.loadData([], [], {});
        this.levels = [];
        this._renderScrubberZones([]);
        this._renderScrubberChapters([]);
        this._updateLevelDisplay(0.0);
        this._updateTrackCounts();
      }
    } catch (e) {
      console.warn('Failed to load beats:', e);
      this.beatbar.loadData([], [], {});
      this.levels = [];
      this._renderScrubberZones([]);
      this._renderScrubberChapters([]);
      this._updateLevelDisplay(0.0);
      this._updateTrackCounts();
    }

    // Apply user settings overrides
    this.beatbar.updateSettings(this.settings);

    // Check for bundled pack skin in .beat video
    try {
      const skinResp = await fetch(`/api/video_skin/${encodeURIComponent(videoMeta.filename)}`);
      if (skinResp.ok) {
        const packSkin = await skinResp.json();
        if (packSkin && packSkin.has_pack_skin) {
          this.beatbar.setSkin(packSkin);
          if (this.activeSkinBadge) {
            this.activeSkinBadge.textContent = packSkin.name || 'Pack Skin';
          }
        } else if (this.currentSkinId) {
          this.applySkin(this.currentSkinId, false);
        }
      } else if (this.currentSkinId) {
        this.applySkin(this.currentSkinId, false);
      }
    } catch (e) {
      if (this.currentSkinId) {
        this.applySkin(this.currentSkinId, false);
      }
    }

    // Set video source
    this.video.src = videoMeta.video_url;
    this.video.load();
    this._clockTime = 0.0;
    this._lastPerfTime = performance.now();

    // Attempt playback
    try {
      await this.video.play();
      this.autoplayOverlay.classList.remove('active');
    } catch (e) {
      // Browser autoplay policy blocked sound -> show tap-to-play prompt
      console.log('Autoplay blocked:', e);
      this.autoplayOverlay.classList.add('active');
    }

    this.beatbar.resize();
  }

  togglePlayPause() {
    if (this.video.paused) {
      this.video.play().catch(e => console.log('Play error:', e));
    } else {
      this.video.pause();
    }
  }

  seek(targetTime) {
    const t = Math.max(0, Math.min(this.video.duration || 1, targetTime));
    this.video.currentTime = t;
    this._clockTime = t;
    this._lastPerfTime = performance.now();
    this.beatbar.setTime(t);
    this._updateScrubber(t);
    this._updateTimeDisplay(t);
  }

  skip(seconds) {
    this.seek((this.video.currentTime || 0) + seconds);
  }

  playNext() {
    if (this.playlist.length === 0) return;
    const nextIdx = (this.playlistIndex + 1) % this.playlist.length;
    this.loadVideo(this.playlist[nextIdx], this.playlist);
  }

  // ==========================================================================
  // BEAT HIT & VISUAL REACTIONS (SCREEN SHAKE & FLASH)
  // ==========================================================================

  _onBeatHit(beat, isIntenseOrBurst) {
    // 1. Camera Punch Screen Shake
    const shakeMode = this.settings.shake_mode || 'intense_and_bursts';
    if (this.screenShakeEnabled && shakeMode !== 'off') {
      if (shakeMode === 'all' || isIntenseOrBurst) {
        this.currentZoom = 1.045;
        this.videoContainer.style.transform = `scale(${this.currentZoom})`;
      }
    }

    // 2. Visual Hit Flash Effect
    const hitEffect = this.settings.hit_effect || 'border_flash';
    if (hitEffect !== 'none' && this.flashOverlay) {
      this.flashAlpha = isIntenseOrBurst ? 0.85 : 0.55;
      this._applyFlashStyle(hitEffect);
    }
  }

  _applyFlashStyle(effect) {
    if (!this.flashOverlay) return;
    const color = this.settings.flash_color || '#e056fd';
    if (effect === 'border_flash' || effect === 'both') {
      this.flashOverlay.style.boxShadow = `inset 0 0 85px 35px ${color}`;
      this.flashOverlay.style.backgroundColor = 'transparent';
    } else if (effect === 'picture_flash') {
      this.flashOverlay.style.boxShadow = 'none';
      this.flashOverlay.style.backgroundColor = color;
    }
    this.flashOverlay.style.opacity = this.flashAlpha.toFixed(2);
  }

  // ==========================================================================
  // RENDER & SYNC LOOP (60-120 FPS)
  // ==========================================================================

  _startAnimLoop() {
    const loop = () => {
      const now = performance.now();
      const dt = Math.min(0.08, (now - this._lastPerfTime) / 1000.0);
      this._lastPerfTime = now;

      // Smooth clock interpolation between coarse video time updates
      if (!this.video.paused && !this.video.seeking && this.video.readyState >= 2) {
        const rate = this.video.playbackRate || 1.0;
        this._clockTime += dt * rate;

        const actualTime = this.video.currentTime || 0.0;
        const drift = actualTime - this._clockTime;

        if (Math.abs(drift) > 0.12) {
          this._clockTime = actualTime;
        } else if (Math.abs(drift) > 0.005) {
          this._clockTime += drift * 0.12;
        }
      } else {
        this._clockTime = this.video.currentTime || 0.0;
      }

      // Sync clock with Beatbar for buttery smooth 120 FPS (with latency calibration)
      const audioOffsetSec = (Number(this.settings.audio_offset) || 0) / 1000.0;
      this.beatbar.setTime(this._clockTime + audioOffsetSec);
      this.beatbar.render();

      // Throttle DOM scrubber updates to ~30 FPS to save mobile CPU/DOM layout work
      if (now - this._lastScrubberUpdateTime > 33) {
        this._lastScrubberUpdateTime = now;
        if (!this.isDraggingScrubber) {
          this._updateScrubber(this._clockTime);
        }
        this._updateTimeDisplay(this._clockTime);
      }

      // Screen shake spring decay
      if (this.currentZoom > 1.0) {
        this.currentZoom = Math.max(1.0, 1.0 + (this.currentZoom - 1.0) * 0.84);
        if (this.currentZoom <= 1.001) {
          this.currentZoom = 1.0;
          this.videoContainer.style.transform = '';
        } else {
          this.videoContainer.style.transform = `scale(${this.currentZoom})`;
        }
      }

      // Hit flash decay
      if (this.flashAlpha > 0.0) {
        this.flashAlpha = Math.max(0.0, this.flashAlpha - dt * 4.5);
        if (this.flashOverlay) {
          this.flashOverlay.style.opacity = this.flashAlpha > 0.01 ? this.flashAlpha.toFixed(2) : '0';
        }
      }

      // Check for skippable credits zone (anime streaming site style)
      if (this.btnSkipCredits) {
        const curT = this._clockTime;
        const creditsZone = (this.beatbar.zones || []).find(
          z => z.type === 'credits' && curT >= z.start_time && curT < z.end_time
        );
        if (creditsZone) {
          this.activeCreditsZone = creditsZone;
          this.btnSkipCredits.style.display = 'inline-flex';
        } else {
          this.activeCreditsZone = null;
          this.btnSkipCredits.style.display = 'none';
        }
      }

      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  // ==========================================================================
  // SCRUBBER & ZONES
  // ==========================================================================

  _renderScrubberZones(zones) {
    // Clear old zone elements
    const oldZones = this.scrubberTrack.querySelectorAll('.scrubber-zone-segment');
    oldZones.forEach(el => el.remove());

    if (!this.settings.show_timeline_zones) return;
    if (!zones || zones.length === 0) return;
    const duration = this.video.duration || 1.0;

    zones.forEach(z => {
      const seg = document.createElement('div');
      seg.className = `scrubber-zone-segment ${(z.type || '').toLowerCase()}`;
      const leftPct = (z.start_time / duration) * 100;
      const widthPct = Math.max(0.2, ((z.end_time - z.start_time) / duration) * 100);
      seg.style.left = `${leftPct}%`;
      seg.style.width = `${widthPct}%`;
      if (z.color) seg.style.backgroundColor = z.color;
      this.scrubberTrack.appendChild(seg);
    });
  }

  _renderScrubberChapters(levels) {
    // Clear old chapter breaks
    const oldBreaks = this.scrubberTrack.querySelectorAll('.scrubber-chapter-break');
    oldBreaks.forEach(el => el.remove());

    if (!levels || levels.length <= 1) return;
    const duration = this.video.duration || 1.0;

    for (let i = 1; i < levels.length; i++) {
      const ch = levels[i];
      const st = Number(ch.start_time || 0);
      if (st > 0 && st < duration) {
        const breakEl = document.createElement('div');
        breakEl.className = 'scrubber-chapter-break';
        const leftPct = (st / duration) * 100;
        breakEl.style.left = `${leftPct}%`;
        this.scrubberTrack.appendChild(breakEl);
      }
    }
  }

  _setupScrubber() {
    const seekFromPos = (clientX) => {
      const rect = this.scrubberTrack.getBoundingClientRect();
      const norm = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const targetTime = norm * (this.video.duration || 1.0);
      this.seek(targetTime);
    };

    const handleStart = (clientX) => {
      this.isDraggingScrubber = true;
      seekFromPos(clientX);
    };

    const handleMove = (clientX) => {
      if (!this.isDraggingScrubber) return;
      seekFromPos(clientX);
    };

    const handleEnd = () => {
      this.isDraggingScrubber = false;
    };

    this.scrubberContainer.addEventListener('mousedown', (e) => handleStart(e.clientX));
    window.addEventListener('mousemove', (e) => handleMove(e.clientX));
    window.addEventListener('mouseup', handleEnd);

    // Hover tooltip for YouTube-style chapter and time preview
    this.scrubberContainer.addEventListener('mousemove', (e) => {
      if (this.isDraggingScrubber) return;
      const rect = this.scrubberTrack.getBoundingClientRect();
      const norm = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const hoverTime = norm * (this.video.duration || 1.0);
      
      let foundCh = null;
      if (this.levels && this.levels.length > 0) {
        foundCh = this.levels.find(ch => hoverTime >= (ch.start_time || 0) && hoverTime <= (ch.end_time || this.video.duration || 99999));
      }
      
      if (this.scrubberTooltip) {
        if (foundCh) {
          const stStr = this._formatTime(foundCh.start_time || 0);
          const etStr = this._formatTime(foundCh.end_time || this.video.duration || 0);
          this.scrubberTooltip.textContent = `${foundCh.name} • ${foundCh.difficulty} [${stStr} - ${etStr}]`;
        } else {
          this.scrubberTooltip.textContent = this._formatTime(hoverTime);
        }
        this.scrubberTooltip.style.left = `${norm * 100}%`;
        this.scrubberTooltip.style.display = 'block';
      }
    });

    this.scrubberContainer.addEventListener('mouseleave', () => {
      if (this.scrubberTooltip) {
        this.scrubberTooltip.style.display = 'none';
      }
    });

    this.scrubberContainer.addEventListener('touchstart', (e) => {
      if (e.touches.length > 0) handleStart(e.touches[0].clientX);
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
      if (this.isDraggingScrubber && e.touches.length > 0) {
        handleMove(e.touches[0].clientX);
      }
    }, { passive: true });

    window.addEventListener('touchend', handleEnd);
  }

  _updateScrubber(timeSec) {
    const duration = this.video.duration || 1.0;
    const progress = Math.max(0, Math.min(1, timeSec / duration));
    const pct = progress * 100;

    this.scrubberFill.style.width = `${pct}%`;
    this.scrubberKnob.style.left = `${pct}%`;
    this._updateLevelDisplay(timeSec);
  }

  _updateLevelDisplay(timeSec) {
    if (!this.playerLevelName) return;
    let activeCh = null;
    if (this.levels && this.levels.length > 0) {
      activeCh = this.levels.find(ch => timeSec >= (ch.start_time || 0) && timeSec <= (ch.end_time || 99999));
    }
    if (activeCh) {
      this.playerLevelName.textContent = `${activeCh.name} • ${activeCh.difficulty}`;
    } else if (this.currentDifficulty) {
      this.playerLevelName.textContent = `Level ${this.currentLevel || 1} • ${this.currentDifficulty}`;
    } else {
      this.playerLevelName.textContent = '';
    }
  }

  _updateTimeDisplay(timeSec) {
    const t = typeof timeSec === 'number' ? timeSec : (this.video.currentTime || 0);
    const cur = this._formatTime(t);
    const dur = this._formatTime(this.video.duration || 0);
    this.timeDisplay.textContent = `${cur} / ${dur}`;
  }

  _formatTime(seconds) {
    const s = Math.floor(seconds % 60);
    const m = Math.floor(seconds / 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  _updatePlayPauseUI(isPlaying) {
    // Play/Pause icon in bottom bar
    const playSvg = '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
    const pauseSvg = '<rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>';
    this.iconPlayPause.innerHTML = isPlaying ? pauseSvg : playSvg;

    // Knob inside icon
    this.scrubberKnobIcon.innerHTML = isPlaying ? pauseSvg : playSvg;
  }

  // ==========================================================================
  // SOUND / VOLUME
  // ==========================================================================

  _setupSoundSlider() {
    const updateVol = (clientY) => {
      const rect = this.soundSliderTrack.getBoundingClientRect();
      const norm = Math.max(0, Math.min(1, (rect.bottom - clientY) / rect.height));
      this.video.volume = norm;
      this.soundSliderFill.style.height = `${norm * 100}%`;
      this.soundSliderThumb.style.bottom = `${norm * 100}%`;
      this.soundPct.textContent = `${Math.round(norm * 100)}%`;
      localStorage.setItem('beatmake_player_volume', norm.toFixed(3));
    };

    const handleStart = (clientY) => {
      this.isDraggingSound = true;
      updateVol(clientY);
    };

    const handleMove = (clientY) => {
      if (!this.isDraggingSound) return;
      updateVol(clientY);
    };

    const handleEnd = () => {
      this.isDraggingSound = false;
    };

    this.soundSliderTrack.addEventListener('mousedown', (e) => handleStart(e.clientY));
    window.addEventListener('mousemove', (e) => handleMove(e.clientY));
    window.addEventListener('mouseup', handleEnd);

    this.soundSliderTrack.addEventListener('touchstart', (e) => {
      if (e.touches.length > 0) handleStart(e.touches[0].clientY);
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
      if (this.isDraggingSound && e.touches.length > 0) {
        handleMove(e.touches[0].clientY);
      }
    }, { passive: true });

    window.addEventListener('touchend', handleEnd);

    // Initial value (saved from localStorage, or default 20% sound)
    const savedVolStr = localStorage.getItem('beatmake_player_volume');
    const initVol = savedVolStr !== null ? Math.max(0, Math.min(1, parseFloat(savedVolStr))) : 0.20;
    this.video.volume = initVol;
    const volPct = Math.round(initVol * 100);
    this.soundSliderFill.style.height = `${volPct}%`;
    this.soundSliderThumb.style.bottom = `${volPct}%`;
    this.soundPct.textContent = `${volPct}%`;
  }

  // ==========================================================================
  // INACTIVITY AUTO-COLLAPSE & GESTURES
  // ==========================================================================

  _setupInactivityAndGestures() {
    const poke = () => this._resetInactivityTimer();

    window.addEventListener('mousemove', poke);
    window.addEventListener('mousedown', poke);
    window.addEventListener('keydown', poke);
    window.addEventListener('touchstart', poke, { passive: true });

    // Touch Layer Double Tap to Skip / Single Tap to Toggle UI
    // Uses dedicated touchstart handlers with e.preventDefault() to eliminate delayed click collisions
    const handleGesture = (side, e) => {
      if (e.type === 'touchstart') {
        e.preventDefault();
      }
      poke();

      const isLeft = (side === 'left');
      const now = performance.now();
      const lastTap = isLeft ? this._lastTapLeft : this._lastTapRight;
      const timerKey = isLeft ? '_tapLeftTimer' : '_tapRightTimer';
      const ripple = isLeft ? this.rippleLeft : this.rippleRight;
      const skipSeconds = isLeft ? -5 : 5;

      if (now - lastTap < 300) {
        // Double tap confirmed: clear pending single-tap toggle
        if (this[timerKey]) {
          clearTimeout(this[timerKey]);
          this[timerKey] = null;
        }
        if (isLeft) this._lastTapLeft = 0;
        else this._lastTapRight = 0;

        this.skip(skipSeconds);
        this._triggerRipple(ripple);
      } else {
        // First tap: record timestamp and debounce single tap toggle
        if (isLeft) this._lastTapLeft = now;
        else this._lastTapRight = now;

        if (this[timerKey]) {
          clearTimeout(this[timerKey]);
        }
        this[timerKey] = setTimeout(() => {
          this._toggleControls();
          if (isLeft) this._lastTapLeft = 0;
          else this._lastTapRight = 0;
          this[timerKey] = null;
        }, 300);
      }
    };

    this.touchLeft.addEventListener('touchstart', (e) => handleGesture('left', e), { passive: false });
    this.touchLeft.addEventListener('click', (e) => handleGesture('left', e));

    this.touchRight.addEventListener('touchstart', (e) => handleGesture('right', e), { passive: false });
    this.touchRight.addEventListener('click', (e) => handleGesture('right', e));
  }

  _triggerRipple(el) {
    el.classList.add('active');
    setTimeout(() => el.classList.remove('active'), 400);
  }

  _showControls() {
    this.playerUi.classList.remove('idle-hidden');
    this.isUserActive = true;
    if (this.inactivityTimeout) clearTimeout(this.inactivityTimeout);
  }

  _hideControls() {
    if (!this.video.paused) {
      this.playerUi.classList.add('idle-hidden');
      this.soundPopup.classList.remove('active');
      this.isUserActive = false;
    }
  }

  _toggleControls() {
    if (this.playerUi.classList.contains('idle-hidden')) {
      this._showControls();
      this._resetInactivityTimer();
    } else {
      this._hideControls();
    }
  }

  _resetInactivityTimer() {
    this._showControls();
    if (this.inactivityTimeout) clearTimeout(this.inactivityTimeout);

    const delaySec = Number(this.settings?.auto_hide);
    if (delaySec === 0) return; // Never hide
    const delayMs = (delaySec || 2.5) * 1000;

    if (!this.video.paused) {
      this.inactivityTimeout = setTimeout(() => {
        this._hideControls();
      }, delayMs);
    }
  }

  // ==========================================================================
  // FULLSCREEN & ORIENTATION
  // ==========================================================================

  toggleFullscreen() {
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      const el = document.documentElement;
      if (el.requestFullscreen) {
        el.requestFullscreen();
      } else if (el.webkitRequestFullscreen) {
        el.webkitRequestFullscreen();
      }
      // On Android / mobile, attempt orientation lock to landscape
      if (screen.orientation && screen.orientation.lock) {
        screen.orientation.lock('landscape').catch(() => {});
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
      if (screen.orientation && screen.orientation.unlock) {
        screen.orientation.unlock();
      }
    }
  }

  _onFullscreenChange() {
    const isFull = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
    const expandSvg = '<polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line>';
    const shrinkSvg = '<polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line>';
    this.iconFullscreen.innerHTML = isFull ? shrinkSvg : expandSvg;
    setTimeout(() => this.beatbar.resize(), 100);
  }

  // ==========================================================================
  // KEYBOARD SHORTCUTS
  // ==========================================================================

  _setupKeyboard() {
    window.addEventListener('keydown', (e) => {
      // Only process when player view is active
      const playerView = document.getElementById('view-player');
      if (!playerView || !playerView.classList.contains('active')) return;

      if (['input', 'textarea'].includes(document.activeElement.tagName.toLowerCase())) return;

      switch (e.code) {
        case 'Space':
          e.preventDefault();
          this.togglePlayPause();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          this.skip(-5);
          break;
        case 'ArrowRight':
          e.preventDefault();
          this.skip(5);
          break;
        case 'ArrowUp':
          e.preventDefault();
          this.video.volume = Math.min(1, this.video.volume + 0.05);
          this.soundSliderFill.style.height = `${this.video.volume * 100}%`;
          this.soundSliderThumb.style.bottom = `${this.video.volume * 100}%`;
          this.soundPct.textContent = `${Math.round(this.video.volume * 100)}%`;
          localStorage.setItem('beatmake_player_volume', this.video.volume.toFixed(3));
          break;
        case 'ArrowDown':
          e.preventDefault();
          this.video.volume = Math.max(0, this.video.volume - 0.05);
          this.soundSliderFill.style.height = `${this.video.volume * 100}%`;
          this.soundSliderThumb.style.bottom = `${this.video.volume * 100}%`;
          this.soundPct.textContent = `${Math.round(this.video.volume * 100)}%`;
          localStorage.setItem('beatmake_player_volume', this.video.volume.toFixed(3));
          break;
        case 'KeyM':
          this.video.muted = !this.video.muted;
          break;
        case 'KeyS':
          this.btnShake.click();
          break;
        case 'KeyF':
          this.toggleFullscreen();
          break;
        case 'KeyN':
          this.playNext();
          break;
        case 'KeyT':
          e.preventDefault();
          this.cycleTrack();
          break;
        case 'Escape':
          if (this.modalSettings && this.modalSettings.classList.contains('active')) {
            this.closeSettingsModal();
          } else if (this.modalSkinPicker && this.modalSkinPicker.classList.contains('active')) {
            this.closeSkinModal();
          } else if (document.fullscreenElement || document.webkitFullscreenElement) {
            this.toggleFullscreen();
          } else {
            this.video.pause();
            this.app.showView('library');
          }
          break;
      }
    });
  }

  // ==========================================================================
  // TRACK SELECTION (ALL / T1 / T2 / T3)
  // ==========================================================================

  setTrack(track) {
    this.currentTrack = track || 'all';
    this.beatbar.setTrack(this.currentTrack);
    localStorage.setItem('beatmake_active_track', this.currentTrack);

    this.trackBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.track === String(this.currentTrack));
    });
  }

  cycleTrack() {
    const tracks = ['all', '1', '2', '3'];
    const curIdx = tracks.indexOf(String(this.currentTrack));
    const nextIdx = (curIdx + 1) % tracks.length;
    this.setTrack(tracks[nextIdx]);
    const label = tracks[nextIdx] === 'all' ? 'All Tracks' : `Track ${tracks[nextIdx]}`;
    this.app.showToast(`Active Track: ${label}`);
  }

  _updateTrackCounts() {
    const counts = this.beatbar.getTrackCounts();
    const allSpan = document.getElementById('track-count-all');
    const t1Span = document.getElementById('track-count-1');
    const t2Span = document.getElementById('track-count-2');
    const t3Span = document.getElementById('track-count-3');

    if (allSpan) allSpan.textContent = counts.all > 0 ? ` (${counts.all})` : '';
    if (t1Span) t1Span.textContent = counts[1] > 0 ? ` (${counts[1]})` : '';
    if (t2Span) t2Span.textContent = counts[2] > 0 ? ` (${counts[2]})` : '';
    if (t3Span) t3Span.textContent = counts[3] > 0 ? ` (${counts[3]})` : '';

    this.trackBtns.forEach(btn => {
      const t = btn.dataset.track;
      const count = t === 'all' ? counts.all : (counts[t] || 0);
      btn.classList.toggle('empty-track', count === 0 && counts.all > 0);
    });
  }

  // ==========================================================================
  // SKIN CUSTOMIZATION
  // ==========================================================================

  async loadSkins() {
    try {
      const resp = await fetch('/api/skins');
      if (resp.ok) {
        const data = await resp.json();
        this.availableSkins = data.skins || [];
        this._renderSkinsGrid();

        // Apply saved or default skin
        const savedSkin = this.availableSkins.find(s => s.id === this.currentSkinId) || this.availableSkins[0];
        if (savedSkin) {
          this.applySkin(savedSkin.id, false);
        }
      }
    } catch (e) {
      console.warn('Failed to load skins:', e);
    }
  }

  _renderSkinsGrid() {
    if (!this.skinsGrid) return;
    this.skinsGrid.innerHTML = '';

    for (const skin of this.availableSkins) {
      const card = document.createElement('div');
      card.className = `skin-card ${skin.id === this.currentSkinId ? 'active' : ''}`;
      card.dataset.skinId = skin.id;

      const p = skin.palette || {};
      const primaryCol = p.primary || '#be2edd';
      const accentCol = p.accent || '#e056fd';
      const targetCol = p.target || '#9b51e0';
      const glowCol = p.glow || '#f368e0';

      const comps = skin.components || {};
      const compBadges = Object.keys(comps).map(role => {
        const label = role.replace('_', ' ');
        return `<span class="skin-comp-badge">${label}</span>`;
      }).join('');

      card.innerHTML = `
        <div class="skin-card-header">
          <div class="skin-card-titles">
            <h4 class="skin-title">${skin.name}</h4>
            <span class="skin-author">by ${skin.author || 'User'}</span>
          </div>
          <div class="skin-active-indicator" title="Currently Selected Skin">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </div>
        </div>
        ${skin.description ? `<p class="skin-desc">${skin.description}</p>` : ''}
        <div class="skin-palette-bar">
          <span class="palette-swatch" style="background-color: ${primaryCol}; box-shadow: 0 0 6px ${primaryCol}80;" title="Primary: ${primaryCol}"></span>
          <span class="palette-swatch" style="background-color: ${accentCol}; box-shadow: 0 0 6px ${accentCol}80;" title="Accent: ${accentCol}"></span>
          <span class="palette-swatch" style="background-color: ${targetCol}; box-shadow: 0 0 6px ${targetCol}80;" title="Target: ${targetCol}"></span>
          <span class="palette-swatch" style="background-color: ${glowCol}; box-shadow: 0 0 6px ${glowCol}80;" title="Glow: ${glowCol}"></span>
          <span class="palette-label">${p.name || skin.name}</span>
        </div>
        <div class="skin-components-row">
          ${compBadges}
        </div>
      `;

      card.addEventListener('click', () => {
        this.applySkin(skin.id, true);
      });

      this.skinsGrid.appendChild(card);
    }
  }

  applySkin(skinId, showToast = true) {
    const skin = this.availableSkins.find(s => s.id === skinId);
    if (!skin) return;

    this.currentSkinId = skin.id;
    localStorage.setItem('beatmake_active_skin', skin.id);

    // Update beatbar widget in real time
    this.beatbar.setSkin(skin);

    // Update top bar badge
    if (this.activeSkinBadge) {
      this.activeSkinBadge.textContent = skin.name;
    }

    // Update card selection state
    if (this.skinsGrid) {
      this.skinsGrid.querySelectorAll('.skin-card').forEach(card => {
        card.classList.toggle('active', card.dataset.skinId === skin.id);
      });
    }

    if (showToast) {
      this.app.showToast(`Applied skin: ${skin.name}`);
    }
  }

  openSkinModal() {
    if (this.modalSkinPicker) {
      this.modalSkinPicker.classList.add('active');
    }
  }

  closeSkinModal() {
    if (this.modalSkinPicker) {
      this.modalSkinPicker.classList.remove('active');
    }
  }

  // ==========================================================================
  // EXTENDED PLAYER & VISUAL SETTINGS
  // ==========================================================================

  _initSettings() {
    this.defaultSettings = {
      lead_time: 1.5,
      beat_scale: 100,
      beats_skin: 'custom',
      hit_effect: 'border_flash',
      flash_color: '#e056fd',
      shake_mode: 'intense_and_bursts',
      show_timeline_zones: true,
      audio_offset: 0,
      auto_hide: 2.5,
      default_author: 'User'
    };

    let saved = {};
    try {
      const stored = localStorage.getItem('beatmake_web_settings');
      if (stored) saved = JSON.parse(stored);
    } catch (e) {}
    this.settings = Object.assign({}, this.defaultSettings, saved);

    // DOM controls
    this.btnSettings = document.getElementById('btn-player-settings');
    this.modalSettings = document.getElementById('modal-settings');
    this.btnSaveSettings = document.getElementById('btn-save-settings');
    this.btnResetSettings = document.getElementById('btn-reset-settings');

    this.inputLeadTime = document.getElementById('set-lead-time');
    this.valLeadTime = document.getElementById('set-lead-time-val');
    this.inputBeatScale = document.getElementById('set-beat-scale');
    this.valBeatScale = document.getElementById('set-beat-scale-val');
    this.selectBeatsSkin = document.getElementById('set-beats-skin');
    this.selectHitEffect = document.getElementById('set-hit-effect');
    this.inputFlashColor = document.getElementById('set-flash-color');
    this.valFlashColor = document.getElementById('set-flash-color-val');
    this.selectShakeMode = document.getElementById('set-shake-mode');
    this.checkTimelineZones = document.getElementById('set-timeline-zones');
    this.inputAudioOffset = document.getElementById('set-audio-offset');
    this.valAudioOffset = document.getElementById('set-audio-offset-val');
    this.selectAutoHide = document.getElementById('set-auto-hide');
    this.inputDefaultAuthor = document.getElementById('set-default-author');

    // Cache & Storage controls
    this.statPreviews = document.getElementById('stat-previews-info');
    this.statThumbnails = document.getElementById('stat-thumbnails-info');
    this.statExtracted = document.getElementById('stat-extracted-info');
    this.statUnused = document.getElementById('stat-unused-info');
    this.btnCleanUnused = document.getElementById('btn-clean-unused-cache');
    this.btnClearPreviews = document.getElementById('btn-clear-previews');

    this._syncSettingsToUI();

    if (this.btnSettings) {
      this.btnSettings.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openSettingsModal();
      });
    }

    if (this.btnCleanUnused) {
      this.btnCleanUnused.addEventListener('click', async () => {
        try {
          this.btnCleanUnused.disabled = true;
          this.btnCleanUnused.textContent = 'Cleaning...';
          const resp = await fetch('/api/cache/clean_unused', { method: 'POST' });
          const data = await resp.json();
          if (data.success) {
            this.app.showToast(`Cleaned unused cache: freed ${data.freed_bytes_formatted}!`);
            await this.loadCacheStats();
          } else {
            this.app.showToast('Clean cache failed');
          }
        } catch (e) {
          this.app.showToast('Error cleaning cache');
        } finally {
          this.btnCleanUnused.disabled = false;
          this.btnCleanUnused.innerHTML = `
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            <span>Clean Unused Cache</span>
          `;
        }
      });
    }

    if (this.btnClearPreviews) {
      this.btnClearPreviews.addEventListener('click', async () => {
        if (!confirm('Clear all 5-second preview clips? They will re-render automatically on demand.')) return;
        try {
          this.btnClearPreviews.disabled = true;
          this.btnClearPreviews.textContent = 'Purging...';
          const resp = await fetch('/api/cache/clear_previews', { method: 'POST' });
          const data = await resp.json();
          if (data.success) {
            this.app.showToast(`Purged ${data.deleted_count} previews (${data.freed_bytes_formatted} freed)`);
            await this.loadCacheStats();
          } else {
            this.app.showToast('Failed to clear previews');
          }
        } catch (e) {
          this.app.showToast('Error clearing previews');
        } finally {
          this.btnClearPreviews.disabled = false;
          this.btnClearPreviews.innerHTML = `
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            <span>Clear All Previews</span>
          `;
        }
      });
    }

    if (this.btnSaveSettings) {
      this.btnSaveSettings.addEventListener('click', () => {
        this._saveSettingsFromUI();
        this.closeSettingsModal();
        this.app.showToast('Settings saved!');
      });
    }

    if (this.btnResetSettings) {
      this.btnResetSettings.addEventListener('click', () => {
        this.settings = Object.assign({}, this.defaultSettings);
        this._syncSettingsToUI();
        this._applyCurrentSettings();
        this.app.showToast('Settings reset to defaults');
      });
    }

    // Real-time preview bindings
    if (this.inputLeadTime) {
      this.inputLeadTime.addEventListener('input', (e) => {
        if (this.valLeadTime) this.valLeadTime.textContent = `${Number(e.target.value).toFixed(1)}s`;
        this.settings.lead_time = Number(e.target.value);
        this.beatbar.updateSettings({ lead_time: this.settings.lead_time });
      });
    }
    if (this.inputBeatScale) {
      this.inputBeatScale.addEventListener('input', (e) => {
        if (this.valBeatScale) this.valBeatScale.textContent = `${e.target.value}%`;
        this.settings.beat_scale = Number(e.target.value);
        this.beatbar.updateSettings({ beat_scale: this.settings.beat_scale });
      });
    }
    if (this.selectBeatsSkin) {
      this.selectBeatsSkin.addEventListener('change', (e) => {
        this.settings.beats_skin = e.target.value;
        this.beatbar.updateSettings({ beats_skin: this.settings.beats_skin });
      });
    }
    if (this.selectHitEffect) {
      this.selectHitEffect.addEventListener('change', (e) => {
        this.settings.hit_effect = e.target.value;
      });
    }
    if (this.inputFlashColor) {
      this.inputFlashColor.addEventListener('input', (e) => {
        if (this.valFlashColor) this.valFlashColor.textContent = e.target.value;
        this.settings.flash_color = e.target.value;
      });
    }
    if (this.selectShakeMode) {
      this.selectShakeMode.addEventListener('change', (e) => {
        this.settings.shake_mode = e.target.value;
      });
    }
    if (this.checkTimelineZones) {
      this.checkTimelineZones.addEventListener('change', (e) => {
        this.settings.show_timeline_zones = e.target.checked;
        this._renderScrubberZones(this.beatbar.zones);
      });
    }
    if (this.inputAudioOffset) {
      this.inputAudioOffset.addEventListener('input', (e) => {
        if (this.valAudioOffset) this.valAudioOffset.textContent = `${e.target.value} ms`;
        this.settings.audio_offset = Number(e.target.value);
      });
    }
    if (this.selectAutoHide) {
      this.selectAutoHide.addEventListener('change', (e) => {
        this.settings.auto_hide = Number(e.target.value);
      });
    }
    if (this.inputDefaultAuthor) {
      this.inputDefaultAuthor.addEventListener('input', (e) => {
        this.settings.default_author = e.target.value.trim() || 'User';
      });
    }
  }

  _syncSettingsToUI() {
    if (this.inputLeadTime) {
      this.inputLeadTime.value = this.settings.lead_time;
      if (this.valLeadTime) this.valLeadTime.textContent = `${Number(this.settings.lead_time).toFixed(1)}s`;
    }
    if (this.inputBeatScale) {
      this.inputBeatScale.value = this.settings.beat_scale;
      if (this.valBeatScale) this.valBeatScale.textContent = `${this.settings.beat_scale}%`;
    }
    if (this.selectBeatsSkin) this.selectBeatsSkin.value = this.settings.beats_skin;
    if (this.selectHitEffect) this.selectHitEffect.value = this.settings.hit_effect;
    if (this.inputFlashColor) {
      this.inputFlashColor.value = this.settings.flash_color;
      if (this.valFlashColor) this.valFlashColor.textContent = this.settings.flash_color;
    }
    if (this.selectShakeMode) this.selectShakeMode.value = this.settings.shake_mode;
    if (this.checkTimelineZones) this.checkTimelineZones.checked = Boolean(this.settings.show_timeline_zones);
    if (this.inputAudioOffset) {
      this.inputAudioOffset.value = this.settings.audio_offset;
      if (this.valAudioOffset) this.valAudioOffset.textContent = `${this.settings.audio_offset} ms`;
    }
    if (this.selectAutoHide) this.selectAutoHide.value = String(this.settings.auto_hide);
    if (this.inputDefaultAuthor) this.inputDefaultAuthor.value = this.settings.default_author || 'User';
  }

  _saveSettingsFromUI() {
    if (this.inputLeadTime) this.settings.lead_time = Number(this.inputLeadTime.value);
    if (this.inputBeatScale) this.settings.beat_scale = Number(this.inputBeatScale.value);
    if (this.selectBeatsSkin) this.settings.beats_skin = this.selectBeatsSkin.value;
    if (this.selectHitEffect) this.settings.hit_effect = this.selectHitEffect.value;
    if (this.inputFlashColor) this.settings.flash_color = this.inputFlashColor.value;
    if (this.selectShakeMode) this.settings.shake_mode = this.selectShakeMode.value;
    if (this.checkTimelineZones) this.settings.show_timeline_zones = this.checkTimelineZones.checked;
    if (this.inputAudioOffset) this.settings.audio_offset = Number(this.inputAudioOffset.value);
    if (this.selectAutoHide) this.settings.auto_hide = Number(this.selectAutoHide.value);
    if (this.inputDefaultAuthor) this.settings.default_author = this.inputDefaultAuthor.value.trim() || 'User';

    this._applyCurrentSettings();
    try {
      localStorage.setItem('beatmake_web_settings', JSON.stringify(this.settings));
    } catch (e) {}
  }

  _applyCurrentSettings() {
    this.beatbar.updateSettings(this.settings);
    this._renderScrubberZones(this.beatbar.zones);
  }

  openSettingsModal() {
    if (this.modalSettings) {
      this._syncSettingsToUI();
      this.loadCacheStats();
      this.modalSettings.classList.add('active');
    }
  }

  async loadCacheStats() {
    if (!this.statPreviews) return;
    try {
      const resp = await fetch('/api/cache/stats');
      if (resp.ok) {
        const stats = await resp.json();
        if (this.statPreviews) this.statPreviews.textContent = `${stats.previews_count} clips (${stats.previews_size_formatted})`;
        if (this.statThumbnails) this.statThumbnails.textContent = `${stats.thumbnails_count} images (${stats.thumbnails_size_formatted})`;
        if (this.statExtracted) this.statExtracted.textContent = `${stats.extracted_count} files (${stats.extracted_size_formatted})`;
        if (this.statUnused) {
          this.statUnused.textContent = `${stats.unused_count} files (${stats.unused_size_formatted})`;
          const parentItem = this.statUnused.closest('.cache-stat-item');
          if (parentItem) {
            parentItem.classList.toggle('has-stale', stats.unused_count > 0);
          }
        }
      }
    } catch (e) {}
  }

  closeSettingsModal() {
    if (this.modalSettings) {
      this.modalSettings.classList.remove('active');
    }
  }
}
