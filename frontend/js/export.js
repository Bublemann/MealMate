/**
 * Export Utilities for MealMate
 * Handles clipboard and share API functionality
 */

/**
 * Copy text to clipboard
 * @param {string} text - The text to copy
 * @returns {Promise<boolean>} - True if successful, false otherwise
 */
async function copyToClipboard(text) {
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            // Modern clipboard API
            await navigator.clipboard.writeText(text);
            return true;
        } else {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            const successful = document.execCommand('copy');
            document.body.removeChild(textArea);

            return successful;
        }
    } catch (error) {
        console.error('Failed to copy to clipboard:', error);
        return false;
    }
}

/**
 * Share text using Web Share API (for mobile devices, especially iOS)
 * @param {string} text - The text to share
 * @param {string} title - The title for the share dialog
 * @returns {Promise<boolean>} - True if successful or share dialog was shown, false otherwise
 */
async function shareText(text, title = 'MealMate Shopping List') {
    try {
        if (navigator.share) {
            // Web Share API is available
            await navigator.share({
                title: title,
                text: text,
            });
            return true;
        } else {
            // Web Share API not available, fall back to clipboard
            console.warn('Web Share API not available, falling back to clipboard');
            const success = await copyToClipboard(text);
            if (success) {
                showToast('Copied to clipboard! You can paste it into Notes app', 'success');
            }
            return success;
        }
    } catch (error) {
        // User cancelled the share dialog or other error
        if (error.name === 'AbortError') {
            // User cancelled - this is not really an error
            return false;
        }
        console.error('Failed to share:', error);
        return false;
    }
}

/**
 * Check if Web Share API is available
 * @returns {boolean}
 */
function isShareAvailable() {
    return navigator.share !== undefined;
}

/**
 * Check if Clipboard API is available
 * @returns {boolean}
 */
function isClipboardAvailable() {
    return navigator.clipboard !== undefined || document.execCommand !== undefined;
}

/**
 * Format shopping list data for export
 * @param {Object} listData - Shopping list data from API
 * @returns {string} - Formatted text
 */
function formatShoppingListText(listData) {
    // This function is here for reference, but the backend already
    // returns formatted text from the export endpoint
    // You could use this if you want to do client-side formatting
    return listData;
}

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - The type of toast ('success', 'error', or default)
 * @param {number} duration - How long to show the toast (ms)
 */
function showToast(message, type = '', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            container.removeChild(toast);
        }, 300);
    }, duration);
}

// Export functions to global scope
window.ExportUtils = {
    copyToClipboard,
    shareText,
    isShareAvailable,
    isClipboardAvailable,
    formatShoppingListText,
    showToast,
};
