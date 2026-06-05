"""
Template tags for calculator widget
"""
from django import template

register = template.Library()


@register.inclusion_tag('calculator_widget.html')
def calculator_widget():
    """
    Render the advanced calculator widget.
    Usage: {% load calculator_tags %}
           {% calculator_widget %}
    """
    return {}
