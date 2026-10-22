/**
 * web/static/js/app.js - Main Application Orchestrator & SPA Router.
 */

class BeatbarApp {
  constructor() {
    this.currentView = 'library';
    this.toastContainer = document.getElementById('toast-container');

    // Instantiate sub-controllers
    this.library = new WebLibrary(this);
    this.player = new WebPlayer(this);

    this._setupRouting();
  }

  async init() {
    // Initial load
    await this.library.loadLibrary();

    // Check hash route
    this._handleHash();
  }

  showView(viewName) {
    this.currentView = viewName;

    const viewLib = document.getElementById('view-library');
    const viewPlayer = document.getElementById('view-player');

    if (viewName === 'player') {
      this.library._cleanupVideos();
      viewLib.classList.remove('active');
      viewPlayer.classList.add('active');
      this.player.beatbar.resize();
    } else {
      viewPlayer.classList.remove('active');
      viewLib.classList.add('active');
      window.location.hash = '#library';
      if (this.library.thumbMode === 'loop_videos') {
        this.library.render();
      }
    }
  }

  playVideo(videoMeta, playlist) {
    this.showView('player');
    window.location.hash = `#player/${encodeURIComponent(videoMeta.id)}`;
    this.player.loadVideo(videoMeta, playlist);
  }

  _setupRouting() {
    window.addEventListener('hashchange', () => this._handleHash());
  }

  _handleHash() {
    const hash = window.location.hash;
    if (hash.startsWith('#player/')) {
      const vidId = decodeURIComponent(hash.substring('#player/'.length));
      const video = this.library.videos.find(v => v.id === vidId);
      if (video) {
        this.playVideo(video, this.library.videos);
      } else {
        this.showView('library');
      }
    } else {
      this.showView('library');
    }
  }

  showToast(message, duration = 3000) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    this.toastContainer.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => {
      toast.classList.add('show');
    });

    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
}

// Global initialization
window.addEventListener('DOMContentLoaded', () => {
  window.beatbarApp = new BeatbarApp();
  window.beatbarApp.init();
});
