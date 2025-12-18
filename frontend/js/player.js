/**
 * =======================================================================
 * i3T4AN (Ethan Blair)
 * Project:      StreamDock
 * File:         Video player with Netflix-style detail view
 * =======================================================================
 */

const Player = {
    modal: null,
    video: null,
    currentMediaId: null,
    currentEpisodeId: null,
    currentDetails: null,
    progressInterval: null,
    isFullscreen: false,

    init() {
        this.modal = document.getElementById('playerModal');
        this.video = document.getElementById('videoPlayer');

        if (!this.modal || !this.video) return;

        this.bindEvents();
    },

    bindEvents() {
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (!this.modal || this.modal.hidden) return;

            switch (e.key) {
                case 'Escape':
                    if (this.isFullscreen) {
                        this.exitDetailFullscreen();
                    } else {
                        this.close();
                    }
                    break;
                case ' ':
                    e.preventDefault();
                    this.togglePlay();
                    break;
                case 'ArrowLeft':
                    this.seek(-10);
                    break;
                case 'ArrowRight':
                    this.seek(10);
                    break;
                case 'f':
                case 'F':
                    this.toggleDetailFullscreen();
                    break;
                case 'm':
                case 'M':
                    this.toggleMute();
                    break;
            }
        });
    },

    async open(mediaId, episodeId = null) {
        if (!this.modal) {
            this.init();
        }

        this.currentMediaId = mediaId;
        this.isFullscreen = false;

        try {
            // Fetch full details including cast
            const details = await API.get(`/library/${mediaId}/details`);
            this.currentDetails = details;

            // Render the detail view
            this.renderDetailView(details, episodeId);

            // Show modal
            this.modal.hidden = false;
            this.modal.classList.add('open');

        } catch (error) {
            console.error('Failed to open player:', error);
            Toast.error('Failed to load video');
        }
    },

    renderDetailView(details, episodeId = null) {
        // Clear existing content and use modal directly
        const modal = this.modal;

        // Determine video source
        let streamUrl;
        let subtitle = '';

        if (details.media_type === 'tv') {
            const epId = episodeId || (details.episodes && details.episodes[0]?.id);
            this.currentEpisodeId = epId; // Track for progress saving
            if (epId) {
                streamUrl = `/api/stream/${details.id}/episode/${epId}`;
                const ep = details.episodes?.find(e => e.id === epId);
                if (ep) {
                    subtitle = `S${ep.season.toString().padStart(2, '0')}E${ep.episode.toString().padStart(2, '0')}`;
                    if (ep.title) subtitle += ` - ${ep.title}`;
                }
            }
        } else {
            this.currentEpisodeId = null; // Movies don't have episodes
            streamUrl = `/api/stream/${details.id}`;
        }

        // Build cast HTML
        const castHtml = (details.cast || []).map(person => `
            <div class="detail-cast-item">
                <div class="detail-cast-photo">
                    ${person.profile_url
                ? `<img src="${person.profile_url}" alt="${person.name}" loading="lazy">`
                : `<div class="detail-cast-photo-placeholder">👤</div>`
            }
                </div>
                <div class="detail-cast-name">${person.name}</div>
                <div class="detail-cast-character">${person.character || ''}</div>
            </div>
        `).join('');

        // Build genres HTML
        const genresHtml = (details.genres || []).map(g =>
            `<span class="detail-genre">${g}</span>`
        ).join('');

        // Build creator/director line
        let creatorLine = '';
        if (details.director) {
            creatorLine = `<p class="detail-creator">Directed by <strong>${details.director}</strong></p>`;
        } else if (details.creators && details.creators.length > 0) {
            creatorLine = `<p class="detail-creator">Created by <strong>${details.creators.join(', ')}</strong></p>`;
        }

        // Runtime display
        let runtimeDisplay = '';
        if (details.runtime) {
            const hours = Math.floor(details.runtime / 60);
            const mins = details.runtime % 60;
            runtimeDisplay = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
        }

        // Episode selector for TV shows
        let episodeSelectorHtml = '';
        let currentEpisodeId = null;
        if (details.media_type === 'tv' && details.episodes && details.episodes.length > 0) {
            // Group episodes by season
            const seasons = {};
            details.episodes.forEach(ep => {
                if (!seasons[ep.season]) {
                    seasons[ep.season] = [];
                }
                seasons[ep.season].push(ep);
            });
            const seasonNumbers = Object.keys(seasons).map(Number).sort((a, b) => a - b);

            // Determine current episode
            const currentEp = episodeId
                ? details.episodes.find(e => e.id === episodeId)
                : details.episodes[0];
            currentEpisodeId = currentEp?.id;
            const currentSeason = currentEp?.season || seasonNumbers[0];

            // Build season options
            const seasonOptions = seasonNumbers.map(s =>
                `<option value="${s}" ${s === currentSeason ? 'selected' : ''}>Season ${s}</option>`
            ).join('');

            // Build episode options (for current season)
            const episodeOptions = (seasons[currentSeason] || []).map(ep =>
                `<option value="${ep.id}" ${ep.id === currentEpisodeId ? 'selected' : ''}>
                    E${ep.episode.toString().padStart(2, '0')}${ep.title ? ` - ${ep.title}` : ''}
                </option>`
            ).join('');

            episodeSelectorHtml = `
                <div class="episode-selector">
                    <h3 class="episode-selector-title">Episodes</h3>
                    <div class="episode-selector-controls">
                        <select id="seasonSelect" class="episode-select">
                            ${seasonOptions}
                        </select>
                        <select id="episodeSelect" class="episode-select">
                            ${episodeOptions}
                        </select>
                    </div>
                </div>
            `;
        }

        modal.innerHTML = `
            <div class="detail-view">
                <!-- Back Button Header -->
                <div class="detail-header">
                    <button class="detail-back-btn" id="detailBackBtn">
                        <span>←</span> Back
                    </button>
                </div>

                <!-- Left: Metadata Panel -->
                <div class="detail-metadata">
                    <div class="detail-backdrop" style="background-image: url('${details.backdrop_url || ''}')"></div>
                    <div class="detail-content">
                        <h1 class="detail-title">${details.title}</h1>
                        ${subtitle ? `<p class="detail-subtitle">${subtitle}</p>` : ''}
                        
                        <div class="detail-meta">
                            ${details.vote_average ? `
                                <div class="detail-rating">
                                    <span class="detail-rating-star">⭐</span>
                                    <span>${details.vote_average.toFixed(1)}</span>
                                </div>
                            ` : ''}
                            ${details.year ? `<span class="detail-year">${details.year}</span>` : ''}
                            ${runtimeDisplay ? `<span class="detail-runtime">${runtimeDisplay}</span>` : ''}
                            ${details.number_of_seasons ? `<span class="detail-seasons">${details.number_of_seasons} Season${details.number_of_seasons > 1 ? 's' : ''}</span>` : ''}
                        </div>

                        ${genresHtml ? `<div class="detail-genres">${genresHtml}</div>` : ''}
                        
                        ${details.tagline ? `<p class="detail-tagline">"${details.tagline}"</p>` : ''}
                        
                        ${details.overview ? `<p class="detail-overview">${details.overview}</p>` : ''}
                        
                        ${creatorLine}

                        ${episodeSelectorHtml}

                        ${castHtml ? `
                            <div class="detail-cast-section">
                                <h3 class="detail-cast-title">Cast</h3>
                                <div class="detail-cast-grid">${castHtml}</div>
                            </div>
                        ` : ''}
                    </div>
                </div>

                <!-- Right: Video Player -->
                <div class="detail-player">
                    <div class="player-container">
                        <video id="videoPlayer" controls>
                            <source id="videoSource" src="${streamUrl}" type="video/mp4">
                        </video>
                    </div>
                </div>
            </div>
        `;

        // Re-bind video reference
        this.video = document.getElementById('videoPlayer');

        // Bind back button
        document.getElementById('detailBackBtn')?.addEventListener('click', () => {
            this.close();
        });

        // Bind episode selectors for TV shows
        if (details.media_type === 'tv' && details.episodes) {
            const seasonSelect = document.getElementById('seasonSelect');
            const episodeSelect = document.getElementById('episodeSelect');

            // Group episodes by season for reference
            const seasons = {};
            details.episodes.forEach(ep => {
                if (!seasons[ep.season]) seasons[ep.season] = [];
                seasons[ep.season].push(ep);
            });

            // When season changes, update episode dropdown
            seasonSelect?.addEventListener('change', (e) => {
                const season = parseInt(e.target.value);
                const eps = seasons[season] || [];
                episodeSelect.innerHTML = eps.map(ep =>
                    `<option value="${ep.id}">E${ep.episode.toString().padStart(2, '0')}${ep.title ? ` - ${ep.title}` : ''}</option>`
                ).join('');
                // Auto-play first episode of new season
                if (eps.length > 0) {
                    this.switchEpisode(details.id, eps[0].id);
                }
            });

            // When episode changes, switch video
            episodeSelect?.addEventListener('change', (e) => {
                const epId = parseInt(e.target.value);
                this.switchEpisode(details.id, epId);
            });
        }

        // Bind video events
        this.video.addEventListener('timeupdate', () => this.saveProgress());

        // Load progress
        this.loadProgress();

        // Start video
        this.video.play().catch(() => {
            // Autoplay blocked, user will click play
        });

        // Start progress saving
        this.startProgressInterval();
    },

    switchEpisode(mediaId, episodeId) {
        if (!this.video) return;

        // Save current progress before switching
        this.saveProgress();

        // Update current episode ID
        this.currentEpisodeId = episodeId;

        // Update video source
        const source = document.getElementById('videoSource');
        source.src = `/api/stream/${mediaId}/episode/${episodeId}`;
        this.video.load();

        // Load progress for the new episode
        this.loadProgress();

        this.video.play().catch(() => { });
    },

    toggleDetailFullscreen() {
        const detailView = this.modal.querySelector('.detail-view');
        if (!detailView) return;

        if (this.isFullscreen) {
            this.exitDetailFullscreen();
        } else {
            detailView.classList.add('fullscreen-mode');
            this.modal.requestFullscreen().catch(() => { });
            this.isFullscreen = true;
        }
    },

    exitDetailFullscreen() {
        const detailView = this.modal.querySelector('.detail-view');
        if (!detailView) return;

        detailView.classList.remove('fullscreen-mode');
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(() => { });
        }
        this.isFullscreen = false;
    },

    close() {
        if (!this.modal) return;

        if (this.video) {
            this.video.pause();
        }
        this.saveProgress();
        this.stopProgressInterval();
        this.exitDetailFullscreen();

        this.modal.classList.remove('open');
        this.modal.hidden = true;
        this.currentMediaId = null;
        this.currentEpisodeId = null;
        this.currentDetails = null;
    },

    togglePlay() {
        if (!this.video) return;
        if (this.video.paused) {
            this.video.play();
        } else {
            this.video.pause();
        }
    },

    seek(seconds) {
        if (!this.video) return;
        this.video.currentTime = Math.max(0, this.video.currentTime + seconds);
    },

    toggleMute() {
        if (!this.video) return;
        this.video.muted = !this.video.muted;
    },

    async loadProgress() {
        if (!this.currentMediaId) return;

        try {
            let url = `/progress/${this.currentMediaId}`;
            if (this.currentEpisodeId) {
                url += `?episode_id=${this.currentEpisodeId}`;
            }
            const data = await API.get(url);
            if (data.position && data.position > 10 && this.video) {
                this.showResumePopup(data.position);
            }
        } catch (error) {
            // No saved progress, start from beginning
        }
    },

    showResumePopup(position) {
        const popup = document.createElement('div');
        popup.className = 'resume-popup';
        popup.innerHTML = `
            <div class="resume-popup-content">
                <p>Resume from <strong>${Utils.formatDuration(position)}</strong>?</p>
                <div class="resume-popup-buttons">
                    <button class="btn resume-btn" data-action="resume">Resume</button>
                    <button class="btn resume-btn-secondary" data-action="start">Start Over</button>
                </div>
            </div>
        `;

        const container = this.modal.querySelector('.player-container');
        if (container) {
            container.appendChild(popup);
        }

        this.video.pause();

        popup.querySelector('[data-action="resume"]').addEventListener('click', () => {
            this.video.currentTime = position;
            this.video.play();
            popup.remove();
        });

        popup.querySelector('[data-action="start"]').addEventListener('click', () => {
            this.video.currentTime = 0;
            this.video.play();
            popup.remove();
        });

        setTimeout(() => {
            if (document.contains(popup)) {
                this.video.currentTime = position;
                this.video.play();
                popup.remove();
            }
        }, 5000);
    },

    startProgressInterval() {
        this.stopProgressInterval();
        this.progressInterval = setInterval(() => {
            this.saveProgress();
        }, 10000);
    },

    stopProgressInterval() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
    },

    async saveProgress() {
        if (!this.currentMediaId || !this.video || !this.video.currentTime) return;

        try {
            const payload = {
                position: Math.floor(this.video.currentTime),
                completed: this.video.ended,
            };
            if (this.currentEpisodeId) {
                payload.episode_id = this.currentEpisodeId;
            }
            await API.post(`/progress/${this.currentMediaId}`, payload);
        } catch (error) {
            console.error('Failed to save progress:', error);
        }
    },
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    Player.init();
});
