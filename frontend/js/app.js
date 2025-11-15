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

// State for Items Management
let editingItemId = null;
let allItems = [];
let itemCategories = [];

async function showItemManagement() {
    try {
        // Load categories and items
        [itemCategories, allItems] = await Promise.all([
            API.Categories.getAll(),
            API.Items.getAll()
        ]);

        renderItemForm();
        renderItemList(allItems);
    } catch (error) {
        console.error('Error loading item management:', error);
        ExportUtils.showToast('Error loading items', 'error');
    }
}

function renderItemForm(editingItem = null) {
    const formContainer = document.getElementById('manage-form-container');
    const isEditing = editingItem !== null;

    // Build category options
    const categoryOptions = itemCategories.map(cat =>
        `<option value="${cat.id}" ${isEditing && editingItem.category_id === cat.id ? 'selected' : ''}>${cat.name}</option>`
    ).join('');

    formContainer.innerHTML = `
        <h3>${isEditing ? 'Edit' : 'Add'} Item</h3>

        <!-- Search placeholder for future implementation -->
        <div id="item-search-container" class="search-placeholder hidden">
            <!-- Future: Search input will go here -->
        </div>

        <div class="form-row">
            <label for="item-name">Name *</label>
            <input type="text" id="item-name" placeholder="Item name" value="${isEditing ? editingItem.name : ''}" required>
        </div>

        <div class="form-row">
            <label for="item-category">Category *</label>
            <select id="item-category" required>
                <option value="">Select category...</option>
                ${categoryOptions}
            </select>
        </div>

        <div class="form-row">
            <label for="item-calories">Calories per 100g/ml</label>
            <input type="number" id="item-calories" placeholder="Optional" step="0.1" min="0"
                   value="${isEditing && editingItem.calories_per_100 ? editingItem.calories_per_100 : ''}">
        </div>

        <div class="form-row">
            <label for="item-protein">Protein per 100g/ml</label>
            <input type="number" id="item-protein" placeholder="Optional" step="0.1" min="0"
                   value="${isEditing && editingItem.protein_per_100 ? editingItem.protein_per_100 : ''}">
        </div>

        <div class="form-row">
            <label for="item-sugar">Sugar per 100g/ml</label>
            <input type="number" id="item-sugar" placeholder="Optional" step="0.1" min="0"
                   value="${isEditing && editingItem.sugar_per_100 ? editingItem.sugar_per_100 : ''}">
        </div>

        <div class="form-actions">
            <button class="btn-primary" onclick="${isEditing ? `updateItem(${editingItem.id})` : 'createItem()'}">${isEditing ? 'Update' : 'Add'} Item</button>
            ${isEditing ? '<button class="btn-secondary" onclick="cancelEditItem()">Cancel</button>' : ''}
        </div>
    `;
}

function renderItemList(items) {
    const listContainer = document.getElementById('manage-list-container');

    if (items.length === 0) {
        listContainer.innerHTML = '<h3>Existing Items</h3><p class="empty-state">No items yet. Add your first item above.</p>';
        return;
    }

    listContainer.innerHTML = '<h3>Existing Items</h3>';

    items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'manage-item-card';

        // Build nutritional info display
        const nutritionalInfo = [];
        if (item.calories_per_100) nutritionalInfo.push(`${item.calories_per_100}kcal`);
        if (item.protein_per_100) nutritionalInfo.push(`${item.protein_per_100}g protein`);
        if (item.sugar_per_100) nutritionalInfo.push(`${item.sugar_per_100}g sugar`);
        const nutritionalDisplay = nutritionalInfo.length > 0
            ? `<div class="nutritional-info">${nutritionalInfo.join(' | ')} per 100g/ml</div>`
            : '';

        card.innerHTML = `
            <div class="item-info">
                <strong>${item.name}</strong>
                <div class="item-category">${item.category.name}</div>
                ${nutritionalDisplay}
            </div>
            <div class="actions">
                <button class="btn-edit" onclick="editItem(${item.id})">Edit</button>
                <button class="btn-delete" onclick="deleteItem(${item.id})">Delete</button>
            </div>
        `;
        listContainer.appendChild(card);
    });
}

async function loadAndRenderItems() {
    try {
        allItems = await API.Items.getAll();
        renderItemList(allItems);
    } catch (error) {
        console.error('Error loading items:', error);
        ExportUtils.showToast('Error loading items', 'error');
    }
}

// Global CRUD functions for Items
window.createItem = async function() {
    const name = document.getElementById('item-name').value.trim();
    const categoryId = document.getElementById('item-category').value;
    const calories = document.getElementById('item-calories').value;
    const protein = document.getElementById('item-protein').value;
    const sugar = document.getElementById('item-sugar').value;

    // Validation
    if (!name) {
        ExportUtils.showToast('Please enter an item name', 'error');
        return;
    }
    if (!categoryId) {
        ExportUtils.showToast('Please select a category', 'error');
        return;
    }

    // Check for duplicate name (case-insensitive)
    const duplicateItem = allItems.find(item =>
        item.name.toLowerCase() === name.toLowerCase()
    );
    if (duplicateItem) {
        ExportUtils.showToast(`An item named "${duplicateItem.name}" already exists`, 'error');
        return;
    }

    // Build item data
    const itemData = {
        name: name,
        category_id: parseInt(categoryId),
        calories_per_100: calories ? parseFloat(calories) : null,
        protein_per_100: protein ? parseFloat(protein) : null,
        sugar_per_100: sugar ? parseFloat(sugar) : null
    };

    try {
        console.log('Creating item with data:', itemData);
        await API.Items.create(itemData);

        // Reset state
        editingItemId = null;

        // Reload the item list
        await loadAndRenderItems();

        // Reset form with fresh empty state
        renderItemForm();

        // Show success message
        ExportUtils.showToast(`Item "${name}" created successfully!`, 'success', 4000);

        // Scroll to top of form
        document.getElementById('manage-form-container').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
        console.error('Error creating item:', error);
        console.error('Item data that failed:', itemData);

        // Provide more specific error messages
        let errorMessage = 'Failed to create item';
        if (error.message) {
            errorMessage = error.message;
        }

        ExportUtils.showToast(errorMessage, 'error');
    }
};

window.editItem = async function(id) {
    try {
        const item = await API.Items.getById(id);
        editingItemId = id;
        renderItemForm(item);
        // Scroll to top of form
        document.getElementById('manage-form-container').scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error loading item:', error);
        ExportUtils.showToast('Error loading item', 'error');
    }
};

window.updateItem = async function(id) {
    const name = document.getElementById('item-name').value.trim();
    const categoryId = document.getElementById('item-category').value;
    const calories = document.getElementById('item-calories').value;
    const protein = document.getElementById('item-protein').value;
    const sugar = document.getElementById('item-sugar').value;

    // Validation
    if (!name) {
        ExportUtils.showToast('Please enter an item name', 'error');
        return;
    }
    if (!categoryId) {
        ExportUtils.showToast('Please select a category', 'error');
        return;
    }

    // Check for duplicate name (case-insensitive, excluding current item)
    const duplicateItem = allItems.find(item =>
        item.id !== id && item.name.toLowerCase() === name.toLowerCase()
    );
    if (duplicateItem) {
        ExportUtils.showToast(`An item named "${duplicateItem.name}" already exists`, 'error');
        return;
    }

    // Build item data
    const itemData = {
        name: name,
        category_id: parseInt(categoryId),
        calories_per_100: calories ? parseFloat(calories) : null,
        protein_per_100: protein ? parseFloat(protein) : null,
        sugar_per_100: sugar ? parseFloat(sugar) : null
    };

    try {
        console.log('Updating item with data:', itemData);
        await API.Items.update(id, itemData);

        // Reset state
        editingItemId = null;

        // Reload the item list
        await loadAndRenderItems();

        // Reset form with fresh empty state
        renderItemForm();

        // Show success message
        ExportUtils.showToast(`Item "${name}" updated successfully!`, 'success', 4000);

        // Scroll to top of form
        document.getElementById('manage-form-container').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
        console.error('Error updating item:', error);
        console.error('Item data that failed:', itemData);

        // Provide more specific error messages
        let errorMessage = 'Failed to update item';
        if (error.message) {
            errorMessage = error.message;
        }

        ExportUtils.showToast(errorMessage, 'error');
    }
};

window.deleteItem = async function(id) {
    if (!confirm('Are you sure you want to delete this item? This will fail if the item is used in any meals.')) return;

    try {
        await API.Items.delete(id);
        ExportUtils.showToast('Item deleted!', 'success');
        await loadAndRenderItems();
    } catch (error) {
        console.error('Error deleting item:', error);
        ExportUtils.showToast(error.message || 'Cannot delete item. It may be used in meals.', 'error');
    }
};

window.cancelEditItem = function() {
    editingItemId = null;
    renderItemForm();
};

// State for Meals Management
let editingMealId = null;
let allMeals = [];
let mealCuisines = [];
let availableItems = [];
let ingredientRowCounter = 0;

async function showMealManagement() {
    try {
        // Load cuisines, items, and meals
        [mealCuisines, availableItems, allMeals] = await Promise.all([
            API.Cuisines.getAll(),
            API.Items.getAll(),
            API.Meals.getAll()
        ]);

        // Warn if no items exist (can't create meals without items)
        if (availableItems.length === 0) {
            ExportUtils.showToast('Please create items first before adding meals', 'error');
        }

        renderMealForm();
        renderMealList(allMeals);
    } catch (error) {
        console.error('Error loading meal management:', error);
        ExportUtils.showToast('Error loading meals', 'error');
    }
}

function renderMealForm(editingMeal = null) {
    const formContainer = document.getElementById('manage-form-container');
    const isEditing = editingMeal !== null;

    // Build cuisine options
    const cuisineOptions = mealCuisines.map(cuisine =>
        `<option value="${cuisine.id}" ${isEditing && editingMeal.cuisine_id === cuisine.id ? 'selected' : ''}>${cuisine.name}</option>`
    ).join('');

    formContainer.innerHTML = `
        <h3>${isEditing ? 'Edit' : 'Add'} Meal</h3>

        <!-- Search placeholder for future implementation -->
        <div id="meal-search-container" class="search-placeholder hidden">
            <!-- Future: Search input will go here -->
        </div>

        <div class="form-row">
            <label for="meal-name">Name *</label>
            <input type="text" id="meal-name" placeholder="Meal name" value="${isEditing ? editingMeal.name : ''}" required>
        </div>

        <div class="form-row">
            <label for="meal-cuisine">Cuisine *</label>
            <select id="meal-cuisine" required>
                <option value="">Select cuisine...</option>
                ${cuisineOptions}
            </select>
        </div>

        <div class="form-row">
            <label for="meal-servings">Servings *</label>
            <input type="number" id="meal-servings" placeholder="How many servings" min="1" step="1"
                   value="${isEditing ? editingMeal.servings : '1'}" required>
        </div>

        <div class="form-row">
            <label for="meal-recipe">Recipe (optional)</label>
            <textarea id="meal-recipe" placeholder="Step-by-step instructions..." rows="6">${isEditing && editingMeal.recipe ? editingMeal.recipe : ''}</textarea>
        </div>

        <div class="form-row">
            <label for="meal-image-url">Image URL (optional)</label>
            <input type="text" id="meal-image-url" placeholder="https://..." value="${isEditing && editingMeal.image_url ? editingMeal.image_url : ''}">
        </div>

        <div class="ingredients-section">
            <h4>Ingredients *</h4>
            <div id="ingredients-container"></div>
            <button type="button" class="btn-add-ingredient" onclick="addIngredientRow()">+ Add Ingredient</button>
        </div>

        <div class="form-actions">
            <button class="btn-primary" onclick="${isEditing ? `updateMeal(${editingMeal.id})` : 'createMeal()'}">${isEditing ? 'Update' : 'Add'} Meal</button>
            ${isEditing ? '<button class="btn-secondary" onclick="cancelEditMeal()">Cancel</button>' : ''}
        </div>
    `;

    // Render ingredient rows
    if (isEditing && editingMeal.ingredients && editingMeal.ingredients.length > 0) {
        editingMeal.ingredients.forEach(ingredient => {
            addIngredientRow(ingredient);
        });
    } else {
        // Start with one empty ingredient row
        addIngredientRow();
    }
}

function renderMealList(meals) {
    const listContainer = document.getElementById('manage-list-container');

    if (meals.length === 0) {
        listContainer.innerHTML = '<h3>Existing Meals</h3><p class="empty-state">No meals yet. Add your first meal above.</p>';
        return;
    }

    listContainer.innerHTML = '<h3>Existing Meals</h3>';

    meals.forEach(meal => {
        const card = document.createElement('div');
        card.className = 'manage-item-card';

        card.innerHTML = `
            <div class="item-info">
                <strong>${meal.name}</strong>
                <div class="meal-meta">
                    <span class="cuisine">${meal.cuisine.name}</span> |
                    <span class="servings">${meal.servings}x serving${meal.servings > 1 ? 's' : ''}</span>
                </div>
            </div>
            <div class="actions">
                <button class="btn-edit" onclick="editMeal(${meal.id})">Edit</button>
                <button class="btn-delete" onclick="deleteMeal(${meal.id})">Delete</button>
            </div>
        `;
        listContainer.appendChild(card);
    });
}

async function loadAndRenderMeals() {
    try {
        allMeals = await API.Meals.getAll();
        renderMealList(allMeals);
    } catch (error) {
        console.error('Error loading meals:', error);
        ExportUtils.showToast('Error loading meals', 'error');
    }
}

// Ingredient Row Management
window.addIngredientRow = function(ingredient = null) {
    const container = document.getElementById('ingredients-container');
    if (!container) return;

    const rowId = `ingredient-row-${ingredientRowCounter++}`;
    const row = document.createElement('div');
    row.className = 'ingredient-row';
    row.id = rowId;

    // Build item options
    const itemOptions = availableItems.map(item =>
        `<option value="${item.id}" ${ingredient && ingredient.item_id === item.id ? 'selected' : ''}>${item.name}</option>`
    ).join('');

    row.innerHTML = `
        <div class="ingredient-inputs">
            <select class="ingredient-item" required>
                <option value="">Select item...</option>
                ${itemOptions}
            </select>
            <input type="number" class="ingredient-quantity" placeholder="Qty" min="0.1" step="0.1"
                   value="${ingredient ? ingredient.quantity : ''}" required>
            <input type="text" class="ingredient-unit" placeholder="g, ml, x, cup..."
                   value="${ingredient && ingredient.unit ? ingredient.unit : ''}">
            <button type="button" class="btn-remove-ingredient" onclick="removeIngredientRow('${rowId}')">×</button>
        </div>
    `;

    container.appendChild(row);
    updateIngredientRemoveButtons();
};

window.removeIngredientRow = function(rowId) {
    const row = document.getElementById(rowId);
    if (row) {
        row.remove();
        updateIngredientRemoveButtons();
    }
};

function updateIngredientRemoveButtons() {
    const container = document.getElementById('ingredients-container');
    if (!container) return;

    const rows = container.querySelectorAll('.ingredient-row');
    // Hide remove button if only one row
    rows.forEach((row, index) => {
        const removeBtn = row.querySelector('.btn-remove-ingredient');
        if (removeBtn) {
            removeBtn.style.display = rows.length > 1 ? 'inline-block' : 'none';
        }
    });
}

function collectIngredientsFromForm() {
    const container = document.getElementById('ingredients-container');
    if (!container) return [];

    const rows = container.querySelectorAll('.ingredient-row');
    const ingredients = [];

    rows.forEach(row => {
        const itemId = row.querySelector('.ingredient-item').value;
        const quantity = row.querySelector('.ingredient-quantity').value;
        const unit = row.querySelector('.ingredient-unit').value.trim();

        if (itemId && quantity) {
            ingredients.push({
                item_id: parseInt(itemId),
                quantity: parseFloat(quantity),
                unit: unit || null
            });
        }
    });

    return ingredients;
}

// Global CRUD functions for Meals
window.createMeal = async function() {
    const name = document.getElementById('meal-name').value.trim();
    const cuisineId = document.getElementById('meal-cuisine').value;
    const servings = document.getElementById('meal-servings').value;
    const recipe = document.getElementById('meal-recipe').value.trim();
    const imageUrl = document.getElementById('meal-image-url').value.trim();
    const ingredients = collectIngredientsFromForm();

    // Validation
    if (!name) {
        ExportUtils.showToast('Please enter a meal name', 'error');
        return;
    }
    if (!cuisineId) {
        ExportUtils.showToast('Please select a cuisine', 'error');
        return;
    }
    if (!servings || servings < 1) {
        ExportUtils.showToast('Please enter valid servings (min 1)', 'error');
        return;
    }
    if (ingredients.length === 0) {
        if (availableItems.length === 0) {
            ExportUtils.showToast('Please create items first before adding meals', 'error');
        } else {
            ExportUtils.showToast('Please add at least one ingredient with item and quantity', 'error');
        }
        return;
    }

    // Check for duplicate name (case-insensitive)
    const duplicateMeal = allMeals.find(meal =>
        meal.name.toLowerCase() === name.toLowerCase()
    );
    if (duplicateMeal) {
        ExportUtils.showToast(`A meal named "${duplicateMeal.name}" already exists`, 'error');
        return;
    }

    // Build meal data
    const mealData = {
        name: name,
        cuisine_id: parseInt(cuisineId),
        servings: parseInt(servings),
        recipe: recipe || null,
        image_url: imageUrl || null,
        ingredients: ingredients
    };

    try {
        console.log('Creating meal with data:', mealData);
        await API.Meals.create(mealData);

        // Reset state and form
        editingMealId = null;
        ingredientRowCounter = 0;

        // Reload the meal list
        await loadAndRenderMeals();

        // Reset form with fresh empty state
        renderMealForm();

        // Show success message
        ExportUtils.showToast(`Meal "${name}" created successfully!`, 'success', 4000);

        // Scroll to top of form
        document.getElementById('manage-form-container').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
        console.error('Error creating meal:', error);
        console.error('Meal data that failed:', mealData);

        // Provide more specific error messages
        let errorMessage = 'Failed to create meal';
        if (error.message) {
            errorMessage = error.message;
        }

        ExportUtils.showToast(errorMessage, 'error');
    }
};

window.editMeal = async function(id) {
    try {
        const meal = await API.Meals.getById(id);
        editingMealId = id;
        ingredientRowCounter = 0;
        renderMealForm(meal);
        // Scroll to top of form
        document.getElementById('manage-form-container').scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error loading meal:', error);
        ExportUtils.showToast('Error loading meal', 'error');
    }
};

window.updateMeal = async function(id) {
    const name = document.getElementById('meal-name').value.trim();
    const cuisineId = document.getElementById('meal-cuisine').value;
    const servings = document.getElementById('meal-servings').value;
    const recipe = document.getElementById('meal-recipe').value.trim();
    const imageUrl = document.getElementById('meal-image-url').value.trim();
    const ingredients = collectIngredientsFromForm();

    // Validation
    if (!name) {
        ExportUtils.showToast('Please enter a meal name', 'error');
        return;
    }
    if (!cuisineId) {
        ExportUtils.showToast('Please select a cuisine', 'error');
        return;
    }
    if (!servings || servings < 1) {
        ExportUtils.showToast('Please enter valid servings (min 1)', 'error');
        return;
    }
    if (ingredients.length === 0) {
        if (availableItems.length === 0) {
            ExportUtils.showToast('Please create items first before adding meals', 'error');
        } else {
            ExportUtils.showToast('Please add at least one ingredient with item and quantity', 'error');
        }
        return;
    }

    // Check for duplicate name (case-insensitive, excluding current meal)
    const duplicateMeal = allMeals.find(meal =>
        meal.id !== id && meal.name.toLowerCase() === name.toLowerCase()
    );
    if (duplicateMeal) {
        ExportUtils.showToast(`A meal named "${duplicateMeal.name}" already exists`, 'error');
        return;
    }

    // Build meal data
    const mealData = {
        name: name,
        cuisine_id: parseInt(cuisineId),
        servings: parseInt(servings),
        recipe: recipe || null,
        image_url: imageUrl || null,
        ingredients: ingredients
    };

    try {
        console.log('Updating meal with data:', mealData);
        await API.Meals.update(id, mealData);

        // Reset state
        editingMealId = null;
        ingredientRowCounter = 0;

        // Reload the meal list
        await loadAndRenderMeals();

        // Reset form with fresh empty state
        renderMealForm();

        // Show success message
        ExportUtils.showToast(`Meal "${name}" updated successfully!`, 'success', 4000);

        // Scroll to top of form
        document.getElementById('manage-form-container').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
        console.error('Error updating meal:', error);
        console.error('Meal data that failed:', mealData);

        // Provide more specific error messages
        let errorMessage = 'Failed to update meal';
        if (error.message) {
            errorMessage = error.message;
        }

        ExportUtils.showToast(errorMessage, 'error');
    }
};

window.deleteMeal = async function(id) {
    if (!confirm('Are you sure you want to delete this meal?')) return;

    try {
        await API.Meals.delete(id);
        ExportUtils.showToast('Meal deleted!', 'success');
        await loadAndRenderMeals();
    } catch (error) {
        console.error('Error deleting meal:', error);
        ExportUtils.showToast(error.message, 'error');
    }
};

window.cancelEditMeal = function() {
    editingMealId = null;
    ingredientRowCounter = 0;
    renderMealForm();
};

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
