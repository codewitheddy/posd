from decimal import Decimal
from datetime import date, datetime, time, timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum, Count, Q


class AttendanceService:

    DEFAULT_SHIFT_START = time(8, 0)  # 08:00
    DEFAULT_SHIFT_END = time(17, 0)   # 17:00
    LATE_THRESHOLD_MINUTES = 15

    @staticmethod
    def get_working_hours_policy(business):
        """Return configured shift policy for a business with safe defaults."""
        shift_start = AttendanceService.DEFAULT_SHIFT_START
        shift_end = AttendanceService.DEFAULT_SHIFT_END
        grace_minutes = AttendanceService.LATE_THRESHOLD_MINUTES
        overtime_rate_multiplier = Decimal('1.50')

        try:
            from pos.api import get_working_hours_settings
            biz_id = business.id if hasattr(business, 'id') else business
            settings_dict = get_working_hours_settings(biz_id)
            shift_start = settings_dict.get('workday_start_time') or shift_start
            shift_end = settings_dict.get('workday_end_time') or shift_end
            grace_minutes = settings_dict.get('late_grace_minutes', grace_minutes)
            overtime_rate_multiplier = settings_dict.get('overtime_rate_multiplier') or overtime_rate_multiplier
        except Exception:
            pass

        start_dt = datetime.combine(date.today(), shift_start)
        end_dt = datetime.combine(date.today(), shift_end)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        scheduled_hours = round(
            Decimal(str((end_dt - start_dt).total_seconds())) / Decimal('3600'),
            2,
        )

        return {
            'shift_start': shift_start,
            'shift_end': shift_end,
            'late_grace_minutes': grace_minutes,
            'scheduled_hours': max(Decimal('0.00'), scheduled_hours),
            'overtime_rate_multiplier': overtime_rate_multiplier,
        }

    @staticmethod
    def clock_in(employee):
        """Clock in an employee. Returns the Attendance record."""
        from hr.models import Attendance
        today = timezone.localdate()
        now_time = timezone.localtime().time()

        # Check for existing open record
        existing = Attendance.objects.filter(
            employee=employee, date=today, clock_out__isnull=True
        ).first()
        if existing:
            raise ValidationError("Employee is already clocked in today.")

        # Determine status using configured business shift policy.
        policy = AttendanceService.get_working_hours_policy(employee.business)
        shift_start = policy['shift_start']
        threshold_dt = datetime.combine(date.today(), shift_start) + timedelta(
            minutes=policy['late_grace_minutes']
        )
        status = 'late' if now_time > threshold_dt.time() else 'present'

        attendance = Attendance.objects.create(
            employee=employee,
            date=today,
            clock_in=now_time,
            status=status,
        )
        return attendance

    @staticmethod
    def clock_out(employee):
        """Clock out an employee. Computes total_hours. Returns the Attendance record."""
        from hr.models import Attendance
        today = timezone.localdate()
        now_time = timezone.localtime().time()

        attendance = Attendance.objects.filter(
            employee=employee, date=today, clock_out__isnull=True
        ).first()
        if not attendance:
            raise ValidationError("No open attendance record found for today.")

        attendance.clock_out = now_time

        # Compute total_hours as decimal hours rounded to 2dp
        clock_in_dt = datetime.combine(today, attendance.clock_in)
        clock_out_dt = datetime.combine(today, now_time)
        delta_seconds = (clock_out_dt - clock_in_dt).total_seconds()
        total_hours = round(Decimal(str(delta_seconds)) / Decimal('3600'), 2)
        attendance.total_hours = max(Decimal('0.00'), total_hours)
        attendance.save(update_fields=['clock_out', 'total_hours'])
        return attendance


class PayrollService:

    @staticmethod
    def calculate_period(business, period_start, period_end):
        """Create or update Payroll records for all active employees in the business using active StatutoryRuleSet."""
        from hr.models import Employee, Attendance, StaffAdvance, Payroll, StatutoryRuleSet
        from datetime import timedelta

        employees = Employee.objects.filter(business=business, status='active')
        payrolls = []
        policy = AttendanceService.get_working_hours_policy(business)
        scheduled_hours_per_day = policy['scheduled_hours']
        overtime_multiplier = policy['overtime_rate_multiplier']

        # Resolve active statutory ruleset for this business and date
        ruleset = StatutoryRuleSet.get_active_ruleset(business, target_date=period_end)

        # Calculate number of working days in period
        total_days = (period_end - period_start).days + 1
        working_days = sum(1 for d in range(total_days) if (period_start + timedelta(days=d)).weekday() < 5)  # Mon-Fri
        period_ratio = Decimal(str(working_days)) / Decimal('26') if working_days > 0 else Decimal('0.00')

        for employee in employees:
            # Sum attendance hours in period (present or late statuses)
            attendance_qs = Attendance.objects.filter(
                employee=employee,
                date__gte=period_start,
                date__lte=period_end,
                status__in=('present', 'late'),
            )
            attendance_data = attendance_qs.aggregate(total=Sum('total_hours'))
            total_hours = attendance_data['total'] or Decimal('0.00')

            # Overtime is computed per attended day above configured scheduled hours.
            overtime_hours = Decimal('0.00')
            if scheduled_hours_per_day > 0:
                for record in attendance_qs:
                    worked = record.total_hours or Decimal('0.00')
                    overtime_hours += max(Decimal('0.00'), worked - scheduled_hours_per_day)

            # Calculate basic salary: monthly basic salary is prorated to days in period.
            if employee.basic_salary > 0:
                basic_salary = round(employee.basic_salary * period_ratio, 2)
            else:
                hourly_rate = employee.hourly_rate or Decimal('0.00')
                basic_salary = total_hours * hourly_rate

            # Fixed monthly allowances are also prorated for partial periods.
            house_allowance = round(employee.house_allowance * period_ratio, 2)
            transport_allowance = round(employee.transport_allowance * period_ratio, 2)
            medical_allowance = round(employee.medical_allowance * period_ratio, 2)
            other_allowance = round(employee.other_allowance * period_ratio, 2)
            other_allowances_total = round(employee.total_other_allowances * period_ratio, 2)

            overtime_amount = overtime_hours * (employee.effective_hourly_rate * overtime_multiplier)

            # Calculate gross before deductions
            gross = basic_salary + house_allowance + transport_allowance + medical_allowance + other_allowance + other_allowances_total + overtime_amount

            # Calculate absence deduction
            absent_days = Attendance.objects.filter(
                employee=employee,
                date__gte=period_start,
                date__lte=period_end,
                status='absent',
            ).count()
            if employee.basic_salary > 0:
                daily_rate = employee.basic_salary / Decimal('26')  # 26 working days per month
            else:
                daily_rate = employee.effective_hourly_rate * Decimal('8')  # 8 hours per day
            absence_deduction = absent_days * daily_rate

            # Active advances
            active_advances = StaffAdvance.objects.filter(employee=employee, status='active')
            advances_deducted = sum(
                (a.deduction_per_month for a in active_advances), Decimal('0.00')
            )

            # Calculate statutory deductions using active StatutoryRuleSet
            nssf_emp, nssf_empr = PayrollService._calculate_nssf(gross, ruleset)
            shif = PayrollService._calculate_shif(gross, ruleset)
            hl_emp, hl_empr = PayrollService._calculate_housing_levy(gross, ruleset)
            nita_empr = PayrollService._calculate_nita(ruleset)

            # PAYE Tax calculation (Income Tax Act Cap 470)
            paye = PayrollService._calculate_paye_monthly(gross, nssf_emp, shif, employee, ruleset)

            # Total employee deductions
            total_deductions = paye + shif + nssf_emp + hl_emp + absence_deduction + advances_deducted

            # Net salary
            net_salary = max(Decimal('0.00'), gross - total_deductions)

            payroll, _ = Payroll.objects.update_or_create(
                employee=employee,
                period_start=period_start,
                period_end=period_end,
                defaults={
                    'ruleset_used': ruleset,
                    'basic_salary': basic_salary,
                    'house_allowance': house_allowance,
                    'transport_allowance': transport_allowance,
                    'medical_allowance': medical_allowance,
                    'other_allowance': other_allowance,
                    'other_allowances_total': other_allowances_total,
                    'overtime_hours': overtime_hours,
                    'overtime_amount': overtime_amount,
                    'bonus': Decimal('0.00'),
                    'commission': Decimal('0.00'),
                    'paye': paye,
                    'shif': shif,
                    'nssf': nssf_emp,
                    'housing_levy': hl_emp,
                    'employer_nssf': nssf_empr,
                    'employer_housing_levy': hl_empr,
                    'employer_nita': nita_empr,
                    'absence_deduction': absence_deduction,
                    'other_deductions': Decimal('0.00'),
                    'advances_deducted': advances_deducted,
                    'net_salary': net_salary,
                    'status': 'pending',
                }
            )
            payrolls.append(payroll)

        return payrolls

    @staticmethod
    def _calculate_paye_monthly(gross, nssf_emp, shif, employee, ruleset):
        """
        Compute monthly PAYE under Kenya Income Tax Act Cap 470 with progressive brackets and reliefs.
        """
        g = Decimal(str(gross))
        
        # Check disability exemption (NCPWD) - First KES 150,000 exempt
        if employee.disability_status:
            pwd_relief = ruleset.relief_rules.filter(relief_type='disability').first()
            exempt_limit = pwd_relief.monthly_amount if pwd_relief else Decimal('150000.00')
            if g <= exempt_limit:
                return Decimal('0.00')
            taxable_income = g - exempt_limit
        else:
            # Allowable deduction: NSSF employee contribution
            taxable_income = max(Decimal('0.00'), g - nssf_emp)

        # Apply progressive tax bands from ruleset
        bands = ruleset.paye_bands.all().order_by('band_order')
        tax = Decimal('0.00')
        
        if not bands.exists():
            # Fallback default 2026 monthly bands if none defined in DB
            bands_data = [
                (Decimal('0.00'), Decimal('24000.00'), Decimal('10.00')),
                (Decimal('24000.01'), Decimal('32333.00'), Decimal('25.00')),
                (Decimal('32333.01'), Decimal('500000.00'), Decimal('30.00')),
                (Decimal('500000.01'), Decimal('800000.00'), Decimal('32.50')),
                (Decimal('800000.01'), None, Decimal('35.00')),
            ]
            remaining = taxable_income
            for lower, upper, rate in bands_data:
                if remaining <= Decimal('0.00'):
                    break
                band_capacity = (upper - lower + Decimal('0.01')) if upper else remaining
                taxable_in_band = min(remaining, band_capacity)
                tax += taxable_in_band * (rate / Decimal('100.00'))
                remaining -= taxable_in_band
        else:
            # Calculate tax using database-configured bands
            for band in bands:
                if taxable_income <= band.lower_limit:
                    continue
                if band.upper_limit:
                    taxable_in_band = min(taxable_income, band.upper_limit) - band.lower_limit
                else:
                    taxable_in_band = taxable_income - band.lower_limit
                if taxable_in_band > Decimal('0.00'):
                    tax += taxable_in_band * (band.rate_percentage / Decimal('100.00'))

        # Reliefs:
        # 1. Personal Relief: KES 2,400/month (not applicable to secondary employees or non-residents)
        personal_relief = Decimal('0.00')
        if not employee.is_secondary_employee and not employee.is_non_resident:
            pr_rule = ruleset.relief_rules.filter(relief_type='personal').first()
            personal_relief = pr_rule.monthly_amount if pr_rule else Decimal('2400.00')

        # 2. Insurance Relief: 15% of SHIF up to monthly cap (KES 5,000)
        ins_rule = ruleset.relief_rules.filter(relief_type='insurance').first()
        ins_pct = (ins_rule.percentage / Decimal('100.00')) if ins_rule and ins_rule.percentage > 0 else Decimal('0.15')
        ins_cap = ins_rule.maximum_monthly_limit if ins_rule and ins_rule.maximum_monthly_limit > 0 else Decimal('5000.00')
        insurance_relief = min(shif * ins_pct, ins_cap)

        net_paye = max(Decimal('0.00'), tax - personal_relief - insurance_relief)
        return round(net_paye, 2)

    @staticmethod
    def _calculate_shif(gross_monthly, ruleset):
        """
        SHIF (Social Health Insurance Fund) — 2.75% of gross salary (Min KES 300).
        """
        g = Decimal(str(gross_monthly))
        shif_rule = getattr(ruleset, 'shif_rule', None)
        pct = (shif_rule.percentage_rate / Decimal('100.00')) if shif_rule else Decimal('0.0275')
        min_contrib = shif_rule.minimum_contribution if shif_rule else Decimal('300.00')
        max_contrib = shif_rule.maximum_contribution if shif_rule and shif_rule.maximum_contribution else None

        calculated = g * pct
        result = max(min_contrib, calculated)
        if max_contrib:
            result = min(result, max_contrib)
        return round(result, 2)

    @staticmethod
    def _calculate_housing_levy(gross_monthly, ruleset):
        """
        Affordable Housing Levy (Affordable Housing Act 2024) — 1.5% employee + 1.5% employer.
        """
        g = Decimal(str(gross_monthly))
        hl_rule = getattr(ruleset, 'housing_levy_rule', None)
        emp_rate = (hl_rule.employee_rate / Decimal('100.00')) if hl_rule else Decimal('0.015')
        empr_rate = (hl_rule.employer_rate / Decimal('100.00')) if hl_rule else Decimal('0.015')

        return round(g * emp_rate, 2), round(g * empr_rate, 2)

    @staticmethod
    def _calculate_nssf(gross_monthly, ruleset):
        """
        NSSF Act 2013 Tier I + Tier II limits with employee & matching employer portions.
        """
        g = Decimal(str(gross_monthly))
        tier1_rule = ruleset.nssf_tiers.filter(tier_name='tier_1').first()
        tier2_rule = ruleset.nssf_tiers.filter(tier_name='tier_2').first()

        t1_limit = tier1_rule.upper_limit if tier1_rule else Decimal('9000.00')
        t1_rate = (tier1_rule.employee_rate / Decimal('100.00')) if tier1_rule else Decimal('0.06')
        t1_emp_max = tier1_rule.max_employee_deduction if tier1_rule else Decimal('540.00')
        t1_empr_max = tier1_rule.max_employer_contribution if tier1_rule else Decimal('540.00')

        t2_limit = tier2_rule.upper_limit if tier2_rule else Decimal('108000.00')
        t2_rate = (tier2_rule.employee_rate / Decimal('100.00')) if tier2_rule else Decimal('0.06')
        t2_emp_max = tier2_rule.max_employee_deduction if tier2_rule else Decimal('5940.00')
        t2_empr_max = tier2_rule.max_employer_contribution if tier2_rule else Decimal('5940.00')

        # Tier 1
        t1_base = min(g, t1_limit)
        t1_emp = min(t1_base * t1_rate, t1_emp_max)
        t1_empr = min(t1_base * t1_rate, t1_empr_max)

        # Tier 2
        t2_base = max(Decimal('0.00'), min(g, t2_limit) - t1_limit)
        t2_emp = min(t2_base * t2_rate, t2_emp_max)
        t2_empr = min(t2_base * t2_rate, t2_empr_max)

        total_emp = round(t1_emp + t2_emp, 2)
        total_empr = round(t1_empr + t2_empr, 2)
        return total_emp, total_empr

    @staticmethod
    def _calculate_nita(ruleset):
        """
        NITA training employer levy (flat KES 50 per employee per month).
        """
        nita_rule = getattr(ruleset, 'nita_rule', None)
        return nita_rule.monthly_employer_levy if nita_rule else Decimal('50.00')

    @staticmethod
    def mark_paid(payroll):
        """Mark a payroll record as paid and update advance balances."""
        from hr.models import StaffAdvance
        if payroll.status == 'paid':
            raise ValidationError("Payroll record is already paid and cannot be modified.")

        payroll.pay_date = timezone.localdate()
        payroll.status = 'paid'
        payroll.save(update_fields=['pay_date', 'status'])

        # Reduce advance balances
        active_advances = StaffAdvance.objects.filter(
            employee=payroll.employee, status='active'
        )
        for advance in active_advances:
            deduction = min(advance.deduction_per_month, advance.balance_remaining)
            advance.balance_remaining -= deduction
            if advance.balance_remaining <= Decimal('0.00'):
                advance.balance_remaining = Decimal('0.00')
                advance.status = 'settled'
            advance.save(update_fields=['balance_remaining', 'status'])

        return payroll


class PerformanceService:

    @staticmethod
    def generate_period(business, period_start, period_end):
        """Generate or update PerformanceRecord for all active employees."""
        from hr.models import Employee, PerformanceRecord
        from pos.api import get_cashier_performance_metrics

        employees = Employee.objects.filter(business=business, status='active')
        records = []
        biz_id = business.id if hasattr(business, 'id') else business

        # Compute metrics per employee via POS public API
        sales_counts = {}
        for employee in employees:
            cashier_id = employee.user_account_id if employee.user_account else None
            metrics = get_cashier_performance_metrics(
                business_id=biz_id,
                cashier_user_id=cashier_id,
                period_start=period_start,
                period_end=period_end,
            )
            sales_counts[employee.pk] = metrics

        # Performance score relative to max sales in period, clamped to [0, 100]
        max_sales = max((v['total_sales'] for v in sales_counts.values()), default=0)

        for employee in employees:
            data = sales_counts[employee.pk]
            if max_sales > 0:
                score = round(
                    Decimal(str(data['total_sales'])) / Decimal(str(max_sales)) * 100, 2
                )
            else:
                score = Decimal('0.00')
            score = max(Decimal('0.00'), min(Decimal('100.00'), score))

            record, _ = PerformanceRecord.objects.update_or_create(
                employee=employee,
                period_start=period_start,
                period_end=period_end,
                defaults={
                    'total_sales': data['total_sales'],
                    'total_transactions': data['total_transactions'],
                    'total_discounts_given': data['total_discounts_given'],
                    'total_voids': data['total_voids'],
                    'total_refunds': data['total_refunds'],
                    'shift_shortages': data['shift_shortages'],
                    'performance_score': score,
                }
            )
            records.append(record)

        return records


class PayrollAccountingService:
    """
    Integrates HR Payroll runs into Accounting General Ledger journals.
    Ensures that Kenyan statutory payroll (PAYE, NSSF, SHIF, Housing Levy, NITA, HELB, Advances)
    posts as an auto-balancing double-entry journal via accounting.api.
    """

    @staticmethod
    def post_payroll_to_gl(business, period_start: date, period_end: date, user=None):
        """
        Aggregates payroll records for a period and posts a balanced journal to the General Ledger.
        """
        import logging
        logger = logging.getLogger(__name__)

        from hr.models import Payroll, HRGLMapping
        from pos.models import _get_or_create_core_company_and_branch
        from accounting import api

        payrolls = Payroll.objects.filter(
            employee__business=business,
            period_start=period_start,
            period_end=period_end
        )

        if not payrolls.exists():
            logger.warning("No payroll records found for %s (%s to %s)", business, period_start, period_end)
            return None

        company, core_branch = _get_or_create_core_company_and_branch(business)
        if not company:
            logger.warning("Cannot post Payroll to Accounting: Core Company not found.")
            return None

        mapping = HRGLMapping.get_for_business(business)

        # Financial totals
        total_gross = Decimal('0.00')
        total_empr_nssf = Decimal('0.00')
        total_empr_hl = Decimal('0.00')
        total_empr_nita = Decimal('0.00')

        total_net = Decimal('0.00')
        total_paye = Decimal('0.00')
        total_shif = Decimal('0.00')
        total_emp_nssf = Decimal('0.00')
        total_emp_hl = Decimal('0.00')
        total_helb = Decimal('0.00')
        total_advances = Decimal('0.00')
        total_other_ded = Decimal('0.00')

        for p in payrolls:
            total_gross += p.gross_salary
            total_empr_nssf += p.employer_nssf
            total_empr_hl += p.employer_housing_levy
            total_empr_nita += p.employer_nita

            total_net += p.net_salary
            total_paye += p.paye
            total_shif += p.shif
            total_emp_nssf += p.nssf
            total_emp_hl += p.housing_levy
            total_helb += p.helb_deduction
            total_advances += p.advances_deducted
            total_other_ded += (p.absence_deduction + p.other_deductions)

        # Construct double-entry lines
        lines = []

        # 1. Debits (Expenses)
        if total_gross > Decimal('0.00'):
            lines.append({
                'account_code': mapping.basic_salaries_expense_code,
                'debit': total_gross,
                'credit': Decimal('0.00'),
                'description': f"Gross Salaries & Allowances ({period_start.strftime('%b %Y')})",
            })

        if total_empr_nssf > Decimal('0.00'):
            lines.append({
                'account_code': mapping.employer_nssf_expense_code,
                'debit': total_empr_nssf,
                'credit': Decimal('0.00'),
                'description': f"Employer NSSF Matching Contribution ({period_start.strftime('%b %Y')})",
            })

        if total_empr_hl > Decimal('0.00'):
            lines.append({
                'account_code': mapping.employer_housing_levy_expense_code,
                'debit': total_empr_hl,
                'credit': Decimal('0.00'),
                'description': f"Employer Affordable Housing Levy ({period_start.strftime('%b %Y')})",
            })

        if total_empr_nita > Decimal('0.00'):
            lines.append({
                'account_code': mapping.employer_nita_expense_code,
                'debit': total_empr_nita,
                'credit': Decimal('0.00'),
                'description': f"Employer NITA Training Levy ({period_start.strftime('%b %Y')})",
            })

        # 2. Credits (Payables & Asset deductions)
        if total_net > Decimal('0.00'):
            lines.append({
                'account_code': mapping.net_salaries_payable_code,
                'debit': Decimal('0.00'),
                'credit': total_net,
                'description': f"Net Salaries Payable to Staff ({period_start.strftime('%b %Y')})",
            })

        if total_paye > Decimal('0.00'):
            lines.append({
                'account_code': mapping.paye_payable_code,
                'debit': Decimal('0.00'),
                'credit': total_paye,
                'description': f"KRA PAYE Withholding Tax Payable ({period_start.strftime('%b %Y')})",
            })

        total_nssf_combined = total_emp_nssf + total_empr_nssf
        if total_nssf_combined > Decimal('0.00'):
            lines.append({
                'account_code': mapping.nssf_payable_code,
                'debit': Decimal('0.00'),
                'credit': total_nssf_combined,
                'description': f"NSSF Statutory Remittance (Emp + Empr) ({period_start.strftime('%b %Y')})",
            })

        if total_shif > Decimal('0.00'):
            lines.append({
                'account_code': mapping.shif_payable_code,
                'debit': Decimal('0.00'),
                'credit': total_shif,
                'description': f"SHIF Statutory Health Remittance ({period_start.strftime('%b %Y')})",
            })

        total_hl_combined = total_emp_hl + total_empr_hl
        if total_hl_combined > Decimal('0.00'):
            lines.append({
                'account_code': mapping.housing_levy_payable_code,
                'debit': Decimal('0.00'),
                'credit': total_hl_combined,
                'description': f"KRA Affordable Housing Levy (Emp + Empr) ({period_start.strftime('%b %Y')})",
            })

        if total_helb > Decimal('0.00'):
            lines.append({
                'account_code': mapping.helb_payable_code,
                'debit': Decimal('0.00'),
                'credit': total_helb,
                'description': f"HELB Higher Education Loan Deductions ({period_start.strftime('%b %Y')})",
            })

        if total_advances > Decimal('0.00'):
            lines.append({
                'account_code': mapping.staff_advances_asset_code,
                'debit': Decimal('0.00'),
                'credit': total_advances,
                'description': f"Recovery of Staff Salary Advances ({period_start.strftime('%b %Y')})",
            })

        if total_other_ded > Decimal('0.00'):
            lines.append({
                'account_code': mapping.basic_salaries_expense_code,
                'debit': Decimal('0.00'),
                'credit': total_other_ded,
                'description': f"Absence & Sundry Payroll Deductions ({period_start.strftime('%b %Y')})",
            })

        if total_empr_nita > Decimal('0.00'):
            nita_code = getattr(mapping, 'nita_payable_code', '2160') or '2160'
            lines.append({
                'account_code': nita_code,
                'debit': Decimal('0.00'),
                'credit': total_empr_nita,
                'description': f"NITA Training Levy Payable ({period_start.strftime('%b %Y')})",
            })

        if len(lines) < 2:
            return None

        biz_id = business.pk if hasattr(business, 'pk') else business
        source_ref = f"PAYROLL-{period_start.strftime('%Y%m')}-{biz_id}"
        idempotency_key = f"hr:payroll:{biz_id}:{period_start}:{period_end}"
        narration = f"Payroll Run {period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')} ({payrolls.count()} staff)"

        payload = {
            'source_module': 'hr',
            'source_ref': source_ref,
            'date': period_end.isoformat(),
            'narration': narration,
            'lines': lines,
            'entry_type': 'payroll',
            'idempotency_key': idempotency_key,
        }

        try:
            entry = api.post_journal(
                company=company,
                source_module='hr',
                source_ref=source_ref,
                date_val=period_end,
                lines=lines,
                narration=narration,
                posted_by=user,
                idempotency_key=idempotency_key,
                branch=core_branch,
                entry_type='payroll',
            )
            return entry
        except Exception as e:
            logger.error("Failed to post Payroll to GL (%s). Queueing for exception review.", e)
            queue_item = api.queue_posting(
                company=company,
                payload=payload,
                source_module='hr',
                source_ref=source_ref,
                idempotency_key=idempotency_key,
                process_immediately=False,
            )
            queue_item.status = 'failed'
            queue_item.error_message = str(e)
            queue_item.save(update_fields=['status', 'error_message'])
            return queue_item

