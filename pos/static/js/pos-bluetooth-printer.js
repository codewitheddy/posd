/**
 * Marid POS - Web Bluetooth ESC/POS Printing Engine
 * 
 * Provides direct, zero-dialog 1-click receipt printing to standard
 * portable & desktop Bluetooth thermal receipt printers (58mm / 80mm).
 * 
 * Compatible with Chrome, Edge, Chromium on Android, Windows, Mac, Linux.
 */

(function(window) {
    'use strict';

    // ==========================================
    // 1. ESC/POS Command Byte Builder
    // ==========================================
    class ESCBuilder {
        constructor(paperWidth = 80) {
            this.paperWidth = parseInt(paperWidth, 10) === 58 ? 58 : 80;
            this.maxCols = this.paperWidth === 58 ? 32 : 48; // Standard ASCII char limit per line
            this.buffer = [];
            this.encoder = new TextEncoder();
            this.init();
        }

        // Push raw byte(s) or arrays to buffer
        raw(...bytes) {
            for (let i = 0; i < bytes.length; i++) {
                const b = bytes[i];
                if (Array.isArray(b) || b instanceof Uint8Array) {
                    for (let j = 0; j < b.length; j++) this.buffer.push(b[j]);
                } else if (typeof b === 'number') {
                    this.buffer.push(b);
                }
            }
            return this;
        }

        // Initialize printer
        init() {
            return this.raw(0x1B, 0x40); // ESC @
        }

        // Text Alignment: 'left' | 'center' | 'right'
        align(align = 'left') {
            const code = align === 'center' ? 0x01 : align === 'right' ? 0x02 : 0x00;
            return this.raw(0x1B, 0x61, code); // ESC a n
        }

        // Bold formatting
        bold(enable = true) {
            return this.raw(0x1B, 0x45, enable ? 0x01 : 0x00); // ESC E n
        }

        // Underline formatting
        underline(enable = true) {
            return this.raw(0x1B, 0x2D, enable ? 0x01 : 0x00); // ESC - n
        }

        // Inverted text (white on black)
        invert(enable = true) {
            return this.raw(0x1D, 0x42, enable ? 0x01 : 0x00); // GS B n
        }

        // Font sizing: 'normal' | 'double-height' | 'double-width' | 'double' | 'large'
        size(mode = 'normal') {
            let byteVal = 0x00;
            if (mode === 'double-height') byteVal = 0x01;
            else if (mode === 'double-width') byteVal = 0x10;
            else if (mode === 'double' || mode === 'large') byteVal = 0x11;
            return this.raw(0x1D, 0x21, byteVal); // GS ! n
        }

        // Set default line spacing
        defaultLineSpacing() {
            return this.raw(0x1B, 0x32); // ESC 2
        }

        // Feed N lines
        feed(lines = 1) {
            return this.raw(0x1B, 0x64, Math.max(1, Math.min(lines, 20))); // ESC d n
        }

        // Line break
        newLine() {
            return this.raw(0x0A); // LF
        }

        // Print text encoded in UTF-8 / ASCII
        text(str = '') {
            if (!str) return this;
            // Normalize string to handle common currency symbols and accents
            const cleanStr = str
                .replace(/[•]/g, '-')
                .replace(/[—–]/g, '-')
                .replace(/[“”]/g, '"')
                .replace(/[‘’]/g, "'")
                .replace(/[⭐]/g, '*');
            const bytes = this.encoder.encode(cleanStr);
            return this.raw(bytes);
        }

        // Print text with a newline
        line(str = '') {
            this.text(str);
            return this.newLine();
        }

        // Horizontal divider line
        divider(char = '-') {
            const rule = char.repeat(this.maxCols);
            return this.line(rule);
        }

        // Double horizontal divider
        doubleDivider() {
            return this.divider('=');
        }

        // Dashed divider
        dashedDivider() {
            return this.divider('-');
        }

        // Formatted two-column row (Left and Right aligned)
        // Example: "Subtotal", "KES 1,200.00"
        row(leftText = '', rightText = '', fillChar = ' ') {
            leftText = String(leftText || '');
            rightText = String(rightText || '');

            const totalLen = this.maxCols;
            const rightLen = rightText.length;

            if (leftText.length + rightLen >= totalLen) {
                // Wrap or truncate left if too long
                const maxLeft = totalLen - rightLen - 1;
                if (maxLeft > 0) {
                    const truncatedLeft = leftText.substring(0, maxLeft);
                    const spaces = totalLen - (truncatedLeft.length + rightLen);
                    return this.line(truncatedLeft + fillChar.repeat(Math.max(1, spaces)) + rightText);
                } else {
                    this.line(leftText);
                    const spaces = Math.max(0, totalLen - rightLen);
                    return this.line(fillChar.repeat(spaces) + rightText);
                }
            } else {
                const spaces = totalLen - (leftText.length + rightLen);
                return this.line(leftText + fillChar.repeat(spaces) + rightText);
            }
        }

        // Formatted line item row
        // Line 1: Item Name [SKU]
        // Line 2: "  2 x 100.00"   ->   "200.00"
        itemRow(name, code, qtyUnit, unitPrice, totalPrice) {
            let title = name;
            if (code) title += ` [${code}]`;
            this.line(title);

            const calcLeft = `  ${qtyUnit} x ${unitPrice}`;
            const totalRight = String(totalPrice);
            return this.row(calcLeft, totalRight);
        }

        // Center aligned block
        centerText(str = '', isBold = false, sizeMode = 'normal') {
            this.align('center');
            if (isBold) this.bold(true);
            if (sizeMode !== 'normal') this.size(sizeMode);
            
            this.line(str);

            if (sizeMode !== 'normal') this.size('normal');
            if (isBold) this.bold(false);
            this.align('left');
            return this;
        }

        // Print Code 128 Barcode
        barcode128(data) {
            if (!data) return this;
            const strData = String(data).trim();
            this.align('center');
            // Height: 50 dots
            this.raw(0x1D, 0x68, 50); // GS h n
            // Width: 2 (default)
            this.raw(0x1D, 0x77, 2);  // GS w n
            // HRI characters below barcode
            this.raw(0x1D, 0x48, 2);  // GS H 2
            // Print Code128 (System B)
            const bytes = this.encoder.encode(strData);
            this.raw(0x1D, 0x6B, 0x49, bytes.length, bytes); // GS k 73 len bytes
            this.newLine();
            this.align('left');
            return this;
        }

        // Print Standard ESC/POS QR Code
        qrCode(data) {
            if (!data) return this;
            const strData = String(data).trim();
            const bytes = this.encoder.encode(strData);
            const len = bytes.length + 3;
            const pL = len % 256;
            const pH = Math.floor(len / 256);

            this.align('center');
            // 1. Model: QR Model 2
            this.raw(0x1D, 0x28, 0x6B, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00);
            // 2. Size: Module size 4 (58mm) or 5 (80mm)
            const moduleSize = this.paperWidth === 58 ? 4 : 5;
            this.raw(0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x43, moduleSize);
            // 3. Error correction: Level M
            this.raw(0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x45, 0x31);
            // 4. Store data
            this.raw(0x1D, 0x28, 0x6B, pL, pH, 0x31, 0x50, 0x30, bytes);
            // 5. Print QR
            this.raw(0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x51, 0x30);
            this.newLine();
            this.align('left');
            return this;
        }

        // Cut paper & feed
        cut(autoCut = true) {
            this.feed(3);
            if (autoCut) {
                // Partial Cut command: GS V 66 0
                this.raw(0x1D, 0x56, 0x42, 0x00);
            }
            return this;
        }

        // Cash drawer kick pulse (Pin 2 / 5)
        kickDrawer() {
            return this.raw(0x1B, 0x70, 0x00, 0x19, 0xFA); // ESC p 0 25 250
        }

        // Build final Uint8Array payload
        build() {
            return new Uint8Array(this.buffer);
        }
    }


    // ==========================================
    // 2. Web Bluetooth Printer Manager
    // ==========================================
    class WebBluetoothPrinterManager {
        constructor() {
            this.device = null;
            this.server = null;
            this.characteristic = null;
            this.isConnecting = false;
            this.isPrinting = false;
            this.lastDeviceName = localStorage.getItem('pos_bt_printer_name') || null;
            this.lastDeviceId = localStorage.getItem('pos_bt_printer_id') || null;
            this.autoPrintEnabled = localStorage.getItem('pos_bt_autoprint') === 'true';

            // Common Thermal Printer Bluetooth GATT Service UUIDs
            this.SERVICES = [
                '000018f0-0000-1000-8000-00805f9b34fb', // Standard POS Printer Service
                'e7810a71-73ae-499d-8c15-faa9aef0c3f2', // Rongta / POS-58 / POS-80
                '49535343-fe7d-4ae5-8fa9-9fafd205e455', // ISSC Transparent Serial
                '0000fff0-0000-1000-8000-00805f9b34fb', // Common BLE Serial (0xFFF0)
                '0000ff00-0000-1000-8000-00805f9b34fb', // Common BLE Serial (0xFF00)
                '0000fee7-0000-1000-8000-00805f9b34fb', // Tencent / WeChat POS
                '0000ae00-0000-1000-8000-00805f9b34fb', // GOOJPRT / Zhuhai
                '0000ae30-0000-1000-8000-00805f9b34fb',
                '0000ffe0-0000-1000-8000-00805f9b34fb', // HM-10 / CC2541 BLE
                '00001101-0000-1000-8000-00805f9b34fb'  // SPP Serial Port Profile
            ];
        }

        // Check if Web Bluetooth is supported in current browser & context
        isSupported() {
            return !!(navigator && 'bluetooth' in navigator && typeof navigator.bluetooth.requestDevice === 'function');
        }

        // Is currently connected
        isConnected() {
            return !!(this.device && this.device.gatt && this.device.gatt.connected && this.characteristic);
        }

        // Get Printer Display Name
        getDeviceName() {
            if (this.device && this.device.name) return this.device.name;
            if (this.lastDeviceName) return `${this.lastDeviceName} (Saved)`;
            return 'No Bluetooth Printer';
        }

        // Connect to a Bluetooth Printer
        async connect() {
            if (!this.isSupported()) {
                throw new Error('Web Bluetooth is not supported in this browser. Please use Chrome or Edge on Windows, Android, Mac, or Linux over HTTPS / localhost.');
            }

            if (this.isConnected()) {
                return this.device;
            }

            this.isConnecting = true;
            this._notifyStatus('connecting', 'Searching for Bluetooth thermal printers...');

            try {
                // Request Bluetooth Device
                const device = await navigator.bluetooth.requestDevice({
                    acceptAllDevices: true,
                    optionalServices: this.SERVICES
                });

                this._notifyStatus('connecting', `Connecting to ${device.name || 'Printer'}...`);

                device.addEventListener('gattserverdisconnected', (e) => this._onDisconnected(e));

                const server = await device.gatt.connect();
                this.server = server;
                this.device = device;

                // Find write characteristic
                let writeChar = null;

                // Search primary services
                const services = await server.getPrimaryServices();
                for (const service of services) {
                    try {
                        const characteristics = await service.getCharacteristics();
                        for (const char of characteristics) {
                            if (char.properties.write || char.properties.writeWithoutResponse) {
                                writeChar = char;
                                break;
                            }
                        }
                    } catch (err) {
                        console.warn('Error reading characteristics for service:', service.uuid, err);
                    }
                    if (writeChar) break;
                }

                if (!writeChar) {
                    throw new Error('Could not find a writable ESC/POS characteristic on this Bluetooth device.');
                }

                this.characteristic = writeChar;
                this.lastDeviceName = device.name || 'Thermal Printer';
                this.lastDeviceId = device.id;
                localStorage.setItem('pos_bt_printer_name', this.lastDeviceName);
                localStorage.setItem('pos_bt_printer_id', this.lastDeviceId);

                this._notifyStatus('connected', `Connected to ${this.lastDeviceName}`);
                return device;

            } catch (error) {
                console.error('[Web Bluetooth] Connection failed:', error);
                this._notifyStatus('error', error.message || 'Connection cancelled or failed');
                throw error;
            } finally {
                this.isConnecting = false;
            }
        }

        // Disconnect
        async disconnect() {
            try {
                if (this.device && this.device.gatt && this.device.gatt.connected) {
                    this.device.gatt.disconnect();
                }
            } catch (err) {
                console.warn('Error disconnecting:', err);
            } finally {
                this.characteristic = null;
                this.server = null;
                this._notifyStatus('disconnected', 'Bluetooth printer disconnected');
            }
        }

        // Send raw Uint8Array buffer in chunks to prevent BLE MTU buffer overruns
        async sendRawBuffer(uint8Data, chunkSize = 100, delayMs = 15) {
            if (!this.isConnected()) {
                await this.connect();
            }

            if (!this.characteristic) {
                throw new Error('Printer write characteristic is not ready.');
            }

            this.isPrinting = true;
            this._notifyStatus('printing', 'Sending receipt data to printer...');

            try {
                const totalBytes = uint8Data.length;
                let offset = 0;

                while (offset < totalBytes) {
                    const chunk = uint8Data.slice(offset, offset + chunkSize);
                    
                    if (this.characteristic.properties.writeWithoutResponse) {
                        await this.characteristic.writeValueWithoutResponse(chunk);
                    } else {
                        await this.characteristic.writeValue(chunk);
                    }

                    offset += chunkSize;
                    if (offset < totalBytes && delayMs > 0) {
                        await new Promise(resolve => setTimeout(resolve, delayMs));
                    }
                }

                this._notifyStatus('connected', `Receipt printed successfully!`);
                return true;

            } catch (error) {
                console.error('[Web Bluetooth] Print transfer error:', error);
                this._notifyStatus('error', `Print failed: ${error.message}`);
                throw error;
            } finally {
                this.isPrinting = false;
            }
        }

        // ==========================================
        // 3. High-Level Receipt Printing Methods
        // ==========================================

        /**
         * Generate and print receipt from structured sale data
         */
        async printReceipt(saleData, settings = {}) {
            const paperWidth = parseInt(settings.thermal_receipt_width || 80, 10);
            const autoCut = settings.thermal_auto_cut !== false;
            const copies = Math.max(1, parseInt(settings.thermal_copies || 1, 10));

            const builder = new ESCBuilder(paperWidth);

            for (let c = 0; c < copies; c++) {
                builder.init();

                // 1. Store Header
                const storeName = settings.shop_name || settings.business_name || 'RETAIL STORE';
                builder.centerText(storeName.toUpperCase(), true, 'double');

                if (settings.receipt_header) {
                    builder.centerText(settings.receipt_header, false);
                }
                if (saleData.branch_name) {
                    builder.centerText(`Branch: ${saleData.branch_name}`, true);
                }
                if (settings.address) {
                    builder.centerText(settings.address, false);
                }
                if (settings.phone) {
                    builder.centerText(`Tel: ${settings.phone}`, false);
                }
                if (settings.tax_id) {
                    builder.centerText(`KRA PIN / Tax ID: ${settings.tax_id}`, true);
                }

                builder.doubleDivider();

                // 2. Transaction Metadata
                builder.row('Invoice:', String(saleData.invoice_number || '-'));
                builder.row('Date:', String(saleData.date || new Date().toLocaleString()));
                if (saleData.cashier_name) {
                    builder.row('Cashier:', String(saleData.cashier_name));
                }
                if (saleData.terminal_code) {
                    builder.row('Terminal:', String(saleData.terminal_code));
                }
                if (saleData.customer_name) {
                    builder.row('Customer:', String(saleData.customer_name));
                }

                builder.dashedDivider();

                // 3. Line Items
                builder.row('ITEM / DESC', 'AMOUNT (KES)');
                builder.dashedDivider();

                const items = saleData.items || [];
                items.forEach(item => {
                    const name = item.name || item.product_name || 'Item';
                    const code = item.product_code || item.barcode || '';
                    const qty = item.quantity || 1;
                    const unit = item.unit || '';
                    const unitPrice = parseFloat(item.unit_price || item.price || 0).toFixed(2);
                    const total = parseFloat(item.total_price || item.total || 0).toFixed(2);
                    const qtyStr = unit ? `${qty} ${unit}` : `${qty}`;

                    builder.itemRow(name, code, qtyStr, unitPrice, total);
                    if (item.note) {
                        builder.line(`  * ${item.note}`);
                    }
                });

                builder.dashedDivider();

                // 4. Totals & VAT Breakdown
                const subtotal = parseFloat(saleData.subtotal || 0).toFixed(2);
                const discount = parseFloat(saleData.discount_amount || 0);
                const vatAmount = parseFloat(saleData.vat_amount || 0).toFixed(2);
                const vatRate = saleData.vat_rate || 16;
                const total = parseFloat(saleData.total || 0).toFixed(2);

                builder.row('Subtotal (Excl Tax):', subtotal);
                if (discount > 0) {
                    builder.row('Discount:', `-${discount.toFixed(2)}`);
                }
                if (settings.thermal_show_tax_breakdown !== false) {
                    builder.row(`VAT (${vatRate}%):`, vatAmount);
                }
                
                builder.doubleDivider();
                builder.align('left');
                builder.bold(true);
                builder.size('double-height');
                builder.row('TOTAL DUE:', `KES ${total}`);
                builder.size('normal');
                builder.bold(false);

                // 5. Payment Summary
                if (saleData.payments && saleData.payments.length > 0) {
                    builder.dashedDivider();
                    builder.centerText('PAYMENT SUMMARY', true);
                    saleData.payments.forEach(pm => {
                        const mName = pm.name || pm.method_name || 'Payment';
                        const mAmount = parseFloat(pm.amount || 0).toFixed(2);
                        builder.row(mName, mAmount);
                        if (pm.reference) {
                            builder.line(`  Ref: ${pm.reference}`);
                        }
                    });

                    const paid = parseFloat(saleData.amount_paid || saleData.total || 0).toFixed(2);
                    const change = parseFloat(saleData.change_given || 0).toFixed(2);
                    builder.dashedDivider();
                    builder.row('Amount Paid:', paid);
                    if (parseFloat(change) > 0) {
                        builder.row('Change Returned:', change);
                    }
                }

                // 6. Loyalty Rewards
                if (saleData.loyalty_points || saleData.customer_loyalty_balance) {
                    builder.dashedDivider();
                    builder.centerText('* LOYALTY REWARDS *', true);
                    if (saleData.loyalty_earned) {
                        builder.centerText(`+${saleData.loyalty_earned} Points Earned!`, true);
                    }
                    if (saleData.loyalty_redeemed) {
                        builder.centerText(`-${saleData.loyalty_redeemed} Points Redeemed`, true);
                    }
                    if (saleData.customer_loyalty_balance) {
                        builder.centerText(`Available Balance: ${saleData.customer_loyalty_balance} pts`);
                    }
                }

                // 7. QR Code / Barcode
                if (settings.thermal_print_barcode !== false && saleData.invoice_number) {
                    builder.feed(1);
                    builder.barcode128(saleData.invoice_number);
                }

                if (saleData.qr_url || saleData.tims_verification_url) {
                    builder.feed(1);
                    builder.qrCode(saleData.tims_verification_url || saleData.qr_url);
                }

                // 8. Footer
                builder.dashedDivider();
                const footerNotice = settings.receipt_footer || 'THANK YOU FOR YOUR BUSINESS!';
                builder.centerText(footerNotice, true);
                if (settings.website) {
                    builder.centerText(settings.website);
                }
                builder.centerText('Powered by Marid POS');

                // 9. Cut paper
                builder.cut(autoCut);
            }

            const rawBytes = builder.build();
            return await this.sendRawBuffer(rawBytes);
        }

        /**
         * Generate and print Z-Report from report data
         */
        async printZReport(zData, settings = {}) {
            const paperWidth = parseInt(settings.thermal_receipt_width || 80, 10);
            const autoCut = settings.thermal_auto_cut !== false;
            const builder = new ESCBuilder(paperWidth);

            builder.init();

            // Header
            builder.centerText(settings.shop_name || 'STORE NAME', true, 'double');
            builder.centerText('*** END OF DAY Z-REPORT ***', true);
            if (zData.branch_name) builder.centerText(`Branch: ${zData.branch_name}`);
            builder.doubleDivider();

            // Metadata
            builder.row('Z-Report #:', String(zData.z_number || '-'));
            builder.row('Date:', String(zData.generated_at || new Date().toLocaleString()));
            builder.row('Generated By:', String(zData.generated_by || '-'));
            builder.dashedDivider();

            // Sales Summary
            builder.centerText('FINANCIAL SUMMARY', true);
            builder.row('Total Transactions:', String(zData.total_transactions || 0));
            builder.row('Gross Sales:', `KES ${parseFloat(zData.gross_sales || 0).toFixed(2)}`);
            builder.row('Discounts:', `-KES ${parseFloat(zData.total_discounts || 0).toFixed(2)}`);
            builder.row('VAT Collected:', `KES ${parseFloat(zData.vat_collected || 0).toFixed(2)}`);
            builder.doubleDivider();
            builder.bold(true);
            builder.row('NET SALES:', `KES ${parseFloat(zData.net_sales || 0).toFixed(2)}`);
            builder.bold(false);

            // Payments Breakdown
            if (zData.payments_breakdown && zData.payments_breakdown.length > 0) {
                builder.dashedDivider();
                builder.centerText('PAYMENTS BREAKDOWN', true);
                zData.payments_breakdown.forEach(p => {
                    builder.row(p.method, `KES ${parseFloat(p.amount).toFixed(2)}`);
                });
            }

            // Cash Drawer Status
            if (zData.cash_opening !== undefined) {
                builder.dashedDivider();
                builder.centerText('CASH DRAWER RECONCILIATION', true);
                builder.row('Opening Float:', `KES ${parseFloat(zData.cash_opening || 0).toFixed(2)}`);
                builder.row('Cash Sales:', `KES ${parseFloat(zData.cash_sales || 0).toFixed(2)}`);
                builder.row('Expected Cash:', `KES ${parseFloat(zData.expected_cash || 0).toFixed(2)}`);
                builder.row('Actual Counted:', `KES ${parseFloat(zData.counted_cash || 0).toFixed(2)}`);
                const diff = parseFloat(zData.variance || 0);
                builder.row('Variance:', `KES ${diff >= 0 ? '+' : ''}${diff.toFixed(2)}`);
            }

            builder.dashedDivider();
            builder.centerText('*** END OF REPORT ***', true);
            builder.centerText('Marid POS System');
            builder.cut(autoCut);

            const rawBytes = builder.build();
            return await this.sendRawBuffer(rawBytes);
        }

        /**
         * Test print receipt
         */
        async printTestReceipt(paperWidth = 80) {
            const builder = new ESCBuilder(paperWidth);
            builder.init();
            builder.centerText('MARID POS', true, 'double');
            builder.centerText('BLUETOOTH PRINTER TEST', true);
            builder.doubleDivider();
            builder.row('Paper Size:', `${paperWidth}mm Thermal Roll`);
            builder.row('Connection:', 'Direct Web Bluetooth GATT');
            builder.row('Status:', 'ONLINE & READY');
            builder.row('Test Time:', new Date().toLocaleTimeString());
            builder.dashedDivider();
            builder.centerText('Alignment & Style Tests:', true);
            builder.align('left').line('Left aligned standard text');
            builder.align('center').line('Center aligned text');
            builder.align('right').line('Right aligned text');
            builder.align('left');
            builder.bold(true).line('Bold Text Enabled').bold(false);
            builder.invert(true).centerText(' INVERTED WHITE ON BLACK ', true).invert(false);
            builder.dashedDivider();
            builder.centerText('Code 128 Barcode Test:');
            builder.barcode128('TEST-PRINTER-OK');
            builder.dashedDivider();
            builder.centerText('Bluetooth 1-Click Print Working!');
            builder.cut(true);

            return await this.sendRawBuffer(builder.build());
        }

        // ==========================================
        // 4. Event Dispatcher & Toast Helper
        // ==========================================
        _notifyStatus(status, message) {
            const detail = {
                status, // 'connected' | 'disconnected' | 'connecting' | 'printing' | 'error'
                message,
                deviceName: this.getDeviceName(),
                isConnected: this.isConnected()
            };

            window.dispatchEvent(new CustomEvent('pos-bluetooth-status', { detail }));

            // Update any UI badge if present on screen
            this._updateUIBadges(detail);
        }

        _onDisconnected(event) {
            console.warn('[Web Bluetooth] Device disconnected:', event);
            this.characteristic = null;
            this.server = null;
            this._notifyStatus('disconnected', `Printer ${this.lastDeviceName || ''} disconnected`);
        }

        _updateUIBadges(detail) {
            const badges = document.querySelectorAll('.bt-printer-badge');
            badges.forEach(badge => {
                if (detail.status === 'connected') {
                    badge.classList.remove('badge-secondary', 'badge-danger', 'badge-warning', 'bg-secondary', 'bg-danger', 'bg-warning');
                    badge.classList.add('badge-success', 'bg-success');
                    badge.innerHTML = `<i class="bi bi-bluetooth me-1"></i> ${detail.deviceName}`;
                    badge.title = `Bluetooth printer connected: ${detail.deviceName}. Click to manage.`;
                } else if (detail.status === 'connecting' || detail.status === 'printing') {
                    badge.classList.remove('badge-secondary', 'badge-success', 'badge-danger', 'bg-secondary', 'bg-success', 'bg-danger');
                    badge.classList.add('badge-warning', 'bg-warning', 'text-dark');
                    badge.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> ${detail.message}`;
                } else {
                    badge.classList.remove('badge-success', 'badge-warning', 'bg-success', 'bg-warning');
                    badge.classList.add('badge-secondary', 'bg-secondary');
                    badge.innerHTML = `<i class="bi bi-bluetooth me-1"></i> Connect Bluetooth`;
                    badge.title = 'No Bluetooth printer connected. Click to pair.';
                }
            });
        }
    }

    // Expose global instance
    window.ESCBuilder = ESCBuilder;
    window.BluetoothPrinter = new WebBluetoothPrinterManager();

    // Auto-initialize UI badge listeners on DOM ready
    document.addEventListener('DOMContentLoaded', () => {
        window.BluetoothPrinter._updateUIBadges({
            status: window.BluetoothPrinter.isConnected() ? 'connected' : 'disconnected',
            deviceName: window.BluetoothPrinter.getDeviceName(),
            message: ''
        });
    });

})(window);
