// Shared Filter Utilities for LegalMatch Platform
// This file provides consistent filtering functionality across all templates

class LegalMatchFilter {
    constructor(options = {}) {
        this.options = {
            debounceDelay: 300,
            pagination: true,
            itemsPerPage: 10,
            ...options
        };
        
        this.allItems = [];
        this.filteredItems = [];
        this.currentPage = 1;
        this.filters = {};
    }

    // Initialize the filter system
    init(container, items = []) {
        this.container = container;
        this.allItems = items;
        this.filteredItems = [...items];
        
        this.setupEventListeners();
        this.updateDisplay();
        this.updateFilterStatus();
    }

    // Setup event listeners for filter controls
    setupEventListeners() {
        const searchInput = this.container.querySelector('#searchInput, #search-filter');
        const specialtyFilter = this.container.querySelector('#specialtyFilter, #specialty-filter');
        const experienceFilter = this.container.querySelector('#experienceFilter, #experience-filter');
        const ratingFilter = this.container.querySelector('#ratingFilter, #rating-filter');
        const locationFilter = this.container.querySelector('#locationFilter, #location-filter');
        const sortFilter = this.container.querySelector('#sortFilter, #sort-filter');
        const clearFilters = this.container.querySelector('#clearFilters, #clear-filters');

        if (searchInput) {
            searchInput.addEventListener('input', this.debounce(() => this.filterAndPaginate(), this.options.debounceDelay));
        }
        
        if (specialtyFilter) {
            specialtyFilter.addEventListener('change', () => this.filterAndPaginate());
        }
        
        if (experienceFilter) {
            experienceFilter.addEventListener('change', () => this.filterAndPaginate());
        }
        
        if (ratingFilter) {
            ratingFilter.addEventListener('change', () => this.filterAndPaginate());
        }
        
        if (locationFilter) {
            locationFilter.addEventListener('input', this.debounce(() => this.filterAndPaginate(), this.options.debounceDelay));
        }
        
        if (sortFilter) {
            sortFilter.addEventListener('change', () => this.sortAndPaginate());
        }
        
        if (clearFilters) {
            clearFilters.addEventListener('click', () => this.clearAllFilters());
        }
    }

    // Apply filters and pagination
    filterAndPaginate() {
        this.collectFilters();
        this.applyFilters();
        this.currentPage = 1;
        this.updateDisplay();
        this.updateFilterStatus();
    }

    // Collect filter values
    collectFilters() {
        this.filters = {
            search: this.getFilterValue('#searchInput, #search-filter'),
            specialty: this.getFilterValue('#specialtyFilter, #specialty-filter'),
            experience: this.getFilterValue('#experienceFilter, #experience-filter'),
            rating: this.getFilterValue('#ratingFilter, #rating-filter'),
            location: this.getFilterValue('#locationFilter, #location-filter'),
            court: this.getFilterValue('#courtFilter'),
            winRate: this.getFilterValue('#winRateFilter'),
            fee: this.getFilterValue('#feeFilter'),
            status: this.getFilterValue('#statusFilter'),
            type: this.getFilterValue('#typeFilter'),
            priority: this.getFilterValue('#priorityFilter')
        };
    }

    // Get filter value by selector
    getFilterValue(selectors) {
        const element = this.container.querySelector(selectors);
        return element ? element.value : '';
    }

    // Apply filters to items
    applyFilters() {
        this.filteredItems = this.allItems.filter(item => {
            return this.matchesSearch(item) &&
                   this.matchesSpecialty(item) &&
                   this.matchesExperience(item) &&
                   this.matchesRating(item) &&
                   this.matchesLocation(item) &&
                   this.matchesCourt(item) &&
                   this.matchesWinRate(item) &&
                   this.matchesFee(item) &&
                   this.matchesStatus(item) &&
                   this.matchesType(item) &&
                   this.matchesPriority(item);
        });
    }

    // Individual filter matching methods
    matchesSearch(item) {
        if (!this.filters.search) return true;
        const searchTerm = this.filters.search.toLowerCase();
        return (item.name && item.name.toLowerCase().includes(searchTerm)) ||
               (item.specialization && item.specialization.toLowerCase().includes(searchTerm)) ||
               (item.location && item.location.toLowerCase().includes(searchTerm)) ||
               (item.case_title && item.case_title.toLowerCase().includes(searchTerm)) ||
               (item.user_name && item.user_name.toLowerCase().includes(searchTerm));
    }

    matchesSpecialty(item) {
        if (!this.filters.specialty) return true;
        return item.specialization && item.specialization.toLowerCase().includes(this.filters.specialty.toLowerCase());
    }

    matchesExperience(item) {
        if (!this.filters.experience) return true;
        const [min, max] = this.filters.experience.split('-').map(x => x === '+' ? Infinity : parseInt(x));
        const experience = item.years_experience || item.experience || 0;
        return experience >= min && experience <= max;
    }

    matchesRating(item) {
        if (!this.filters.rating) return true;
        const minRating = parseFloat(this.filters.rating);
        return (item.rating || 0) >= minRating;
    }

    matchesLocation(item) {
        if (!this.filters.location) return true;
        const locationTerm = this.filters.location.toLowerCase();
        return (item.location && item.location.toLowerCase().includes(locationTerm)) ||
               (item.pincode && item.pincode.includes(locationTerm));
    }

    matchesCourt(item) {
        if (!this.filters.court) return true;
        return item.court_workplace === this.filters.court;
    }

    matchesWinRate(item) {
        if (!this.filters.winRate) return true;
        const minWinRate = parseFloat(this.filters.winRate);
        return (item.case_win_rate || 0) >= minWinRate;
    }

    matchesFee(item) {
        if (!this.filters.fee) return true;
        const fee = item.consultation_fee || 0;
        const [min, max] = this.filters.fee.split('-').map(x => x === '+' ? Infinity : parseInt(x));
        return fee >= min && fee <= max;
    }

    matchesStatus(item) {
        if (!this.filters.status) return true;
        return item.status === this.filters.status || item.case_status === this.filters.status;
    }

    matchesType(item) {
        if (!this.filters.type) return true;
        return item.case_type === this.filters.type;
    }

    matchesPriority(item) {
        if (!this.filters.priority) return true;
        return item.priority === this.filters.priority;
    }

    // Sort and paginate
    sortAndPaginate() {
        const sortBy = this.getFilterValue('#sortFilter, #sort-filter');
        
        this.filteredItems.sort((a, b) => {
            switch (sortBy) {
                case 'name':
                    return (a.name || '').localeCompare(b.name || '');
                case 'experience':
                    return (b.years_experience || b.experience || 0) - (a.years_experience || a.experience || 0);
                case 'win_rate':
                    return (b.case_win_rate || 0) - (a.case_win_rate || 0);
                case 'fee_low':
                    return (a.consultation_fee || 0) - (b.consultation_fee || 0);
                case 'fee_high':
                    return (b.consultation_fee || 0) - (a.consultation_fee || 0);
                case 'oldest':
                    return new Date(a.created_at) - new Date(b.created_at);
                case 'priority':
                    const priorityOrder = { 'urgent': 4, 'high': 3, 'medium': 2, 'low': 1 };
                    return (priorityOrder[b.priority] || 0) - (priorityOrder[a.priority] || 0);
                case 'status':
                    const statusOrder = { 'open': 4, 'in_progress': 3, 'pending': 2, 'closed': 1 };
                    return (statusOrder[b.case_status] || 0) - (statusOrder[a.case_status] || 0);
                case 'newest':
                    return new Date(b.created_at) - new Date(a.created_at);
                case 'rating':
                default:
                    return (b.rating || 0) - (a.rating || 0);
            }
        });
        
        this.currentPage = 1;
        this.updateDisplay();
    }

    // Clear all filters
    clearAllFilters() {
        const filters = [
            '#searchInput', '#search-filter',
            '#specialtyFilter', '#specialty-filter',
            '#experienceFilter', '#experience-filter',
            '#ratingFilter', '#rating-filter',
            '#locationFilter', '#location-filter',
            '#courtFilter', '#winRateFilter', '#feeFilter',
            '#statusFilter', '#typeFilter', '#priorityFilter'
        ];
        
        filters.forEach(selector => {
            const element = this.container.querySelector(selector);
            if (element) {
                element.value = '';
            }
        });
        
        const sortFilter = this.container.querySelector('#sortFilter, #sort-filter');
        if (sortFilter) {
            sortFilter.value = 'rating';
        }
        
        this.filteredItems = [...this.allItems];
        this.currentPage = 1;
        this.updateDisplay();
        this.updateFilterStatus();
    }

    // Update display (to be implemented by specific templates)
    updateDisplay() {
        // This method should be overridden by specific implementations
        console.log('updateDisplay should be implemented by specific templates');
    }

    // Update filter status
    updateFilterStatus() {
        const statusElement = this.container.querySelector('#filterStatus, #filter-status');
        if (!statusElement) return;
        
        const filters = [];
        if (this.filters.search) filters.push(`Search: "${this.filters.search}"`);
        if (this.filters.specialty) filters.push(`Specialty: ${this.filters.specialty}`);
        if (this.filters.experience) filters.push(`Experience: ${this.filters.experience}`);
        if (this.filters.rating) filters.push(`Rating: ${this.filters.rating}+`);
        if (this.filters.location) filters.push(`Location: ${this.filters.location}`);
        if (this.filters.court) filters.push(`Court: ${this.filters.court}`);
        if (this.filters.winRate) filters.push(`Win Rate: ${this.filters.winRate}%+`);
        if (this.filters.fee) filters.push(`Fee: ${this.filters.fee}`);
        if (this.filters.status) filters.push(`Status: ${this.filters.status}`);
        if (this.filters.type) filters.push(`Type: ${this.filters.type}`);
        if (this.filters.priority) filters.push(`Priority: ${this.filters.priority}`);
        
        const status = filters.length > 0 ? `Filtered by: ${filters.join(', ')}` : 'Showing all items';
        statusElement.textContent = status;
    }

    // Utility function for debouncing
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Get current filtered items
    getFilteredItems() {
        return this.filteredItems;
    }

    // Get paginated items
    getPaginatedItems() {
        if (!this.options.pagination) return this.filteredItems;
        
        const startIndex = (this.currentPage - 1) * this.options.itemsPerPage;
        const endIndex = startIndex + this.options.itemsPerPage;
        return this.filteredItems.slice(startIndex, endIndex);
    }

    // Get total pages
    getTotalPages() {
        return Math.ceil(this.filteredItems.length / this.options.itemsPerPage);
    }
}

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LegalMatchFilter;
} else {
    window.LegalMatchFilter = LegalMatchFilter;
}
