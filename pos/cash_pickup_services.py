"""
Cash Pickup / Till Drop / Safe Drop Services for Marid POS
Enforces retail cash management controls:
1. Live drawer cash aggregation (Opening Float + Cash Sales - Prior Pickups - Cash Refunds).
2. Dual-custody verification (Cashier + Supervisor PIN/Password).
3. Chain of Custody tracking: Till -> Safe -> Bank Deposit -> Bank Statement Match.
4. Summary reports for audits, supervisor accountability, and Z-report closing variances.
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
    CashPickup, BankingRecord, BankingAuditLog, ActivityLog, UserProfile, BusinessMembership
)
from pos.security_utils import verify_supervisor_credentials, is_user_supervisor


class CashPickupService:
    """
    Core business logic engine for Cash Pickups / Till Drops.
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
        - Cash Refunds / Returns
        = Current Drawer Cash
        Also calculates suggested pickup amount above the target float.
        """
        # Resolve active session if not provided
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

        # 3. Active Cash Paid-Outs (Drawn from till)
        from pos.models import CashPaidOut
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

        # Target float buffer defaults to opening float (or KES 3,000 baseline)
        target_float = opening_float if opening_float > 0 else Decimal('3000.00')
        suggested_pickup = max(Decimal('0.00'), current_drawer_cash - target_float)

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
            'total_refunds': total_refunds,
            'current_drawer_cash': current_drawer_cash,
            'target_float': target_float,
            'suggested_pickup': suggested_pickup,
            'recent_pickups': list(pickups_qs.select_related('cashier', 'supervisor').order_by('-pickup_time')[:10])
        }

    @staticmethod
    @transaction.atomic
    def record_pickup(business: Business, cashier: User, supervisor_credential: str,
                      amount: Decimal, pickup_reference: str, reason: str = 'threshold_exceeded',
                      tender_type: str = 'cash', currency: str = 'KES',
                      session: Optional[POSSession] = None, terminal: Optional[POSTerminal] = None,
                      branch: Optional[Branch] = None, shift: Optional[Shift] = None,
                      notes: str = '', witness_type: str = 'supervisor',
                      peer_witness_user: Optional[User] = None,
                      ip_address: str = None, user_agent: str = None) -> CashPickup:
        """
        Executes and locks a new dual-custody Cash Pickup / Till Drop.
        Authenticates supervisor (or peer witness fallback) and decreases running drawer cash.
        """
        if not amount or amount <= Decimal('0.00'):
            raise ValidationError("Pickup amount must be greater than zero.")

        pickup_ref_clean = str(pickup_reference or '').strip()
        if not pickup_ref_clean:
            raise ValidationError("A pickup bag number, tamper envelope barcode, or slip ID is required.")

        supervisor_user = None

        # 1. Dual Custody Authentication
        if witness_type == 'peer_cashier' or peer_witness_user:
            # Fallback: peer cashier witness
            if not peer_witness_user:
                raise ValidationError("Peer witness cashier is required for witness fallback.")
            if peer_witness_user.id == cashier.id:
                raise ValidationError("Witness cannot be the same as the cashier operating the till.")
            supervisor_user = peer_witness_user
            witness_type = 'peer_cashier'
        else:
            # Standard: verify supervisor PIN or password
            # Create a mock request object for verify_supervisor_credentials
            class _AuthRequest:
                def __init__(self, biz, user):
                    self.business = biz
                    self.user = user
                    self.content_type = 'text/plain'
                    self.body = None
                    self.POST = {}

            auth_req = _AuthRequest(business, cashier)
            is_valid, sup_user, err_msg = verify_supervisor_credentials(auth_req, supervisor_credential)
            if not is_valid or not sup_user:
                raise ValidationError(err_msg or "Supervisor authorization failed. Invalid PIN or password.")
            if sup_user.id == cashier.id:
                raise ValidationError("Supervisor authorizer cannot be the same user as the till cashier.")
            supervisor_user = sup_user
            witness_type = 'supervisor'

        # Auto-resolve branch and terminal from session if not provided
        if session:
            branch = branch or session.branch
            terminal = terminal or session.terminal

        # 2. Check Drawer Cash Balance Warning
        drawer_summary = CashPickupService.get_drawer_cash_summary(
            business=business, session=session, terminal=terminal, cashier=cashier
        )
        current_cash = drawer_summary['current_drawer_cash']

        # 3. Create CashPickup Record
        now = timezone.now()
        pickup = CashPickup.objects.create(
            business=business,
            branch=branch,
            terminal=terminal,
            session=session,
            shift=shift,
            cashier=cashier,
            supervisor=supervisor_user,
            witness_type=witness_type,
            tender_type=tender_type,
            currency=currency or 'KES',
            amount=amount,
            pickup_reference=pickup_ref_clean,
            pickup_time=now,
            reason=reason,
            cashier_confirmed_at=now,
            supervisor_confirmed_at=now,
            status='confirmed',
            is_locked=True,
            notes=notes
        )

        # 4. Create Audit Logs
        BankingAuditLog.objects.create(
            business=business,
            action='auto_matched',  # or action for pickup
            performed_by=supervisor_user,
            details={
                'event': 'cash_pickup_recorded',
                'pickup_number': pickup.pickup_number,
                'amount': str(pickup.amount),
                'reference': pickup.pickup_reference,
                'cashier': cashier.username,
                'supervisor': supervisor_user.username,
                'witness_type': witness_type,
                'reason': reason,
                'terminal': terminal.terminal_code if terminal else '',
                'session_id': session.id if session else None,
                'ip_address': ip_address
            }
        )

        ActivityLog.objects.create(
            business=business,
            user=cashier,
            action_type='other',
            operation_type='create',
            entity_type='CashPickup',
            entity_id=str(pickup.id),
            description=(
                f"Cash Pickup {pickup.pickup_number} of {pickup.currency} {pickup.amount:.2f} "
                f"(Ref: {pickup.pickup_reference}) authorized by {supervisor_user.username}"
            )
        )

        return pickup

    @staticmethod
    @transaction.atomic
    def transfer_to_safe(pickup_ids: List[int], business: Business, user: User, notes: str = '') -> int:
        """
        Transfers confirmed cash pickups from till transport bags into the store central safe.
        Advances status from 'confirmed' -> 'in_safe'.
        """
        pickups = CashPickup.objects.filter(
            business=business,
            id__in=pickup_ids,
            status='confirmed'
        )
        count = pickups.count()
        if count == 0:
            return 0

        now = timezone.now()
        for p in pickups:
            p.status = 'in_safe'
            if notes:
                p.notes = f"{p.notes}\n[Safe Transfer {now:%Y-%m-%d %H:%M} by {user.username}]: {notes}".strip()
            p.save(update_fields=['status', 'notes', 'updated_at'])

            BankingAuditLog.objects.create(
                business=business,
                action='created',
                performed_by=user,
                details={
                    'event': 'pickup_transferred_to_safe',
                    'pickup_number': p.pickup_number,
                    'amount': str(p.amount),
                    'reference': p.pickup_reference,
                    'transferred_by': user.username
                }
            )

        return count

    @staticmethod
    @transaction.atomic
    def roll_into_banking_record(pickup_ids: List[int], banking_record: BankingRecord, user: User) -> int:
        """
        Attaches safe cash pickups to an official physical BankingRecord deposit slip.
        Advances status from 'in_safe' (or 'confirmed') -> 'banked'.
        """
        pickups = CashPickup.objects.filter(
            business=banking_record.business,
            id__in=pickup_ids,
            status__in=['confirmed', 'in_safe']
        )
        count = pickups.count()
        if count == 0:
            return 0

        for p in pickups:
            p.banking_record = banking_record
            p.status = 'banked'
            p.save(update_fields=['banking_record', 'status', 'updated_at'])

            BankingAuditLog.objects.create(
                business=banking_record.business,
                banking_record=banking_record,
                action='reconciled_manual',
                performed_by=user,
                details={
                    'event': 'pickup_banked',
                    'pickup_number': p.pickup_number,
                    'amount': str(p.amount),
                    'banking_record_ref': banking_record.record_number,
                    'deposit_slip': banking_record.deposit_reference
                }
            )

        return count

    @staticmethod
    def get_chain_of_custody(pickup: CashPickup, business: Business) -> Dict:
        """
        Builds complete end-to-end chain of custody audit trajectory:
        Step 1: Till Register & Shift Session
        Step 2: Dual-Custody Joint Count & Bag Sealing
        Step 3: Cash Office / Safe Custody
        Step 4: Bank Deposit Slip (BankingRecord)
        Step 5: Bank Statement Line Match (Reconciliation)
        """
        if hasattr(pickup, 'refresh_from_db'):
            try:
                pickup.refresh_from_db()
            except Exception:
                pass

        trajectory = {
            'pickup': pickup,
            'step1_till': {
                'completed': True,
                'terminal': pickup.terminal.name if pickup.terminal else 'Main Register',
                'terminal_code': pickup.terminal.terminal_code if pickup.terminal else '',
                'session_number': pickup.session.session_number if pickup.session else 'Direct Shift',
                'branch': pickup.branch.name if pickup.branch else 'Consolidated HQ',
                'timestamp': pickup.pickup_time,
                'amount': pickup.amount,
                'currency': pickup.currency,
                'tender_type': pickup.get_tender_type_display(),
            },
            'step2_dual_custody': {
                'completed': bool(pickup.cashier_confirmed_at and pickup.supervisor_confirmed_at),
                'cashier': pickup.cashier.get_full_name() or pickup.cashier.username,
                'cashier_confirmed_at': pickup.cashier_confirmed_at,
                'supervisor': pickup.supervisor.get_full_name() or pickup.supervisor.username,
                'supervisor_confirmed_at': pickup.supervisor_confirmed_at,
                'witness_type': pickup.get_witness_type_display(),
                'bag_reference': pickup.pickup_reference,
                'reason': pickup.get_reason_display(),
            },
            'step3_safe': {
                'completed': pickup.status in ['in_safe', 'banked'],
                'status': 'Stored in Store Vault / Safe' if pickup.status in ['in_safe', 'banked'] else 'Pending Safe Transfer',
                'transferred_at': pickup.updated_at if pickup.status in ['in_safe', 'banked'] else None,
            },
            'step4_banking': {
                'completed': bool(pickup.banking_record),
                'banking_record': pickup.banking_record,
                'record_number': pickup.banking_record.record_number if pickup.banking_record else None,
                'deposit_date': pickup.banking_record.deposit_date if pickup.banking_record else None,
                'deposit_slip': pickup.banking_record.deposit_reference if pickup.banking_record else None,
                'bank_account': pickup.banking_record.bank_account.bank_name if pickup.banking_record else None,
                'account_number': pickup.banking_record.bank_account.account_number if pickup.banking_record else None,
            },
            'step5_statement': {
                'completed': False,
                'statement_line': None,
                'cleared_date': None,
                'credit_amount': None,
                'match_type': None,
            }
        }

        # Check if banking record was matched to a bank statement line
        if pickup.banking_record and pickup.banking_record.status == 'matched':
            # Find linked statement line from ReconciliationMatch
            match = pickup.banking_record.reconciliation_matches.first()
            if match:
                st_line = match.statement_lines.first()
                if st_line:
                    trajectory['step5_statement'] = {
                        'completed': True,
                        'statement_line': st_line,
                        'cleared_date': st_line.transaction_date,
                        'credit_amount': st_line.amount,
                        'match_type': match.get_match_type_display(),
                        'matched_at': match.matched_at,
                        'matched_by': match.matched_by.username if match.matched_by else 'Auto-Match',
                    }

        return trajectory

    @staticmethod
    def get_supervisor_summary(business: Business, start_date: Optional[date] = None,
                               end_date: Optional[date] = None,
                               branch: Optional[Branch] = None) -> List[Dict]:
        """
        Summarizes total cash custody witnessed and authorized by each supervisor.
        """
        today = timezone.localdate()
        s_date = start_date or (today - timezone.timedelta(days=30))
        e_date = end_date or today

        qs = CashPickup.objects.filter(
            business=business,
            pickup_time__date__gte=s_date,
            pickup_time__date__lte=e_date,
            status__in=['confirmed', 'in_safe', 'banked']
        )
        if branch:
            qs = qs.filter(branch=branch)

        supervisors = User.objects.filter(
            id__in=qs.values_list('supervisor_id', flat=True).distinct()
        )

        summary_list = []
        for sup in supervisors:
            sup_qs = qs.filter(supervisor=sup)
            agg = sup_qs.aggregate(
                total_amt=Sum('amount'),
                total_count=Count('id')
            )
            cash_amt = sup_qs.filter(tender_type='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
            cheque_amt = sup_qs.filter(tender_type='cheque').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
            other_amt = (agg['total_amt'] or Decimal('0.00')) - cash_amt - cheque_amt

            summary_list.append({
                'supervisor': sup,
                'name': sup.get_full_name() or sup.username,
                'pickups_count': agg['total_count'] or 0,
                'total_amount': agg['total_amt'] or Decimal('0.00'),
                'cash_amount': cash_amt,
                'cheque_amount': cheque_amt,
                'other_amount': other_amt,
                'branches': list(sup_qs.values_list('branch__name', flat=True).distinct()),
                'last_pickup': sup_qs.order_by('-pickup_time').first()
            })

        summary_list.sort(key=lambda x: x['total_amount'], reverse=True)
        return summary_list

    @staticmethod
    def get_zreport_variance_analysis(business: Business, start_date: Optional[date] = None,
                                       end_date: Optional[date] = None,
                                       branch: Optional[Branch] = None) -> List[Dict]:
        """
        Surfaces all closed POS sessions and compares expected drawer cash
        (factoring in pickups) against actual counted closing cash.
        """
        today = timezone.localdate()
        s_date = start_date or (today - timezone.timedelta(days=14))
        e_date = end_date or today

        sessions = POSSession.objects.filter(
            business=business,
            status='closed',
            opened_at__date__gte=s_date,
            opened_at__date__lte=e_date
        ).select_related('cashier', 'opened_by', 'closed_by', 'terminal', 'branch').order_by('-closed_at')

        if branch:
            sessions = sessions.filter(branch=branch)

        analysis = []
        for s in sessions:
            # Aggregate sales payments
            cash_sales = SalePayment.objects.filter(
                sale__session=s
            ).filter(
                Q(payment_method__code__iexact='CASH') | Q(payment_method__name__icontains='cash')
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            # Aggregate cash pickups for this session
            pickups_agg = CashPickup.objects.filter(
                session=s,
                status__in=['confirmed', 'in_safe', 'banked']
            ).aggregate(t=Sum('amount'), c=Count('id'))

            pickups_total = pickups_agg['t'] or Decimal('0.00')
            pickups_count = pickups_agg['c'] or 0

            expected_drawer = s.opening_cash + cash_sales - pickups_total
            counted_closing = s.closing_cash or Decimal('0.00')
            variance = counted_closing - expected_drawer

            analysis.append({
                'session': s,
                'session_number': s.session_number,
                'date': s.opened_at.date(),
                'terminal': s.terminal.name if s.terminal else 'Main Terminal',
                'branch': s.branch.name if s.branch else 'HQ',
                'cashier': s.cashier.get_full_name() or s.cashier.username if s.cashier else (s.opened_by.username if s.opened_by else 'Unknown'),
                'opening_float': s.opening_cash,
                'cash_sales': cash_sales,
                'pickups_total': pickups_total,
                'pickups_count': pickups_count,
                'expected_drawer': expected_drawer,
                'counted_closing': counted_closing,
                'variance': variance,
                'is_balanced': variance == Decimal('0.00'),
                'is_short': variance < Decimal('0.00'),
                'is_over': variance > Decimal('0.00'),
            })

        return analysis
