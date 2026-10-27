"""平台工具声明：来源引用和操作频道不属于通用工具箱职责。"""

from dataclasses import dataclass

from domain.core import CallableTool
from domain.core.channel_filters import matches, normalize_channels, validate_mode


@dataclass(eq=False)
class DeclaredTool(CallableTool):
    reference: str | None = None
    access_channels: tuple[str, ...] | None = None
    channel_mode: str = "allow"
    private: bool = False

    def __post_init__(self):
        super().__post_init__()
        if self.reference is None:
            self.reference = self.name
        if not isinstance(self.reference, str) or not self.reference:
            raise ValueError("工具来源引用必须为非空字符串")
        if self.access_channels is not None:
            self.access_channels = normalize_channels(self.access_channels)
        self.channel_mode = validate_mode(self.channel_mode)

    def exposed_to(self, channels, *, local):
        if self.private:
            return False
        if self.access_channels is None:
            return True
        return (local and not self.access_channels and self.channel_mode == "allow") or matches(
            self.access_channels, channels, self.channel_mode,
        )
