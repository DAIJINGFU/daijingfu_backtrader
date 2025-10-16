"""结果处理模块公共接口。"""

from .analyzer import compute_metrics_and_curves, collect_trade_and_order_details
from .formatter import (
	FormatterPayload,
	BaseResultFormatter,
	DailyResultFormatter,
	IntradayResultFormatter,
	build_formatter,
)
from .reporter import TradeCapture, create_order_capture_analyzer

__all__ = [
	"compute_metrics_and_curves",
	"collect_trade_and_order_details",
	"FormatterPayload",
	"BaseResultFormatter",
	"DailyResultFormatter",
	"IntradayResultFormatter",
	"build_formatter",
	"TradeCapture",
	"create_order_capture_analyzer",
]

