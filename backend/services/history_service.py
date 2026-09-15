"""历史记录存储兼容层（默认使用 SQLite 实现）。

该模块保留原路径，直接复用 history_service_sqlite 中的异步接口，
便于渐进迁移旧代码，同时避免循环引用。
"""

from .history_service_sqlite import (
    clear_history,
    delete_history,
    get_history_batch,
    list_history,
    persist_analysis_result,
    store_result,
)

__all__ = [
    'store_result',
    'list_history',
    'get_history_batch',
    'delete_history',
    'clear_history',
    'persist_analysis_result',
]
