import copy
from django.apps import AppConfig


class PosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pos'

    def ready(self):
        import pos.signals  # noqa: F401 — registers webhook signals
        
        # Transparent single-store URL reversing (ignores legacy slug kwargs if URL pattern doesn't expect it)
        import django.urls.base
        import django.urls.resolvers
        import django.urls.exceptions
        import django.shortcuts

        _orig_reverse_with_prefix = django.urls.resolvers.URLResolver._reverse_with_prefix
        _orig_reverse = django.urls.base.reverse

        def smart_reverse_with_prefix(self, lookup_view, _prefix, *args, **kwargs):
            try:
                return _orig_reverse_with_prefix(self, lookup_view, _prefix, *args, **kwargs)
            except django.urls.exceptions.NoReverseMatch as e:
                if kwargs and 'slug' in kwargs:
                    clean_kwargs = {k: v for k, v in kwargs.items() if k != 'slug'}
                    try:
                        return _orig_reverse_with_prefix(self, lookup_view, _prefix, *args, **clean_kwargs)
                    except django.urls.exceptions.NoReverseMatch:
                        pass
                raise e

        def smart_reverse(viewname, urlconf=None, args=None, kwargs=None, current_app=None):
            try:
                return _orig_reverse(viewname, urlconf=urlconf, args=args, kwargs=kwargs, current_app=current_app)
            except django.urls.exceptions.NoReverseMatch as e:
                if kwargs and 'slug' in kwargs:
                    clean_kwargs = {k: v for k, v in kwargs.items() if k != 'slug'}
                    try:
                        return _orig_reverse(viewname, urlconf=urlconf, args=args, kwargs=clean_kwargs, current_app=current_app)
                    except django.urls.exceptions.NoReverseMatch:
                        pass
                raise e

        django.urls.resolvers.URLResolver._reverse_with_prefix = smart_reverse_with_prefix
        django.urls.base.reverse = smart_reverse
        django.urls.reverse = smart_reverse
        django.shortcuts.reverse = smart_reverse

        # Fix Python 3.14 copy(context) compatibility where copy(super()) fails on super() proxy
        import copy as _py_copy
        import django.template.context

        def _full_context_copy(self):
            duplicate = self.__class__.__new__(self.__class__)
            for k, v in self.__dict__.items():
                if k == 'dicts':
                    duplicate.dicts = self.dicts[:]
                elif k == 'render_context':
                    duplicate.render_context = _py_copy.copy(v)
                else:
                    setattr(duplicate, k, v)
            if hasattr(self, 'render_context') and not hasattr(duplicate, 'render_context'):
                duplicate.render_context = _py_copy.copy(self.render_context)
            return duplicate

        django.template.context.BaseContext.__copy__ = _full_context_copy
        django.template.context.Context.__copy__ = _full_context_copy
        django.template.context.RequestContext.__copy__ = _full_context_copy
