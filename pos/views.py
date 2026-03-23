from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q, F
from django.db import models
from django.db.models.functions import Coalesce, TruncHour, ExtractHour
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from .models import (
    Product, Category, Sale, SaleItem, StockAdjustment, Supplier, Purchase, 
    PurchaseItem, Customer, SupplierPayment, PaymentAllocation, ActivityLog,
    SalePayment, Shift, Business, BusinessMembership, PaymentMethod, BusinessSettings,
    GoodsReturnedNote, GoodsReturnedNoteItem, GoodsReceivedNote, GoodsReceivedNoteItem, DayClosureReport
)
from .decorators import business_required, business_permission_required, feature_required
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
import io


# ==================== PLATFORM ADMIN DASHBOARD ====================

@login_required
@user_passes_test(lambda u: u.is_superuser)
def platform_admin_dashboard(request):
    """Platform-wide admin dashboard - only for superusers"""
    from django.utils import timezone
    
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    # Business statistics
    total_businesses = Business.objects.count()
    active_businesses = Business.objects.filter(is_active=True).count()
    inactive_businesses = total_businesses - active_businesses
    pending_activations = Business.objects.filter(is_active=False).count()
    
    # User statistics
    total_users = User.objects.count()
    
    # Sales statistics
    total_sales = Sale.objects.count()
    total_revenue = Sale.objects.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    today_sales = Sale.objects.filter(date__date=today).count()
    today_revenue = Sale.objects.filter(date__date=today).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    month_sales = Sale.objects.filter(date__date__gte=month_start).count()
    month_revenue = Sale.objects.filter(date__date__gte=month_start).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    # Product and customer statistics
    total_products = Product.objects.count()
    total_customers = Customer.objects.count()
    
    # Get all businesses with additional stats
    businesses = Business.objects.select_related('owner').all()
    for business in businesses:
        business.member_count = BusinessMembership.objects.filter(business=business).count()
        business.sales_count = Sale.objects.filter(business=business).count()
    
    context = {
        'total_businesses': total_businesses,
        'active_businesses': active_businesses,
        'inactive_businesses': inactive_businesses,
        'pending_activations': pending_activations,
        'total_users': total_users,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'today_sales': today_sales,
        'today_revenue': today_revenue,
        'month_sales': month_sales,
        'month_revenue': month_revenue,
        'total_products': total_products,
        'total_customers': total_customers,
        'businesses': businesses,
    }
    
    return render(request, 'pos/platform_admin_dashboard.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def admin_create_business(request):
    """Create a new business from platform admin dashboard"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        owner_email = request.POST.get('owner_email', '').strip()
        owner_name = request.POST.get('owner_name', '').strip()
        
        if not name or not owner_email:
            messages.error(request, 'Business name and owner email are required.')
            return redirect('platform_admin_dashboard')
        
        try:
            # Check if user exists, create if not
            try:
                owner = User.objects.get(email=owner_email)
            except User.DoesNotExist:
                # Create new user
                username = owner_email.split('@')[0]
                # Ensure unique username
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                owner = User.objects.create_user(
                    username=username,
                    email=owner_email,
                    password=User.objects.make_random_password(length=12)
                )
                
                if owner_name:
                    name_parts = owner_name.split(' ', 1)
                    owner.first_name = name_parts[0]
                    if len(name_parts) > 1:
                        owner.last_name = name_parts[1]
                    owner.save()
                
                messages.info(request, f'New user account created for {owner_email}. Password reset email should be sent.')
            
            # Create business
            slug = name.lower().replace(' ', '-')
            # Ensure unique slug
            base_slug = slug
            counter = 1
            while Business.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            business = Business.objects.create(
                name=name,
                slug=slug,
                owner=owner,
                is_active=True
            )
            
            # Create business membership for owner
            BusinessMembership.objects.create(
                business=business,
                user=owner,
                role='owner'
            )
            
            # Create default business settings
            BusinessSettings.objects.create(
                business=business,
                currency='KES',
                tax_rate=Decimal('16.00'),
                low_stock_threshold=10
            )
            
            messages.success(request, f'Business "{name}" created successfully! Owner: {owner.email}')
            
        except Exception as e:
            messages.error(request, f'Error creating business: {str(e)}')
    
    return redirect('platform_admin_dashboard')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def extend_license(request):
    """Extend business license"""
    if request.method == 'POST':
        business_id = request.POST.get('business_id')
        days = request.POST.get('days')
        
        if not business_id or not days:
            messages.error(request, 'Business ID and days are required.')
            return redirect('platform_admin_dashboard')
        
        try:
            business = Business.objects.get(id=business_id)
            days = int(days)
            
            if days <= 0:
                messages.error(request, 'Days must be a positive number.')
                return redirect('platform_admin_dashboard')
            
            # Extend the license
            business.extend_license(days)
            
            messages.success(
                request, 
                f'License for "{business.name}" extended by {days} days. New expiry: {business.license_expires_at.strftime("%B %d, %Y")}'
            )
            
        except Business.DoesNotExist:
            messages.error(request, 'Business not found.')
        except ValueError:
            messages.error(request, 'Invalid number of days.')
        except Exception as e:
            messages.error(request, f'Error extending license: {str(e)}')
    
    return redirect('platform_admin_dashboard')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def activate_business(request, business_id):
    """Activate a business and send notification email"""
    if request.method == 'POST':
        try:
            business = Business.objects.get(id=business_id)
            
            if business.is_active:
                messages.info(request, f'Business "{business.name}" is already active.')
                return redirect('platform_admin_dashboard')
            
            # Activate the business
            business.is_active = True
            business.save()
            
            # Send activation email
            try:
                from django.core.mail import send_mail
                from django.conf import settings
                
                login_url = f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/login/"
                
                subject = f'Your Business "{business.name}" Has Been Activated!'
                message = f"""
Hello {business.owner.first_name or business.owner.username},

Great news! Your business "{business.name}" has been activated and is now ready to use.

You can now log in and start using the Marid POS:
Login URL: {login_url}
Username: {business.owner.username}

Your 30-day free trial has started. Explore all features and let us know if you need any help.

Need Support?
Email: info@marid.co.ke
Phone/WhatsApp: +254 717 147 700

Best regards,
Marid POS Team
                """
                
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [business.owner.email],
                    fail_silently=True,
                )
                
                messages.success(
                    request, 
                    f'Business "{business.name}" has been activated! Notification email sent to {business.owner.email}.'
                )
            except Exception as e:
                messages.success(
                    request, 
                    f'Business "{business.name}" has been activated! (Email notification failed: {str(e)})'
                )
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='update',
                model_name='Business',
                object_id=business.id,
                description=f'Business activated: {business.name}',
                request=request
            )
            
        except Business.DoesNotExist:
            messages.error(request, 'Business not found.')
        except Exception as e:
            messages.error(request, f'Error activating business: {str(e)}')
    
    return redirect('platform_admin_dashboard')


# ==================== LEGACY DECORATORS ====================

def manager_required(view_func):
    """Decorator to check if user is a manager, owner, or superuser"""
    def wrapper(request, *args, **kwargs):
        # Check superuser
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # Check business membership role (multi-tenant)
        if hasattr(request, 'business_membership') and request.business_membership:
            role = request.business_membership.role
            if role in ['owner', 'admin', 'manager']:
                return view_func(request, *args, **kwargs)
        
        # Fallback to Django groups (legacy)
        if request.user.groups.filter(name__in=['Administrator', 'Manager']).exists():
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        # Try to redirect with slug if business context exists
        if hasattr(request, 'business') and request.business:
            return redirect('dashboard', slug=request.business.slug)
        return redirect('business_list')
    return wrapper


def can_manage_products(view_func):
    """Decorator to check if user can manage products"""
    def wrapper(request, *args, **kwargs):
        # Check superuser
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # Check business membership role (multi-tenant)
        if hasattr(request, 'business_membership') and request.business_membership:
            role = request.business_membership.role
            if role in ['owner', 'admin', 'manager', 'stock_manager']:
                return view_func(request, *args, **kwargs)
        
        # Fallback to Django groups/permissions (legacy)
        if (request.user.groups.filter(name__in=['Administrator', 'Manager', 'Stock Manager']).exists() or
            request.user.has_perm('pos.change_product')):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to manage products.')
        # Try to redirect with slug if business context exists
        if hasattr(request, 'business') and request.business:
            return redirect('dashboard', slug=request.business.slug)
        return redirect('business_list')
    return wrapper


def can_manage_purchases(view_func):
    """Decorator to check if user can manage purchases"""
    def wrapper(request, *args, **kwargs):
        # Check superuser
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # Check business membership role (multi-tenant)
        if hasattr(request, 'business_membership') and request.business_membership:
            role = request.business_membership.role
            if role in ['owner', 'admin', 'manager', 'stock_manager']:
                return view_func(request, *args, **kwargs)
        
        # Fallback to Django groups/permissions (legacy)
        if (request.user.groups.filter(name__in=['Administrator', 'Manager', 'Stock Manager']).exists() or
            request.user.has_perm('pos.change_purchase')):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to manage purchases.')
        # Try to redirect with slug if business context exists
        if hasattr(request, 'business') and request.business:
            return redirect('dashboard', slug=request.business.slug)
        return redirect('business_list')
    return wrapper


@login_required
@business_required
def dashboard(request, slug=None):
    """Main dashboard with quick stats - Optimized with caching"""
    from django.core.cache import cache
    from .cache_utils import get_cache_key
    
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    # Try to get dashboard data from cache
    cache_key = get_cache_key('dashboard', request.business.id, today)
    cached_data = cache.get(cache_key)
    
    if cached_data:
        # Return cached data
        return render(request, 'pos/dashboard.html', cached_data)
    
    # Calculate dashboard data (cache miss)
    # Today's sales - Optimized with select_related
    today_sales = Sale.objects.filter(
        date__date=today, 
        business=request.business
    ).select_related('cashier', 'customer')
    
    today_sales_count = today_sales.count()
    today_revenue = today_sales.aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
    today_vat = today_sales.aggregate(Sum('vat_amount'))['vat_amount__sum'] or Decimal('0.00')
    today_items_sold = today_sales.aggregate(Sum('items__quantity'))['items__quantity__sum'] or 0
    
    # Yesterday's sales for comparison
    yesterday_sales = Sale.objects.filter(date__date=yesterday, business=request.business)
    yesterday_revenue = yesterday_sales.aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
    yesterday_count = yesterday_sales.count()
    
    # This week's sales
    week_sales = Sale.objects.filter(date__date__gte=week_start, business=request.business)
    week_revenue = week_sales.aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
    week_count = week_sales.count()
    
    # This month's sales
    month_sales = Sale.objects.filter(date__date__gte=month_start, business=request.business)
    month_revenue = month_sales.aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
    month_count = month_sales.count()
    
    # Calculate percentage changes
    revenue_change = 0
    if yesterday_revenue > 0:
        revenue_change = ((today_revenue - yesterday_revenue) / yesterday_revenue) * 100
    
    sales_change = 0
    if yesterday_count > 0:
        sales_change = ((today_sales_count - yesterday_count) / yesterday_count) * 100
    
    # Top selling products today - Optimized
    top_products_today = list(SaleItem.objects.filter(
        sale__business=request.business,
        sale__date__date=today
    ).values('product__name').annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(models.F('quantity') * models.F('unit_price'))
    ).order_by('-total_quantity')[:5])
    
    # Recent sales (last 10) - Optimized with select_related
    recent_sales = list(Sale.objects.filter(
        business=request.business
    ).select_related('cashier', 'customer').order_by('-date')[:10])
    
    # Payment method breakdown for today - Optimized
    payment_breakdown = list(SalePayment.objects.filter(
        sale__business=request.business,
        sale__date__date=today
    ).select_related('payment_method').values('payment_method__name').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total'))
    
    # Stock statistics - Optimized queries
    low_stock_products = Product.objects.filter(
        business=request.business,
        stock_quantity__lte=models.F('low_stock_threshold'),
        stock_quantity__gt=0
    ).count()
    
    out_of_stock_products = Product.objects.filter(
        business=request.business, 
        stock_quantity=0
    ).count()
    
    total_stock_value = Product.objects.filter(
        business=request.business
    ).aggregate(
        value=Sum(models.F('stock_quantity') * models.F('unit_price'))
    )['value'] or Decimal('0.00')
    
    # Supplier and Purchase statistics
    total_suppliers = Supplier.objects.filter(business=request.business, is_active=True).count()
    pending_purchases = Purchase.objects.filter(business=request.business, status='pending').count()
    
    # Customer statistics
    total_customers = Customer.objects.filter(business=request.business).count()
    today_new_customers = Customer.objects.filter(
        business=request.business,
        created_at__date=today
    ).count()
    
    # Support Access Requests (for business owners)
    pending_support_requests_count = 0
    if hasattr(request, 'business_membership') and request.business_membership and request.business_membership.role == 'owner':
        from .models import SupportAccessRequest
        pending_support_requests_count = SupportAccessRequest.objects.filter(
            business=request.business,
            status='pending'
        ).count()
    
    # Trial/License Information
    trial_info = {
        'is_trial': request.business.is_trial,
        'trial_ends_at': request.business.trial_ends_at,
        'is_expired': request.business.is_trial_expired,
        'days_remaining': None,
        'show_warning': False,
        'warning_level': 'info',  # info, warning, danger
    }
    
    # Superusers (system root) have lifetime access - don't show trial warnings
    if not request.user.is_superuser and request.business.is_trial and request.business.trial_ends_at:
        delta = request.business.trial_ends_at - timezone.now()
        trial_info['days_remaining'] = delta.days
        
        # Determine warning level and whether to show
        if trial_info['is_expired']:
            trial_info['show_warning'] = True
            trial_info['warning_level'] = 'danger'
        elif trial_info['days_remaining'] <= 3:
            trial_info['show_warning'] = True
            trial_info['warning_level'] = 'danger'
        elif trial_info['days_remaining'] <= 7:
            trial_info['show_warning'] = True
            trial_info['warning_level'] = 'warning'
        elif trial_info['days_remaining'] <= 14:
            trial_info['show_warning'] = True
            trial_info['warning_level'] = 'info'
    
    # Expiry statistics - Optimized
    expired_count = Product.objects.filter(
        business=request.business,
        expiry_date__lt=today,
        stock_quantity__gt=0
    ).count()
    
    expiring_soon_count = 0
    products_with_expiry = Product.objects.filter(
        business=request.business,
        expiry_date__gte=today,
        stock_quantity__gt=0
    )
    for product in products_with_expiry:
        if product.is_expiring_soon():
            expiring_soon_count += 1
    
    # Fetch actual products for display - Optimized with select_related
    out_of_stock_list = list(Product.objects.filter(
        business=request.business,
        stock_quantity=0
    ).select_related('category')[:5])
    
    expired_list = list(Product.objects.filter(
        business=request.business,
        expiry_date__lt=today, 
        stock_quantity__gt=0
    ).select_related('category')[:5])
    
    expiring_soon_list = []
    for product in products_with_expiry[:10]:  # Check first 10
        if product.is_expiring_soon():
            expiring_soon_list.append(product)
            if len(expiring_soon_list) >= 5:  # Limit to 5
                break
    
    # Sales by hour today (for chart) - Database agnostic
    hourly_sales_qs = today_sales.annotate(
        hour=ExtractHour('date')
    ).values('hour').annotate(
        count=Count('id'),
        revenue=Sum('total')
    ).order_by('hour')
    # Convert Decimal to float so it serializes to valid JSON in the template
    hourly_sales = [{'hour': r['hour'], 'count': r['count'], 'revenue': float(r['revenue'] or 0)} for r in hourly_sales_qs]
    
    context = {
        # Product stats
        'total_products': Product.objects.filter(business=request.business).count(),
        'total_categories': Category.objects.filter(business=request.business).count(),
        'total_stock_value': total_stock_value,
        
        # Today's stats
        'today_sales_count': today_sales_count,
        'today_revenue': today_revenue,
        'today_vat': today_vat,
        'today_items_sold': today_items_sold,
        'today_new_customers': today_new_customers,
        
        # Comparison stats
        'yesterday_revenue': yesterday_revenue,
        'yesterday_count': yesterday_count,
        'revenue_change': revenue_change,
        'sales_change': sales_change,
        
        # Period stats
        'week_revenue': week_revenue,
        'week_count': week_count,
        'month_revenue': month_revenue,
        'month_count': month_count,
        
        # Stock alerts
        'low_stock_count': low_stock_products,
        'out_of_stock_count': out_of_stock_products,
        'out_of_stock_list': out_of_stock_list,
        
        # Supplier stats
        'total_suppliers': total_suppliers,
        'pending_purchases': pending_purchases,
        
        # Customer stats
        'total_customers': total_customers,
        
        # Support Access (for business owners)
        'pending_support_requests_count': pending_support_requests_count,
        
        # Trial/License Information
        'trial_info': trial_info,
        
        # Expiry alerts
        'expired_count': expired_count,
        'expiring_soon_count': expiring_soon_count,
        'expired_list': expired_list,
        'expiring_soon_list': expiring_soon_list,
        
        # Lists and breakdowns
        'top_products_today': top_products_today,
        'top_product_max_qty': top_products_today[0]['total_quantity'] if top_products_today else 1,
        'recent_sales': recent_sales,
        'payment_breakdown': payment_breakdown,
        'hourly_sales': hourly_sales,
    }
    
    # Cache the dashboard data for 5 minutes
    cache_timeout = getattr(settings, 'CACHE_TTL', {}).get('dashboard', 300)
    cache.set(cache_key, context, cache_timeout)
    
    return render(request, 'pos/dashboard.html', context)


@login_required
@business_required
def product_list(request, slug=None):
    """List all products with filtering"""
    from .models import Brand
    products = Product.objects.filter(business=request.business).select_related('category', 'brand').all()

    # Filters
    category_filter = request.GET.get('category', '')
    brand_filter = request.GET.get('brand', '')
    type_filter = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()

    if category_filter:
        products = products.filter(category_id=category_filter)
    if brand_filter:
        products = products.filter(brand_id=brand_filter)
    if type_filter:
        products = products.filter(product_type=type_filter)
    if status_filter == 'active':
        products = products.filter(is_active=True)
    elif status_filter == 'inactive':
        products = products.filter(is_active=False)
    elif status_filter == 'low_stock':
        products = products.filter(stock_quantity__lte=models.F('low_stock_threshold'), stock_quantity__gt=0)
    elif status_filter == 'out_of_stock':
        products = products.filter(stock_quantity=0)
    if search:
        products = products.filter(
            models.Q(name__icontains=search) |
            models.Q(product_code__icontains=search) |
            models.Q(barcode__icontains=search)
        )

    context = {
        'products': products,
        'categories': Category.objects.filter(business=request.business).order_by('name'),
        'brands': Brand.objects.filter(business=request.business).order_by('name'),
        'product_types': Product.PRODUCT_TYPE_CHOICES,
        'category_filter': category_filter,
        'brand_filter': brand_filter,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'search': search,
    }
    return render(request, 'pos/product_list.html', context)


@business_required
def product_bulk_upload(request, slug=None):
    """Bulk upload products via CSV"""
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, 'No file uploaded!')
            return redirect('product_bulk_upload', slug=request.business.slug)
        
        csv_file = request.FILES['csv_file']
        
        # Validate file extension
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'File must be a CSV!')
            return redirect('product_bulk_upload', slug=request.business.slug)
        
        try:
            # Read CSV file
            import csv
            import io
            
            decoded_file = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)
            
            success_count = 0
            error_count = 0
            errors = []
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
                try:
                    # Get or create category
                    category = None
                    if row.get('category'):
                        category, _ = Category.objects.get_or_create(business=request.business, name=row['category'].strip())
                    
                    # Prepare product data
                    product_code = row.get('product_code', '').strip() or None
                    stock_quantity = int(row.get('stock_quantity', 0))
                    low_stock_threshold = int(row.get('low_stock_threshold', 10))
                    
                    # Check if product exists (by name or code)
                    existing_product = None
                    if product_code:
                        existing_product = Product.objects.filter(business=request.business, product_code=product_code).first()
                    if not existing_product:
                        existing_product = Product.objects.filter(business=request.business, name=row['name'].strip()).first()
                    
                    if existing_product:
                        # Update existing product
                        existing_product.name = row['name'].strip()
                        existing_product.product_code = product_code
                        existing_product.category = category
                        existing_product.unit_price = Decimal(row['unit_price'])
                        existing_product.low_stock_threshold = low_stock_threshold
                        
                        # Update stock if provided and different
                        if stock_quantity != existing_product.stock_quantity:
                            previous_qty = existing_product.stock_quantity
                            existing_product.stock_quantity = stock_quantity
                            
                            # Create stock adjustment record
                            StockAdjustment.objects.create(
                                business=request.business,
                                product=existing_product,
                                adjustment_type='correction',
                                quantity_change=stock_quantity - previous_qty,
                                previous_quantity=previous_qty,
                                new_quantity=stock_quantity,
                                reason=f'CSV bulk upload - Row {row_num}'
                            )
                        
                        existing_product.save()
                        success_count += 1
                    else:
                        # Create new product
                        product = Product.objects.create(
                            business=request.business,
                            name=row['name'].strip(),
                            product_code=product_code,
                            category=category,
                            unit_price=Decimal(row['unit_price']),
                            stock_quantity=stock_quantity,
                            low_stock_threshold=low_stock_threshold
                        )
                        
                        # Create initial stock adjustment if stock > 0
                        if stock_quantity > 0:
                            StockAdjustment.objects.create(
                                business=request.business,
                                product=product,
                                adjustment_type='restock',
                                quantity_change=stock_quantity,
                                previous_quantity=0,
                                new_quantity=stock_quantity,
                                reason=f'CSV bulk upload - Row {row_num}'
                            )
                        
                        success_count += 1
                        
                except Exception as e:
                    error_count += 1
                    errors.append(f"Row {row_num}: {str(e)}")
            
            # Show results
            if success_count > 0:
                messages.success(request, f'Successfully processed {success_count} product(s)!')
            if error_count > 0:
                error_msg = f'{error_count} error(s) occurred:<br>' + '<br>'.join(errors[:10])
                if len(errors) > 10:
                    error_msg += f'<br>...and {len(errors) - 10} more errors'
                messages.error(request, error_msg)
            
            return redirect('product_list', slug=request.business.slug)
            
        except Exception as e:
            messages.error(request, f'Error processing CSV file: {str(e)}')
            return redirect('product_bulk_upload', slug=request.business.slug)
    
    return render(request, 'pos/product_bulk_upload.html')


@login_required
@business_required
def product_toggle_active(request, slug=None, pk=None):
    """Toggle product active/inactive status via AJAX or POST"""
    product = get_object_or_404(Product, business=request.business, pk=pk)
    if request.method == 'POST':
        product.is_active = not product.is_active
        product.save()
        status = 'activated' if product.is_active else 'deactivated'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'is_active': product.is_active, 'status': status})
        messages.success(request, f'Product "{product.name}" has been {status}.')
    return redirect('product_list', slug=request.business.slug)


@business_required
def product_export_csv(request, slug=None):
    """Export products as CSV"""
    import csv
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['name', 'product_code', 'category', 'unit_price', 'stock_quantity', 'low_stock_threshold'])
    
    products = Product.objects.filter(business=request.business).select_related('category').all()
    for product in products:
        writer.writerow([
            product.name,
            product.product_code or '',
            product.category.name if product.category else '',
            product.unit_price,
            product.stock_quantity,
            product.low_stock_threshold
        ])
    
    return response


@login_required
def product_download_template(request):
    """Download CSV template for bulk upload"""
    import csv
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="product_upload_template.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['name', 'product_code', 'category', 'unit_price', 'stock_quantity', 'low_stock_threshold'])
    
    # Add sample rows
    writer.writerow(['Sample Product 1', 'PROD001', 'Electronics', '1500.00', '50', '10'])
    writer.writerow(['Sample Product 2', 'PROD002', 'Groceries', '250.50', '100', '20'])
    writer.writerow(['Sample Product 3', '', 'Beverages', '80.00', '75', '15'])
    
    return response


def _product_form_context(request):
    """Shared context builder for product create/edit forms"""
    from .models import UnitOfMeasurement, Brand
    return {
        'categories': Category.objects.filter(business=request.business).order_by('name'),
        'brands': Brand.objects.filter(business=request.business).order_by('name'),
        'units': UnitOfMeasurement.objects.filter(business=request.business, is_active=True),
        'suppliers': Supplier.objects.filter(business=request.business, is_active=True),
        'product_types': Product.PRODUCT_TYPE_CHOICES,
    }


@business_required
def product_create(request, slug=None):
    """Create new product"""
    from .models import UnitOfMeasurement
    
    if request.method == 'POST':
        name = request.POST.get('name')
        product_code = request.POST.get('product_code')
        barcode = request.POST.get('barcode')
        category_id = request.POST.get('category')
        unit_id = request.POST.get('unit')
        cost_price = request.POST.get('cost_price', '').strip()
        unit_price = request.POST.get('unit_price', '').strip()
        tax_class = request.POST.get('tax_class', 'standard')
        low_stock_threshold = request.POST.get('low_stock_threshold', 10)
        image = request.FILES.get('image')  # Get uploaded image
        
        # Bulk unit fields
        bulk_unit_name = request.POST.get('bulk_unit_name', '').strip()
        bulk_unit_quantity = request.POST.get('bulk_unit_quantity', '').strip()
        bulk_unit_price = request.POST.get('bulk_unit_price', '').strip()
        
        try:
            # Validate cost_price is provided and greater than 0
            if not cost_price:
                messages.error(request, 'Cost Price is required. This is needed for profit tracking and financial reporting.')
                return render(request, 'pos/product_form.html', _product_form_context(request))
            
            cost = Decimal(cost_price)
            if cost <= 0:
                messages.error(request, 'Cost Price must be greater than 0.')
                return render(request, 'pos/product_form.html', _product_form_context(request))
            
            # Validate unit_price
            if not unit_price:
                messages.error(request, 'Selling Price is required.')
                return render(request, 'pos/product_form.html', _product_form_context(request))
            
            selling_price = Decimal(unit_price)
            if selling_price <= 0:
                messages.error(request, 'Selling Price must be greater than 0.')
                return render(request, 'pos/product_form.html', _product_form_context(request))
            
            category = Category.objects.get(id=category_id, business=request.business) if category_id else None
            unit = UnitOfMeasurement.objects.get(id=unit_id, business=request.business) if unit_id else None

            # New fields
            from .models import Brand
            brand_id = request.POST.get('brand')
            brand = Brand.objects.get(id=brand_id, business=request.business) if brand_id else None
            preferred_supplier_id = request.POST.get('preferred_supplier')
            preferred_supplier = Supplier.objects.get(id=preferred_supplier_id, business=request.business) if preferred_supplier_id else None

            # Convert empty strings to default values
            low_stock = Decimal(low_stock_threshold) if low_stock_threshold else Decimal('10')

            product = Product.objects.create(
                business=request.business,
                name=name,
                description=request.POST.get('description', ''),
                product_code=product_code if product_code else None,
                barcode=barcode if barcode else '',
                product_type=request.POST.get('product_type', 'stock'),
                category=category,
                brand=brand,
                unit=unit,
                is_active=request.POST.get('is_active', '1') == '1',
                cost_price=cost,
                unit_price=selling_price,
                wholesale_price=Decimal(request.POST.get('wholesale_price')) if request.POST.get('wholesale_price') else None,
                minimum_price=Decimal(request.POST.get('minimum_price')) if request.POST.get('minimum_price') else None,
                tax_class=tax_class,
                stock_quantity=0,
                low_stock_threshold=low_stock,
                reorder_quantity=Decimal(request.POST.get('reorder_quantity') or '0'),
                preferred_supplier=preferred_supplier,
                lead_time_days=int(request.POST.get('lead_time_days') or '0'),
                image=image if image else None,
                bulk_unit_name=bulk_unit_name if bulk_unit_name else '',
                bulk_unit_quantity=Decimal(bulk_unit_quantity) if bulk_unit_quantity else None,
                bulk_unit_price=Decimal(bulk_unit_price) if bulk_unit_price else None,
                hs_code=request.POST.get('hs_code', ''),
                hs_code_description=request.POST.get('hs_code_description', ''),
                is_excisable=request.POST.get('is_excisable', '0') == '1',
                excise_rate=Decimal(request.POST.get('excise_rate') or '0'),
            )
            
            # Create initial stock adjustment record
            # Stock is 0 for new products - will be added through purchases
            
            # Invalidate dashboard cache
            from django.core.cache import cache
            from .cache_utils import get_cache_key
            from datetime import datetime
            cache_key = get_cache_key('dashboard', request.business.id, datetime.now().date())
            cache.delete(cache_key)
            
            messages.success(request, 'Product created successfully! Add stock through purchase orders.')
            return redirect('product_list', slug=request.business.slug)
        except ValueError as e:
            messages.error(request, f'Invalid price value: {str(e)}')
        except Exception as e:
            messages.error(request, f'Error creating product: {str(e)}')

    return render(request, 'pos/product_form.html', _product_form_context(request))



@business_required
def product_edit(request, slug=None, pk=None):
    """Edit existing product"""
    from .models import UnitOfMeasurement
    product = get_object_or_404(Product, business=request.business, pk=pk)
    
    if request.method == 'POST':
        try:
            # Validate cost_price
            cost_price = request.POST.get('cost_price', '').strip()
            if not cost_price:
                messages.error(request, 'Cost Price is required. This is needed for profit tracking and financial reporting.')
                ctx = _product_form_context(request)
                ctx['product'] = product
                return render(request, 'pos/product_form.html', ctx)
            
            cost = Decimal(cost_price)
            if cost <= 0:
                messages.error(request, 'Cost Price must be greater than 0.')
                ctx = _product_form_context(request)
                ctx['product'] = product
                return render(request, 'pos/product_form.html', ctx)
            
            # Validate unit_price
            unit_price = request.POST.get('unit_price', '').strip()
            if not unit_price:
                messages.error(request, 'Selling Price is required.')
                ctx = _product_form_context(request)
                ctx['product'] = product
                return render(request, 'pos/product_form.html', ctx)
            
            selling_price = Decimal(unit_price)
            if selling_price <= 0:
                messages.error(request, 'Selling Price must be greater than 0.')
                ctx = _product_form_context(request)
                ctx['product'] = product
                return render(request, 'pos/product_form.html', ctx)
            
            product.name = request.POST.get('name')
            product.description = request.POST.get('description', '')
            product.product_code = request.POST.get('product_code') if request.POST.get('product_code') else None
            product.barcode = request.POST.get('barcode', '')
            product.product_type = request.POST.get('product_type', 'stock')
            product.is_active = request.POST.get('is_active', '1') == '1'
            category_id = request.POST.get('category')
            product.category = Category.objects.get(business=request.business, id=category_id) if category_id else None

            from .models import Brand
            brand_id = request.POST.get('brand')
            product.brand = Brand.objects.get(business=request.business, id=brand_id) if brand_id else None

            # Update unit
            unit_id = request.POST.get('unit')
            product.unit = UnitOfMeasurement.objects.get(business=request.business, id=unit_id) if unit_id else None

            preferred_supplier_id = request.POST.get('preferred_supplier')
            product.preferred_supplier = Supplier.objects.get(business=request.business, id=preferred_supplier_id) if preferred_supplier_id else None

            # Update cost price and selling price
            product.cost_price = cost
            product.unit_price = selling_price
            product.wholesale_price = Decimal(request.POST.get('wholesale_price')) if request.POST.get('wholesale_price') else None
            product.minimum_price = Decimal(request.POST.get('minimum_price')) if request.POST.get('minimum_price') else None

            # Update tax class
            product.tax_class = request.POST.get('tax_class', 'standard')

            # Convert empty strings to default values
            low_stock = request.POST.get('low_stock_threshold')
            product.low_stock_threshold = Decimal(low_stock) if low_stock else Decimal('10')
            product.reorder_quantity = Decimal(request.POST.get('reorder_quantity') or '0')
            product.lead_time_days = int(request.POST.get('lead_time_days') or '0')

            # Update bulk unit fields
            bulk_unit_name = request.POST.get('bulk_unit_name', '').strip()
            bulk_unit_quantity = request.POST.get('bulk_unit_quantity', '').strip()
            bulk_unit_price = request.POST.get('bulk_unit_price', '').strip()
            
            product.bulk_unit_name = bulk_unit_name if bulk_unit_name else ''
            product.bulk_unit_quantity = Decimal(bulk_unit_quantity) if bulk_unit_quantity else None
            product.bulk_unit_price = Decimal(bulk_unit_price) if bulk_unit_price else None

            # HS Code / excise
            product.hs_code = request.POST.get('hs_code', '')
            product.hs_code_description = request.POST.get('hs_code_description', '')
            product.is_excisable = request.POST.get('is_excisable', '0') == '1'
            product.excise_rate = Decimal(request.POST.get('excise_rate') or '0')

            # Handle image upload
            image = request.FILES.get('image')
            if image:
                product.image = image
            
            # Handle image removal
            remove_image = request.POST.get('remove_image')
            if remove_image == 'true':
                product.image = None
            
            product.save()
            
            # Invalidate dashboard cache
            from django.core.cache import cache
            from .cache_utils import get_cache_key
            from datetime import datetime
            cache_key = get_cache_key('dashboard', request.business.id, datetime.now().date())
            cache.delete(cache_key)
            
            messages.success(request, 'Product updated successfully!')
            return redirect('product_list', slug=request.business.slug)
        except ValueError as e:
            messages.error(request, f'Invalid price value: {str(e)}')
        except Exception as e:
            messages.error(request, f'Error updating product: {str(e)}')

    ctx = _product_form_context(request)
    ctx['product'] = product
    ctx['stock_history'] = product.stock_adjustments.order_by('-created_at')[:50]
    return render(request, 'pos/product_form.html', ctx)


@business_required
def product_delete(request, slug=None, pk=None):
    """Delete product"""
    product = get_object_or_404(Product, business=request.business, pk=pk)
    
    # Check if product has related records
    sale_items_count = product.saleitem_set.count()
    purchase_items_count = product.purchaseitem_set.count()
    has_related_records = sale_items_count > 0 or purchase_items_count > 0
    
    if request.method == 'POST':
        action = request.POST.get('action', 'delete')
        
        if action == 'discontinue':
            # Mark as out of stock and set quantity to 0
            product.stock_quantity = 0
            product.save()
            messages.success(request, f'Product "{product.name}" has been discontinued (stock set to 0).')
            return redirect('product_list', slug=request.business.slug)
        
        elif action == 'delete':
            try:
                name = product.name
                product.delete()
                messages.success(request, f'Product "{name}" deleted successfully!')
                return redirect('product_list', slug=request.business.slug)
            except models.ProtectedError as e:
                # Handle protected foreign key error
                messages.error(
                    request, 
                    f'Cannot delete product "{product.name}" because it appears in sales or purchase history. '
                    f'Please discontinue the product instead (set stock to 0).'
                )
                return redirect('product_list', slug=request.business.slug)
    
    context = {
        'product': product,
        'sale_items_count': sale_items_count,
        'purchase_items_count': purchase_items_count,
        'has_related_records': has_related_records,
    }
    return render(request, 'pos/product_confirm_delete.html', context)


@business_required
def category_list(request, slug=None):
    """List all categories"""
    categories = Category.objects.filter(business=request.business).all()
    return render(request, 'pos/category_list.html', {'categories': categories})


@business_required
def category_create(request, slug=None):
    """Create new category"""
    if request.method == 'POST':
        name = request.POST.get('name')
        try:
            Category.objects.create(business=request.business, name=name)
            messages.success(request, 'Category created successfully!')
            return redirect('category_list', slug=request.business.slug)
        except Exception as e:
            messages.error(request, f'Error creating category: {str(e)}')
    return render(request, 'pos/category_form.html')


@business_required
def category_edit(request, slug=None, pk=None):
    """Edit existing category"""
    category = get_object_or_404(Category, business=request.business, pk=pk)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        try:
            category.name = name
            category.save()
            messages.success(request, 'Category updated successfully!')
            return redirect('category_list', slug=request.business.slug)
        except Exception as e:
            messages.error(request, f'Error updating category: {str(e)}')
    
    return render(request, 'pos/category_form.html', {'category': category})


@business_required
def category_delete(request, slug=None, pk=None):
    """Delete category"""
    category = get_object_or_404(Category, business=request.business, pk=pk)
    
    # Check if category has products
    product_count = category.products.count()
    has_products = product_count > 0
    
    if request.method == 'POST':
        action = request.POST.get('action', 'delete')
        
        if action == 'reassign':
            # Reassign products to another category or uncategorized
            new_category_id = request.POST.get('new_category')
            if new_category_id:
                new_category = get_object_or_404(Category, business=request.business, pk=new_category_id)
                category.products.update(category=new_category)
                messages.success(request, f'{product_count} product(s) reassigned to "{new_category.name}".')
            else:
                # Set to null (uncategorized)
                category.products.update(category=None)
                messages.success(request, f'{product_count} product(s) set to uncategorized.')
            
            # Now delete the category
            name = category.name
            category.delete()
            messages.success(request, f'Category "{name}" deleted successfully!')
            return redirect('category_list', slug=request.business.slug)
        
        elif action == 'delete':
            try:
                name = category.name
                category.delete()
                messages.success(request, f'Category "{name}" deleted successfully!')
                return redirect('category_list', slug=request.business.slug)
            except models.ProtectedError:
                messages.error(
                    request, 
                    f'Cannot delete category "{category.name}" because it has {product_count} product(s). '
                    f'Please reassign the products first.'
                )
                return redirect('category_list', slug=request.business.slug)
    
    # Get other categories for reassignment option
    other_categories = Category.objects.filter(business=request.business).exclude(pk=pk)
    
    context = {
        'category': category,
        'product_count': product_count,
        'has_products': has_products,
        'other_categories': other_categories,
    }
    return render(request, 'pos/category_confirm_delete.html', context)


# ==================== UNIT OF MEASUREMENT VIEWS ====================

@business_required
def unit_list(request, slug=None):
    """List all units of measurement"""
    from .models import UnitOfMeasurement
    units = UnitOfMeasurement.objects.filter(business=request.business).all()
    return render(request, 'pos/unit_list.html', {'units': units})


@business_required
def unit_create(request, slug=None):
    """Create new unit of measurement"""
    from .models import UnitOfMeasurement
    
    if request.method == 'POST':
        name = request.POST.get('name')
        abbreviation = request.POST.get('abbreviation')
        unit_type = request.POST.get('unit_type', 'count')
        base_unit_id = request.POST.get('base_unit')
        conversion_factor = request.POST.get('conversion_factor', 1)
        
        try:
            base_unit = None
            if base_unit_id:
                base_unit = UnitOfMeasurement.objects.get(pk=base_unit_id, business=request.business)
            
            UnitOfMeasurement.objects.create(
                business=request.business,
                name=name,
                abbreviation=abbreviation,
                unit_type=unit_type,
                base_unit=base_unit,
                conversion_factor=Decimal(conversion_factor)
            )
            messages.success(request, f'Unit "{name}" created successfully!')
            return redirect('unit_list', slug=request.business.slug)
        except Exception as e:
            messages.error(request, f'Error creating unit: {str(e)}')
    
    # Get existing units for base unit selection
    units = UnitOfMeasurement.objects.filter(business=request.business).all()
    return render(request, 'pos/unit_form.html', {'units': units})


@business_required
def unit_edit(request, slug=None, pk=None):
    """Edit existing unit of measurement"""
    from .models import UnitOfMeasurement
    unit = get_object_or_404(UnitOfMeasurement, business=request.business, pk=pk)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        abbreviation = request.POST.get('abbreviation')
        unit_type = request.POST.get('unit_type', 'count')
        base_unit_id = request.POST.get('base_unit')
        conversion_factor = request.POST.get('conversion_factor', 1)
        is_active = request.POST.get('is_active') == 'on'
        
        try:
            base_unit = None
            if base_unit_id:
                base_unit = UnitOfMeasurement.objects.get(pk=base_unit_id, business=request.business)
            
            unit.name = name
            unit.abbreviation = abbreviation
            unit.unit_type = unit_type
            unit.base_unit = base_unit
            unit.conversion_factor = Decimal(conversion_factor)
            unit.is_active = is_active
            unit.save()
            
            messages.success(request, f'Unit "{name}" updated successfully!')
            return redirect('unit_list', slug=request.business.slug)
        except Exception as e:
            messages.error(request, f'Error updating unit: {str(e)}')
    
    # Get other units for base unit selection (exclude self)
    units = UnitOfMeasurement.objects.filter(business=request.business).exclude(pk=pk)
    return render(request, 'pos/unit_form.html', {'unit': unit, 'units': units})


@business_required
def unit_delete(request, slug=None, pk=None):
    """Delete unit of measurement"""
    from .models import UnitOfMeasurement
    unit = get_object_or_404(UnitOfMeasurement, business=request.business, pk=pk)
    
    # Check if unit has products
    product_count = unit.products.count()
    has_products = product_count > 0
    
    if request.method == 'POST':
        action = request.POST.get('action', 'delete')
        
        if action == 'reassign':
            # Reassign products to another unit or no unit
            new_unit_id = request.POST.get('new_unit')
            if new_unit_id:
                new_unit = get_object_or_404(UnitOfMeasurement, business=request.business, pk=new_unit_id)
                unit.products.update(unit=new_unit)
                messages.success(request, f'{product_count} product(s) reassigned to "{new_unit.name}".')
            else:
                # Set to null (no unit)
                unit.products.update(unit=None)
                messages.success(request, f'{product_count} product(s) set to no unit.')
            
            # Now delete the unit
            name = unit.name
            unit.delete()
            messages.success(request, f'Unit "{name}" deleted successfully!')
            return redirect('unit_list', slug=request.business.slug)
        
        elif action == 'delete':
            try:
                name = unit.name
                unit.delete()
                messages.success(request, f'Unit "{name}" deleted successfully!')
                return redirect('unit_list', slug=request.business.slug)
            except models.ProtectedError:
                messages.error(
                    request, 
                    f'Cannot delete unit "{unit.name}" because it has {product_count} product(s). '
                    f'Please reassign the products first.'
                )
                return redirect('unit_list', slug=request.business.slug)
    
    # Get other units for reassignment option
    other_units = UnitOfMeasurement.objects.filter(business=request.business).exclude(pk=pk)
    
    context = {
        'unit': unit,
        'product_count': product_count,
        'has_products': has_products,
        'other_units': other_units,
    }
    return render(request, 'pos/unit_confirm_delete.html', context)


@business_required
def pos_screen(request, slug=None):
    """Main POS sales screen - Optimized for fast loading"""
    from .models import PaymentMethod, POSSession
    from django.db.models import Q
    from django.http import JsonResponse
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check if there's an open POS session
    open_session = POSSession.objects.filter(
        business=request.business,
        status='open'
    ).first()
    
    if not open_session:
        # No open session - redirect to Z-Report page to open one
        messages.warning(
            request,
            'No active POS session. Please open a new session before making sales.'
        )
        return redirect('zreport_session_status', slug=request.business.slug)
    
    # Simple diagnostic endpoint
    if request.GET.get('test_ajax'):
        logger.info(f"🧪 Test AJAX endpoint hit - User: {request.user}, Business: {getattr(request, 'business', None)}")
        
        # Also test product count
        product_count = 0
        if hasattr(request, 'business') and request.business:
            try:
                product_count = Product.objects.filter(business=request.business).count()
            except Exception as e:
                logger.error(f"Error counting products: {e}")
        
        return JsonResponse({
            'success': True,
            'message': 'AJAX is working!',
            'user': str(request.user),
            'business': str(getattr(request, 'business', None)),
            'business_id': getattr(request.business, 'id', None) if hasattr(request, 'business') else None,
            'product_count': product_count,
            'path': request.path
        })
    
    # Handle AJAX request for price refresh
    if request.GET.get('get_prices'):
        product_ids = request.GET.get('ids', '').split(',')
        try:
            product_ids = [int(pid) for pid in product_ids if pid]
            products = Product.objects.filter(
                business=request.business,
                id__in=product_ids
            ).values('id', 'unit_price')
            
            prices = {str(p['id']): float(p['unit_price']) for p in products}
            return JsonResponse({'success': True, 'prices': prices})
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Invalid product IDs'})
    
    # Handle AJAX request for lazy loading products
    if request.GET.get('load_products'):
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        
        try:
            # Log request details
            logger.info(f"🚀 POS Products AJAX Request - User: {request.user}, Business: {getattr(request, 'business', None)}")
            logger.info(f"   Request path: {request.path}")
            logger.info(f"   Request GET params: {dict(request.GET)}")
            
            # Check if business context exists
            if not hasattr(request, 'business') or request.business is None:
                logger.error("❌ No business context in request!")
                return JsonResponse({
                    'success': False,
                    'error': 'No business context. Please refresh the page.',
                    'debug': {
                        'has_business_attr': hasattr(request, 'business'),
                        'business_value': str(getattr(request, 'business', None)),
                        'path': request.path,
                        'user': str(request.user)
                    }
                }, status=400)
            
            search_query = request.GET.get('q', '').strip()
            category_filter = request.GET.get('category', '')
            offset = int(request.GET.get('offset', 0))
            limit = int(request.GET.get('limit', 50))
            
            logger.info(f"   Filters - Search: '{search_query}', Category: '{category_filter}', Offset: {offset}, Limit: {limit}")
        
            # Base product query with optimizations
            products_query = Product.objects.filter(
                business=request.business
            ).select_related('category', 'unit').only(
                'id', 'name', 'unit_price', 'stock_quantity', 'barcode',
                'product_code', 'category__name', 'unit__name', 'unit__abbreviation',
                'tax_class', 'bulk_unit_name', 'bulk_unit_price', 'bulk_unit_quantity'
            )
            
            logger.info(f"   Base query count: {products_query.count()}")
            
            # Apply filters
            if search_query:
                products_query = products_query.filter(
                    Q(name__icontains=search_query) |
                    Q(barcode__icontains=search_query) |
                    Q(product_code__icontains=search_query)
                )
                logger.info(f"   After search filter: {products_query.count()}")
            
            if category_filter:
                products_query = products_query.filter(category_id=category_filter)
                logger.info(f"   After category filter: {products_query.count()}")
            
            # Order by name for consistent results (removed created_at ordering for performance)
            products_query = products_query.order_by('name')
            
            # Get total count efficiently
            total_count = products_query.count()
            logger.info(f"   Total products matching filters: {total_count}")
            
            # Paginate
            products = list(products_query[offset:offset + limit])
            logger.info(f"   Fetched {len(products)} products for this page")
            
            # Serialize products
            products_data = []
            for product in products:
                products_data.append({
                    'id': product.id,
                    'name': product.name,
                    'unit_price': float(product.unit_price),
                    'stock_quantity': product.stock_quantity,
                    'barcode': product.barcode or '',
                    'product_code': product.product_code,
                    'category_name': product.category.name if product.category else '',
                    'unit_name': product.unit.abbreviation if product.unit else 'pcs',
                    'tax_class': product.tax_class,
                    'has_bulk': bool(product.bulk_unit_name and product.bulk_unit_price),
                    'bulk_unit_name': product.bulk_unit_name or '',
                    'bulk_unit_price': float(product.bulk_unit_price) if product.bulk_unit_price else 0,
                    'bulk_unit_quantity': product.bulk_unit_quantity or 1,
                })
            
            response_data = {
                'success': True,
                'products': products_data,
                'total': total_count,
                'has_more': (offset + limit) < total_count,
            }
            
            logger.info(f"✅ Successfully returning {len(products_data)} products")
            return JsonResponse(response_data)
        
        except Exception as e:
            logger.error(f"💥 Error in POS products AJAX: {str(e)}")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            return JsonResponse({
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc(),
                'debug': {
                    'has_business': hasattr(request, 'business'),
                    'business': str(getattr(request, 'business', None)),
                    'user': str(request.user),
                    'path': request.path
                }
            }, status=500)
    
    # Initial page load - minimal data for fast rendering
    categories = Category.objects.filter(business=request.business).only('id', 'name')
    
    # Optimize customer query - only load when needed
    customers = Customer.objects.filter(
        business=request.business, 
        is_active=True
    ).only('id', 'name', 'phone').order_by('name')[:100]
    
    # Payment methods
    payment_methods = PaymentMethod.objects.filter(
        business=request.business, 
        is_active=True
    ).only('id', 'name', 'code', 'requires_reference')
    
    vat_rate = getattr(settings, 'VAT_RATE', 16)
    
    # Get total product count for display
    total_products = Product.objects.filter(
        business=request.business
    ).count()
    
    context = {
        'categories': categories,
        'customers': customers,
        'payment_methods': payment_methods,
        'vat_rate': vat_rate,
        'total_products': total_products,
        'lazy_load': True,
        'current_session': open_session,  # Add session info to context
    }
    return render(request, 'pos/pos_screen.html', context)


@business_required
def complete_sale(request, slug=None):
    """Process and complete a sale"""
    if request.method == 'POST':
        try:
            from django.db import transaction as db_transaction
            from .models import POSSession
            open_session = POSSession.objects.filter(
                business=request.business,
                status='open'
            ).first()
            
            if not open_session:
                messages.error(
                    request,
                    'Cannot complete sale: No active POS session. Please open a new session first.'
                )
                return redirect('zreport_session_status', slug=request.business.slug)
            
            # Get sale data
            items_data = request.POST.getlist('items')
            payments_data = request.POST.getlist('payments')
            customer_id = request.POST.get('customer_id')
            discount_type = request.POST.get('discount_type', 'percentage')
            discount_value = Decimal(request.POST.get('discount_value', 0))
            amount_paid = Decimal(request.POST.get('amount_paid', 0))
            change_given = Decimal(request.POST.get('change_given', 0))
            is_credit_sale = request.POST.get('is_credit_sale', '0') == '1'
            vat_rate = Decimal(getattr(settings, 'VAT_RATE', 16))
            
            if not items_data:
                messages.error(request, 'No items in cart!')
                return redirect('pos_screen', slug=request.business.slug)
            
            # Get customer if selected
            customer = None
            if customer_id:
                try:
                    customer = Customer.objects.get(id=customer_id, business=request.business)
                except Customer.DoesNotExist:
                    pass
            
            # Validate credit sale
            if is_credit_sale:
                if not customer:
                    messages.error(request, 'A customer must be selected for a credit sale.')
                    return redirect('pos_screen', slug=request.business.slug)
                if customer.credit_limit <= 0:
                    messages.error(request, f'{customer.name} does not have a credit limit set.')
                    return redirect('pos_screen', slug=request.business.slug)
            
            # Calculate totals and check stock
            # Prices are now tax-inclusive (final prices)
            total_inclusive = Decimal(0)
            sale_items = []
            
            for item_str in items_data:
                parts = item_str.split(',')
                product_id, quantity, price = parts[0], parts[1], parts[2]
                item_note = ''
                if len(parts) > 3:
                    from urllib.parse import unquote
                    item_note = unquote(parts[3])
                product = Product.objects.get(id=product_id, business=request.business)
                quantity = int(quantity)
                unit_price = Decimal(price)  # This is tax-inclusive price
                total_price = unit_price * quantity
                
                # Check stock availability
                if not product.has_sufficient_stock(quantity):
                    messages.error(request, f'Insufficient stock for {product.name}. Available: {product.stock_quantity}')
                    return redirect('pos_screen', slug=request.business.slug)
                
                total_inclusive += total_price
                sale_items.append({
                    'product': product,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'total_price': total_price,
                    'note': item_note,
                })
            
            # Calculate discount on tax-inclusive amount
            if discount_type == 'percentage':
                discount_amount = (total_inclusive * discount_value) / 100
            else:
                discount_amount = discount_value
            
            # Total after discount (still tax-inclusive)
            total = total_inclusive - discount_amount
            
            # Extract VAT from the tax-inclusive price
            # Formula: VAT = (Price * VAT_RATE) / (100 + VAT_RATE)
            vat_amount = (total * vat_rate) / (100 + vat_rate)
            subtotal = total - vat_amount
            
            # Create sale atomically — all or nothing
            with db_transaction.atomic():
                sale = Sale.objects.create(
                    business=request.business,
                    cashier=request.user,
                    customer=customer,
                    session=open_session,
                    subtotal=subtotal,
                    vat_rate=vat_rate,
                    vat_amount=vat_amount,
                    discount_type=discount_type,
                    discount_value=discount_value,
                    discount_amount=discount_amount,
                    total=total,
                    amount_paid=amount_paid,
                    change_given=change_given,
                    is_credit_sale=is_credit_sale,
                )

                # Create sale items and deduct stock
                for item in sale_items:
                    SaleItem.objects.create(
                        sale=sale,
                        product=item['product'],
                        quantity=item['quantity'],
                        unit_price=item['unit_price'],
                        note=item.get('note', ''),
                        cost_price_at_sale=item['product'].cost_price,
                    )
                    previous_qty = item['product'].stock_quantity
                    item['product'].deduct_stock(item['quantity'])
                    StockAdjustment.objects.create(
                        product=item['product'],
                        adjustment_type='sale',
                        quantity_change=-item['quantity'],
                        previous_quantity=previous_qty,
                        new_quantity=item['product'].stock_quantity,
                        reason=f'Sale: {sale.invoice_number}'
                    )

                # Process payment methods
                from .models import PaymentMethod
                if payments_data:
                    total_payment_allocated = Decimal('0.00')
                    for payment_str in payments_data:
                        method_id, amount, reference = payment_str.split(',')
                        payment_method = PaymentMethod.objects.get(id=method_id, business=request.business)
                        payment_amount = Decimal(amount)
                        is_cash = payment_method.code == 'CASH' or payment_method.name.upper() == 'CASH'
                        remaining_amount = sale.total - total_payment_allocated
                        if is_cash and payment_amount > remaining_amount:
                            payment_amount = remaining_amount
                        if payment_amount > 0:
                            SalePayment.objects.create(
                                sale=sale,
                                payment_method=payment_method,
                                amount=payment_amount,
                                reference_number=reference
                            )
                            total_payment_allocated += payment_amount

                # Handle credit sale — validate and update customer balance
                if is_credit_sale and customer:
                    if customer.get_available_credit() < total:
                        raise ValueError(f'Insufficient credit. Available: KES {customer.get_available_credit()}, Required: KES {total}')
                    customer.credit_balance += total
                    customer.save(update_fields=['credit_balance'])

                # Handle loyalty points
                if customer:
                    if discount_type == 'points' and discount_value > 0:
                        points_redeemed = int(discount_value)
                        if points_redeemed < 100:
                            raise ValueError('Minimum redemption is 100 points')
                        if customer.loyalty_points < 100:
                            raise ValueError(f'Customer needs at least 100 points to redeem. Current balance: {customer.loyalty_points} points')
                        if points_redeemed <= customer.loyalty_points:
                            customer.redeem_points(points_redeemed, sale=sale, description=f"Redeemed for discount - {sale.invoice_number}")
                        else:
                            raise ValueError(f'Customer only has {customer.loyalty_points} points available')
                    points_earned = customer.add_loyalty_points(total, sale=sale, description=f"Purchase - {sale.invoice_number}")
                    customer.total_purchases += total
                    customer.visit_count += 1
                    customer.save()
                    message_parts = [f'Sale completed! Invoice: {sale.invoice_number}.']
                    if is_credit_sale:
                        message_parts.append(f'Charged KES {total} to credit account.')
                    elif change_given > 0:
                        message_parts.append(f'Change: KES {change_given}.')
                    if discount_type == 'points' and discount_value > 0:
                        message_parts.append(f'{int(discount_value)} points redeemed.')
                    message_parts.append(f'Earned {points_earned} loyalty points!')
                    messages.success(request, ' '.join(message_parts))
                else:
                    if change_given > 0:
                        messages.success(request, f'Sale completed! Invoice: {sale.invoice_number}. Change: KES {change_given}')
                    else:
                        messages.success(request, f'Sale completed! Invoice: {sale.invoice_number}')

            # Invalidate dashboard cache after sale
            from django.core.cache import cache
            from .cache_utils import get_cache_key
            cache_key = get_cache_key('dashboard', request.business.id, timezone.localdate())
            cache.delete(cache_key)
            
            return redirect('thermal_receipt', slug=request.business.slug, pk=sale.pk)
            
        except Exception as e:
            messages.error(request, f'Error completing sale: {str(e)}')
            return redirect('pos_screen', slug=request.business.slug)
    
    return redirect('pos_screen', slug=request.business.slug)


@login_required
def invoice_view(request, slug, pk):
    """View invoice details"""
    sale = get_object_or_404(Sale, pk=pk)
    shop_name = getattr(settings, 'SHOP_NAME', 'My Retail Shop')
    return render(request, 'pos/invoice.html', {'sale': sale, 'shop_name': shop_name})
@login_required
def thermal_receipt(request, slug, pk):
    """View thermal printer receipt - Optimized for fast loading"""
    from .models import BusinessSettings
    
    # Optimize query with select_related and prefetch_related to avoid N+1 queries
    sale = get_object_or_404(
        Sale.objects.select_related(
            'customer',
            'cashier',
            'business'
        ).prefetch_related(
            'items__product__unit',  # Prefetch items with product and unit
            'payments__payment_method',  # Prefetch payments with payment method
            'loyalty_transactions'  # Prefetch loyalty transactions
        ),
        pk=pk,
        business=request.business
    )
    
    # Handle email receipt request
    if request.method == 'POST' and 'email_receipt' in request.POST:
        customer_email = request.POST.get('customer_email')
        if customer_email:
            from .email_service import EmailService
            success = EmailService.send_sale_receipt(sale, customer_email)
            if success:
                messages.success(request, f'Receipt emailed to {customer_email}')
            else:
                messages.error(request, 'Failed to send email. Check email settings.')
        else:
            messages.error(request, 'Please provide an email address')
        return redirect('thermal_receipt', slug=slug, pk=pk)
    
    # Get business settings (cached)
    try:
        business_settings = BusinessSettings.get_settings(request.business)
    except Exception:
        business_settings = None
    
    return render(request, 'pos/receipt_thermal.html', {
        'sale': sale, 
        'shop_name': request.business.name,
        'business_settings': business_settings,
    })



@login_required
def invoice_pdf(request, slug, pk):
    """Generate PDF invoice"""
    sale = get_object_or_404(Sale, pk=pk)
    shop_name = getattr(settings, 'SHOP_NAME', 'My Retail Shop')
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], alignment=TA_CENTER)
    elements.append(Paragraph(shop_name, title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Invoice details
    invoice_style = ParagraphStyle('InvoiceDetails', parent=styles['Normal'], fontSize=10)
    elements.append(Paragraph(f"<b>Invoice Number:</b> {sale.invoice_number}", invoice_style))
    elements.append(Paragraph(f"<b>Date:</b> {sale.date.strftime('%d/%m/%Y %H:%M')}", invoice_style))
    if sale.cashier:
        elements.append(Paragraph(f"<b>Cashier:</b> {sale.cashier.get_full_name() or sale.cashier.username}", invoice_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Items table
    data = [['Item', 'Qty', 'Price', 'Total']]
    for item in sale.items.all():
        data.append([
            item.product.name,
            str(item.quantity),
            f'KES {item.unit_price:,.2f}',
            f'KES {item.total_price:,.2f}'
        ])
    
    # Add totals
    data.append(['', '', 'Subtotal (excl. VAT):', f'KES {sale.subtotal:,.2f}'])
    if sale.discount_amount > 0:
        data.append(['', '', f'Discount ({sale.discount_value}{"%" if sale.discount_type == "percentage" else ""}):', f'KES {sale.discount_amount:,.2f}'])
    data.append(['', '', f'VAT ({sale.vat_rate}%):', f'KES {sale.vat_amount:,.2f}'])
    data.append(['', '', '<b>TOTAL (incl. VAT):</b>', f'<b>KES {sale.total:,.2f}</b>'])
    
    table = Table(data, colWidths=[3*inch, 1*inch, 1.5*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -5), 1, colors.black),
        ('LINEBELOW', (2, -4), (-1, -4), 1, colors.black),
        ('LINEBELOW', (2, -1), (-1, -1), 2, colors.black),
    ]))
    
    elements.append(table)
    
    # Add payment details if available
    if sale.payments.exists():
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("<b>Payment Details:</b>", styles['Heading3']))
        elements.append(Spacer(1, 0.1*inch))
        
        payment_data = [['Payment Method', 'Amount', 'Reference']]
        for payment in sale.payments.all():
            payment_data.append([
                payment.payment_method.name,
                f'KES {payment.amount:,.2f}',
                payment.reference_number or '-'
            ])
        
        # Add total paid and change
        payment_data.append(['Total Paid:', f'KES {sale.amount_paid:,.2f}', ''])
        if sale.change_given > 0:
            payment_data.append(['Change Given:', f'KES {sale.change_given:,.2f}', ''])
        
        payment_table = Table(payment_data, colWidths=[2.5*inch, 2*inch, 2.5*inch])
        payment_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('LINEABOVE', (0, -2), (-1, -2), 1, colors.black),
        ]))
        
        elements.append(payment_table)
    
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph("Thank you for your business!", styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{sale.invoice_number}.pdf"'
    return response


@business_required
@business_permission_required('can_view_reports')
def sales_report(request, slug=None):
    """Daily sales report"""
    # Get date filter
    date_str = request.GET.get('date')
    if date_str:
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            filter_date = datetime.now().date()
    else:
        filter_date = datetime.now().date()
    
    # Get sales for the date - filter by business
    sales = Sale.objects.filter(business=request.business, date__date=filter_date).prefetch_related('items')
    
    # Calculate summary
    summary = sales.aggregate(
        total_sales=Sum('total'),
        total_vat=Sum('vat_amount'),
        total_discounts=Sum('discount_amount'),
        transaction_count=Count('id')
    )
    
    context = {
        'sales': sales,
        'filter_date': filter_date,
        'summary': summary,
    }
    return render(request, 'pos/sales_report.html', context)


@business_required
def sales_list(request, slug=None):
    """List all sales with filters and pagination"""
    from django.core.paginator import Paginator
    from datetime import datetime, timedelta
    
    # Get all sales for the business
    sales = Sale.objects.filter(business=request.business).select_related('cashier', 'customer').prefetch_related('items', 'payments')
    
    # Date range filter
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    date_range = request.GET.get('date_range', '')
    
    # Quick date range filters
    if date_range == 'today':
        today = datetime.now().date()
        sales = sales.filter(date__date=today)
    elif date_range == 'yesterday':
        yesterday = datetime.now().date() - timedelta(days=1)
        sales = sales.filter(date__date=yesterday)
    elif date_range == 'this_week':
        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        sales = sales.filter(date__date__gte=start_of_week)
    elif date_range == 'this_month':
        today = datetime.now().date()
        start_of_month = today.replace(day=1)
        sales = sales.filter(date__date__gte=start_of_month)
    elif date_range == 'last_month':
        today = datetime.now().date()
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        sales = sales.filter(date__date__gte=last_month_start, date__date__lte=last_month_end)
    elif start_date and end_date:
        # Custom date range
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            sales = sales.filter(date__date__gte=start, date__date__lte=end)
        except ValueError:
            pass
    elif start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            sales = sales.filter(date__date__gte=start)
        except ValueError:
            pass
    elif end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            sales = sales.filter(date__date__lte=end)
        except ValueError:
            pass
    
    # Cashier filter
    cashier_id = request.GET.get('cashier')
    if cashier_id:
        sales = sales.filter(cashier_id=cashier_id)
    
    # Customer filter
    customer_id = request.GET.get('customer')
    if customer_id:
        sales = sales.filter(customer_id=customer_id)
    
    # Search by invoice number
    search = request.GET.get('search', '').strip()
    if search:
        sales = sales.filter(invoice_number__icontains=search)
    
    # Category filter
    category_id = request.GET.get('category')
    if category_id:
        sales = sales.filter(items__product__category_id=category_id).distinct()

    # Payment method filter
    payment_method_id = request.GET.get('payment_method')
    if payment_method_id:
        sales = sales.filter(payments__payment_method_id=payment_method_id).distinct()
    
    # Minimum amount filter
    min_amount = request.GET.get('min_amount')
    if min_amount:
        try:
            sales = sales.filter(total__gte=Decimal(min_amount))
        except (ValueError, InvalidOperation):
            pass
    
    # Maximum amount filter
    max_amount = request.GET.get('max_amount')
    if max_amount:
        try:
            sales = sales.filter(total__lte=Decimal(max_amount))
        except (ValueError, InvalidOperation):
            pass
    
    # Order by
    order_by = request.GET.get('order_by', '-date')
    if order_by in ['date', '-date', 'total', '-total', 'invoice_number', '-invoice_number']:
        sales = sales.order_by(order_by)
    
    # Calculate summary before pagination
    summary = sales.aggregate(
        total_sales=Sum('total'),
        total_vat=Sum('vat_amount'),
        total_discounts=Sum('discount_amount'),
        total_items=Sum('items__quantity'),
        transaction_count=Count('id')
    )
    
    # Pagination
    per_page = request.GET.get('per_page', '50')
    try:
        per_page = int(per_page)
        if per_page not in [25, 50, 100, 200]:
            per_page = 50
    except (ValueError, TypeError):
        per_page = 50
    
    paginator = Paginator(sales, per_page)
    page = request.GET.get('page', 1)
    sales_page = paginator.get_page(page)
    
    # Get filter options
    cashiers = User.objects.filter(business_memberships__business=request.business).distinct()
    customers = Customer.objects.filter(business=request.business)
    payment_methods = PaymentMethod.objects.filter(business=request.business)
    categories = Category.objects.filter(business=request.business).order_by('name')
    
    context = {
        'sales': sales_page,
        'summary': summary,
        'cashiers': cashiers,
        'customers': customers,
        'payment_methods': payment_methods,
        'categories': categories,
        'search': search,
        'start_date': start_date or '',
        'end_date': end_date or '',
        'date_range': date_range,
        'cashier_id': cashier_id,
        'customer_id': customer_id,
        'payment_method_id': payment_method_id,
        'category_id': category_id,
        'min_amount': min_amount or '',
        'max_amount': max_amount or '',
        'order_by': order_by,
        'per_page': per_page,
    }
    return render(request, 'pos/sales_list.html', context)


# ==================== PRODUCT QUICK-ADD APIs ====================

@login_required
@business_required
def api_create_category(request, slug=None):
    """AJAX: Quick-create a category from the product form"""
    from django.http import JsonResponse
    import json
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)
    cat, created = Category.objects.get_or_create(business=request.business, name=name)
    return JsonResponse({'id': cat.pk, 'name': cat.name})


@login_required
@business_required
def api_create_brand(request, slug=None):
    """AJAX: Quick-create a brand from the product form"""
    from django.http import JsonResponse
    from .models import Brand
    import json
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)
    brand, created = Brand.objects.get_or_create(business=request.business, name=name)
    return JsonResponse({'id': brand.pk, 'name': brand.name})


@business_required
def search_product_by_code(request, slug=None):
    """API endpoint to search product by barcode/product code"""
    code = request.GET.get('code', '').strip()
    
    if not code:
        return JsonResponse({'error': 'No code provided'}, status=400)
    
    try:
        product = Product.objects.get(business=request.business, product_code=code)
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'product_code': product.product_code,
                'price': float(product.unit_price),
                'category': product.category.name if product.category else None,
                'stock_quantity': product.stock_quantity,
                'in_stock': not product.is_out_of_stock(),
                'tax_class': product.tax_class
            }
        })
    except Product.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'Product with code "{code}" not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@business_required
def search_customer_by_phone(request, slug=None):
    """API endpoint to search customer by phone number or customer code"""
    query = request.GET.get('query', '').strip()
    
    if not query:
        return JsonResponse({'error': 'No phone or code provided'}, status=400)
    
    try:
        # Try to find by phone first (most common in Kenya)
        try:
            customer = Customer.objects.get(business=request.business, phone=query)
        except Customer.DoesNotExist:
            # If not found by phone, try customer code
            customer = Customer.objects.get(business=request.business, customer_code=query)
        
        return JsonResponse({
            'success': True,
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'customer_code': customer.customer_code,
                'loyalty_points': customer.loyalty_points,
                'tier': customer.tier,
                'tier_display': customer.get_tier_display(),
                'customer_type': customer.customer_type,
                'credit_limit': float(customer.credit_limit),
                'credit_balance': float(customer.credit_balance),
                'available_credit': float(customer.get_available_credit()),
            }
        })
    except Customer.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'Customer with phone/code "{query}" not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@business_required
def stock_list(request, slug=None):
    """View all products with stock information"""
    # Filter options
    status_filter = request.GET.get('status', 'all')
    
    products = Product.objects.filter(business=request.business).select_related('category').all()
    
    if status_filter == 'low':
        products = products.filter(stock_quantity__lte=models.F('low_stock_threshold'))
    elif status_filter == 'out':
        products = products.filter(stock_quantity=0)
    
    context = {
        'products': products,
        'status_filter': status_filter,
    }
    return render(request, 'pos/stock_list.html', context)


@business_required
def stock_adjust(request, slug=None, pk=None):
    """Adjust stock for a product"""
    product = get_object_or_404(Product, pk=pk, business=request.business)
    
    if request.method == 'POST':
        adjustment_type = request.POST.get('adjustment_type')
        quantity_change = int(request.POST.get('quantity_change', 0))
        reason = request.POST.get('reason', '')
        
        if quantity_change == 0:
            messages.error(request, 'Quantity change cannot be zero!')
            return redirect('stock_adjust', slug=request.business.slug, pk=pk)
        
        # ENFORCE: Cannot restock without a purchase order
        if adjustment_type == 'restock':
            messages.error(request, 
                'Direct restocking is not allowed! Please create a Purchase Order to add stock. '
                'Go to Purchasing > Purchase Orders > Create New Purchase Order.')
            return redirect('stock_adjust', slug=request.business.slug, pk=pk)
        
        try:
            previous_qty = product.stock_quantity
            
            # For positive adjustments (return, correction with +)
            if adjustment_type in ['return', 'correction'] and quantity_change > 0:
                product.add_stock(quantity_change)
            # For negative adjustments (damage, correction with -)
            else:
                if not product.has_sufficient_stock(abs(quantity_change)):
                    messages.error(request, 'Cannot deduct more than available stock!')
                    return redirect('stock_adjust', slug=request.business.slug, pk=pk)
                product.deduct_stock(abs(quantity_change))
            
            # Create adjustment record
            StockAdjustment.objects.create(
                product=product,
                adjustment_type=adjustment_type,
                quantity_change=quantity_change if adjustment_type in ['return', 'correction'] else -abs(quantity_change),
                previous_quantity=previous_qty,
                new_quantity=product.stock_quantity,
                reason=reason
            )
            
            # Invalidate dashboard cache
            from django.core.cache import cache
            from .cache_utils import get_cache_key
            from datetime import datetime
            cache_key = get_cache_key('dashboard', request.business.id, datetime.now().date())
            cache.delete(cache_key)
            
            messages.success(request, f'Stock adjusted successfully! New quantity: {product.stock_quantity}')
            return redirect('stock_list', slug=request.business.slug)
            
        except Exception as e:
            messages.error(request, f'Error adjusting stock: {str(e)}')
    
    return render(request, 'pos/stock_adjust.html', {'product': product})


@business_required
def stock_history(request, slug=None, pk=None):
    """View stock adjustment history for a product"""
    product = get_object_or_404(Product, business=request.business, pk=pk)
    adjustments = product.stock_adjustments.all()
    
    context = {
        'product': product,
        'adjustments': adjustments,
    }
    return render(request, 'pos/stock_history.html', context)


@business_required
def low_stock_alert(request, slug=None):
    """View products with low or out of stock"""
    low_stock = Product.objects.filter(
        business=request.business,
        stock_quantity__lte=models.F('low_stock_threshold'),
        stock_quantity__gt=0
    ).select_related('category')
    
    out_of_stock = Product.objects.filter(
        business=request.business,
        stock_quantity=0
    ).select_related('category')
    
    context = {
        'low_stock_products': low_stock,
        'out_of_stock_products': out_of_stock,
    }
    return render(request, 'pos/low_stock_alert.html', context)


# ==================== SUPPLIER MANAGEMENT ====================

@business_required
def supplier_list(request, slug=None):
    """List all suppliers"""
    suppliers = Supplier.objects.filter(business=request.business).all()
    
    # Add purchase statistics for each supplier
    for supplier in suppliers:
        supplier.total_purchases_amount = supplier.total_purchases()
        supplier.purchases_count = supplier.purchase_count()
    
    context = {
        'suppliers': suppliers,
    }
    return render(request, 'pos/supplier_list.html', context)


@business_required
def supplier_create(request, slug=None):
    """Create a new supplier"""
    if request.method == 'POST':
        name = request.POST.get('name')
        contact_person = request.POST.get('contact_person', '')
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')
        notes = request.POST.get('notes', '')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Supplier name is required!')
            return render(request, 'pos/supplier_form.html')
        
        if email:
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_email(email)
            except DjangoValidationError:
                messages.error(request, f'"{email}" is not a valid email address.')
                return render(request, 'pos/supplier_form.html', {'form_data': request.POST})
        
        Supplier.objects.create(
            business=request.business,
            name=name,
            contact_person=contact_person,
            email=email,
            phone=phone,
            address=address,
            notes=notes,
            is_active=is_active
        )
        
        messages.success(request, f'Supplier "{name}" created successfully!')
        return redirect('supplier_list', slug=request.business.slug)
    
    return render(request, 'pos/supplier_form.html')


@business_required
def supplier_edit(request, slug=None, pk=None):
    """Edit an existing supplier"""
    supplier = get_object_or_404(Supplier, business=request.business, pk=pk)
    
    if request.method == 'POST':
        supplier.name = request.POST.get('name')
        supplier.contact_person = request.POST.get('contact_person', '')
        supplier.email = request.POST.get('email', '').strip()
        supplier.phone = request.POST.get('phone', '')
        supplier.address = request.POST.get('address', '')
        supplier.notes = request.POST.get('notes', '')
        supplier.is_active = request.POST.get('is_active') == 'on'
        
        if not supplier.name:
            messages.error(request, 'Supplier name is required!')
            return render(request, 'pos/supplier_form.html', {'supplier': supplier})
        
        if supplier.email:
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_email(supplier.email)
            except DjangoValidationError:
                messages.error(request, f'"{supplier.email}" is not a valid email address.')
                return render(request, 'pos/supplier_form.html', {'supplier': supplier})
        
        supplier.save()
        messages.success(request, f'Supplier "{supplier.name}" updated successfully!')
        return redirect('supplier_list', slug=request.business.slug)
    
    context = {
        'supplier': supplier,
    }
    return render(request, 'pos/supplier_form.html', context)


@business_required
def supplier_delete(request, slug=None, pk=None):
    """Delete a supplier"""
    supplier = get_object_or_404(Supplier, business=request.business, pk=pk)
    
    # Check if supplier has related records
    purchase_count = supplier.purchases.count()
    payment_count = supplier.payments.count()
    has_related_records = purchase_count > 0 or payment_count > 0
    
    if request.method == 'POST':
        action = request.POST.get('action', 'delete')
        
        if action == 'deactivate':
            # Deactivate instead of delete
            supplier.is_active = False
            supplier.save()
            messages.success(request, f'Supplier "{supplier.name}" has been deactivated.')
            return redirect('supplier_list', slug=request.business.slug)
        
        elif action == 'delete':
            try:
                name = supplier.name
                supplier.delete()
                messages.success(request, f'Supplier "{name}" deleted successfully!')
                return redirect('supplier_list', slug=request.business.slug)
            except models.ProtectedError as e:
                # Handle protected foreign key error
                messages.error(
                    request, 
                    f'Cannot delete supplier "{supplier.name}" because it has related purchase orders or payments. '
                    f'Please deactivate the supplier instead, or delete all related records first.'
                )
                return redirect('supplier_statement', slug=request.business.slug, supplier_id=pk)
    
    context = {
        'supplier': supplier,
        'purchase_count': purchase_count,
        'payment_count': payment_count,
        'has_related_records': has_related_records,
    }
    return render(request, 'pos/supplier_confirm_delete.html', context)


# ==================== PURCHASE MANAGEMENT ====================

@business_required
def purchase_list(request, slug=None):
    """List all purchases"""
    purchases = Purchase.objects.filter(business=request.business).select_related('supplier').all()
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        purchases = purchases.filter(status=status_filter)
    
    context = {
        'purchases': purchases,
        'status_filter': status_filter,
    }
    return render(request, 'pos/purchase_list.html', context)


@business_required
@business_required
def purchase_create(request, slug=None):
    """Create a new purchase order"""
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        expected_delivery = request.POST.get('expected_delivery')
        notes = request.POST.get('notes', '')
        action = request.POST.get('action', 'draft')  # 'draft' or 'submit'

        # Get product items from POST data
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')
        unit_costs = request.POST.getlist('unit_cost[]')
        discounts = request.POST.getlist('discount[]')
        descriptions = request.POST.getlist('description[]')

        if not supplier_id:
            messages.error(request, 'Please select a supplier!')
            return redirect('purchase_create', slug=request.business.slug)

        if not product_ids or not any(product_ids):
            messages.error(request, 'Please add at least one product!')
            return redirect('purchase_create', slug=request.business.slug)

        # Create purchase as draft first
        supplier = get_object_or_404(Supplier, pk=supplier_id, business=request.business)
        purchase = Purchase.objects.create(
            business=request.business,
            supplier=supplier,
            expected_delivery=expected_delivery if expected_delivery else None,
            notes=notes,
            status='draft',
            created_by=request.user,
        )

        # Add purchase items and calculate totals
        subtotal = Decimal('0.00')
        total_discount = Decimal('0.00')
        items_added = 0
        for i, product_id in enumerate(product_ids):
            if product_id and quantities[i] and unit_costs[i]:
                product = get_object_or_404(Product, pk=product_id, business=request.business)
                quantity = int(quantities[i])
                unit_cost = Decimal(unit_costs[i])
                discount = Decimal(discounts[i]) if i < len(discounts) and discounts[i] else Decimal('0')
                description = descriptions[i] if i < len(descriptions) else ''

                if quantity <= 0 or unit_cost < 0:
                    purchase.delete()
                    messages.error(request, 'All quantities must be greater than zero and costs cannot be negative!')
                    return redirect('purchase_create', slug=request.business.slug)

                line_gross = quantity * unit_cost
                line_discount = line_gross * (discount / Decimal('100'))

                PurchaseItem.objects.create(
                    purchase=purchase,
                    product=product,
                    description=description,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    discount=discount,
                )

                subtotal += line_gross
                total_discount += line_discount
                items_added += 1

        if items_added == 0:
            purchase.delete()
            messages.error(request, 'Please add at least one valid item to the purchase!')
            return redirect('purchase_create', slug=request.business.slug)

        if subtotal <= 0:
            purchase.delete()
            messages.error(request, 'Purchase total must be greater than zero!')
            return redirect('purchase_create', slug=request.business.slug)

        # Update purchase totals
        purchase.subtotal = subtotal
        purchase.discount_amount = total_discount
        purchase.tax_amount = Decimal('0.00')
        purchase.total_amount = subtotal - total_discount + purchase.tax_amount

        # Handle action: submit for approval immediately?
        if action == 'submit':
            purchase.status = 'pending_approval'
            purchase.submitted_by = request.user
            purchase.submitted_at = timezone.now()

        purchase.save()

        if action == 'submit':
            messages.success(request, f'Purchase order {purchase.purchase_number} submitted for approval.')
        else:
            messages.success(request, f'Purchase order {purchase.purchase_number} saved as draft.')

        return redirect('purchase_detail', slug=request.business.slug, pk=purchase.pk)

    # GET request
    suppliers = Supplier.objects.filter(business=request.business, is_active=True)
    products = Product.objects.filter(business=request.business).select_related('category').all()

    prefill_product_id = request.GET.get('product')
    prefill_product = None
    if prefill_product_id:
        try:
            prefill_product = Product.objects.get(pk=prefill_product_id, business=request.business)
        except Product.DoesNotExist:
            pass

    context = {
        'suppliers': suppliers,
        'products': products,
        'prefill_product': prefill_product,
    }
    return render(request, 'pos/purchase_form.html', context)


@business_required
def purchase_detail(request, slug=None, pk=None):
    """View purchase order details"""
    purchase = get_object_or_404(Purchase, business=request.business, pk=pk)
    items = purchase.items.select_related('product').all()
    
    context = {
        'purchase': purchase,
        'items': items,
    }
    return render(request, 'pos/purchase_detail.html', context)


@business_required
def purchase_receive(request, slug=None, pk=None):
    """Enhanced purchase receiving with item-level details"""
    purchase = get_object_or_404(Purchase, business=request.business, pk=pk)

    if purchase.status == 'received':
        messages.warning(request, 'This purchase has already been received!')
        return redirect('purchase_detail', slug=request.business.slug, pk=pk)

    # Allow receiving for approved/sent/ordered/pending statuses
    receivable_statuses = ('approved', 'sent', 'ordered', 'pending', 'partially_received')
    if purchase.status not in receivable_statuses:
        messages.error(request, f'Cannot receive goods for a PO with status "{purchase.get_status_display()}". It must be approved first.')
        return redirect('purchase_detail', slug=request.business.slug, pk=pk)
    
    if request.method == 'POST':
        # Collect receiving data
        receiving_data = {'items': []}
        has_errors = False
        expiry_warnings = []
        
        from datetime import datetime, timedelta
        today = timezone.now().date()
        one_week_later = today + timedelta(days=7)
        
        for item in purchase.items.all():
            qty_received = int(request.POST.get(f'received_{item.id}', item.quantity))
            qty_damaged = int(request.POST.get(f'damaged_{item.id}', 0))
            notes = request.POST.get(f'notes_{item.id}', '').strip()
            expiry_date_str = request.POST.get(f'expiry_{item.id}', '').strip()
            batch_number = request.POST.get(f'batch_{item.id}', '').strip()
            
            # Validate quantities
            if qty_received < 0 or qty_damaged < 0:
                messages.error(request, f'{item.product.name}: Quantities cannot be negative!')
                has_errors = True
                break
            
            if qty_received + qty_damaged > item.quantity:
                messages.error(request, f'{item.product.name}: Received + Damaged ({qty_received + qty_damaged}) cannot exceed ordered quantity ({item.quantity})!')
                has_errors = True
                break
            
            # Validate expiry date
            expiry_date_obj = None
            if expiry_date_str:
                try:
                    expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                    
                    # Check if already expired
                    if expiry_date_obj < today:
                        days_overdue = (today - expiry_date_obj).days
                        expiry_warnings.append(
                            f'⚠️ {item.product.name}: Already expired {days_overdue} day{"s" if days_overdue != 1 else ""} ago!'
                        )
                    # Check if expiring within 7 days
                    elif expiry_date_obj <= one_week_later:
                        days_until = (expiry_date_obj - today).days
                        expiry_warnings.append(
                            f'⚠️ {item.product.name}: Expires in {days_until} day{"s" if days_until != 1 else ""}!'
                        )
                except ValueError:
                    messages.error(request, f'{item.product.name}: Invalid expiry date format!')
                    has_errors = True
                    break
            
            receiving_data['items'].append({
                'item_id': item.id,
                'quantity_received': qty_received,
                'quantity_damaged': qty_damaged,
                'notes': notes,
                'expiry_date': expiry_date_str if expiry_date_str else None,
                'batch_number': batch_number
            })
        
        if not has_errors:
            # Show expiry warnings if any
            if expiry_warnings:
                for warning in expiry_warnings:
                    messages.warning(request, warning)
            
            # Mark as received with details
            success = purchase.mark_as_received(receiving_data)
            
            if success:
                # Invalidate dashboard cache
                from django.core.cache import cache
                from .cache_utils import get_cache_key
                from datetime import datetime
                cache_key = get_cache_key('dashboard', request.business.id, datetime.now().date())
                cache.delete(cache_key)

                # Auto-create Goods Received Note document
                try:
                    grn_doc = GoodsReceivedNote.objects.create(
                        business=request.business,
                        purchase=purchase,
                        supplier=purchase.supplier,
                        received_date=timezone.now().date(),
                        received_by=request.user,
                        delivery_note_number=request.POST.get('delivery_note_number', ''),
                        vehicle_number=request.POST.get('vehicle_number', ''),
                        driver_name=request.POST.get('driver_name', ''),
                        notes=request.POST.get('receiving_notes', ''),
                    )
                    total_ordered = total_received = total_damaged = 0
                    total_value = Decimal('0.00')
                    for item in purchase.items.all():
                        GoodsReceivedNoteItem.objects.create(
                            grn=grn_doc,
                            product=item.product,
                            quantity_ordered=item.quantity,
                            quantity_received=item.quantity_received,
                            quantity_damaged=item.quantity_damaged,
                            unit_cost=item.unit_cost,
                            batch_number=item.batch_number,
                            expiry_date=item.expiry_date,
                            notes=item.receiving_notes,
                        )
                        total_ordered += item.quantity
                        total_received += item.quantity_received
                        total_damaged += item.quantity_damaged
                        total_value += Decimal(item.quantity_received) * item.unit_cost

                    has_discrepancy = total_damaged > 0 or total_received < total_ordered
                    grn_doc.total_ordered_qty = total_ordered
                    grn_doc.total_received_qty = total_received
                    grn_doc.total_damaged_qty = total_damaged
                    grn_doc.total_value = total_value
                    grn_doc.status = 'discrepancy' if has_discrepancy else 'confirmed'
                    grn_doc.save()
                except Exception:
                    pass  # GRN doc creation is non-blocking

                # Count discrepancies
                total_damaged = sum(d['quantity_damaged'] for d in receiving_data['items'])
                if total_damaged > 0:
                    messages.warning(request, f'Purchase {purchase.purchase_number} received with {total_damaged} damaged/missing items. Damage adjustments created.')
                else:
                    messages.success(request, f'Purchase {purchase.purchase_number} received successfully! Stock updated.')
                return redirect('purchase_detail', slug=request.business.slug, pk=pk)
            else:
                messages.error(request, 'Failed to receive purchase!')
    
    context = {
        'purchase': purchase,
    }
    return render(request, 'pos/purchase_receive.html', context)
    return render(request, 'pos/purchase_receive_confirm.html', context)


@business_required
def purchase_cancel(request, slug=None, pk=None):
    """Cancel a purchase order with proper validation and audit trail"""
    purchase = get_object_or_404(Purchase, business=request.business, pk=pk)
    
    if request.method == 'POST':
        # Check 1: Cannot cancel if received/closed
        if purchase.status in ('received', 'closed'):
            messages.error(
                request,
                'Cannot cancel a received purchase! Please create a Goods Returned Note (GRN) to return items.'
            )
            return redirect('purchase_detail', slug=request.business.slug, pk=pk)
        
        # Check 2: Cannot cancel if already cancelled
        if purchase.status == 'cancelled':
            messages.info(request, 'This purchase order is already cancelled.')
            return redirect('purchase_detail', slug=request.business.slug, pk=pk)
        
        # Check 3: Get cancellation reason (required)
        cancellation_reason = request.POST.get('cancellation_reason', '').strip()
        if not cancellation_reason:
            messages.error(request, 'Please provide a reason for cancellation.')
            return redirect('purchase_cancel', slug=request.business.slug, pk=pk)
        
        # Check 4: Check for related payments
        from .models import SupplierPaymentAllocation
        has_payments = SupplierPaymentAllocation.objects.filter(purchase=purchase).exists()
        if has_payments:
            messages.error(
                request,
                'This purchase order has payments allocated to it. Please handle payments before cancelling.'
            )
            return redirect('purchase_detail', slug=request.business.slug, pk=pk)
        
        # Perform cancellation
        old_status = purchase.status
        purchase.status = 'cancelled'
        purchase.cancellation_reason = cancellation_reason
        purchase.cancelled_by = request.user
        purchase.cancelled_at = timezone.now()
        purchase.save()
        
        # Send notification email to supplier if it was ordered
        if old_status == 'ordered' and purchase.supplier.email:
            try:
                from .email_service import EmailService
                EmailService.send_purchase_cancellation(purchase)
            except Exception as e:
                # Don't fail the cancellation if email fails
                messages.warning(request, 'Purchase cancelled but email notification to supplier failed.')
        
        messages.success(
            request, 
            f'Purchase Order {purchase.purchase_number} has been cancelled successfully.'
        )
        return redirect('purchase_detail', slug=request.business.slug, pk=pk)
    
    # GET request - show confirmation form
    from .models import SupplierPaymentAllocation
    has_payments = SupplierPaymentAllocation.objects.filter(purchase=purchase).exists()
    
    context = {
        'purchase': purchase,
        'has_payments': has_payments,
        'is_ordered': purchase.status == 'ordered',
        'can_cancel': purchase.status in ['pending', 'ordered', 'draft', 'approved', 'sent'] and not has_payments,
    }
    return render(request, 'pos/purchase_cancel_confirm.html', context)


# ==================== PURCHASE WORKFLOW ACTIONS ====================

@login_required
@business_required
@can_manage_purchases
def purchase_submit(request, slug=None, pk=None):
    """Submit a draft PO for approval"""
    purchase = get_object_or_404(Purchase, business=request.business, pk=pk)
    if purchase.status not in ('draft', 'pending'):
        messages.error(request, 'Only draft purchase orders can be submitted for approval.')
        return redirect('purchase_detail', slug=slug, pk=pk)
    purchase.status = 'pending_approval'
    purchase.submitted_by = request.user
    purchase.submitted_at = timezone.now()
    purchase.save()
    messages.success(request, f'{purchase.purchase_number} submitted for approval.')
    return redirect('purchase_detail', slug=slug, pk=pk)


@login_required
@business_required
@can_manage_purchases
def purchase_approve(request, slug=None, pk=None):
    """Approve a PO that is pending approval"""
    purchase = get_object_or_404(Purchase, business=request.business, pk=pk)
    if purchase.status != 'pending_approval':
        messages.error(request, 'Only purchase orders pending approval can be approved.')
        return redirect('purchase_detail', slug=slug, pk=pk)
    purchase.status = 'approved'
    purchase.approved_by = request.user
    purchase.approved_at = timezone.now()
    purchase.save()
    messages.success(request, f'{purchase.purchase_number} approved.')
    return redirect('purchase_detail', slug=slug, pk=pk)


@login_required
@business_required
@can_manage_purchases
def purchase_send_to_supplier(request, slug=None, pk=None):
    """Mark PO as sent to supplier and optionally email it"""
    purchase = get_object_or_404(Purchase, business=request.business, pk=pk)
    if purchase.status not in ('approved', 'ordered', 'pending'):
        messages.error(request, 'Purchase order must be approved before sending to supplier.')
        return redirect('purchase_detail', slug=slug, pk=pk)
    purchase.status = 'sent'
    purchase.sent_at = timezone.now()
    purchase.save()
    # Try to email supplier
    try:
        from .email_service import EmailService
        EmailService.send_purchase_order(purchase)
        messages.success(request, f'{purchase.purchase_number} marked as sent and emailed to supplier.')
    except Exception:
        messages.success(request, f'{purchase.purchase_number} marked as sent to supplier.')
    return redirect('purchase_detail', slug=slug, pk=pk)


@login_required
@business_required
@can_manage_purchases
def purchase_duplicate(request, slug=None, pk=None):
    """Duplicate a PO as a new draft"""
    original = get_object_or_404(Purchase, business=request.business, pk=pk)
    new_po = Purchase.objects.create(
        business=request.business,
        supplier=original.supplier,
        expected_delivery=original.expected_delivery,
        notes=f'Duplicated from {original.purchase_number}\n{original.notes}'.strip(),
        status='draft',
        created_by=request.user,
        subtotal=original.subtotal,
        discount_amount=original.discount_amount,
        tax_amount=original.tax_amount,
        total_amount=original.total_amount,
    )
    for item in original.items.all():
        PurchaseItem.objects.create(
            purchase=new_po,
            product=item.product,
            description=item.description,
            quantity=item.quantity,
            unit_cost=item.unit_cost,
            discount=item.discount,
        )
    messages.success(request, f'Duplicated as {new_po.purchase_number}.')
    return redirect('purchase_detail', slug=slug, pk=new_po.pk)


@login_required
@business_required
@can_manage_purchases
def purchase_close(request, slug=None, pk=None):
    """Close a fully received and paid PO"""
    purchase = get_object_or_404(Purchase, business=request.business, pk=pk)
    if purchase.status not in ('received', 'partially_received'):
        messages.error(request, 'Only received purchase orders can be closed.')
        return redirect('purchase_detail', slug=slug, pk=pk)

    remaining = purchase.remaining_balance()

    if request.method == 'GET':
        # Always show confirmation page
        return render(request, 'pos/purchase_close_confirm.html', {
            'purchase': purchase,
            'remaining_balance': remaining,
        })

    # POST — check for force_close flag
    force_close = request.POST.get('force_close') == '1'
    if remaining > Decimal('0.00') and not force_close:
        # Redirect back to confirmation page
        return render(request, 'pos/purchase_close_confirm.html', {
            'purchase': purchase,
            'remaining_balance': remaining,
        })

    purchase.status = 'closed'
    purchase.save()
    messages.success(request, f'{purchase.purchase_number} closed.')
    return redirect('purchase_detail', slug=slug, pk=pk)



# ==================== EXPIRY MANAGEMENT ====================

@business_required
def expiry_alert(request, slug=None):
    """View products that are expired or expiring soon"""
    from django.utils import timezone
    from datetime import timedelta
    
    today = timezone.now().date()
    
    # Get expired products for current business
    expired_products = Product.objects.filter(
        business=request.business,
        expiry_date__lt=today,
        stock_quantity__gt=0
    ).select_related('category').order_by('expiry_date')
    
    # Get expiring soon products for current business
    expiring_soon = []
    products_with_expiry = Product.objects.filter(
        business=request.business,
        expiry_date__gte=today,
        stock_quantity__gt=0
    ).select_related('category').order_by('expiry_date')
    
    for product in products_with_expiry:
        if product.is_expiring_soon():
            expiring_soon.append(product)
    
    # Diagnostic info - products with expiry dates
    total_products_with_expiry = Product.objects.filter(
        business=request.business,
        expiry_date__isnull=False
    ).count()
    
    products_with_expiry_in_stock = Product.objects.filter(
        business=request.business,
        expiry_date__isnull=False,
        stock_quantity__gt=0
    ).count()
    
    context = {
        'expired_products': expired_products,
        'expiring_soon_products': expiring_soon,
        'total_products_with_expiry': total_products_with_expiry,
        'products_with_expiry_in_stock': products_with_expiry_in_stock,
    }
    return render(request, 'pos/expiry_alert.html', context)



@business_required
def update_expiry(request, slug=None, pk=None):
    """Update product expiry date"""
    product = get_object_or_404(Product, business=request.business, pk=pk)
    
    if request.method == 'POST':
        expiry_date_str = request.POST.get('expiry_date')
        expiry_alert_days = request.POST.get('expiry_alert_days', 7)
        
        # Store old values for comparison
        old_expiry = product.expiry_date
        
        # Convert string to date object if provided
        from datetime import datetime as dt
        expiry_date_obj = None
        if expiry_date_str:
            try:
                expiry_date_obj = dt.strptime(expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Invalid date format')
                return redirect('update_expiry', slug=request.business.slug, pk=pk)
        
        # Update expiry information
        product.expiry_date = expiry_date_obj
        product.expiry_alert_days = int(expiry_alert_days)
        product.save()
        
        # Create a message based on what changed
        if old_expiry and expiry_date_obj:
            messages.success(request, f'Expiry date updated from {old_expiry.strftime("%d %b %Y")} to {expiry_date_obj.strftime("%d %b %Y")}')
        elif expiry_date_obj:
            messages.success(request, f'Expiry date set to {expiry_date_obj.strftime("%d %b %Y")}')
        else:
            messages.success(request, 'Expiry date removed')
        
        return redirect('stock_list', slug=request.business.slug)
    
    context = {
        'product': product,
    }
    return render(request, 'pos/update_expiry.html', context)



# ==================== AUTHENTICATION ====================

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required

def login_view(request):
    """User login"""
    # TEST MODE: Auto-login for testing (REMOVE IN PRODUCTION!)
    if getattr(settings, 'TEST_MODE', False):
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        
        # Get or create test user
        test_user, created = UserModel.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'test@example.com',
                'is_staff': True,
                'is_superuser': True
            }
        )
        
        # Auto-login
        auth_login(request, test_user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, '🧪 TEST MODE: Auto-logged in as testuser')
        return redirect('business_list')
    
    if request.user.is_authenticated:
        # Redirect superusers to platform admin dashboard
        if request.user.is_superuser:
            return redirect('platform_admin_dashboard')
        return redirect('business_list')
    
    if request.method == 'POST':
        username_or_email = request.POST.get('username')
        password = request.POST.get('password')
        
        # Try to authenticate with username first
        user = authenticate(request, username=username_or_email, password=password)
        
        # If authentication fails, try with email
        if user is None:
            try:
                # Check if input is an email and get the user
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None
        
        if user is not None:
            # Check if user has any active businesses
            from .models import Business
            user_businesses = Business.objects.filter(owner=user)
            
            if user_businesses.exists() and not user_businesses.filter(is_active=True).exists():
                # User has businesses but none are active (pending activation)
                messages.warning(
                    request, 
                    'Your account is pending activation. Our team will review and activate your account within 24 hours. '
                    'You will receive an email notification once activated.'
                )
                return render(request, 'pos/login.html')
            
            auth_login(request, user)
            
            # Log login activity
            ActivityLog.log_activity(
                user=user,
                action_type='login',
                description=f'User logged in: {user.username}',
                request=request
            )
            
            # Redirect superusers to platform admin dashboard
            if user.is_superuser:
                messages.success(request, f'Welcome back, {user.username}!')
                return redirect('platform_admin_dashboard')
            
            next_url = request.GET.get('next', 'business_list')
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username/email or password')
    
    return render(request, 'pos/login.html')


def logout_view(request):
    """User logout"""
    # Log logout activity before logging out
    if request.user.is_authenticated:
        ActivityLog.log_activity(
            user=request.user,
            action_type='logout',
            description=f'User logged out: {request.user.username}',
            request=request
        )
    
    auth_logout(request)
    messages.success(request, 'You have been logged out successfully')
    return redirect('login')


# ==================== PASSWORD RESET ====================

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.urls import reverse

def password_reset_request(request):
    """Request password reset via email"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        if email:
            users = User.objects.filter(email=email)
            
            if users.exists():
                for user in users:
                    # Generate token
                    token = default_token_generator.make_token(user)
                    uid = urlsafe_base64_encode(force_bytes(user.pk))
                    
                    # Build reset URL
                    reset_url = request.build_absolute_uri(
                        reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
                    )
                    
                    # Send email
                    subject = 'Password Reset Request - Marid POS'
                    message = f'''Hello {user.get_full_name() or user.username},

You requested a password reset for your POS account.

Click the link below to reset your password:
{reset_url}

This link will expire in 24 hours.

If you didn't request this, please ignore this email.

Best regards,
Marid POS Team'''
                    
                    try:
                        send_mail(
                            subject,
                            message,
                            settings.DEFAULT_FROM_EMAIL,
                            [user.email],
                            fail_silently=False,
                        )
                    except Exception as e:
                        messages.error(request, 'Error sending email. Please contact support.')
                        return render(request, 'pos/password_reset_request.html')
        
        # Always show success to prevent email enumeration
        messages.success(request, 'If an account exists with that email, you will receive password reset instructions.')
        return redirect('login')
    
    return render(request, 'pos/password_reset_request.html')


def password_reset_confirm(request, uidb64, token):
    """Confirm password reset with token"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            
            if password1 and password2:
                if password1 == password2:
                    if len(password1) >= 8:
                        user.set_password(password1)
                        user.save()
                        
                        # Log activity
                        ActivityLog.log_activity(
                            user=user,
                            action_type='update',
                            model_name='User',
                            object_id=user.id,
                            description='Password reset via email',
                            request=request
                        )
                        
                        messages.success(request, 'Password reset successful! You can now login with your new password.')
                        return redirect('login')
                    else:
                        messages.error(request, 'Password must be at least 8 characters long.')
                else:
                    messages.error(request, 'Passwords do not match.')
            else:
                messages.error(request, 'Please enter both password fields.')
        
        return render(request, 'pos/password_reset_confirm.html', {'validlink': True})
    else:
        return render(request, 'pos/password_reset_confirm.html', {'validlink': False})


# ==================== CASHIER REPORTS ====================

@login_required
@business_required
@manager_required
def cashier_report(request, slug=None):
    """View sales by cashier"""
    from django.contrib.auth.models import User
    from django.utils import timezone
    
    # Get date filter
    date_str = request.GET.get('date')
    if date_str:
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            filter_date = timezone.now().date()
    else:
        filter_date = timezone.now().date()
    
    # Get all users who have made sales for this business
    cashiers = User.objects.filter(
        sales__business=request.business,
        sales__isnull=False
    ).distinct()
    
    cashier_stats = []
    for cashier in cashiers:
        # Get sales for this cashier on the selected date for this business
        sales = Sale.objects.filter(
            business=request.business,
            cashier=cashier,
            date__date=filter_date
        )
        
        if sales.exists():
            stats = sales.aggregate(
                total_sales=Count('id'),
                total_revenue=Sum('total'),
                total_items=Sum('items__quantity')
            )
            
            cashier_stats.append({
                'cashier': cashier,
                'total_sales': stats['total_sales'] or 0,
                'total_revenue': stats['total_revenue'] or 0,
                'total_items': stats['total_items'] or 0,
                'sales': sales
            })
    
    # Overall totals for this business
    all_sales = Sale.objects.filter(
        business=request.business,
        date__date=filter_date
    )
    overall_stats = all_sales.aggregate(
        total_sales=Count('id'),
        total_revenue=Sum('total')
    )
    
    context = {
        'filter_date': filter_date,
        'cashier_stats': cashier_stats,
        'overall_stats': overall_stats,
    }
    return render(request, 'pos/cashier_report.html', context)



# ==================== USER MANAGEMENT ====================

from django.contrib.auth.models import User, Group
from .models import UserProfile, ActivityLog

@login_required
@business_required
@manager_required
def user_list(request, slug):
    """List all users in this business"""
    # Get users who are members of this business
    memberships = request.business.memberships.filter(is_active=True).select_related('user')
    user_ids = memberships.values_list('user_id', flat=True)
    users = User.objects.filter(id__in=user_ids).prefetch_related('groups', 'profile')
    
    # Add statistics for each user (filtered by business)
    for user in users:
        user.total_sales = Sale.objects.filter(cashier=user, business=request.business).count()
        user.total_revenue = Sale.objects.filter(cashier=user, business=request.business).aggregate(
            total=Sum('total')
        )['total'] or 0
        
        # Get user's role in this business
        membership = memberships.filter(user=user).first()
        user.business_role = membership.get_role_display() if membership else 'No Role'
    
    context = {
        'users': users,
    }
    return render(request, 'pos/user_list.html', context)


@login_required
@business_required
@manager_required
def roles_permissions(request, slug):
    """Display roles and permissions matrix"""
    from collections import defaultdict
    
    # Define all roles
    roles = [
        ('owner', 'Owner'),
        ('admin', 'Administrator'),
        ('manager', 'Manager'),
        ('stock_manager', 'Stock Manager'),
        ('cashier', 'Cashier'),
        ('sales', 'Sales Associate'),
        ('viewer', 'Viewer'),
    ]
    
    # Role descriptions
    role_descriptions = {
        'owner': 'Full control over the business including deletion and ownership transfer',
        'admin': 'Full administrative access to all features and settings',
        'manager': 'Can manage users, view reports, and configure business settings',
        'stock_manager': 'Manages inventory, products, suppliers, and stock levels',
        'cashier': 'Can make sales and process transactions at POS',
        'sales': 'Can make sales and view customer information',
        'viewer': 'Read-only access to view data and reports',
    }
    
    # Define permissions matrix
    permissions = [
        {
            'name': 'Make Sales',
            'description': 'Process sales transactions at POS',
            'roles': [True, True, True, False, True, True, False]
        },
        {
            'name': 'View Reports',
            'description': 'Access sales reports and analytics',
            'roles': [True, True, True, False, False, False, True]
        },
        {
            'name': 'Manage Products',
            'description': 'Create, edit, and delete products',
            'roles': [True, True, True, True, False, False, False]
        },
        {
            'name': 'Manage Stock',
            'description': 'Adjust stock levels and manage inventory',
            'roles': [True, True, True, True, False, False, False]
        },
        {
            'name': 'Manage Suppliers',
            'description': 'Add and manage supplier information',
            'roles': [True, True, True, True, False, False, False]
        },
        {
            'name': 'Manage Customers',
            'description': 'Add and edit customer information',
            'roles': [True, True, True, False, True, True, False]
        },
        {
            'name': 'Manage Users',
            'description': 'Add, edit, and remove business users',
            'roles': [True, True, True, False, False, False, False]
        },
        {
            'name': 'Business Settings',
            'description': 'Configure business settings and preferences',
            'roles': [True, True, True, False, False, False, False]
        },
        {
            'name': 'View Activity Log',
            'description': 'View system activity and audit logs',
            'roles': [True, True, True, False, False, False, False]
        },
        {
            'name': 'Delete Records',
            'description': 'Delete sales, products, and other records',
            'roles': [True, True, False, False, False, False, False]
        },
    ]
    
    # Get role counts
    role_counts = {}
    for role_key, role_name in roles:
        count = request.business.memberships.filter(role=role_key, is_active=True).count()
        role_counts[role_key] = count
    
    # Get users by role
    role_users = {}
    for role_key, role_name in roles:
        users = User.objects.filter(
            business_memberships__business=request.business,
            business_memberships__role=role_key,
            business_memberships__is_active=True
        ).distinct()
        role_users[role_key] = users
    
    # Define role permissions list
    role_permissions = {
        'owner': ['All Permissions'],
        'admin': ['All Permissions'],
        'manager': ['Make Sales', 'View Reports', 'Manage Products', 'Manage Stock', 'Manage Suppliers', 'Manage Customers', 'Manage Users', 'Business Settings', 'View Activity Log'],
        'stock_manager': ['Manage Products', 'Manage Stock', 'Manage Suppliers'],
        'cashier': ['Make Sales', 'Manage Customers'],
        'sales': ['Make Sales', 'Manage Customers'],
        'viewer': ['View Reports'],
    }
    
    context = {
        'roles': roles,
        'role_descriptions': role_descriptions,
        'permissions': permissions,
        'role_counts': role_counts,
        'role_users': role_users,
        'role_permissions': role_permissions,
    }
    return render(request, 'pos/roles_permissions.html', context)


@login_required
@manager_required
def user_create(request, slug):
    """Create a new user"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        
        # Profile fields
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')
        employee_id = request.POST.get('employee_id', '')
        date_of_birth = request.POST.get('date_of_birth', '')
        hire_date = request.POST.get('hire_date', '')
        is_active = request.POST.get('is_active') == 'on'
        notes = request.POST.get('notes', '')
        
        # Role
        role = request.POST.get('role')
        
        # Validation
        if not username or not password:
            messages.error(request, 'Username and password are required!')
            return redirect('user_create')
        
        if password != password_confirm:
            messages.error(request, 'Passwords do not match!')
            return redirect('user_create')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists!')
            return redirect('user_create')
        
        try:
            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active
            )
            
            # Assign role
            if role:
                group = Group.objects.get(name=role)
                user.groups.add(group)
            
            # Create profile
            UserProfile.objects.create(
                user=user,
                phone=phone,
                address=address,
                employee_id=employee_id if employee_id else None,
                date_of_birth=date_of_birth if date_of_birth else None,
                hire_date=hire_date if hire_date else None,
                is_active=is_active,
                notes=notes
            )
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='create',
                model_name='User',
                object_id=user.id,
                description=f'Created user: {username}',
                request=request
            )
            
            messages.success(request, f'User "{username}" created successfully!')
            return redirect('user_list')
            
        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
    
    # GET request
    groups = Group.objects.all()
    context = {
        'groups': groups,
    }
    return render(request, 'pos/user_form.html', context)


@login_required
@manager_required
def user_edit(request, slug, pk):
    """Edit existing user"""
    user = get_object_or_404(User, pk=pk)
    
    # Get or create profile
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    if request.method == 'POST':
        user.username = request.POST.get('username')
        user.email = request.POST.get('email', '')
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.is_active = request.POST.get('is_active') == 'on'
        
        # Update password if provided
        new_password = request.POST.get('new_password')
        if new_password:
            password_confirm = request.POST.get('password_confirm')
            if new_password == password_confirm:
                user.set_password(new_password)
            else:
                messages.error(request, 'Passwords do not match!')
                return redirect('user_edit', pk=pk)
        
        # Update profile
        profile.phone = request.POST.get('phone', '')
        profile.address = request.POST.get('address', '')
        profile.employee_id = request.POST.get('employee_id', '') or None
        date_of_birth = request.POST.get('date_of_birth', '')
        profile.date_of_birth = date_of_birth if date_of_birth else None
        hire_date = request.POST.get('hire_date', '')
        profile.hire_date = hire_date if hire_date else None
        profile.is_active = request.POST.get('is_active') == 'on'
        profile.notes = request.POST.get('notes', '')
        
        # Update role
        role = request.POST.get('role')
        user.groups.clear()
        if role:
            group = Group.objects.get(name=role)
            user.groups.add(group)
        
        try:
            user.save()
            profile.save()
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='update',
                model_name='User',
                object_id=user.id,
                description=f'Updated user: {user.username}',
                request=request
            )
            
            messages.success(request, f'User "{user.username}" updated successfully!')
            return redirect('user_list')
            
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
    
    # GET request
    groups = Group.objects.all()
    user_group = user.groups.first()
    
    context = {
        'edit_user': user,
        'profile': profile,
        'groups': groups,
        'user_group': user_group,
    }
    return render(request, 'pos/user_form.html', context)


@login_required
@manager_required
def user_delete(request, slug, pk):
    """Delete user"""
    user = get_object_or_404(User, pk=pk)
    
    # Prevent deleting yourself
    if user == request.user:
        messages.error(request, 'You cannot delete your own account!')
        return redirect('user_list')
    
    # Prevent deleting superuser
    if user.is_superuser:
        messages.error(request, 'Cannot delete superuser account!')
        return redirect('user_list')
    
    if request.method == 'POST':
        username = user.username
        user_id = user.id
        user.delete()
        
        # Log activity
        ActivityLog.log_activity(
            user=request.user,
            action_type='delete',
            model_name='User',
            object_id=user_id,
            description=f'Deleted user: {username}',
            request=request
        )
        
        messages.success(request, f'User "{username}" deleted successfully!')
        return redirect('user_list')
    
    context = {
        'delete_user': user,
    }
    return render(request, 'pos/user_confirm_delete.html', context)


@login_required
def user_profile(request, slug=None):
    """View and edit own profile"""
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.email = request.POST.get('email', '')
        
        profile.phone = request.POST.get('phone', '')
        profile.address = request.POST.get('address', '')
        date_of_birth = request.POST.get('date_of_birth', '')
        profile.date_of_birth = date_of_birth if date_of_birth else None
        
        # Change password if provided
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        
        if new_password:
            if not current_password:
                messages.error(request, 'Current password is required to change password!')
                if slug:
                    return redirect('user_profile', slug=slug)
                return redirect('business_list')
            
            if not user.check_password(current_password):
                messages.error(request, 'Current password is incorrect!')
                if slug:
                    return redirect('user_profile', slug=slug)
                return redirect('business_list')
            
            password_confirm = request.POST.get('password_confirm')
            if new_password != password_confirm:
                messages.error(request, 'New passwords do not match!')
                if slug:
                    return redirect('user_profile', slug=slug)
                return redirect('business_list')
            
            user.set_password(new_password)
            messages.success(request, 'Password changed successfully! Please login again.')
        
        try:
            user.save()
            profile.save()
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='update',
                model_name='UserProfile',
                object_id=profile.id,
                description='Updated own profile',
                request=request
            )
            
            if not new_password:
                messages.success(request, 'Profile updated successfully!')
            
            if slug:
                return redirect('user_profile', slug=slug)
            return redirect('business_list')
            
        except Exception as e:
            messages.error(request, f'Error updating profile: {str(e)}')
    
    # Calculate user statistics
    total_sales = Sale.objects.filter(cashier=user).count()
    total_revenue = Sale.objects.filter(cashier=user).aggregate(
        total=Sum('total')
    )['total'] or 0
    
    context = {
        'profile': profile,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
    }
    return render(request, 'pos/user_profile.html', context)


# ==================== BUSINESS SETTINGS ====================

from .models import BusinessSettings

@login_required
@login_required
@manager_required
def business_settings(request, slug=None):
    """View and edit business settings (legacy view)"""
    settings = BusinessSettings.get_settings(request.business)
    
    if request.method == 'POST':
        # Business Information
        settings.business_name = request.POST.get('business_name', 'My Retail Shop')
        settings.business_address = request.POST.get('business_address', '')
        settings.business_phone = request.POST.get('business_phone', '')
        settings.business_email = request.POST.get('business_email', '')
        settings.business_website = request.POST.get('business_website', '')
        settings.tax_id = request.POST.get('tax_id', '')
        
        # Logo upload
        if 'logo' in request.FILES:
            settings.logo = request.FILES['logo']
        
        # Remove logo if requested
        if request.POST.get('remove_logo') == 'true':
            settings.logo = None
        
        # Tax Settings
        settings.vat_rate = Decimal(request.POST.get('vat_rate', 16))
        settings.vat_enabled = request.POST.get('vat_enabled') == 'on'
        
        # Receipt Settings
        settings.receipt_header = request.POST.get('receipt_header', '')
        settings.receipt_footer = request.POST.get('receipt_footer', '')
        settings.show_logo_on_receipt = request.POST.get('show_logo_on_receipt') == 'on'
        
        # Thermal Receipt Settings
        settings.thermal_receipt_width = int(request.POST.get('thermal_receipt_width', 80))
        settings.thermal_font_size = request.POST.get('thermal_font_size', 'medium')
        settings.thermal_print_logo = request.POST.get('thermal_print_logo') == 'on'
        settings.thermal_print_barcode = request.POST.get('thermal_print_barcode') == 'on'
        settings.thermal_auto_cut = request.POST.get('thermal_auto_cut') == 'on'
        settings.thermal_copies = int(request.POST.get('thermal_copies', 1))
        settings.thermal_show_tax_breakdown = request.POST.get('thermal_show_tax_breakdown') == 'on'
        
        # Currency Settings
        settings.currency_symbol = request.POST.get('currency_symbol', 'KES')
        settings.currency_position = request.POST.get('currency_position', 'before')
        
        # Low Stock Settings
        settings.default_low_stock_threshold = int(request.POST.get('default_low_stock_threshold', 10))
        settings.enable_low_stock_alerts = request.POST.get('enable_low_stock_alerts') == 'on'
        
        # Expiry Settings
        settings.default_expiry_alert_days = int(request.POST.get('default_expiry_alert_days', 7))
        settings.enable_expiry_alerts = request.POST.get('enable_expiry_alerts') == 'on'
        
        # System Settings
        settings.allow_negative_stock = request.POST.get('allow_negative_stock') == 'on'
        settings.require_product_code = request.POST.get('require_product_code') == 'on'
        settings.auto_generate_product_code = request.POST.get('auto_generate_product_code') == 'on'
        
        # Theme Colors
        settings.theme_primary = request.POST.get('theme_primary', '#224195')
        settings.theme_dark = request.POST.get('theme_dark', '#1a1514')
        settings.theme_light = request.POST.get('theme_light', '#d5d3d4')
        settings.theme_accent = request.POST.get('theme_accent', '#cd8a4c')
        
        settings.updated_by = request.user
        
        try:
            settings.save()
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='settings',
                model_name='BusinessSettings',
                object_id=settings.id,
                description='Updated business settings',
                request=request
            )
            
            messages.success(request, 'Business settings updated successfully!')
            if slug:
                return redirect('business_settings', slug=slug)
            return redirect('business_list')
            
        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')
    
    context = {
        'settings': settings,
    }
    return render(request, 'pos/business_settings_enhanced.html', context)


# ==================== ACTIVITY LOG ====================

@login_required
@business_required
@manager_required
def activity_log(request, slug=None):
    """View activity logs for this business"""
    # Get users in this business
    memberships = request.business.memberships.filter(is_active=True).select_related('user')
    business_user_ids = memberships.values_list('user_id', flat=True)
    
    # Filter logs by users in this business
    logs = ActivityLog.objects.filter(user_id__in=business_user_ids).select_related('user')
    
    # Filter by user
    user_filter = request.GET.get('user')
    if user_filter:
        logs = logs.filter(user_id=user_filter)
    
    # Filter by action type
    action_filter = request.GET.get('action')
    if action_filter:
        logs = logs.filter(action_type=action_filter)
    
    # Filter by date
    date_filter = request.GET.get('date')
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            logs = logs.filter(timestamp__date=filter_date)
        except ValueError:
            pass
    
    # Get log statistics
    from datetime import timedelta
    total_logs = logs.count()
    logs_30_days = logs.filter(timestamp__gte=timezone.now() - timedelta(days=30)).count()
    logs_90_days = logs.filter(timestamp__gte=timezone.now() - timedelta(days=90)).count()
    logs_older_90 = logs.filter(timestamp__lt=timezone.now() - timedelta(days=90)).count()
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)  # Show 50 logs per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get users in this business for filter
    users = User.objects.filter(id__in=business_user_ids)
    
    context = {
        'page_obj': page_obj,
        'users': users,
        'user_filter': user_filter,
        'action_filter': action_filter,
        'date_filter': date_filter,
        'action_types': ActivityLog.ACTION_TYPES,
        'total_logs': total_logs,
        'logs_30_days': logs_30_days,
        'logs_90_days': logs_90_days,
        'logs_older_90': logs_older_90,
    }
    return render(request, 'pos/activity_log.html', context)


@login_required
@business_required
@manager_required
def clear_old_logs(request, slug=None):
    """Clear old activity logs"""
    if request.method == 'POST':
        days = int(request.POST.get('days', 90))
        
        from datetime import timedelta
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Get users in this business
        memberships = request.business.memberships.filter(is_active=True)
        business_user_ids = memberships.values_list('user_id', flat=True)
        
        # Delete logs for users in this business older than cutoff date
        deleted_count, _ = ActivityLog.objects.filter(
            user_id__in=business_user_ids,
            timestamp__lt=cutoff_date
        ).delete()
        
        # Log this action
        ActivityLog.log_activity(
            user=request.user,
            action_type='delete',
            description=f'Cleared {deleted_count} activity logs older than {days} days',
            model_name='ActivityLog',
            business=request.business
        )
        
        messages.success(request, f'Successfully deleted {deleted_count} log entries older than {days} days')
        return redirect('activity_log', slug=request.business.slug)
    
    # GET request - show confirmation page
    days = int(request.GET.get('days', 90))
    
    from datetime import timedelta
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Get users in this business
    memberships = request.business.memberships.filter(is_active=True)
    business_user_ids = memberships.values_list('user_id', flat=True)
    
    # Count logs that would be deleted
    logs_to_delete = ActivityLog.objects.filter(
        user_id__in=business_user_ids,
        timestamp__lt=cutoff_date
    )
    count = logs_to_delete.count()
    
    # Get breakdown by action type
    from django.db.models import Count
    breakdown = logs_to_delete.values('action_type').annotate(count=Count('id')).order_by('-count')
    
    context = {
        'days': days,
        'cutoff_date': cutoff_date,
        'count': count,
        'breakdown': breakdown,
    }
    return render(request, 'pos/clear_logs_confirm.html', context)



# ==================== CUSTOMER MANAGEMENT ====================

from .models import Customer

@business_required
def customer_list(request, slug=None):
    """List all customers"""
    all_customers = Customer.objects.filter(business=request.business)
    customers = all_customers
    
    # Get counts by type for statistics
    regular_count = all_customers.filter(customer_type='regular').count()
    vip_count = all_customers.filter(customer_type='vip').count()
    wholesale_count = all_customers.filter(customer_type='wholesale').count()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(name__icontains=search) | 
            Q(phone__icontains=search) | 
            Q(customer_code__icontains=search) |
            Q(email__icontains=search)
        )
    
    # Filter by type
    customer_type = request.GET.get('customer_type', '')
    if customer_type:
        customers = customers.filter(customer_type=customer_type)
    
    context = {
        'customers': customers,
        'search': search,
        'customer_type': customer_type,
        'total_count': all_customers.count(),
        'regular_count': regular_count,
        'vip_count': vip_count,
        'wholesale_count': wholesale_count,
    }
    return render(request, 'pos/customer_list.html', context)


@business_required
def customer_create(request, slug=None):
    """Create new customer"""
    if request.method == 'POST':
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        email = request.POST.get('email', '')
        address = request.POST.get('address', '')
        date_of_birth = request.POST.get('date_of_birth', '')
        customer_type = request.POST.get('customer_type', 'regular')
        is_active = request.POST.get('is_active') == 'on'
        notes = request.POST.get('notes', '')
        
        # Validate age if date of birth is provided
        if date_of_birth:
            try:
                from datetime import datetime, date
                dob = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
                today = date.today()
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                
                if age < 18:
                    messages.error(request, f'Customer must be at least 18 years old. Current age: {age} years.')
                    return render(request, 'pos/customer_form.html')
            except ValueError:
                messages.error(request, 'Invalid date of birth format.')
                return render(request, 'pos/customer_form.html')
        
        credit_limit = request.POST.get('credit_limit', '0') or '0'
        tags = request.POST.get('tags', '')

        if email:
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_email(email)
            except DjangoValidationError:
                messages.error(request, f'"{email}" is not a valid email address.')
                from datetime import date
                today = date.today()
                max_date = date(today.year - 18, today.month, today.day)
                return render(request, 'pos/customer_form.html', {'max_date': max_date.strftime('%Y-%m-%d')})

        try:
            customer = Customer.objects.create(
                business=request.business,
                name=name,
                phone=phone,
                email=email,
                address=address,
                date_of_birth=date_of_birth if date_of_birth else None,
                customer_type=customer_type,
                is_active=is_active,
                notes=notes,
                credit_limit=credit_limit,
                tags=tags,
            )
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='create',
                model_name='Customer',
                object_id=customer.id,
                description=f'Created customer: {customer.name} ({customer.customer_code})',
                request=request
            )
            
            messages.success(request, f'Customer "{customer.name}" created successfully! Customer Code: {customer.customer_code}')
            return redirect('customer_detail', slug=request.business.slug, pk=customer.pk)
            
        except Exception as e:
            messages.error(request, f'Error creating customer: {str(e)}')
    
    # Calculate max date (18 years ago from today)
    from datetime import date
    today = date.today()
    max_date = date(today.year - 18, today.month, today.day)
    
    context = {
        'max_date': max_date.strftime('%Y-%m-%d')
    }
    return render(request, 'pos/customer_form.html', context)


@business_required
def customer_edit(request, slug=None, pk=None):
    """Edit existing customer"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)
    
    if request.method == 'POST':
        customer.name = request.POST.get('name')
        customer.phone = request.POST.get('phone')
        customer.email = request.POST.get('email', '')
        customer.address = request.POST.get('address', '')
        date_of_birth = request.POST.get('date_of_birth', '')
        customer.customer_type = request.POST.get('customer_type', 'regular')
        customer.is_active = request.POST.get('is_active') == 'on'
        customer.notes = request.POST.get('notes', '')
        customer.credit_limit = request.POST.get('credit_limit', '0') or '0'
        customer.tags = request.POST.get('tags', '')
        
        # Validate age if date of birth is provided
        if date_of_birth:
            try:
                from datetime import datetime, date
                dob = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
                today = date.today()
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                
                if age < 18:
                    messages.error(request, f'Customer must be at least 18 years old. Current age: {age} years.')
                    # Calculate max date for template
                    max_date = date(today.year - 18, today.month, today.day)
                    context = {
                        'customer': customer,
                        'max_date': max_date.strftime('%Y-%m-%d')
                    }
                    return render(request, 'pos/customer_form.html', context)
            except ValueError:
                messages.error(request, 'Invalid date of birth format.')
                # Calculate max date for template
                from datetime import date
                today = date.today()
                max_date = date(today.year - 18, today.month, today.day)
                context = {
                    'customer': customer,
                    'max_date': max_date.strftime('%Y-%m-%d')
                }
                return render(request, 'pos/customer_form.html', context)
        
        customer.date_of_birth = date_of_birth if date_of_birth else None
        
        if customer.email:
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_email(customer.email)
            except DjangoValidationError:
                messages.error(request, f'"{customer.email}" is not a valid email address.')
                from datetime import date
                today = date.today()
                max_date = date(today.year - 18, today.month, today.day)
                return render(request, 'pos/customer_form.html', {'customer': customer, 'max_date': max_date.strftime('%Y-%m-%d')})

        try:
            customer.save()
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='update',
                model_name='Customer',
                object_id=customer.id,
                description=f'Updated customer: {customer.name} ({customer.customer_code})',
                request=request
            )
            
            messages.success(request, f'Customer "{customer.name}" updated successfully!')
            return redirect('customer_detail', slug=request.business.slug, pk=customer.pk)
            
        except Exception as e:
            messages.error(request, f'Error updating customer: {str(e)}')
    
    # Calculate max date (18 years ago from today)
    from datetime import date
    today = date.today()
    max_date = date(today.year - 18, today.month, today.day)
    
    context = {
        'customer': customer,
        'max_date': max_date.strftime('%Y-%m-%d')
    }
    return render(request, 'pos/customer_form.html', context)


@business_required
def customer_delete(request, slug=None, pk=None):
    """Delete customer"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)
    
    # Check if customer has related records
    sales_count = customer.purchases.count()
    loyalty_transactions_count = customer.loyalty_transactions.count() if hasattr(customer, 'loyalty_transactions') else 0
    has_related_records = sales_count > 0 or loyalty_transactions_count > 0
    
    if request.method == 'POST':
        action = request.POST.get('action', 'delete')
        
        if action == 'deactivate':
            # Deactivate instead of delete
            customer.is_active = False
            customer.save()
            messages.success(request, f'Customer "{customer.name}" has been deactivated.')
            return redirect('customer_list', slug=request.business.slug)
        
        elif action == 'delete':
            try:
                name = customer.name
                customer.delete()
                messages.success(request, f'Customer "{name}" deleted successfully!')
                return redirect('customer_list', slug=request.business.slug)
            except models.ProtectedError as e:
                # Handle protected foreign key error
                messages.error(
                    request, 
                    f'Cannot delete customer "{customer.name}" because they have purchase history. '
                    f'Please deactivate the customer instead.'
                )
                return redirect('customer_detail', slug=request.business.slug, pk=pk)
    
    context = {
        'customer': customer,
        'sales_count': sales_count,
        'loyalty_transactions_count': loyalty_transactions_count,
        'has_related_records': has_related_records,
    }
    return render(request, 'pos/customer_confirm_delete.html', context)


# ==================== LOYALTY PROGRAM ====================

@login_required
@business_required
def loyalty_dashboard(request, slug=None, pk=None):
    """Customer loyalty dashboard showing points, tier, and transaction history"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)
    
    # Get loyalty transactions
    transactions = customer.loyalty_transactions.all().order_by('-created_at')[:50]
    
    # Get tier info
    tier_info = customer.get_tier_display_info()
    
    # Calculate progress to next tier
    progress_percentage = 0
    points_to_next = 0
    if tier_info['next']:
        points_to_next = tier_info['next'] - customer.lifetime_points
        progress_percentage = (customer.lifetime_points / tier_info['next']) * 100
    
    # Get recent purchases with loyalty transactions prefetched
    recent_purchases = Sale.objects.filter(
        business=request.business, 
        customer=customer
    ).prefetch_related('loyalty_transactions').order_by('-date')[:10]
    
    context = {
        'customer': customer,
        'transactions': transactions,
        'tier_info': tier_info,
        'progress_percentage': progress_percentage,
        'points_to_next': points_to_next,
        'recent_purchases': recent_purchases,
        'points_value': customer.get_points_value(),
    }
    return render(request, 'pos/loyalty_dashboard.html', context)


@login_required
@business_required
def loyalty_transactions(request, slug=None, pk=None):
    """View all loyalty transactions for a customer"""
    from .models import LoyaltyTransaction
    
    customer = get_object_or_404(Customer, business=request.business, pk=pk)
    transactions = customer.loyalty_transactions.all().order_by('-created_at')
    
    # Filter by transaction type if specified
    transaction_type = request.GET.get('type')
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    context = {
        'customer': customer,
        'transactions': transactions,
        'transaction_type': transaction_type,
    }
    return render(request, 'pos/loyalty_transactions.html', context)


@login_required
@business_required
def loyalty_redeem(request, slug=None, pk=None):
    """Redeem loyalty points for discount"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)
    
    if request.method == 'POST':
        points_to_redeem = int(request.POST.get('points', 0))
        
        if points_to_redeem <= 0:
            messages.error(request, 'Please enter a valid number of points.')
        elif points_to_redeem > customer.loyalty_points:
            messages.error(request, f'Customer only has {customer.loyalty_points} points available.')
        else:
            # Redeem points
            discount_amount = customer.redeem_points(
                points_to_redeem, 
                description="Manual Points Redemption"
            )
            
            messages.success(
                request, 
                f'Successfully redeemed {points_to_redeem} points for KES {discount_amount} discount!'
            )
            return redirect('loyalty_dashboard', slug=request.business.slug, pk=pk)
    
    context = {
        'customer': customer,
    }
    return render(request, 'pos/loyalty_redeem.html', context)


@login_required
@business_required
def loyalty_adjust(request, slug=None, pk=None):
    """Manually adjust customer loyalty points (admin only)"""
    from .models import LoyaltyTransaction
    
    customer = get_object_or_404(Customer, business=request.business, pk=pk)
    
    if request.method == 'POST':
        adjustment_type = request.POST.get('adjustment_type')
        points = int(request.POST.get('points', 0))
        reason = request.POST.get('reason', '')
        
        if points == 0:
            messages.error(request, 'Please enter a valid number of points.')
        else:
            # Apply adjustment
            if adjustment_type == 'add':
                customer.loyalty_points += points
                customer.lifetime_points += points
                transaction_points = points
            else:  # subtract
                if points > customer.loyalty_points:
                    messages.error(request, f'Cannot subtract {points} points. Customer only has {customer.loyalty_points} points.')
                    return redirect('loyalty_adjust', slug=request.business.slug, pk=pk)
                customer.loyalty_points -= points
                transaction_points = -points
            
            customer.save()
            
            # Create transaction record
            LoyaltyTransaction.objects.create(
                customer=customer,
                transaction_type='adjust',
                points=transaction_points,
                amount=Decimal('0.00'),
                description=reason or f'Manual adjustment by {request.user.username}',
                created_by=request.user
            )
            
            messages.success(
                request, 
                f'Successfully {"added" if adjustment_type == "add" else "subtracted"} {points} points!'
            )
            return redirect('loyalty_dashboard', slug=request.business.slug, pk=pk)
    
    context = {
        'customer': customer,
    }
    return render(request, 'pos/loyalty_adjust.html', context)


@login_required
@business_required
def loyalty_rewards_list(request, slug=None):
    """List all available loyalty rewards"""
    from .models import LoyaltyReward
    
    business = request.business
    rewards = LoyaltyReward.objects.filter(business=business, is_active=True).order_by('points_required')
    
    context = {
        'rewards': rewards,
    }
    return render(request, 'pos/loyalty_rewards_list.html', context)


@login_required
@business_required
def loyalty_reward_create(request, slug=None):
    """Create a new loyalty reward"""
    from .models import LoyaltyReward
    
    business = request.business
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        points_required = int(request.POST.get('points_required'))
        reward_type = request.POST.get('reward_type')
        discount_value = Decimal(request.POST.get('discount_value', 0))
        
        try:
            LoyaltyReward.objects.create(
                business=business,
                name=name,
                description=description,
                points_required=points_required,
                reward_type=reward_type,
                discount_value=discount_value,
                is_active=True
            )
            messages.success(request, 'Loyalty reward created successfully!')
            return redirect('loyalty_rewards_list', slug=business.slug)
        except Exception as e:
            messages.error(request, f'Error creating reward: {str(e)}')
    
    return render(request, 'pos/loyalty_reward_form.html')


@login_required
@business_required
def loyalty_reward_edit(request, slug=None, pk=None):
    """Edit an existing loyalty reward"""
    from .models import LoyaltyReward
    
    business = request.business
    reward = get_object_or_404(LoyaltyReward, pk=pk, business=business)
    
    if request.method == 'POST':
        reward.name = request.POST.get('name')
        reward.description = request.POST.get('description')
        reward.points_required = int(request.POST.get('points_required'))
        reward.reward_type = request.POST.get('reward_type')
        reward.discount_value = Decimal(request.POST.get('discount_value', 0))
        reward.is_active = request.POST.get('is_active') == 'on'
        
        try:
            reward.save()
            messages.success(request, 'Loyalty reward updated successfully!')
            return redirect('loyalty_rewards_list', slug=business.slug)
        except Exception as e:
            messages.error(request, f'Error updating reward: {str(e)}')
    
    context = {
        'reward': reward,
    }
    return render(request, 'pos/loyalty_reward_form.html', context)


# ==================== WRITE-OFF REPORT ====================

@business_required
def writeoff_report(request, slug=None):
    """Comprehensive write-off report for damaged and expired goods"""
    from django.utils import timezone
    
    # Get date range filters
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    # Default to last 30 days
    if not end_date_str:
        end_date = timezone.now().date()
    else:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = timezone.now().date()
    
    if not start_date_str:
        start_date = end_date - timedelta(days=30)
    else:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = end_date - timedelta(days=30)
    
    # Get all damage/loss adjustments for current business
    writeoffs = StockAdjustment.objects.filter(
        business=request.business,
        adjustment_type='damage',
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).select_related('product', 'product__category').order_by('-created_at')
    
    # Calculate statistics
    total_items_written_off = abs(writeoffs.aggregate(
        total=Sum('quantity_change')
    )['total'] or 0)
    
    # Calculate total value (quantity * unit price)
    total_value = Decimal('0.00')
    for adjustment in writeoffs:
        quantity = abs(adjustment.quantity_change)
        total_value += quantity * adjustment.product.unit_price
    
    # Group by product
    product_summary = {}
    for adjustment in writeoffs:
        product_id = adjustment.product.id
        if product_id not in product_summary:
            product_summary[product_id] = {
                'product': adjustment.product,
                'total_quantity': 0,
                'total_value': Decimal('0.00'),
                'adjustments': []
            }
        
        quantity = abs(adjustment.quantity_change)
        value = quantity * adjustment.product.unit_price
        
        product_summary[product_id]['total_quantity'] += quantity
        product_summary[product_id]['total_value'] += value
        product_summary[product_id]['adjustments'].append(adjustment)
    
    # Convert to list and sort by value
    product_summary_list = sorted(
        product_summary.values(),
        key=lambda x: x['total_value'],
        reverse=True
    )
    
    # Get currently expired products (still in stock)
    today = timezone.now().date()
    expired_in_stock = Product.objects.filter(
        expiry_date__lt=today,
        stock_quantity__gt=0
    ).select_related('category')
    
    # Calculate value of expired stock
    expired_stock_value = Decimal('0.00')
    expired_stock_quantity = 0
    for product in expired_in_stock:
        expired_stock_value += product.stock_quantity * product.unit_price
        expired_stock_quantity += product.stock_quantity
    
    # Category breakdown
    category_summary = {}
    for adjustment in writeoffs:
        category = adjustment.product.category
        category_name = category.name if category else 'Uncategorized'
        
        if category_name not in category_summary:
            category_summary[category_name] = {
                'quantity': 0,
                'value': Decimal('0.00'),
                'count': 0
            }
        
        quantity = abs(adjustment.quantity_change)
        value = quantity * adjustment.product.unit_price
        
        category_summary[category_name]['quantity'] += quantity
        category_summary[category_name]['value'] += value
        category_summary[category_name]['count'] += 1
    
    # Convert to list and sort by value
    category_summary_list = sorted(
        category_summary.items(),
        key=lambda x: x[1]['value'],
        reverse=True
    )
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'writeoffs': writeoffs,
        'total_items_written_off': total_items_written_off,
        'total_value': total_value,
        'product_summary': product_summary_list,
        'category_summary': category_summary_list,
        'expired_in_stock': expired_in_stock,
        'expired_stock_value': expired_stock_value,
        'expired_stock_quantity': expired_stock_quantity,
        'writeoff_count': writeoffs.count(),
    }
    return render(request, 'pos/writeoff_report.html', context)


# ==================== SUPPLIER PAYMENT VIEWS ====================

@login_required
@can_manage_purchases
def supplier_payments(request, slug, supplier_id):
    """List all payments for a supplier"""
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    
    # Get date filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    payments = supplier.payments.all()
    
    if start_date:
        payments = payments.filter(payment_date__gte=start_date)
    if end_date:
        payments = payments.filter(payment_date__lte=end_date)
    
    total_payments = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    context = {
        'supplier': supplier,
        'payments': payments,
        'total_payments': total_payments,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'pos/supplier_payments.html', context)


@login_required
@can_manage_purchases
def create_payment(request, slug, supplier_id):
    """Create a new supplier payment"""
    from .supplier_services import SupplierPaymentService
    from .models import PaymentMethod
    from datetime import datetime
    
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    
    # Check if supplier has any received purchases
    has_received_purchases = supplier.purchases.filter(status='received').exists()
    
    if not has_received_purchases:
        messages.error(
            request, 
            f'Cannot create payment for {supplier.name}. '
            'You must receive at least one purchase order before making payments. '
            'This prevents advance payments and accounting errors.'
        )
        return redirect('supplier_payments', slug=request.business.slug, supplier_id=supplier.id)
    
    # Check if there's an outstanding balance to pay
    outstanding = supplier.outstanding_balance()
    if outstanding <= Decimal('0.00'):
        if outstanding < Decimal('0.00'):
            messages.warning(
                request,
                f'Cannot create payment for {supplier.name}. '
                f'You have a credit balance of KES {abs(outstanding):,.2f}. '
                'The supplier owes you money, not the other way around.'
            )
        else:
            messages.warning(
                request,
                f'Cannot create payment for {supplier.name}. '
                'The account is fully settled with zero outstanding balance.'
            )
        return redirect('supplier_payments', slug=request.business.slug, supplier_id=supplier.id)
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount'))
            payment_date_str = request.POST.get('payment_date')
            payment_method_id = request.POST.get('payment_method')
            reference_number = request.POST.get('reference_number', '')
            notes = request.POST.get('notes', '')
            
            # Validate payment amount doesn't exceed outstanding balance
            outstanding = supplier.outstanding_balance()
            if amount > outstanding:
                messages.error(
                    request,
                    f'Payment amount (KES {amount:,.2f}) exceeds outstanding balance (KES {outstanding:,.2f}). '
                    'You cannot overpay a supplier.'
                )
                # Re-render form with error
                unpaid_purchases = Purchase.objects.filter(
                    supplier=supplier,
                    status__in=('received', 'partially_received')
                ).annotate(
                    allocated=Coalesce(Sum('payment_allocations__amount'), Decimal('0.00'))
                ).filter(
                    allocated__lt=F('total_amount')
                ).order_by('date')
                
                payment_methods = PaymentMethod.objects.filter(business=request.business, is_active=True)
                
                context = {
                    'supplier': supplier,
                    'unpaid_purchases': unpaid_purchases,
                    'payment_methods': payment_methods,
                }
                return render(request, 'pos/payment_form.html', context)
            
            # Parse date string to date object
            if payment_date_str:
                payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
            else:
                payment_date = timezone.now().date()
            
            payment_method = PaymentMethod.objects.get(id=payment_method_id)
            
            # Build manual allocations if provided
            allocations = None
            allocation_keys = [k for k in request.POST if k.startswith('alloc_amount_')]
            if allocation_keys:
                allocations = []
                for key in allocation_keys:
                    purchase_id = key.replace('alloc_amount_', '')
                    alloc_amount_str = request.POST.get(key, '').strip()
                    if not alloc_amount_str:
                        continue
                    alloc_amount = Decimal(alloc_amount_str)
                    if alloc_amount <= Decimal('0.00'):
                        continue
                    purchase = Purchase.objects.get(id=purchase_id, supplier=supplier)
                    allocations.append({'purchase': purchase, 'amount': alloc_amount})
                if not allocations:
                    allocations = None  # fall back to FIFO if nothing selected
            
            # Create payment using service
            payment = SupplierPaymentService.create_payment(
                supplier=supplier,
                amount=amount,
                payment_date=payment_date,
                payment_method=payment_method,
                reference_number=reference_number,
                notes=notes,
                created_by=request.user,
                allocations=allocations
            )
            
            messages.success(request, f'Payment {payment.payment_number} created successfully!')
            return redirect('supplier_payments', slug=request.business.slug, supplier_id=supplier.id)
            
        except Exception as e:
            messages.error(request, f'Error creating payment: {str(e)}')
    
    # Get unpaid purchases for this supplier (received or partially received, with remaining balance)
    unpaid_purchases = Purchase.objects.filter(
        supplier=supplier,
        status__in=('received', 'partially_received')
    ).annotate(
        allocated=Coalesce(Sum('payment_allocations__amount'), Decimal('0.00'))
    ).filter(
        allocated__lt=F('total_amount')
    ).order_by('date')
    
    payment_methods = PaymentMethod.objects.filter(business=request.business, is_active=True)
    
    context = {
        'supplier': supplier,
        'unpaid_purchases': unpaid_purchases,
        'payment_methods': payment_methods,
    }
    return render(request, 'pos/payment_form.html', context)


@login_required
@login_required
@can_manage_purchases
def payment_detail(request, slug, payment_id):
    """View payment details"""
    from .models import SupplierPayment
    
    try:
        # Get payment and verify it belongs to current business
        payment = get_object_or_404(
            SupplierPayment, 
            pk=payment_id,
            business=request.business
        )
        allocations = payment.allocations.select_related('purchase').all()
        
        context = {
            'payment': payment,
            'allocations': allocations,
        }
        return render(request, 'pos/payment_detail_simple.html', context)
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in payment_detail: {str(e)}")
        logger.error(traceback.format_exc())
        messages.error(request, f"Error loading payment details: {str(e)}")
        return redirect('dashboard', slug=request.business.slug)


@login_required
@can_manage_purchases
def delete_payment(request, slug, payment_id):
    """Delete a supplier payment"""
    from .models import SupplierPayment
    
    payment = get_object_or_404(SupplierPayment, pk=payment_id)
    supplier_id = payment.supplier.id
    
    if request.method == 'POST':
        payment_number = payment.payment_number
        payment.delete()
        
        # Log deletion
        ActivityLog.log_activity(
            user=request.user,
            action_type='delete',
            description=f'Deleted supplier payment {payment_number}',
            model_name='SupplierPayment'
        )
        
        messages.success(request, 'Payment deleted successfully!')
        return redirect('supplier_payments', slug=request.business.slug, supplier_id=supplier_id)
    
    return render(request, 'pos/payment_confirm_delete.html', {'payment': payment})


@login_required
@can_manage_purchases
def supplier_statement(request, slug, supplier_id):
    """Generate supplier statement - Always fresh, no caching"""
    from django.views.decorators.cache import never_cache
    from .supplier_services import SupplierStatementService
    
    supplier = get_object_or_404(Supplier, pk=supplier_id, business=request.business)
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Generate fresh statement (no caching)
    statement = SupplierStatementService.generate_statement(
        supplier=supplier,
        start_date=start_date,
        end_date=end_date
    )
    
    context = statement
    response = render(request, 'pos/supplier_statement.html', context)
    
    # Add cache-control headers to prevent browser caching
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response


@login_required
@can_manage_purchases
def supplier_balances(request):
    """List all suppliers with their outstanding balances"""
    suppliers = Supplier.objects.filter(is_active=True)
    
    # Add outstanding balance to each supplier
    supplier_data = []
    total_outstanding = Decimal('0.00')
    
    for supplier in suppliers:
        balance = supplier.outstanding_balance()
        if balance > Decimal('0.00') or request.GET.get('show_all'):
            supplier_data.append({
                'supplier': supplier,
                'balance': balance
            })
            total_outstanding += balance
    
    # Sort by balance or name
    sort_by = request.GET.get('sort', 'balance')
    if sort_by == 'name':
        supplier_data.sort(key=lambda x: x['supplier'].name)
    else:
        supplier_data.sort(key=lambda x: x['balance'], reverse=True)
    
    context = {
        'supplier_data': supplier_data,
        'total_outstanding': total_outstanding,
        'sort_by': sort_by,
    }
    return render(request, 'pos/supplier_balances.html', context)


@login_required
@manager_required
def aging_analysis(request):
    """Generate aging analysis report"""
    from .supplier_services import SupplierStatementService
    
    as_of_date = request.GET.get('as_of_date')
    if as_of_date:
        as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
    
    aging_data = SupplierStatementService.generate_aging_analysis(as_of_date=as_of_date)
    
    # Calculate totals
    totals = {
        'current': sum(d['current'] for d in aging_data),
        '30_days': sum(d['30_days'] for d in aging_data),
        '60_days': sum(d['60_days'] for d in aging_data),
        '90_plus': sum(d['90_plus'] for d in aging_data),
        'total': sum(d['total'] for d in aging_data),
    }
    
    context = {
        'aging_data': aging_data,
        'totals': totals,
        'as_of_date': as_of_date or datetime.now().date(),
    }
    return render(request, 'pos/aging_analysis.html', context)


# ==================== Z-REPORT (END OF DAY) ====================
# Note: Z-Report system has been replaced with new production-ready version
# See: posd/pos/zreport_views.py and posd/pos/zreport_service.py
# Old URLs redirect to new system for backward compatibility

@business_required
def z_report_redirect(request, slug=None):
    """Redirect old Z-Report URLs to new system"""
    messages.info(request, "Z-Report system has been upgraded. You've been redirected to the new system.")
    return redirect('zreport_session_status', slug=request.business.slug)










@business_required
def analytics_api(request, slug=None):
    """API endpoint for analytics data"""
    from django.db.models import Sum, Count, Avg
    
    try:
        period = request.GET.get('period', 'month')
        today = datetime.now().date()
        
        # Calculate date range based on period
        if period == 'today':
            start_date = today
            end_date = today
        elif period == 'yesterday':
            start_date = today - timedelta(days=1)
            end_date = start_date
        elif period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = today
        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today
        elif period == 'custom':
            start_date = datetime.strptime(request.GET.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.GET.get('end_date'), '%Y-%m-%d').date()
        else:
            start_date = today.replace(day=1)
            end_date = today
        
        # Get sales in date range for current business
        sales = Sale.objects.filter(
            business=request.business,
            date__date__gte=start_date,
            date__date__lte=end_date
        )
        
        # Calculate summary metrics
        total_sales = sales.count()
        total_revenue = sales.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        average_sale = sales.aggregate(avg=Avg('total'))['avg'] or Decimal('0.00')
        total_discounts = sales.aggregate(total=Sum('discount_amount'))['total'] or Decimal('0.00')
        
        # Payment methods breakdown
        payment_methods = list(SalePayment.objects.filter(
            sale__business=request.business,
            sale__date__date__gte=start_date,
            sale__date__date__lte=end_date
        ).values('payment_method__name').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total'))
        
        payment_methods_data = []
        for pm in payment_methods:
            payment_methods_data.append({
                'name': pm.get('payment_method__name') or 'Unknown',
                'total': float(pm.get('total') or 0),
                'count': pm.get('count') or 0
            })
        
        # Sales trend (daily breakdown) - limit to 31 days max
        sales_trend = []
        current_date = start_date
        days_count = 0
        max_days = 31
        
        while current_date <= end_date and days_count < max_days:
            day_sales = sales.filter(date__date=current_date).aggregate(
                total=Sum('total')
            )['total'] or Decimal('0.00')
            
            sales_trend.append({
                'label': current_date.strftime('%b %d'),
                'total': float(day_sales)
            })
            current_date += timedelta(days=1)
            days_count += 1
        
        # Top products
        top_products = list(SaleItem.objects.filter(
            sale__business=request.business,
            sale__date__date__gte=start_date,
            sale__date__date__lte=end_date
        ).values('product__name').annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price')
        ).order_by('-revenue')[:10])
        
        top_products_data = []
        for product in top_products:
            top_products_data.append({
                'name': product.get('product__name') or 'Unknown',
                'quantity': product.get('quantity') or 0,
                'revenue': float(product.get('revenue') or 0)
            })
        
        # Sales by cashier
        cashier_sales = list(sales.values(
            'cashier__username',
            'cashier__first_name',
            'cashier__last_name'
        ).annotate(
            total=Sum('total'),
            count=Count('id')
        ).order_by('-total'))
        
        cashier_sales_data = []
        for cashier in cashier_sales:
            first_name = cashier.get('cashier__first_name') or ''
            last_name = cashier.get('cashier__last_name') or ''
            name = f"{first_name} {last_name}".strip()
            if not name:
                name = cashier.get('cashier__username') or 'Unknown'
            
            total = float(cashier.get('total') or 0)
            count = cashier.get('count') or 0
            average = total / count if count > 0 else 0
            
            cashier_sales_data.append({
                'name': name,
                'total': total,
                'count': count,
                'average': average
            })
        
        response_data = {
            'total_sales': total_sales,
            'total_revenue': float(total_revenue),
            'average_sale': float(average_sale),
            'total_discounts': float(total_discounts),
            'payment_methods': payment_methods_data,
            'sales_trend': sales_trend,
            'top_products': top_products_data,
            'cashier_sales': cashier_sales_data,
            'period': period,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        error_trace = traceback.format_exc()
        logger.error(f"Analytics API Error: {error_trace}")
        return JsonResponse({
            'error': str(e),
            'traceback': error_trace
        }, status=500)



@business_required
def analytics_export_pdf(request, slug=None):
    """Export analytics as PDF"""
    from django.db.models import Sum, Count
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    
    try:
        period = request.GET.get('period', 'month')
        today = datetime.now().date()
        
        # Calculate date range based on period
        if period == 'today':
            start_date = today
            end_date = today
            period_label = 'Today'
        elif period == 'yesterday':
            start_date = today - timedelta(days=1)
            end_date = start_date
            period_label = 'Yesterday'
        elif period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
            period_label = 'This Week'
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = today
            period_label = 'This Month'
        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today
            period_label = 'This Year'
        elif period == 'custom':
            start_date = datetime.strptime(request.GET.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.GET.get('end_date'), '%Y-%m-%d').date()
            period_label = f'{start_date.strftime("%b %d, %Y")} - {end_date.strftime("%b %d, %Y")}'
        else:
            start_date = today.replace(day=1)
            end_date = today
            period_label = 'This Month'
        
        # Get sales data for current business
        sales = Sale.objects.filter(
            business=request.business,
            date__date__gte=start_date,
            date__date__lte=end_date
        )
        
        # Calculate metrics
        total_sales = sales.count()
        total_revenue = sales.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        total_discounts = sales.aggregate(total=Sum('discount_amount'))['total'] or Decimal('0.00')
        total_vat = sales.aggregate(total=Sum('vat_amount'))['total'] or Decimal('0.00')
        
        # Payment methods
        payment_methods = SalePayment.objects.filter(
            sale__business=request.business,
            sale__date__date__gte=start_date,
            sale__date__date__lte=end_date
        ).values('payment_method__name').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')
        
        # Top products
        top_products = SaleItem.objects.filter(
            sale__business=request.business,
            sale__date__date__gte=start_date,
            sale__date__date__lte=end_date
        ).values('product__name').annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price')
        ).order_by('-revenue')[:10]
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1d29'),
            spaceAfter=10,
            alignment=TA_CENTER
        )
        elements.append(Paragraph('SALES ANALYTICS REPORT', title_style))
        
        # Period
        period_style = ParagraphStyle(
            'Period',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#666666'),
            spaceAfter=20,
            alignment=TA_CENTER
        )
        elements.append(Paragraph(period_label, period_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Summary section
        elements.append(Paragraph('<b>SUMMARY</b>', styles['Heading2']))
        elements.append(Spacer(1, 0.1*inch))
        
        summary_data = [
            ['Metric', 'Value'],
            ['Total Sales', str(total_sales)],
            ['Total Revenue', f'KES {total_revenue:,.2f}'],
            ['Total Discounts', f'KES {total_discounts:,.2f}'],
            ['Total VAT', f'KES {total_vat:,.2f}'],
            ['Average Sale', f'KES {(total_revenue / total_sales if total_sales > 0 else 0):,.2f}'],
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Payment methods section
        if payment_methods:
            elements.append(Paragraph('<b>PAYMENT METHODS BREAKDOWN</b>', styles['Heading2']))
            elements.append(Spacer(1, 0.1*inch))
            
            payment_data = [['Payment Method', 'Transactions', 'Total Amount']]
            for pm in payment_methods:
                payment_data.append([
                    pm['payment_method__name'] or 'Unknown',
                    str(pm['count']),
                    f"KES {pm['total']:,.2f}"
                ])
            
            payment_table = Table(payment_data, colWidths=[2.5*inch, 1.5*inch, 2*inch])
            payment_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(payment_table)
            elements.append(Spacer(1, 0.3*inch))
        
        # Top products section
        if top_products:
            elements.append(Paragraph('<b>TOP 10 PRODUCTS</b>', styles['Heading2']))
            elements.append(Spacer(1, 0.1*inch))
            
            products_data = [['#', 'Product', 'Qty Sold', 'Revenue']]
            for idx, product in enumerate(top_products, 1):
                products_data.append([
                    str(idx),
                    product['product__name'] or 'Unknown',
                    str(product['quantity']),
                    f"KES {product['revenue']:,.2f}"
                ])
            
            products_table = Table(products_data, colWidths=[0.5*inch, 3*inch, 1*inch, 1.5*inch])
            products_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 1), (0, -1), 'CENTER'),
                ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
                ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(products_table)
        
        # Footer
        elements.append(Spacer(1, 0.5*inch))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#999999'),
            alignment=TA_CENTER
        )
        elements.append(Paragraph(f'Generated on {datetime.now().strftime("%B %d, %Y at %I:%M %p")}', footer_style))
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="analytics-report-{start_date}-to-{end_date}.pdf"'
        return response
        
    except Exception as e:
        messages.error(request, f'Error generating PDF: {str(e)}')
        return redirect('dashboard')



@business_required
def payment_transactions_report(request, slug=None):
    """Detailed payment transactions report with filters"""
    from django.core.paginator import Paginator
    from django.db.models import Q, Sum
    
    try:
        # Get filter parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        payment_method = request.GET.get('payment_method')
        search = request.GET.get('search', '').strip()
        
        # Default date range (current month)
        today = datetime.now().date()
        if not start_date:
            start_date = today.replace(day=1)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if not end_date:
            end_date = today
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Base query - filter by business
        payments = SalePayment.objects.filter(
            business=request.business,
            sale__date__date__gte=start_date,
            sale__date__date__lte=end_date
        ).select_related('sale', 'payment_method', 'sale__customer', 'sale__cashier')
        
        # Apply filters
        if payment_method:
            payments = payments.filter(payment_method_id=payment_method)
        
        if search:
            payments = payments.filter(
                Q(sale__invoice_number__icontains=search) |
                Q(reference_number__icontains=search) |
                Q(sale__customer__name__icontains=search)
            )
        
        # Order by date (newest first)
        payments = payments.order_by('-sale__date')
        
        # Calculate summary
        total_transactions = payments.count()
        total_amount = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        # Calculate cash total - check both code and name for backward compatibility
        cash_total = payments.filter(
            Q(payment_method__code='CASH') | Q(payment_method__name__iexact='CASH')
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        non_cash_total = total_amount - cash_total
        
        # Pagination
        paginator = Paginator(payments, 50)  # 50 transactions per page
        page_number = request.GET.get('page')
        payments_page = paginator.get_page(page_number)
        
        # Get all payment methods for filter dropdown
        payment_methods_list = PaymentMethod.objects.filter(business=request.business, is_active=True).order_by('name')
        
        context = {
            'payments': payments_page,
            'start_date': start_date,
            'end_date': end_date,
            'payment_method': payment_method,
            'search': search,
            'total_transactions': total_transactions,
            'total_amount': total_amount,
            'cash_total': cash_total,
            'non_cash_total': non_cash_total,
            'payment_methods_list': payment_methods_list,
        }
        
        return render(request, 'pos/payment_transactions_report.html', context)
    
    except Exception as e:
        # Log the error and show a user-friendly message
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in payment_transactions_report: {str(e)}")
        logger.error(traceback.format_exc())
        messages.error(request, f"Error loading payment transactions: {str(e)}")
        return redirect('dashboard', slug=request.business.slug)



@business_required
def payment_transactions_export(request, slug=None):
    """Export payment transactions as PDF"""
    from django.db.models import Q, Sum
    
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    payment_method = request.GET.get('payment_method')
    search = request.GET.get('search', '').strip()
    
    # Default date range
    today = datetime.now().date()
    if not start_date:
        start_date = today.replace(day=1)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = today
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Query payments - filter by business
    payments = SalePayment.objects.filter(
        business=request.business,
        sale__date__date__gte=start_date,
        sale__date__date__lte=end_date
    ).select_related('sale', 'payment_method', 'sale__customer', 'sale__cashier')
    
    if payment_method:
        payments = payments.filter(payment_method_id=payment_method)
    
    if search:
        payments = payments.filter(
            Q(sale__invoice_number__icontains=search) |
            Q(reference_number__icontains=search) |
            Q(sale__customer__name__icontains=search)
        )
    
    payments = payments.order_by('-sale__date')
    
    # Calculate totals
    total_amount = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1a1d29'),
        spaceAfter=10,
        alignment=TA_CENTER
    )
    elements.append(Paragraph('PAYMENT TRANSACTIONS REPORT', title_style))
    
    # Period
    period_style = ParagraphStyle(
        'Period',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#666666'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    elements.append(Paragraph(
        f'{start_date.strftime("%B %d, %Y")} - {end_date.strftime("%B %d, %Y")}',
        period_style
    ))
    elements.append(Spacer(1, 0.2*inch))
    
    # Summary
    elements.append(Paragraph(f'<b>Total Transactions:</b> {payments.count()}', styles['Normal']))
    elements.append(Paragraph(f'<b>Total Amount:</b> KES {total_amount:,.2f}', styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Transactions table
    data = [['Date', 'Invoice', 'Method', 'Amount', 'Reference']]
    
    for payment in payments[:500]:  # Limit to 500 for PDF
        data.append([
            payment.sale.date.strftime('%m/%d/%Y %H:%M'),
            payment.sale.invoice_number,
            payment.payment_method.name,
            f'KES {payment.amount:,.2f}',
            payment.reference_number or '-'
        ])
    
    table = Table(data, colWidths=[1.3*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1.8*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table)
    
    # Footer
    elements.append(Spacer(1, 0.3*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#999999'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(
        f'Generated on {datetime.now().strftime("%B %d, %Y at %I:%M %p")}',
        footer_style
    ))
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="payment-transactions-{start_date}-to-{end_date}.pdf"'
    return response


@business_required
def payment_transactions_csv(request, slug=None):
    """Export payment transactions as CSV"""
    import csv
    from django.db.models import Q
    
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    payment_method = request.GET.get('payment_method')
    search = request.GET.get('search', '').strip()
    
    # Default date range
    today = datetime.now().date()
    if not start_date:
        start_date = today.replace(day=1)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = today
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Query payments - filter by business
    payments = SalePayment.objects.filter(
        business=request.business,
        sale__date__date__gte=start_date,
        sale__date__date__lte=end_date
    ).select_related('sale', 'payment_method', 'sale__customer', 'sale__cashier')
    
    if payment_method:
        payments = payments.filter(payment_method_id=payment_method)
    
    if search:
        payments = payments.filter(
            Q(sale__invoice_number__icontains=search) |
            Q(reference_number__icontains=search) |
            Q(sale__customer__name__icontains=search)
        )
    
    payments = payments.order_by('-sale__date')
    
    # Create CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="payment-transactions-{start_date}-to-{end_date}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Time', 'Invoice Number', 'Payment Method', 'Amount', 'Reference', 'Customer', 'Cashier'])
    
    for payment in payments:
        writer.writerow([
            payment.sale.date.strftime('%Y-%m-%d'),
            payment.sale.date.strftime('%H:%M:%S'),
            payment.sale.invoice_number,
            payment.payment_method.name,
            float(payment.amount),
            payment.reference_number or '',
            payment.sale.customer.name if payment.sale.customer else 'Walk-in',
            payment.sale.cashier.get_full_name() if payment.sale.cashier else ''
        ])
    
    return response


# ==================== PAYMENT METHODS MANAGEMENT ====================

@login_required
@business_required
def payment_method_list(request, slug):
    """List all payment methods for the business"""
    payment_methods = request.business.payment_methods.all().order_by('name')
    
    context = {
        'payment_methods': payment_methods,
    }
    return render(request, 'pos/payment_method_list.html', context)


@login_required
@business_required
def payment_method_create(request, slug):
    """Create a new payment method"""
    from .models import PaymentMethod
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        is_active = request.POST.get('is_active') == 'on'
        requires_reference = request.POST.get('requires_reference') == 'on'
        icon = request.POST.get('icon', '').strip()
        
        # Validation
        if not name or not code:
            messages.error(request, 'Name and code are required.')
            return redirect('payment_method_create', slug=request.business.slug)
        
        # Check if code already exists for this business
        if PaymentMethod.objects.filter(business=request.business, code=code).exists():
            messages.error(request, f'Payment method with code "{code}" already exists.')
            return redirect('payment_method_create', slug=request.business.slug)
        
        # Create payment method
        payment_method = PaymentMethod.objects.create(
            business=request.business,
            name=name,
            code=code,
            is_active=is_active,
            requires_reference=requires_reference,
            icon=icon
        )
        
        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action_type='create',
            model_name='PaymentMethod',
            object_id=payment_method.id,
            description=f'Created payment method: {payment_method.name}'
        )
        
        messages.success(request, f'Payment method "{payment_method.name}" created successfully.')
        return redirect('payment_method_list', slug=request.business.slug)
    
    # Bootstrap icon suggestions
    icon_suggestions = [
        {'icon': 'bi-cash-coin', 'name': 'Cash'},
        {'icon': 'bi-credit-card', 'name': 'Card'},
        {'icon': 'bi-phone', 'name': 'Mobile Money'},
        {'icon': 'bi-bank', 'name': 'Bank Transfer'},
        {'icon': 'bi-wallet2', 'name': 'Wallet'},
    ]
    
    context = {
        'icon_suggestions': icon_suggestions,
    }
    return render(request, 'pos/payment_method_form.html', context)


@login_required
@business_required
def payment_method_edit(request, slug, pk):
    """Edit an existing payment method"""
    from .models import PaymentMethod
    
    payment_method = get_object_or_404(PaymentMethod, pk=pk, business=request.business)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        is_active = request.POST.get('is_active') == 'on'
        requires_reference = request.POST.get('requires_reference') == 'on'
        icon = request.POST.get('icon', '').strip()
        
        # Validation
        if not name or not code:
            messages.error(request, 'Name and code are required.')
            return redirect('payment_method_edit', slug=request.business.slug, pk=pk)
        
        # Check if code already exists for another payment method
        if PaymentMethod.objects.filter(business=request.business, code=code).exclude(pk=pk).exists():
            messages.error(request, f'Payment method with code "{code}" already exists.')
            return redirect('payment_method_edit', slug=request.business.slug, pk=pk)
        
        # Update payment method
        payment_method.name = name
        payment_method.code = code
        payment_method.is_active = is_active
        payment_method.requires_reference = requires_reference
        payment_method.icon = icon
        payment_method.save()
        
        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action_type='update',
            model_name='PaymentMethod',
            object_id=payment_method.id,
            description=f'Updated payment method: {payment_method.name}'
        )
        
        messages.success(request, f'Payment method "{payment_method.name}" updated successfully.')
        return redirect('payment_method_list', slug=request.business.slug)
    
    # Bootstrap icon suggestions
    icon_suggestions = [
        {'icon': 'bi-cash-coin', 'name': 'Cash'},
        {'icon': 'bi-credit-card', 'name': 'Card'},
        {'icon': 'bi-phone', 'name': 'Mobile Money'},
        {'icon': 'bi-bank', 'name': 'Bank Transfer'},
        {'icon': 'bi-wallet2', 'name': 'Wallet'},
    ]
    
    context = {
        'payment_method': payment_method,
        'icon_suggestions': icon_suggestions,
    }
    return render(request, 'pos/payment_method_form.html', context)


@login_required
@business_required
def payment_method_delete(request, slug, pk):
    """Delete a payment method"""
    from .models import PaymentMethod
    
    payment_method = get_object_or_404(PaymentMethod, pk=pk, business=request.business)
    
    # Check if payment method is being used
    if payment_method.salepayment_set.exists():
        messages.error(request, f'Cannot delete "{payment_method.name}" because it has been used in sales.')
        return redirect('payment_method_list', slug=request.business.slug)
    
    if payment_method.supplierpayment_set.exists():
        messages.error(request, f'Cannot delete "{payment_method.name}" because it has been used in supplier payments.')
        return redirect('payment_method_list', slug=request.business.slug)
    
    if request.method == 'POST':
        name = payment_method.name
        
        # Log activity before deletion
        ActivityLog.objects.create(
            user=request.user,
            action_type='delete',
            model_name='PaymentMethod',
            object_id=payment_method.id,
            description=f'Deleted payment method: {name}'
        )
        
        payment_method.delete()
        messages.success(request, f'Payment method "{name}" deleted successfully.')
        return redirect('payment_method_list', slug=request.business.slug)
    
    context = {
        'payment_method': payment_method,
    }
    return render(request, 'pos/payment_method_confirm_delete.html', context)


# ==================== GOODS RECEIVED NOTE VIEWS ====================

@login_required
@business_required
@can_manage_purchases
def goods_received_list(request, slug=None):
    """List all Goods Received Notes"""
    notes = GoodsReceivedNote.objects.filter(
        business=request.business
    ).select_related('supplier', 'purchase', 'received_by')

    status_filter = request.GET.get('status', '')
    supplier_filter = request.GET.get('supplier', '')
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')

    if status_filter:
        notes = notes.filter(status=status_filter)
    if supplier_filter:
        notes = notes.filter(supplier_id=supplier_filter)
    if from_date:
        notes = notes.filter(received_date__gte=from_date)
    if to_date:
        notes = notes.filter(received_date__lte=to_date)

    context = {
        'notes': notes,
        'suppliers': Supplier.objects.filter(business=request.business, is_active=True),
        'status_filter': status_filter,
        'supplier_filter': supplier_filter,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'pos/goods_received_list.html', context)


@login_required
@business_required
@can_manage_purchases
def goods_received_detail(request, slug=None, pk=None):
    """View a Goods Received Note"""
    note = get_object_or_404(GoodsReceivedNote, business=request.business, pk=pk)
    items = note.items.select_related('product').all()
    context = {'note': note, 'items': items}
    return render(request, 'pos/goods_received_detail.html', context)


@login_required
@business_required
@can_manage_purchases
def goods_received_print(request, slug=None, pk=None):
    """Print-friendly Goods Received Note"""
    note = get_object_or_404(GoodsReceivedNote, business=request.business, pk=pk)
    items = note.items.select_related('product').all()
    return render(request, 'pos/goods_received_print.html', {'note': note, 'items': items})


# ==================== GOODS RETURNED NOTE (GRN) VIEWS ====================

@login_required
@business_required
@can_manage_purchases
def grn_list(request, slug=None):
    """List all GRNs"""
    grns = GoodsReturnedNote.objects.filter(business=request.business).select_related('supplier', 'created_by')
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        grns = grns.filter(status=status_filter)
    
    # Filter by supplier
    supplier_filter = request.GET.get('supplier')
    if supplier_filter:
        grns = grns.filter(supplier_id=supplier_filter)
    
    # Filter by date range
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    if from_date:
        grns = grns.filter(return_date__gte=from_date)
    if to_date:
        grns = grns.filter(return_date__lte=to_date)
    
    context = {
        'grns': grns,
        'suppliers': Supplier.objects.filter(business=request.business, is_active=True),
        'status_filter': status_filter,
        'supplier_filter': supplier_filter,
        'from_date': from_date or '',
        'to_date': to_date or '',
    }
    return render(request, 'pos/grn_list.html', context)


@login_required
@business_required
@can_manage_purchases
def grn_create(request, slug=None):
    """Create new GRN"""
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        purchase_id = request.POST.get('related_purchase')
        return_reason = request.POST.get('return_reason')
        reason_details = request.POST.get('reason_details')
        return_date = request.POST.get('return_date')
        
        try:
            supplier = Supplier.objects.get(id=supplier_id, business=request.business)
            purchase = None
            if purchase_id:
                purchase = Purchase.objects.get(id=purchase_id, business=request.business)
            
            # Create GRN
            grn = GoodsReturnedNote.objects.create(
                business=request.business,
                supplier=supplier,
                related_purchase=purchase,
                return_reason=return_reason,
                reason_details=reason_details,
                return_date=return_date if return_date else timezone.now().date(),
                created_by=request.user
            )
            
            # Add items
            item_count = 0
            for key in request.POST:
                if key.startswith('item_product_'):
                    index = key.split('_')[-1]
                    product_id = request.POST.get(f'item_product_{index}')
                    quantity = request.POST.get(f'item_quantity_{index}')
                    unit_cost = request.POST.get(f'item_cost_{index}')
                    batch = request.POST.get(f'item_batch_{index}', '')
                    expiry = request.POST.get(f'item_expiry_{index}', '')
                    notes = request.POST.get(f'item_notes_{index}', '')
                    
                    if product_id and quantity and unit_cost:
                        product = Product.objects.get(id=product_id, business=request.business)
                        
                        GoodsReturnedNoteItem.objects.create(
                            grn=grn,
                            product=product,
                            quantity=int(quantity),
                            unit_cost=Decimal(unit_cost),
                            batch_number=batch,
                            expiry_date=expiry if expiry else None,
                            item_notes=notes
                        )
                        
                        # Create stock adjustment (deduct returned items)
                        previous_qty = product.stock_quantity
                        product.stock_quantity -= Decimal(quantity)
                        product.save()
                        
                        StockAdjustment.objects.create(
                            business=request.business,
                            product=product,
                            adjustment_type='return',
                            quantity_change=-int(quantity),
                            previous_quantity=int(previous_qty),
                            new_quantity=int(product.stock_quantity),
                            reason=f'Returned to supplier - {grn.grn_number}'
                        )
                        
                        item_count += 1
            
            if item_count == 0:
                grn.delete()
                messages.error(request, 'Please add at least one item to the GRN.')
                return redirect('grn_create', slug=slug)
            
            # Check if should submit immediately
            action = request.POST.get('action', 'draft')
            if action == 'submit':
                grn.submit_to_supplier()
                from .email_service import EmailService
                EmailService.send_grn_notification(grn)
                messages.success(request, f'GRN {grn.grn_number} created and submitted to supplier!')
            else:
                messages.success(request, f'GRN {grn.grn_number} created as draft.')
            
            return redirect('grn_detail', slug=slug, pk=grn.pk)
            
        except Exception as e:
            messages.error(request, f'Error creating GRN: {str(e)}')
    
    # GET request
    suppliers = Supplier.objects.filter(business=request.business, is_active=True)
    purchases = Purchase.objects.filter(business=request.business, status='received').order_by('-date')[:50]
    products = Product.objects.filter(business=request.business).order_by('name')
    
    context = {
        'suppliers': suppliers,
        'purchases': purchases,
        'products': products,
        'today': timezone.now().date(),
    }
    return render(request, 'pos/grn_form.html', context)


@login_required
@business_required
@can_manage_purchases
def grn_detail(request, slug=None, pk=None):
    """View GRN details"""
    grn = get_object_or_404(GoodsReturnedNote, business=request.business, pk=pk)
    items = grn.items.select_related('product').all()
    
    context = {
        'grn': grn,
        'items': items,
    }
    return render(request, 'pos/grn_detail.html', context)


@login_required
@business_required
@can_manage_purchases
def grn_submit(request, slug=None, pk=None):
    """Submit GRN to supplier"""
    grn = get_object_or_404(GoodsReturnedNote, business=request.business, pk=pk)
    
    if request.method == 'POST':
        if grn.submit_to_supplier():
            # Send email to supplier
            from .email_service import EmailService
            email_sent = EmailService.send_grn_notification(grn)

            if email_sent:
                messages.success(request, f'GRN {grn.grn_number} submitted and emailed to supplier.')
            else:
                messages.success(request, f'GRN {grn.grn_number} submitted to supplier.')
                if grn.supplier.email:
                    messages.info(request, 'Email notification could not be sent. Check email settings.')
        else:
            messages.error(request, 'GRN cannot be submitted (already submitted or wrong status).')
        return redirect('grn_detail', slug=slug, pk=pk)
    
    return render(request, 'pos/grn_submit_confirm.html', {'grn': grn})


@login_required
@business_required
@can_manage_purchases
def grn_mark_collected(request, slug=None, pk=None):
    """Mark GRN as collected"""
    grn = get_object_or_404(GoodsReturnedNote, business=request.business, pk=pk)
    
    if request.method == 'POST':
        collection_date = request.POST.get('collection_date')
        collection_notes = request.POST.get('collection_notes', '')
        
        grn.mark_collected(
            collection_date=collection_date if collection_date else None,
            notes=collection_notes
        )
        messages.success(request, f'GRN {grn.grn_number} marked as collected.')
        return redirect('grn_detail', slug=slug, pk=pk)
    
    return render(request, 'pos/grn_mark_collected.html', {
        'grn': grn,
        'today': timezone.now().date(),
    })


@login_required
@business_required
@can_manage_purchases
def grn_apply_credit(request, slug=None, pk=None):
    """Apply credit note to GRN"""
    grn = get_object_or_404(GoodsReturnedNote, business=request.business, pk=pk)
    
    if request.method == 'POST':
        credit_note_number = request.POST.get('credit_note_number')
        credit_note_amount = request.POST.get('credit_amount')  # Form uses 'credit_amount'
        credit_note_date = request.POST.get('credit_date')  # Form uses 'credit_date'
        
        # Validate required fields
        if not credit_note_number or not credit_note_amount:
            messages.error(request, 'Credit note number and amount are required.')
            return redirect('grn_apply_credit', slug=slug, pk=pk)
        
        try:
            amount = Decimal(credit_note_amount)
            if amount <= 0:
                messages.error(request, 'Credit note amount must be greater than zero.')
                return redirect('grn_apply_credit', slug=slug, pk=pk)
        except (ValueError, TypeError):
            messages.error(request, 'Invalid credit note amount.')
            return redirect('grn_apply_credit', slug=slug, pk=pk)
        
        grn.apply_credit_note(
            credit_note_number=credit_note_number,
            amount=amount,
            date=credit_note_date if credit_note_date else None
        )
        messages.success(request, f'Credit note applied to GRN {grn.grn_number}.')
        return redirect('grn_detail', slug=slug, pk=pk)
    
    return render(request, 'pos/grn_apply_credit.html', {
        'grn': grn,
        'today': timezone.now().date(),
        'suggested_cn_number': f'CN-{grn.grn_number}',
    })


@login_required
@business_required
@can_manage_purchases
def grn_cancel(request, slug=None, pk=None):
    """Cancel GRN"""
    grn = get_object_or_404(GoodsReturnedNote, business=request.business, pk=pk)
    
    if request.method == 'POST':
        if grn.cancel():
            # Reverse stock adjustments
            for item in grn.items.all():
                product = item.product
                previous_qty = product.stock_quantity
                product.stock_quantity += Decimal(item.quantity)
                product.save()
                
                StockAdjustment.objects.create(
                    business=request.business,
                    product=product,
                    adjustment_type='correction',
                    quantity_change=item.quantity,
                    previous_quantity=int(previous_qty),
                    new_quantity=int(product.stock_quantity),
                    reason=f'GRN {grn.grn_number} cancelled - stock restored'
                )
            
            messages.success(request, f'GRN {grn.grn_number} cancelled and stock restored.')
        else:
            messages.error(request, 'GRN cannot be cancelled (already collected or credited).')
        return redirect('grn_detail', slug=slug, pk=pk)
    
    return render(request, 'pos/grn_cancel_confirm.html', {'grn': grn})


@login_required
@business_required
@can_manage_purchases
def grn_acknowledge(request, slug=None, pk=None):
    """Mark GRN as acknowledged by supplier"""
    grn = get_object_or_404(GoodsReturnedNote, business=request.business, pk=pk)

    if request.method == 'POST':
        if grn.status == 'submitted':
            grn.status = 'acknowledged'
            grn.save()
            messages.success(request, f'GRN {grn.grn_number} marked as acknowledged by supplier.')
        else:
            messages.error(request, 'Only submitted GRNs can be acknowledged.')
        return redirect('grn_detail', slug=slug, pk=pk)

    return render(request, 'pos/grn_acknowledge_confirm.html', {'grn': grn})


@login_required
@business_required
@can_manage_purchases
def grn_print(request, slug=None, pk=None):
    """Print-friendly GRN view"""
    grn = get_object_or_404(GoodsReturnedNote, business=request.business, pk=pk)
    items = grn.items.select_related('product').all()
    return render(request, 'pos/grn_print.html', {'grn': grn, 'items': items})


@login_required
@business_required
@can_manage_purchases
def api_grn_supplier_purchases(request, slug=None):
    """AJAX: Return received purchases for a given supplier"""
    from django.http import JsonResponse
    supplier_id = request.GET.get('supplier_id')
    if not supplier_id:
        return JsonResponse({'purchases': []})

    purchases = Purchase.objects.filter(
        business=request.business,
        supplier_id=supplier_id,
        status='received'
    ).order_by('-date').values('id', 'purchase_number', 'date', 'total_amount')[:50]

    data = [
        {
            'id': p['id'],
            'text': f"{p['purchase_number']} — KES {p['total_amount']:,.2f}",
        }
        for p in purchases
    ]
    return JsonResponse({'purchases': data})


@login_required
@business_required
def subscription(request, slug=None):
    """Subscription and billing page for businesses"""
    # Superusers have lifetime access, no subscription needed
    if request.user.is_superuser:
        messages.info(request, 'As the app owner, you have lifetime access to all features. No subscription required!')
        return redirect('dashboard', slug=slug)
    
    business = request.business
    
    # Get payment history for this business
    payments = business.subscription_payments.all().order_by('-payment_date')[:10]
    
    context = {
        'business': business,
        'payments': payments,
    }
    
    return render(request, 'pos/subscription.html', context)


# ==================== ADVANCED ANALYTICS ====================

@login_required
@business_required
def global_search(request, slug=None):
    """Global search across products, customers, and invoices"""
    query = request.GET.get('q', '').strip()
    products = customers = sales = []

    if query:
        products = Product.objects.filter(
            business=request.business, is_active=True
        ).filter(
            Q(name__icontains=query) |
            Q(product_code__icontains=query) |
            Q(barcode__icontains=query)
        ).select_related('category')[:20]

        customers = Customer.objects.filter(
            business=request.business
        ).filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(email__icontains=query)
        )[:20]

        sales = Sale.objects.filter(
            business=request.business
        ).filter(
            Q(invoice_number__icontains=query) |
            Q(customer__name__icontains=query)
        ).select_related('customer', 'cashier').order_by('-date')[:20]

    return render(request, 'pos/global_search.html', {
        'query': query,
        'products': products,
        'customers': customers,
        'sales': sales,
    })


@business_required
@business_permission_required('can_view_reports')
def analytics_dashboard(request, slug=None):
    """Advanced analytics dashboard with charts and insights"""
    from .analytics_service import AnalyticsService
    from django.utils import timezone
    import json
    
    # Get date range from request (default to last 30 days)
    days = int(request.GET.get('days', 30))
    
    # Initialize analytics service
    analytics = AnalyticsService(request.business)
    
    # Get dashboard summary
    summary = analytics.get_dashboard_summary(days=days)
    
    # Get sales trends for chart
    sales_trends_raw = analytics.get_sales_trends(days=days)
    sales_trends = {
        'dates': json.dumps(sales_trends_raw['dates']),
        'totals': json.dumps(sales_trends_raw['totals']),
        'profits': json.dumps(sales_trends_raw['profits']),
    }
    
    # Get best sellers
    best_sellers = analytics.get_best_sellers(limit=10, days=days)
    
    # Get sales by category — serialize to JSON for Chart.js
    cat_start = timezone.now().date() - timedelta(days=days)
    category_sales_raw = analytics.get_sales_by_category(start_date=cat_start)
    category_sales = [
        {**item, 'total_revenue': float(item['total_revenue'] or 0)}
        for item in category_sales_raw
    ]
    category_chart = {
        'labels': json.dumps([item['product__category__name'] or 'Uncategorized' for item in category_sales]),
        'data': json.dumps([item['total_revenue'] for item in category_sales]),
    }
    
    # Get payment method breakdown
    payment_breakdown_raw = analytics.get_payment_method_breakdown(days=days)
    payment_breakdown = {
        'labels': json.dumps(payment_breakdown_raw['labels']),
        'amounts': json.dumps(payment_breakdown_raw['amounts']),
    }
    
    # Get profit margin analysis
    profit_analysis = analytics.get_profit_margin_analysis()
    
    # Get customer retention
    retention = analytics.get_customer_retention_rate(days=days)
    
    # Get stock turnover
    turnover = analytics.get_stock_turnover_rate(days=days)
    
    context = {
        'summary': summary,
        'sales_trends': sales_trends,
        'best_sellers': best_sellers,
        'category_sales': category_sales,
        'category_chart': category_chart,
        'payment_breakdown': payment_breakdown,
        'profit_analysis': profit_analysis,
        'retention': retention,
        'turnover': turnover,
        'days': days,
    }
    
    return render(request, 'pos/analytics_dashboard.html', context)


@business_required
@business_permission_required('can_view_reports')
def analytics_sales_trends(request, slug=None):
    """Detailed sales trends analysis"""
    from .analytics_service import AnalyticsService
    import json
    
    days = int(request.GET.get('days', 30))
    analytics = AnalyticsService(request.business)
    
    # Get sales trends
    st = analytics.get_sales_trends(days=days)
    sales_trends = {
        'dates': json.dumps(st['dates']),
        'totals': json.dumps(st['totals']),
        'profits': json.dumps(st['profits']),
    }
    
    # Get hourly patterns
    hp = analytics.get_hourly_sales_pattern(days=7)
    hourly_patterns = {
        'hours': json.dumps(hp['hours']),
        'totals': json.dumps(hp['totals']),
    }
    
    # Get revenue vs profit
    rp = analytics.get_revenue_vs_profit_trend(days=days)
    revenue_profit = {
        'dates': json.dumps(rp['dates']),
        'revenue': json.dumps(rp['revenue']),
        'profit': json.dumps(rp['profit']),
    }
    
    context = {
        'sales_trends': sales_trends,
        'hourly_patterns': hourly_patterns,
        'revenue_profit': revenue_profit,
        'days': days,
    }
    
    return render(request, 'pos/analytics_sales_trends.html', context)


@business_required
@business_permission_required('can_view_reports')
def analytics_products(request, slug=None):
    """Product performance analytics"""
    from .analytics_service import AnalyticsService
    
    days = int(request.GET.get('days', 30))
    analytics = AnalyticsService(request.business)
    
    # Get product analytics
    best_sellers = analytics.get_best_sellers(limit=20, days=days)
    slow_movers = analytics.get_slow_moving_items(limit=20, days=days)
    abc_analysis = analytics.get_abc_analysis()
    turnover = analytics.get_stock_turnover_rate(days=days)
    
    context = {
        'best_sellers': best_sellers,
        'slow_movers': slow_movers,
        'abc_analysis': abc_analysis,
        'turnover': turnover,
        'days': days,
    }
    
    return render(request, 'pos/analytics_products.html', context)


@business_required
@business_permission_required('can_view_reports')
def analytics_customers(request, slug=None):
    """Customer analytics and insights"""
    from .analytics_service import AnalyticsService
    
    days = int(request.GET.get('days', 90))
    analytics = AnalyticsService(request.business)
    
    # Get customer analytics
    customer_insights = analytics.get_customer_insights(days=days)
    retention = analytics.get_customer_retention_rate(days=30)
    
    context = {
        'customer_insights': customer_insights,
        'retention': retention,
        'days': days,
    }
    
    return render(request, 'pos/analytics_customers.html', context)


@business_required
@business_permission_required('can_view_reports')
def analytics_api(request, slug=None):
    """API endpoint for analytics data (AJAX)"""
    from .analytics_service import AnalyticsService
    import json
    
    analytics_type = request.GET.get('type', 'summary')
    days = int(request.GET.get('days', 30))
    
    analytics = AnalyticsService(request.business)
    
    if analytics_type == 'summary':
        data = analytics.get_dashboard_summary(days=days)
    elif analytics_type == 'sales_trends':
        data = analytics.get_sales_trends(days=days)
    elif analytics_type == 'hourly_pattern':
        data = analytics.get_hourly_sales_pattern(days=7)
    elif analytics_type == 'category_sales':
        data = analytics.get_sales_by_category()
    elif analytics_type == 'best_sellers':
        data = analytics.get_best_sellers(limit=10, days=days)
    elif analytics_type == 'payment_breakdown':
        data = analytics.get_payment_method_breakdown(days=days)
    else:
        data = {'error': 'Invalid analytics type'}
    
    # Convert Decimal to float for JSON serialization
    def decimal_to_float(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: decimal_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [decimal_to_float(item) for item in obj]
        return obj
    
    data = decimal_to_float(data)
    
    return JsonResponse(data, safe=False)
