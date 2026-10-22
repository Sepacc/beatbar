/**
 * web/static/js/library.js - Library View Controller.
 * 
 * Manages:
 * - Loading and rendering the video collection.
 * - Multi-attribute search and filters:
 *   - Search input (title, filename)
 *   - Status tabs (All, With Beats, Missing Beats)
 *   - Difficulty (All, Easy, Normal, Hard, Expert)
 *   - Duration (All, <2m, 2-4m, >4m)
 *   - Rating (All, 5 Stars, 4+ Stars, 3+ Stars, Unrated)
 *   - Sort Order (Date Newest/Oldest, Title, Duration, Rating, Beats)
 * - 5-second preview on hover (skipping first 30s and last 30s).
 * - Mobile toggle: "Pictures (hold to preview)" vs "All Looping Videos" with persistence.
 * - Star ratings (1-5) directly on cards with API synchronization.
 * - QR code mobile connection modal.
 * - .beat / .json beatmap upload and attach modal.
 */

class WebLibrary {
  constructor(app) {
    this.app = app;
    this.videos = [];
    this.filteredVideos = [];
    this.activeFilter = 'all';
    this.searchQuery = '';
    this.mobileUrl = '';

    // Filter states (loaded from localStorage with fallback)
    this.diffFilter = localStorage.getItem('beatmake_diff_filter') || 'all';
    this.durFilter = localStorage.getItem('beatmake_dur_filter') || 'all';
    this.sortOrder = localStorage.getItem('beatmake_sort_order') || 'date_desc';

    // Thumbnail mode: 'pictures' or 'loop_videos'
    this.thumbMode = localStorage.getItem('beatmake_thumb_mode') || 'pictures';

    // UI references
    this.grid = document.getElementById('video-grid');
    this.emptyState = document.getElementById('empty-library');
    this.folderBadge = document.getElementById('folder-path-badge');
    this.searchInput = document.getElementById('search-input');
    this.filterTabs = document.querySelectorAll('.filter-tab');
    this.btnRescan = document.getElementById('btn-rescan');
    this.btnQrCode = document.getElementById('btn-qrcode');
    this.btnMobileUrl = document.getElementById('btn-mobile-url');

    // Extended Filter controls
    this.selectDiffFilter = document.getElementById('select-diff-filter');
    this.selectDurFilter = document.getElementById('select-dur-filter');
    this.selectSortOrder = document.getElementById('select-sort-order');
    this.btnThumbMode = document.getElementById('btn-thumb-mode');
    this.labelThumbMode = document.getElementById('label-thumb-mode');

    // Restore select dropdown values
    if (this.selectDiffFilter) this.selectDiffFilter.value = this.diffFilter;
    if (this.selectDurFilter) this.selectDurFilter.value = this.durFilter;
    if (this.selectSortOrder) this.selectSortOrder.value = this.sortOrder;

    // Modals
    this.modalQr = document.getElementById('modal-qrcode');
    this.modalUpload = document.getElementById('modal-upload');
    this.qrImage = document.getElementById('qr-image');
    this.qrUrlText = document.getElementById('qr-url-text');
    this.btnCopyUrl = document.getElementById('btn-copy-url');

    // Upload modal elements
    this.uploadVideoTitle = document.getElementById('upload-video-title');
    this.uploadDropzone = document.getElementById('upload-dropzone');
    this.uploadFileInput = document.getElementById('upload-file-input');
    this.targetUploadVideo = null;

    // IntersectionObserver for looping video previews (performance & battery safe)
    this._previewObserver = null;
    this._initObserver();

    this._updateThumbModeUI();
    this._bindEvents();
  }

  _initObserver() {
    if ('IntersectionObserver' in window) {
      this._previewObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (typeof entry.target._onIntersect === 'function') {
            entry.target._onIntersect(entry.isIntersecting);
          }
        });
      }, { rootMargin: '60px 0px 60px 0px', threshold: 0.1 });
    }
  }

  _cleanupVideos() {
    if (this._previewObserver) {
      this._previewObserver.disconnect();
    }
    if (!this.grid) return;
    this.grid.querySelectorAll('.card-thumbnail').forEach(el => {
      if (typeof el._cleanupPreview === 'function') {
        try { el._cleanupPreview(); } catch (e) {}
        el._cleanupPreview = null;
      }
      el._onIntersect = null;
    });
    const vids = this.grid.querySelectorAll('video');
    vids.forEach(v => {
      try {
        v.pause();
        v.removeAttribute('src');
        v.load();
        v.remove();
      } catch (e) {}
    });
  }

  _bindEvents() {
    // Search
    if (this.searchInput) {
      this.searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.toLowerCase().trim();
        this._applyFilterAndRender();
      });
    }

    // Status filter tabs
    this.filterTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        this.filterTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        this.activeFilter = tab.dataset.filter;
        this._applyFilterAndRender();
      });
    });

    // Extended filter selects
    if (this.selectDiffFilter) {
      this.selectDiffFilter.addEventListener('change', (e) => {
        this.diffFilter = e.target.value;
        localStorage.setItem('beatmake_diff_filter', this.diffFilter);
        this._applyFilterAndRender();
      });
    }
    if (this.selectDurFilter) {
      this.selectDurFilter.addEventListener('change', (e) => {
        this.durFilter = e.target.value;
        localStorage.setItem('beatmake_dur_filter', this.durFilter);
        this._applyFilterAndRender();
      });
    }
    if (this.selectSortOrder) {
      this.selectSortOrder.addEventListener('change', (e) => {
        this.sortOrder = e.target.value;
        localStorage.setItem('beatmake_sort_order', this.sortOrder);
        this._applyFilterAndRender();
      });
    }

    // Thumbnail mode toggle (fully cleans up video decoders to prevent black screen bug)
    if (this.btnThumbMode) {
      this.btnThumbMode.addEventListener('click', () => {
        this._cleanupVideos();
        this.thumbMode = this.thumbMode === 'pictures' ? 'loop_videos' : 'pictures';
        localStorage.setItem('beatmake_thumb_mode', this.thumbMode);
        this._updateThumbModeUI();
        this.render();
      });
    }

    // Rescan button
    if (this.btnRescan) {
      this.btnRescan.addEventListener('click', async () => {
        this.app.showToast('Rescanning video directory...');
        await this.loadLibrary(true);
      });
    }

    // Library Settings & Cache button
    const btnLibSettings = document.getElementById('btn-lib-settings');
    if (btnLibSettings) {
      btnLibSettings.addEventListener('click', () => {
        if (this.app && this.app.player) {
          this.app.player.openSettingsModal();
        }
      });
    }

    // QR Code button
    if (this.btnQrCode) {
      this.btnQrCode.addEventListener('click', () => this.openQrModal());
    }
    if (this.btnMobileUrl) {
      this.btnMobileUrl.addEventListener('click', () => this.openQrModal());
    }

    // Modal Close buttons
    document.querySelectorAll('.modal-close-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const modal = e.target.closest('.modal-backdrop');
        if (modal) modal.classList.remove('active');
      });
    });

    // Copy URL button
    if (this.btnCopyUrl) {
      this.btnCopyUrl.addEventListener('click', () => {
        if (this.mobileUrl) {
          navigator.clipboard.writeText(this.mobileUrl).then(() => {
            this.app.showToast('Copied link to clipboard!');
          });
        }
      });
    }

    // File Upload Dropzone
    this._setupUploadDropzone();
  }

  _updateThumbModeUI() {
    if (!this.btnThumbMode) return;
    const isLoop = this.thumbMode === 'loop_videos';
    if (this.labelThumbMode) {
      this.labelThumbMode.textContent = isLoop ? 'Thumbs: Looping Videos' : 'Thumbs: Pictures (Hold Preview)';
    }
    this.btnThumbMode.classList.toggle('active-mode', isLoop);
  }

  async loadConfig() {
    try {
      const resp = await fetch('/api/config');
      if (resp.ok) {
        const data = await resp.json();
        if (this.folderBadge) this.folderBadge.textContent = data.videos_folder;
        this.mobileUrl = data.active_mobile_url;
        if (this.qrUrlText) this.qrUrlText.textContent = this.mobileUrl;
        if (this.btnMobileUrl) {
          this.btnMobileUrl.innerHTML = `
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="5" y="2" width="14" height="20" rx="2" ry="2"></rect>
              <line x1="12" y1="18" x2="12.01" y2="18"></line>
            </svg>
            <span>${this.mobileUrl}</span>
          `;
        }
      }
    } catch (e) {
      console.warn('Failed to load config:', e);
    }
  }

  async loadLibrary(forceRefresh = false) {
    this._cleanupVideos();
    await this.loadConfig();

    try {
      const url = forceRefresh ? '/api/library?refresh=true' : '/api/library';
      const resp = await fetch(url);
      if (resp.ok) {
        const data = await resp.json();
        this.videos = data.videos || [];
        this._updateFilterCounts();
        this._applyFilterAndRender();
      }
    } catch (e) {
      console.error('Failed to load library:', e);
      this.app.showToast('Failed to load videos from server');
    }
  }

  _updateFilterCounts() {
    const withBeats = this.videos.filter(v => v.beat_info && v.beat_info.has_beats).length;
    const missing = this.videos.length - withBeats;

    const tabAll = document.querySelector('.filter-tab[data-filter="all"]');
    const tabBeats = document.querySelector('.filter-tab[data-filter="beats"]');
    const tabMissing = document.querySelector('.filter-tab[data-filter="missing"]');

    if (tabAll) tabAll.textContent = `All Videos (${this.videos.length})`;
    if (tabBeats) tabBeats.textContent = `With Beats (${withBeats})`;
    if (tabMissing) tabMissing.textContent = `Missing Beats (${missing})`;
  }

  _applyFilterAndRender() {
    this.filteredVideos = this.videos.filter(v => {
      // 1. Text search
      const matchesSearch = !this.searchQuery ||
        (v.title && v.title.toLowerCase().includes(this.searchQuery)) ||
        (v.filename && v.filename.toLowerCase().includes(this.searchQuery));

      if (!matchesSearch) return false;

      // 2. Status filter
      const hasBeats = Boolean(v.beat_info && v.beat_info.has_beats);
      if (this.activeFilter === 'beats' && !hasBeats) return false;
      if (this.activeFilter === 'missing' && hasBeats) return false;

      // 3. Difficulty filter
      if (this.diffFilter !== 'all') {
        const diff = (v.beat_info && v.beat_info.difficulty) || v.difficulty || '';
        if (diff.toLowerCase() !== this.diffFilter.toLowerCase()) return false;
      }

      // 4. Duration filter
      const dur = Number(v.duration) || 0;
      if (this.durFilter === 'short' && dur >= 120) return false;
      if (this.durFilter === 'medium' && (dur < 120 || dur > 240)) return false;
      if (this.durFilter === 'long' && dur <= 240) return false;

      return true;
    });

    // 5. Sorting
    this.filteredVideos.sort((a, b) => {
      switch (this.sortOrder) {
        case 'date_desc':
          return (b.mtime || 0) - (a.mtime || 0);
        case 'date_asc':
          return (a.mtime || 0) - (b.mtime || 0);
        case 'title_asc':
          return (a.title || '').localeCompare(b.title || '');
        case 'duration_desc':
          return (b.duration || 0) - (a.duration || 0);
        case 'duration_asc':
          return (a.duration || 0) - (b.duration || 0);
        case 'beats_desc':
          const beatsA = (a.beat_info && a.beat_info.beat_count) || 0;
          const beatsB = (b.beat_info && b.beat_info.beat_count) || 0;
          return beatsB - beatsA;
        default:
          return 0;
      }
    });

    this.render();
  }

  // 5-second preview range (excluding first 30s and last 30s)
  _getPreviewRange(dur) {
    dur = Number(dur) || 60;
    if (dur >= 65) {
      return { start: 30, end: 35 };
    }
    if (dur > 35) {
      return { start: 30, end: Math.min(dur, 35) };
    }
    const start = Math.max(0, (dur - 5) / 2);
    return { start, end: Math.min(dur, start + 5) };
  }

  render() {
    this._cleanupVideos();
    this.grid.innerHTML = '';

    if (this.filteredVideos.length === 0) {
      this.emptyState.style.display = 'block';
      return;
    }

    this.emptyState.style.display = 'none';

    this.filteredVideos.forEach(v => {
      const card = this._createVideoCard(v);
      this.grid.appendChild(card);
    });
  }

  _createVideoCard(video) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.dataset.filename = video.filename;

    const beatInfo = video.beat_info || {};
    const beatCount = beatInfo.beat_count || 0;
    const diff = beatInfo.difficulty || video.difficulty || 'Normal';

    // Top-Left Difficulty Badge (matching Python viewer library UI)
    let badgeHtml = '';
    const diffLower = (diff || '').toLowerCase();
    const diffGradients = {
      easy: 'linear-gradient(135deg, #10b981 0%, #9333ea 100%)',
      normal: 'linear-gradient(135deg, #8b5cf6 0%, #9333ea 100%)',
      hard: 'linear-gradient(135deg, #f59e0b 0%, #9333ea 100%)',
      expert: 'linear-gradient(135deg, #ef4444 0%, #9333ea 100%)',
      master: 'linear-gradient(135deg, #ec4899 0%, #9333ea 100%)'
    };
    const badgeGrad = diffGradients[diffLower] || 'linear-gradient(135deg, #8b5cf6 0%, #9333ea 100%)';

    if (beatCount > 0) {
      badgeHtml = `
        <div class="card-badge-pill" style="background: ${badgeGrad}">
          ${beatCount} Beats • ${diff}
        </div>
      `;
    } else {
      badgeHtml = `
        <div class="card-badge-pill no-beats">
          No Beatmap
        </div>
      `;
    }

    // Subtitle metadata string: Master • 63.1 MB • .beat pack
    const isBundle = Boolean(video.is_bundle || (video.filename && video.filename.toLowerCase().endsWith('.beat')));
    const bundleTag = isBundle ? '.beat pack' : 'video';
    const subItems = [beatCount > 0 ? diff : '', video.file_size_formatted, bundleTag].filter(Boolean);
    const subText = subItems.join(' • ');

    const previewRange = this._getPreviewRange(video.duration);
    const cleanTitle = (video.title || video.filename || '').replace(/\.(beat|mp4|mkv|webm|avi|mov)$/i, '');

    card.innerHTML = `
      <div class="card-thumbnail">
        <img class="card-thumb-img" src="${video.thumbnail_url}" alt="${cleanTitle}" loading="lazy">
        ${badgeHtml}
        <div class="thumbnail-overlay">
          <div class="play-circle">
            <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          </div>
        </div>
        <span class="duration-pill">${video.duration_formatted}</span>
      </div>
      <div class="card-body">
        <h4 class="card-title" title="${video.title}">${cleanTitle}</h4>
        <div class="card-sub-meta" title="${subText}">${subText}</div>

        <div class="card-actions">
          <button class="card-queue-btn" title="Add to Up Next Queue">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            <span>Queue</span>
          </button>
          <button class="card-play-btn" title="Play Video in Viewer">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
            <span>Play</span>
          </button>
          <button class="card-upload-btn" title="Attach or Upload .beat / .json beatmap">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
          </button>
        </div>
      </div>
    `;

    const thumbEl = card.querySelector('.card-thumbnail');

    // Setup Video Previews based on Thumbnail Mode
    if (this.thumbMode === 'loop_videos') {
      this._setupLoopVideo(thumbEl, video, previewRange);
    } else {
      this._setupHoverAndHoldPreview(thumbEl, video, previewRange);
    }

    // Play action triggers (Thumbnail, Title, and Play Button)
    const playActions = [
      card.querySelector('.card-thumbnail'),
      card.querySelector('.card-title'),
      card.querySelector('.card-play-btn')
    ];
    playActions.forEach(el => {
      el.addEventListener('click', () => {
        this.app.playVideo(video, this.filteredVideos);
      });
    });

    // Queue button trigger
    const btnQueue = card.querySelector('.card-queue-btn');
    if (btnQueue) {
      btnQueue.addEventListener('click', (e) => {
        e.stopPropagation();
        this._addToQueue(video, btnQueue);
      });
    }

    // Upload / Attach button
    const btnUpload = card.querySelector('.card-upload-btn');
    if (btnUpload) {
      btnUpload.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openUploadModal(video);
      });
    }

    return card;
  }

  _addToQueue(video, btn) {
    if (!this.app.player.playlist) {
      this.app.player.playlist = [];
    }
    const alreadyIdx = this.app.player.playlist.findIndex(v => v.filename === video.filename);
    if (alreadyIdx === -1) {
      this.app.player.playlist.push(video);
    }
    btn.classList.add('added');
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="#10b981" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
      <span style="color: #10b981; font-weight: bold;">Added!</span>
    `;
    this.app.showToast(`Added "${video.title}" to queue`);
    setTimeout(() => {
      btn.classList.remove('added');
      btn.innerHTML = `
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
        <span>Queue</span>
      `;
    }, 1200);
  }

  // Setup Looping Video for 'loop_videos' mode (lightweight 500KB preview clip, zero-lag in memory)
  _setupLoopVideo(thumbEl, video, range) {
    let vid = null;
    const previewSrc = video.preview_url || `/api/preview/${encodeURIComponent(video.filename)}`;

    const startLoop = () => {
      if (vid) {
        if (vid.paused) vid.play().catch(() => {});
        return;
      }
      vid = document.createElement('video');
      vid.className = 'preview-video preview-loop-video';
      vid.muted = true;
      vid.playsInline = true;
      vid.loop = true;
      vid.preload = 'auto';
      vid.src = previewSrc;

      thumbEl.appendChild(vid);
      vid.play().catch(() => {});
    };

    const stopLoop = () => {
      if (vid) {
        try {
          vid.pause();
          vid.removeAttribute('src');
          vid.load();
          vid.remove();
        } catch (e) {}
        vid = null;
      }
    };

    thumbEl._cleanupPreview = stopLoop;

    if (this._previewObserver) {
      thumbEl._onIntersect = (isIntersecting) => {
        if (isIntersecting) {
          startLoop();
        } else {
          stopLoop();
        }
      };
      this._previewObserver.observe(thumbEl);
    } else {
      startLoop();
    }
  }

  // Setup Hover (desktop) and Press-and-hold (mobile) for 'pictures' mode
  _setupHoverAndHoldPreview(thumbEl, video, range) {
    let previewVid = null;
    let hoverTimeout = null;
    let touchHoldTimeout = null;
    let isHoldTriggered = false;
    const previewSrc = video.preview_url || `/api/preview/${encodeURIComponent(video.filename)}`;

    const startPreview = () => {
      if (previewVid) return;
      previewVid = document.createElement('video');
      previewVid.className = 'preview-video';
      previewVid.muted = true;
      previewVid.playsInline = true;
      previewVid.loop = true;
      previewVid.preload = 'auto';
      previewVid.src = previewSrc;

      thumbEl.appendChild(previewVid);
      previewVid.play().catch(() => {});
    };

    const stopPreview = () => {
      if (hoverTimeout) {
        clearTimeout(hoverTimeout);
        hoverTimeout = null;
      }
      if (touchHoldTimeout) {
        clearTimeout(touchHoldTimeout);
        touchHoldTimeout = null;
      }
      if (previewVid) {
        try {
          previewVid.pause();
          previewVid.removeAttribute('src');
          previewVid.load();
          previewVid.remove();
        } catch (e) {}
        previewVid = null;
      }
    };

    thumbEl._cleanupPreview = stopPreview;

    // Desktop hover (180ms debounce)
    thumbEl.addEventListener('mouseenter', () => {
      hoverTimeout = setTimeout(startPreview, 180);
    });
    thumbEl.addEventListener('mouseleave', stopPreview);

    // Mobile / Touch press-and-hold (300ms)
    thumbEl.addEventListener('touchstart', (e) => {
      isHoldTriggered = false;
      touchHoldTimeout = setTimeout(() => {
        isHoldTriggered = true;
        startPreview();
      }, 300);
    }, { passive: true });

    thumbEl.addEventListener('touchend', (e) => {
      if (isHoldTriggered) {
        // Was holding preview - stop it and prevent accidental click
        e.preventDefault();
        stopPreview();
      } else {
        // Quick tap: stop preview timer and allow normal click to fire
        stopPreview();
      }
    });

    thumbEl.addEventListener('touchcancel', stopPreview);
  }

  // ==========================================================================
  // MODALS
  // ==========================================================================

  openQrModal() {
    if (this.qrImage) this.qrImage.src = '/api/qrcode';
    if (this.qrUrlText) this.qrUrlText.textContent = this.mobileUrl || window.location.origin;
    if (this.modalQr) this.modalQr.classList.add('active');
  }

  openUploadModal(video) {
    this.targetUploadVideo = video;
    if (this.uploadVideoTitle) this.uploadVideoTitle.textContent = video.title;
    if (this.modalUpload) this.modalUpload.classList.add('active');
  }

  _setupUploadDropzone() {
    if (!this.uploadDropzone || !this.uploadFileInput) return;

    this.uploadDropzone.addEventListener('click', () => {
      this.uploadFileInput.click();
    });

    this.uploadFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        this._uploadFile(e.target.files[0]);
      }
    });

    this.uploadDropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      this.uploadDropzone.classList.add('dragover');
    });

    this.uploadDropzone.addEventListener('dragleave', () => {
      this.uploadDropzone.classList.remove('dragover');
    });

    this.uploadDropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      this.uploadDropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        this._uploadFile(e.dataTransfer.files[0]);
      }
    });
  }

  async _uploadFile(file) {
    if (!this.targetUploadVideo) return;

    const ext = file.name.split('.').pop().toLowerCase();
    if (!['beat', 'json'].includes(ext)) {
      this.app.showToast('Please upload a .beat or .json file');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    this.app.showToast(`Uploading ${file.name}...`);

    try {
      const resp = await fetch(`/api/upload_beat/${encodeURIComponent(this.targetUploadVideo.filename)}`, {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      if (data.success) {
        this.app.showToast(data.message);
        if (this.modalUpload) this.modalUpload.classList.remove('active');
        await this.loadLibrary(true);
      } else {
        this.app.showToast(`Error: ${data.error}`);
      }
    } catch (e) {
      this.app.showToast('Upload failed');
    }
  }
}
