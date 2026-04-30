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

from .decorators import business_required
from .models import Business, POSSession, ZReport, ZReportAuditLog, SalePayment
from .zreport_service import ZReportService


def _membership_has(request, permission_code):
    membership = getattr(request, 'business_membership', None)
    return bool(membership and membership.has_permission(permission_code))


def _has_report_access(request):
    return (
        request.user.is_superuser
        or _membership_has(request, 'can_view_reports')
        or _membership_has(request, 'reports')
    )


def _has_close_session_access(request):
    return (
        request.user.is_superuser
        or request.user.has_perm('pos.can_close_session')
        or _membership_has(request, 'reports')
    )


def _has_verify_access(request):
    return request.user.is_superuser or request.user.has_perm('pos.can_verify_zreport') or _has_report_access(request)


def _has_export_access(request):
    return request.user.is_superuser or request.user.has_perm('pos.can_export_zreport') or _has_report_access(request)


def _redirect_no_access(request, slug, message):
    messages.error(request, message)
    return redirect('zreport_session_status', slug=slug)


# ============================================================================
# SESSION MANAGEMENT VIEWS
# ============================================================================

@login_required
@business_required
def session_open(request, slug=None):
    """Open a new POS session"""
    business = request.business
    
    # Check if there's already an open session
    current_session = ZReportService.get_current_session(business)
    if current_session:
        messages.warning(request, f"Session #{current_session.session_number} is already open.")
        return redirect('zreport_session_status', slug=business.slug)
    
    if request.method == 'POST':
        try:
            opening_cash = Decimal(request.POST.get('opening_cash', '0'))
            notes = request.POST.get('notes', '').strip()
            
            session = ZReportService.open_session(
                business=business,
                user=request.user,
                opening_cash=opening_cash,
                notes=notes
            )
            
            messages.success(
                request, 
                f"Session #{session.session_number} opened successfully with opening cash: KES {opening_cash:,.2f}"
            )
            return redirect('zreport_session_status', slug=business.slug)
            
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error opening session: {str(e)}")
    
    context = {
        'business': business,
    }
    return render(request, 'pos/zreport_session_open.html', context)


@login_required
@business_required
def session_status(request, slug=None):
    """View current session status"""
    business = request.business
    current_session = ZReportService.get_current_session(business)
    
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
        'session_stats': session_stats,
    }
    return render(request, 'pos/zreport_session_status.html', context)


@login_required
@business_required
def session_close(request, slug=None):
    """Close current session and generate Z-Report"""
    business = request.business
    current_session = ZReportService.get_current_session(business)
    
    if not current_session:
        messages.error(request, "No open session to close.")
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

    if not _has_report_access(request):
        return _redirect_no_access(request, business.slug, "You don't have permission to view Z-Reports.")
    
    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )
    
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

    if not _has_export_access(request):
        return _redirect_no_access(request, business.slug, "You don't have permission to export Z-Reports.")
    
    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )
    
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

    if not _has_export_access(request):
        return _redirect_no_access(request, business.slug, "You don't have permission to export Z-Reports.")
    
    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )
    
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
    """Export Z-Report as PDF"""
    business = request.business

    if not _has_export_access(request):
        return _redirect_no_access(request, business.slug, "You don't have permission to export Z-Reports.")
    
    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )
    
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
    
    # For now, render HTML version (PDF generation can be added later with reportlab/weasyprint)
    context = {
        'business': business,
        'zreport': zreport,
        'report_data': zreport.report_data,
        'is_pdf': True,
    }
    
    response = render(request, 'pos/zreport_pdf.html', context)
    response['Content-Disposition'] = f'inline; filename="zreport_{z_number:05d}.pdf"'
    
    return response


@login_required
@business_required
def zreport_print(request, slug=None, z_number=None):
    """Print-friendly Z-Report view"""
    business = request.business

    if not _has_report_access(request):
        return _redirect_no_access(request, business.slug, "You don't have permission to view Z-Reports.")
    
    zreport = get_object_or_404(
        ZReport,
        business=business,
        z_number=z_number
    )
    
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
    
    context = {
        'business': business,
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
