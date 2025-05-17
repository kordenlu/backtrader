import backtrader as bt
import numpy as np
from enum import Enum


class Direction(Enum):
    UP = 1
    DOWN = -1


class FractalsType(Enum):
    NONE = 0
    TOP = 1
    BOTTOM = -1


class ChanTheoryIndicator(bt.Indicator):
    """缠中说缠理论指标"""

    lines = (
        "buy1",
        "buy2",
        "buy3",
        "sell1",
        "sell2",
        "sell3",
        "top_fractal",
        "bottom_fractal",  # 顶底分型
        "stroke_high",
        "stroke_low",  # 笔的高低点
        "hub_top",
        "hub_bottom",  # 中枢上下边界
    )

    params = (
        ("fractal_len", 3),  # 分型长度，默认为3根K线
        ("min_stroke_len", 5),  # 最小笔长度，默认为5根K线
        ("threshold", 0.0),  # 分型确认阈值
        ("hub_strokes", 3),  # 构成中枢的最少笔数
    )

    def __init__(self):
        # 初始化MACD等指标用于辅助判断买卖点
        self.macd = bt.indicators.MACD(
            self.data, period_me1=12, period_me2=26, period_signal=9
        )

        # 初始化变量
        self.fractal_data = []  # 存储分型数据
        self.strokes = []  # 存储笔数据
        self.hubs = []  # 存储中枢数据

        # 计数器和状态变量
        self.count = 0
        self.last_direction = None
        self.current_stroke = None
        self.current_hub = None

    def next(self):
        # 默认设置信号为0
        self.lines.buy1[0] = 0
        self.lines.buy2[0] = 0
        self.lines.buy3[0] = 0
        self.lines.sell1[0] = 0
        self.lines.sell2[0] = 0
        self.lines.sell3[0] = 0
        self.lines.top_fractal[0] = 0
        self.lines.bottom_fractal[0] = 0
        self.lines.stroke_high[0] = 0
        self.lines.stroke_low[0] = 0
        self.lines.hub_top[0] = 0
        self.lines.hub_bottom[0] = 0

        self.count += 1

        # 至少需要2*fractal_len-1根K线才能开始计算
        if len(self) < 2 * self.p.fractal_len - 1:
            return

        # 识别分型
        fractal = self._identify_fractal()
        if fractal != FractalsType.NONE:
            # 处理分型并更新笔
            self._update_fractal_data(fractal)
            self._update_strokes()

            # 基于笔更新中枢
            self._update_hubs()

            # 使用分型、笔和中枢识别买卖点
            self._identify_buy_sell_points()

            # 设置线显示分型
            if fractal == FractalsType.TOP:
                self.lines.top_fractal[0] = self.data.high[0]
            elif fractal == FractalsType.BOTTOM:
                self.lines.bottom_fractal[0] = self.data.low[0]

            # 显示最新笔的高低点
            if self.strokes and len(self.strokes) > 0:
                last_stroke = self.strokes[-1]
                if last_stroke["direction"] == Direction.UP:
                    self.lines.stroke_high[0] = last_stroke["high"]
                    self.lines.stroke_low[0] = last_stroke["low"]
                else:
                    self.lines.stroke_high[0] = last_stroke["low"]
                    self.lines.stroke_low[0] = last_stroke["high"]

            # 显示中枢边界
            if self.hubs and len(self.hubs) > 0:
                last_hub = self.hubs[-1]
                self.lines.hub_top[0] = last_hub["top"]
                self.lines.hub_bottom[0] = last_hub["bottom"]

    def _identify_fractal(self):
        """识别顶底分型"""
        mid_point = self.p.fractal_len - 1

        # 获取前中后的K线数据
        highs = [self.data.high[-i] for i in range(2 * self.p.fractal_len - 1)]
        lows = [self.data.low[-i] for i in range(2 * self.p.fractal_len - 1)]

        # 顶分型判断
        is_top = True
        mid_high = highs[mid_point]
        for i in range(2 * self.p.fractal_len - 1):
            if i != mid_point and highs[i] >= mid_high:
                is_top = False
                break

        # 底分型判断
        is_bottom = True
        mid_low = lows[mid_point]
        for i in range(2 * self.p.fractal_len - 1):
            if i != mid_point and lows[i] <= mid_low:
                is_bottom = False
                break

        if is_top:
            return FractalsType.TOP
        elif is_bottom:
            return FractalsType.BOTTOM

        return FractalsType.NONE

    def _update_fractal_data(self, fractal):
        """更新分型数据"""
        if fractal == FractalsType.TOP:
            self.fractal_data.append(
                {
                    "type": "top",
                    "high": self.data.high[0],
                    "low": self.data.low[0],
                    "index": self.count,
                    "time": self.data.datetime.datetime(0),
                }
            )
        elif fractal == FractalsType.BOTTOM:
            self.fractal_data.append(
                {
                    "type": "bottom",
                    "high": self.data.high[0],
                    "low": self.data.low[0],
                    "index": self.count,
                    "time": self.data.datetime.datetime(0),
                }
            )

    def _update_strokes(self):
        """更新笔数据"""
        # 至少需要两个分型才能形成笔
        if len(self.fractal_data) < 2:
            return

        # 如果还没有笔，则创建第一笔
        if not self.strokes:
            first = self.fractal_data[0]
            second = self.fractal_data[1]

            # 第一个分型和第二个分型必须是不同类型
            if first["type"] != second["type"]:
                if first["type"] == "top":
                    self.strokes.append(
                        {
                            "direction": Direction.DOWN,
                            "high": first["high"],
                            "low": second["low"],
                            "start_index": first["index"],
                            "end_index": second["index"],
                            "start_time": first["time"],
                            "end_time": second["time"],
                        }
                    )
                    self.last_direction = Direction.DOWN
                else:
                    self.strokes.append(
                        {
                            "direction": Direction.UP,
                            "high": second["high"],
                            "low": first["low"],
                            "start_index": first["index"],
                            "end_index": second["index"],
                            "start_time": first["time"],
                            "end_time": second["time"],
                        }
                    )
                    self.last_direction = Direction.UP
        else:
            # 获取最后一笔和最新的分型
            last_stroke = self.strokes[-1]
            last_fractal = self.fractal_data[-1]

            # 根据最后一笔的方向和最新分型的类型来更新或创建新笔
            if last_stroke["direction"] == Direction.UP:
                if last_fractal["type"] == "top":
                    # 如果新高点高于上一笔的高点，则更新上一笔
                    if last_fractal["high"] > last_stroke["high"]:
                        last_stroke["high"] = last_fractal["high"]
                        last_stroke["end_index"] = last_fractal["index"]
                        last_stroke["end_time"] = last_fractal["time"]
                    # 否则，检查是否能创建新的向下笔
                elif last_fractal["type"] == "bottom":
                    # 只有当底分型的低点低于上一笔的起始低点，才创建新笔
                    if last_fractal["low"] < last_stroke["low"]:
                        self.strokes.append(
                            {
                                "direction": Direction.DOWN,
                                "high": last_stroke["high"],
                                "low": last_fractal["low"],
                                "start_index": last_stroke["end_index"],
                                "end_index": last_fractal["index"],
                                "start_time": last_stroke["end_time"],
                                "end_time": last_fractal["time"],
                            }
                        )
                        self.last_direction = Direction.DOWN
            else:  # Direction.DOWN
                if last_fractal["type"] == "bottom":
                    # 如果新低点低于上一笔的低点，则更新上一笔
                    if last_fractal["low"] < last_stroke["low"]:
                        last_stroke["low"] = last_fractal["low"]
                        last_stroke["end_index"] = last_fractal["index"]
                        last_stroke["end_time"] = last_fractal["time"]
                    # 否则，检查是否能创建新的向上笔
                elif last_fractal["type"] == "top":
                    # 只有当顶分型的高点高于上一笔的起始高点，才创建新笔
                    if last_fractal["high"] > last_stroke["high"]:
                        self.strokes.append(
                            {
                                "direction": Direction.UP,
                                "high": last_fractal["high"],
                                "low": last_stroke["low"],
                                "start_index": last_stroke["end_index"],
                                "end_index": last_fractal["index"],
                                "start_time": last_stroke["end_time"],
                                "end_time": last_fractal["time"],
                            }
                        )
                        self.last_direction = Direction.UP

    def _update_hubs(self):
        """更新中枢数据"""
        # 至少需要3笔才能形成中枢
        if len(self.strokes) < self.p.hub_strokes:
            return

        # 如果没有中枢，则尝试创建第一个中枢
        if not self.hubs:
            self._create_new_hub()
        else:
            # 获取最后一个中枢和最新的笔
            last_hub = self.hubs[-1]
            last_stroke = self.strokes[-1]

            # 判断最新的笔是否突破中枢
            if last_stroke["direction"] == Direction.UP:
                if last_stroke["low"] > last_hub["top"]:
                    # 向上突破，尝试创建新中枢
                    self._create_new_hub()
                elif (
                    last_stroke["high"] > last_hub["top"]
                    and last_stroke["low"] < last_hub["top"]
                ):
                    # 部分突破上边界，扩展中枢上边界
                    last_hub["top"] = last_stroke["high"]
            else:  # Direction.DOWN
                if last_stroke["high"] < last_hub["bottom"]:
                    # 向下突破，尝试创建新中枢
                    self._create_new_hub()
                elif (
                    last_stroke["low"] < last_hub["bottom"]
                    and last_stroke["high"] > last_hub["bottom"]
                ):
                    # 部分突破下边界，扩展中枢下边界
                    last_hub["bottom"] = last_stroke["low"]

    def _create_new_hub(self):
        """创建新的中枢"""
        if len(self.strokes) < self.p.hub_strokes:
            return

        # 取最近的n笔来确定中枢区间
        recent_strokes = self.strokes[-self.p.hub_strokes :]

        # 确定中枢的上下边界
        highs = [stroke["high"] for stroke in recent_strokes]
        lows = [stroke["low"] for stroke in recent_strokes]

        # 中枢的上边界是次高点，下边界是次低点
        highs.sort()
        lows.sort()

        hub_top = highs[-2]  # 次高点
        hub_bottom = lows[1]  # 次低点

        # 如果形成有效区间，则创建中枢
        if hub_top > hub_bottom:
            start_idx = recent_strokes[0]["start_index"]
            end_idx = recent_strokes[-1]["end_index"]

            self.hubs.append(
                {
                    "top": hub_top,
                    "bottom": hub_bottom,
                    "start_index": start_idx,
                    "end_index": end_idx,
                    "start_time": recent_strokes[0]["start_time"],
                    "end_time": recent_strokes[-1]["end_time"],
                }
            )

    def _identify_buy_sell_points(self):
        """识别买卖点"""
        # 需要至少一个中枢和足够的笔才能判断买卖点
        if not self.hubs or len(self.strokes) < self.p.hub_strokes + 1:
            return

        last_hub = self.hubs[-1]
        last_stroke = self.strokes[-1]

        # 一买：下跌趋势中，在中枢下方构成底分型并确认
        if last_stroke["direction"] == Direction.UP and len(self.fractal_data) >= 2:
            last_fractal = self.fractal_data[-1]
            if (
                last_fractal["type"] == "bottom"
                and last_fractal["low"] < last_hub["bottom"]
            ):
                # MACD辅助判断：MACD金叉或底背离
                if (
                    self.macd.macd[0] > self.macd.signal[0]
                    and self.macd.macd[-1] <= self.macd.signal[-1]
                ):
                    self.lines.buy1[0] = 1

        # 二买：上涨趋势中回调不破前低
        if last_stroke["direction"] == Direction.UP and len(self.strokes) >= 3:
            prev_stroke = self.strokes[-3]  # 上一个同向笔
            if (
                prev_stroke["direction"] == Direction.UP
                and last_stroke["low"] > prev_stroke["low"]
            ):
                self.lines.buy2[0] = 1

        # 三买：突破中枢上边界后回调
        if last_stroke["direction"] == Direction.UP and len(self.strokes) >= 2:
            prev_stroke = self.strokes[-2]
            if (
                prev_stroke["high"] > last_hub["top"]
                and last_stroke["low"] > last_hub["top"]
            ):
                self.lines.buy3[0] = 1

        # 一卖：上涨趋势中，在中枢上方构成顶分型并确认
        if last_stroke["direction"] == Direction.DOWN and len(self.fractal_data) >= 2:
            last_fractal = self.fractal_data[-1]
            if last_fractal["type"] == "top" and last_fractal["high"] > last_hub["top"]:
                # MACD辅助判断：MACD死叉或顶背离
                if (
                    self.macd.macd[0] < self.macd.signal[0]
                    and self.macd.macd[-1] >= self.macd.signal[-1]
                ):
                    self.lines.sell1[0] = 1

        # 二卖：下跌趋势中反弹不破前高
        if last_stroke["direction"] == Direction.DOWN and len(self.strokes) >= 3:
            prev_stroke = self.strokes[-3]  # 上一个同向笔
            if (
                prev_stroke["direction"] == Direction.DOWN
                and last_stroke["high"] < prev_stroke["high"]
            ):
                self.lines.sell2[0] = 1

        # 三卖：跌破中枢下边界后反弹
        if last_stroke["direction"] == Direction.DOWN and len(self.strokes) >= 2:
            prev_stroke = self.strokes[-2]
            if (
                prev_stroke["low"] < last_hub["bottom"]
                and last_stroke["high"] < last_hub["bottom"]
            ):
                self.lines.sell3[0] = 1
