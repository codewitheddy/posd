/**
 * Advanced Floating Calculator Widget
 * Features: Basic & advanced operations, memory functions, history, unit conversion, presets
 */

class AdvancedCalculator {
    constructor() {
        this.display = '0';
        this.previousValue = null;
        this.operation = null;
        this.memory = 0;
        this.history = [];
        this.maxHistory = 50;
        this.isDragging = false;
        this.dragOffsetX = 0;
        this.dragOffsetY = 0;
        
        this.init();
    }

    init() {
        this.createWidget();
        this.attachEventListeners();
        this.loadHistory();
    }

    createWidget() {
        // Check if widget already exists
        if (document.getElementById('calculator-widget')) {
            return;
        }

        const widget = document.createElement('div');
        widget.id = 'calculator-widget';
        widget.className = 'calculator-widget';
        widget.innerHTML = `
            <div class="calculator-header">
                <span class="calculator-title">Calculator</span>
                <div class="calculator-controls">
                    <button class="calc-btn-icon calc-toggle-history" title="History">
                        <i class="icon-history">📋</i>
                    </button>
                    <button class="calc-btn-icon calc-toggle-advanced" title="Advanced">
                        <i class="icon-advanced">🔧</i>
                    </button>
                    <button class="calc-btn-icon calc-minimize" title="Minimize">
                        <i class="icon-minimize">−</i>
                    </button>
                    <button class="calc-btn-icon calc-close" title="Close">
                        <i class="icon-close">✕</i>
                    </button>
                </div>
            </div>

            <div class="calculator-content">
                <!-- Main Calculator -->
                <div class="calculator-main">
                    <div class="calculator-display">
                        <input type="text" class="display-input" id="calc-display" value="0" readonly>
                        <div class="memory-indicator">
                            <span id="memory-display"></span>
                        </div>
                    </div>

                    <div class="calculator-buttons">
                        <!-- Row 1: Memory & Clear -->
                        <div class="button-row">
                            <button class="calc-btn func-btn" data-action="memory-clear">MC</button>
                            <button class="calc-btn func-btn" data-action="memory-recall">MR</button>
                            <button class="calc-btn func-btn" data-action="memory-add">M+</button>
                            <button class="calc-btn func-btn" data-action="memory-subtract">M−</button>
                        </div>

                        <!-- Row 2: Functions -->
                        <div class="button-row">
                            <button class="calc-btn func-btn" data-action="clear">C</button>
                            <button class="calc-btn func-btn" data-action="backspace">⌫</button>
                            <button class="calc-btn func-btn" data-action="percent">%</button>
                            <button class="calc-btn op-btn" data-operation="/">÷</button>
                        </div>

                        <!-- Row 3: Numbers 7-9 -->
                        <div class="button-row">
                            <button class="calc-btn num-btn" data-number="7">7</button>
                            <button class="calc-btn num-btn" data-number="8">8</button>
                            <button class="calc-btn num-btn" data-number="9">9</button>
                            <button class="calc-btn op-btn" data-operation="*">×</button>
                        </div>

                        <!-- Row 4: Numbers 4-6 -->
                        <div class="button-row">
                            <button class="calc-btn num-btn" data-number="4">4</button>
                            <button class="calc-btn num-btn" data-number="5">5</button>
                            <button class="calc-btn num-btn" data-number="6">6</button>
                            <button class="calc-btn op-btn" data-operation="-">−</button>
                        </div>

                        <!-- Row 5: Numbers 1-3 -->
                        <div class="button-row">
                            <button class="calc-btn num-btn" data-number="1">1</button>
                            <button class="calc-btn num-btn" data-number="2">2</button>
                            <button class="calc-btn num-btn" data-number="3">3</button>
                            <button class="calc-btn op-btn" data-operation="+">+</button>
                        </div>

                        <!-- Row 6: 0 and decimals -->
                        <div class="button-row">
                            <button class="calc-btn num-btn" data-number="0" style="flex: 2;">0</button>
                            <button class="calc-btn func-btn" data-action="decimal">.</button>
                            <button class="calc-btn equals-btn" data-action="equals">=</button>
                        </div>

                        <!-- Row 7: Advanced Functions (Hidden by default) -->
                        <div class="button-row advanced-row" style="display: none;">
                            <button class="calc-btn func-btn" data-action="sqrt">√</button>
                            <button class="calc-btn func-btn" data-action="square">x²</button>
                            <button class="calc-btn func-btn" data-action="cube">x³</button>
                            <button class="calc-btn func-btn" data-action="reciprocal">1/x</button>
                        </div>

                        <!-- Row 8: Trigonometric (Hidden) -->
                        <div class="button-row advanced-row" style="display: none;">
                            <button class="calc-btn func-btn" data-action="sin">sin</button>
                            <button class="calc-btn func-btn" data-action="cos">cos</button>
                            <button class="calc-btn func-btn" data-action="tan">tan</button>
                            <button class="calc-btn func-btn" data-action="log">log</button>
                        </div>

                        <!-- Row 9: Conversions (Hidden) -->
                        <div class="button-row advanced-row" style="display: none;">
                            <button class="calc-btn func-btn" data-action="convert-currency">💱</button>
                            <button class="calc-btn func-btn" data-action="convert-length">📏</button>
                            <button class="calc-btn func-btn" data-action="convert-weight">⚖️</button>
                            <button class="calc-btn func-btn" data-action="convert-temp">🌡️</button>
                        </div>
                    </div>

                    <!-- Presets -->
                    <div class="presets-section" style="display: none;">
                        <label>Presets:</label>
                        <div class="preset-buttons">
                            <button class="calc-btn preset-btn" data-preset="15">15%</button>
                            <button class="calc-btn preset-btn" data-preset="18">18%</button>
                            <button class="calc-btn preset-btn" data-preset="20">20%</button>
                            <button class="calc-btn preset-btn" data-preset="50">50</button>
                            <button class="calc-btn preset-btn" data-preset="100">100</button>
                            <button class="calc-btn preset-btn" data-preset="1000">1000</button>
                        </div>
                    </div>
                </div>

                <!-- History Panel (Hidden by default) -->
                <div class="calculator-history" style="display: none;">
                    <div class="history-header">
                        <h4>Calculation History</h4>
                        <button class="calc-btn-small" id="clear-history">Clear</button>
                    </div>
                    <div class="history-list" id="history-list">
                        <p class="no-history">No history yet</p>
                    </div>
                </div>

                <!-- Converter Panel (Hidden by default) -->
                <div class="calculator-converter" style="display: none;">
                    <div class="converter-content" id="converter-content">
                        <p>Select a conversion type from the calculator</p>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(widget);
    }

    attachEventListeners() {
        const display = document.getElementById('calc-display');
        const widget = document.getElementById('calculator-widget');

        // Number buttons
        document.querySelectorAll('[data-number]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.inputNumber(btn.dataset.number);
                this.updateDisplay();
            });
        });

        // Operation buttons
        document.querySelectorAll('[data-operation]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.setOperation(btn.dataset.operation);
                this.updateDisplay();
            });
        });

        // Action buttons
        document.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleAction(btn.dataset.action);
            });
        });

        // Preset buttons
        document.querySelectorAll('[data-preset]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.display = btn.dataset.preset;
                this.updateDisplay();
            });
        });

        // Toggle buttons
        document.querySelector('.calc-toggle-history').addEventListener('click', () => {
            this.toggleHistory();
        });

        document.querySelector('.calc-toggle-advanced').addEventListener('click', () => {
            this.toggleAdvanced();
        });

        document.querySelector('.calc-minimize').addEventListener('click', () => {
            this.toggleMinimize();
        });

        document.querySelector('.calc-close').addEventListener('click', () => {
            widget.style.display = 'none';
        });

        // Keyboard support
        document.addEventListener('keydown', (e) => {
            if (e.key.match(/[0-9]/)) this.inputNumber(e.key);
            if (e.key === '.') this.handleAction('decimal');
            if (e.key === '+') this.setOperation('+');
            if (e.key === '-') this.setOperation('-');
            if (e.key === '*') this.setOperation('*');
            if (e.key === '/') { e.preventDefault(); this.setOperation('/'); }
            if (e.key === 'Enter') this.handleAction('equals');
            if (e.key === 'Backspace') this.handleAction('backspace');
            if (e.key === 'Escape') widget.style.display = 'none';
            this.updateDisplay();
        });

        // Clear history
        const clearHistoryBtn = document.getElementById('clear-history');
        if (clearHistoryBtn) {
            clearHistoryBtn.addEventListener('click', () => {
                this.history = [];
                this.saveHistory();
                this.updateHistoryDisplay();
            });
        }
    }

    inputNumber(num) {
        if (this.display === '0' && num !== '.') {
            this.display = num;
        } else if (num === '.' && this.display.includes('.')) {
            return;
        } else {
            this.display += num;
        }
    }

    setOperation(op) {
        if (this.previousValue === null) {
            this.previousValue = parseFloat(this.display);
            this.display = '0';
        } else if (this.operation) {
            this.calculate();
        }
        this.operation = op;
    }

    calculate() {
        if (this.operation === null || this.previousValue === null) return;

        const current = parseFloat(this.display);
        let result = 0;

        switch (this.operation) {
            case '+': result = this.previousValue + current; break;
            case '-': result = this.previousValue - current; break;
            case '*': result = this.previousValue * current; break;
            case '/': result = this.previousValue / current; break;
        }

        this.addToHistory(`${this.previousValue} ${this.operation} ${current} = ${result}`);
        this.display = result.toString();
        this.previousValue = null;
        this.operation = null;
    }

    handleAction(action) {
        const current = parseFloat(this.display);

        switch (action) {
            case 'clear':
                this.display = '0';
                this.previousValue = null;
                this.operation = null;
                break;
            case 'backspace':
                this.display = this.display.slice(0, -1) || '0';
                break;
            case 'decimal':
                if (!this.display.includes('.')) {
                    this.display += '.';
                }
                break;
            case 'percent':
                this.display = (current / 100).toString();
                break;
            case 'equals':
                this.calculate();
                break;
            case 'sqrt':
                this.display = Math.sqrt(current).toString();
                this.addToHistory(`√${current} = ${this.display}`);
                break;
            case 'square':
                this.display = (current * current).toString();
                this.addToHistory(`${current}² = ${this.display}`);
                break;
            case 'cube':
                this.display = (current * current * current).toString();
                this.addToHistory(`${current}³ = ${this.display}`);
                break;
            case 'reciprocal':
                this.display = (1 / current).toString();
                this.addToHistory(`1/${current} = ${this.display}`);
                break;
            case 'sin':
                this.display = Math.sin(current * Math.PI / 180).toString();
                this.addToHistory(`sin(${current}°) = ${this.display}`);
                break;
            case 'cos':
                this.display = Math.cos(current * Math.PI / 180).toString();
                this.addToHistory(`cos(${current}°) = ${this.display}`);
                break;
            case 'tan':
                this.display = Math.tan(current * Math.PI / 180).toString();
                this.addToHistory(`tan(${current}°) = ${this.display}`);
                break;
            case 'log':
                this.display = Math.log10(current).toString();
                this.addToHistory(`log(${current}) = ${this.display}`);
                break;
            case 'memory-clear':
                this.memory = 0;
                this.updateMemoryDisplay();
                break;
            case 'memory-add':
                this.memory += current;
                this.updateMemoryDisplay();
                break;
            case 'memory-subtract':
                this.memory -= current;
                this.updateMemoryDisplay();
                break;
            case 'memory-recall':
                this.display = this.memory.toString();
                break;
            case 'convert-currency':
            case 'convert-length':
            case 'convert-weight':
            case 'convert-temp':
                this.showConverter(action);
                break;
        }

        this.updateDisplay();
    }

    updateDisplay() {
        const display = document.getElementById('calc-display');
        display.value = this.display;
    }

    updateMemoryDisplay() {
        const memoryDisplay = document.getElementById('memory-display');
        if (this.memory !== 0) {
            memoryDisplay.textContent = `M: ${this.memory.toFixed(2)}`;
            memoryDisplay.style.display = 'block';
        } else {
            memoryDisplay.style.display = 'none';
        }
    }

    addToHistory(entry) {
        this.history.unshift({
            calculation: entry,
            timestamp: new Date().toLocaleTimeString()
        });
        if (this.history.length > this.maxHistory) {
            this.history.pop();
        }
        this.saveHistory();
        this.updateHistoryDisplay();
    }

    updateHistoryDisplay() {
        const historyList = document.getElementById('history-list');
        if (this.history.length === 0) {
            historyList.innerHTML = '<p class="no-history">No history yet</p>';
            return;
        }
        
        historyList.innerHTML = this.history.map(entry => `
            <div class="history-item">
                <span class="history-calc">${entry.calculation}</span>
                <span class="history-time">${entry.timestamp}</span>
            </div>
        `).join('');
    }

    toggleHistory() {
        const history = document.querySelector('.calculator-history');
        const main = document.querySelector('.calculator-main');
        
        if (history.style.display === 'none') {
            history.style.display = 'block';
            main.style.display = 'none';
        } else {
            history.style.display = 'none';
            main.style.display = 'block';
        }
        this.updateHistoryDisplay();
    }

    toggleAdvanced() {
        const rows = document.querySelectorAll('.advanced-row');
        const presets = document.querySelector('.presets-section');
        
        rows.forEach(row => {
            row.style.display = row.style.display === 'none' ? 'flex' : 'none';
        });
        
        if (presets) {
            presets.style.display = presets.style.display === 'none' ? 'block' : 'none';
        }
    }

    toggleMinimize() {
        const content = document.querySelector('.calculator-content');
        content.style.display = content.style.display === 'none' ? 'block' : 'none';
    }

    showConverter(type) {
        const converterPanel = document.querySelector('.calculator-converter');
        const main = document.querySelector('.calculator-main');
        const current = parseFloat(this.display);

        let converterHTML = '';
        switch (type) {
            case 'convert-currency':
                converterHTML = `
                    <h4>Currency Conversion</h4>
                    <p>${current} USD = ${(current * 1).toFixed(2)} USD</p>
                    <p>(Conversion rates would be fetched from API in production)</p>
                `;
                break;
            case 'convert-length':
                converterHTML = `
                    <h4>Length Conversion</h4>
                    <p>${current} m = ${(current * 3.28084).toFixed(2)} ft</p>
                    <p>${current} m = ${(current * 1.09361).toFixed(2)} yd</p>
                    <p>${current} km = ${(current * 0.621371).toFixed(2)} mi</p>
                `;
                break;
            case 'convert-weight':
                converterHTML = `
                    <h4>Weight Conversion</h4>
                    <p>${current} kg = ${(current * 2.20462).toFixed(2)} lb</p>
                    <p>${current} kg = ${(current * 35.274).toFixed(2)} oz</p>
                    <p>${current} g = ${(current * 0.00220462).toFixed(2)} lb</p>
                `;
                break;
            case 'convert-temp':
                converterHTML = `
                    <h4>Temperature Conversion</h4>
                    <p>${current}°C = ${((current * 9/5) + 32).toFixed(2)}°F</p>
                    <p>${current}°C = ${(current + 273.15).toFixed(2)}K</p>
                `;
                break;
        }

        document.getElementById('converter-content').innerHTML = converterHTML;
        main.style.display = 'none';
        converterPanel.style.display = 'block';
    }

    saveHistory() {
        try {
            localStorage.setItem('calculator_history', JSON.stringify(this.history));
        } catch (e) {
            console.warn('Could not save calculator history:', e);
        }
    }

    loadHistory() {
        try {
            const saved = localStorage.getItem('calculator_history');
            if (saved) {
                this.history = JSON.parse(saved);
            }
        } catch (e) {
            console.warn('Could not load calculator history:', e);
        }
    }
}

// Initialize calculator when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.calculator = new AdvancedCalculator();
});
