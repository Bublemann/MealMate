/**
 * API Communication Layer for MealMate
 * Handles all HTTP requests to the backend API
 */

// Configuration
// Automatically use the same protocol (http/https) as the current page
const API_BASE_URL = (() => {
    const protocol = window.location.protocol; // 'http:' or 'https:'
    const hostname = window.location.hostname;

    // If we're on HTTPS (port 8443), use HTTPS for API
    // Otherwise use HTTP (port 8000)
    if (protocol === 'https:') {
        return `https://${hostname}:8443/api`;
    } else {
        return `http://${hostname}:8000/api`;
    }
})();

// Storage keys
const TOKEN_KEY = 'mealmate_token';
const USER_KEY = 'mealmate_user';

/**
 * Get stored authentication token
 */
function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

/**
 * Store authentication token
 */
function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Remove authentication token
 */
function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
}

/**
 * Get stored user info
 */
function getUser() {
    const userJson = localStorage.getItem(USER_KEY);
    return userJson ? JSON.parse(userJson) : null;
}

/**
 * Store user info
 */
function setUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/**
 * Make an authenticated API request
 */
async function apiRequest(endpoint, options = {}) {
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        ...options,
        headers,
    };

    const response = await fetch(`${API_BASE_URL}${endpoint}`, config);

    if (response.status === 401) {
        // Unauthorized - clear token and redirect to login
        clearToken();
        window.location.reload();
        throw new Error('Session expired. Please log in again.');
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    // Handle 204 No Content
    if (response.status === 204) {
        return null;
    }

    return response.json();
}

// ========================================
// Authentication API
// ========================================

const AuthAPI = {
    async register(username, password) {
        const data = await apiRequest('/users/register', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
        setToken(data.access_token);
        setUser({ id: data.user_id, username: data.username });
        return data;
    },

    async login(username, password) {
        const data = await apiRequest('/users/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
        setToken(data.access_token);
        setUser({ id: data.user_id, username: data.username });
        return data;
    },

    logout() {
        clearToken();
        window.location.reload();
    },

    async getCurrentUser() {
        return apiRequest('/users/me');
    },
};

// ========================================
// Categories API
// ========================================

const CategoriesAPI = {
    async getAll() {
        return apiRequest('/categories');
    },

    async getById(id) {
        return apiRequest(`/categories/${id}`);
    },

    async create(name) {
        return apiRequest('/categories', {
            method: 'POST',
            body: JSON.stringify({ name }),
        });
    },

    async update(id, name) {
        return apiRequest(`/categories/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ name }),
        });
    },

    async delete(id) {
        return apiRequest(`/categories/${id}`, {
            method: 'DELETE',
        });
    },
};

// ========================================
// Cuisines API
// ========================================

const CuisinesAPI = {
    async getAll() {
        return apiRequest('/cuisines');
    },

    async getById(id) {
        return apiRequest(`/cuisines/${id}`);
    },

    async create(name) {
        return apiRequest('/cuisines', {
            method: 'POST',
            body: JSON.stringify({ name }),
        });
    },

    async update(id, name) {
        return apiRequest(`/cuisines/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ name }),
        });
    },

    async delete(id) {
        return apiRequest(`/cuisines/${id}`, {
            method: 'DELETE',
        });
    },
};

// ========================================
// Items API
// ========================================

const ItemsAPI = {
    async getAll(filters = {}) {
        const params = new URLSearchParams();
        if (filters.category_id) params.append('category_id', filters.category_id);
        if (filters.search) params.append('search', filters.search);

        const queryString = params.toString();
        return apiRequest(`/items${queryString ? '?' + queryString : ''}`);
    },

    async getById(id) {
        return apiRequest(`/items/${id}`);
    },

    async create(itemData) {
        return apiRequest('/items', {
            method: 'POST',
            body: JSON.stringify(itemData),
        });
    },

    async update(id, itemData) {
        return apiRequest(`/items/${id}`, {
            method: 'PUT',
            body: JSON.stringify(itemData),
        });
    },

    async delete(id) {
        return apiRequest(`/items/${id}`, {
            method: 'DELETE',
        });
    },
};

// ========================================
// Meals API
// ========================================

const MealsAPI = {
    async getAll(filters = {}) {
        const params = new URLSearchParams();
        if (filters.cuisine_id) params.append('cuisine_id', filters.cuisine_id);
        if (filters.search) params.append('search', filters.search);

        const queryString = params.toString();
        return apiRequest(`/meals${queryString ? '?' + queryString : ''}`);
    },

    async getById(id) {
        return apiRequest(`/meals/${id}`);
    },

    async create(mealData) {
        return apiRequest('/meals', {
            method: 'POST',
            body: JSON.stringify(mealData),
        });
    },

    async update(id, mealData) {
        return apiRequest(`/meals/${id}`, {
            method: 'PUT',
            body: JSON.stringify(mealData),
        });
    },

    async delete(id) {
        return apiRequest(`/meals/${id}`, {
            method: 'DELETE',
        });
    },
};

// ========================================
// Shopping Lists API
// ========================================

const ShoppingListsAPI = {
    async getAll() {
        return apiRequest('/shopping-lists');
    },

    async getById(id) {
        return apiRequest(`/shopping-lists/${id}`);
    },

    async create(name) {
        return apiRequest('/shopping-lists', {
            method: 'POST',
            body: JSON.stringify({ name }),
        });
    },

    async update(id, name) {
        return apiRequest(`/shopping-lists/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ name }),
        });
    },

    async delete(id) {
        return apiRequest(`/shopping-lists/${id}`, {
            method: 'DELETE',
        });
    },

    async addMeal(listId, mealId, quantity) {
        return apiRequest(`/shopping-lists/${listId}/add-meal`, {
            method: 'POST',
            body: JSON.stringify({ meal_id: mealId, quantity }),
        });
    },

    async addItem(listId, itemId, quantity, unit) {
        return apiRequest(`/shopping-lists/${listId}/add-item`, {
            method: 'POST',
            body: JSON.stringify({ item_id: itemId, quantity, unit }),
        });
    },

    async addCustom(listId, customText) {
        return apiRequest(`/shopping-lists/${listId}/add-custom`, {
            method: 'POST',
            body: JSON.stringify({ custom_text: customText }),
        });
    },

    async export(listId) {
        return apiRequest(`/shopping-lists/${listId}/export`);
    },
};

// ========================================
// Search API
// ========================================

const SearchAPI = {
    async search(query, type = 'all', limit = 10) {
        const params = new URLSearchParams({ q: query, type, limit });
        return apiRequest(`/search?${params.toString()}`);
    },

    async getSuggestions(query, limit = 5) {
        const params = new URLSearchParams({ q: query, limit });
        return apiRequest(`/search/suggestions?${params.toString()}`);
    },
};

// Export all APIs
window.API = {
    Auth: AuthAPI,
    Categories: CategoriesAPI,
    Cuisines: CuisinesAPI,
    Items: ItemsAPI,
    Meals: MealsAPI,
    ShoppingLists: ShoppingListsAPI,
    Search: SearchAPI,
    getToken,
    getUser,
};
