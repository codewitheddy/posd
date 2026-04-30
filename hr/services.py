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
            from pos.models import BusinessSettings
            settings = BusinessSettings.get_settings(business)
            shift_start = settings.workday_start_time or shift_start
            shift_end = settings.workday_end_time or shift_end
            grace_minutes = settings.late_grace_minutes
            overtime_rate_multiplier = settings.overtime_rate_multiplier or overtime_rate_multiplier
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
        """Create or update Payroll records for all active employees in the business."""
        from hr.models import Employee, Attendance, StaffAdvance, Payroll, Leave
        from datetime import timedelta

        employees = Employee.objects.filter(business=business, status='active')
        payrolls = []
        policy = AttendanceService.get_working_hours_policy(business)
        scheduled_hours_per_day = policy['scheduled_hours']
        overtime_multiplier = policy['overtime_rate_multiplier']

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

            # Calculate statutory deductions (2026 Kenya rules)
            nssf = PayrollService._calculate_nssf(gross)
            shif = PayrollService._calculate_shif(gross)
            housing_levy = PayrollService._calculate_housing_levy(gross)
            # PAYE taxable = gross - NSSF; insurance relief = 15% of SHIF
            taxable_annual = (gross - nssf) * 12
            annual_paye = PayrollService._calculate_paye(taxable_annual, annual_shif=shif * 12)
            paye = annual_paye / 12

            # Total deductions
            total_deductions = paye + shif + nssf + housing_levy + absence_deduction + advances_deducted

            # Net salary
            net_salary = max(Decimal('0.00'), gross - total_deductions)

            payroll, _ = Payroll.objects.update_or_create(
                employee=employee,
                period_start=period_start,
                period_end=period_end,
                defaults={
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
                    'nssf': nssf,
                    'housing_levy': housing_levy,
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
    def _calculate_paye(annual_taxable, annual_shif=Decimal('0.00')):
        """
        Calculate annual PAYE — Kenya 2026.
        Taxable = Gross - NSSF (employee portion).
        Bands: 0-288,000 @ 10%, 288,001-388,000 @ 25%, 388,001-6,000,000 @ 30%,
               6,000,001-9,600,000 @ 32.5%, above 9,600,000 @ 35%.
        Reliefs: Personal KES 28,800/year; Insurance relief 15% of annual SHIF.
        """
        g = Decimal(str(annual_taxable))
        tax = Decimal('0')
        bands = [
            (Decimal('288000'), Decimal('0.10')),
            (Decimal('100000'), Decimal('0.25')),   # 288,001 – 388,000
            (Decimal('5612000'), Decimal('0.30')),  # 388,001 – 6,000,000
            (Decimal('3600000'), Decimal('0.325')), # 6,000,001 – 9,600,000
        ]
        remaining = g
        for band_size, rate in bands:
            if remaining <= 0:
                break
            taxable = min(remaining, band_size)
            tax += taxable * rate
            remaining -= taxable
        if remaining > 0:
            tax += remaining * Decimal('0.35')
        # Personal relief (KES 28,800/year = 2,400/month)
        personal_relief = Decimal('28800')
        # Insurance relief: 15% of annual SHIF contributions
        insurance_relief = Decimal(str(annual_shif)) * Decimal('0.15')
        tax = max(Decimal('0'), tax - personal_relief - insurance_relief)
        return tax

    @staticmethod
    def _calculate_shif(gross_monthly):
        """
        SHIF (Social Health Insurance Fund) — 2026.
        Flat rate: 2.75% of gross salary. No cap.
        """
        return round(Decimal(str(gross_monthly)) * Decimal('0.0275'), 2)

    @staticmethod
    def _calculate_housing_levy(gross_monthly):
        """
        Affordable Housing Levy (employee portion) — 2026.
        Flat rate: 1.5% of gross salary.
        """
        return round(Decimal(str(gross_monthly)) * Decimal('0.015'), 2)

    @staticmethod
    def _calculate_nssf(gross_monthly):
        """
        NSSF Tier I + Tier II — February 2026 limits.
        Tier I : 6% of first KES 9,000   (max KES 540).
        Tier II: 6% of KES 9,001–108,000 (max KES 5,940).
        Total max: KES 6,480.
        """
        g = Decimal(str(gross_monthly))
        tier1 = min(g, Decimal('9000')) * Decimal('0.06')
        tier2 = max(Decimal('0'), min(g, Decimal('108000')) - Decimal('9000')) * Decimal('0.06')
        return tier1 + tier2

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
        from pos.models import Sale, SaleReturn, Shift

        employees = Employee.objects.filter(business=business, status='active')
        records = []

        # Compute metrics per employee
        sales_counts = {}
        for employee in employees:
            sales_qs = Sale.objects.filter(
                business=business,
                cashier=employee.user_account,
                date__date__gte=period_start,
                date__date__lte=period_end,
            )
            total_sales = sales_qs.count()
            total_transactions = sales_qs.aggregate(
                items=Sum('items__quantity')
            )['items'] or 0
            total_discounts = sales_qs.aggregate(
                disc=Sum('discount_amount')
            )['disc'] or Decimal('0.00')
            total_voids = sales_qs.filter(total=0).count()
            total_refunds = SaleReturn.objects.filter(
                original_sale__cashier=employee.user_account,
                return_date__date__gte=period_start,
                return_date__date__lte=period_end,
            ).count()

            shift_shortages = Shift.objects.filter(
                cashier=employee.user_account,
                start_time__date__gte=period_start,
                start_time__date__lte=period_end,
                cash_difference__lt=0,
            ).aggregate(total=Sum('cash_difference'))['total'] or Decimal('0.00')

            sales_counts[employee.pk] = {
                'total_sales': total_sales,
                'total_transactions': int(total_transactions),
                'total_discounts_given': Decimal(str(total_discounts)),
                'total_voids': total_voids,
                'total_refunds': total_refunds,
                'shift_shortages': abs(Decimal(str(shift_shortages))),
            }

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
