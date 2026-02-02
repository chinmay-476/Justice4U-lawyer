// Lawyers Page JavaScript - Enhanced Search, Filter, and Rating System

document.addEventListener('DOMContentLoaded', function() {
    initializeLawyersPage();
});

let allLawyers = [];
let filteredLawyers = [];
let selectedRating = 0;
let currentRatingLawyerId = null;

function initializeLawyersPage() {
    loadLawyers();
    initializeFilters();
    initializeRatingSystem();
}

// Load lawyers from API
async function loadLawyers() {
    const grid = document.getElementById('lawyersGrid');
    const loading = document.getElementById('loadingSpinner');
    const noResults = document.getElementById('noResults');
    
    try {
        loading.classList.remove('d-none');
        grid.style.display = 'none';
        
        const response = await fetch('/api/lawyers');
        const data = await response.json();
        
        if (data.success) {
            allLawyers = data.lawyers;
            filteredLawyers = [...allLawyers];
            renderLawyers(filteredLawyers);
            updateLawyerCount(filteredLawyers.length);
        } else {
            throw new Error(data.error || 'Failed to load lawyers');
        }
    } catch (error) {
        console.error('Error loading lawyers:', error);
        showError('Failed to load lawyers. Please try again.');
        noResults.classList.remove('d-none');
    } finally {
        loading.classList.add('d-none');
        grid.style.display = 'block';
    }
}

// Initialize search and filter functionality
function initializeFilters() {
    const searchInput = document.getElementById('searchInput');
    const specialtyFilter = document.getElementById('specialtyFilter');
    const sortFilter = document.getElementById('sortFilter');
    const clearFilters = document.getElementById('clearFilters');
    
    // Debounced search
    const debouncedSearch = debounce(filterAndRenderLawyers, 300);
    
    searchInput.addEventListener('input', debouncedSearch);
    specialtyFilter.addEventListener('change', filterAndRenderLawyers);
    sortFilter.addEventListener('change', filterAndRenderLawyers);
    
    clearFilters.addEventListener('click', function() {
        searchInput.value = '';
        specialtyFilter.value = '';
        sortFilter.value = 'rating';
        filterAndRenderLawyers();
    });
}

// Filter and render lawyers based on current filters
function filterAndRenderLawyers() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase().trim();
    const selectedSpecialty = document.getElementById('specialtyFilter').value.toLowerCase();
    const sortBy = document.getElementById('sortFilter').value;
    
    // Filter lawyers
    filteredLawyers = allLawyers.filter(lawyer => {
        const matchesSearch = !searchTerm || 
            lawyer.name.toLowerCase().includes(searchTerm) ||
            lawyer.specialization.toLowerCase().includes(searchTerm) ||
            lawyer.location.toLowerCase().includes(searchTerm) ||
            (lawyer.keywords && lawyer.keywords.some(keyword => 
                keyword.toLowerCase().includes(searchTerm)
            ));
            
        const matchesSpecialty = !selectedSpecialty ||
            lawyer.specialization.toLowerCase().includes(selectedSpecialty);
            
        return matchesSearch && matchesSpecialty;
    });
    
    // Sort lawyers
    filteredLawyers.sort((a, b) => {
        switch (sortBy) {
            case 'experience':
                return b.years_experience - a.years_experience;
            case 'name':
                return a.name.localeCompare(b.name);
            case 'rating':
            default:
                return b.rating - a.rating;
        }
    });
    
    renderLawyers(filteredLawyers);
    updateLawyerCount(filteredLawyers.length);
}

// Render lawyers in the grid
function renderLawyers(lawyers) {
    const grid = document.getElementById('lawyersGrid');
    const noResults = document.getElementById('noResults');
    
    if (lawyers.length === 0) {
        grid.innerHTML = '';
        grid.classList.add('d-none');
        noResults.classList.remove('d-none');
        return;
    }
    
    grid.classList.remove('d-none');
    noResults.classList.add('d-none');
    
    grid.innerHTML = lawyers.map(lawyer => createLawyerCard(lawyer)).join('');
    
    // Add staggered animation
    const cards = grid.querySelectorAll('.lawyer-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 50);
    });
}

// Create individual lawyer card HTML
function createLawyerCard(lawyer) {
    const stars = generateStarRating(lawyer.rating);
    const keywords = lawyer.keywords ? lawyer.keywords.slice(0, 3) : [];
    
    return `
        <div class="col-lg-4 col-md-6 lawyer-card">
            <div class="card h-100 shadow-sm border-0 lawyer-item">
                <div class="position-relative">
                    <img src="${lawyer.photo}" class="card-img-top lawyer-photo" alt="${lawyer.name}" loading="lazy">
                    <div class="position-absolute top-0 end-0 p-2">
                        <span class="badge bg-success">
                            <i class="bi bi-patch-check-fill me-1"></i>Verified
                        </span>
                    </div>
                    ${lawyer.rating >= 4.5 ? '<div class="position-absolute top-0 start-0 p-2"><span class="badge bg-warning"><i class="bi bi-star-fill me-1"></i>Top Rated</span></div>' : ''}
                </div>
                
                <div class="card-body d-flex flex-column">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <h5 class="card-title mb-0">${lawyer.name}</h5>
                        <div class="rating-display">
                            <div class="stars">${stars}</div>
                            <small class="text-muted d-block text-center">
                                ${lawyer.rating}/5 
                                ${lawyer.total_ratings ? `(${lawyer.total_ratings})` : '(0)'}
                            </small>
                        </div>
                    </div>
                    
                    <div class="mb-2">
                        <span class="badge bg-primary-subtle text-primary">
                            ${lawyer.specialization}
                        </span>
                        ${lawyer.years_experience >= 10 ? '<span class="badge bg-info-subtle text-info ms-1">Senior</span>' : ''}
                    </div>
                    
                    <div class="text-muted small mb-2">
                        <i class="bi bi-geo-alt me-1"></i>${lawyer.location}
                        <span class="mx-2">|</span>
                        <i class="bi bi-briefcase me-1"></i>${lawyer.years_experience} years exp.
                    </div>
                    
                    ${keywords.length > 0 ? `
                        <div class="mb-2">
                            ${keywords.map(keyword => `<span class="badge bg-light text-dark me-1">${keyword}</span>`).join('')}
                        </div>
                    ` : ''}
                    
                    <p class="card-text text-muted small flex-grow-1">
                        ${truncateText(lawyer.bio, 120)}
                    </p>
                    
                    <div class="mt-auto">
                        <div class="d-flex gap-2 mb-3">
                            <a href="tel:${lawyer.phone}" class="btn btn-outline-primary btn-sm flex-fill">
                                <i class="bi bi-telephone me-1"></i>Call
                            </a>
                            <a href="mailto:${lawyer.email}" class="btn btn-outline-secondary btn-sm flex-fill">
                                <i class="bi bi-envelope me-1"></i>Email
                            </a>
                        </div>
                        
                        <div class="d-flex gap-2">
                            <a href="/lawyer/${lawyer.id}" class="btn btn-primary btn-sm flex-fill">
                                <i class="bi bi-person me-1"></i>View Profile
                            </a>
                            <button class="btn btn-outline-warning btn-sm" 
                                    onclick="openRatingModal(${lawyer.id}, '${lawyer.name}')">
                                <i class="bi bi-star me-1"></i>Rate
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Generate star rating HTML
function generateStarRating(rating) {
    let stars = '';
    const fullStars = Math.floor(rating);
    const hasHalfStar = rating % 1 >= 0.5;
    
    for (let i = 1; i <= 5; i++) {
        if (i <= fullStars) {
            stars += '<i class="bi bi-star-fill text-warning"></i>';
        } else if (i === fullStars + 1 && hasHalfStar) {
            stars += '<i class="bi bi-star-half text-warning"></i>';
        } else {
            stars += '<i class="bi bi-star text-muted"></i>';
        }
    }
    
    return stars;
}

// Truncate text to specified length
function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Update lawyer count display
function updateLawyerCount(count) {
    const countElement = document.getElementById('lawyerCount');
    if (countElement) {
        countElement.textContent = `${count} lawyer${count !== 1 ? 's' : ''} found`;
    }
}

// Rating System
function initializeRatingSystem() {
    const modal = document.getElementById('ratingModal');
    const ratingButtons = document.querySelectorAll('.rating-btn');
    const submitButton = document.getElementById('submitRating');
    
    // Rating button interactions
    ratingButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            selectedRating = parseInt(this.dataset.rating);
            updateRatingButtons(ratingButtons);
            submitButton.disabled = false;
        });
        
        btn.addEventListener('mouseenter', function() {
            const rating = parseInt(this.dataset.rating);
            highlightStars(ratingButtons, rating);
        });
    });
    
    document.querySelector('.rating-input').addEventListener('mouseleave', function() {
        updateRatingButtons(ratingButtons);
    });
    
    // Submit rating
    submitButton.addEventListener('click', submitRating);
    
    // Reset modal on close
    if (modal) {
        modal.addEventListener('hidden.bs.modal', function() {
            resetRatingModal();
        });
    }
}

// Open rating modal
function openRatingModal(lawyerId, lawyerName) {
    currentRatingLawyerId = lawyerId;
    document.getElementById('ratingLawyerName').textContent = lawyerName;
    
    const modal = new bootstrap.Modal(document.getElementById('ratingModal'));
    modal.show();
}

// Highlight stars on hover
function highlightStars(buttons, rating) {
    buttons.forEach((btn, index) => {
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
}

// Update rating buttons based on selection
function updateRatingButtons(buttons) {
    highlightStars(buttons, selectedRating);
}

// Submit rating to server
async function submitRating() {
    const submitBtn = document.getElementById('submitRating');
    const errorDiv = document.getElementById('ratingError');
    const successDiv = document.getElementById('ratingSuccess');
    
    if (!currentRatingLawyerId || selectedRating === 0) return;
    
    // Reset messages
    errorDiv.classList.add('d-none');
    successDiv.classList.add('d-none');
    
    // Show loading state
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Submitting...';
    submitBtn.disabled = true;
    
    try {
        const response = await fetch('/api/rate-lawyer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                lawyer_id: currentRatingLawyerId,
                rating: selectedRating
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            successDiv.textContent = 'Thank you for your rating!';
            successDiv.classList.remove('d-none');
            
            // Update the lawyer's rating in the current view
            updateLawyerRatingInDOM(currentRatingLawyerId, data.new_rating, data.total_ratings);
            
            // Close modal after delay
            setTimeout(() => {
                bootstrap.Modal.getInstance(document.getElementById('ratingModal')).hide();
            }, 2000);
        } else {
            throw new Error(data.error || 'Failed to submit rating');
        }
    } catch (error) {
        console.error('Rating submission error:', error);
        errorDiv.textContent = error.message || 'Error submitting rating';
        errorDiv.classList.remove('d-none');
    } finally {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
    }
}

// Update lawyer rating in the DOM
function updateLawyerRatingInDOM(lawyerId, newRating, totalRatings) {
    // Find the lawyer card and update its rating
    const cards = document.querySelectorAll('.lawyer-card');
    cards.forEach(card => {
        const profileLink = card.querySelector(`a[href="/lawyer/${lawyerId}"]`);
        if (profileLink) {
            const ratingDisplay = card.querySelector('.rating-display');
            const stars = ratingDisplay.querySelector('.stars');
            const ratingText = ratingDisplay.querySelector('small');
            
            stars.innerHTML = generateStarRating(newRating);
            ratingText.innerHTML = `${newRating}/5 (${totalRatings})`;
        }
    });
    
    // Update the lawyer in our data
    const lawyerIndex = allLawyers.findIndex(l => l.id === lawyerId);
    if (lawyerIndex !== -1) {
        allLawyers[lawyerIndex].rating = newRating;
        allLawyers[lawyerIndex].total_ratings = totalRatings;
    }
}

// Reset rating modal
function resetRatingModal() {
    selectedRating = 0;
    currentRatingLawyerId = null;
    
    const buttons = document.querySelectorAll('.rating-btn');
    buttons.forEach(btn => {
        btn.classList.remove('btn-warning');
        btn.classList.add('btn-outline-warning');
        btn.querySelector('i').className = 'bi bi-star';
    });
    
    document.getElementById('submitRating').disabled = true;
    document.getElementById('ratingError').classList.add('d-none');
    document.getElementById('ratingSuccess').classList.add('d-none');
}

// Utility functions
function debounce(func, wait) {
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

function showError(message) {
    // You can integrate this with your global alert system
    console.error(message);
    
    // Show alert if global function exists
    if (window.LegalMatch && window.LegalMatch.showAlert) {
        window.LegalMatch.showAlert(message, 'danger');
    }
}

// Export for global use
window.openRatingModal = openRatingModal;