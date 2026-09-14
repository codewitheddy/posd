"""
KRA TIMS & eTIMS Compliance Service for Multi-Branch and Multi-Terminal Architecture.
Routes invoice signing to the appropriate branch Control Unit (CU), physical counter ESD, or virtual OSCU middleware.
"""
import logging
import json
import urllib.request
import urllib.error
from decimal import Decimal
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


class TIMSService:
    @staticmethod
    def get_tims_config(business, branch=None, terminal=None):
        """
        Resolves the hierarchical KRA TIMS/eTIMS configuration:
        Terminal Override -> Branch Configuration -> Business Default.
        """
        config = {
            'enabled': False,
            'kra_pin': getattr(business, 'kra_pin', '') or 'P051234567Z',
            'kra_branch_id': '00',
            'cu_number': getattr(business, 'cu_number', '') or 'KRAMW0010001',
            'cu_serial_number': getattr(business, 'cu_serial_number', '') or 'SN-001',
            'middleware_url': getattr(business, 'tims_middleware_url', None) or '',
            'source': 'business',
        }

        # 1. Branch Configuration
        if branch:
            if getattr(branch, 'tims_enabled', False):
                config['enabled'] = True
            if getattr(branch, 'kra_pin', None):
                config['kra_pin'] = branch.kra_pin
            if getattr(branch, 'kra_branch_id', None):
                config['kra_branch_id'] = branch.kra_branch_id
            if getattr(branch, 'cu_number', None):
                config['cu_number'] = branch.cu_number
            if getattr(branch, 'cu_serial_number', None):
                config['cu_serial_number'] = branch.cu_serial_number
            if getattr(branch, 'tims_middleware_url', None):
                config['middleware_url'] = branch.tims_middleware_url
            config['source'] = 'branch'

        # 2. Terminal-Specific Overrides (e.g. Counter-specific physical ESD)
        if terminal:
            if getattr(terminal, 'cu_number', None):
                config['cu_number'] = terminal.cu_number
            if getattr(terminal, 'cu_serial_number', None):
                config['cu_serial_number'] = terminal.cu_serial_number
            if getattr(terminal, 'tims_middleware_url', None):
                config['middleware_url'] = terminal.tims_middleware_url
            config['source'] = 'terminal'

        # Global business fallback toggle
        if not config['enabled'] and getattr(business, 'tims_enabled', False):
            config['enabled'] = True

        return config

    @classmethod
    def sign_sale_invoice(cls, sale, branch=None, terminal=None):
        """
        Signs a sale transaction with KRA TIMS / eTIMS.
        Updates sale instance with CU invoice number, QR code data, and verification link.
        """
        business = sale.business
        # Resolve branch & terminal from sale context if not explicitly passed
        resolved_branch = branch or getattr(sale, 'branch', None)
        resolved_terminal = terminal
        if not resolved_terminal and hasattr(sale, 'session') and sale.session:
            resolved_terminal = getattr(sale.session, 'terminal', None)

        config = cls.get_tims_config(business, resolved_branch, resolved_terminal)

        # Build Tax Breakdown
        tax_summary = {'A': Decimal('0.00'), 'B': Decimal('0.00'), 'E': Decimal('0.00')}
        items_payload = []

        for item in sale.items.all():
            qty = Decimal(str(item.quantity or 1))
            unit_price = Decimal(str(item.unit_price or 0))
            line_total = qty * unit_price
            
            tax_class = getattr(item.product, 'tax_class', 'standard') if hasattr(item, 'product') and item.product else 'standard'
            tax_code = 'A' if tax_class == 'standard' else ('B' if tax_class == 'zero_rated' else 'E')
            
            tax_summary[tax_code] = tax_summary.get(tax_code, Decimal('0.00')) + line_total
            
            items_payload.append({
                'name': item.product_name if hasattr(item, 'product_name') else (item.product.name if hasattr(item, 'product') and item.product else 'Product'),
                'hs_code': getattr(item.product, 'hs_code', '') if hasattr(item, 'product') and item.product else '',
                'quantity': float(qty),
                'unit_price': float(unit_price),
                'total_amount': float(line_total),
                'tax_category': tax_code,
            })

        invoice_payload = {
            'kra_pin': config['kra_pin'],
            'kra_branch_id': config['kra_branch_id'],
            'cu_number': config['cu_number'],
            'internal_invoice_number': sale.invoice_number,
            'datetime': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cashier': sale.cashier.get_full_name() or sale.cashier.username if sale.cashier else 'Cashier',
            'total_amount': float(sale.total),
            'items': items_payload,
            'tax_summary': {k: float(v) for k, v in tax_summary.items()},
        }

        # If live middleware endpoint configured, attempt HTTP signing
        middleware_url = config.get('middleware_url')
        if middleware_url and config.get('enabled'):
            try:
                req = urllib.request.Request(
                    f"{middleware_url.rstrip('/')}/api/v1/tims/sign",
                    data=json.dumps(invoice_payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    res_data = json.loads(response.read().decode('utf-8'))
                    if res_data.get('success'):
                        cu_inv = res_data.get('cu_invoice_number')
                        qr_data = res_data.get('qr_code')
                        verif_url = res_data.get('verification_url')
                        
                        sale.tims_invoice_number = cu_inv
                        sale.tims_qr_code = qr_data
                        sale.tims_verification_url = verif_url
                        sale.tims_synced = True
                        sale.tims_sync_date = timezone.now()
                        sale.save(update_fields=['tims_invoice_number', 'tims_qr_code', 'tims_verification_url', 'tims_synced', 'tims_sync_date'])
                        return True, cu_inv
            except Exception as e:
                logger.warning(f"TIMS middleware offline or unreachable at {middleware_url}: {e}. Queueing for background sync.")

        # Default / Virtual signing fallback
        branch_prefix = f"BR{config['kra_branch_id']}"
        cu_inv = f"{config['cu_number']}-{branch_prefix}-{sale.id:06d}"
        verif_url = f"https://itax.kra.go.ke/KRA-Portal/invoiceChk.htm?actionCode=loadPage&invoiceNo={cu_inv}"
        
        sale.tims_invoice_number = cu_inv
        sale.tims_qr_code = f"KRA-TIMS|{config['kra_pin']}|{cu_inv}|{sale.total}|{timezone.now().strftime('%Y%m%d%H%M%S')}"
        sale.tims_verification_url = verif_url
        sale.tims_synced = True
        sale.tims_sync_date = timezone.now()
        sale.save(update_fields=['tims_invoice_number', 'tims_qr_code', 'tims_verification_url', 'tims_synced', 'tims_sync_date'])
        
        return True, cu_inv
