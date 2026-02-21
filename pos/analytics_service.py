"""
Advanced Analytics Service for POS System
Provides business intelligence and insights
"""
from django.db.models import Sum, Count, Avg, F, Q, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
from .models import Sale, SaleItem, Product, Customer, Purchase, StockAdjustment


class AnalyticsService:
    """Service for generating business analytics and insights"""
    
    def __init__(self, business):
        self.business = business
    
    # ==================== SALES ANALYTICS ====================
    
    def get_sales_trends(self, days=30):
        """Get daily sales trends for the last N days"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Get sales data
        sales = Sale.objects.filter(
            business=self.business,
            date__gte=start_date
        ).annotate(
            day=TruncDate('date')
        ).values('day').annotate(
            total_sales=Sum('total'),
            transaction_count=Count('id'),
            items_sold=Sum('items__quantity')
        ).order_by('day')
        
        sales_list = list(sales)
        
        # Calculate profit separately from SaleItems
        profit_by_day = {}
        sale_items = SaleItem.objects.filter(
            sale__business=self.business,
            sale__date__gte=start_date
        ).annotate(
            day=TruncDate('sale__date')
        ).values('day').annotate(
            total_profit=Sum(
                ExpressionWrapper(
                    F('quantity') * (F('unit_price') - F('product__cost_price')),
                    output_field=DecimalField()
                )
            )
        )
        
        for item in sale_items:
            profit_by_day[item['day']] = float(item['total_profit'] or 0)
        
        # Format for Chart.js
        return {
            'dates': [s['day'].strftime('%Y-%m-%d') for s in sales_list],
            'totals': [float(s['total_sales'] or 0) for s in sales_list],
            'profits': [profit_by_day.get(s['day'], 0) for s in sales_list],
            'transactions': [s['transaction_count'] for s in sales_list],
            'items': [float(s['items_sold'] or 0) for s in sales_list]
        }
    
    def get_hourly_sales_pattern(self, days=7):
        """Analyze sales by hour to identify peak times"""
        from django.db.models.functions import ExtractHour
        
        start_date = timezone.now() - timedelta(days=days)
        
        hourly_sales = Sale.objects.filter(
            business=self.business,
            date__gte=start_date
        ).annotate(
            hour=ExtractHour('date')
        ).values('hour').annotate(
            total_sales=Sum('total'),
            transaction_count=Count('id'),
            avg_transaction=Avg('total')
        ).order_by('hour')
        
        hourly_list = list(hourly_sales)
        
        # Format for Chart.js
        return {
            'hours': [f"{h['hour']:02d}:00" for h in hourly_list],
            'totals': [float(h['total_sales'] or 0) for h in hourly_list],
            'transactions': [h['transaction_count'] for h in hourly_list],
            'averages': [float(h['avg_transaction'] or 0) for h in hourly_list]
        }
    
    def get_sales_by_category(self, start_date=None, end_date=None):
        """Get sales breakdown by product category"""
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()
        
        category_sales = SaleItem.objects.filter(
            sale__business=self.business,
            sale__date__gte=start_date,
            sale__date__lte=end_date
        ).values(
            'product__category__name'
        ).annotate(
            total_revenue=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price'),
                    output_field=DecimalField()
                )
            ),
            total_cost=Sum(
                ExpressionWrapper(
                    F('quantity') * F('product__cost_price'),
                    output_field=DecimalField()
                )
            ),
            total_profit=Sum(
                ExpressionWrapper(
                    F('quantity') * (F('unit_price') - F('product__cost_price')),
                    output_field=DecimalField()
                )
            ),
            units_sold=Sum('quantity'),
            transaction_count=Count('sale', distinct=True)
        ).order_by('-total_revenue')
        
        return list(category_sales)
    
    def get_profit_margin_analysis(self, start_date=None, end_date=None):
        """Analyze profit margins across products"""
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()
        
        profit_analysis = SaleItem.objects.filter(
            sale__business=self.business,
            sale__date__gte=start_date,
            sale__date__lte=end_date
        ).aggregate(
            total_revenue=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price'),
                    output_field=DecimalField()
                )
            ),
            total_cost=Sum(
                ExpressionWrapper(
                    F('quantity') * F('product__cost_price'),
                    output_field=DecimalField()
                )
            ),
            total_profit=Sum(
                ExpressionWrapper(
                    F('quantity') * (F('unit_price') - F('product__cost_price')),
                    output_field=DecimalField()
                )
            )
        )
        
        if profit_analysis['total_revenue']:
            profit_analysis['profit_margin'] = (
                (profit_analysis['total_profit'] / profit_analysis['total_revenue']) * 100
            )
        else:
            profit_analysis['profit_margin'] = 0
        
        return profit_analysis
    
    # ==================== PRODUCT ANALYTICS ====================
    
    def get_best_sellers(self, limit=10, days=30):
        """Get top selling products"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        best_sellers = SaleItem.objects.filter(
            sale__business=self.business,
            sale__date__gte=start_date
        ).values(
            'product__id',
            'product__name',
            'product__category__name'
        ).annotate(
            units_sold=Sum('quantity'),
            total_revenue=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price'),
                    output_field=DecimalField()
                )
            ),
            total_profit=Sum(
                ExpressionWrapper(
                    F('quantity') * (F('unit_price') - F('product__cost_price')),
                    output_field=DecimalField()
                )
            ),
            transaction_count=Count('sale', distinct=True)
        ).order_by('-units_sold')[:limit]
        
        # Format for template
        return [{
            'id': item['product__id'],
            'name': item['product__name'],
            'category': item['product__category__name'] or 'Uncategorized',
            'units_sold': float(item['units_sold'] or 0),
            'revenue': float(item['total_revenue'] or 0),
            'profit': float(item['total_profit'] or 0),
            'transactions': item['transaction_count']
        } for item in best_sellers]
    
    def get_slow_moving_items(self, limit=10, days=30):
        """Identify slow-moving inventory"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Get products with stock but low sales
        slow_movers = Product.objects.filter(
            business=self.business,
            stock_quantity__gt=0
        ).annotate(
            units_sold=Sum(
                'saleitem__quantity',
                filter=Q(
                    saleitem__sale__date__gte=start_date
                )
            )
        ).annotate(
            units_sold_clean=Count('saleitem', filter=Q(
                saleitem__sale__date__gte=start_date
            ))
        ).filter(
            units_sold_clean__lte=5  # Sold 5 or fewer times
        ).values(
            'id', 'name', 'category__name', 'stock_quantity', 'unit_price'
        ).annotate(
            total_sold=Sum(
                'saleitem__quantity',
                filter=Q(
                    saleitem__sale__date__gte=start_date
                )
            )
        ).order_by('total_sold')[:limit]
        
        # Format for template
        return [{
            'id': item['id'],
            'name': item['name'],
            'category': item['category__name'],
            'stock': float(item['stock_quantity'] or 0),
            'units_sold': float(item['total_sold'] or 0),
            'unit_price': float(item['unit_price'] or 0),
            'days_since_sale': None  # Would need last sale date tracking
        } for item in slow_movers]
    
    def get_stock_turnover_rate(self, days=30):
        """Calculate inventory turnover rate"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Total cost of goods sold
        cogs = SaleItem.objects.filter(
            sale__business=self.business,
            sale__date__gte=start_date
        ).aggregate(
            total_cogs=Sum(F('quantity') * F('product__cost_price'))
        )['total_cogs'] or Decimal('0')
        
        # Average inventory value
        avg_inventory = Product.objects.filter(
            business=self.business
        ).aggregate(
            total_value=Sum(F('stock_quantity') * F('cost_price'))
        )['total_value'] or Decimal('1')
        
        # Turnover rate = COGS / Average Inventory
        if avg_inventory > 0:
            turnover_rate = float(cogs / avg_inventory)
        else:
            turnover_rate = 0
        
        return {
            'turnover_rate': round(turnover_rate, 2),
            'cogs': float(cogs),
            'avg_stock_value': float(avg_inventory),
            'days_to_sell': round(days / turnover_rate, 1) if turnover_rate > 0 else 0
        }
    
    def get_abc_analysis(self):
        """ABC Analysis: Classify products by revenue contribution"""
        # Get all products with their revenue
        products = SaleItem.objects.filter(
            sale__business=self.business
        ).values(
            'product__id',
            'product__name'
        ).annotate(
            total_revenue=Sum(F('quantity') * F('unit_price'))
        ).order_by('-total_revenue')
        
        products_list = list(products)
        total_revenue = sum(p['total_revenue'] for p in products_list if p['total_revenue'])
        
        if total_revenue == 0 or not products_list:
            return {
                'a_count': 0,
                'b_count': 0,
                'c_count': 0,
                'a_percentage': 0,
                'b_percentage': 0,
                'c_percentage': 0,
                'A': [],
                'B': [],
                'C': []
            }
        
        # Calculate cumulative percentage
        cumulative = 0
        abc_classification = {'A': [], 'B': [], 'C': []}
        
        for product in products_list:
            revenue = product['total_revenue'] or 0
            percentage = (revenue / total_revenue) * 100
            cumulative += percentage
            
            product['revenue_percentage'] = round(percentage, 2)
            product['cumulative_percentage'] = round(cumulative, 2)
            
            # A items: Top 80% of revenue (usually 20% of products)
            if cumulative <= 80:
                abc_classification['A'].append(product)
            # B items: Next 15% of revenue
            elif cumulative <= 95:
                abc_classification['B'].append(product)
            # C items: Last 5% of revenue
            else:
                abc_classification['C'].append(product)
        
        # Calculate summary stats
        a_revenue = sum(p['total_revenue'] for p in abc_classification['A'])
        b_revenue = sum(p['total_revenue'] for p in abc_classification['B'])
        c_revenue = sum(p['total_revenue'] for p in abc_classification['C'])
        
        return {
            'a_count': len(abc_classification['A']),
            'b_count': len(abc_classification['B']),
            'c_count': len(abc_classification['C']),
            'a_percentage': round((a_revenue / total_revenue * 100), 1) if total_revenue > 0 else 0,
            'b_percentage': round((b_revenue / total_revenue * 100), 1) if total_revenue > 0 else 0,
            'c_percentage': round((c_revenue / total_revenue * 100), 1) if total_revenue > 0 else 0,
            'A': abc_classification['A'],
            'B': abc_classification['B'],
            'C': abc_classification['C']
        }
    
    # ==================== CUSTOMER ANALYTICS ====================
    
    def get_customer_insights(self, days=90):
        """Get customer behavior insights"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        customer_stats = Customer.objects.filter(
            business=self.business
        ).annotate(
            purchase_count=Count(
                'purchases',
                filter=Q(purchases__date__gte=start_date)
            ),
            amount_spent=Sum(
                'purchases__total',
                filter=Q(purchases__date__gte=start_date)
            ),
            avg_purchase_value=Avg(
                'purchases__total',
                filter=Q(purchases__date__gte=start_date)
            )
        ).filter(
            purchase_count__gt=0
        ).order_by('-amount_spent')
        
        return list(customer_stats.values(
            'id', 'name', 'phone', 'purchase_count', 'amount_spent', 'avg_purchase_value'
        )[:20])
    
    def get_customer_retention_rate(self, days=30):
        """Calculate customer retention rate"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        previous_start = start_date - timedelta(days=days)
        
        # Customers who purchased in previous period
        previous_customers = set(
            Sale.objects.filter(
                business=self.business,
                date__gte=previous_start,
                date__lt=start_date,
                customer__isnull=False
            ).values_list('customer_id', flat=True)
        )
        
        # Customers who purchased in current period
        current_customers = set(
            Sale.objects.filter(
                business=self.business,
                date__gte=start_date,
                date__lte=end_date,
                customer__isnull=False
            ).values_list('customer_id', flat=True)
        )
        
        # Returning customers
        returning = previous_customers.intersection(current_customers)
        
        retention_rate = (len(returning) / len(previous_customers) * 100) if previous_customers else 0
        
        return {
            'retention_rate': round(retention_rate, 2),
            'previous_customers': len(previous_customers),
            'current_customers': len(current_customers),
            'returning_customers': len(returning),
            'new_customers': len(current_customers - previous_customers)
        }
    
    # ==================== FINANCIAL ANALYTICS ====================
    
    def get_payment_method_breakdown(self, days=30):
        """Analyze sales by payment method"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Get payment transactions grouped by method
        from .models import SalePayment
        
        breakdown = SalePayment.objects.filter(
            business=self.business,
            sale__date__gte=start_date
        ).values(
            'payment_method__name'
        ).annotate(
            total_amount=Sum('amount'),
            transaction_count=Count('id')
        ).order_by('-total_amount')
        
        # Format for Chart.js
        return {
            'labels': [item['payment_method__name'] or 'Unknown' for item in breakdown],
            'amounts': [float(item['total_amount'] or 0) for item in breakdown],
            'counts': [item['transaction_count'] for item in breakdown]
        }
    
    def get_revenue_vs_profit_trend(self, days=30):
        """Compare revenue and profit trends"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Get revenue data from Sales
        daily_revenue = Sale.objects.filter(
            business=self.business,
            date__gte=start_date
        ).annotate(
            day=TruncDate('date')
        ).values('day').annotate(
            revenue=Sum('total')
        ).order_by('day')
        
        revenue_dict = {item['day']: float(item['revenue'] or 0) for item in daily_revenue}
        
        # Get cost and profit from SaleItems
        daily_profit = SaleItem.objects.filter(
            sale__business=self.business,
            sale__date__gte=start_date
        ).annotate(
            day=TruncDate('sale__date')
        ).values('day').annotate(
            cost=Sum(
                ExpressionWrapper(
                    F('quantity') * F('product__cost_price'),
                    output_field=DecimalField()
                )
            ),
            profit=Sum(
                ExpressionWrapper(
                    F('quantity') * (F('unit_price') - F('product__cost_price')),
                    output_field=DecimalField()
                )
            )
        ).order_by('day')
        
        profit_dict = {}
        cost_dict = {}
        for item in daily_profit:
            profit_dict[item['day']] = float(item['profit'] or 0)
            cost_dict[item['day']] = float(item['cost'] or 0)
        
        # Get all unique dates
        all_dates = sorted(set(list(revenue_dict.keys()) + list(profit_dict.keys())))
        
        # Format for Chart.js
        return {
            'dates': [d.strftime('%Y-%m-%d') for d in all_dates],
            'revenue': [revenue_dict.get(d, 0) for d in all_dates],
            'profit': [profit_dict.get(d, 0) for d in all_dates],
            'cost': [cost_dict.get(d, 0) for d in all_dates]
        }
    
    # ==================== SUMMARY DASHBOARD ====================
    
    def get_dashboard_summary(self, days=30):
        """Get comprehensive dashboard summary"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Sales summary
        sales_summary = Sale.objects.filter(
            business=self.business,
            date__gte=start_date
        ).aggregate(
            total_revenue=Sum('total'),
            total_transactions=Count('id'),
            avg_transaction=Avg('total')
        )
        
        # Profit calculation from SaleItems
        profit_data = SaleItem.objects.filter(
            sale__business=self.business,
            sale__date__gte=start_date
        ).aggregate(
            total_profit=Sum(
                ExpressionWrapper(
                    F('quantity') * (F('unit_price') - F('product__cost_price')),
                    output_field=DecimalField()
                )
            )
        )
        
        # Customer metrics
        customer_metrics = {
            'total_customers': Customer.objects.filter(business=self.business).count(),
            'active_customers': Sale.objects.filter(
                business=self.business,
                date__gte=start_date,
                customer__isnull=False
            ).values('customer').distinct().count()
        }
        
        # Inventory metrics
        inventory_metrics = Product.objects.filter(
            business=self.business
        ).aggregate(
            total_products=Count('id'),
            total_stock_value=Sum(
                ExpressionWrapper(
                    F('stock_quantity') * F('cost_price'),
                    output_field=DecimalField()
                )
            ),
            low_stock_count=Count('id', filter=Q(stock_quantity__lte=F('low_stock_threshold')))
        )
        
        return {
            'sales': sales_summary,
            'profit': profit_data,
            'customers': customer_metrics,
            'inventory': inventory_metrics,
            'period_days': days
        }
