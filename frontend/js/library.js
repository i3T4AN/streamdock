/**
 * =======================================================================
 * i3T4AN (Ethan Blair)
 * Project:      StreamDock
 * File:         Library page functionality
 * =======================================================================
 */

const Library = {
    mediaItems: [],
    currentFilter: 'all',

    async init() {
        this.bindEvents();
        await this.loadMedia();
    },

    bindEvents() {
        // Filter buttons
        document.querySelectorAll('.chip[data-filter]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.setFilter(e.target.dataset.filter);
            });
        });

        // Search
        const searchInput = document.getElementById('librarySearch');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterMedia(e.target.value);
            });
        }

        // Scan button
        const scanBtn = document.getElementById('scanLibrary');
        if (scanBtn) {
            scanBtn.addEventListener('click', () => this.scanLibrary());
        }
    },

    async loadMedia() {
        this.showSkeletons();  // Show loading state

        try {
            this.mediaItems = await API.getArray('/library', 'items');
            this.renderGrid();
        } catch (error) {
            console.error('Failed to load library:', error);
            this.showEmpty();
        }
    },

    showSkeletons() {
        const grid = document.getElementById('libraryGrid');
        const empty = document.getElementById('libraryEmpty');
        if (empty) empty.style.display = 'none';

        // Generate 8 skeleton placeholders
        const skeletons = Array(8).fill(0).map(() => `
            <div class="media-card media-skeleton skeleton"></div>
        `).join('');

        grid.innerHTML = skeletons;
    },

    setFilter(filter) {
        this.currentFilter = filter;

        // Update active state
        document.querySelectorAll('.chip[data-filter]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
            btn.setAttribute('aria-pressed', btn.dataset.filter === filter);
        });

        this.renderGrid();
    },

    filterMedia(searchQuery = '') {
        const query = searchQuery.toLowerCase();
        const grid = document.getElementById('libraryGrid');

        grid.querySelectorAll('.media-card').forEach(card => {
            const title = card.dataset.title?.toLowerCase() || '';
            const visible = title.includes(query);
            card.style.display = visible ? '' : 'none';
        });
    },

    renderGrid() {
        const grid = document.getElementById('libraryGrid');
        const empty = document.getElementById('libraryEmpty');

        let items = this.mediaItems;

        // Apply filter
        if (this.currentFilter === 'movies') {
            items = items.filter(m => m.media_type === 'movie');
        } else if (this.currentFilter === 'shows') {
            items = items.filter(m => m.media_type === 'tv');
        } else if (this.currentFilter === 'recent') {
            items = [...items].sort((a, b) =>
                new Date(b.created_at) - new Date(a.created_at)
            ).slice(0, 20);
        }

        if (items.length === 0) {
            this.showEmpty();
            return;
        }

        if (empty) empty.style.display = 'none';
        grid.innerHTML = items.map(item => this.renderCard(item)).join('');

        // Bind card clicks
        grid.querySelectorAll('.media-card').forEach(card => {
            // Play on card click
            card.addEventListener('click', (e) => {
                // Don't trigger if clicking delete button
                if (e.target.closest('.media-delete-btn')) return;
                const id = card.dataset.id;
                Player.open(id);
            });
        });

        // Bind delete buttons
        grid.querySelectorAll('.media-delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                const title = btn.dataset.title;

                if (confirm(`Delete "${title}" and its files permanently?`)) {
                    await this.deleteMedia(id);
                }
            });
        });
    },

    async deleteMedia(id) {
        try {
            await API.delete(`/library/${id}?delete_files=true`);
            Toast.success('Media deleted');
            this.loadMedia();
        } catch (error) {
            console.error('Failed to delete media:', error);
            Toast.error('Failed to delete media');
        }
    },

    renderCard(item) {
        const poster = item.poster_url || '/images/placeholder.jpg';
        const year = item.year || '';

        return `
            <div class="media-card" data-id="${item.id}" data-title="${item.title}">
                <button class="media-delete-btn" data-id="${item.id}" data-title="${item.title}" title="Delete">×</button>
                <img src="${poster}" alt="${item.title}" loading="lazy">
                <div class="media-card-overlay">
                    <div class="media-card-title">${item.title}</div>
                    <div class="media-card-meta">${year} • ${item.media_type === 'tv' ? 'TV Show' : 'Movie'}</div>
                </div>
            </div>
        `;
    },

    showEmpty() {
        const grid = document.getElementById('libraryGrid');
        const empty = document.getElementById('libraryEmpty');

        grid.innerHTML = '';
        if (empty) empty.style.display = 'block';
    },

    async scanLibrary() {
        const btn = document.getElementById('scanLibrary');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner spinner-sm"></span> Scanning...';

        try {
            await API.post('/library/scan');
            Toast.success('Library scan complete!');
            await this.loadMedia();
        } catch (error) {
            Toast.error('Failed to scan library');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<span class=\"emoji\">🔄</span> Scan Library';
        }
    },
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    Library.init();
});
