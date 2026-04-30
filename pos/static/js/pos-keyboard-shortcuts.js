/**
 * POS Keyboard Shortcuts System
 * Optimizes desktop POS experience with keyboard navigation
 */

class POSKeyboardShortcuts {
    constructor() {
        this.shortcuts = {
            // Navigation
            'F1': { action: () => this.focusBarcode(), description: 'Focus barcode input' },
            'F2': { action: () => this.focusSearch(), description: 'Focus product search' },
            'F3': { action: () => this.focusCustomer(), description: 'Focus customer search' },
            
            // Cart Operations
            'F5': { action: () => this.clearCart(), description: 'Clear cart' },
            'F6': { action: () => this.holdOrder(), description: 'Hold order' },
            'F7': { action: () => this.applyDiscount(), description: 'Apply discount' },
            'F8': { action: () => this.completePayment(), description: 'Complete payment' },
            
            // Quick Actions
            'F9': { action: () => this.openCalculator(), description: 'Open calculator' },
            'F10': { action: () => this.printLastReceipt(), description: 'Reprint last receipt' },
            'F11': { action: () => this.openCashDrawer(), description: 'Open cash drawer' },
            'F12': { action: () => this.showShortcuts(), description: 'Show shortcuts' },
            
            // Modifiers
            'ctrl+d': { action: () => this.removeLastItem(), description: 'Remove last cart item' },
            'ctrl+h': { action: () => this.showHeldOrders(), description: 'Show held orders' },
            'ctrl+n': { action: () => this.newSale(), description: 'New sale' },
            'ctrl+p': { action: () => this.printReceipt(), description: 'Print receipt' },
            'ctrl+s': { action: () => this.quickSave(), description: 'Quick save (hold)' },
            
            // Number pad quick add (Alt + 1-9)
            'alt+1': { action: () => this.quickAddProduct(1), description: 'Quick add product 1' },
            'alt+2': { action: () => this.quickAddProduct(2), description: 'Quick add product 2' },
            'alt+3': { action: () => this.quickAddProduct(3), description: 'Quick add product 3' },
            'alt+4': { action: () => this.quickAddProduct(4), description: 'Quick add product 4' },
            'alt+5': { action: () => this.quickAddProduct(5), description: 'Quick add product 5' },
            'alt+6': { action: () => this.quickAddProduct(6), description: 'Quick add product 6' },
            'alt+7': { action: () => this.quickAddProduct(7), description: 'Quick add product 7' },
            'alt+8': { action: () => this.quickAddProduct(8), description: 'Quick add product 8' },
            'alt+9': { action: () => this.quickAddProduct(9), description: 'Quick add product 9' },
            
            // ESC to cancel/close
            'escape': { action: () => this.handleEscape(), description: 'Cancel/Close' }
        };
        
        this.init();
    }
    
    init() {
        document.addEventListener('keydown', (e) => this.handleKeyPress(e));
        this.createShortcutsPanel();
        this.setupAutoFocus();
    }
    
    handleKeyPress(e) {
        // Don't trigger if user is typing in an input/textarea
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            // Allow ESC to blur inputs
            if (e.key === 'Escape') {
                e.target.blur();
                return;
            }
            // Allow shortcuts in barcode input only
            if (e.target.id !== 'barcode-input') {
                return;
            }
        }
        
        const key = this.getKeyCombo(e);
        const shortcut = this.shortcuts[key];
        
        if (shortcut) {
            e.preventDefault();
            shortcut.action();
        }
    }
    
    getKeyCombo(e) {
        const parts = [];
        if (e.ctrlKey) parts.push('ctrl');
        if (e.altKey) parts.push('alt');
        if (e.shiftKey) parts.push('shift');
        parts.push(e.key.toLowerCase());
        return parts.join('+');
    }
    
    // Action Methods
    focusBarcode() {
        const input = document.getElementById('barcode-input');
        if (input) {
            input.focus();
            input.select();
        }
    }
    
    focusSearch() {
        const input = document.getElementById('search-input');
        if (input) {
            input.focus();
            input.select();
        }
    }
    
    focusCustomer() {
        const input = document.getElementById('customer-phone-input');
        if (input) {
            input.focus();
            input.select();
        }
    }
    
    clearCart() {
        if (confirm('Clear entire cart?')) {
            if (typeof clearCart === 'function') {
                clearCart();
            }
        }
    }
    
    holdOrder() {
        const btn = document.querySelector('[onclick*="holdOrder"]');
        if (btn) btn.click();
    }
    
    applyDiscount() {
        const btn = document.querySelector('[onclick*="applyDiscount"]');
        if (btn) btn.click();
    }
    
    completePayment() {
        const btn = document.getElementById('complete-sale-btn');
        if (btn && !btn.disabled) {
            btn.click();
        }
    }
    
    openCalculator() {
        // Open system calculator or show on-screen calculator
        alert('Calculator: Use your system calculator (Windows: Calc, Mac: Calculator)');
    }
    
    printLastReceipt() {
        alert('Reprint last receipt feature - implement based on your receipt system');
    }
    
    openCashDrawer() {
        alert('Cash drawer open command - requires hardware integration');
    }
    
    showShortcuts() {
        const panel = document.getElementById('shortcuts-panel');
        if (panel) {
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        }
    }
    
    removeLastItem() {
        const cartItems = document.querySelectorAll('.cart-item');
        if (cartItems.length > 0) {
            const lastItem = cartItems[cartItems.length - 1];
            const removeBtn = lastItem.querySelector('[onclick*="removeFromCart"]');
            if (removeBtn) removeBtn.click();
        }
    }
    
    showHeldOrders() {
        const btn = document.querySelector('[onclick*="showHeldOrders"]');
        if (btn) btn.click();
    }
    
    newSale() {
        if (confirm('Start new sale? Current cart will be cleared.')) {
            window.location.reload();
        }
    }
    
    printReceipt() {
        window.print();
    }
    
    quickSave() {
        this.holdOrder();
    }
    
    quickAddProduct(index) {
        const products = document.querySelectorAll('.product-card');
        if (products[index - 1]) {
            products[index - 1].click();
        }
    }
    
    handleEscape() {
        // Close any open modals
        const modals = document.querySelectorAll('.modal.show');
        modals.forEach(modal => {
            const closeBtn = modal.querySelector('[data-bs-dismiss="modal"]');
            if (closeBtn) closeBtn.click();
        });
        
        // Hide shortcuts panel
        const panel = document.getElementById('shortcuts-panel');
        if (panel && panel.style.display !== 'none') {
            panel.style.display = 'none';
        }
    }
    
    setupAutoFocus() {
        // Auto-focus barcode input on page load
        window.addEventListener('load', () => {
            setTimeout(() => this.focusBarcode(), 500);
        });
        
        // Return focus to barcode after adding item
        const originalAddToCart = window.addToCart;
        if (originalAddToCart) {
            window.addToCart = function(...args) {
                originalAddToCart.apply(this, args);
                setTimeout(() => {
                    const input = document.getElementById('barcode-input');
                    if (input) input.focus();
                }, 300);
            };
        }
    }
    
    createShortcutsPanel() {
        const panel = document.createElement('div');
        panel.id = 'shortcuts-panel';
        panel.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            border: 2px solid #0d6efd;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            z-index: 9999;
            max-width: 600px;
            max-height: 80vh;
            overflow-y: auto;
            display: none;
        `;
        
        let html = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h4 style="margin: 0;"><i class="bi bi-keyboard"></i> Keyboard Shortcuts</h4>
                <button onclick="document.getElementById('shortcuts-panel').style.display='none'" 
                        style="border: none; background: none; font-size: 1.5rem; cursor: pointer;">&times;</button>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 10px; font-size: 0.9rem;">
        `;
        
        for (const [key, shortcut] of Object.entries(this.shortcuts)) {
            html += `
                <div style="font-weight: bold; color: #0d6efd;">${key.toUpperCase()}</div>
                <div>${shortcut.description}</div>
            `;
        }
        
        html += `</div>`;
        panel.innerHTML = html;
        document.body.appendChild(panel);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.posKeyboard = new POSKeyboardShortcuts();
});
