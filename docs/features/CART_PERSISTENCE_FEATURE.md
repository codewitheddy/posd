# Cart Persistence Feature

## Overview

The POS system now includes **automatic cart persistence** - your shopping cart is automatically saved and restored even if you refresh the page, close the browser, or experience a power outage.

## Features

### ✅ Automatic Saving
- Cart items saved automatically when:
  - Adding products to cart
  - Removing products from cart
  - Changing quantities
  - Selecting/changing customer
  - Applying discounts
  - Every 30 seconds (auto-save)
  - Before closing/refreshing page

### ✅ Automatic Restoration
- Cart restored automatically when:
  - Page loads
  - Browser reopens
  - After system restart
  - After accidental refresh

### ✅ Smart Validation
- Stock availability checked on restore
- Out-of-stock items removed automatically
- Quantities adjusted if stock decreased
- Notifications shown for any changes

### ✅ Complete State Preservation
- Cart items (products, quantities, prices)
- Selected customer (with loyalty info)
- Discount type and value
- All cart calculations

## How It Works

### Storage Location
Data is stored in browser's **localStorage**:
- `pos_cart` - Cart items
- `pos_customer` - Selected customer
- `pos_discount` - Discount settings

### Storage Keys
```javascript
localStorage.setItem('pos_cart', JSON.stringify(cart));
localStorage.setItem('pos_customer', JSON.stringify(selectedCustomer));
localStorage.setItem('pos_discount', JSON.stringify(discountData));
```

### Data Validation
When cart is restored:
1. Check if products still exist
2. Verify stock availability
3. Adjust quantities if needed
4. Remove unavailable items
5. Show notifications for changes

## User Experience

### Scenario 1: Accidental Refresh
```
1. User adds 5 items to cart
2. User accidentally hits F5 (refresh)
3. Page reloads
4. Cart automatically restored with all 5 items
5. Success notification shown
```

### Scenario 2: Browser Close
```
1. User adds items to cart
2. User closes browser (end of day)
3. Next day, user opens browser
4. Navigates to POS screen
5. Cart automatically restored
6. User can continue where they left off
```

### Scenario 3: Stock Changed
```
1. User adds 10 units of Product A to cart
2. User closes browser
3. Meanwhile, another cashier sells 8 units
4. User reopens browser
5. Cart restored with only 2 units (adjusted)
6. Warning notification shown
```

### Scenario 4: Product Deleted
```
1. User adds Product X to cart
2. User closes browser
3. Admin deletes Product X
4. User reopens browser
5. Product X removed from cart
6. Warning notification shown
```

### Scenario 5: Sale Completed
```
1. User adds items to cart
2. User completes sale
3. Cart cleared from storage
4. Fresh start for next sale
```

## Technical Implementation

### Save Function
```javascript
function saveCartToStorage() {
    localStorage.setItem('pos_cart', JSON.stringify(cart));
    
    if (selectedCustomer) {
        localStorage.setItem('pos_customer', JSON.stringify(selectedCustomer));
    }
    
    const discountData = {
        type: document.getElementById('discount-type').value,
        value: document.getElementById('discount-value').value
    };
    localStorage.setItem('pos_discount', JSON.stringify(discountData));
}
```

### Load Function
```javascript
function loadCartFromStorage() {
    const savedCart = localStorage.getItem('pos_cart');
    const savedCustomer = localStorage.getItem('pos_customer');
    const savedDiscount = localStorage.getItem('pos_discount');
    
    // Restore and validate cart
    // Restore customer selection
    // Restore discount settings
    // Update UI
}
```

### Clear Function
```javascript
function clearCartStorage() {
    localStorage.removeItem('pos_cart');
    localStorage.removeItem('pos_customer');
    localStorage.removeItem('pos_discount');
}
```

## Automatic Triggers

### Save Triggers
- `addToCart()` - When product added
- `removeFromCart()` - When product removed
- `updateQuantity()` - When quantity changed
- `customer-select.change` - When customer selected
- `calculateTotal()` - When discount applied
- `beforeunload` event - Before page close
- `setInterval()` - Every 30 seconds

### Clear Triggers
- `completeSale()` - When sale completed
- `clearCart()` - When user clears cart manually

## Storage Limits

### Browser Limits
- **localStorage**: 5-10 MB per domain
- **Typical cart**: < 10 KB
- **Capacity**: ~500-1000 carts worth of data

### Data Size
```
Single cart item: ~100 bytes
10 items: ~1 KB
100 items: ~10 KB
```

## Browser Compatibility

### Supported Browsers
✅ Chrome 4+
✅ Firefox 3.5+
✅ Safari 4+
✅ Edge (all versions)
✅ Opera 10.5+
✅ IE 8+ (with limitations)

### Mobile Support
✅ iOS Safari 3.2+
✅ Android Browser 2.1+
✅ Chrome Mobile
✅ Firefox Mobile

## Privacy & Security

### Data Storage
- Stored locally in browser
- Not sent to server
- Cleared when browser cache cleared
- Separate per browser/device

### Security Considerations
- Data stored in plain text (localStorage)
- Accessible via JavaScript
- Not encrypted by default
- Cleared on logout (optional)

### Best Practices
- Don't store sensitive data (passwords, credit cards)
- Only store cart items and preferences
- Clear on sale completion
- Validate on restoration

## Testing

### Test Scenarios

**Test 1: Basic Persistence**
1. Add items to cart
2. Refresh page (F5)
3. Verify cart restored

**Test 2: Customer Persistence**
1. Select customer
2. Add items to cart
3. Close browser
4. Reopen browser
5. Verify customer and cart restored

**Test 3: Discount Persistence**
1. Add items to cart
2. Apply discount
3. Refresh page
4. Verify discount restored

**Test 4: Stock Validation**
1. Add 10 units to cart
2. In another tab, reduce stock to 5
3. Refresh POS tab
4. Verify quantity adjusted to 5

**Test 5: Sale Completion**
1. Add items to cart
2. Complete sale
3. Verify cart cleared from storage

**Test 6: Manual Clear**
1. Add items to cart
2. Click "Clear Cart"
3. Verify storage cleared

## Troubleshooting

### Cart Not Restoring?

**Check Browser Console:**
```javascript
// Check if data exists
console.log(localStorage.getItem('pos_cart'));
console.log(localStorage.getItem('pos_customer'));
console.log(localStorage.getItem('pos_discount'));
```

**Clear Corrupted Data:**
```javascript
localStorage.removeItem('pos_cart');
localStorage.removeItem('pos_customer');
localStorage.removeItem('pos_discount');
```

### Storage Full?

**Check Storage Usage:**
```javascript
// Estimate storage used
let total = 0;
for (let key in localStorage) {
    if (localStorage.hasOwnProperty(key)) {
        total += localStorage[key].length + key.length;
    }
}
console.log('Storage used:', total, 'bytes');
```

**Clear Old Data:**
```javascript
// Clear all POS data
Object.keys(localStorage)
    .filter(key => key.startsWith('pos_'))
    .forEach(key => localStorage.removeItem(key));
```

### Cart Items Invalid?

**Validate Manually:**
```javascript
const cart = JSON.parse(localStorage.getItem('pos_cart'));
console.log('Cart items:', cart);

// Check each item
cart.forEach(item => {
    console.log('Product ID:', item.id);
    console.log('Available stock:', productStock[item.id]);
});
```

## Configuration

### Auto-Save Interval

Change auto-save frequency:
```javascript
// Current: 30 seconds
setInterval(function() {
    if (cart.length > 0) {
        saveCartToStorage();
    }
}, 30000);

// Change to 60 seconds
setInterval(function() {
    if (cart.length > 0) {
        saveCartToStorage();
    }
}, 60000);
```

### Disable Auto-Save

Comment out auto-save:
```javascript
// Disable periodic auto-save
/*
setInterval(function() {
    if (cart.length > 0) {
        saveCartToStorage();
    }
}, 30000);
*/
```

### Clear on Logout

Add to logout function:
```javascript
function logout() {
    // Clear cart storage on logout
    clearCartStorage();
    
    // Proceed with logout
    window.location.href = '/logout/';
}
```

## Benefits

### For Cashiers
✅ No lost work from accidental refresh
✅ Can take breaks without losing cart
✅ Resume interrupted sales
✅ Less stress about system crashes

### For Business
✅ Reduced abandoned sales
✅ Improved cashier efficiency
✅ Better customer experience
✅ Less training needed

### For Customers
✅ Faster checkout (no re-scanning)
✅ Less waiting time
✅ Better service quality

## Limitations

### Known Limitations
- ⚠️ Data stored per browser/device
- ⚠️ Not synced across devices
- ⚠️ Cleared when cache cleared
- ⚠️ Limited to ~5-10 MB storage
- ⚠️ Not encrypted

### Not Supported
- ❌ Cross-device sync
- ❌ Cloud backup
- ❌ Multi-user sharing
- ❌ Automatic encryption

## Future Enhancements

### Planned Features
- [ ] Cloud sync (with offline-first architecture)
- [ ] Multi-device cart sharing
- [ ] Cart expiration (auto-clear after X days)
- [ ] Cart history/recovery
- [ ] Encrypted storage option
- [ ] Cart templates (saved carts)

### Integration with Offline-First
The cart persistence works seamlessly with the new offline-first architecture:
- Cart saved to localStorage (immediate)
- Cart synced to IndexedDB (offline storage)
- Cart synced to cloud (when online)
- Full cart recovery from any source

## Conclusion

Cart persistence is now a core feature of your POS system, providing:

✅ **Reliability** - Never lose cart data
✅ **Convenience** - Resume anytime
✅ **Validation** - Smart stock checking
✅ **Notifications** - Clear user feedback
✅ **Automatic** - No user action needed

Your cashiers can now work with confidence, knowing their cart is always safe!

## Quick Reference

### Check Cart Storage
```javascript
console.log(JSON.parse(localStorage.getItem('pos_cart')));
```

### Clear Cart Storage
```javascript
localStorage.removeItem('pos_cart');
localStorage.removeItem('pos_customer');
localStorage.removeItem('pos_discount');
```

### Force Save
```javascript
saveCartToStorage();
```

### Force Load
```javascript
loadCartFromStorage();
```

---

**Feature Status:** ✅ Implemented and Active

**Last Updated:** February 10, 2026

**Tested:** Chrome, Firefox, Safari, Edge
