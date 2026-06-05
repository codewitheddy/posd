# Quick Start: Modern Calculator for POS System

## ⚡ 5-Minute Setup

### Step 1: Update Your Base Template

Add the calculator to your main POS template (e.g., `pos/templates/base.html`):

```django
{% load static %}
{% load calculator_tags %}

<!DOCTYPE html>
<html>
<head>
    <!-- ... existing head content ... -->
    <link rel="stylesheet" href="{% static 'css/calculator.css' %}">
</head>
<body>
    <!-- ... your page content ... -->
    
    <!-- Add calculator widget at the end -->
    {% calculator_widget %}
    
    <script src="{% static 'js/calculator.js' %}"></script>
</body>
</html>
```

### Step 2: Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### Step 3: Test It

1. Start your Django development server: `python manage.py runserver`
2. Navigate to any POS page
3. Look for the purple calculator in the bottom-right corner
4. Try clicking buttons or typing numbers

## 🎯 What Cashiers Can Do

| Action | How |
|--------|-----|
| **Basic Math** | Click buttons or use keyboard (1+1, 5×4, etc.) |
| **Remember Totals** | Use M+ to add, MR to recall |
| **Quick Calculations** | Click preset buttons (15%, 20%, 100, etc.) |
| **Check History** | Click 📋 icon to see last 50 calculations |
| **Advanced Math** | Click 🔧 to expand scientific functions |
| **Unit Conversions** | Convert currency, length, weight, temperature |
| **Move Around** | Drag the header to reposition calculator |
| **Hide It** | Click ✕ to close (or press Escape) |

## ⌨️ Keyboard Shortcuts

Press these keys directly:
- **Numbers**: 0-9
- **Decimal**: . (period)
- **Plus/Minus/Multiply/Divide**: +, -, *, /
- **Equals**: Enter
- **Delete last**: Backspace
- **Close**: Escape

## 📁 Files Added

```
pos/
├── static/
│   ├── js/
│   │   └── calculator.js          (22KB - Main logic)
│   └── css/
│       └── calculator.css         (7KB - Styling)
├── templatetags/
│   └── calculator_tags.py         (Template tag)
└── templates/
    └── calculator_widget.html     (Widget template)

docs/
├── CALCULATOR_WIDGET.md           (Full documentation)
└── CALCULATOR_INTEGRATION_GUIDE.md (Developer guide)
```

## 🎨 Customization

### Change Colors

Edit `pos/static/css/calculator.css` line 8:

```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
/* Change #667eea and #764ba2 to your brand colors */
```

### Change Position

Edit `pos/static/css/calculator.css` line 5-6:

```css
bottom: 20px;  /* Distance from bottom */
right: 20px;   /* Distance from right */
```

### Add Custom Presets

Edit `pos/static/js/calculator.js`, find the presets section and add buttons:

```html
<button class="calc-btn preset-btn" data-preset="25">25</button>
<button class="calc-btn preset-btn" data-preset="500">500</button>
```

## ✅ Checklist Before Going Live

- [ ] Calculator appears on page
- [ ] Clicking buttons works
- [ ] Keyboard shortcuts work (try typing: 15+25=)
- [ ] Memory buttons work (M+, MR)
- [ ] History saves calculations
- [ ] Advanced toggle shows scientific functions
- [ ] Mobile view works (if using tablets)

## 🐛 Troubleshooting

### Calculator doesn't appear

**Issue**: Purple widget not showing

**Solution**:
1. Check browser console (F12 → Console)
2. Run: `python manage.py collectstatic`
3. Hard refresh browser: Ctrl+Shift+R (or Cmd+Shift+R on Mac)
4. Check template has `{% calculator_widget %}`

### Buttons don't work

**Issue**: Clicking buttons does nothing

**Solution**:
1. Check `js/calculator.js` loaded (F12 → Network)
2. Check `css/calculator.css` loaded
3. Check for JavaScript errors (F12 → Console)
4. Try typing directly (might be faster than clicking)

### History disappears

**Issue**: Calculations not remembered

**Solution**:
1. Browser LocalStorage might be disabled
2. Try in regular (non-private) mode
3. Check browser storage quota

## 📞 Support

For detailed information, see:
- `docs/CALCULATOR_WIDGET.md` - Complete feature documentation
- `docs/CALCULATOR_INTEGRATION_GUIDE.md` - Developer integration guide

## 🚀 Next Steps

Once working, consider:
1. **Train cashiers** on keyboard shortcuts
2. **Customize colors** to match your branding
3. **Add your logo** to the calculator header (optional)
4. **Set up server-side history logging** (optional, see integration guide)
5. **Test on mobile/tablet** devices used by cashiers

---

**That's it!** Your cashiers now have a powerful calculator available anywhere in the POS system.

Enjoy! 🎉
