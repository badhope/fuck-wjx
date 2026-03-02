"""随机IP额度管理 - API缓存、注册表读写"""
import logging
import threading
import time
from typing import Optional

import wjx.network.http_client as http_client
from wjx.utils.app.config import DEFAULT_HTTP_HEADERS
from wjx.utils.logging.log_utils import log_suppressed_exception
from wjx.utils.system.registry_manager import RegistryManager

_cached_default_quota: Optional[int] = None
_cached_default_quota_timestamp: float = 0.0
_DEFAULT_QUOTA_CACHE_TTL = 1800
_DEFAULT_QUOTA_API_ENDPOINT = "https://api-wjx.hungrym0.top/api/default"
_quota_update_lock = threading.Lock()
_quota_updating = False


def _fetch_default_quota_from_api() -> Optional[int]:
    try:
        response = http_client.get(
            _DEFAULT_QUOTA_API_ENDPOINT, timeout=5, headers=DEFAULT_HTTP_HEADERS, proxies={}
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return None
        quota = data.get("quota")
        if quota is None:
            return None
        quota_int = int(quota)
        if quota_int <= 0:
            return None
        return quota_int
    except http_client.exceptions.Timeout:
        return None
    except http_client.exceptions.RequestException:
        return None
    except (ValueError, TypeError):
        return None
    except Exception as exc:
        log_suppressed_exception("quota._fetch_default_quota_from_api", exc)
        return None


def _update_quota_cache_async() -> None:
    global _quota_updating
    with _quota_update_lock:
        if _quota_updating:
            return
        _quota_updating = True

    def _do_update():
        global _cached_default_quota, _cached_default_quota_timestamp, _quota_updating
        try:
            api_quota = _fetch_default_quota_from_api()
            if api_quota is not None:
                with _quota_update_lock:
                    _cached_default_quota = api_quota
                    _cached_default_quota_timestamp = time.time()
        except Exception as exc:
            log_suppressed_exception("_update_quota_cache_async", exc)
        finally:
            with _quota_update_lock:
                _quota_updating = False

    threading.Thread(target=_do_update, daemon=True, name="QuotaUpdateThread").start()


def _get_default_quota_with_cache() -> Optional[int]:
    global _cached_default_quota, _cached_default_quota_timestamp
    current_time = time.time()
    if _cached_default_quota is not None:
        cache_age = current_time - _cached_default_quota_timestamp
        if cache_age < _DEFAULT_QUOTA_CACHE_TTL:
            if cache_age > _DEFAULT_QUOTA_CACHE_TTL - 300:
                _update_quota_cache_async()
            return _cached_default_quota
    api_quota = _fetch_default_quota_from_api()
    if api_quota is not None:
        _cached_default_quota = api_quota
        _cached_default_quota_timestamp = current_time
        return api_quota
    return None


def get_random_ip_limit() -> int:
    try:
        limit = int(RegistryManager.read_quota_limit(0))  # type: ignore[attr-defined]
        if limit > 0:
            return limit
    except Exception as exc:
        log_suppressed_exception("quota.get_random_ip_limit", exc)
    default_quota = _get_default_quota_with_cache()
    if default_quota is None:
        return 0
    try:
        RegistryManager.write_quota_limit(default_quota)
    except Exception as exc:
        log_suppressed_exception("quota.get_random_ip_limit write default quota", exc)
    return default_quota


def get_random_ip_counter_snapshot_local() -> tuple[int, int, bool]:
    from wjx.network.proxy.provider import is_custom_proxy_api_active
    count = RegistryManager.read_submit_count()
    limit = max(0, int(RegistryManager.read_quota_limit(0)))
    return count, limit, is_custom_proxy_api_active()


def normalize_random_ip_enabled_value(desired_enabled: bool) -> bool:
    if not desired_enabled:
        return False
    from wjx.network.proxy.provider import is_custom_proxy_api_active
    if is_custom_proxy_api_active():
        return True
    limit = int(get_random_ip_limit() or 0)
    if limit <= 0:
        logging.warning("配置中启用了随机IP，但额度不可用，已禁用")
        return False
    count = RegistryManager.read_submit_count()
    if count >= limit:
        logging.warning(f"配置中启用了随机IP，但已达到{limit}份限制，已禁用此选项")
        return False
    return True
