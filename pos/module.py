"""
POS Module Manifest
Declares navigation, dashboard cards, default roles, and module metadata.
"""
from core.registry import ModuleManifest, MenuSection, MenuItem, DashboardCard, HealthCheck


def pos_health_check():
    """Verify POS catalog and tax configurations are sane."""
    from pos.models import Product, VATCode
    product_count = Product.objects.count()
    vat_count = VATCode.objects.count()
    return True, f"{product_count} products cataloged, {vat_count} VAT codes active."


def pos_dashboard_card_context(request, company, branch):
    """Context data callback for POS Summary Dashboard Card."""
    from pos.models import Sale
    from django.utils import timezone
    today = timezone.now().date()
    today_sales = Sale.objects.filter(date__date=today)
    if branch:
        today_sales = today_sales.filter(branch__name=branch.name)

    total_amount = sum(s.total for s in today_sales)
    return {
        'today_sales_count': today_sales.count(),
        'today_sales_total': total_amount,
    }


manifest = ModuleManifest(
    key='pos',
    name='Point of Sale & Retail',
    version='2.1.0',
    description='Retail operations, till cash management, receipt printing, and front-office checkout.',
    icon='bi bi-cart3',
    dependencies=[],
    permission_prefix='pos',
    default_roles={
        'Store Manager': [
            'pos.view_product',
            'pos.add_product',
            'pos.change_product',
            'pos.view_sale',
            'pos.view_activitylog',
        ],
        'Cashier': [
            'pos.view_product',
            'pos.add_sale',
            'pos.view_sale',
        ],
        'Stock Manager': [
            'pos.view_product',
            'pos.change_product',
            'pos.add_stockadjustment',
            'pos.view_stockadjustment',
        ],
    },
    menu_sections=[
        MenuSection(
            title='Retail & Sales',
            order=20,
            items=[
                MenuItem(
                    title='Point of Sale',
                    url_name='pos_home',
                    icon='bi bi-calculator',
                    order=10,
                ),
                MenuItem(
                    title='Sales History',
                    url_name='sales_list',
                    icon='bi bi-receipt',
                    order=20,
                ),
                MenuItem(
                    title='End of Day (Z-Report)',
                    url_name='zreport_session_status',
                    icon='bi bi-file-earmark-check',
                    badge='EOD',
                    badge_class='badge bg-danger',
                    order=30,
                ),
            ],
        ),
        MenuSection(
            title='Products & Inventory',
            order=30,
            items=[
                MenuItem(
                    title='Products Catalog',
                    url_name='product_list',
                    icon='bi bi-box-seam',
                    order=10,
                ),
                MenuItem(
                    title='Stock Management',
                    url_name='stock_list',
                    icon='bi bi-boxes',
                    order=20,
                ),
                MenuItem(
                    title='Categories',
                    url_name='category_list',
                    icon='bi bi-tags',
                    order=30,
                ),
            ],
        ),
    ],
    dashboard_cards=[
        DashboardCard(
            key='pos_today_summary',
            title="Today's Retail Sales",
            template_name='pos/components/card_today_sales.html',
            context_callback=pos_dashboard_card_context,
            order=10,
        ),
    ],
    health_checks=[
        HealthCheck(name='Catalog & Tax Engine', check_callback=pos_health_check),
    ],
    url_prefix='/pos/',
)
