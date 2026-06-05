# Advanced Calculator Widget for POS System

A modern, floating calculator widget designed for cashiers in the POS system. Features advanced calculations, history tracking, unit conversions, and memory functions.

## Features

### Basic Operations
- Addition, Subtraction, Multiplication, Division
- Percentage calculations
- Decimal support
- Backspace/Clear functionality

### Advanced Functions
- **Math**: Square root (√), Square (x²), Cube (x³), Reciprocal (1/x)
- **Trigonometry**: Sine, Cosine, Tangent (in degrees)
- **Logarithm**: Base-10 logarithm

### Memory Functions
- **MC**: Clear memory
- **MR**: Recall memory value
- **M+**: Add to memory
- **M−**: Subtract from memory

### Conversion Tools
- **Currency Conversion**: USD conversions (extensible for other currencies)
- **Length Conversion**: Meters ↔ Feet, Yards, Miles
- **Weight Conversion**: Kilograms ↔ Pounds, Ounces
- **Temperature Conversion**: Celsius ↔ Fahrenheit, Kelvin

### Additional Features
- **Calculation History**: Last 50 calculations stored with timestamps
- **Presets**: Quick access buttons for common values (15%, 18%, 20%, 50, 100, 1000)
- **Persistent Storage**: History saved to browser LocalStorage
- **Draggable Widget**: Move calculator anywhere on screen
- **Keyboard Support**: Full keyboard control (numbers, operators, Backspace, Enter, Escape)
- **Responsive Design**: Works on desktop and mobile

## Installation

### 1. JavaScript and CSS Files

The calculator files are already included:
- `pos/static/js/calculator.js` - Main calculator logic
- `pos/static/css/calculator.css` - Styling

### 2. Add to Your Templates

**Option A: Using Template Tag**

In your base template (e.g., `templates/base.html`):
```django
{% load calculator_tags %}
<!DOCTYPE html>
<html>
<head>
    {% calculator_widget %}
</head>
<body>
    <!-- Your content -->
</body>
</html>
```

**Option B: Manual Inclusion**

In your base template:
```django
{% load static %}
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="{% static 'css/calculator.css' %}">
</head>
<body>
    <!-- Your content -->
    <script src="{% static 'js/calculator.js' %}"></script>
</body>
</html>
```

### 3. Collect Static Files (Production)

```bash
python manage.py collectstatic
```

## Usage

### For Cashiers

1. **Access the Calculator**: The calculator appears as a floating widget in the bottom-right corner
2. **Basic Calculations**: Click buttons or use keyboard to enter numbers and operations
3. **Memory Functions**: Use MC, MR, M+, M− buttons to store intermediate values
4. **View History**: Click the 📋 icon to see calculation history
5. **Advanced Functions**: Click the 🔧 icon to expand advanced math and conversion tools
6. **Drag Widget**: Click and drag the header to move calculator anywhere
7. **Minimize**: Click the − button to collapse the calculator
8. **Close**: Click the ✕ button to hide the calculator (it'll appear again on page refresh)

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `0-9` | Input numbers |
| `.` | Decimal point |
| `+`, `-`, `*`, `/` | Operations |
| `Enter` | Calculate |
| `Backspace` | Delete last digit |
| `Escape` | Close calculator |

## Customization

### Changing Position

Edit `pos/static/css/calculator.css`, line 5:
```css
#calculator-widget {
    position: fixed;
    bottom: 20px;  /* Change this */
    right: 20px;   /* Or this */
}
```

### Changing Colors

The calculator uses a purple gradient by default. Modify these in `calculator.css`:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Adding Presets

Edit `pos/static/js/calculator.js`, search for the presets section:
```html
<button class="calc-btn preset-btn" data-preset="15">15%</button>
<!-- Add more buttons as needed -->
```

### Adding Conversion Rates

To add real currency conversion rates, modify the `showConverter()` method in `calculator.js` to fetch from an API:
```javascript
case 'convert-currency':
    const rates = await fetch('/api/exchange-rates/').then(r => r.json());
    // Use rates to display conversions
    break;
```

## Architecture

### JavaScript Class: `AdvancedCalculator`

**Properties:**
- `display` - Current display value
- `previousValue` - Stored operand
- `operation` - Current operation
- `memory` - Memory register value
- `history` - Array of calculation history

**Key Methods:**
- `inputNumber(num)` - Add digit to display
- `setOperation(op)` - Set operation and store value
- `calculate()` - Perform calculation
- `handleAction(action)` - Handle special functions
- `addToHistory(entry)` - Log calculation
- `toggleAdvanced()` - Show/hide advanced functions
- `toggleHistory()` - Show/hide history panel
- `showConverter(type)` - Display conversion tool

### Storage

Calculation history is stored in browser LocalStorage under the key `calculator_history`. This persists across page refreshes.

## Browser Compatibility

- Chrome/Edge 60+
- Firefox 55+
- Safari 11+
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance Considerations

- Lightweight (~22KB JavaScript, ~7KB CSS)
- No external dependencies (pure vanilla JavaScript)
- LocalStorage limits history to 50 calculations
- CSS animations optimized for 60fps

## API Integration (Future)

The calculator can be extended to:
1. **Sync with backend**: POST calculations for audit logging
2. **Real exchange rates**: Fetch current currency rates
3. **Custom presets**: Load presets per business/user
4. **Calculation sharing**: Export/share calculation history

Example API endpoint structure:
```
POST /api/calculator/history/
{
    "calculation": "15 + 25 = 40",
    "timestamp": "2026-05-17T17:46:55Z"
}
```

## Troubleshooting

### Calculator not appearing
1. Check browser console for errors (F12 → Console)
2. Verify static files are collected: `python manage.py collectstatic`
3. Clear browser cache and refresh

### History not persisting
- LocalStorage may be disabled in browser settings
- Private/Incognito mode may not support LocalStorage
- Check browser storage quota

### Keyboard shortcuts not working
- Calculator JavaScript may not have focus
- Try clicking on the calculator first
- Check for conflicting JavaScript on the page

## Security & Privacy

- All calculations happen client-side (browser)
- History stored in browser LocalStorage (not sent to server)
- No personal data collected
- To clear history: Open calculator → History → Clear

## Testing

Manual test checklist:
- [ ] Basic math operations (+ - × ÷)
- [ ] Decimal calculations
- [ ] Memory functions
- [ ] Keyboard input
- [ ] History saving and clearing
- [ ] Advanced functions toggle
- [ ] Conversions display correctly
- [ ] Drag/move widget
- [ ] Minimize/maximize
- [ ] Mobile responsiveness

## Future Enhancements

- [ ] Scientific mode with more functions
- [ ] Unit conversion with live exchange rates
- [ ] Voice input for numbers
- [ ] Dark mode toggle
- [ ] Custom themes per business
- [ ] Calculation export (PDF/CSV)
- [ ] Server-side history sync
- [ ] Split screen view (calculation + item entry)

## Support

For issues or feature requests related to the calculator, check:
1. Browser console for JavaScript errors
2. Network tab for failed static file loads
3. Django logs for template rendering errors

---

**Version**: 1.0  
**Last Updated**: 2026-05-17  
**Author**: POS System Development Team
