from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q, F
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from decimal import Decimal
from datetime import datetime, timedelta
from .models import Product, Category, Sale, SaleItem, StockAdjustment, Supplier, Purchase, PurchaseItem, Customer
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.core.exceptions import PermissionDenied
import io


def manager_required(view_func):
    """Decorator to check if user is a manager or superuser"""
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')
    return wrapper


def can_manage_products(view_func):
    """Decorator to check if user can manage products"""
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            request.user.groups.filter(name__in=['Manager', 'Stock Manager']).exists() or
            request.user.has_perm('pos.change_product')):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You do not have permission to manage products.')
        return redirect('dashboard')
    return wrapper


def can_manage_purchases(view_func):
    """Decorator to check if user can manage purchases"""
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            request.user.groups.filter(name__in=['Manager', 'Stock Manager']).exists() or
            request.user.has_perm('pos.add_purchase')):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You do not have permission to manage purchases.')
        return redirect('dashboard')
    return wrapper


@login_required
@login_required
def dashboard(request):
    """Main dashboard with quick stats"""
    today = datetime.now().date()
    today_sales = Sale.objects.filter(date__date=today)
    
    # Stock statistics
    low_stock_products = Product.objects.filter(stock_quantity__lte=models.F('low_stock_threshold')).count()
    out_of_stock_products = Product.objects.filter(stock_quantity=0).count()
    
    # Supplier and Purchase statistics
    total_suppliers = Supplier.objects.filter(is_active=True).count()
    pending_purchases = Purchase.objects.filter(status='pending').count()
    
    # Expiry statistics
    expired_count = Product.objects.filter(expiry_date__lt=today, stock_quantity__gt=0).count()
    expiring_soon_count = 0
    products_with_expiry = Product.objects.filter(expiry_date__gte=today, stock_quantity__gt=0)
    for product in products_with_expiry:
        if product.is_expiring_soon():
            expiring_soon_count += 1
    
    # Fetch actual products for display
    out_of_stock_list = Product.objects.filter(stock_quantity=0).select_related('category')[:5]
    
    expired_list = Product.objects.filter(
        expiry_date__lt=today, 
        stock_quantity__gt=0
    ).select_related('category')[:5]
    
    expiring_soon_list = []
    for product in products_with_expiry[:10]:  # Check first 10
        if product.is_expiring_soon():
            expiring_soon_list.append(product)
            if len(expiring_soon_list) >= 5:  # Limit to 5
                break
    
    context = {
        'total_products': Product.objects.count(),
        'total_categories': Category.objects.count(),
        'today_sales_count': today_sales.count(),
        'today_revenue': today_sales.aggregate(Sum('total'))['total__sum'] or 0,
        'low_stock_count': low_stock_products,
        'out_of_stock_count': out_of_stock_products,
        'total_suppliers': total_suppliers,
        'pending_purchases': pending_purchases,
        'expired_count': expired_count,
        'expiring_soon_count': expiring_soon_count,
        'out_of_stock_list': out_of_stock_list,
        'expired_list': expired_list,
        'expiring_soon_list': expiring_soon_list,
    }
    return render(request, 'pos/dashboard.html', context)


@login_required
@login_required
def product_list(request):
    """List all products"""
    products = Product.objects.select_related('category').all()
    categories = Category.objects.all()
    return render(request, 'pos/product_list.html', {'products': products, 'categories': categories})


@login_required
@login_required
def product_bulk_upload(request):
    """Bulk upload products via CSV"""
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, 'No file uploaded!')
            return redirect('product_bulk_upload')
        
        csv_file = request.FILES['csv_file']
        
        # Validate file extension
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'File must be a CSV!')
            return redirect('product_bulk_upload')
        
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
                        category, _ = Category.objects.get_or_create(name=row['category'].strip())
                    
                    # Prepare product data
                    product_code = row.get('product_code', '').strip() or None
                    stock_quantity = int(row.get('stock_quantity', 0))
                    low_stock_threshold = int(row.get('low_stock_threshold', 10))
                    
                    # Check if product exists (by name or code)
                    existing_product = None
                    if product_code:
                        existing_product = Product.objects.filter(product_code=product_code).first()
                    if not existing_product:
                        existing_product = Product.objects.filter(name=row['name'].strip()).first()
                    
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
            
            return redirect('product_list')
            
        except Exception as e:
            messages.error(request, f'Error processing CSV file: {str(e)}')
            return redirect('product_bulk_upload')
    
    return render(request, 'pos/product_bulk_upload.html')


@login_required
def product_export_csv(request):
    """Export products as CSV"""
    import csv
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['name', 'product_code', 'category', 'unit_price', 'stock_quantity', 'low_stock_threshold'])
    
    products = Product.objects.select_related('category').all()
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


@login_required
def product_create(request):
    """Create new product"""
    if request.method == 'POST':
        name = request.POST.get('name')
        product_code = request.POST.get('product_code')
        category_id = request.POST.get('category')
        unit_price = request.POST.get('unit_price')
        stock_quantity = request.POST.get('stock_quantity', 0)
        low_stock_threshold = request.POST.get('low_stock_threshold', 10)
        expiry_date = request.POST.get('expiry_date')
        expiry_alert_days = request.POST.get('expiry_alert_days', 3)
        image = request.FILES.get('image')  # Get uploaded image
        
        try:
            category = Category.objects.get(id=category_id) if category_id else None
            product = Product.objects.create(
                name=name, 
                product_code=product_code if product_code else None,
                category=category, 
                unit_price=unit_price,
                stock_quantity=int(stock_quantity),
                low_stock_threshold=int(low_stock_threshold),
                expiry_date=expiry_date if expiry_date else None,
                expiry_alert_days=int(expiry_alert_days),
                image=image if image else None  # Add image
            )
            
            # Create initial stock adjustment record
            if int(stock_quantity) > 0:
                StockAdjustment.objects.create(
                    product=product,
                    adjustment_type='restock',
                    quantity_change=int(stock_quantity),
                    previous_quantity=0,
                    new_quantity=int(stock_quantity),
                    reason='Initial stock'
                )
            
            messages.success(request, 'Product created successfully!')
            return redirect('product_list')
        except Exception as e:
            messages.error(request, f'Error creating product: {str(e)}')
    
    categories = Category.objects.all()
    return render(request, 'pos/product_form.html', {'categories': categories})



@login_required
def product_edit(request, pk):
    """Edit existing product"""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product.name = request.POST.get('name')
        product.product_code = request.POST.get('product_code') if request.POST.get('product_code') else None
        category_id = request.POST.get('category')
        product.category = Category.objects.get(id=category_id) if category_id else None
        product.unit_price = request.POST.get('unit_price')
        product.low_stock_threshold = int(request.POST.get('low_stock_threshold', 10))
        expiry_date = request.POST.get('expiry_date')
        product.expiry_date = expiry_date if expiry_date else None
        product.expiry_alert_days = int(request.POST.get('expiry_alert_days', 3))
        
        # Handle image upload
        image = request.FILES.get('image')
        if image:
            product.image = image
        
        # Handle image removal
        remove_image = request.POST.get('remove_image')
        if remove_image == 'true':
            product.image = None
        
        product.save()
        messages.success(request, 'Product updated successfully!')
        return redirect('product_list')
    
    categories = Category.objects.all()
    return render(request, 'pos/product_form.html', {'product': product, 'categories': categories})


@login_required
def product_delete(request, pk):
    """Delete product"""
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
        messages.success(request, 'Product deleted successfully!')
        return redirect('product_list')
    return render(request, 'pos/product_confirm_delete.html', {'product': product})


@login_required
def category_list(request):
    """List all categories"""
    categories = Category.objects.all()
    return render(request, 'pos/category_list.html', {'categories': categories})


@login_required
def category_create(request):
    """Create new category"""
    if request.method == 'POST':
        name = request.POST.get('name')
        try:
            Category.objects.create(name=name)
            messages.success(request, 'Category created successfully!')
            return redirect('category_list')
        except Exception as e:
            messages.error(request, f'Error creating category: {str(e)}')
    return render(request, 'pos/category_form.html')


@login_required
def pos_screen(request):
    """Main POS sales screen"""
    products = Product.objects.select_related('category').all()
    categories = Category.objects.all()
    customers = Customer.objects.filter(is_active=True).order_by('name')
    vat_rate = getattr(settings, 'VAT_RATE', 16)
    
    context = {
        'products': products,
        'categories': categories,
        'customers': customers,
        'vat_rate': vat_rate,
    }
    return render(request, 'pos/pos_screen.html', context)


@login_required
def complete_sale(request):
    """Process and complete a sale"""
    if request.method == 'POST':
        try:
            # Get sale data
            items_data = request.POST.getlist('items')
            customer_id = request.POST.get('customer_id')
            discount_type = request.POST.get('discount_type', 'percentage')
            discount_value = Decimal(request.POST.get('discount_value', 0))
            vat_rate = Decimal(getattr(settings, 'VAT_RATE', 16))
            
            if not items_data:
                messages.error(request, 'No items in cart!')
                return redirect('pos_screen')
            
            # Get customer if selected
            customer = None
            if customer_id:
                try:
                    customer = Customer.objects.get(id=customer_id)
                except Customer.DoesNotExist:
                    pass
            
            # Calculate totals and check stock
            subtotal = Decimal(0)
            sale_items = []
            
            for item_str in items_data:
                product_id, quantity, price = item_str.split(',')
                product = Product.objects.get(id=product_id)
                quantity = int(quantity)
                unit_price = Decimal(price)
                total_price = unit_price * quantity
                
                # Check stock availability
                if not product.has_sufficient_stock(quantity):
                    messages.error(request, f'Insufficient stock for {product.name}. Available: {product.stock_quantity}')
                    return redirect('pos_screen')
                
                subtotal += total_price
                sale_items.append({
                    'product': product,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'total_price': total_price
                })
            
            # Calculate discount
            if discount_type == 'percentage':
                discount_amount = (subtotal * discount_value) / 100
            else:
                discount_amount = discount_value
            
            # Calculate VAT on discounted amount
            amount_after_discount = subtotal - discount_amount
            vat_amount = (amount_after_discount * vat_rate) / 100
            total = amount_after_discount + vat_amount
            
            # Create sale
            sale = Sale.objects.create(
                cashier=request.user,
                customer=customer,
                subtotal=subtotal,
                vat_rate=vat_rate,
                vat_amount=vat_amount,
                discount_type=discount_type,
                discount_value=discount_value,
                discount_amount=discount_amount,
                total=total
            )
            
            # Create sale items and deduct stock
            for item in sale_items:
                SaleItem.objects.create(
                    sale=sale,
                    product=item['product'],
                    quantity=item['quantity'],
                    unit_price=item['unit_price']
                )
                
                # Deduct stock and create adjustment record
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
            
            # Award loyalty points if customer is selected
            if customer:
                points_earned = customer.add_loyalty_points(total, sale=sale, description=f"Purchase - {sale.invoice_number}")
                customer.total_purchases += total
                customer.visit_count += 1
                customer.save()
                
                messages.success(request, f'Sale completed! Invoice: {sale.invoice_number}. Customer earned {points_earned} loyalty points!')
            else:
                messages.success(request, f'Sale completed! Invoice: {sale.invoice_number}')
            
            return redirect('invoice_view', pk=sale.pk)
            
        except Exception as e:
            messages.error(request, f'Error completing sale: {str(e)}')
            return redirect('pos_screen')
    
    return redirect('pos_screen')


@login_required
def invoice_view(request, pk):
    """View invoice details"""
    sale = get_object_or_404(Sale, pk=pk)
    shop_name = getattr(settings, 'SHOP_NAME', 'My Retail Shop')
    return render(request, 'pos/invoice.html', {'sale': sale, 'shop_name': shop_name})


@login_required
def invoice_pdf(request, pk):
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
    data.append(['', '', 'Subtotal:', f'KES {sale.subtotal:,.2f}'])
    if sale.discount_amount > 0:
        data.append(['', '', f'Discount ({sale.discount_value}{"%" if sale.discount_type == "percentage" else ""}):', f'KES {sale.discount_amount:,.2f}'])
    data.append(['', '', f'VAT ({sale.vat_rate}%):', f'KES {sale.vat_amount:,.2f}'])
    data.append(['', '', '<b>TOTAL:</b>', f'<b>KES {sale.total:,.2f}</b>'])
    
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
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph("Thank you for your business!", styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{sale.invoice_number}.pdf"'
    return response


@login_required
def sales_report(request):
    """Daily sales report"""
    # Get date filter
    date_str = request.GET.get('date')
    if date_str:
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            filter_date = datetime.now().date()
    else:
        filter_date = datetime.now().date()
    
    # Get sales for the date
    sales = Sale.objects.filter(date__date=filter_date).prefetch_related('items')
    
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


@login_required
def search_product_by_code(request):
    """API endpoint to search product by barcode/product code"""
    code = request.GET.get('code', '').strip()
    
    if not code:
        return JsonResponse({'error': 'No code provided'}, status=400)
    
    try:
        product = Product.objects.get(product_code=code)
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'product_code': product.product_code,
                'price': float(product.unit_price),
                'category': product.category.name if product.category else None,
                'stock_quantity': product.stock_quantity,
                'in_stock': not product.is_out_of_stock()
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


@login_required
def stock_list(request):
    """View all products with stock information"""
    # Filter options
    status_filter = request.GET.get('status', 'all')
    
    products = Product.objects.select_related('category').all()
    
    if status_filter == 'low':
        products = products.filter(stock_quantity__lte=models.F('low_stock_threshold'))
    elif status_filter == 'out':
        products = products.filter(stock_quantity=0)
    
    context = {
        'products': products,
        'status_filter': status_filter,
    }
    return render(request, 'pos/stock_list.html', context)


@login_required
def stock_adjust(request, pk):
    """Adjust stock for a product"""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        adjustment_type = request.POST.get('adjustment_type')
        quantity_change = int(request.POST.get('quantity_change', 0))
        reason = request.POST.get('reason', '')
        
        if quantity_change == 0:
            messages.error(request, 'Quantity change cannot be zero!')
            return redirect('stock_adjust', pk=pk)
        
        try:
            previous_qty = product.stock_quantity
            
            if quantity_change > 0:
                product.add_stock(quantity_change)
            else:
                if not product.has_sufficient_stock(abs(quantity_change)):
                    messages.error(request, 'Cannot deduct more than available stock!')
                    return redirect('stock_adjust', pk=pk)
                product.deduct_stock(abs(quantity_change))
            
            # Create adjustment record
            StockAdjustment.objects.create(
                product=product,
                adjustment_type=adjustment_type,
                quantity_change=quantity_change,
                previous_quantity=previous_qty,
                new_quantity=product.stock_quantity,
                reason=reason
            )
            
            messages.success(request, f'Stock adjusted successfully! New quantity: {product.stock_quantity}')
            return redirect('stock_list')
            
        except Exception as e:
            messages.error(request, f'Error adjusting stock: {str(e)}')
    
    return render(request, 'pos/stock_adjust.html', {'product': product})


@login_required
def stock_history(request, pk):
    """View stock adjustment history for a product"""
    product = get_object_or_404(Product, pk=pk)
    adjustments = product.stock_adjustments.all()
    
    context = {
        'product': product,
        'adjustments': adjustments,
    }
    return render(request, 'pos/stock_history.html', context)


@login_required
def low_stock_alert(request):
    """View products with low or out of stock"""
    low_stock = Product.objects.filter(
        stock_quantity__lte=models.F('low_stock_threshold'),
        stock_quantity__gt=0
    ).select_related('category')
    
    out_of_stock = Product.objects.filter(stock_quantity=0).select_related('category')
    
    context = {
        'low_stock_products': low_stock,
        'out_of_stock_products': out_of_stock,
    }
    return render(request, 'pos/low_stock_alert.html', context)


# ==================== SUPPLIER MANAGEMENT ====================

@login_required
def supplier_list(request):
    """List all suppliers"""
    suppliers = Supplier.objects.all()
    
    # Add purchase statistics for each supplier
    for supplier in suppliers:
        supplier.total_purchases_amount = supplier.total_purchases()
        supplier.purchases_count = supplier.purchase_count()
    
    context = {
        'suppliers': suppliers,
    }
    return render(request, 'pos/supplier_list.html', context)


@login_required
def supplier_create(request):
    """Create a new supplier"""
    if request.method == 'POST':
        name = request.POST.get('name')
        contact_person = request.POST.get('contact_person', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')
        notes = request.POST.get('notes', '')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Supplier name is required!')
            return redirect('supplier_create')
        
        Supplier.objects.create(
            name=name,
            contact_person=contact_person,
            email=email,
            phone=phone,
            address=address,
            notes=notes,
            is_active=is_active
        )
        
        messages.success(request, f'Supplier "{name}" created successfully!')
        return redirect('supplier_list')
    
    return render(request, 'pos/supplier_form.html')


@login_required
def supplier_edit(request, pk):
    """Edit an existing supplier"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        supplier.name = request.POST.get('name')
        supplier.contact_person = request.POST.get('contact_person', '')
        supplier.email = request.POST.get('email', '')
        supplier.phone = request.POST.get('phone', '')
        supplier.address = request.POST.get('address', '')
        supplier.notes = request.POST.get('notes', '')
        supplier.is_active = request.POST.get('is_active') == 'on'
        
        if not supplier.name:
            messages.error(request, 'Supplier name is required!')
            return redirect('supplier_edit', pk=pk)
        
        supplier.save()
        messages.success(request, f'Supplier "{supplier.name}" updated successfully!')
        return redirect('supplier_list')
    
    context = {
        'supplier': supplier,
    }
    return render(request, 'pos/supplier_form.html', context)


@login_required
def supplier_delete(request, pk):
    """Delete a supplier"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        name = supplier.name
        supplier.delete()
        messages.success(request, f'Supplier "{name}" deleted successfully!')
        return redirect('supplier_list')
    
    context = {
        'supplier': supplier,
    }
    return render(request, 'pos/supplier_confirm_delete.html', context)


# ==================== PURCHASE MANAGEMENT ====================

@login_required
def purchase_list(request):
    """List all purchases"""
    purchases = Purchase.objects.select_related('supplier').all()
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        purchases = purchases.filter(status=status_filter)
    
    context = {
        'purchases': purchases,
        'status_filter': status_filter,
    }
    return render(request, 'pos/purchase_list.html', context)


@login_required
def purchase_create(request):
    """Create a new purchase order"""
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        expected_delivery = request.POST.get('expected_delivery')
        notes = request.POST.get('notes', '')
        
        # Get product items from POST data
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')
        unit_costs = request.POST.getlist('unit_cost[]')
        
        if not supplier_id:
            messages.error(request, 'Please select a supplier!')
            return redirect('purchase_create')
        
        if not product_ids or not any(product_ids):
            messages.error(request, 'Please add at least one product!')
            return redirect('purchase_create')
        
        # Create purchase
        supplier = get_object_or_404(Supplier, pk=supplier_id)
        purchase = Purchase.objects.create(
            supplier=supplier,
            expected_delivery=expected_delivery if expected_delivery else None,
            notes=notes,
            status='pending'
        )
        
        # Add purchase items and calculate totals
        subtotal = Decimal('0.00')
        for i, product_id in enumerate(product_ids):
            if product_id and quantities[i] and unit_costs[i]:
                product = get_object_or_404(Product, pk=product_id)
                quantity = int(quantities[i])
                unit_cost = Decimal(unit_costs[i])
                
                PurchaseItem.objects.create(
                    purchase=purchase,
                    product=product,
                    quantity=quantity,
                    unit_cost=unit_cost
                )
                
                subtotal += quantity * unit_cost
        
        # Update purchase totals
        purchase.subtotal = subtotal
        purchase.tax_amount = Decimal('0.00')  # Can be customized
        purchase.total_amount = subtotal + purchase.tax_amount
        purchase.save()
        
        messages.success(request, f'Purchase order {purchase.purchase_number} created successfully!')
        return redirect('purchase_detail', pk=purchase.pk)
    
    # GET request
    suppliers = Supplier.objects.filter(is_active=True)
    products = Product.objects.select_related('category').all()
    
    context = {
        'suppliers': suppliers,
        'products': products,
    }
    return render(request, 'pos/purchase_form.html', context)


@login_required
def purchase_detail(request, pk):
    """View purchase order details"""
    purchase = get_object_or_404(Purchase, pk=pk)
    items = purchase.items.select_related('product').all()
    
    context = {
        'purchase': purchase,
        'items': items,
    }
    return render(request, 'pos/purchase_detail.html', context)


@login_required
def purchase_receive(request, pk):
    """Mark purchase as received and update stock"""
    purchase = get_object_or_404(Purchase, pk=pk)
    
    if request.method == 'POST':
        if purchase.status == 'received':
            messages.warning(request, 'This purchase has already been received!')
        else:
            success = purchase.mark_as_received()
            if success:
                messages.success(request, f'Purchase {purchase.purchase_number} marked as received! Stock updated.')
            else:
                messages.error(request, 'Failed to mark purchase as received!')
        
        return redirect('purchase_detail', pk=pk)
    
    context = {
        'purchase': purchase,
    }
    return render(request, 'pos/purchase_receive_confirm.html', context)


@login_required
def purchase_cancel(request, pk):
    """Cancel a purchase order"""
    purchase = get_object_or_404(Purchase, pk=pk)
    
    if request.method == 'POST':
        if purchase.status == 'received':
            messages.error(request, 'Cannot cancel a received purchase!')
        else:
            purchase.status = 'cancelled'
            purchase.save()
            messages.success(request, f'Purchase {purchase.purchase_number} cancelled!')
        
        return redirect('purchase_detail', pk=pk)
    
    context = {
        'purchase': purchase,
    }
    return render(request, 'pos/purchase_cancel_confirm.html', context)



# ==================== EXPIRY MANAGEMENT ====================

@login_required
def expiry_alert(request):
    """View products that are expired or expiring soon"""
    from django.utils import timezone
    from datetime import timedelta
    
    today = timezone.now().date()
    
    # Get expired products
    expired_products = Product.objects.filter(
        expiry_date__lt=today,
        stock_quantity__gt=0
    ).select_related('category')
    
    # Get expiring soon products
    expiring_soon = []
    products_with_expiry = Product.objects.filter(
        expiry_date__gte=today,
        stock_quantity__gt=0
    ).select_related('category')
    
    for product in products_with_expiry:
        if product.is_expiring_soon():
            expiring_soon.append(product)
    
    context = {
        'expired_products': expired_products,
        'expiring_soon_products': expiring_soon,
    }
    return render(request, 'pos/expiry_alert.html', context)



@login_required
def update_expiry(request, pk):
    """Update product expiry date"""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        expiry_date_str = request.POST.get('expiry_date')
        expiry_alert_days = request.POST.get('expiry_alert_days', 3)
        
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
                return redirect('update_expiry', pk=pk)
        
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
        
        return redirect('stock_list')
    
    context = {
        'product': product,
    }
    return render(request, 'pos/update_expiry.html', context)



# ==================== AUTHENTICATION ====================

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required

def login_view(request):
    """User login"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            
            # Log login activity
            ActivityLog.log_activity(
                user=user,
                action_type='login',
                description=f'User logged in: {username}',
                request=request
            )
            
            next_url = request.GET.get('next', 'dashboard')
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password')
    
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



# ==================== CASHIER REPORTS ====================

@login_required
@manager_required
def cashier_report(request):
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
    
    # Get all users who have made sales
    cashiers = User.objects.filter(sales__isnull=False).distinct()
    
    cashier_stats = []
    for cashier in cashiers:
        # Get sales for this cashier on the selected date
        sales = Sale.objects.filter(
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
    
    # Overall totals
    all_sales = Sale.objects.filter(date__date=filter_date)
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
@manager_required
def user_list(request):
    """List all users"""
    users = User.objects.prefetch_related('groups', 'profile').all()
    
    # Add statistics for each user
    for user in users:
        user.total_sales = Sale.objects.filter(cashier=user).count()
        user.total_revenue = Sale.objects.filter(cashier=user).aggregate(
            total=Sum('total')
        )['total'] or 0
    
    context = {
        'users': users,
    }
    return render(request, 'pos/user_list.html', context)


@login_required
@manager_required
def user_create(request):
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
def user_edit(request, pk):
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
def user_delete(request, pk):
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
def user_profile(request):
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
                return redirect('user_profile')
            
            if not user.check_password(current_password):
                messages.error(request, 'Current password is incorrect!')
                return redirect('user_profile')
            
            password_confirm = request.POST.get('password_confirm')
            if new_password != password_confirm:
                messages.error(request, 'New passwords do not match!')
                return redirect('user_profile')
            
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
            
            return redirect('user_profile')
            
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
@manager_required
def business_settings(request):
    """View and edit business settings"""
    settings = BusinessSettings.get_settings()
    
    if request.method == 'POST':
        # Business Information
        settings.business_name = request.POST.get('business_name', 'My Retail Shop')
        settings.business_address = request.POST.get('business_address', '')
        settings.business_phone = request.POST.get('business_phone', '')
        settings.business_email = request.POST.get('business_email', '')
        settings.business_website = request.POST.get('business_website', '')
        settings.tax_id = request.POST.get('tax_id', '')
        
        # Tax Settings
        settings.vat_rate = Decimal(request.POST.get('vat_rate', 16))
        settings.vat_enabled = request.POST.get('vat_enabled') == 'on'
        
        # Receipt Settings
        settings.receipt_header = request.POST.get('receipt_header', '')
        settings.receipt_footer = request.POST.get('receipt_footer', '')
        settings.show_logo_on_receipt = request.POST.get('show_logo_on_receipt') == 'on'
        
        # Currency Settings
        settings.currency_symbol = request.POST.get('currency_symbol', 'KES')
        settings.currency_position = request.POST.get('currency_position', 'before')
        
        # Low Stock Settings
        settings.default_low_stock_threshold = int(request.POST.get('default_low_stock_threshold', 10))
        settings.enable_low_stock_alerts = request.POST.get('enable_low_stock_alerts') == 'on'
        
        # Expiry Settings
        settings.default_expiry_alert_days = int(request.POST.get('default_expiry_alert_days', 3))
        settings.enable_expiry_alerts = request.POST.get('enable_expiry_alerts') == 'on'
        
        # System Settings
        settings.allow_negative_stock = request.POST.get('allow_negative_stock') == 'on'
        settings.require_product_code = request.POST.get('require_product_code') == 'on'
        settings.auto_generate_product_code = request.POST.get('auto_generate_product_code') == 'on'
        
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
            return redirect('business_settings')
            
        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')
    
    context = {
        'settings': settings,
    }
    return render(request, 'pos/business_settings.html', context)


# ==================== ACTIVITY LOG ====================

@login_required
@manager_required
def activity_log(request):
    """View system activity logs"""
    logs = ActivityLog.objects.select_related('user').all()
    
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
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)  # Show 50 logs per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get all users for filter
    users = User.objects.all()
    
    context = {
        'page_obj': page_obj,
        'users': users,
        'user_filter': user_filter,
        'action_filter': action_filter,
        'date_filter': date_filter,
        'action_types': ActivityLog.ACTION_TYPES,
    }
    return render(request, 'pos/activity_log.html', context)



# ==================== CUSTOMER MANAGEMENT ====================

from .models import Customer

@login_required
def customer_list(request):
    """List all customers"""
    customers = Customer.objects.all()
    
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
    }
    return render(request, 'pos/customer_list.html', context)


@login_required
def customer_create(request):
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
        
        try:
            customer = Customer.objects.create(
                name=name,
                phone=phone,
                email=email,
                address=address,
                date_of_birth=date_of_birth if date_of_birth else None,
                customer_type=customer_type,
                is_active=is_active,
                notes=notes
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
            return redirect('customer_detail', pk=customer.pk)
            
        except Exception as e:
            messages.error(request, f'Error creating customer: {str(e)}')
    
    return render(request, 'pos/customer_form.html')


@login_required
def customer_edit(request, pk):
    """Edit existing customer"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        customer.name = request.POST.get('name')
        customer.phone = request.POST.get('phone')
        customer.email = request.POST.get('email', '')
        customer.address = request.POST.get('address', '')
        date_of_birth = request.POST.get('date_of_birth', '')
        customer.date_of_birth = date_of_birth if date_of_birth else None
        customer.customer_type = request.POST.get('customer_type', 'regular')
        customer.is_active = request.POST.get('is_active') == 'on'
        customer.notes = request.POST.get('notes', '')
        
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
            return redirect('customer_detail', pk=customer.pk)
            
        except Exception as e:
            messages.error(request, f'Error updating customer: {str(e)}')
    
    context = {
        'customer': customer,
    }
    return render(request, 'pos/customer_form.html', context)


@login_required
def customer_detail(request, pk):
    """View customer details and purchase history"""
    customer = get_object_or_404(Customer, pk=pk)
    purchases = Sale.objects.filter(customer=customer).order_by('-date')[:20]
    
    context = {
        'customer': customer,
        'purchases': purchases,
    }
    return render(request, 'pos/customer_detail.html', context)



# ==================== WRITE-OFF REPORT ====================

@login_required
def writeoff_report(request):
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
    
    # Get all damage/loss adjustments
    writeoffs = StockAdjustment.objects.filter(
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
