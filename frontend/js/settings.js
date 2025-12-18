/**
 * =======================================================================
 * i3T4AN (Ethan Blair)
 * Project:      StreamDock
 * File:         Settings page functionality
 * =======================================================================
 */

const Settings = {
    currentSettings: {},

    async init() {
        this.bindEvents();
        await this.loadSettings();
        await this.checkConnections();
        this.displayNetworkUrl();
    },

    bindEvents() {
        // Save button
        const saveBtn = document.getElementById('saveSettings');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveSettings());
        }

        // Rescan button
        const rescanBtn = document.getElementById('rescanLibrary');
        if (rescanBtn) {
            rescanBtn.addEventListener('click', () => this.rescanLibrary());
        }

        // Theme selector
        const themeSelect = document.getElementById('themeSetting');
        if (themeSelect) {
            themeSelect.addEventListener('change', (e) => this.setTheme(e.target.value));
        }
    },

    async loadSettings() {
        try {
            const data = await API.get('/settings');
            this.currentSettings = data || {};
            this.applySettings();
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    },

    applySettings() {
        // Theme
        const themeSelect = document.getElementById('themeSetting');
        if (themeSelect && this.currentSettings.theme) {
            themeSelect.value = this.currentSettings.theme;
            this.setTheme(this.currentSettings.theme);
        }

        // Quality
        const qualitySelect = document.getElementById('qualitySetting');
        if (qualitySelect && this.currentSettings.default_quality) {
            qualitySelect.value = this.currentSettings.default_quality;
        }

        // Max jobs
        const maxJobsInput = document.getElementById('maxJobsSetting');
        if (maxJobsInput && this.currentSettings.max_concurrent_jobs) {
            maxJobsInput.value = this.currentSettings.max_concurrent_jobs;
        }
    },

    setTheme(theme) {
        const body = document.body;

        if (theme === 'system') {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            body.classList.toggle('theme-dark', prefersDark);
            body.classList.toggle('theme-light', !prefersDark);
        } else if (theme === 'light') {
            body.classList.remove('theme-dark');
            body.classList.add('theme-light');
        } else {
            body.classList.remove('theme-light');
            body.classList.add('theme-dark');
        }
    },

    async checkConnections() {
        try {
            const data = await API.get('/status');
            const services = data.services || {};

            this.updateStatus('qbitStatus', services.qbittorrent);
            this.updateStatus('dbStatus', services.database);
            this.updateStatus('tmdbStatus', services.tmdb);
        } catch (error) {
            this.updateStatus('qbitStatus', 'error');
            this.updateStatus('dbStatus', 'error');
            this.updateStatus('tmdbStatus', 'error');
        }
    },

    updateStatus(elementId, status) {
        const el = document.getElementById(elementId);
        if (!el) return;

        const isConnected = status === 'connected' || status === 'configured';
        el.textContent = isConnected ? 'Connected' : 'Disconnected';
        el.className = `badge ${isConnected ? 'badge-success' : 'badge-danger'}`;
    },

    async displayNetworkUrl() {
        const urlEl = document.getElementById('networkUrl');
        const qrEl = document.getElementById('qrCode');

        try {
            const status = await API.get('/status');
            const ip = status.server_ip || window.location.hostname;
            const port = window.location.port || '8000';
            const url = `http://${ip}:${port}`;

            if (urlEl) urlEl.textContent = url;

            // Generate QR code
            if (qrEl && typeof QRCode !== 'undefined') {
                qrEl.innerHTML = '';
                new QRCode(qrEl, {
                    text: url,
                    width: 128,
                    height: 128,
                    colorDark: '#a855f7',
                    colorLight: 'transparent',
                    correctLevel: QRCode.CorrectLevel.M
                });
            }
        } catch (error) {
            if (urlEl) urlEl.textContent = window.location.href;
        }
    },

    async saveSettings() {
        const settings = {
            theme: document.getElementById('themeSetting')?.value || 'dark',
            default_quality: document.getElementById('qualitySetting')?.value || '1080p',
            max_concurrent_jobs: String(document.getElementById('maxJobsSetting')?.value || '1'),
        };

        try {
            await API.put('/settings', { settings });
            Toast.success('Settings saved!');
            this.currentSettings = settings;
        } catch (error) {
            Toast.error('Failed to save settings');
        }
    },

    async rescanLibrary() {
        const btn = document.getElementById('rescanLibrary');
        btn.disabled = true;
        btn.textContent = 'Scanning...';

        try {
            await API.post('/library/scan');
            Toast.success('Library scan complete!');
        } catch (error) {
            Toast.error('Failed to scan library');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<span class=\"emoji\">🔄</span> Rescan Library';
        }
    },
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    Settings.init();
});
