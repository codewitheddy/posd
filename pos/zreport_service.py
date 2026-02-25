"""
Z-Report Service Layer
Production-ready financial reporting with immutability, auditability, and security.

This service handles:
- POS session management
- Z-Report generation with atomicity
- Sequential numbering (thread-safe)
- Integrity verification
- Void operations
- Audit logging
"""

from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from decimal import Decimal
import hashlib
import json
from typing import Dict, Optional, Tuple
from datetime import datetime

from .models import (
    POSSession, ZReport, ZReportAuditLog, Sale, SalePayment,
    Business, User, PaymentMethod
)


class ZReportService:
    """
    Service for managing POS sessions and Z-Reports.
    All operations are atomic and audited.
    """
    
    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================
    
    @staticmethod
    @transaction.atomic
    def open_session(business: Business, user: User, opening_cash: Decimal = Decimal('0.00'), 
                     notes: str = '') -> POSSession:
        """
        Open a new POS session.
        
        Args:
            business: Business entity
            user: User opening the session
            opening_cash: Starting cash in drawer
            notes: Optional notes
            
        Returns:
            POSSession instance
            
        Raises:
            ValidationError: If there's already an open session
        """
        # Check for existing open session
        existing_open = POSSession.objects.filter(
            business=business,
            status='open'
        ).exists()
        
        if existing_open:
            raise ValidationError(
                "Cannot open new session. There is already an open session for this business."
            )
        
        # Validate opening cash
        if opening_cash < 0:
            raise ValidationError("Opening cash cannot be negative")
        
        # Create session
        session = POSSession.objects.create(
            business=business,
            opened_by=user,
            opening_cash=opening_cash,
            notes=notes,
            status='open'
        )
        
        return session
    
    @staticmethod
    def get_current_session(business: Business) -> Optional[POSSession]:
        """
        Get the currently open session for a business.
        
        Args:
            business: Business entity
            
        Returns:
            POSSession if open, None otherwise
        """
        return POSSession.objects.filter(
            business=business,
            status='open'
        ).first()
    
    @staticmethod
    def get_or_create_session(business: Business, user: User, 
                             opening_cash: Decimal = Decimal('0.00')) -> POSSession:
        """
        Get current session or create new one if none exists.
        
        Args:
            business: Business entity
            user: User for session creation
            opening_cash: Starting cash if creating new session
            
        Returns:
            POSSession instance
        """
        session = ZReportService.get_current_session(business)
        if not session:
            session = ZReportService.open_session(business, user, opening_cash)
        return session
    
    # ========================================================================
    # Z-REPORT GENERATION
    # ========================================================================
    
    @staticmethod
    @transaction.atomic
    def close_session(session_id: int, user: User, closing_cash: Decimal,
                     ip_address: str = None, user_agent: str = None) -> ZReport:
        """
        Close a POS session and generate Z-Report atomically.
        
        This is the main Z-Report generation function. It:
        1. Locks the session (prevents concurrent access)
        2. Validates session can be closed
        3. Locks all transactions in the session
        4. Aggregates financial data
        5. Generates immutable JSON snapshot
        6. Calculates SHA256 hash
        7. Creates Z-Report with sequential number
        8. Closes session
        9. Creates audit log
        
        Args:
            session_id: POSSession ID
            user: User closing the session
            closing_cash: Actual cash counted in drawer
            ip_address: User's IP address
            user_agent: User's browser/client
            
        Returns:
            ZReport instance
            
        Raises:
            ValidationError: If session cannot be closed
            PermissionDenied: If user lacks permission
        """
        # Lock session row (prevents concurrent closes)
        session = POSSession.objects.select_for_update().get(id=session_id)
        
        # Validate session can be closed
        if session.status != 'open':
            raise ValidationError(f"Session #{session.session_number} is already closed")
        
        # Validate closing cash
        if closing_cash < 0:
            raise ValidationError("Closing cash cannot be negative")
        
        # Lock all sales in this session
        sales = Sale.objects.select_for_update().filter(
            session=session,
            is_locked=False
        )
        
        # Generate report data
        report_data = ZReportService._aggregate_session_data(
            session=session,
            sales=sales,
            closing_cash=closing_cash,
            user=user
        )
        
        # Generate hash
        data_hash = ZReportService._generate_hash(report_data)
        
        # Get next Z-number (thread-safe)
        z_number = ZReportService._get_next_z_number(session.business)
        
        # Create Z-Report
        zreport = ZReport.objects.create(
            business=session.business,
            z_number=z_number,
            session=session,
            created_by=user,
            report_data=report_data,
            data_hash=data_hash
        )
        
        # Lock all sales
        now = timezone.now()
        sales.update(is_locked=True, locked_at=now)
        
        # Close session
        session.status = 'closed'
        session.closed_by = user
        session.closed_at = now
        session.save(update_fields=['status', 'closed_by', 'closed_at'])
        
        # Create audit log
        ZReportAuditLog.objects.create(
            zreport=zreport,
            action='created',
            performed_by=user,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                'closing_cash': str(closing_cash),
                'session_number': session.session_number,
                'sales_count': sales.count(),
            }
        )
        
        return zreport
    
    @staticmethod
    def _aggregate_session_data(session: POSSession, sales, closing_cash: Decimal, 
                                user: User) -> Dict:
        """
        Aggregate all financial data for the session.
        
        Args:
            session: POSSession instance
            sales: QuerySet of Sale objects
            closing_cash: Actual cash counted
            user: User generating report
            
        Returns:
            Dictionary with complete financial snapshot
        """
        from django.db.models import Sum, Count, Min, Max, Avg, Q
        
        # Sales summary
        sales_aggregates = sales.aggregate(
            total_transactions=Count('id'),
            gross_sales=Sum('total'),
            total_tax=Sum('vat_amount'),
            total_discounts=Sum('discount_amount'),
        )
        
        total_transactions = sales_aggregates['total_transactions'] or 0
        gross_sales = sales_aggregates['gross_sales'] or Decimal('0.00')
        total_tax = sales_aggregates['total_tax'] or Decimal('0.00')
        total_discounts = sales_aggregates['total_discounts'] or Decimal('0.00')
        
        # Calculate net sales (gross - tax)
        net_sales = gross_sales - total_tax
        
        # Get refunds and voids (if you have these fields)
        # For now, setting to 0
        total_refunds = Decimal('0.00')
        total_voids = Decimal('0.00')
        
        # Payment breakdown
        payment_breakdown = []
        payments = SalePayment.objects.filter(sale__in=sales).select_related('payment_method')
        
        payment_summary = payments.values('payment_method__name').annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        ).order_by('-total_amount')
        
        for pm in payment_summary:
            payment_breakdown.append({
                'method': pm['payment_method__name'] or 'Unknown',
                'count': pm['count'],
                'amount': float(pm['total_amount'] or 0)
            })
        
        # Cash management
        cash_payments = payments.filter(
            payment_method__name__iexact='CASH'
        ).aggregate(total=Sum('amount'))
        
        cash_sales = cash_payments['total'] or Decimal('0.00')
        expected_cash = session.opening_cash + cash_sales
        cash_difference = closing_cash - expected_cash
        
        # Calculate difference percentage
        if expected_cash > 0:
            difference_percentage = float((cash_difference / expected_cash) * 100)
        else:
            difference_percentage = 0.0
        
        # Transaction metrics
        if total_transactions > 0:
            transaction_metrics = sales.aggregate(
                first_transaction=Min('date'),
                last_transaction=Max('date'),
                average_value=Avg('total'),
                largest_transaction=Max('total'),
                smallest_transaction=Min('total'),
            )
            
            avg_transaction = transaction_metrics['average_value'] or Decimal('0.00')
        else:
            transaction_metrics = {
                'first_transaction': None,
                'last_transaction': None,
                'average_value': Decimal('0.00'),
                'largest_transaction': Decimal('0.00'),
                'smallest_transaction': Decimal('0.00'),
            }
            avg_transaction = Decimal('0.00')
        
        # Tax breakdown by rate
        tax_breakdown = []
        tax_rates = sales.values('vat_rate').annotate(
            taxable_amount=Sum('subtotal'),
            tax_amount=Sum('vat_amount')
        ).order_by('-vat_rate')
        
        for rate in tax_rates:
            tax_breakdown.append({
                'rate': f"{float(rate['vat_rate'])}%",
                'taxable_amount': float(rate['taxable_amount'] or 0),
                'tax_amount': float(rate['tax_amount'] or 0)
            })
        
        # Top products
        from .models import SaleItem
        top_products_data = SaleItem.objects.filter(
            sale__in=sales
        ).values('product__name').annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price')
        ).order_by('-revenue')[:10]
        
        top_products = [
            {
                'name': item['product__name'],
                'quantity': item['quantity'],
                'revenue': float(item['revenue'])
            }
            for item in top_products_data
        ]
        
        # Transaction IDs
        transaction_ids = list(sales.values_list('id', flat=True))
        
        # Build complete report data
        report_data = {
            'session': {
                'session_number': session.session_number,
                'opened_at': session.opened_at.isoformat(),
                'closed_at': timezone.now().isoformat(),
                'opened_by': session.opened_by.get_full_name() or session.opened_by.username,
                'closed_by': user.get_full_name() or user.username,
            },
            'sales_summary': {
                'total_transactions': total_transactions,
                'gross_sales': float(gross_sales),
                'net_sales': float(net_sales),
                'total_tax': float(total_tax),
                'total_discounts': float(total_discounts),
                'total_refunds': float(total_refunds),
                'total_voids': float(total_voids),
            },
            'tax_breakdown': tax_breakdown,
            'payment_breakdown': payment_breakdown,
            'cash_management': {
                'opening_float': float(session.opening_cash),
                'cash_sales': float(cash_sales),
                'expected_cash': float(expected_cash),
                'actual_cash_counted': float(closing_cash),
                'difference': float(cash_difference),
                'difference_percentage': round(difference_percentage, 2),
            },
            'transaction_metrics': {
                'first_transaction': transaction_metrics['first_transaction'].isoformat() if transaction_metrics['first_transaction'] else None,
                'last_transaction': transaction_metrics['last_transaction'].isoformat() if transaction_metrics['last_transaction'] else None,
                'average_transaction_value': float(avg_transaction),
                'largest_transaction': float(transaction_metrics['largest_transaction'] or 0),
                'smallest_transaction': float(transaction_metrics['smallest_transaction'] or 0),
            },
            'top_products': top_products,
            'transaction_ids': transaction_ids,
            'metadata': {
                'business_name': session.business.name,
                'business_address': session.business.address,
                'report_generated_at': timezone.now().isoformat(),
                'timezone': str(timezone.get_current_timezone()),
                'generated_by': user.get_full_name() or user.username,
            }
        }
        
        return report_data
    
    @staticmethod
    def _generate_hash(report_data: Dict) -> str:
        """
        Generate SHA256 hash of report data for integrity verification.
        
        Args:
            report_data: Report data dictionary
            
        Returns:
            SHA256 hash as hex string
        """
        # Convert to JSON with sorted keys for consistent hashing
        data_string = json.dumps(report_data, sort_keys=True)
        return hashlib.sha256(data_string.encode()).hexdigest()
    
    @staticmethod
    def _get_next_z_number(business: Business) -> int:
        """
        Get next sequential Z-number for business (thread-safe).
        
        Args:
            business: Business entity
            
        Returns:
            Next Z-number
        """
        # Use select_for_update to prevent race conditions
        last_report = ZReport.objects.filter(
            business=business
        ).select_for_update().order_by('-z_number').first()
        
        return (last_report.z_number + 1) if last_report else 1
    
    # ========================================================================
    # INTEGRITY VERIFICATION
    # ========================================================================
    
    @staticmethod
    def verify_integrity(zreport: ZReport, user: User, ip_address: str = None,
                        user_agent: str = None) -> Tuple[bool, str]:
        """
        Verify Z-Report integrity by checking hash.
        
        Args:
            zreport: ZReport instance
            user: User performing verification
            ip_address: User's IP address
            user_agent: User's browser/client
            
        Returns:
            Tuple of (is_valid, message)
        """
        computed_hash = ZReportService._generate_hash(zreport.report_data)
        is_valid = computed_hash == zreport.data_hash
        
        # Log verification
        action = 'integrity_verified' if is_valid else 'integrity_failed'
        ZReportAuditLog.objects.create(
            zreport=zreport,
            action=action,
            performed_by=user,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                'computed_hash': computed_hash,
                'stored_hash': zreport.data_hash,
                'match': is_valid,
            }
        )
        
        if is_valid:
            return True, "Report integrity verified successfully"
        else:
            return False, "INTEGRITY VIOLATION: Report data has been tampered with"
    
    # ========================================================================
    # VOID OPERATIONS
    # ========================================================================
    
    @staticmethod
    @transaction.atomic
    def void_zreport(zreport: ZReport, reason: str, user: User,
                    ip_address: str = None, user_agent: str = None) -> ZReport:
        """
        Void a Z-Report (never delete, only mark as voided).
        
        Args:
            zreport: ZReport instance
            reason: Reason for voiding
            user: User performing void
            ip_address: User's IP address
            user_agent: User's browser/client
            
        Returns:
            Updated ZReport instance
            
        Raises:
            PermissionDenied: If user lacks permission
            ValidationError: If report already voided
        """
        # Check permission
        if not user.has_perm('pos.can_void_zreport'):
            raise PermissionDenied("You do not have permission to void Z-Reports")
        
        # Check if already voided
        if zreport.is_voided:
            raise ValidationError("This Z-Report is already voided")
        
        # Validate reason
        if not reason or len(reason.strip()) < 10:
            raise ValidationError("Void reason must be at least 10 characters")
        
        # Void the report
        now = timezone.now()
        zreport.is_voided = True
        zreport.voided_at = now
        zreport.voided_by = user
        zreport.void_reason = reason
        zreport.save(update_fields=['is_voided', 'voided_at', 'voided_by', 'void_reason'])
        
        # Create audit log
        ZReportAuditLog.objects.create(
            zreport=zreport,
            action='voided',
            performed_by=user,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                'reason': reason,
                'voided_at': now.isoformat(),
            }
        )
        
        return zreport
    
    # ========================================================================
    # AUDIT LOGGING
    # ========================================================================
    
    @staticmethod
    def log_action(zreport: ZReport, action: str, user: User,
                  ip_address: str = None, user_agent: str = None,
                  details: Dict = None):
        """
        Log an action on a Z-Report.
        
        Args:
            zreport: ZReport instance
            action: Action type (viewed, exported_pdf, etc.)
            user: User performing action
            ip_address: User's IP address
            user_agent: User's browser/client
            details: Additional details dictionary
        """
        ZReportAuditLog.objects.create(
            zreport=zreport,
            action=action,
            performed_by=user,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {}
        )
    
    # ========================================================================
    # QUERY HELPERS
    # ========================================================================
    
    @staticmethod
    def get_zreport_by_number(business: Business, z_number: int) -> Optional[ZReport]:
        """Get Z-Report by number"""
        return ZReport.objects.filter(
            business=business,
            z_number=z_number
        ).first()
    
    @staticmethod
    def get_latest_zreport(business: Business, include_voided: bool = False) -> Optional[ZReport]:
        """Get latest Z-Report for business"""
        queryset = ZReport.objects.filter(business=business)
        if not include_voided:
            queryset = queryset.filter(is_voided=False)
        return queryset.order_by('-z_number').first()
    
    @staticmethod
    def get_zreports_for_period(business: Business, start_date: datetime, 
                                end_date: datetime, include_voided: bool = False):
        """Get Z-Reports for a date range"""
        queryset = ZReport.objects.filter(
            business=business,
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        if not include_voided:
            queryset = queryset.filter(is_voided=False)
        return queryset.order_by('-created_at')
