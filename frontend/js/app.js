/**
 * MealMate Main Application
 * Core application logic and event handlers
 */

// Global state
const AppState = {
    currentShoppingList: null,
    categories: [],
    cuisines: [],
    searchTimeout: null,
};

// ========================================
// Initialization
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing app...');
    initializeApp();
});

async function initializeApp() {
    console.log('initializeApp called');
    // Check if user is logged in
    const token = API.getToken();
    console.log('Token:', token ? 'exists' : 'not found');
    if (token) {
        // Show app screen
        console.log('User has token, showing app screen');
        showScreen('app-screen');
        await loadInitialData();
        setupEventListeners();
    } else {
        // Show auth screen
        console.log('No token, showing auth screen and setting up auth listeners');
        showScreen('auth-screen');
        setupAuthListeners();
    }
}

function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(screen => {
        screen.classList.remove('active');
    });
    document.getElementById(screenId).classList.add('active');
}

// ========================================
// Authentication
// ========================================

function setupAuthListeners() {
    console.log('Setting up auth listeners...');

    // Toggle between login and register forms
    document.getElementById('show-register').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('login-form').classList.add('hidden');
        document.getElementById('register-form').classList.remove('hidden');
    });

    document.getElementById('show-login').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('register-form').classList.add('hidden');
        document.getElementById('login-form').classList.remove('hidden');
    });

    // Login
    document.getElementById('login-btn').addEventListener('click', async () => {
        console.log('Login button clicked!');
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        console.log('Username:', username, 'Password length:', password.length);

        if (!username || !password) {
            ExportUtils.showToast('Please enter username and password', 'error');
            return;
        }

        try {
            await API.Auth.login(username, password);
            console.log('Login successful, switching screen...');
            showScreen('app-screen');
            console.log('Screen switched, loading data...');
            await loadInitialData();
            console.log('Data loaded, setting up listeners...');
            setupEventListeners();
            console.log('All done!');
        } catch (error) {
            console.error('Login error:', error);
            ExportUtils.showToast(error.message, 'error');
        }
    });

    // Register
    document.getElementById('register-btn').addEventListener('click', async () => {
        const username = document.getElementById('register-username').value.trim();
        const password = document.getElementById('register-password').value;

        if (!username || !password) {
            ExportUtils.showToast('Please enter username and password', 'error');
            return;
        }

        if (password.length < 6) {
            ExportUtils.showToast('Password must be at least 6 characters', 'error');
            return;
        }

        try {
            await API.Auth.register(username, password);
            showScreen('app-screen');
            await loadInitialData();
            setupEventListeners();
        } catch (error) {
            ExportUtils.showToast(error.message, 'error');
        }
    });

    // Handle Enter key in forms
    ['login-username', 'login-password'].forEach(id => {
        document.getElementById(id).addEventListener('keypress', (e) => {
            if (e.key === 'Enter') document.getElementById('login-btn').click();
        });
    });

    ['register-username', 'register-password'].forEach(id => {
        document.getElementById(id).addEventListener('keypress', (e) => {
            if (e.key === 'Enter') document.getElementById('register-btn').click();
        });
    });
}

// ========================================
// Initial Data Loading
// ========================================

async function loadInitialData() {
    try {
        // Load categories and cuisines for filters
        [AppState.categories, AppState.cuisines] = await Promise.all([
            API.Categories.getAll(),
            API.Cuisines.getAll(),
        ]);

        // Load shopping lists
        await loadShoppingLists();

        // Setup cuisine filters
        setupCuisineFilters();
    } catch (error) {
        console.error('Error loading initial data:', error);
        ExportUtils.showToast('Error loading data', 'error');
    }
}

// ========================================
// Event Listeners Setup
// ========================================

function setupEventListeners() {
    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => {
        API.Auth.logout();
    });

    // Sidebar toggle
    document.getElementById('menu-toggle').addEventListener('click', openSidebar);
    document.getElementById('sidebar-close').addEventListener('click', closeSidebar);
    document.getElementById('sidebar-overlay').addEventListener('click', closeSidebar);

    // Tab navigation
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const tabName = link.dataset.tab;
            switchTab(tabName);
            closeSidebar();
        });
    });

    // Shopping list controls
    document.getElementById('shopping-list-selector').addEventListener('change', handleShoppingListSelect);
    document.getElementById('new-shopping-list-btn').addEventListener('click', showNewListModal);
    document.getElementById('create-list-btn').addEventListener('click', createNewShoppingList);

    // Export buttons
    document.getElementById('copy-to-clipboard-btn').addEventListener('click', handleCopyToClipboard);
    document.getElementById('share-to-notes-btn').addEventListener('click', handleShareToNotes);

    // Search
    document.getElementById('search-input').addEventListener('input', handleSearchInput);

    // Filter toggle
    document.getElementById('filter-toggle').addEventListener('click', toggleFilters);

    // Filter type change
    document.querySelectorAll('input[name="filter-type"]').forEach(radio => {
        radio.addEventListener('change', handleFilterChange);
    });

    // Manage type selector
    document.getElementById('manage-type-selector').addEventListener('change', handleManageTypeChange);

    // Modal close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', closeAllModals);
    });

    // Initial manage tab setup
    handleManageTypeChange();
}

// ========================================
// Sidebar
// ========================================

function openSidebar() {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('sidebar-overlay').classList.add('active');
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebar-overlay').classList.remove('active');
}

// ========================================
// Tab Switching
// ========================================

function switchTab(tabName) {
    // Update nav links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById(`${tabName}-tab`).classList.add('active');
}

// ========================================
// Shopping List Management
// ========================================

async function loadShoppingLists() {
    try {
        const lists = await API.ShoppingLists.getAll();
        const selector = document.getElementById('shopping-list-selector');

        selector.innerHTML = '';
        lists.forEach(list => {
            const option = document.createElement('option');
            option.value = list.id;

            // Format the creation date
            const date = new Date(list.created_at);
            const formattedDate = date.toLocaleDateString('en-GB', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric'
            });

            option.textContent = `${list.name} (${formattedDate})`;
            selector.appendChild(option);
        });

        // Automatically select and load the latest shopping list (first in the list)
        if (lists.length > 0) {
            selector.value = lists[0].id;
            await handleShoppingListSelect({ target: { value: lists[0].id } });
        }
    } catch (error) {
        console.error('Error loading shopping lists:', error);
        ExportUtils.showToast('Error loading shopping lists', 'error');
    }
}

async function handleShoppingListSelect(event) {
    const listId = event.target.value;
    if (!listId) {
        document.getElementById('shopping-list-preview').innerHTML = '<p class="empty-state">No shopping list selected</p>';
        document.getElementById('export-buttons').classList.add('hidden');
        AppState.currentShoppingList = null;
        return;
    }

    try {
        const exportData = await API.ShoppingLists.export(listId);
        AppState.currentShoppingList = { id: listId, text: exportData.text };

        // Display preview
        const preview = document.getElementById('shopping-list-preview');
        preview.innerHTML = `<pre>${exportData.text}</pre>`;

        // Show export buttons
        document.getElementById('export-buttons').classList.remove('hidden');
    } catch (error) {
        console.error('Error loading shopping list:', error);
        ExportUtils.showToast('Error loading shopping list', 'error');
    }
}

function showNewListModal() {
    document.getElementById('new-list-modal').classList.remove('hidden');
    document.getElementById('new-list-name').value = 'Weekly Shopping List';
    document.getElementById('new-list-name').focus();
    document.getElementById('new-list-name').select();
}

function closeAllModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.add('hidden');
    });
}

async function createNewShoppingList() {
    const name = document.getElementById('new-list-name').value.trim();
    if (!name) {
        ExportUtils.showToast('Please enter a list name', 'error');
        return;
    }

    try {
        const newList = await API.ShoppingLists.create(name);
        await loadShoppingLists();
        document.getElementById('shopping-list-selector').value = newList.id;
        await handleShoppingListSelect({ target: { value: newList.id } });
        closeAllModals();
        ExportUtils.showToast('Shopping list created!', 'success');
    } catch (error) {
        console.error('Error creating shopping list:', error);
        ExportUtils.showToast('Error creating shopping list', 'error');
    }
}

// ========================================
// Export Functions
// ========================================

async function handleCopyToClipboard() {
    if (!AppState.currentShoppingList) return;

    const success = await ExportUtils.copyToClipboard(AppState.currentShoppingList.text);
    if (success) {
        ExportUtils.showToast('Copied to clipboard!', 'success');
    } else {
        ExportUtils.showToast('Failed to copy to clipboard', 'error');
    }
}

async function handleShareToNotes() {
    if (!AppState.currentShoppingList) return;

    const success = await ExportUtils.shareText(AppState.currentShoppingList.text);
    if (success) {
        ExportUtils.showToast('Shared successfully!', 'success');
    }
}

// ========================================
// Search Functionality
// ========================================

function handleSearchInput(event) {
    const query = event.target.value.trim();

    // Clear previous timeout
    if (AppState.searchTimeout) {
        clearTimeout(AppState.searchTimeout);
    }

    if (query.length < 2) {
        document.getElementById('search-suggestions').classList.add('hidden');
        document.getElementById('search-results').innerHTML = '<p class="empty-state">Search for items or meals to add to your shopping list</p>';
        return;
    }

    // Debounce search
    AppState.searchTimeout = setTimeout(async () => {
        await performSearch(query);
    }, 300);
}

async function performSearch(query) {
    try {
        const filterType = document.querySelector('input[name="filter-type"]:checked').value;
        const results = await API.Search.search(query, filterType);

        displaySearchResults(results);
    } catch (error) {
        console.error('Error searching:', error);
        ExportUtils.showToast('Error performing search', 'error');
    }
}

function displaySearchResults(results) {
    const container = document.getElementById('search-results');
    container.innerHTML = '';

    const allResults = [
        ...results.items.map(item => ({ ...item, type: 'item' })),
        ...results.meals.map(meal => ({ ...meal, type: 'meal' }))
    ];

    if (allResults.length === 0) {
        container.innerHTML = '<p class="empty-state">No results found</p>';
        return;
    }

    allResults.forEach(result => {
        const card = createResultCard(result);
        container.appendChild(card);
    });
}

function createResultCard(result) {
    const card = document.createElement('div');
    card.className = 'result-card';

    const meta = result.type === 'item'
        ? `Item - ${result.category_name}`
        : `Meal - ${result.cuisine_name} - ${result.servings}x servings`;

    card.innerHTML = `
        <h3>${result.name}</h3>
        <div class="meta">${meta}</div>
        <div class="quantity-controls">
            <button onclick="decrementQuantity(this)">-</button>
            <input type="number" value="1" min="1" max="99">
            <button onclick="incrementQuantity(this)">+</button>
            <button class="btn-secondary" onclick="addToCurrentList('${result.type}', ${result.id}, this)">Add to List</button>
        </div>
    `;

    return card;
}

// Quantity control functions (global scope for onclick handlers)
window.incrementQuantity = function(button) {
    const input = button.parentElement.querySelector('input[type="number"]');
    input.value = Math.min(99, parseInt(input.value) + 1);
};

window.decrementQuantity = function(button) {
    const input = button.parentElement.querySelector('input[type="number"]');
    input.value = Math.max(1, parseInt(input.value) - 1);
};

window.addToCurrentList = async function(type, id, button) {
    const listSelector = document.getElementById('shopping-list-selector');
    const listId = listSelector.value;

    if (!listId) {
        ExportUtils.showToast('Please select a shopping list first', 'error');
        return;
    }

    const quantity = parseInt(button.parentElement.querySelector('input[type="number"]').value);

    try {
        if (type === 'meal') {
            await API.ShoppingLists.addMeal(listId, id, quantity);
        } else {
            await API.ShoppingLists.addItem(listId, id, quantity, null);
        }
        ExportUtils.showToast('Added to shopping list!', 'success');

        // Refresh the shopping list if it's currently selected
        if (AppState.currentShoppingList && AppState.currentShoppingList.id == listId) {
            await handleShoppingListSelect({ target: { value: listId } });
        }
    } catch (error) {
        console.error('Error adding to list:', error);
        ExportUtils.showToast('Error adding to list', 'error');
    }
};

// ========================================
// Filter Management
// ========================================

function toggleFilters() {
    document.getElementById('filter-options').classList.toggle('hidden');
}

function setupCuisineFilters() {
    const container = document.getElementById('cuisine-filters');
    if (AppState.cuisines.length === 0) return;

    container.innerHTML = '<h4>Cuisines:</h4>';
    AppState.cuisines.forEach(cuisine => {
        const label = document.createElement('label');
        label.innerHTML = `<input type="checkbox" name="cuisine" value="${cuisine.id}"> ${cuisine.name}`;
        container.appendChild(label);
    });
}

function handleFilterChange() {
    const query = document.getElementById('search-input').value.trim();
    if (query.length >= 2) {
        performSearch(query);
    }
}

// ========================================
// Manage Tab
// ========================================

function handleManageTypeChange() {
    const type = document.getElementById('manage-type-selector').value;
    switch (type) {
        case 'item':
            showItemManagement();
            break;
        case 'meal':
            showMealManagement();
            break;
        case 'category':
            showCategoryManagement();
            break;
        case 'cuisine':
            showCuisineManagement();
            break;
    }
}

// Simplified manage functions (you can expand these as needed)
async function showCategoryManagement() {
    const formContainer = document.getElementById('manage-form-container');
    const listContainer = document.getElementById('manage-list-container');

    formContainer.innerHTML = `
        <h3>Add Category</h3>
        <input type="text" id="category-name" placeholder="Category name">
        <button class="btn-primary" onclick="createCategory()">Add Category</button>
    `;

    try {
        const categories = await API.Categories.getAll();
        listContainer.innerHTML = '<h3>Existing Categories</h3>';
        categories.forEach(category => {
            const card = document.createElement('div');
            card.className = 'manage-item-card';
            card.innerHTML = `
                <span>${category.name}</span>
                <div class="actions">
                    <button class="btn-delete" onclick="deleteCategory(${category.id})">Delete</button>
                </div>
            `;
            listContainer.appendChild(card);
        });
    } catch (error) {
        console.error('Error loading categories:', error);
    }
}

async function showCuisineManagement() {
    const formContainer = document.getElementById('manage-form-container');
    const listContainer = document.getElementById('manage-list-container');

    formContainer.innerHTML = `
        <h3>Add Cuisine</h3>
        <input type="text" id="cuisine-name" placeholder="Cuisine name">
        <button class="btn-primary" onclick="createCuisine()">Add Cuisine</button>
    `;

    try {
        const cuisines = await API.Cuisines.getAll();
        listContainer.innerHTML = '<h3>Existing Cuisines</h3>';
        cuisines.forEach(cuisine => {
            const card = document.createElement('div');
            card.className = 'manage-item-card';
            card.innerHTML = `
                <span>${cuisine.name}</span>
                <div class="actions">
                    <button class="btn-delete" onclick="deleteCuisine(${cuisine.id})">Delete</button>
                </div>
            `;
            listContainer.appendChild(card);
        });
    } catch (error) {
        console.error('Error loading cuisines:', error);
    }
}

async function showItemManagement() {
    const formContainer = document.getElementById('manage-form-container');
    formContainer.innerHTML = `
        <h3>Add Item</h3>
        <p>Item management UI coming soon. Use the API directly for now.</p>
    `;
    document.getElementById('manage-list-container').innerHTML = '';
}

async function showMealManagement() {
    const formContainer = document.getElementById('manage-form-container');
    formContainer.innerHTML = `
        <h3>Add Meal</h3>
        <p>Meal management UI coming soon. Use the API directly for now.</p>
    `;
    document.getElementById('manage-list-container').innerHTML = '';
}

// Global functions for manage actions
window.createCategory = async function() {
    const name = document.getElementById('category-name').value.trim();
    if (!name) {
        ExportUtils.showToast('Please enter a category name', 'error');
        return;
    }

    try {
        await API.Categories.create(name);
        ExportUtils.showToast('Category created!', 'success');
        await showCategoryManagement();
    } catch (error) {
        ExportUtils.showToast(error.message, 'error');
    }
};

window.deleteCategory = async function(id) {
    if (!confirm('Are you sure you want to delete this category?')) return;

    try {
        await API.Categories.delete(id);
        ExportUtils.showToast('Category deleted!', 'success');
        await showCategoryManagement();
    } catch (error) {
        ExportUtils.showToast(error.message, 'error');
    }
};

window.createCuisine = async function() {
    const name = document.getElementById('cuisine-name').value.trim();
    if (!name) {
        ExportUtils.showToast('Please enter a cuisine name', 'error');
        return;
    }

    try {
        await API.Cuisines.create(name);
        ExportUtils.showToast('Cuisine created!', 'success');
        await showCuisineManagement();
    } catch (error) {
        ExportUtils.showToast(error.message, 'error');
    }
};

window.deleteCuisine = async function(id) {
    if (!confirm('Are you sure you want to delete this cuisine?')) return;

    try {
        await API.Cuisines.delete(id);
        ExportUtils.showToast('Cuisine deleted!', 'success');
        await showCuisineManagement();
    } catch (error) {
        ExportUtils.showToast(error.message, 'error');
    }
};
