"""
Banking & Bank Reconciliation Services for Marid POS
Handles:
- Expected cash / collection aggregation from POS sales and cash drawer sessions
- Multi-format bank statement ingestion (CSV, OFX, Manual entry)
- Auto-matching and manual multi-link reconciliation engine
- Classic accounting bank reconciliation calculations and reports
"""

import csv
import io
import re
from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.utils import timezone

from .models import (
    Business, Branch, POSTerminal, Sale, SalePayment, Shift, POSSession,
    BankAccount, BankingRecord, BankStatementImportBatch, BankStatementLine,
    ReconciliationMatch, BankingAuditLog, Expense, SupplierPayment, SupplierRefund,
    SupplierCredit, SupplierInvoice
)


class BankingCalculationService:
    """
    Calculates expected cash/cheque/tender collections from POS operations
    and computes unbanked cash sitting in drawers/safes.
    """

    @staticmethod
    def calculate_expected_cash(business, branch=None, terminal=None, period_start=None, period_end=None, payment_type='cash'):
        """
        Calculates expected cash collections for a given date range and location.
        Deducts any collections already committed to prior active BankingRecords.
        """
        today = timezone.localdate()
        start_d = period_start or today
        end_d = period_end or today

        # 1. Base query for payments
        payments_qs = SalePayment.objects.filter(
            sale__business=business,
            sale__date__date__gte=start_d,
            sale__date__date__lte=end_d
        ).select_related('sale', 'payment_method')

        if branch:
            payments_qs = payments_qs.filter(sale__branch=branch)
        if terminal:
            payments_qs = payments_qs.filter(
                Q(sale__terminal=terminal) | Q(sale__session__terminal=terminal)
            )

        # 2. Filter by payment type
        if payment_type == 'cash':
            payments_qs = payments_qs.filter(
                Q(payment_method__code__iexact='CASH') | Q(payment_method__name__icontains='cash')
            )
        elif payment_type == 'cheque':
            payments_qs = payments_qs.filter(
                Q(payment_method__code__iexact='CHEQUE') | Q(payment_method__name__icontains='cheque')
            )
        elif payment_type == 'mixed':
            payments_qs = payments_qs.filter(
                Q(payment_method__code__iexact='CASH') | Q(payment_method__name__icontains='cash') |
                Q(payment_method__code__iexact='CHEQUE') | Q(payment_method__name__icontains='cheque')
            )
        elif payment_type == 'card_settlement':
            payments_qs = payments_qs.filter(
                Q(payment_method__code__icontains='CARD') | Q(payment_method__name__icontains='card') |
                Q(payment_method__name__icontains='visa') | Q(payment_method__name__icontains='mastercard')
            )
        elif payment_type == 'mobile_money':
            payments_qs = payments_qs.filter(
                Q(payment_method__code__icontains='MPESA') | Q(payment_method__name__icontains='mpesa') |
                Q(payment_method__name__icontains='mobile')
            )

        total_collected = payments_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        sales_count = payments_qs.values('sale_id').distinct().count()

        # 3. Check already banked records in this period/location
        banked_qs = BankingRecord.objects.filter(
            business=business,
            period_start__lte=end_d,
            period_end__gte=start_d,
            payment_type=payment_type
        ).exclude(status='pending')

        if branch:
            banked_qs = banked_qs.filter(branch=branch)
        if terminal:
            banked_qs = banked_qs.filter(terminal=terminal)

        already_banked = banked_qs.aggregate(total=Sum('deposited_amount'))['total'] or Decimal('0.00')
        expected_remaining = max(Decimal('0.00'), total_collected - already_banked)

        return {
            'period_start': start_d,
            'period_end': end_d,
            'total_collected': total_collected,
            'already_banked': already_banked,
            'expected_amount': total_collected, # Standard expected for selected period
            'expected_remaining': expected_remaining,
            'sales_count': sales_count,
            'payment_type': payment_type,
        }

    @staticmethod
    def calculate_unbanked_funds(business, as_of_date=None, branch=None):
        """
        Computes total physical cash collected at POS till registers that has NOT yet been banked.
        """
        as_of = as_of_date or timezone.localdate()

        # Cumulative cash collected up to as_of date
        cash_payments_qs = SalePayment.objects.filter(
            sale__business=business,
            sale__date__date__lte=as_of
        ).filter(
            Q(payment_method__code__iexact='CASH') | Q(payment_method__name__icontains='cash')
        )
        if branch:
            cash_payments_qs = cash_payments_qs.filter(sale__branch=branch)

        total_cash_collected = cash_payments_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Cumulative cash banked up to as_of date
        banked_qs = BankingRecord.objects.filter(
            business=business,
            deposit_date__lte=as_of,
            payment_type__in=['cash', 'mixed']
        )
        if branch:
            banked_qs = banked_qs.filter(branch=branch)

        total_cash_banked = banked_qs.aggregate(total=Sum('deposited_amount'))['total'] or Decimal('0.00')

        # Cash Pickups currently sitting in Safe vs Pending
        from pos.models import CashPickup
        safe_pickups_qs = CashPickup.objects.filter(
            business=business,
            pickup_time__date__lte=as_of,
            status='in_safe'
        )
        if branch:
            safe_pickups_qs = safe_pickups_qs.filter(branch=branch)

        safe_cash_amount = safe_pickups_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        safe_pickups_count = safe_pickups_qs.count()

        # Total unbanked (cash in safe/tills)
        unbanked_amount = max(Decimal('0.00'), total_cash_collected - total_cash_banked)

        return {
            'as_of_date': as_of,
            'total_cash_collected': total_cash_collected,
            'total_cash_banked': total_cash_banked,
            'unbanked_amount': unbanked_amount,
            'safe_cash_amount': safe_cash_amount,
            'safe_pickups_count': safe_pickups_count,
            'safe_pickups': list(safe_pickups_qs.select_related('cashier', 'supervisor', 'branch').order_by('-pickup_time')[:20]),
        }


class StatementParserService:
    """
    Parses CSV and OFX bank statement files and creates BankStatementLine entries.
    """

    @staticmethod
    def parse_csv(file_obj, bank_account, user, mapping=None):
        """
        Parses a bank statement CSV file.
        Supports standard bank layouts and custom column mappings.
        """
        if hasattr(file_obj, 'read'):
            raw_bytes = file_obj.read()
        else:
            with open(file_obj, 'rb') as f:
                raw_bytes = f.read()

        # Decode with fallback
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
            try:
                text_content = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Unable to decode statement file. Please ensure it is saved as UTF-8 or standard CSV.")

        # Detect delimiter
        first_line = text_content.strip().split('\n')[0] if text_content.strip() else ""
        delimiter = ','
        if ';' in first_line and first_line.count(';') > first_line.count(','):
            delimiter = ';'
        elif '\t' in first_line:
            delimiter = '\t'

        reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV file appears to be empty or has no header row.")

        # Normalize field names
        field_map = {}
        for fn in reader.fieldnames:
            if not fn:
                continue
            clean = fn.strip().lower().replace('_', ' ').replace('-', ' ')
            field_map[clean] = fn

        def find_field(*candidates):
            for cand in candidates:
                cand_lower = cand.lower().replace('_', ' ').replace('-', ' ')
                for clean_name, original_name in field_map.items():
                    if cand_lower == clean_name or cand_lower in clean_name:
                        return original_name
            return None

        # Determine column positions
        date_col = find_field('date', 'txn date', 'transaction date', 'posting date', 'value date')
        desc_col = find_field('description', 'details', 'narrative', 'particulars', 'narration', 'memo')
        ref_col = find_field('reference', 'ref', 'chq no', 'cheque no', 'document no', 'ref no')
        credit_col = find_field('credit', 'credit amount', 'deposit', 'paid in', 'cr')
        debit_col = find_field('debit', 'debit amount', 'withdrawal', 'paid out', 'dr')
        amount_col = find_field('amount', 'txn amount', 'net amount')

        if not date_col or (not credit_col and not amount_col):
            # Fallback to positional parsing if standard headers not found
            pass

        batch = BankStatementImportBatch.objects.create(
            business=bank_account.business,
            bank_account=bank_account,
            file_format='csv',
            imported_by=user,
            notes=f"Imported from {getattr(file_obj, 'name', 'CSV file')}"
        )

        created_lines = []
        total_credits = Decimal('0.00')
        total_debits = Decimal('0.00')
        earliest_date = None
        latest_date = None

        for row in reader:
            raw_date = row.get(date_col, '').strip() if date_col else ''
            if not raw_date:
                continue

            parsed_date = StatementParserService._parse_date_flexible(raw_date)
            if not parsed_date:
                continue

            if earliest_date is None or parsed_date < earliest_date:
                earliest_date = parsed_date
            if latest_date is None or parsed_date > latest_date:
                latest_date = parsed_date

            description = row.get(desc_col, '').strip() if desc_col else ''
            reference = row.get(ref_col, '').strip() if ref_col else ''

            line_type = 'credit'
            amount = Decimal('0.00')

            if credit_col and debit_col:
                raw_credit = StatementParserService._clean_decimal(row.get(credit_col, ''))
                raw_debit = StatementParserService._clean_decimal(row.get(debit_col, ''))
                if raw_credit and raw_credit > 0:
                    amount = raw_credit
                    line_type = 'credit'
                elif raw_debit and raw_debit > 0:
                    amount = raw_debit
                    line_type = 'debit'
                else:
                    continue
            elif amount_col:
                raw_amt = StatementParserService._clean_decimal(row.get(amount_col, ''))
                if raw_amt is not None and raw_amt != 0:
                    if raw_amt < 0:
                        line_type = 'debit'
                        amount = abs(raw_amt)
                    else:
                        line_type = 'credit'
                        amount = raw_amt
                else:
                    continue

            if line_type == 'credit':
                total_credits += amount
            else:
                total_debits += amount

            line = BankStatementLine(
                business=bank_account.business,
                bank_account=bank_account,
                batch=batch,
                transaction_date=parsed_date,
                line_type=line_type,
                amount=amount,
                reference=reference[:255],
                description=description,
                status='unmatched'
            )
            created_lines.append(line)

        if not created_lines:
            batch.delete()
            raise ValueError("No valid transaction lines could be parsed from the CSV file.")

        BankStatementLine.objects.bulk_create(created_lines)

        batch.total_lines = len(created_lines)
        batch.total_credits = total_credits
        batch.total_debits = total_debits
        batch.statement_start_date = earliest_date
        batch.statement_end_date = latest_date
        batch.save()

        BankingAuditLog.objects.create(
            business=bank_account.business,
            action='statement_imported',
            performed_by=user,
            details={
                'batch_id': batch.id,
                'batch_number': batch.batch_number,
                'bank_account': bank_account.bank_name,
                'total_lines': len(created_lines),
                'total_credits': float(total_credits),
                'total_debits': float(total_debits),
            }
        )

        return batch

    @staticmethod
    def parse_ofx(file_obj, bank_account, user):
        """
        Parses an Open Financial Exchange (OFX) / QBO bank statement file.
        """
        if hasattr(file_obj, 'read'):
            raw_bytes = file_obj.read()
        else:
            with open(file_obj, 'rb') as f:
                raw_bytes = f.read()

        text = raw_bytes.decode('utf-8', errors='ignore')

        batch = BankStatementImportBatch.objects.create(
            business=bank_account.business,
            bank_account=bank_account,
            file_format='ofx',
            imported_by=user,
            notes=f"Imported from {getattr(file_obj, 'name', 'OFX file')}"
        )

        # Regex extract STMTTRN blocks
        trn_blocks = re.findall(r'<STMTTRN>.*?</STMTTRN>', text, re.DOTALL | re.IGNORECASE)
        if not trn_blocks:
            batch.delete()
            raise ValueError("No <STMTTRN> transaction blocks found in OFX file.")

        created_lines = []
        total_credits = Decimal('0.00')
        total_debits = Decimal('0.00')
        earliest_date = None
        latest_date = None

        def extract_tag(block, tag):
            m = re.search(rf'<{tag}>([^<\r\n]+)', block, re.IGNORECASE)
            return m.group(1).strip() if m else ''

        for block in trn_blocks:
            dt_raw = extract_tag(block, 'DTPOSTED') or extract_tag(block, 'DTUSER')
            amt_raw = extract_tag(block, 'TRNAMT')
            name = extract_tag(block, 'NAME')
            memo = extract_tag(block, 'MEMO')
            checknum = extract_tag(block, 'CHECKNUM') or extract_tag(block, 'FITID')

            if not dt_raw or not amt_raw:
                continue

            parsed_date = StatementParserService._parse_ofx_date(dt_raw)
            if not parsed_date:
                continue

            if earliest_date is None or parsed_date < earliest_date:
                earliest_date = parsed_date
            if latest_date is None or parsed_date > latest_date:
                latest_date = parsed_date

            try:
                amt = Decimal(amt_raw.replace(',', ''))
            except (InvalidOperation, ValueError):
                continue

            if amt >= 0:
                line_type = 'credit'
                amount = amt
                total_credits += amount
            else:
                line_type = 'debit'
                amount = abs(amt)
                total_debits += amount

            description = f"{name} {memo}".strip()

            line = BankStatementLine(
                business=bank_account.business,
                bank_account=bank_account,
                batch=batch,
                transaction_date=parsed_date,
                line_type=line_type,
                amount=amount,
                reference=checknum[:255],
                description=description,
                status='unmatched'
            )
            created_lines.append(line)

        if not created_lines:
            batch.delete()
            raise ValueError("Could not extract any valid transactions from the OFX file.")

        BankStatementLine.objects.bulk_create(created_lines)

        batch.total_lines = len(created_lines)
        batch.total_credits = total_credits
        batch.total_debits = total_debits
        batch.statement_start_date = earliest_date
        batch.statement_end_date = latest_date
        batch.save()

        BankingAuditLog.objects.create(
            business=bank_account.business,
            action='statement_imported',
            performed_by=user,
            details={
                'batch_id': batch.id,
                'batch_number': batch.batch_number,
                'file_format': 'ofx',
                'total_lines': len(created_lines),
            }
        )

        return batch

    @staticmethod
    def _parse_date_flexible(date_str):
        """Tries common date formats (YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY)."""
        date_str = date_str.strip()
        # Clean timestamp if present e.g. 2026-09-15 14:30:00
        date_str = date_str.split(' ')[0].split('T')[0]

        formats = [
            '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
            '%Y/%m/%d', '%d.%m.%Y', '%d %b %Y', '%d-%b-%Y'
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_ofx_date(dt_str):
        """Parses YYYYMMDD[HHMMSS] OFX timestamp format."""
        dt_str = re.sub(r'[^0-9]', '', dt_str)[:8]
        if len(dt_str) == 8:
            try:
                return datetime.strptime(dt_str, '%Y%m%d').date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _clean_decimal(val):
        if val is None:
            return None
        val_str = str(val).strip().replace(',', '').replace(' ', '').replace('KES', '').replace('$', '')
        if not val_str:
            return None
        try:
            return Decimal(val_str)
        except (InvalidOperation, ValueError):
            return None


class ReconciliationEngine:
    """
    Executes automated and manual bank reconciliation matching.
    """

    @staticmethod
    def auto_match(business, bank_account=None, date_tolerance_days=3, user=None):
        """
        Scans unmatched BankingRecords, SupplierRefunds (Credits/Inflows) and
        SupplierPayments (Debits/Outflows) against BankStatementLines.
        Matches pairs with exact amount within the configured ±date tolerance window.
        """
        matched_pairs = []
        used_line_ids = set()
        used_record_ids = set()
        used_refund_ids = set()
        used_payment_ids = set()

        with transaction.atomic():
            # ==================== 1. CREDITS (MONEY IN) ====================
            lines_credit_qs = BankStatementLine.objects.filter(
                business=business,
                status='unmatched',
                line_type='credit'
            ).select_related('bank_account')
            if bank_account:
                lines_credit_qs = lines_credit_qs.filter(bank_account=bank_account)
            credit_lines = list(lines_credit_qs.order_by('transaction_date'))

            # 1a. Match POS Banking Records (Cash/Cheque Deposits)
            records_qs = BankingRecord.objects.filter(
                business=business,
                status__in=['banked', 'pending', 'discrepancy']
            ).select_related('bank_account')
            if bank_account:
                records_qs = records_qs.filter(bank_account=bank_account)
            records = list(records_qs.order_by('deposit_date'))

            for rec in records:
                if rec.id in used_record_ids:
                    continue

                best_line = None
                best_date_diff = 9999

                for line in credit_lines:
                    if line.id in used_line_ids:
                        continue
                    if line.bank_account_id != rec.bank_account_id:
                        continue

                    if rec.deposited_amount == line.amount:
                        date_diff = abs((line.transaction_date - rec.deposit_date).days)
                        if date_diff <= date_tolerance_days and date_diff < best_date_diff:
                            best_date_diff = date_diff
                            best_line = line

                if best_line:
                    match_obj = ReconciliationMatch.objects.create(
                        business=business,
                        match_type='one_to_one',
                        total_banked_amount=rec.deposited_amount,
                        total_statement_amount=best_line.amount,
                        bank_charge_amount=Decimal('0.00'),
                        variance_amount=Decimal('0.00'),
                        matched_by=user or rec.deposited_by,
                        notes=f"Auto-matched Deposit (Date Diff: {best_date_diff} days)"
                    )
                    match_obj.banking_records.add(rec)
                    match_obj.statement_lines.add(best_line)

                    rec.status = 'matched'
                    rec.reconciled_by = user or rec.deposited_by
                    rec.reconciled_at = timezone.now()
                    rec.save(update_fields=['status', 'reconciled_by', 'reconciled_at', 'updated_at'])

                    best_line.status = 'matched'
                    best_line.matched_banking_record = rec
                    best_line.save(update_fields=['status', 'matched_banking_record'])

                    used_record_ids.add(rec.id)
                    used_line_ids.add(best_line.id)

                    matched_pairs.append({
                        'type': 'banking_record',
                        'record_number': rec.record_number,
                        'statement_line_id': best_line.id,
                        'amount': float(rec.deposited_amount),
                        'direction': 'inflow',
                        'date': rec.deposit_date.isoformat(),
                    })

                    BankingAuditLog.objects.create(
                        business=business,
                        banking_record=rec,
                        statement_line=best_line,
                        reconciliation_match=match_obj,
                        action='auto_matched',
                        performed_by=user,
                        details={
                            'match_number': match_obj.match_number,
                            'amount': float(rec.deposited_amount),
                            'date_difference_days': best_date_diff,
                        }
                    )

            # 1b. Match Supplier Refunds (Money in from supplier claims)
            refunds_qs = SupplierRefund.objects.filter(
                business=business,
                status='pending',
                received_via='bank_transfer'
            ).select_related('destination_account')
            if bank_account:
                refunds_qs = refunds_qs.filter(destination_account=bank_account)
            refunds = list(refunds_qs.order_by('received_date'))

            for ref in refunds:
                if ref.id in used_refund_ids:
                    continue

                best_line = None
                best_date_diff = 9999

                for line in credit_lines:
                    if line.id in used_line_ids:
                        continue
                    if ref.destination_account_id and line.bank_account_id != ref.destination_account_id:
                        continue

                    if ref.amount == line.amount:
                        date_diff = abs((line.transaction_date - ref.received_date).days)
                        if date_diff <= date_tolerance_days and date_diff < best_date_diff:
                            best_date_diff = date_diff
                            best_line = line

                if best_line:
                    match_obj = ReconciliationMatch.objects.create(
                        business=business,
                        match_type='one_to_one',
                        total_banked_amount=ref.amount,
                        total_statement_amount=best_line.amount,
                        bank_charge_amount=Decimal('0.00'),
                        variance_amount=Decimal('0.00'),
                        matched_by=user or ref.received_by,
                        notes=f"Auto-matched Supplier Refund (Date Diff: {best_date_diff} days)"
                    )
                    match_obj.supplier_refunds.add(ref)
                    match_obj.statement_lines.add(best_line)

                    ref.status = 'matched'
                    ref.bank_statement_line = best_line
                    ref.save(update_fields=['status', 'bank_statement_line', 'updated_at'])

                    best_line.status = 'matched'
                    best_line.matched_supplier_refund = ref
                    best_line.save(update_fields=['status', 'matched_supplier_refund'])

                    used_refund_ids.add(ref.id)
                    used_line_ids.add(best_line.id)

                    matched_pairs.append({
                        'type': 'supplier_refund',
                        'record_number': ref.refund_number,
                        'statement_line_id': best_line.id,
                        'amount': float(ref.amount),
                        'direction': 'inflow',
                        'date': ref.received_date.isoformat(),
                    })

            # ==================== 2. DEBITS (MONEY OUT) ====================
            lines_debit_qs = BankStatementLine.objects.filter(
                business=business,
                status='unmatched',
                line_type='debit'
            ).select_related('bank_account')
            if bank_account:
                lines_debit_qs = lines_debit_qs.filter(bank_account=bank_account)
            debit_lines = list(lines_debit_qs.order_by('transaction_date'))

            # 2a. Match Outgoing Supplier Payments (EFT / Cheques / Transfers)
            payments_qs = SupplierPayment.objects.filter(
                business=business,
                status__in=['sent', 'pending'],
                is_reversed=False,
                bank_statement_line__isnull=True
            ).select_related('bank_account')
            if bank_account:
                payments_qs = payments_qs.filter(bank_account=bank_account)
            payments = list(payments_qs.order_by('payment_date'))

            for pay in payments:
                if pay.id in used_payment_ids:
                    continue

                best_line = None
                best_date_diff = 9999

                for line in debit_lines:
                    if line.id in used_line_ids:
                        continue
                    if pay.bank_account_id and line.bank_account_id != pay.bank_account_id:
                        continue

                    if pay.amount == line.amount:
                        date_diff = abs((line.transaction_date - pay.payment_date).days)
                        if date_diff <= date_tolerance_days and date_diff < best_date_diff:
                            best_date_diff = date_diff
                            best_line = line

                if best_line:
                    match_obj = ReconciliationMatch.objects.create(
                        business=business,
                        match_type='one_to_one',
                        total_banked_amount=pay.amount,
                        total_statement_amount=best_line.amount,
                        bank_charge_amount=Decimal('0.00'),
                        variance_amount=Decimal('0.00'),
                        matched_by=user or pay.created_by,
                        notes=f"Auto-matched Supplier Payment (Date Diff: {best_date_diff} days)"
                    )
                    match_obj.supplier_payments.add(pay)
                    match_obj.statement_lines.add(best_line)

                    pay.status = 'cleared'
                    pay.bank_statement_line = best_line
                    pay.save(update_fields=['status', 'bank_statement_line', 'updated_at'])

                    best_line.status = 'matched'
                    best_line.matched_supplier_payment = pay
                    best_line.save(update_fields=['status', 'matched_supplier_payment'])

                    used_payment_ids.add(pay.id)
                    used_line_ids.add(best_line.id)

                    matched_pairs.append({
                        'type': 'supplier_payment',
                        'record_number': pay.payment_number,
                        'statement_line_id': best_line.id,
                        'amount': float(pay.amount),
                        'direction': 'outflow',
                        'date': pay.payment_date.isoformat(),
                    })

        total_matched_amt = sum(Decimal(str(p['amount'])) for p in matched_pairs)

        return {
            'matched_count': len(matched_pairs),
            'total_matched_amount': total_matched_amt,
            'matched_pairs': matched_pairs,
            'remaining_unmatched_lines': (len(credit_lines) + len(debit_lines)) - len(used_line_ids),
        }

    @staticmethod
    def manual_match(business, banking_record_ids=None, supplier_payment_ids=None,
                     supplier_refund_ids=None, statement_line_ids=None,
                     bank_charge=Decimal('0.00'), user=None, notes=''):
        """
        Manually links one or more BankingRecords, SupplierPayments, or SupplierRefunds
        to one or more BankStatementLines.
        """
        b_ids = banking_record_ids or []
        p_ids = supplier_payment_ids or []
        r_ids = supplier_refund_ids or []
        l_ids = statement_line_ids or []

        if not (b_ids or p_ids or r_ids) or not l_ids:
            raise ValueError("Please select at least one internal transaction and one bank statement line.")

        records = list(BankingRecord.objects.filter(business=business, id__in=b_ids))
        payments = list(SupplierPayment.objects.filter(business=business, id__in=p_ids, is_reversed=False))
        refunds = list(SupplierRefund.objects.filter(business=business, id__in=r_ids))
        lines = list(BankStatementLine.objects.filter(business=business, id__in=l_ids))

        total_internal = (
            sum(r.deposited_amount for r in records) +
            sum(p.amount for p in payments) +
            sum(rf.amount for rf in refunds)
        )
        total_statement = sum(l.amount for l in lines)
        bank_charge_amt = Decimal(str(bank_charge or '0.00'))
        variance = (total_internal - bank_charge_amt) - total_statement

        match_type = 'one_to_one'
        if (len(records) + len(payments) + len(refunds)) > 1:
            match_type = 'many_to_one'
        elif len(lines) > 1:
            match_type = 'one_to_many'
        elif bank_charge_amt > 0:
            match_type = 'with_fee'

        with transaction.atomic():
            match_obj = ReconciliationMatch.objects.create(
                business=business,
                match_type=match_type,
                total_banked_amount=total_internal,
                total_statement_amount=total_statement,
                bank_charge_amount=bank_charge_amt,
                variance_amount=variance,
                matched_by=user,
                notes=notes or "Manually reconciled"
            )
            if records:
                match_obj.banking_records.set(records)
            if payments:
                match_obj.supplier_payments.set(payments)
            if refunds:
                match_obj.supplier_refunds.set(refunds)
            match_obj.statement_lines.set(lines)

            for rec in records:
                rec.status = 'matched' if variance == 0 else 'discrepancy'
                rec.reconciled_by = user
                rec.reconciled_at = timezone.now()
                rec.save(update_fields=['status', 'reconciled_by', 'reconciled_at', 'updated_at'])

            for pay in payments:
                pay.status = 'cleared'
                if len(lines) == 1:
                    pay.bank_statement_line = lines[0]
                pay.save(update_fields=['status', 'bank_statement_line', 'updated_at'])

            for ref in refunds:
                ref.status = 'matched'
                if len(lines) == 1:
                    ref.bank_statement_line = lines[0]
                ref.save(update_fields=['status', 'bank_statement_line', 'updated_at'])

            for line in lines:
                line.status = 'matched'
                if len(records) == 1:
                    line.matched_banking_record = records[0]
                elif len(payments) == 1:
                    line.matched_supplier_payment = payments[0]
                elif len(refunds) == 1:
                    line.matched_supplier_refund = refunds[0]
                line.save(update_fields=['status', 'matched_banking_record', 'matched_supplier_payment', 'matched_supplier_refund'])

            BankingAuditLog.objects.create(
                business=business,
                reconciliation_match=match_obj,
                action='manual_matched',
                performed_by=user,
                details={
                    'match_number': match_obj.match_number,
                    'total_internal': float(total_internal),
                    'total_statement': float(total_statement),
                    'bank_charge': float(bank_charge_amt),
                    'variance': float(variance),
                }
            )

        return match_obj

    @staticmethod
    def unmatch(reconciliation_match_id, business, user=None):
        """
        Rolls back a reconciliation match, reverting records, payments, refunds and statement lines.
        """
        match_obj = ReconciliationMatch.objects.filter(
            id=reconciliation_match_id, business=business
        ).first()

        if not match_obj:
            raise ValueError("Reconciliation match not found.")

        with transaction.atomic():
            records = list(match_obj.banking_records.all())
            payments = list(match_obj.supplier_payments.all())
            refunds = list(match_obj.supplier_refunds.all())
            lines = list(match_obj.statement_lines.all())

            for rec in records:
                rec.status = 'banked'
                rec.reconciled_by = None
                rec.reconciled_at = None
                rec.save(update_fields=['status', 'reconciled_by', 'reconciled_at', 'updated_at'])

            for pay in payments:
                pay.status = 'sent'
                pay.bank_statement_line = None
                pay.save(update_fields=['status', 'bank_statement_line', 'updated_at'])

            for ref in refunds:
                ref.status = 'pending'
                ref.bank_statement_line = None
                ref.save(update_fields=['status', 'bank_statement_line', 'updated_at'])

            for line in lines:
                line.status = 'unmatched'
                line.matched_banking_record = None
                line.matched_supplier_payment = None
                line.matched_supplier_refund = None
                line.save(update_fields=['status', 'matched_banking_record', 'matched_supplier_payment', 'matched_supplier_refund'])

            BankingAuditLog.objects.create(
                business=business,
                action='unmatched',
                performed_by=user,
                details={
                    'match_number': match_obj.match_number,
                    'reverted_records': [r.record_number for r in records],
                    'reverted_payments': [p.payment_number for p in payments],
                    'reverted_refunds': [rf.refund_number for rf in refunds],
                    'reverted_lines': [l.id for l in lines],
                }
            )

            match_obj.delete()

        return True

    @staticmethod
    def get_reconciliation_statement(business, bank_account, as_of_date=None):
        """
        Generates the standard 4-part Bank Reconciliation Statement:
        1. General Ledger Book Balance (as of date)
        2. PLUS: Deposits & Refunds in Transit (not yet cleared on statement)
        3. LESS: Outstanding / Unpresented Cheques and Outgoing Payments
        4. LESS: Unmatched Bank Charges and Fees
        = Adjusted Book Balance vs. Actual Bank Statement Balance
        """
        as_of = as_of_date or timezone.localdate()

        opening = bank_account.opening_balance

        # Deposits banked to this account
        deposits_qs = BankingRecord.objects.filter(
            business=business,
            bank_account=bank_account,
            deposit_date__lte=as_of
        )
        total_banked = deposits_qs.aggregate(t=Sum('deposited_amount'))['t'] or Decimal('0.00')

        # Supplier refunds received into this account
        refunds_qs = SupplierRefund.objects.filter(
            business=business,
            destination_account=bank_account,
            received_date__lte=as_of
        )
        total_refunds = refunds_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # Total direct expenses through bank
        expenses_qs = Expense.objects.filter(
            business=business,
            expense_date__lte=as_of,
            payment_method='bank'
        )
        total_expenses = expenses_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # Supplier payments sent from this bank account
        supplier_payments_qs = SupplierPayment.objects.filter(
            business=business,
            bank_account=bank_account,
            payment_date__lte=as_of,
            is_reversed=False
        )
        total_supplier_payments = supplier_payments_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        book_balance = opening + total_banked + total_refunds - total_expenses - total_supplier_payments

        # 2. Inflows in Transit (Deposits + Refunds not yet matched)
        deposits_in_transit_qs = deposits_qs.filter(status__in=['banked', 'pending'])
        deposits_in_transit = deposits_in_transit_qs.aggregate(t=Sum('deposited_amount'))['t'] or Decimal('0.00')

        refunds_in_transit_qs = refunds_qs.filter(status='pending')
        refunds_in_transit = refunds_in_transit_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        total_inflows_in_transit = deposits_in_transit + refunds_in_transit

        # 3. Outflows / Cheques in Transit (Supplier payments sent but not cleared)
        payments_in_transit_qs = supplier_payments_qs.filter(status__in=['sent', 'pending'], bank_statement_line__isnull=True)
        payments_in_transit = payments_in_transit_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # 4. Bank Statement Balance
        statement_credits = BankStatementLine.objects.filter(
            business=business,
            bank_account=bank_account,
            transaction_date__lte=as_of,
            line_type='credit'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        statement_debits = BankStatementLine.objects.filter(
            business=business,
            bank_account=bank_account,
            transaction_date__lte=as_of,
            line_type='debit'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        statement_balance = opening + statement_credits - statement_debits

        # 5. Bank charges & fees on statement unmatched
        unmatched_bank_fees = BankStatementLine.objects.filter(
            business=business,
            bank_account=bank_account,
            transaction_date__lte=as_of,
            line_type='debit',
            status='unmatched'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # Adjusted Book Balance = Book Balance + Inflows in Transit - Outflows in Transit - Unmatched Bank Fees
        adjusted_book_balance = book_balance + total_inflows_in_transit - payments_in_transit - unmatched_bank_fees
        reconciliation_variance = statement_balance - adjusted_book_balance

        return {
            'as_of_date': as_of,
            'bank_account': bank_account,
            'opening_balance': opening,
            'total_banked': total_banked,
            'total_refunds': total_refunds,
            'total_expenses': total_expenses,
            'total_supplier_payments': total_supplier_payments,
            'book_balance': book_balance,
            'deposits_in_transit': deposits_in_transit,
            'refunds_in_transit': refunds_in_transit,
            'total_inflows_in_transit': total_inflows_in_transit,
            'payments_in_transit': payments_in_transit,
            'payments_in_transit_count': payments_in_transit_qs.count(),
            'unmatched_bank_fees': unmatched_bank_fees,
            'statement_credits': statement_credits,
            'statement_debits': statement_debits,
            'statement_balance': statement_balance,
            'adjusted_book_balance': adjusted_book_balance,
            'reconciliation_variance': reconciliation_variance,
            'is_balanced': abs(reconciliation_variance) < Decimal('0.01'),
        }
