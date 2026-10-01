"""
Dynamic Modular Dashboard Engine
Renders registered dashboard cards with isolated error boundaries.
"""
import logging
from typing import Any, Dict, List
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from core.registry import module_registry, DashboardCard
from core.scoping import get_current_company, get_current_branch

logger = logging.getLogger(__name__)


def get_visible_dashboard_cards(request) -> List[DashboardCard]:
    """Retrieve all dashboard cards accessible to the current user and company."""
    if not request.user.is_authenticated:
        return []

    company = get_current_company(request)
    company_id = company.id if company else None

    cards: List[DashboardCard] = []

    for manifest in module_registry.get_all():
        if not module_registry.is_enabled(manifest.key, company_id):
            continue

        for card in manifest.dashboard_cards:
            if card.permission and not (request.user.is_superuser or request.user.has_perm(card.permission)):
                continue
            cards.append(card)

    return sorted(cards, key=lambda c: c.order)


def render_dashboard_cards(request) -> List[Dict[str, Any]]:
    """
    Render all dashboard cards with isolated error boundaries.
    If one card fails, it renders a safe error notice without breaking the page.
    """
    company = get_current_company(request)
    branch = get_current_branch(request)
    cards = get_visible_dashboard_cards(request)
    rendered_cards = []

    for card in cards:
        card_context = {
            'request': request,
            'company': company,
            'branch': branch,
            'card': card,
        }

        # Isolated error boundary for card data computation
        try:
            if card.context_callback and callable(card.context_callback):
                callback_data = card.context_callback(request, company, branch)
                if isinstance(callback_data, dict):
                    card_context.update(callback_data)

            # Render card template
            html_content = render_to_string(card.template_name, card_context, request=request)
        except Exception as e:
            logger.error("Error rendering dashboard card '%s' (%s): %s", card.key, card.title, e, exc_info=True)
            html_content = f"""
            <div class="{card.width}">
                <div class="card border-left-danger shadow h-100 py-2">
                    <div class="card-body">
                        <div class="text-xs font-weight-bold text-danger text-uppercase mb-1">{card.title}</div>
                        <div class="small text-muted">Temporarily unavailable</div>
                    </div>
                </div>
            </div>
            """

        rendered_cards.append({
            'key': card.key,
            'title': card.title,
            'width': card.width,
            'html': mark_safe(html_content),
        })

    return rendered_cards
