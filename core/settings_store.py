"""
Typed Settings Store Service
Provides hierarchical setting resolution with caching and type safety.
"""
from typing import Any, Dict, Optional
from django.core.cache import cache
from core.models.settings import CoreSetting


class SettingStore:
    """
    Central service for fetching and modifying hierarchical settings.
    Resolution order:
      1. Branch Override (company + branch + module + key)
      2. Company Override (company + module + key)
      3. Global Default (module + key)
      4. Fallback Default passed by caller
    """
    CACHE_TIMEOUT = 3600  # 1 hour

    @classmethod
    def _cache_key(cls, module_key: str, key: str, company_id: Optional[int] = None, branch_id: Optional[int] = None) -> str:
        return f"cset_{company_id or 0}_{branch_id or 0}_{module_key}_{key}"

    @classmethod
    def get(cls, module_key: str, key: str, default: Any = None, company=None, branch=None) -> Any:
        company_id = company.id if hasattr(company, 'id') else company
        branch_id = branch.id if hasattr(branch, 'id') else branch

        cache_k = cls._cache_key(module_key, key, company_id, branch_id)
        cached_val = cache.get(cache_k)
        if cached_val is not None:
            return cached_val

        # 1. Branch level check
        if company_id and branch_id:
            branch_setting = CoreSetting.objects.filter(
                company_id=company_id,
                branch_id=branch_id,
                module_key=module_key,
                key=key,
            ).first()
            if branch_setting:
                val = branch_setting.get_value()
                cache.set(cache_k, val, timeout=cls.CACHE_TIMEOUT)
                return val

        # 2. Company level check
        if company_id:
            company_setting = CoreSetting.objects.filter(
                company_id=company_id,
                branch__isnull=True,
                module_key=module_key,
                key=key,
            ).first()
            if company_setting:
                val = company_setting.get_value()
                cache.set(cache_k, val, timeout=cls.CACHE_TIMEOUT)
                return val

        # 3. Global default check
        global_setting = CoreSetting.objects.filter(
            company__isnull=True,
            branch__isnull=True,
            module_key=module_key,
            key=key,
        ).first()
        if global_setting:
            val = global_setting.get_value()
            cache.set(cache_k, val, timeout=cls.CACHE_TIMEOUT)
            return val

        return default

    @classmethod
    def set(
        cls,
        module_key: str,
        key: str,
        value: Any,
        value_type: str = CoreSetting.TYPE_STRING,
        company=None,
        branch=None,
        description: str = '',
    ) -> CoreSetting:
        company_id = company.id if hasattr(company, 'id') else company
        branch_id = branch.id if hasattr(branch, 'id') else branch

        setting_obj, created = CoreSetting.objects.get_or_create(
            company_id=company_id,
            branch_id=branch_id,
            module_key=module_key,
            key=key,
            defaults={
                'value_type': value_type,
                'description': description,
            },
        )
        setting_obj.value_type = value_type
        if description:
            setting_obj.description = description
        setting_obj.set_value(value)
        setting_obj.save()

        # Invalidate cache
        cache_k = cls._cache_key(module_key, key, company_id, branch_id)
        cache.delete(cache_k)

        return setting_obj

    @classmethod
    def get_module_settings(cls, module_key: str, company=None, branch=None) -> Dict[str, Any]:
        """Return a combined dictionary of all settings for a module."""
        company_id = company.id if hasattr(company, 'id') else company
        branch_id = branch.id if hasattr(branch, 'id') else branch

        settings_dict = {}

        # Fetch all global defaults
        for s in CoreSetting.objects.filter(company__isnull=True, branch__isnull=True, module_key=module_key):
            settings_dict[s.key] = s.get_value()

        # Overlay company settings
        if company_id:
            for s in CoreSetting.objects.filter(company_id=company_id, branch__isnull=True, module_key=module_key):
                settings_dict[s.key] = s.get_value()

        # Overlay branch settings
        if company_id and branch_id:
            for s in CoreSetting.objects.filter(company_id=company_id, branch_id=branch_id, module_key=module_key):
                settings_dict[s.key] = s.get_value()

        return settings_dict
