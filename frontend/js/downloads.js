/**
 * =======================================================================
 * i3T4AN (Ethan Blair)
 * Project:      StreamDock
 * File:         Downloads page functionality
 * =======================================================================
 */

class DownloadManager {
    constructor() {
        this.pollInterval = null;
        this.POLL_RATE = 2000; // 2 seconds
        this.torrentStates = new Map(); // Track states for notifications
        this.init();
    }

    async init() {
        this.bindEvents();
        await this.fetchTorrents();
        await this.loadJobs();
        this.startPolling();
    }

    bindEvents() {
        // Add torrent button
        const addBtn = document.getElementById('addTorrent');
        if (addBtn) {
            addBtn.addEventListener('click', () => this.openModal());
        }

        // Modal controls
        const closeBtn = document.getElementById('torrentModalClose');
        const cancelBtn = document.getElementById('cancelTorrent');
        const submitBtn = document.getElementById('submitTorrent');
        const backdrop = document.getElementById('torrentBackdrop');
        const modal = document.getElementById('addTorrentModal');

        if (closeBtn) closeBtn.addEventListener('click', () => this.closeModal());
        if (cancelBtn) cancelBtn.addEventListener('click', () => this.closeModal());
        if (backdrop) backdrop.addEventListener('click', () => this.closeModal());

        // Submit on enter in input
        const input = document.getElementById('magnetInput');
        if (input) {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.addMagnet(input.value);
            });
        }

        if (submitBtn) {
            submitBtn.addEventListener('click', () => {
                const val = document.getElementById('magnetInput').value;
                this.addMagnet(val);
            });
        }
    }

    startPolling() {
        if (this.pollInterval) clearInterval(this.pollInterval);

        this.pollInterval = setInterval(() => {
            this.fetchTorrents();
            this.loadJobs();
            this.updateStats();
        }, this.POLL_RATE);

        // Stop polling when page is hidden
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (this.pollInterval) clearInterval(this.pollInterval);
            } else {
                this.startPolling();
            }
        });
    }

    async fetchTorrents() {
        try {
            const torrents = await API.getArray('/torrents', 'torrents');

            // Check for completed downloads
            torrents.forEach(t => {
                const oldState = this.torrentStates.get(t.hash);
                if (oldState &&
                    oldState !== 'completed' &&
                    oldState !== 'seeding' &&
                    (t.state === 'completed' || t.state === 'seeding')) {
                    Toast.success(`Download complete: ${t.name}`);
                }
                this.torrentStates.set(t.hash, t.state);
            });

            this.renderTorrentList(torrents);
        } catch (error) {
            console.error('Failed to load torrents:', error);
        }
    }

    async loadJobs() {
        try {
            const jobs = await API.getArray('/transcode/jobs', 'jobs');
            this.renderJobs(jobs);
        } catch (error) {
            console.error('Failed to load jobs:', error);
        }
    }

    async updateStats() {
        try {
            const data = await API.get('/torrents/stats');
            const dl = document.getElementById('downloadSpeed');
            const ul = document.getElementById('uploadSpeed');

            if (dl) dl.textContent = Utils.formatSpeed(data.download_speed || 0);
            if (ul) ul.textContent = Utils.formatSpeed(data.upload_speed || 0);
        } catch (error) {
            console.error('Failed to update stats:', error);
        }
    }

    renderList(listId, emptyId, items, renderFn) {
        const list = document.getElementById(listId);
        const empty = document.getElementById(emptyId);
        if (!list || !empty) return;

        if (items.length === 0) {
            empty.style.display = '';
            list.innerHTML = '';
            list.appendChild(empty);
            return;
        }

        empty.style.display = 'none';
        list.innerHTML = items.map(renderFn).join('');
        list.appendChild(empty);
    }

    renderTorrentList(torrents) {
        this.renderList('torrentList', 'torrentsEmpty', torrents, t => this.renderTorrentRow(t));
    }

    renderTorrentRow(t) {
        const isPaused = t.state === 'paused';
        const progressClass = t.progress_percent >= 100 ? 'success' : '';
        const percent = t.progress_percent.toFixed(1);

        return `
            <div class="torrent-item" data-hash="${t.hash}">
                <div class="torrent-info">
                    <div class="torrent-name" title="${t.name}">${t.name}</div>
                    <div class="torrent-meta">
                        <span class="meta-item">${t.size_formatted}</span>
                        <span class="meta-separator">•</span>
                        <span class="meta-item status-badge status-${t.state}">${t.state}</span>
                        <span class="meta-separator">•</span>
                        <span class="meta-item">ETA: ${t.eta_formatted}</span>
                        <span class="meta-separator">•</span>
                        <span class="meta-item accent">↓ ${t.download_speed_formatted}</span>
                        <span class="meta-item">↑ ${t.upload_speed_formatted}</span>
                    </div>
                </div>
                <div class="torrent-progress">
                    <div class="progress">
                        <div class="progress-bar ${progressClass}" 
                             style="width: ${percent}%"></div>
                    </div>
                    <div class="progress-text">
                        <span>${percent}%</span>
                    </div>
                </div>
                <div class="torrent-actions">
                    ${isPaused
                ? `<button class="action-btn" onclick="downloads.resumeTorrent('${t.hash}')" title="Resume"><span class="emoji">▶️</span></button>`
                : `<button class="action-btn" onclick="downloads.pauseTorrent('${t.hash}')" title="Pause"><span class="emoji">⏸️</span></button>`
            }
                    <button class="action-btn action-delete" onclick="downloads.deleteTorrent('${t.hash}')" title="Delete"><span class="emoji">🗑️</span></button>
                </div>
            </div>
        `;
    }

    renderJobs(jobs) {
        this.renderList('transcodeJobs', 'jobsEmpty', jobs, j => this.renderJobRow(j));

        // Show/hide clear button based on finished jobs
        const hasFinished = jobs.some(j => j.status === 'complete' || j.status === 'failed');
        const clearBtn = document.getElementById('clearFinishedJobs');
        if (clearBtn) clearBtn.style.display = hasFinished ? '' : 'none';
    }

    renderJobRow(j) {
        const canCancel = j.status === 'pending' || j.status === 'processing';
        const canRestart = j.status === 'processing' || j.status === 'failed';
        const statusClass = `status-${j.status}`;
        const errorMessage = j.status === 'failed' && j.error_message ? `<div class="job-error" title="${j.error_message}">${j.error_message}</div>` : '';

        return `
        <div class="job-item" data-id="${j.id}">
            <div class="job-info">
                <div class="job-name">${j.source_path.split('/').pop()}</div>
                <div class="job-meta">
                    <span class="status-badge ${statusClass}">${j.status}</span>
                    ${errorMessage}
                </div>
            </div>
            <div class="job-progress">
                <div class="progress">
                    <div class="progress-bar animated" style="width: ${j.progress}%"></div>
                </div>
            </div>
            <div class="job-actions">
                ${canCancel ? `<button class="action-btn action-delete" onclick="downloads.cancelJob(${j.id})" title="Cancel"><span class="emoji">❌</span></button>` : ''}
                ${canRestart ? `<button class="action-btn" onclick="downloads.restartJob(${j.id})" title="Restart"><span class="emoji">🔄</span></button>` : ''}
            </div>
        </div>
        `;
    }

    openModal() {
        const modal = document.getElementById('addTorrentModal');
        if (modal) {
            modal.hidden = false;
            modal.classList.add('open');
            setTimeout(() => document.getElementById('magnetInput')?.focus(), 50);
        }
    }

    closeModal() {
        const modal = document.getElementById('addTorrentModal');
        if (modal) {
            modal.classList.remove('open');
            modal.hidden = true;
            const input = document.getElementById('magnetInput');
            if (input) input.value = '';
        }
    }

    async addMagnet(link) {
        const magnet = link ? link.trim() : '';

        if (!magnet) {
            Toast.warning('Please enter a magnet link');
            return;
        }

        if (!magnet.startsWith('magnet:')) {
            Toast.warning('Invalid magnet link format');
            return;
        }

        const btn = document.getElementById('submitTorrent');
        if (btn) btn.disabled = true;

        try {
            await API.post('/torrents', { magnet_link: magnet });
            Toast.success('Torrent added successfully');
            this.closeModal();
            await this.fetchTorrents();
        } catch (error) {
            Toast.error('Failed to add torrent');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async pauseTorrent(hash) {
        try {
            await API.post(`/torrents/${hash}/pause`);
            Toast.info('Torrent paused');
            await this.fetchTorrents();
        } catch (error) {
            Toast.error('Failed to pause torrent');
        }
    }

    async resumeTorrent(hash) {
        try {
            await API.post(`/torrents/${hash}/resume`);
            Toast.info('Torrent resumed');
            await this.fetchTorrents();
        } catch (error) {
            Toast.error('Failed to resume torrent');
        }
    }

    async deleteTorrent(hash) {
        if (!confirm('Are you sure you want to delete this torrent? Downloaded files may be kept depending on settings.')) return;

        try {
            await API.delete(`/torrents/${hash}`);
            Toast.success('Torrent deleted');
            await this.fetchTorrents();
        } catch (error) {
            Toast.error('Failed to delete torrent');
        }
    }

    async cancelJob(id) {
        if (!confirm('Cancel this transcoding job?')) return;

        try {
            await API.delete(`/transcode/jobs/${id}`);
            Toast.success('Job cancelled');
            await this.loadJobs();
        } catch (error) {
            Toast.error('Failed to cancel job');
        }
    }

    async restartJob(id) {
        if (!confirm('Restart this job?')) return;

        try {
            await API.post(`/transcode/jobs/${id}/restart`);
            Toast.success('Job restarted');
            await this.loadJobs();
        } catch (error) {
            Toast.error('Failed to restart job');
        }
    }

    async clearFinishedJobs() {
        if (!confirm('Clear all completed and failed jobs?')) return;

        try {
            const result = await API.delete('/transcode/jobs/finished');
            Toast.success(`Cleared ${result.cleared} jobs`);
            await this.loadJobs();
        } catch (error) {
            Toast.error('Failed to clear jobs');
        }
    }
}

// Initialize on DOM ready
let downloads;
document.addEventListener('DOMContentLoaded', () => {
    downloads = new DownloadManager();
});
