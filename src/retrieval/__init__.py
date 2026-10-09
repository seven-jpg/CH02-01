"""C 模块（检索）实现包。

只包含纯文本检索：官方 Web 索引 + BGE 编码器。不加载图像/CLIP 分支。
"""

from __future__ import annotations

__all__ = ["text_retrieval"]
