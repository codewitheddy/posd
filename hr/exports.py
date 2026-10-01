"""
Republic of Kenya Statutory Returns & Banking File Exporters
Outputs official CSV and data structures for KRA iTax, NSSF, SHA, Housing Levy, EFT and M-Pesa.
"""
import csv
import io
from decimal import Decimal
from datetime import date
from django.db.models import Sum


def generate_kra_itax_paye_csv(payrolls, business, period_start, period_end):
    """
    Generate KRA iTax Monthly PAYE Return CSV (P10 format).
    Header: PIN of Employee, Name of Employee, Residential Status, Type of Employee,
            Basic Salary, Housing Allowance, Transport Allowance, Other Allowances,
            Total Cash Pay, Value of Non-Cash Benefit, Value of Quarters, Total Gross Pay,
            Defined Pension Contribution (Actual), Defined Pension Contribution (Fixed),
            Owner Occupied Interest, Post-Retirement Medical, Allowable Deductions,
            Taxable Pay, Tax Payable, Monthly Personal Relief, Insurance Relief,
            PAYE Deducted (Tax Paid).
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # File metadata header
    writer.writerow(["KRA iTax Monthly PAYE Return (Form P10)"])
    writer.writerow(["Employer Name", business.name])
    writer.writerow(["Employer PIN", getattr(business, 'kra_pin', 'P051234567Z')])
    writer.writerow(["Return Period", f"{period_start.strftime('%d/%m/%Y')} to {period_end.strftime('%d/%m/%Y')}"])
    writer.writerow([])

    # Table columns
    headers = [
        "PIN of Employee",
        "Name of Employee",
        "National ID No",
        "Residential Status",
        "Employment Type",
        "Basic Salary (KES)",
        "House Allowance (KES)",
        "Transport Allowance (KES)",
        "Other Allowances (KES)",
        "Overtime & Bonus (KES)",
        "Total Gross Pay (KES)",
        "NSSF Employee Contribution (KES)",
        "Allowable Deductions (KES)",
        "Taxable Pay (KES)",
        "Tax Charged (KES)",
        "Monthly Personal Relief (KES)",
        "Insurance Relief (KES)",
        "PAYE Tax Deducted (KES)"
    ]
    writer.writerow(headers)

    for p in payrolls:
        emp = p.employee
        pin = emp.kra_pin or "NO_PIN"
        name = emp.get_full_name()
        id_num = emp.id_number or ""
        res_status = "Non-Resident" if emp.is_non_resident else "Resident"
        emp_type = "Secondary" if emp.is_secondary_employee else "Primary"
        
        other_all = p.other_allowance + p.other_allowances_total
        overtime_bonus = p.overtime_amount + p.bonus + p.commission
        taxable_pay = max(Decimal('0.00'), p.gross_salary - p.nssf)
        
        # Approximate tax charged before relief for reporting
        personal_relief = Decimal('0.00') if emp.is_secondary_employee or emp.is_non_resident else Decimal('2400.00')
        insurance_relief = min(p.shif * Decimal('0.15'), Decimal('5000.00'))
        tax_charged = p.paye + personal_relief + insurance_relief if p.paye > Decimal('0.00') else Decimal('0.00')

        writer.writerow([
            pin,
            name,
            id_num,
            res_status,
            emp_type,
            f"{p.basic_salary:.2f}",
            f"{p.house_allowance:.2f}",
            f"{p.transport_allowance:.2f}",
            f"{other_all:.2f}",
            f"{overtime_bonus:.2f}",
            f"{p.gross_salary:.2f}",
            f"{p.nssf:.2f}",
            f"{p.nssf:.2f}",
            f"{taxable_pay:.2f}",
            f"{tax_charged:.2f}",
            f"{personal_relief:.2f}",
            f"{insurance_relief:.2f}",
            f"{p.paye:.2f}",
        ])

    return output.getvalue()


def generate_nssf_return_csv(payrolls, business, period_start, period_end):
    """
    Generate NSSF Act 2013 Monthly Contribution Return CSV.
    Columns: Payroll Number, National ID, Employee Name, KRA PIN, NSSF Number,
             Gross Pay, Voluntary Contribution, Tier I Employee, Tier I Employer,
             Tier II Employee, Tier II Employer, Total NSSF Remittance.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["NSSF Act 2013 Monthly Contribution Schedule"])
    writer.writerow(["Employer Name", business.name])
    writer.writerow(["Period", f"{period_start.strftime('%B %Y')}"])
    writer.writerow([])

    headers = [
        "Payroll No / Staff Code",
        "National ID No",
        "Employee Name",
        "KRA PIN",
        "NSSF Number",
        "Gross Pay (KES)",
        "Tier I Employee (KES)",
        "Tier I Employer (KES)",
        "Tier II Employee (KES)",
        "Tier II Employer (KES)",
        "Total Employee (KES)",
        "Total Employer (KES)",
        "Total Remittance (KES)"
    ]
    writer.writerow(headers)

    for p in payrolls:
        emp = p.employee
        gross = p.gross_salary
        # Split Tier I (max 540) and Tier II (up to 5940)
        tier1_base = min(gross, Decimal('9000.00'))
        tier1 = min(tier1_base * Decimal('0.06'), Decimal('540.00'))
        tier2 = max(Decimal('0.00'), p.nssf - tier1)
        total_remit = p.nssf + p.employer_nssf

        writer.writerow([
            emp.staff_code or f"EMP{emp.pk:03d}",
            emp.id_number or "",
            emp.get_full_name(),
            emp.kra_pin or "",
            emp.nssf_number or "",
            f"{gross:.2f}",
            f"{tier1:.2f}",
            f"{tier1:.2f}",
            f"{tier2:.2f}",
            f"{tier2:.2f}",
            f"{p.nssf:.2f}",
            f"{p.employer_nssf:.2f}",
            f"{total_remit:.2f}",
        ])

    return output.getvalue()


def generate_sha_return_csv(payrolls, business, period_start, period_end):
    """
    Generate Social Health Authority (SHA / SHIF) Monthly Return CSV.
    Rate: 2.75% of Gross Salary.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Social Health Authority (SHA / SHIF) Monthly Contribution Return"])
    writer.writerow(["Employer Name", business.name])
    writer.writerow(["Period", f"{period_start.strftime('%B %Y')}"])
    writer.writerow([])

    headers = [
        "Staff Code",
        "National ID No",
        "Employee Name",
        "KRA PIN",
        "SHA / SHIF Number",
        "Legacy NHIF Number",
        "Gross Salary (KES)",
        "Rate (%)",
        "SHA Contribution (KES)"
    ]
    writer.writerow(headers)

    for p in payrolls:
        emp = p.employee
        writer.writerow([
            emp.staff_code or f"EMP{emp.pk:03d}",
            emp.id_number or "",
            emp.get_full_name(),
            emp.kra_pin or "",
            emp.sha_number or emp.nhif_number or "",
            emp.nhif_number or "",
            f"{p.gross_salary:.2f}",
            "2.75%",
            f"{p.shif:.2f}",
        ])

    return output.getvalue()


def generate_housing_levy_return_csv(payrolls, business, period_start, period_end):
    """
    Generate Affordable Housing Levy (Affordable Housing Act 2024) Return CSV.
    1.5% Employee + 1.5% Employer matching on Gross Salary.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Affordable Housing Levy Monthly Declaration (AHA 2024)"])
    writer.writerow(["Employer Name", business.name])
    writer.writerow(["Period", f"{period_start.strftime('%B %Y')}"])
    writer.writerow([])

    headers = [
        "Staff Code",
        "National ID No",
        "Employee Name",
        "KRA PIN",
        "Gross Monthly Pay (KES)",
        "Employee Deduction (1.5%) (KES)",
        "Employer Matching (1.5%) (KES)",
        "Total Housing Levy Remittance (KES)"
    ]
    writer.writerow(headers)

    for p in payrolls:
        emp = p.employee
        total_hl = p.housing_levy + p.employer_housing_levy
        writer.writerow([
            emp.staff_code or f"EMP{emp.pk:03d}",
            emp.id_number or "",
            emp.get_full_name(),
            emp.kra_pin or "",
            f"{p.gross_salary:.2f}",
            f"{p.housing_levy:.2f}",
            f"{p.employer_housing_levy:.2f}",
            f"{total_hl:.2f}",
        ])

    return output.getvalue()


def generate_bank_eft_csv(payrolls, business):
    """
    Generate Bank EFT / RTGS salary payment upload batch CSV for Kenyan commercial banks.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "Bank Code",
        "Bank Name",
        "Branch Sort Code",
        "Branch Name",
        "Account Number",
        "Account Name",
        "Payment Amount (KES)",
        "Payment Reference"
    ]
    writer.writerow(headers)

    for p in payrolls:
        emp = p.employee
        if p.net_salary > Decimal('0.00'):
            writer.writerow([
                emp.bank_code or "01",
                emp.bank_name or "Commercial Bank",
                emp.bank_branch_code or "000",
                emp.bank_branch or "Main",
                emp.bank_account_number or "",
                emp.get_full_name(),
                f"{p.net_salary:.2f}",
                f"SALARY-{p.period_end.strftime('%m%Y')}"
            ])

    return output.getvalue()


def generate_mpesa_b2c_csv(payrolls, business):
    """
    Generate Safaricom M-Pesa Bulk Salary Payment (B2C) upload file.
    Format: Phone Number, Amount, Reference, Remarks.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "Phone Number",
        "Amount (KES)",
        "Reference",
        "Recipient Name"
    ]
    writer.writerow(headers)

    for p in payrolls:
        emp = p.employee
        phone = emp.mpesa_number or emp.phone_number
        if phone and p.net_salary > Decimal('0.00'):
            # Format phone to 2547XXXXXXXX
            clean_phone = phone.replace('+', '').replace(' ', '').strip()
            if clean_phone.startswith('0'):
                clean_phone = '254' + clean_phone[1:]
            elif clean_phone.startswith('7') or clean_phone.startswith('1'):
                clean_phone = '254' + clean_phone

            writer.writerow([
                clean_phone,
                f"{p.net_salary:.2f}",
                f"SAL-{p.period_end.strftime('%b%y').upper()}",
                emp.get_full_name()
            ])

    return output.getvalue()


def get_p9_annual_data(employee, tax_year):
    """
    Calculate 12-month calendar data and totals for KRA Tax Form P9A.
    """
    from hr.models import Payroll

    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    monthly_data = []
    totals = {
        'basic_salary': Decimal('0.00'),
        'benefits': Decimal('0.00'),
        'quarters': Decimal('0.00'),
        'gross_pay': Decimal('0.00'),
        'nssf_actual': Decimal('0.00'),
        'nssf_fixed': Decimal('0.00'),
        'nssf_percent': Decimal('0.00'),
        'mortgage_interest': Decimal('0.00'),
        'post_retirement': Decimal('0.00'),
        'allowable_deductions': Decimal('0.00'),
        'taxable_pay': Decimal('0.00'),
        'tax_charged': Decimal('0.00'),
        'personal_relief': Decimal('0.00'),
        'insurance_relief': Decimal('0.00'),
        'paye_deducted': Decimal('0.00'),
    }

    for idx, month_name in enumerate(months, start=1):
        # Fetch payroll for this month in tax_year
        p = Payroll.objects.filter(
            employee=employee,
            period_end__year=tax_year,
            period_end__month=idx,
        ).first()

        if p:
            basic = p.basic_salary
            benefits = p.house_allowance + p.transport_allowance + p.medical_allowance + p.other_allowance + p.other_allowances_total
            quarters = Decimal('0.00')
            gross = p.gross_salary

            nssf_act = p.nssf
            nssf_fixed = Decimal('20000.00')  # Statutory retirement cap
            nssf_pct = round(basic * Decimal('0.30'), 2)
            allowable = min(nssf_act, nssf_fixed, nssf_pct)
            
            taxable = max(Decimal('0.00'), gross - allowable)
            
            personal_relief = Decimal('0.00') if employee.is_secondary_employee or employee.is_non_resident else Decimal('2400.00')
            insurance_relief = min(p.shif * Decimal('0.15'), Decimal('5000.00'))
            tax_charged = p.paye + personal_relief + insurance_relief if p.paye > Decimal('0.00') else Decimal('0.00')
            paye = p.paye
        else:
            basic = benefits = quarters = gross = nssf_act = nssf_fixed = nssf_pct = allowable = taxable = tax_charged = personal_relief = insurance_relief = paye = Decimal('0.00')

        entry = {
            'month_name': month_name,
            'basic_salary': basic,
            'benefits': benefits,
            'quarters': quarters,
            'gross_pay': gross,
            'nssf_actual': nssf_act,
            'nssf_fixed': nssf_fixed if p else Decimal('0.00'),
            'nssf_percent': nssf_pct,
            'mortgage_interest': Decimal('0.00'),
            'post_retirement': Decimal('0.00'),
            'allowable_deductions': allowable,
            'taxable_pay': taxable,
            'tax_charged': tax_charged,
            'personal_relief': personal_relief,
            'insurance_relief': insurance_relief,
            'paye_deducted': paye,
        }
        monthly_data.append(entry)

        for k in totals:
            totals[k] += entry[k]

    return monthly_data, totals
