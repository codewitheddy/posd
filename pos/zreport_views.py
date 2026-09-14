"""
Z-Report Views
Production-ready views for Z-Report management with security and auditability.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.db.models import Q, Sum, Count
from decimal import Decimal
import json
import csv
from datetime import datetime, timedelta

import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from .decorators import business_required
from .models import Business, POSSession, ZReport, ZReportAuditLog, SalePayment
from .zreport_service import ZReportService


def _membership_has(request, permission_code):
    membership = getattr(request, 'business_membership', None)
    return bool(membership and membership.has_permission(permission_code))


def _has_report_access(request, zreport=None):
    if zreport:
        session_user = getattr(zreport.session, 'cashier', None) or getattr(zreport.session, 'opened_by', None)
        if zreport.created_by == request.user or session_user == request.user:
            return True
    membership = getattr(request, 'business_membership', None)
    role = getattr(membership, 'role', '') if membership else ''
    if role in ['cashier', 'sales'] and not request.user.is_superuser:
        return False  # Cashiers use Front Office Shift Z-Reports for full listing
    return (
        request.user.is_superuser
        or _membership_has(request, 'can_view_reports')
        or _membership_has(request, 'reports')
        or (membership and membership.role in ['owner', 'admin', 'manager', 'chief_cashier', 'viewer'])
    )


def _has_close_session_access(request):
    return (
        request.user.is_superuser
        or request.user.has_perm('pos.can_close_session')
        or _membership_has(request, 'reports')
        or (hasattr(request, 'business_membership') and request.business_membership.role in ['owner', 'admin', 'manager', 'chief_cashier', 'cashier'])
    )


def _has_verify_access(request):
    return request.user.is_superuser or request.user.has_perm('pos.can_verify_zreport') or _has_report_access(request)


def _has_export_access(request, zreport=None):
    if zreport:
        session_user = getattr(zreport.session, 'cashier', None) or getattr(zreport.session, 'opened_by', None)
        if zreport.created_by == request.user or session_user == request.user:
            return True
    membership = getattr(request, 'business_membership', None)
    role = getattr(membership, 'role', '') if membership else ''
    if role in ['cashier', 'sales'] and not request.user.is_superuser:
        return False
    return request.user.is_superuser or request.user.has_perm('pos.can_export_zreport') or _has_report_access(request)


def _redirect_no_access(request, slug, message):
    messages.error(request, message)
    membership = getattr(request, 'business_membership', None)
    if membership and membership.role in ['cashier', 'sales'] and not request.user.is_superuser:
        return redirect('front_office_zreport')
    if slug:
        return redirect('zreport_session_status', slug=slug)
    return redirect('zreport_session_status')


# ============================================================================
# SESSION MANAGEMENT VIEWS
# ============================================================================

@login_required
@business_required
def session_open(request, slug=None):
    """Open a new POS session"""
    business = request.business
    user = request.user
    branch = getattr(request, 'branch', None)
    terminal = getattr(request, 'terminal', None)
    
    # Check if this user already has an open session
    current_session = ZReportService.get_current_session(business, user=user, terminal=terminal)
    if current_session:
        messages.warning(request, f"You already have an active shift session (#Session {current_session.session_number}).")
        return redirect('zreport_session_status', slug=business.slug)
    
    if request.method == 'POST':
        try:
            opening_cash = Decimal(request.POST.get('opening_cash', '0'))
            notes = request.POST.get('notes', '').strip()
            
            session = ZReportService.open_session(
                business=business,
                user=user,
                opening_cash=opening_cash,
                notes=notes,
                branch=branch,
                terminal=terminal
            )
            
            request.session['pos_session_id'] = session.pk
            messages.success(
                request, 
                f"Shift Session #{session.session_number} opened successfully with opening cash: KES {opening_cash:,.2f}"
            )
            return redirect('zreport_session_status', slug=business.slug)
            
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error opening session: {str(e)}")
    
    context = {
        'business': business,
        'branch': branch,
        'terminal': terminal,
    }
    return render(request, 'pos/zreport_session_open.html', context)


@login_required
@business_required
def session_status(request, slug=None):
    """View current session status or all active sessions for managers"""
    business = request.business
    user = request.user
    session_id = request.GET.get('session_id')
    terminal = getattr(request, 'terminal', None)
    
    current_session = ZReportService.get_current_session(
        business, user=user, terminal=terminal, session_id=session_id
    )
    
    # Get all active sessions for business (useful for managers with multiple registers)
    all_open_sessions = POSSession.objects.filter(
        business=business, status='open'
    ).select_related('cashier', 'opened_by', 'terminal', 'branch').order_by('-opened_at')
    
    # Get session statistics if session is open
    session_stats = None
    if current_session:
        from django.db.models import Sum, Count
        sales = current_session.sales.all()
        
        sales_aggregates = sales.aggregate(
            total_sales=Sum('total'),
            total_transactions=Count('id')
        )
        
        session_stats = {
            'total_sales': sales_aggregates['total_sales'] or Decimal('0.00'),
            'total_transactions': sales_aggregates['total_transactions'] or 0,
            'duration': timezone.now() - current_session.opened_at,
        }
    
    context = {
        'business': business,
        'current_session': current_session,
        'all_open_sessions': all_open_sessions,
        'session_stats': session_stats,
    }
    return render(request, 'pos/zreport_session_status.html', context)


@login_required
@business_required
def session_close(request, slug=None):
    """Close current session and generate Z-Report"""
    business = request.business
    user = request.user
    session_id = request.GET.get('session_id') or request.POST.get('session_id')
    terminal = getattr(request, 'terminal', None)
    
    current_session = ZReportService.get_current_session(
        business, user=user, terminal=terminal, session_id=session_id
    )
    
    if not current_session:
        messages.error(request, "No open session found to close.")
        return redirect('zreport_list', slug=business.slug)
    
    # Check permission - superusers have all permissions
    if not _has_close_session_access(request):
        messages.error(request, "You don't have permission to close sessions.")
        return redirect('zreport_session_status', slug=business.slug)
    
    if request.method == 'POST':
        try:
            closing_cash = Decimal(request.POST.get('closing_cash', '0'))
            
            # Get IP address and user agent
            ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Close session and generate Z-Report
            zreport = ZReportService.close_session(
                session_id=current_session.id,
                user=request.user,
                closing_cash=closing_cash,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            messages.success(
                request,
                f"Session #{current_session.session_number} closed successfully. Z-Report #{zreport.z_number:05d} generated."
            )
            return redirect('zreport_detail', slug=business.slug, z_number=zreport.z_number)
            
        except ValidationError as e:
            messages.error(request, str(e))
        except PermissionDenied as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error closing session: {str(e)}")
    
    # Calculate expected cash for display
    from .models import SalePayment
    cash_payments = SalePayment.objects.filter(
        sale__session=current_session,
        payment_method__name__iexact='CASH'
    ).aggregate(total=Sum('amount'))
    
    cash_sales = cash_payments['total'] or Decimal('0.00')
    expected_cash = current_session.opening_cash + cash_sales
    
    context = {
        'business': business,
        'session': current_session,
        'expected_cash': expected_cash,
        'opening_cash': current_session.opening_cash,
        'cash_sales': cash_sales,
    }
    return render(request, 'pos/zreport_session_close.html', context)


# ============================================================================
# Z-REPORT VIEWS
# ============================================================================

@login_required
@business_required
def zreport_list(request, slug=None):
    """List all Z-Reports for the business"""
    business = request.business

    if not _has_report_access(request):
        return _redirect_no_access(request, business.slug, "You don't have permission to view Z-Reports.")
    
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    include_voided = request.GET.get('include_voided') == 'true'
    
    # Base queryset
    zreports = ZReport.objects.filter(business=business).select_related(
        'session', 'created_by'
    )
    
    # Role scoping
    membership = getattr(request, 'business_membership', None)
    is_admin = request.user.is_superuser or (membership and membership.role in ['owner', 'admin'])
    is_manager = membership and membership.role in ['manager', 'chief_cashier']
    
    if not is_admin and not is_manager:
        # Cashier: strictly view own shifts
        zreports = zreports.filter(Q(created_by=request.user) | Q(session__opened_by=request.user) | Q(session__cashier=request.user))
    elif is_manager:
        branch = getattr(request, 'branch', None)
        if branch:
            zreports = zreports.filter(Q(branch=branch) | Q(session__branch=branch) | Q(created_by=request.user))

    # Apply filters
    if not include_voided:
        zreports = zreports.filter(is_voided=False)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            zreports = zreports.filter(created_at__gte=start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
            zreports = zreports.filter(created_at__lte=end)
        except ValueError:
            pass
    
    zreports = zreports.order_by('-z_number')
    
    context = {
        'business': business,
        'zreports': zreports,
        'start_date': start_date,
        'end_date': end_date,
        'include_voided': include_voided,
    }
    return render(request, 'pos/zreport_list.html', context)


@login_required
@business_required
def zreport_detail(request, slug=None, z_number=None):
    """View detailed Z-Report"""
    business = request.business

    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )

    if not _has_report_access(request, zreport):
        return _redirect_no_access(request, business.slug, "You don't have permission to view Z-Reports.")
    
    # Cashier access validation: cashiers can only view own shift report
    membership = getattr(request, 'business_membership', None)
    if membership and membership.role in ['cashier', 'sales'] and not request.user.is_superuser:
        session_user = getattr(zreport.session, 'cashier', None) or getattr(zreport.session, 'opened_by', None)
        if zreport.created_by != request.user and session_user != request.user:
            messages.error(request, "You can only view your own shift Z-Reports.")
            return redirect('front_office_pos')
    
    # Log view action
    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    ZReportService.log_action(
        zreport=zreport,
        action='viewed',
        user=request.user,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # Get audit logs
    audit_logs = zreport.audit_logs.select_related('performed_by').order_by('-performed_at')[:20]
    
    context = {
        'business': business,
        'zreport': zreport,
        'report_data': zreport.report_data,
        'audit_logs': audit_logs,
        'can_verify_zreport': _has_verify_access(request),
        'can_export_zreport': _has_export_access(request),
        'can_void_zreport': request.user.is_superuser or request.user.has_perm('pos.can_void_zreport'),
    }
    return render(request, 'pos/zreport_detail.html', context)


@login_required
@business_required
def zreport_verify(request, slug=None, z_number=None):
    """Verify Z-Report integrity"""
    business = request.business

    if not _has_verify_access(request):
        return _redirect_no_access(request, business.slug, "You don't have permission to verify Z-Reports.")
    
    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )
    
    # Get IP address and user agent
    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Verify integrity
    is_valid, message = ZReportService.verify_integrity(
        zreport=zreport,
        user=request.user,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if is_valid:
        messages.success(request, message)
    else:
        messages.error(request, message)
    
    return redirect('zreport_detail', slug=business.slug, z_number=z_number)


@login_required
@business_required
def zreport_void(request, slug=None, z_number=None):
    """Void a Z-Report"""
    business = request.business
    
    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )
    
    # Check permission
    if not request.user.has_perm('pos.can_void_zreport'):
        messages.error(request, "You don't have permission to void Z-Reports.")
        return redirect('zreport_detail', slug=business.slug, z_number=z_number)
    
    if zreport.is_voided:
        messages.warning(request, "This Z-Report is already voided.")
        return redirect('zreport_detail', slug=business.slug, z_number=z_number)
    
    if request.method == 'POST':
        try:
            reason = request.POST.get('reason', '').strip()
            
            # Get IP address and user agent
            ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Void the report
            zreport = ZReportService.void_zreport(
                zreport=zreport,
                reason=reason,
                user=request.user,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            messages.success(request, f"Z-Report #{z_number:05d} has been voided.")
            return redirect('zreport_detail', slug=business.slug, z_number=z_number)
            
        except ValidationError as e:
            messages.error(request, str(e))
        except PermissionDenied as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error voiding report: {str(e)}")
    
    context = {
        'business': business,
        'zreport': zreport,
    }
    return render(request, 'pos/zreport_void.html', context)


# ============================================================================
# EXPORT VIEWS
# ============================================================================

@login_required
@business_required
def zreport_export_json(request, slug=None, z_number=None):
    """Export Z-Report as JSON"""
    business = request.business

    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )

    if not _has_export_access(request, zreport):
        return _redirect_no_access(request, business.slug, "You don't have permission to export Z-Reports.")
    
    # Log export action
    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    ZReportService.log_action(
        zreport=zreport,
        action='exported_json',
        user=request.user,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # Prepare export data
    export_data = {
        'z_number': zreport.z_number,
        'created_at': zreport.created_at.isoformat(),
        'created_by': zreport.created_by.get_full_name() or zreport.created_by.username,
        'is_voided': zreport.is_voided,
        'data_hash': zreport.data_hash,
        'report_data': zreport.report_data,
    }
    
    response = JsonResponse(export_data, json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename="zreport_{z_number:05d}.json"'
    
    return response


@login_required
@business_required
def zreport_export_csv(request, slug=None, z_number=None):
    """Export Z-Report as CSV"""
    business = request.business

    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )

    if not _has_export_access(request, zreport):
        return _redirect_no_access(request, business.slug, "You don't have permission to export Z-Reports.")
    
    # Log export action
    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    ZReportService.log_action(
        zreport=zreport,
        action='exported_csv',
        user=request.user,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="zreport_{z_number:05d}.csv"'
    
    writer = csv.writer(response)
    
    # Header
    writer.writerow(['Z-REPORT', f'#{z_number:05d}'])
    writer.writerow(['Business', business.name])
    writer.writerow(['Generated', zreport.created_at.strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Generated By', zreport.created_by.get_full_name() or zreport.created_by.username])
    writer.writerow([])
    
    # Sales Summary
    sales_summary = zreport.report_data.get('sales_summary', {})
    writer.writerow(['SALES SUMMARY'])
    writer.writerow(['Total Transactions', sales_summary.get('total_transactions', 0)])
    writer.writerow(['Gross Sales', f"KES {sales_summary.get('gross_sales', 0):,.2f}"])
    writer.writerow(['Net Sales', f"KES {sales_summary.get('net_sales', 0):,.2f}"])
    writer.writerow(['Total Tax', f"KES {sales_summary.get('total_tax', 0):,.2f}"])
    writer.writerow(['Total Discounts', f"KES {sales_summary.get('total_discounts', 0):,.2f}"])
    writer.writerow([])
    
    # Payment Breakdown
    writer.writerow(['PAYMENT BREAKDOWN'])
    writer.writerow(['Method', 'Count', 'Amount'])
    for payment in zreport.report_data.get('payment_breakdown', []):
        writer.writerow([
            payment['method'],
            payment['count'],
            f"KES {payment['amount']:,.2f}"
        ])
    writer.writerow([])
    
    # Cash Management
    cash_mgmt = zreport.report_data.get('cash_management', {})
    writer.writerow(['CASH MANAGEMENT'])
    writer.writerow(['Opening Float', f"KES {cash_mgmt.get('opening_float', 0):,.2f}"])
    writer.writerow(['Cash Sales', f"KES {cash_mgmt.get('cash_sales', 0):,.2f}"])
    writer.writerow(['Expected Cash', f"KES {cash_mgmt.get('expected_cash', 0):,.2f}"])
    writer.writerow(['Actual Cash', f"KES {cash_mgmt.get('actual_cash_counted', 0):,.2f}"])
    writer.writerow(['Difference', f"KES {cash_mgmt.get('difference', 0):,.2f}"])
    writer.writerow([])
    
    # Top Products
    writer.writerow(['TOP PRODUCTS'])
    writer.writerow(['Product', 'Quantity', 'Revenue'])
    for product in zreport.report_data.get('top_products', []):
        writer.writerow([
            product['name'],
            product['quantity'],
            f"KES {product['revenue']:,.2f}"
        ])
    
    return response


@login_required
@business_required
def zreport_export_pdf(request, slug=None, z_number=None):
    """Export Z-Report as a downloadable PDF document"""
    business = request.business

    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )

    if not _has_export_access(request, zreport):
        return _redirect_no_access(request, business.slug, "You don't have permission to export Z-Reports.")
    
    # Log export action
    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    ZReportService.log_action(
        zreport=zreport,
        action='exported_pdf',
        user=request.user,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    report_data = zreport.report_data or {}
    sales_summary = report_data.get('sales_summary', {})
    cash_mgmt = report_data.get('cash_management', {})
    session_info = report_data.get('session', {})
    payments = report_data.get('payment_breakdown', [])
    taxes = report_data.get('tax_breakdown', [])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    elements = []
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'ZHeader',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0f172a'),
        alignment=TA_CENTER
    )
    sub_style = ParagraphStyle(
        'ZSub',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#475569'),
        alignment=TA_CENTER
    )
    title_style = ParagraphStyle(
        'ZTitle',
        parent=styles['Heading2'],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#1e40af'),
        alignment=TA_CENTER,
        spaceAfter=8
    )
    section_head = ParagraphStyle(
        'ZSectionHead',
        parent=styles['Heading3'],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=8,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        'ZBody',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155')
    )
    bold_style = ParagraphStyle(
        'ZBold',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a')
    )
    right_style = ParagraphStyle(
        'ZRight',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#0f172a')
    )
    right_bold = ParagraphStyle(
        'ZRightBold',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        fontName='Helvetica-Bold',
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#0f172a')
    )

    elements.append(Paragraph(business.name.upper(), header_style))
    if zreport.session and zreport.session.branch:
        elements.append(Paragraph(f"Branch: {zreport.session.branch.name}", sub_style))
    if business.address:
        elements.append(Paragraph(business.address, sub_style))
    contact_parts = []
    if business.phone:
        contact_parts.append(f"Tel: {business.phone}")
    if business.email:
        contact_parts.append(f"Email: {business.email}")
    if contact_parts:
        elements.append(Paragraph(" | ".join(contact_parts), sub_style))
    
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(f"<b>OFFICIAL SHIFT Z-REPORT #{zreport.z_number:05d}</b>", title_style))
    if zreport.is_voided:
        elements.append(Paragraph("<font color='red'><b>*** VOIDED REPORT ***</b></font>", ParagraphStyle('Void', alignment=TA_CENTER, fontSize=11, leading=14)))
    
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1e40af'), spaceAfter=8))

    # Session details table
    opened_by_str = str(session_info.get('opened_by') or (zreport.session.opened_by.get_full_name() or zreport.session.opened_by.username if zreport.session and zreport.session.opened_by else 'N/A'))
    opened_at_str = str(session_info.get('opened_at') or (zreport.session.opened_at.strftime('%d/%m/%Y %H:%M') if zreport.session and zreport.session.opened_at else 'N/A'))
    closed_by_str = str(session_info.get('closed_by') or (zreport.created_by.get_full_name() or zreport.created_by.username if zreport.created_by else 'N/A'))
    closed_at_str = str(session_info.get('closed_at') or (zreport.session.closed_at.strftime('%d/%m/%Y %H:%M') if zreport.session and zreport.session.closed_at else zreport.created_at.strftime('%d/%m/%Y %H:%M')))

    session_data = [
        [
            Paragraph("<b>Session Number:</b>", body_style),
            Paragraph(f"#{zreport.session.session_number if zreport.session else '-'}", bold_style),
            Paragraph("<b>Generated:</b>", body_style),
            Paragraph(zreport.created_at.strftime('%d/%m/%Y %H:%M:%S'), right_style)
        ],
        [
            Paragraph("<b>Opened By:</b>", body_style),
            Paragraph(opened_by_str, body_style),
            Paragraph("<b>Opened At:</b>", body_style),
            Paragraph(opened_at_str, right_style)
        ],
        [
            Paragraph("<b>Closed By:</b>", body_style),
            Paragraph(closed_by_str, body_style),
            Paragraph("<b>Closed At:</b>", body_style),
            Paragraph(closed_at_str, right_style)
        ],
    ]
    t_session = Table(session_data, colWidths=[1.5*inch, 2.2*inch, 1.3*inch, 2.3*inch])
    t_session.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#f1f5f9')),
    ]))
    elements.append(t_session)
    elements.append(Spacer(1, 8))

    # Sales Summary
    elements.append(Paragraph("<b>Sales & Financial Summary</b>", section_head))
    gross_sales = Decimal(str(sales_summary.get('gross_sales', 0)))
    net_sales = Decimal(str(sales_summary.get('net_sales', 0)))
    total_tax = Decimal(str(sales_summary.get('total_tax', 0)))
    total_discounts = Decimal(str(sales_summary.get('total_discounts', 0)))
    total_txns = sales_summary.get('total_transactions', 0)

    sales_table_data = [
        [Paragraph("<b>Metric</b>", bold_style), Paragraph("<b>Value</b>", right_bold)],
        [Paragraph("Total Transactions", body_style), Paragraph(str(total_txns), right_style)],
        [Paragraph("Gross Sales (Turnover)", bold_style), Paragraph(f"KES {gross_sales:,.2f}", right_bold)],
        [Paragraph("Total Discounts Given", body_style), Paragraph(f"-KES {total_discounts:,.2f}", right_style)],
        [Paragraph("Net Sales (excl. VAT)", body_style), Paragraph(f"KES {net_sales:,.2f}", right_style)],
        [Paragraph("Tax Collected (VAT)", body_style), Paragraph(f"KES {total_tax:,.2f}", right_style)],
    ]
    if sales_summary.get('total_refunds'):
        sales_table_data.append([Paragraph("Total Refunds", body_style), Paragraph(f"KES {Decimal(str(sales_summary['total_refunds'])):,.2f}", right_style)])
    if sales_summary.get('total_voids'):
        sales_table_data.append([Paragraph("Total Voids", body_style), Paragraph(f"KES {Decimal(str(sales_summary['total_voids'])):,.2f}", right_style)])

    t_sales = Table(sales_table_data, colWidths=[4.3*inch, 3.0*inch])
    t_sales.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f0fdf4')),
    ]))
    elements.append(t_sales)
    elements.append(Spacer(1, 8))

    # Cash Drawer Reconciliation Table
    elements.append(Paragraph("<b>Cash Drawer Reconciliation</b>", section_head))
    opening_float = Decimal(str(cash_mgmt.get('opening_float', 0)))
    cash_sales = Decimal(str(cash_mgmt.get('cash_sales', 0)))
    expected_cash = Decimal(str(cash_mgmt.get('expected_cash', 0)))
    actual_cash = Decimal(str(cash_mgmt.get('actual_cash_counted', 0)))
    difference = Decimal(str(cash_mgmt.get('difference', 0)))

    var_prefix = "+" if difference > 0 else ""
    var_color = colors.HexColor('#16a34a') if difference >= 0 else colors.HexColor('#dc2626')

    diff_para = Paragraph(f"<font color='{var_color.hexval()}'><b>{var_prefix}KES {difference:,.2f}</b></font>", right_bold)

    cash_table_data = [
        [Paragraph("<b>Drawer Cash Flow</b>", bold_style), Paragraph("<b>Amount (KES)</b>", right_bold)],
        [Paragraph("Opening Float", body_style), Paragraph(f"KES {opening_float:,.2f}", right_style)],
        [Paragraph("Cash Sales in Till", body_style), Paragraph(f"KES {cash_sales:,.2f}", right_style)],
        [Paragraph("<b>Expected Cash in Drawer</b>", bold_style), Paragraph(f"<b>KES {expected_cash:,.2f}</b>", right_bold)],
        [Paragraph("<b>Actual Counted Cash</b>", bold_style), Paragraph(f"<b>KES {actual_cash:,.2f}</b>", right_bold)],
        [Paragraph("<b>Cash Variance (Over / Short)</b>", bold_style), diff_para],
    ]
    t_cash = Table(cash_table_data, colWidths=[4.3*inch, 3.0*inch])
    t_cash.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#eff6ff')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#fef3c7')),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t_cash)
    elements.append(Spacer(1, 8))

    # Payment Methods Breakdown
    if payments:
        elements.append(Paragraph("<b>Payment Methods Breakdown</b>", section_head))
        pay_table_data = [
            [Paragraph("<b>Payment Method</b>", bold_style), Paragraph("<b>Transactions</b>", ParagraphStyle('CHead', parent=right_bold, alignment=TA_CENTER)), Paragraph("<b>Total Amount</b>", right_bold)]
        ]
        for p in payments:
            amt = Decimal(str(p.get('amount', 0)))
            pay_table_data.append([
                Paragraph(str(p.get('method', 'Unknown')).upper(), body_style),
                Paragraph(str(p.get('count', 0)), ParagraphStyle('CCell', parent=right_style, alignment=TA_CENTER)),
                Paragraph(f"KES {amt:,.2f}", right_bold)
            ])
        t_pay = Table(pay_table_data, colWidths=[3.5*inch, 1.8*inch, 2.0*inch])
        t_pay.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
        elements.append(t_pay)
        elements.append(Spacer(1, 8))

    # Tax Breakdown
    if taxes:
        elements.append(Paragraph("<b>Tax Breakdown (VAT)</b>", section_head))
        tax_table_data = [
            [Paragraph("<b>Tax Rate</b>", bold_style), Paragraph("<b>Taxable Amount</b>", right_bold), Paragraph("<b>VAT Amount</b>", right_bold)]
        ]
        for t in taxes:
            taxable = Decimal(str(t.get('taxable_amount', 0)))
            tax_amt = Decimal(str(t.get('tax_amount', 0)))
            tax_table_data.append([
                Paragraph(str(t.get('rate', '')), body_style),
                Paragraph(f"KES {taxable:,.2f}", right_style),
                Paragraph(f"KES {tax_amt:,.2f}", right_bold)
            ])
        t_tax = Table(tax_table_data, colWidths=[2.5*inch, 2.4*inch, 2.4*inch])
        t_tax.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
        elements.append(t_tax)
        elements.append(Spacer(1, 8))

    # Audit & Security Hash Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#94a3b8'), spaceBefore=6, spaceAfter=4))
    elements.append(Paragraph(f"<b>Digital Audit Hash:</b> {zreport.data_hash}", ParagraphStyle('Hash', parent=styles['Normal'], fontSize=7.5, leading=9, textColor=colors.HexColor('#64748b'), alignment=TA_CENTER)))
    elements.append(Paragraph(f"Generated by {business.name} · {zreport.created_at.strftime('%d/%m/%Y %H:%M:%S')}", ParagraphStyle('Foot', parent=styles['Normal'], fontSize=7.5, leading=9, textColor=colors.HexColor('#94a3b8'), alignment=TA_CENTER)))

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="zreport_{z_number:05d}.pdf"'
    return response


@login_required
@business_required
def zreport_print(request, slug=None, z_number=None):
    """Print-friendly Z-Report view"""
    business = request.business

    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )

    if not _has_report_access(request, zreport):
        return _redirect_no_access(request, business.slug, "You don't have permission to view Z-Reports.")
    
    # Log print action
    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    ZReportService.log_action(
        zreport=zreport,
        action='printed',
        user=request.user,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    business_settings = None
    try:
        from .models import BusinessSettings
        business_settings = BusinessSettings.get_settings(business)
    except Exception:
        business_settings = None

    context = {
        'business': business,
        'business_settings': business_settings,
        'zreport': zreport,
        'report_data': zreport.report_data,
        'is_print': True,
    }
    return render(request, 'pos/zreport_print.html', context)


# ============================================================================
# API ENDPOINTS (JSON)
# ============================================================================

@login_required
@business_required
def api_session_status(request, slug=None):
    """API: Get current session status"""
    business = request.business
    current_session = ZReportService.get_current_session(business)
    
    if not current_session:
        return JsonResponse({
            'status': 'no_session',
            'message': 'No open session'
        })
    
    # Get session stats
    from django.db.models import Sum, Count
    sales_aggregates = current_session.sales.aggregate(
        total_sales=Sum('total'),
        total_transactions=Count('id')
    )
    
    return JsonResponse({
        'status': 'open',
        'session': {
            'id': current_session.id,
            'session_number': current_session.session_number,
            'opened_at': current_session.opened_at.isoformat(),
            'opened_by': current_session.opened_by.get_full_name() or current_session.opened_by.username,
            'opening_cash': float(current_session.opening_cash),
            'total_sales': float(sales_aggregates['total_sales'] or 0),
            'total_transactions': sales_aggregates['total_transactions'] or 0,
        }
    })


@login_required
@business_required
def api_zreport_data(request, slug=None, z_number=None):
    """API: Get Z-Report data as JSON"""
    business = request.business

    if not _has_report_access(request):
        return JsonResponse({'error': "You don't have permission to view Z-Reports."}, status=403)
    
    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )
    
    return JsonResponse({
        'z_number': zreport.z_number,
        'created_at': zreport.created_at.isoformat(),
        'created_by': zreport.created_by.get_full_name() or zreport.created_by.username,
        'is_voided': zreport.is_voided,
        'report_data': zreport.report_data,
    })
