"""导出任务 Pydantic 模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ExportJobOut(BaseModel):
    """异步导出任务对外视图。download_ready 由路由按文件实际存在性填充。"""

    id: int
    status: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    download_ready: bool = False

    model_config = {"from_attributes": True}
