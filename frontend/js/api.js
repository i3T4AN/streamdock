/**
 * =======================================================================
 * i3T4AN (Ethan Blair)
 * Project:      StreamDock
 * File:         API client for backend communication
 * =======================================================================
 */

const API = {
    baseUrl: '/api',
    timeout: 30000, // 30 second timeout
    maxRetries: 2,
    retryDelay: 1000,

    /**
     * Check if browser is online
     */
    isOnline() {
        return navigator.onLine;
    },

    /**
     * Make a request with retry logic and timeout
     */
    async request(endpoint, options = {}, retries = 0) {
        // Check offline first
        if (!this.isOnline()) {
            Toast.error('You are offline. Please check your connection.');
            throw new Error('Network offline');
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                ...options,
                signal: controller.signal,
            });
            clearTimeout(timeoutId);

            if (!response.ok) {
                const errorText = await response.text().catch(() => response.statusText);
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }
            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);

            // Handle abort (timeout)
            if (error.name === 'AbortError') {
                Toast.error('Request timed out. Please try again.');
                throw new Error('Request timeout');
            }

            // Retry on network errors
            if (retries < this.maxRetries && (error.message.includes('fetch') || error.name === 'TypeError')) {
                console.warn(`API retry ${retries + 1}/${this.maxRetries} for ${endpoint}`);
                await new Promise(r => setTimeout(r, this.retryDelay * (retries + 1)));
                return this.request(endpoint, options, retries + 1);
            }

            console.error(`API ${options.method || 'GET'} ${endpoint} failed:`, error);
            throw error;
        }
    },

    /**
     * Make a GET request
     */
    async get(endpoint) {
        return this.request(endpoint);
    },

    /**
     * GET request that normalizes response to array
     */
    async getArray(endpoint, fallbackKey = 'items') {
        const data = await this.request(endpoint);
        return Array.isArray(data) ? data : (data[fallbackKey] || []);
    },

    /**
     * Make a POST request
     */
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
    },

    /**
     * Make a PUT request
     */
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
    },

    /**
     * Make a DELETE request
     */
    async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    },
};

/**
 * Toast notification system
 */
const Toast = {
    container: null,

    init() {
        this.container = document.getElementById('toastContainer');
    },

    show(message, type = 'info', duration = 3000) {
        if (!this.container) this.init();

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span class="toast-icon emoji">${this.getIcon(type)}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
        `;

        this.container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    getIcon(type) {
        switch (type) {
            case 'success': return '✅';
            case 'warning': return '⚠️';
            case 'danger': return '❌';
            default: return 'ℹ️';
        }
    },

    success(message) { this.show(message, 'success'); },
    warning(message) { this.show(message, 'warning'); },
    error(message) { this.show(message, 'danger'); },
    info(message) { this.show(message, 'info'); },
};

/**
 * Utility functions
 */
const Utils = {
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    formatSpeed(bytesPerSecond) {
        return this.formatBytes(bytesPerSecond) + '/s';
    },

    formatDuration(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if (h > 0) {
            return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        }
        return `${m}:${s.toString().padStart(2, '0')}`;
    },

    formatEta(seconds) {
        if (seconds <= 0 || !isFinite(seconds)) return '∞';
        if (seconds < 60) return `${seconds}s`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
        return `${Math.floor(seconds / 86400)}d`;
    },
};

// Initialize toast on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    Toast.init();

    // Network status listeners
    window.addEventListener('online', () => {
        Toast.success('Back online!');
    });

    window.addEventListener('offline', () => {
        Toast.warning('You are offline. Some features may not work.');
    });

    // Global image error handler for graceful degradation
    document.addEventListener('error', (e) => {
        if (e.target.tagName === 'IMG' && !e.target.dataset.fallback) {
            e.target.dataset.fallback = 'true';
            e.target.src = '/images/placeholder.jpg';
        }
    }, true);
});
