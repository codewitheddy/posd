"""
Email notification service for POS system
Handles sending emails for purchase orders, payments, GRNs, etc.
"""

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails with templates and logging"""
    
    @staticmethod
    def send_email(
        template_type,
        recipient,
        context,
        business=None,
        subject=None,
        html_body=None,
        text_body=None,
        attachments=None
    ):
        """
        Send email with template or custom content
        
        Args:
            template_type: Type of email (for logging)
            recipient: Email address or list of addresses
            context: Dictionary of template variables
            business: Business instance (optional)
            subject: Email subject (if not using template)
            html_body: HTML body (if not using template)
            text_body: Plain text body (if not using template)
            attachments: List of (filename, content, mimetype) tuples
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        from .models import EmailLog, EmailTemplate, BusinessEmailSettings
        
        # Convert single recipient to list
        recipients = [recipient] if isinstance(recipient, str) else recipient
        
        # Check if business has email settings
        email_settings = None
        if business:
            try:
                email_settings = BusinessEmailSettings.objects.get(business=business)
            except BusinessEmailSettings.DoesNotExist:
                pass
        
        # Get template if not provided
        if not subject or not html_body:
            template = EmailService._get_template(template_type, business)
            if template:
                subject = template.subject.format(**context)
                html_body = template.body_html.format(**context)
                text_body = template.body_text.format(**context)
        
        # Get from email
        from_email = settings.DEFAULT_FROM_EMAIL
        if email_settings and email_settings.from_email:
            from_email = email_settings.from_email
        
        # Create email log entry
        log_entry = EmailLog.objects.create(
            business=business,
            template_type=template_type,
            recipient=', '.join(recipients),
            subject=subject,
            status='pending'
        )
        
        try:
            # Create email message
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_body or 'Please view this email in HTML format.',
                from_email=from_email,
                to=recipients
            )
            
            # Add HTML alternative
            if html_body:
                email.attach_alternative(html_body, "text/html")
            
            # Add attachments
            if attachments:
                for filename, content, mimetype in attachments:
                    email.attach(filename, content, mimetype)
            
            # Send email
            email.send(fail_silently=False)
            
            # Update log
            log_entry.status = 'sent'
            log_entry.sent_at = timezone.now()
            log_entry.save()
            
            logger.info(f"Email sent: {template_type} to {', '.join(recipients)}")
            return True
            
        except Exception as e:
            # Update log with error
            log_entry.status = 'failed'
            log_entry.error_message = str(e)
            log_entry.save()
            
            logger.error(f"Failed to send email: {template_type} to {', '.join(recipients)}. Error: {str(e)}")
            return False
    
    @staticmethod
    def _get_template(template_type, business=None):
        """Get email template for business or default"""
        from .models import EmailTemplate
        
        if business:
            template = EmailTemplate.objects.filter(
                business=business,
                template_type=template_type,
                is_active=True
            ).first()
            if template:
                return template
        
        # Return None - will use default templates
        return None
    
    # ============================================
    # PURCHASE ORDER EMAILS
    # ============================================
    
    @staticmethod
    def send_purchase_order(purchase):
        """Send purchase order to supplier"""
        from .models import BusinessEmailSettings
        
        # Check if supplier has email
        if not purchase.supplier.email:
            logger.warning(f"Purchase {purchase.purchase_number}: Supplier has no email")
            return False
        
        # Check if business wants to send purchase orders
        try:
            email_settings = BusinessEmailSettings.objects.get(business=purchase.business)
            if not email_settings.send_purchase_orders:
                return False
        except BusinessEmailSettings.DoesNotExist:
            pass  # Default is to send
        
        # Build items table
        items_html = ""
        for item in purchase.items.all():
            items_html += f"""
            <tr>
                <td>{item.product.name}</td>
                <td style="text-align: right;">{item.quantity}</td>
                <td style="text-align: right;">KES {item.unit_cost:,.2f}</td>
                <td style="text-align: right;">KES {item.total_cost:,.2f}</td>
            </tr>
            """
        
        context = {
            'purchase_number': purchase.purchase_number,
            'supplier_name': purchase.supplier.name,
            'business_name': purchase.business.name,
            'order_date': purchase.date.strftime('%d/%m/%Y') if hasattr(purchase.date, 'strftime') else str(purchase.date),
            'expected_date': purchase.expected_delivery.strftime('%d/%m/%Y') if purchase.expected_delivery and hasattr(purchase.expected_delivery, 'strftime') else (str(purchase.expected_delivery) if purchase.expected_delivery else 'TBD'),
            'total_amount': f'KES {purchase.total_amount:,.2f}',
            'items_html': items_html,
        }
        
        subject = f"Purchase Order {purchase.purchase_number} from {purchase.business.name}"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background: #f8f9fa; font-weight: bold; }}
                .footer {{ padding: 20px; background: #f8f9fa; text-align: center; font-size: 12px; color: #666; }}
                .total {{ font-size: 18px; font-weight: bold; color: #007bff; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Purchase Order: {context['purchase_number']}</h2>
            </div>
            <div class="content">
                <p>Dear {context['supplier_name']},</p>
                <p>We would like to place the following order:</p>
                
                <p><strong>Order Date:</strong> {context['order_date']}<br>
                <strong>Expected Delivery:</strong> {context['expected_date']}</p>
                
                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th style="text-align: right;">Quantity</th>
                            <th style="text-align: right;">Unit Price</th>
                            <th style="text-align: right;">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {context['items_html']}
                    </tbody>
                </table>
                
                <p class="total">Total Amount: {context['total_amount']}</p>
                
                <p>Please confirm receipt of this order and advise on delivery schedule.</p>
                
                <p>Best regards,<br><strong>{context['business_name']}</strong></p>
            </div>
            <div class="footer">
                <p>This is an automated email from {context['business_name']} POS System</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
Purchase Order: {context['purchase_number']}

Dear {context['supplier_name']},

We would like to place the following order:

Order Date: {context['order_date']}
Expected Delivery: {context['expected_date']}

Total Amount: {context['total_amount']}

Please confirm receipt of this order and advise on delivery schedule.

Best regards,
{context['business_name']}
        """
        
        return EmailService.send_email(
            template_type='purchase_order',
            recipient=purchase.supplier.email,
            context=context,
            business=purchase.business,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )
    
    # ============================================
    # PAYMENT CONFIRMATION EMAILS
    # ============================================
    
    @staticmethod
    def send_payment_confirmation(payment):
        """Send payment confirmation to supplier"""
        from .models import BusinessEmailSettings
        
        # Check if supplier has email
        if not payment.supplier.email:
            logger.warning(f"Payment {payment.payment_number}: Supplier has no email")
            return False
        
        # Check if business wants to send payment confirmations
        try:
            email_settings = BusinessEmailSettings.objects.get(business=payment.business)
            if not email_settings.send_payment_confirmations:
                return False
        except BusinessEmailSettings.DoesNotExist:
            pass  # Default is to send
        
        context = {
            'payment_number': payment.payment_number,
            'supplier_name': payment.supplier.name,
            'business_name': payment.business.name,
            'amount': f'KES {payment.amount:,.2f}',
            'payment_date': payment.payment_date.strftime('%d/%m/%Y'),
            'payment_method': payment.payment_method.name,
            'reference': payment.reference_number or 'N/A',
        }
        
        subject = f"Payment Confirmation - {payment.payment_number} from {payment.business.name}"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #28a745; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .payment-box {{ background: #f8f9fa; border-left: 4px solid #28a745; padding: 15px; margin: 20px 0; }}
                .amount {{ font-size: 24px; font-weight: bold; color: #28a745; }}
                .footer {{ padding: 20px; background: #f8f9fa; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Payment Confirmation</h2>
            </div>
            <div class="content">
                <p>Dear {context['supplier_name']},</p>
                <p>This is to confirm that we have processed a payment to your account.</p>
                
                <div class="payment-box">
                    <p><strong>Payment Number:</strong> {context['payment_number']}</p>
                    <p><strong>Payment Date:</strong> {context['payment_date']}</p>
                    <p><strong>Payment Method:</strong> {context['payment_method']}</p>
                    <p><strong>Reference:</strong> {context['reference']}</p>
                    <p class="amount">Amount: {context['amount']}</p>
                </div>
                
                <p>Please verify this payment in your records. If you have any questions, please contact us.</p>
                
                <p>Thank you for your continued partnership.</p>
                
                <p>Best regards,<br><strong>{context['business_name']}</strong></p>
            </div>
            <div class="footer">
                <p>This is an automated email from {context['business_name']} POS System</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
Payment Confirmation

Dear {context['supplier_name']},

This is to confirm that we have processed a payment to your account.

Payment Number: {context['payment_number']}
Payment Date: {context['payment_date']}
Payment Method: {context['payment_method']}
Reference: {context['reference']}
Amount: {context['amount']}

Please verify this payment in your records. If you have any questions, please contact us.

Thank you for your continued partnership.

Best regards,
{context['business_name']}
        """
        
        return EmailService.send_email(
            template_type='payment_confirmation',
            recipient=payment.supplier.email,
            context=context,
            business=payment.business,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )
    
    # ============================================
    # GRN NOTIFICATION EMAILS
    # ============================================
    
    @staticmethod
    def send_grn_notification(grn):
        """Send GRN notification to supplier"""
        from .models import BusinessEmailSettings
        
        # Check if supplier has email
        if not grn.supplier.email:
            logger.warning(f"GRN {grn.grn_number}: Supplier has no email")
            return False
        
        # Check if business wants to send GRN notifications
        try:
            email_settings = BusinessEmailSettings.objects.get(business=grn.business)
            if not email_settings.send_grn_notifications:
                return False
        except BusinessEmailSettings.DoesNotExist:
            pass  # Default is to send
        
        # Build items table
        items_html = ""
        for item in grn.items.all():
            items_html += f"""
            <tr>
                <td>{item.product.name}</td>
                <td style="text-align: right;">{item.quantity}</td>
                <td style="text-align: right;">KES {item.unit_cost:,.2f}</td>
                <td style="text-align: right;">KES {item.total_cost:,.2f}</td>
                <td>{item.item_notes if item.item_notes else '-'}</td>
            </tr>
            """
        
        # Get purchase number if related purchase exists
        purchase_number = grn.related_purchase.purchase_number if grn.related_purchase else 'N/A'
        
        context = {
            'grn_number': grn.grn_number,
            'supplier_name': grn.supplier.name,
            'business_name': grn.business.name,
            'purchase_number': purchase_number,
            'return_date': grn.return_date.strftime('%d/%m/%Y') if hasattr(grn.return_date, 'strftime') else str(grn.return_date),
            'total_amount': f'KES {grn.total_value:,.2f}',
            'reason': grn.get_return_reason_display(),
            'reason_details': grn.reason_details,
            'items_html': items_html,
            'status': grn.get_status_display(),
        }
        
        subject = f"Goods Return Note {grn.grn_number} - {grn.business.name}"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background: #f8f9fa; font-weight: bold; }}
                .footer {{ padding: 20px; background: #f8f9fa; text-align: center; font-size: 12px; color: #666; }}
                .alert {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Goods Return Note: {context['grn_number']}</h2>
            </div>
            <div class="content">
                <p>Dear {context['supplier_name']},</p>
                <p>We are returning the following items from Purchase Order {context['purchase_number']}:</p>
                
                <div class="alert">
                    <p><strong>Return Date:</strong> {context['return_date']}<br>
                    <strong>Status:</strong> {context['status']}<br>
                    <strong>Reason:</strong> {context['reason']}</p>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th style="text-align: right;">Quantity</th>
                            <th style="text-align: right;">Unit Price</th>
                            <th style="text-align: right;">Total</th>
                            <th>Reason</th>
                        </tr>
                    </thead>
                    <tbody>
                        {context['items_html']}
                    </tbody>
                </table>
                
                <p><strong>Total Return Amount: {context['total_amount']}</strong></p>
                
                <p>Please review this return and advise on the next steps for credit or replacement.</p>
                
                <p>Best regards,<br><strong>{context['business_name']}</strong></p>
            </div>
            <div class="footer">
                <p>This is an automated email from {context['business_name']} POS System</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
Goods Return Note: {context['grn_number']}

Dear {context['supplier_name']},

We are returning the following items from Purchase Order {context['purchase_number']}:

Return Date: {context['return_date']}
Status: {context['status']}
Reason: {context['reason']}

Total Return Amount: {context['total_amount']}

Please review this return and advise on the next steps for credit or replacement.

Best regards,
{context['business_name']}
        """
        
        return EmailService.send_email(
            template_type='grn',
            recipient=grn.supplier.email,
            context=context,
            business=grn.business,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )
    
    # ============================================
    # LICENSE EXPIRY REMINDERS
    # ============================================
    
    @staticmethod
    def send_license_expiry_reminder(business, days_remaining):
        """Send license expiry reminder to business admins"""
        from .models import BusinessEmailSettings
        
        # Get email settings
        try:
            email_settings = BusinessEmailSettings.objects.get(business=business)
            if not email_settings.send_license_reminders:
                return False
            recipients = email_settings.get_admin_emails()
            if not recipients:
                logger.warning(f"Business {business.name}: No admin emails configured")
                return False
        except BusinessEmailSettings.DoesNotExist:
            logger.warning(f"Business {business.name}: No email settings configured")
            return False
        
        context = {
            'business_name': business.name,
            'days_remaining': days_remaining,
            'expiry_date': business.license_expiry_date.strftime('%d/%m/%Y'),
        }
        
        subject = f"License Expiry Reminder - {business.name} ({days_remaining} days remaining)"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #ffc107; color: #333; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
                .footer {{ padding: 20px; background: #f8f9fa; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ License Expiry Reminder</h2>
            </div>
            <div class="content">
                <p>Dear {context['business_name']} Administrator,</p>
                
                <div class="warning">
                    <p><strong>Your POS license will expire in {context['days_remaining']} days!</strong></p>
                    <p><strong>Expiry Date:</strong> {context['expiry_date']}</p>
                </div>
                
                <p>To avoid service interruption, please renew your license before the expiry date.</p>
                
                <p>Contact your system administrator or support team to renew your license.</p>
                
                <p>Thank you for using our POS system.</p>
            </div>
            <div class="footer">
                <p>This is an automated reminder from POS System</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
License Expiry Reminder

Dear {context['business_name']} Administrator,

Your POS license will expire in {context['days_remaining']} days!

Expiry Date: {context['expiry_date']}

To avoid service interruption, please renew your license before the expiry date.

Contact your system administrator or support team to renew your license.

Thank you for using our POS system.
        """
        
        return EmailService.send_email(
            template_type='license_expiry',
            recipient=recipients,
            context=context,
            business=business,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )

    
    # ============================================
    # CUSTOMER SALE RECEIPT EMAILS
    # ============================================
    
    @staticmethod
    def send_sale_receipt(sale, customer_email=None):
        """Send sale receipt to customer"""
        from .models import BusinessEmailSettings
        
        # Use provided email or customer's email
        recipient_email = customer_email
        if not recipient_email and sale.customer:
            recipient_email = sale.customer.email
        
        if not recipient_email:
            logger.warning(f"Sale {sale.invoice_number}: No customer email provided")
            return False
        
        # Build items table
        items_html = ""
        for item in sale.items.all():
            items_html += f"""
            <tr>
                <td>{item.product.name}</td>
                <td style="text-align: right;">{item.quantity}</td>
                <td style="text-align: right;">KES {item.unit_price:,.2f}</td>
                <td style="text-align: right;">KES {item.total_price:,.2f}</td>
            </tr>
            """
        
        context = {
            'invoice_number': sale.invoice_number,
            'business_name': sale.business.name,
            'sale_date': sale.date.strftime('%d/%m/%Y %H:%M'),
            'customer_name': sale.customer.name if sale.customer else 'Valued Customer',
            'subtotal': f'KES {sale.subtotal:,.2f}',
            'vat_amount': f'KES {sale.vat_amount:,.2f}',
            'vat_rate': sale.vat_rate,
            'discount_amount': f'KES {sale.discount_amount:,.2f}' if sale.discount_amount > 0 else '',
            'total': f'KES {sale.total:,.2f}',
            'amount_paid': f'KES {sale.amount_paid:,.2f}',
            'change_given': f'KES {sale.change_given:,.2f}' if sale.change_given > 0 else '',
            'items_html': items_html,
        }
        
        subject = f"Receipt - {sale.invoice_number} from {sale.business.name}"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #28a745; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background: #f8f9fa; font-weight: bold; }}
                .totals {{ background: #f8f9fa; padding: 15px; margin: 20px 0; }}
                .footer {{ padding: 20px; background: #f8f9fa; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Thank You for Your Purchase!</h2>
                <p>Receipt: {context['invoice_number']}</p>
            </div>
            <div class="content">
                <p>Dear {context['customer_name']},</p>
                <p>Thank you for shopping with us. Here is your receipt:</p>
                
                <p><strong>Date:</strong> {context['sale_date']}<br>
                <strong>Invoice:</strong> {context['invoice_number']}</p>
                
                <table>
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th style="text-align: right;">Qty</th>
                            <th style="text-align: right;">Price</th>
                            <th style="text-align: right;">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {context['items_html']}
                    </tbody>
                </table>
                
                <div class="totals">
                    <p><strong>Subtotal (excl. VAT):</strong> {context['subtotal']}</p>
                    {'<p><strong>Discount:</strong> ' + context['discount_amount'] + '</p>' if context['discount_amount'] else ''}
                    <p><strong>VAT ({context['vat_rate']}%):</strong> {context['vat_amount']}</p>
                    <p style="font-size: 18px;"><strong>TOTAL:</strong> {context['total']}</p>
                    <p><strong>Amount Paid:</strong> {context['amount_paid']}</p>
                    {'<p><strong>Change:</strong> ' + context['change_given'] + '</p>' if context['change_given'] else ''}
                </div>
                
                <p>We appreciate your business and look forward to serving you again!</p>
                
                <p>Best regards,<br><strong>{context['business_name']}</strong></p>
            </div>
            <div class="footer">
                <p>This is an automated receipt from {context['business_name']}</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
Receipt: {context['invoice_number']}

Dear {context['customer_name']},

Thank you for shopping with us. Here is your receipt:

Date: {context['sale_date']}
Invoice: {context['invoice_number']}

Subtotal (excl. VAT): {context['subtotal']}
{'Discount: ' + context['discount_amount'] if context['discount_amount'] else ''}
VAT ({context['vat_rate']}%): {context['vat_amount']}
TOTAL: {context['total']}

Amount Paid: {context['amount_paid']}
{'Change: ' + context['change_given'] if context['change_given'] else ''}

We appreciate your business and look forward to serving you again!

Best regards,
{context['business_name']}
        """
        
        return EmailService.send_email(
            template_type='sale_receipt',
            recipient=recipient_email,
            context=context,
            business=sale.business,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )
    
    # ============================================
    # LOW STOCK ALERT EMAILS
    # ============================================
    
    @staticmethod
    def send_low_stock_alert(business, products):
        """Send low stock alert to managers"""
        from .models import BusinessEmailSettings
        
        # Get email settings
        try:
            email_settings = BusinessEmailSettings.objects.get(business=business)
            if not email_settings.send_low_stock_alerts:
                return False
            recipients = email_settings.get_manager_emails()
            if not recipients:
                # Fallback to admin emails
                recipients = email_settings.get_admin_emails()
            if not recipients:
                logger.warning(f"Business {business.name}: No manager/admin emails configured")
                return False
        except BusinessEmailSettings.DoesNotExist:
            logger.warning(f"Business {business.name}: No email settings configured")
            return False
        
        # Build products table
        products_html = ""
        for product in products:
            status_color = '#dc3545' if product.stock_quantity == 0 else '#ffc107'
            products_html += f"""
            <tr>
                <td>{product.name}</td>
                <td>{product.category.name if product.category else 'N/A'}</td>
                <td style="text-align: right; color: {status_color}; font-weight: bold;">{product.stock_quantity}</td>
                <td style="text-align: right;">{product.low_stock_threshold}</td>
                <td style="text-align: right;">KES {product.unit_price:,.2f}</td>
            </tr>
            """
        
        context = {
            'business_name': business.name,
            'product_count': len(products),
            'products_html': products_html,
        }
        
        subject = f"Low Stock Alert - {business.name} ({len(products)} products)"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #ffc107; color: #333; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background: #f8f9fa; font-weight: bold; }}
                .alert {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
                .footer {{ padding: 20px; background: #f8f9fa; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ Low Stock Alert</h2>
            </div>
            <div class="content">
                <div class="alert">
                    <p><strong>{context['product_count']} product(s) are running low on stock!</strong></p>
                </div>
                
                <p>The following products need to be restocked:</p>
                
                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Category</th>
                            <th style="text-align: right;">Current Stock</th>
                            <th style="text-align: right;">Threshold</th>
                            <th style="text-align: right;">Unit Price</th>
                        </tr>
                    </thead>
                    <tbody>
                        {context['products_html']}
                    </tbody>
                </table>
                
                <p>Please create purchase orders to restock these items.</p>
                
                <p>Best regards,<br><strong>{context['business_name']} POS System</strong></p>
            </div>
            <div class="footer">
                <p>This is an automated alert from {context['business_name']} POS System</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
Low Stock Alert - {context['business_name']}

{context['product_count']} product(s) are running low on stock!

Please create purchase orders to restock these items.

Best regards,
{context['business_name']} POS System
        """
        
        return EmailService.send_email(
            template_type='low_stock',
            recipient=recipients,
            context=context,
            business=business,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )
    
    # ============================================
    # DAILY SUMMARY EMAILS
    # ============================================
    
    @staticmethod
    def send_daily_summary(business, date=None):
        """Send daily sales summary to managers"""
        from .models import BusinessEmailSettings, Sale, Product
        from django.db.models import Sum, Count
        
        if date is None:
            date = timezone.now().date()
        
        # Get email settings
        try:
            email_settings = BusinessEmailSettings.objects.get(business=business)
            if not email_settings.send_daily_summaries:
                return False
            recipients = email_settings.get_admin_emails()
            if not recipients:
                logger.warning(f"Business {business.name}: No admin emails configured")
                return False
        except BusinessEmailSettings.DoesNotExist:
            logger.warning(f"Business {business.name}: No email settings configured")
            return False
        
        # Get sales data
        sales = Sale.objects.filter(
            business=business,
            date__date=date
        )
        
        total_sales = sales.aggregate(
            count=Count('id'),
            total=Sum('total'),
            subtotal=Sum('subtotal'),
            vat=Sum('vat_amount')
        )
        
        # Top products
        from .models import SaleItem
        top_products = SaleItem.objects.filter(
            sale__business=business,
            sale__date__date=date
        ).values('product__name').annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price')
        ).order_by('-revenue')[:5]
        
        # Build top products table
        top_products_html = ""
        for item in top_products:
            top_products_html += f"""
            <tr>
                <td>{item['product__name']}</td>
                <td style="text-align: right;">{item['quantity']}</td>
                <td style="text-align: right;">KES {item['revenue']:,.2f}</td>
            </tr>
            """
        
        if not top_products_html:
            top_products_html = "<tr><td colspan='3' style='text-align: center;'>No sales today</td></tr>"
        
        context = {
            'business_name': business.name,
            'date': date.strftime('%d/%m/%Y'),
            'sales_count': total_sales['count'] or 0,
            'total_revenue': f"KES {total_sales['total'] or 0:,.2f}",
            'subtotal': f"KES {total_sales['subtotal'] or 0:,.2f}",
            'vat': f"KES {total_sales['vat'] or 0:,.2f}",
            'top_products_html': top_products_html,
        }
        
        subject = f"Daily Summary - {business.name} ({date.strftime('%d/%m/%Y')})"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .summary-box {{ background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .stat {{ display: inline-block; margin: 10px 20px; }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #007bff; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background: #f8f9fa; font-weight: bold; }}
                .footer {{ padding: 20px; background: #f8f9fa; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Daily Sales Summary</h2>
                <p>{context['date']}</p>
            </div>
            <div class="content">
                <div class="summary-box">
                    <div class="stat">
                        <div>Total Sales</div>
                        <div class="stat-value">{context['sales_count']}</div>
                    </div>
                    <div class="stat">
                        <div>Total Revenue</div>
                        <div class="stat-value">{context['total_revenue']}</div>
                    </div>
                </div>
                
                <h3>Financial Summary</h3>
                <p><strong>Subtotal (excl. VAT):</strong> {context['subtotal']}<br>
                <strong>VAT:</strong> {context['vat']}<br>
                <strong>Total Revenue:</strong> {context['total_revenue']}</p>
                
                <h3>Top 5 Products</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th style="text-align: right;">Quantity Sold</th>
                            <th style="text-align: right;">Revenue</th>
                        </tr>
                    </thead>
                    <tbody>
                        {context['top_products_html']}
                    </tbody>
                </table>
                
                <p>Have a great day!</p>
                
                <p>Best regards,<br><strong>{context['business_name']} POS System</strong></p>
            </div>
            <div class="footer">
                <p>This is an automated daily summary from {context['business_name']} POS System</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
Daily Sales Summary - {context['date']}

Total Sales: {context['sales_count']}
Total Revenue: {context['total_revenue']}

Financial Summary:
Subtotal (excl. VAT): {context['subtotal']}
VAT: {context['vat']}
Total Revenue: {context['total_revenue']}

Have a great day!

Best regards,
{context['business_name']} POS System
        """
        
        return EmailService.send_email(
            template_type='daily_summary',
            recipient=recipients,
            context=context,
            business=business,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )
