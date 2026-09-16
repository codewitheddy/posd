"""
Cash Paid-Out / Till Expenses (Petty Cash Out) Services for Marid POS
Enforces retail cash expense controls:
1. Running drawer cash deduction (Opening Float + Cash Sales - Pickups - Paid Outs - Refunds).
2. Category threshold validation and mandatory supervisor PIN/Password authorization.
3. Post-payout receipt tracking, aging, and missing receipt chase-up alerts.
4. Informal vendor exception notes signed by managers.
5. Reversal transactions returning cash to till with audit preservation.
6. Automatic General Ledger Expense posting on receipt/exception confirmation.
7. Financial and compliance reports.
"""

from decimal import Decimal
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from pos.models import (
    Business, Branch, POSTerminal, POSSession, Shift, Sale, SalePayment, SaleReturn,
    ExpenseCategory, Expense, CashPickup, CashPaidOut, BankingAuditLog, ActivityLog,
    UserProfile, BusinessMembership
)
from pos.security_utils import verify_supervisor_credentials, is_user_supervisor


class CashPaidOutService:
    """
    Core business logic engine for Cash Paid-Outs / Till Expenses.
    """

    @staticmethod
    def get_drawer_cash_summary(business: Business, session: Optional[POSSession] = None,
                                 terminal: Optional[POSTerminal] = None,
                                 cashier: Optional[User] = None) -> Dict:
        """
        Calculates the real-time running cash total inside the register drawer:
          Opening Float
        + Cash Sales during Session
        - Confirmed Cash Pickups (Safe Drops)
        - Cash Paid-Outs (Till Expenses)
        - Cash Refunds / Returns
        = Current Drawer Cash
        """
        if not session:
            if terminal:
                session = POSSession.objects.filter(
                    business=business, terminal=terminal, status='open'
                ).order_by('-opened_at').first()
            elif cashier:
                session = POSSession.objects.filter(
                    business=business, status='open'
                ).filter(
                    Q(cashier=cashier) | Q(opened_by=cashier)
                ).order_by('-opened_at').first()
            else:
                session = POSSession.objects.filter(
                    business=business, status='open'
                ).order_by('-opened_at').first()

        opening_float = session.opening_cash if session else Decimal('0.00')

        # 1. Cash Sales in this session
        if session:
            cash_sales_qs = SalePayment.objects.filter(
                sale__business=business,
                sale__session=session
            ).filter(
                Q(payment_method__code__iexact='CASH') | Q(payment_method__name__icontains='cash')
            )
        elif terminal:
            cash_sales_qs = SalePayment.objects.filter(
                sale__business=business,
                sale__terminal=terminal,
                sale__date__date=timezone.localdate()
            ).filter(
                Q(payment_method__code__iexact='CASH') | Q(payment_method__name__icontains='cash')
            )
        else:
            cash_sales_qs = SalePayment.objects.filter(
                sale__business=business,
                sale__date__date=timezone.localdate()
            ).filter(
                Q(payment_method__code__iexact='CASH') | Q(payment_method__name__icontains='cash')
            )

        total_cash_sales = cash_sales_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        sales_count = cash_sales_qs.values('sale').distinct().count()

        # 2. Confirmed Cash Pickups
        pickups_qs = CashPickup.objects.filter(
            business=business,
            status__in=['confirmed', 'in_safe', 'banked']
        )
        if session:
            pickups_qs = pickups_qs.filter(session=session)
        elif terminal:
            pickups_qs = pickups_qs.filter(terminal=terminal, pickup_time__date=timezone.localdate())
        else:
            pickups_qs = pickups_qs.filter(pickup_time__date=timezone.localdate())

        total_pickups = pickups_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        pickups_count = pickups_qs.count()

        # 3. Active Cash Paid-Outs (Drawn from till, not petty cash fund)
        paid_outs_qs = CashPaidOut.objects.filter(
            business=business,
            is_petty_cash_fund=False,
            status__in=['paid_pending_receipt', 'confirmed', 'written_off']
        )
        if session:
            paid_outs_qs = paid_outs_qs.filter(session=session)
        elif terminal:
            paid_outs_qs = paid_outs_qs.filter(terminal=terminal, paid_out_time__date=timezone.localdate())
        else:
            paid_outs_qs = paid_outs_qs.filter(paid_out_time__date=timezone.localdate())

        total_paid_outs = paid_outs_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        paid_outs_count = paid_outs_qs.count()

        pending_receipts_qs = paid_outs_qs.filter(status='paid_pending_receipt')
        pending_receipts_count = pending_receipts_qs.count()
        pending_receipts_amount = pending_receipts_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # 4. Cash Returns / Refunds
        returns_qs = SaleReturn.objects.filter(original_sale__business=business)
        if session:
            returns_qs = returns_qs.filter(original_sale__session=session)
        else:
            returns_qs = returns_qs.filter(return_date__date=timezone.localdate())

        total_refunds = returns_qs.aggregate(t=Sum('total_refund'))['t'] or Decimal('0.00')

        # 5. Computed drawer cash
        current_drawer_cash = opening_float + total_cash_sales - total_pickups - total_paid_outs - total_refunds
        if current_drawer_cash < 0:
            current_drawer_cash = Decimal('0.00')

        return {
            'session': session,
            'terminal': terminal,
            'opening_float': opening_float,
            'total_cash_sales': total_cash_sales,
            'sales_count': sales_count,
            'total_pickups': total_pickups,
            'pickups_count': pickups_count,
            'total_paid_outs': total_paid_outs,
            'paid_outs_count': paid_outs_count,
            'pending_receipts_count': pending_receipts_count,
            'pending_receipts_amount': pending_receipts_amount,
            'total_refunds': total_refunds,
            'current_drawer_cash': current_drawer_cash,
            'recent_paid_outs': list(paid_outs_qs.select_related('category', 'requested_by', 'authorized_by').order_by('-paid_out_time')[:10])
        }

    @staticmethod
    @transaction.atomic
    def record_paid_out(business: Business, requested_by: User, category: ExpenseCategory,
                        amount: Decimal, payee: str, description: str,
                        supervisor_credential: Optional[str] = None,
                        session: Optional[POSSession] = None,
                        terminal: Optional[POSTerminal] = None,
                        branch: Optional[Branch] = None,
                        shift: Optional[Shift] = None,
                        is_petty_cash_fund: bool = False,
                        receipt_due_by: Optional[datetime] = None,
                        receipt_reference: str = '',
                        notes: str = '',
                        ip_address: str = None,
                        user_agent: str = None) -> CashPaidOut:
        """
        Records and locks a new Cash Paid-Out disbursement.
        Validates category approval thresholds, verifies supervisor credentials if required,
        and decreases running drawer cash immediately.
        """
        if not amount or amount <= Decimal('0.00'):
            raise ValidationError("Payout amount must be greater than zero.")

        payee_clean = str(payee or '').strip()
        if not payee_clean:
            raise ValidationError("Payee (recipient of cash) is required.")

        desc_clean = str(description or '').strip()
        if not desc_clean or len(desc_clean) < 3:
            raise ValidationError("A clear expense description/purpose (at least 3 characters) is required.")

        # Resolve branch & terminal from session if omitted
        if session:
            branch = branch or session.branch
            terminal = terminal or session.terminal

        # 1. Threshold & Authorization Check
        threshold = category.requires_manager_approval_above or Decimal('1000.00')
        requires_supervisor = amount > threshold

        authorized_by_user = None

        if requires_supervisor or supervisor_credential:
            if not supervisor_credential:
                raise ValidationError(
                    f"Amount of {category.business.name if category.business else 'KES'} {amount:.2f} "
                    f"exceeds the category approval limit of {threshold:.2f}. "
                    "Supervisor or Manager PIN/password is required to authorize this payout."
                )

            # Authenticate supervisor
            class _AuthRequest:
                def __init__(self, biz, user):
                    self.business = biz
                    self.user = user
                    self.content_type = 'text/plain'
                    self.body = None
                    self.POST = {}

            auth_req = _AuthRequest(business, requested_by)
            is_valid, sup_user, err_msg = verify_supervisor_credentials(auth_req, supervisor_credential)
            if not is_valid or not sup_user:
                raise ValidationError(err_msg or "Supervisor authorization failed. Invalid PIN or password.")
            
            # Prevent self-authorization if requested_by is a cashier operating till
            if not is_user_supervisor(requested_by, business) and sup_user.id == requested_by.id:
                raise ValidationError("Cashier cannot self-authorize payouts that exceed the manager threshold.")

            authorized_by_user = sup_user
        else:
            # Under threshold: requester can authorize if they have cashier/manager permissions
            authorized_by_user = requested_by

        # 2. Check Drawer Cash Availability (if taking from till)
        if not is_petty_cash_fund:
            drawer_summary = CashPaidOutService.get_drawer_cash_summary(
                business=business, session=session, terminal=terminal, cashier=requested_by
            )
            current_cash = drawer_summary['current_drawer_cash']
            if amount > current_cash:
                # If supervisor authorized, allow with note; otherwise block
                if not is_user_supervisor(authorized_by_user, business):
                    raise ValidationError(
                        f"Insufficient cash in register drawer. Current balance is KES {current_cash:.2f}, "
                        f"requested payout is KES {amount:.2f}."
                    )

        # 3. Monthly Budget Cap Check (Warning Log)
        if category.monthly_budget_cap:
            now = timezone.now()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_spend = CashPaidOut.objects.filter(
                business=business,
                category=category,
                paid_out_time__gte=month_start,
                status__in=['paid_pending_receipt', 'confirmed']
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            if month_spend + amount > category.monthly_budget_cap:
                budget_warning = (
                    f"Warning: Monthly budget cap of KES {category.monthly_budget_cap:.2f} "
                    f"for category '{category.name}' reached (Current spend: KES {month_spend + amount:.2f})."
                )
                notes = f"{notes}\n[Budget Cap Notice]: {budget_warning}".strip()

        # 4. Create CashPaidOut
        now = timezone.now()
        paid_out = CashPaidOut.objects.create(
            business=business,
            branch=branch,
            terminal=terminal,
            session=session,
            shift=shift,
            is_petty_cash_fund=is_petty_cash_fund,
            requested_by=requested_by,
            authorized_by=authorized_by_user,
            amount=amount,
            currency='KES',
            category=category,
            payee=payee_clean,
            description=desc_clean,
            receipt_reference=receipt_reference.strip(),
            receipt_due_by=receipt_due_by,
            status='paid_pending_receipt',
            paid_out_time=now,
            notes=notes
        )

        # 5. Audit Logging
        BankingAuditLog.objects.create(
            business=business,
            action='created',
            performed_by=authorized_by_user,
            details={
                'event': 'cash_paid_out_disbursed',
                'paid_out_number': paid_out.paid_out_number,
                'amount': str(paid_out.amount),
                'category': category.name,
                'payee': paid_out.payee,
                'description': paid_out.description,
                'requested_by': requested_by.username,
                'authorized_by': authorized_by_user.username,
                'is_petty_cash_fund': is_petty_cash_fund,
                'session_id': session.id if session else None,
                'ip_address': ip_address
            }
        )

        ActivityLog.objects.create(
            business=business,
            user=authorized_by_user,
            action_type='other',
            operation_type='create',
            entity_type='CashPaidOut',
            entity_id=str(paid_out.id),
            description=(
                f"Paid Out {paid_out.paid_out_number} of {paid_out.currency} {paid_out.amount:.2f} "
                f"for '{category.name}' to {paid_out.payee} authorized by {authorized_by_user.username}"
            )
        )

        return paid_out

    @staticmethod
    @transaction.atomic
    def attach_receipt(paid_out: CashPaidOut, user: User, receipt_reference: str,
                       receipt_file=None, notes: str = '') -> CashPaidOut:
        """
        Attaches a vendor receipt image/reference, advances status to 'confirmed',
        and automatically posts a General Ledger Expense entry for P&L reporting.
        """
        if hasattr(paid_out, 'refresh_from_db'):
            paid_out.refresh_from_db()

        if paid_out.is_reversed or paid_out.status == 'reversed':
            raise ValidationError("Cannot attach receipt to a reversed paid-out transaction.")

        receipt_ref_clean = str(receipt_reference or '').strip()
        if not receipt_ref_clean and not receipt_file and not paid_out.receipt_attachment:
            raise ValidationError("Please provide a receipt / invoice number or upload a receipt photo.")

        now = timezone.now()
        paid_out.receipt_reference = receipt_ref_clean or paid_out.receipt_reference
        if receipt_file:
            paid_out.receipt_attachment = receipt_file
        paid_out.receipt_received_at = now
        paid_out.status = 'confirmed'

        if notes:
            paid_out.notes = f"{paid_out.notes}\n[Receipt Attached {now:%Y-%m-%d %H:%M} by {user.username}]: {notes}".strip()

        # Create or update General Ledger Expense entry
        if not paid_out.expense_entry:
            expense = Expense.objects.create(
                business=paid_out.business,
                category=paid_out.category,
                description=f"Till Paid-Out: {paid_out.description} ({paid_out.payee})",
                amount=paid_out.amount,
                expense_date=paid_out.paid_out_time.date(),
                payment_method='cash',
                reference_number=paid_out.receipt_reference or paid_out.paid_out_number,
                attachment=paid_out.receipt_attachment,
                recorded_by=user,
                notes=f"Auto-posted from Till Paid-Out {paid_out.paid_out_number} authorized by {paid_out.authorized_by.username}"
            )
            paid_out.expense_entry = expense

        paid_out.save()

        BankingAuditLog.objects.create(
            business=paid_out.business,
            action='auto_matched',
            performed_by=user,
            details={
                'event': 'paid_out_receipt_confirmed',
                'paid_out_number': paid_out.paid_out_number,
                'receipt_reference': paid_out.receipt_reference,
                'expense_number': paid_out.expense_entry.expense_number if paid_out.expense_entry else '',
                'confirmed_by': user.username
            }
        )

        return paid_out

    @staticmethod
    @transaction.atomic
    def grant_receipt_exception(paid_out: CashPaidOut, supervisor_user: User, exception_reason: str) -> CashPaidOut:
        """
        Signs a documented manager exception note for informal vendors who cannot supply
        formal receipts. Confirms the payout and posts to GL.
        """
        if hasattr(paid_out, 'refresh_from_db'):
            paid_out.refresh_from_db()

        if paid_out.is_reversed or paid_out.status == 'reversed':
            raise ValidationError("Cannot sign receipt exception for a reversed transaction.")

        clean_reason = str(exception_reason or '').strip()
        if not clean_reason or len(clean_reason) < 5:
            raise ValidationError("A detailed manager exception explanation (at least 5 characters) is required.")

        now = timezone.now()
        paid_out.has_receipt_exception = True
        paid_out.exception_reason = clean_reason
        paid_out.exception_approved_by = supervisor_user
        paid_out.receipt_received_at = now
        paid_out.status = 'confirmed'
        paid_out.notes = f"{paid_out.notes}\n[Manager Exception Signed {now:%Y-%m-%d %H:%M} by {supervisor_user.username}]: {clean_reason}".strip()

        # Post to General Ledger Expense
        if not paid_out.expense_entry:
            expense = Expense.objects.create(
                business=paid_out.business,
                category=paid_out.category,
                description=f"Till Paid-Out (Informal Vendor): {paid_out.description} ({paid_out.payee})",
                amount=paid_out.amount,
                expense_date=paid_out.paid_out_time.date(),
                payment_method='cash',
                reference_number=f"EXC-{paid_out.paid_out_number}",
                recorded_by=supervisor_user,
                notes=f"Manager Exception signed by {supervisor_user.username}. Reason: {clean_reason}"
            )
            paid_out.expense_entry = expense

        paid_out.save()

        BankingAuditLog.objects.create(
            business=paid_out.business,
            action='auto_matched',
            performed_by=supervisor_user,
            details={
                'event': 'paid_out_exception_approved',
                'paid_out_number': paid_out.paid_out_number,
                'approved_by': supervisor_user.username,
                'reason': clean_reason
            }
        )

        return paid_out

    @staticmethod
    @transaction.atomic
    def reverse_paid_out(paid_out: CashPaidOut, user: User, supervisor_credential: str,
                         reversal_reason: str) -> CashPaidOut:
        """
        Reverses an unspent or cancelled paid out transaction, returning the physical cash
        back into the till drawer. Voids any linked General Ledger expense entry.
        """
        if hasattr(paid_out, 'refresh_from_db'):
            paid_out.refresh_from_db()

        if paid_out.is_reversed or paid_out.status == 'reversed':
            raise ValidationError("This transaction has already been reversed.")

        clean_reason = str(reversal_reason or '').strip()
        if not clean_reason or len(clean_reason) < 5:
            raise ValidationError("A clear reason for reversing this payout (at least 5 characters) is required.")

        # Authenticate supervisor for reversal
        class _AuthRequest:
            def __init__(self, biz, user):
                self.business = biz
                self.user = user
                self.content_type = 'text/plain'
                self.body = None
                self.POST = {}

        auth_req = _AuthRequest(paid_out.business, user)
        is_valid, sup_user, err_msg = verify_supervisor_credentials(auth_req, supervisor_credential)
        if not is_valid or not sup_user:
            raise ValidationError(err_msg or "Supervisor authorization required to reverse a cash payout.")

        now = timezone.now()
        paid_out.is_reversed = True
        paid_out.reversed_at = now
        paid_out.reversed_by = sup_user
        paid_out.reversal_reason = clean_reason
        paid_out.status = 'reversed'
        paid_out.notes = f"{paid_out.notes}\n[Reversed {now:%Y-%m-%d %H:%M} by {sup_user.username}]: Cash returned to drawer. Reason: {clean_reason}".strip()

        # Void or delete linked Expense entry so P&L isn't distorted
        if paid_out.expense_entry:
            expense = paid_out.expense_entry
            paid_out.expense_entry = None
            expense.delete()

        paid_out.save()

        BankingAuditLog.objects.create(
            business=paid_out.business,
            action='unmatched',
            performed_by=sup_user,
            details={
                'event': 'paid_out_reversed',
                'paid_out_number': paid_out.paid_out_number,
                'amount': str(paid_out.amount),
                'reversed_by': sup_user.username,
                'reason': clean_reason
            }
        )

        return paid_out

    @staticmethod
    @transaction.atomic
    def write_off_missing_receipt(paid_out: CashPaidOut, user: User, notes: str = '') -> CashPaidOut:
        """
        Marks an unrecovered receipt as written off (unaccounted cash loss).
        """
        if hasattr(paid_out, 'refresh_from_db'):
            paid_out.refresh_from_db()

        if paid_out.is_reversed or paid_out.status == 'reversed':
            raise ValidationError("Cannot write off a reversed transaction.")

        now = timezone.now()
        paid_out.status = 'written_off'
        paid_out.notes = f"{paid_out.notes}\n[Written Off {now:%Y-%m-%d %H:%M} by {user.username}]: {notes}".strip()
        paid_out.save()

        BankingAuditLog.objects.create(
            business=paid_out.business,
            action='manual_match_override',
            performed_by=user,
            details={
                'event': 'paid_out_written_off',
                'paid_out_number': paid_out.paid_out_number,
                'amount': str(paid_out.amount),
                'written_off_by': user.username
            }
        )

        return paid_out

    @staticmethod
    def get_missing_receipts(business: Business, branch: Optional[Branch] = None,
                             date_from: Optional[date] = None,
                             date_to: Optional[date] = None) -> List[Dict]:
        """
        Returns list of all paid-outs pending vendor receipts, highlighting overdue items.
        """
        qs = CashPaidOut.objects.filter(
            business=business,
            status='paid_pending_receipt'
        ).select_related('category', 'requested_by', 'authorized_by', 'branch', 'terminal', 'session')

        if branch:
            qs = qs.filter(branch=branch)
        if date_from:
            qs = qs.filter(paid_out_time__date__gte=date_from)
        if date_to:
            qs = qs.filter(paid_out_time__date__lte=date_to)

        now = timezone.now()
        results = []
        for p in qs.order_by('paid_out_time'):
            is_overdue = p.receipt_due_by and p.receipt_due_by < now
            hours_open = (now - p.paid_out_time).total_seconds() / 3600.0
            results.append({
                'paid_out': p,
                'is_overdue': is_overdue,
                'hours_open': round(hours_open, 1),
                'due_by': p.receipt_due_by,
            })
        return results

    @staticmethod
    def get_expense_category_summary(business: Business, start_date: date, end_date: date,
                                     branch: Optional[Branch] = None) -> List[Dict]:
        """
        Aggregates spend by expense category with budget cap tracking.
        """
        categories = ExpenseCategory.objects.filter(
            Q(business=business) | Q(business__isnull=True)
        ).order_by('name')

        results = []
        for cat in categories:
            qs = CashPaidOut.objects.filter(
                business=business,
                category=cat,
                paid_out_time__date__gte=start_date,
                paid_out_time__date__lte=end_date,
                status__in=['paid_pending_receipt', 'confirmed', 'written_off']
            )
            if branch:
                qs = qs.filter(branch=branch)

            agg = qs.aggregate(
                total_spent=Sum('amount'),
                payout_count=Count('id'),
                pending_receipt_count=Count('id', filter=Q(status='paid_pending_receipt')),
                confirmed_count=Count('id', filter=Q(status='confirmed'))
            )

            total_spent = agg['total_spent'] or Decimal('0.00')
            count = agg['payout_count'] or 0

            cap = cat.monthly_budget_cap
            cap_pct = round((total_spent / cap * 100), 1) if cap and cap > 0 else None

            results.append({
                'category': cat,
                'total_spent': total_spent,
                'payout_count': count,
                'pending_receipt_count': agg['pending_receipt_count'] or 0,
                'confirmed_count': agg['confirmed_count'] or 0,
                'budget_cap': cap,
                'budget_utilization_pct': cap_pct,
                'is_over_budget': bool(cap and total_spent > cap)
            })

        return sorted(results, key=lambda x: x['total_spent'], reverse=True)

    @staticmethod
    def get_approval_audit_trail(business: Business, start_date: Optional[date] = None,
                                 end_date: Optional[date] = None) -> List[CashPaidOut]:
        """
        Returns all high-value or supervisor-authorized paid-outs for compliance review.
        """
        qs = CashPaidOut.objects.filter(
            business=business
        ).select_related('category', 'requested_by', 'authorized_by', 'branch', 'terminal')

        if start_date:
            qs = qs.filter(paid_out_time__date__gte=start_date)
        if end_date:
            qs = qs.filter(paid_out_time__date__lte=end_date)

        return list(qs.order_by('-paid_out_time')[:100])
