from django import template

from reading.markdown_utils import render_markdown

register = template.Library()


@register.filter
def markdownify(value):
    return render_markdown(value or "")
