/**
 * LegalMatch Reusable Components
 * This file contains modular, reusable components for the LegalMatch platform
 */

// Global LegalMatch object to hold all components
window.LegalMatch = window.LegalMatch || {};

/**
 * Alert System Component
 * Provides consistent alert notifications across the platform
 */
LegalMatch.Alert = {
    container: null,
    
    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'alertContainer';
            this.container.className = 'position-fixed top-0 end-0 p-3';
            this.container.style.zIndex = '9999';
            document.body.appendChild(this.container);
        }
    },
    
    show(message, type = 'info', duration = 5000) {
        this.init();
        
        const alertId = 'alert-' + Date.now();
        const icon = this.getIcon(type);
        const alertHTML = `
            <div id="${alertId}" class="alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show" role="alert">
                <i class="bi bi-${icon} me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        this.container.insertAdjacentHTML('beforeend', alertHTML);
        
        // Auto-dismiss
        setTimeout(() => {
            const alert = document.getElementById(alertId);
            if (alert) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        }, duration);
    },
    
    getIcon(type) {
        const icons = {
            'success': 'check-circle-fill',
            'danger': 'exclamation-triangle-fill',
            'error': 'exclamation-triangle-fill',
            'warning': 'exclamation-triangle-fill',
            'info': 'info-circle-fill'
        };
        return icons[type] || 'info-circle-fill';
    }
};

/**
 * Form Validation Component
 * Provides consistent form validation across the platform
 */
LegalMatch.FormValidator = {
    validators: {
        required: (value) => value && value.trim().length > 0,
        email: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
        phone: (value) => !value || /^[\+]?[1-9][\d]{0,15}$/.test(value),
        minLength: (min) => (value) => value.length >= min,
        maxLength: (max) => (value) => value.length <= max,
        range: (min, max) => (value) => {
            const num = parseInt(value);
            return !isNaN(num) && num >= min && num <= max;
        }
    },
    
    validateField(field, rules) {
        const value = field.value;
        let isValid = true;
        let errorMessage = '';
        
        for (const rule of rules) {
            if (typeof rule === 'string') {
                const validator = this.validators[rule];
                if (validator && !validator(value)) {
                    isValid = false;
                    errorMessage = this.getErrorMessage(rule);
                    break;
                }
            } else if (typeof rule === 'function') {
                if (!rule(value)) {
                    isValid = false;
                    errorMessage = 'Invalid input';
                    break;
                }
            }
        }
        
        this.updateFieldState(field, isValid);
        return { isValid, errorMessage };
    },
    
    validateForm(form, rules) {
        let isFormValid = true;
        const errors = {};
        
        for (const [fieldName, fieldRules] of Object.entries(rules)) {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (field) {
                const result = this.validateField(field, fieldRules);
                if (!result.isValid) {
                    isFormValid = false;
                    errors[fieldName] = result.errorMessage;
                }
            }
        }
        
        return { isFormValid, errors };
    },
    
    updateFieldState(field, isValid) {
        field.classList.toggle('is-valid', isValid && field.value.length > 0);
        field.classList.toggle('is-invalid', !isValid && field.value.length > 0);
    },
    
    getErrorMessage(rule) {
        const messages = {
            'required': 'This field is required',
            'email': 'Please enter a valid email address',
            'phone': 'Please enter a valid phone number',
            'minLength': 'Input is too short',
            'maxLength': 'Input is too long',
            'range': 'Value is out of range'
        };
        return messages[rule] || 'Invalid input';
    }
};

/**
 * Rating System Component
 * Provides consistent rating functionality across the platform
 */
LegalMatch.Rating = {
    currentRating: 0,
    lawyerId: null,
    
    init(container) {
        this.container = container;
        this.setupEventListeners();
    },
    
    setupEventListeners() {
        const ratingButtons = this.container.querySelectorAll('.rating-btn');
        const submitBtn = this.container.querySelector('#submitRating');
        
        ratingButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.currentRating = parseInt(e.currentTarget.dataset.rating);
                this.updateRatingButtons();
                if (submitBtn) submitBtn.disabled = false;
            });
            
            btn.addEventListener('mouseenter', (e) => {
                const rating = parseInt(e.currentTarget.dataset.rating);
                this.highlightStars(rating);
            });
        });
        
        this.container.addEventListener('mouseleave', () => {
            this.updateRatingButtons();
        });
        
        if (submitBtn) {
            submitBtn.addEventListener('click', () => this.submitRating());
        }
    },
    
    highlightStars(rating) {
        const ratingButtons = this.container.querySelectorAll('.rating-btn');
        ratingButtons.forEach((btn, index) => {
            const star = btn.querySelector('i');
            if (index < rating) {
                star.className = 'bi bi-star-fill';
                btn.classList.add('btn-warning');
                btn.classList.remove('btn-outline-warning');
            } else {
                star.className = 'bi bi-star';
                btn.classList.remove('btn-warning');
                btn.classList.add('btn-outline-warning');
            }
        });
    },
    
    updateRatingButtons() {
        this.highlightStars(this.currentRating);
    },
    
    async submitRating() {
        if (this.currentRating === 0) return;
        
        const submitBtn = this.container.querySelector('#submitRating');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Submitting...';
        submitBtn.disabled = true;
        
        try {
            const response = await fetch('/api/rate-lawyer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    lawyer_id: this.lawyerId,
                    rating: this.currentRating
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                LegalMatch.Alert.show(
                    `Thank you for your ${this.currentRating}-star rating!`, 
                    'success'
                );
                this.reset();
                this.updateDisplay(data.new_rating, data.total_ratings);
            } else {
                LegalMatch.Alert.show(data.error || 'Error submitting rating', 'error');
            }
        } catch (error) {
            LegalMatch.Alert.show('Network error. Please try again.', 'error');
        } finally {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    },
    
    updateDisplay(newRating, totalRatings) {
        // This would be implemented by the parent component
        if (window.updateLawyerRatingDisplay) {
            window.updateLawyerRatingDisplay(this.lawyerId, newRating, totalRatings);
        }
    },
    
    reset() {
        this.currentRating = 0;
        this.updateRatingButtons();
        const submitBtn = this.container.querySelector('#submitRating');
        if (submitBtn) submitBtn.disabled = true;
    }
};

/**
 * Search and Filter Component
 * Provides consistent search and filtering functionality
 */
LegalMatch.SearchFilter = {
    filters: {},
    results: [],
    currentPage: 1,
    itemsPerPage: 9,
    
    init(container, options = {}) {
        this.container = container;
        this.options = { ...this.defaultOptions, ...options };
        this.setupEventListeners();
        this.loadInitialData();
    },
    
    defaultOptions: {
        searchFields: ['name', 'specialization', 'location'],
        filterFields: ['specialization', 'experience', 'rating'],
        sortOptions: ['rating', 'experience', 'name', 'recent'],
        pagination: true
    },
    
    setupEventListeners() {
        const searchInput = this.container.querySelector('#searchInput');
        const filterInputs = this.container.querySelectorAll('[id$="Filter"]');
        const clearBtn = this.container.querySelector('#clearFilters');
        
        if (searchInput) {
            searchInput.addEventListener('input', this.debounce(() => this.filter(), 300));
        }
        
        filterInputs.forEach(input => {
            input.addEventListener('change', () => this.filter());
        });
        
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearFilters());
        }
    },
    
    loadInitialData() {
        // This would be implemented by the parent component
        if (window.loadSearchData) {
            this.results = window.loadSearchData();
            this.updateDisplay();
        }
    },
    
    filter() {
        this.collectFilters();
        this.applyFilters();
        this.currentPage = 1;
        this.updateDisplay();
    },
    
    collectFilters() {
        const searchInput = this.container.querySelector('#searchInput');
        const filterInputs = this.container.querySelectorAll('[id$="Filter"]');
        
        this.filters = {
            search: searchInput ? searchInput.value.toLowerCase() : '',
        };
        
        filterInputs.forEach(input => {
            const field = input.id.replace('Filter', '');
            this.filters[field] = input.value;
        });
    },
    
    applyFilters() {
        this.filteredResults = this.results.filter(item => {
            // Search filter
            if (this.filters.search) {
                const searchMatch = this.options.searchFields.some(field => 
                    item[field] && item[field].toLowerCase().includes(this.filters.search)
                );
                if (!searchMatch) return false;
            }
            
            // Other filters
            for (const [field, value] of Object.entries(this.filters)) {
                if (field === 'search' || !value) continue;
                
                if (field === 'experience' && value) {
                    const [min, max] = value.split('-').map(x => x === '+' ? Infinity : parseInt(x));
                    if (item.years_experience < min || item.years_experience > max) return false;
                } else if (field === 'rating' && value) {
                    if (item.rating < parseFloat(value)) return false;
                } else if (item[field] && !item[field].toLowerCase().includes(value.toLowerCase())) {
                    return false;
                }
            }
            
            return true;
        });
    },
    
    updateDisplay() {
        if (this.options.pagination) {
            this.updatePagination();
        }
        this.updateResults();
    },
    
    updatePagination() {
        const totalPages = Math.ceil(this.filteredResults.length / this.itemsPerPage);
        const pagination = this.container.querySelector('#pagination');
        
        if (!pagination) return;
        
        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }
        
        let paginationHTML = '';
        
        // Previous button
        paginationHTML += `
            <li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${this.currentPage - 1}">Previous</a>
            </li>
        `;
        
        // Page numbers
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(totalPages, this.currentPage + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            paginationHTML += `
                <li class="page-item ${i === this.currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }
        
        // Next button
        paginationHTML += `
            <li class="page-item ${this.currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${this.currentPage + 1}">Next</a>
            </li>
        `;
        
        pagination.innerHTML = paginationHTML;
        
        // Add click event listeners
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                if (page && page !== this.currentPage && page >= 1 && page <= totalPages) {
                    this.currentPage = page;
                    this.updateDisplay();
                }
            });
        });
    },
    
    updateResults() {
        // This would be implemented by the parent component
        if (window.updateSearchResults) {
            const startIndex = (this.currentPage - 1) * this.itemsPerPage;
            const endIndex = startIndex + this.itemsPerPage;
            const itemsToShow = this.filteredResults.slice(startIndex, endIndex);
            window.updateSearchResults(itemsToShow);
        }
    },
    
    clearFilters() {
        const searchInput = this.container.querySelector('#searchInput');
        const filterInputs = this.container.querySelectorAll('[id$="Filter"]');
        
        if (searchInput) searchInput.value = '';
        filterInputs.forEach(input => input.value = '');
        
        this.filter();
    },
    
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
};

/**
 * Modal Component
 * Provides consistent modal functionality
 */
LegalMatch.Modal = {
    modals: new Map(),
    
    create(id, options = {}) {
        const modal = {
            id,
            title: options.title || 'Modal',
            content: options.content || '',
            size: options.size || 'md',
            buttons: options.buttons || []
        };
        
        this.modals.set(id, modal);
        this.render(modal);
        return modal;
    },
    
    render(modal) {
        const modalHTML = `
            <div class="modal fade" id="${modal.id}" tabindex="-1">
                <div class="modal-dialog modal-${modal.size}">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">${modal.title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            ${modal.content}
                        </div>
                        <div class="modal-footer">
                            ${modal.buttons.map(btn => `
                                <button type="button" class="btn btn-${btn.type || 'secondary'}" 
                                        data-bs-dismiss="${btn.dismiss ? 'modal' : ''}"
                                        ${btn.onclick ? `onclick="${btn.onclick}"` : ''}>
                                    ${btn.text}
                                </button>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove existing modal if it exists
        const existing = document.getElementById(modal.id);
        if (existing) existing.remove();
        
        // Add to body
        document.body.insertAdjacentHTML('beforeend', modalHTML);
    },
    
    show(id) {
        const modalElement = document.getElementById(id);
        if (modalElement) {
            const bsModal = new bootstrap.Modal(modalElement);
            bsModal.show();
        }
    },
    
    hide(id) {
        const modalElement = document.getElementById(id);
        if (modalElement) {
            const bsModal = bootstrap.Modal.getInstance(modalElement);
            if (bsModal) bsModal.hide();
        }
    }
};

/**
 * Loading Component
 * Provides consistent loading states across the platform
 */
LegalMatch.Loading = {
    show(element, message = 'Loading...') {
        if (typeof element === 'string') {
            element = document.querySelector(element);
        }
        if (element) {
            element.dataset.originalContent = element.innerHTML;
            element.innerHTML = `
                <div class="d-flex align-items-center justify-content-center">
                    <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                    <span>${message}</span>
                </div>
            `;
            element.disabled = true;
        }
    },
    
    hide(element) {
        if (typeof element === 'string') {
            element = document.querySelector(element);
        }
        if (element && element.dataset.originalContent) {
            element.innerHTML = element.dataset.originalContent;
            element.disabled = false;
            delete element.dataset.originalContent;
        }
    }
};

/**
 * Utility Functions
 */
LegalMatch.Utils = {
    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    },
    
    formatPhone(phone) {
        const cleaned = phone.replace(/\D/g, '');
        if (cleaned.length >= 10) {
            return cleaned.replace(/(\d{3})(\d{3})(\d{4})/, '($1) $2-$3');
        }
        return phone;
    },
    
    generateStars(rating) {
        let stars = '';
        for (let i = 1; i <= 5; i++) {
            if (i <= rating) {
                stars += '<i class="bi bi-star-fill text-warning"></i>';
            } else {
                stars += '<i class="bi bi-star"></i>';
            }
        }
        return stars;
    },
    
    sanitizeInput(input) {
        return input.replace(/[<>]/g, '');
    }
};

// Initialize components when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Auto-initialize rating components
    document.querySelectorAll('.rating-container').forEach(container => {
        LegalMatch.Rating.init(container);
    });
    
    // Auto-initialize search filter components
    document.querySelectorAll('.search-filter-container').forEach(container => {
        LegalMatch.SearchFilter.init(container);
    });
});
