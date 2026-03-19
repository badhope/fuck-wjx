"""核心服务层 - 封装业务逻辑供 Controller 调用"""
from wjx.core.services.area_service import (
    build_benefit_city_code_index,
    load_area_codes,
    load_benefit_supported_areas,
    load_supported_area_codes,
    resolve_proxy_area_for_source,
)
from wjx.core.services.survey_service import parse_survey
from wjx.core.services.proxy_service import prefetch_proxy_pool

__all__ = [
    "build_benefit_city_code_index",
    "load_area_codes",
    "load_benefit_supported_areas",
    "load_supported_area_codes",
    "parse_survey",
    "prefetch_proxy_pool",
    "resolve_proxy_area_for_source",
]
