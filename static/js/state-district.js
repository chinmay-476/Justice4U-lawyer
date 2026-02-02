/**
 * State-District Management JavaScript
 * Handles AJAX loading of Indian states and districts
 */

class StateDistrictManager {
    constructor() {
        this.statesData = {};
        this.init();
    }

    init() {
        this.loadStates();
    }

    async loadStates() {
        try {
            const response = await fetch('/api/states');
            const data = await response.json();
            
            if (data.success) {
                this.statesData = data.states;
                this.populateStateSelects();
            }
        } catch (error) {
            console.error('Error loading states:', error);
        }
    }

    populateStateSelects() {
        const stateSelects = document.querySelectorAll('#state, #stateFilter');
        
        stateSelects.forEach(select => {
            if (select) {
                select.innerHTML = '<option value="">Select State</option>';
                
                this.statesData.forEach(state => {
                    const option = document.createElement('option');
                    option.value = state;
                    option.textContent = state;
                    select.appendChild(option);
                });
            }
        });
    }

    async loadDistricts(state, targetSelectId) {
        if (!state) {
            const districtSelect = document.getElementById(targetSelectId);
            if (districtSelect) {
                districtSelect.innerHTML = '<option value="">Select District</option>';
                districtSelect.disabled = true;
            }
            return;
        }

        try {
            const response = await fetch(`/api/districts/${encodeURIComponent(state)}`);
            const data = await response.json();
            
            if (data.success) {
                const districtSelect = document.getElementById(targetSelectId);
                if (districtSelect) {
                    districtSelect.innerHTML = '<option value="">Select District</option>';
                    
                    data.districts.forEach(district => {
                        const option = document.createElement('option');
                        option.value = district;
                        option.textContent = district;
                        districtSelect.appendChild(option);
                    });
                    
                    districtSelect.disabled = false;
                }
            }
        } catch (error) {
            console.error('Error loading districts:', error);
        }
    }

    setupStateDistrictHandlers(stateSelectId, districtSelectId) {
        const stateSelect = document.getElementById(stateSelectId);
        const districtSelect = document.getElementById(districtSelectId);
        
        if (stateSelect && districtSelect) {
            stateSelect.addEventListener('change', (e) => {
                const selectedState = e.target.value;
                this.loadDistricts(selectedState, districtSelectId);
            });
        }
    }

    // For filtering pages - load states with lowercase values
    async loadStatesForFilter() {
        try {
            const response = await fetch('/api/states');
            const data = await response.json();
            
            if (data.success) {
                const stateSelects = document.querySelectorAll('#stateFilter');
                
                stateSelects.forEach(select => {
                    if (select) {
                        select.innerHTML = '<option value="">All States</option>';
                        
                        data.states.forEach(state => {
                            const option = document.createElement('option');
                            option.value = state.toLowerCase();
                            option.textContent = state;
                            select.appendChild(option);
                        });
                    }
                });
            }
        } catch (error) {
            console.error('Error loading states for filter:', error);
        }
    }

    async loadDistrictsForFilter(state, targetSelectId) {
        if (!state) {
            const districtSelect = document.getElementById(targetSelectId);
            if (districtSelect) {
                districtSelect.innerHTML = '<option value="">All Districts</option>';
                districtSelect.disabled = true;
            }
            return;
        }

        try {
            const response = await fetch(`/api/districts/${encodeURIComponent(state)}`);
            const data = await response.json();
            
            if (data.success) {
                const districtSelect = document.getElementById(targetSelectId);
                if (districtSelect) {
                    districtSelect.innerHTML = '<option value="">All Districts</option>';
                    
                    data.districts.forEach(district => {
                        const option = document.createElement('option');
                        option.value = district.toLowerCase();
                        option.textContent = district;
                        districtSelect.appendChild(option);
                    });
                    
                    districtSelect.disabled = false;
                }
            }
        } catch (error) {
            console.error('Error loading districts for filter:', error);
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.stateDistrictManager = new StateDistrictManager();
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StateDistrictManager;
}
