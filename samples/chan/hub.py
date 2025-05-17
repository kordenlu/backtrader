import matplotlib.dates as mdates
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi
from datetime import datetime, timedelta
from enum import Enum
import argparse
import traceback
import tushare as ts


class Direction(Enum):
    UP = 1
    DOWN = -1


class FractalType(Enum):
    NONE = 0
    TOP = 1
    BOTTOM = -1


class ChartAnalyzer:
    """缠论分析工具"""

    def __init__(self, data, fractal_len=3, min_stroke_len=5, hub_strokes=3):
        """
        初始化分析器

        参数:
        data: DataFrame - 包含OHLC数据的DataFrame
        fractal_len: int - 分型识别的K线数量(默认3)
        min_stroke_len: int - 最小笔长度(默认5根K线)
        hub_strokes: int - 构成中枢的最少笔数量(默认3)
        """
        self.data = data
        if "open" in self.data.columns and "Open" not in self.data.columns:
            self.data = self.data.rename(
                columns={
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume",
                }
            )
        self.fractal_len = fractal_len
        self.min_stroke_len = min_stroke_len
        self.hub_strokes = hub_strokes

        # 初始化数据结构
        self.fractals = []  # 存储分型
        self.strokes = []  # 存储笔
        self.hubs = []  # 存储中枢

        # 开始分析
        self._handle_inclusive_k_lines()  # 先处理包含关系
        self._identify_fractals()
        self._construct_strokes()
        self._identify_hubs()
        self._identify_macd_divergence()

    def _handle_inclusive_k_lines(self):
        """处理K线包含关系"""
        print("处理K线包含关系...")

        if len(self.data) < 2:
            print("数据量不足，无法处理包含关系")
            return

        # 创建新的处理后的K线数据
        processed_data = self.data.copy()

        # 初始化处理方向（默认为向上）
        direction = Direction.UP

        # 从第二根K线开始处理
        i = 1
        while i < len(processed_data):
            # 获取前一根K线和当前K线
            prev_k = processed_data.iloc[i - 1]
            curr_k = processed_data.iloc[i]

            # 判断是否存在包含关系
            has_inclusion = (
                curr_k["High"] <= prev_k["High"] and curr_k["Low"] >= prev_k["Low"]
            ) or (  # 当前K线被前一根包含
                curr_k["High"] >= prev_k["High"] and curr_k["Low"] <= prev_k["Low"]
            )  # 当前K线包含前一根

            if has_inclusion:
                # 根据方向合并K线
                if direction == Direction.UP:
                    # 向上时，取高点高的和低点高的
                    new_high = max(prev_k["High"], curr_k["High"])
                    new_low = max(prev_k["Low"], curr_k["Low"])
                    new_open = prev_k["Open"]  # 保留前一根K线的开盘价
                    new_close = (
                        curr_k["Close"]
                        if new_high == curr_k["High"]
                        else prev_k["Close"]
                    )
                else:  # Direction.DOWN
                    # 向下时，取高点低的和低点低的
                    new_high = min(prev_k["High"], curr_k["High"])
                    new_low = min(prev_k["Low"], curr_k["Low"])
                    new_open = prev_k["Open"]  # 保留前一根K线的开盘价
                    new_close = (
                        curr_k["Close"] if new_low == curr_k["Low"] else prev_k["Close"]
                    )

                # 合并成交量
                new_volume = (
                    prev_k["Volume"] + curr_k["Volume"]
                    if "Volume" in processed_data.columns
                    else None
                )

                # 更新前一根K线的值
                processed_data.at[processed_data.index[i - 1], "High"] = new_high
                processed_data.at[processed_data.index[i - 1], "Low"] = new_low
                processed_data.at[processed_data.index[i - 1], "Close"] = new_close
                if new_volume is not None:
                    processed_data.at[processed_data.index[i - 1], "Volume"] = (
                        new_volume
                    )

                # 删除当前K线
                processed_data = processed_data.drop(processed_data.index[i])

                # 索引不增加，继续处理下一根K线
            else:
                # 无包含关系，判断是否转向
                if curr_k["High"] > prev_k["High"] and curr_k["Low"] > prev_k["Low"]:
                    direction = Direction.UP
                elif curr_k["High"] < prev_k["High"] and curr_k["Low"] < prev_k["Low"]:
                    direction = Direction.DOWN

                # 处理下一根K线
                i += 1

        # 更新数据
        print(f"处理完毕，处理前K线数: {len(self.data)}，处理后: {len(processed_data)}")
        self.data = processed_data

    def _identify_fractals(self):
        """识别所有顶底分型"""
        print("开始识别分型...")

        # 至少需要2*fractal_len-1根K线才能识别分型
        if len(self.data) < 2 * self.fractal_len - 1:
            print(f"数据量不足，至少需要{2 * self.fractal_len - 1}根K线")
            return

        for i in range(self.fractal_len - 1, len(self.data) - self.fractal_len + 1):
            # 获取当前位置前后的K线
            window = self.data.iloc[i - (self.fractal_len - 1) : i + self.fractal_len]
            mid_idx = self.fractal_len - 1

            # 顶分型判断
            is_top = True
            mid_high = window.iloc[mid_idx]["High"]
            for j in range(len(window)):
                if j != mid_idx and window.iloc[j]["High"] >= mid_high:
                    is_top = False
                    break

            # 底分型判断
            is_bottom = True
            mid_low = window.iloc[mid_idx]["Low"]
            for j in range(len(window)):
                if j != mid_idx and window.iloc[j]["Low"] <= mid_low:
                    is_bottom = False
                    break

            # 记录分型
            if is_top:
                self.fractals.append(
                    {
                        "type": FractalType.TOP,
                        "index": i,
                        "price": mid_high,
                        "time": self.data.index[i],
                    }
                )
            elif is_bottom:
                self.fractals.append(
                    {
                        "type": FractalType.BOTTOM,
                        "index": i,
                        "price": mid_low,
                        "time": self.data.index[i],
                    }
                )

        print(f"识别到{len(self.fractals)}个分型")

    def _construct_strokes(self):
        """根据分型构建笔"""
        print("开始构建笔...")

        if len(self.fractals) < 2:
            print("分型数量不足，无法构建笔")
            return

        # 初始化第一笔
        first = self.fractals[0]
        current_direction = None
        current_start = first

        for i in range(1, len(self.fractals)):
            current = self.fractals[i]

            # 确定第一笔的方向
            if current_direction is None:
                if current["type"] != first["type"]:
                    if first["type"] == FractalType.TOP:
                        current_direction = Direction.DOWN
                    else:
                        current_direction = Direction.UP

            # 当前分型与笔的起始分型类型相同，需要判断是否更新起始点
            if current["type"] == current_start["type"]:
                if (
                    current_direction == Direction.UP
                    and current["price"] > current_start["price"]
                ) or (
                    current_direction == Direction.DOWN
                    and current["price"] < current_start["price"]
                ):
                    current_start = current
            # 当前分型与笔的起始分型类型不同，可能形成新笔
            else:
                # 判断是否符合笔的条件
                valid_stroke = False

                if current_direction == Direction.UP:
                    # 向上笔：终点必须高于起点
                    if current["price"] > current_start["price"]:
                        valid_stroke = True
                else:  # Direction.DOWN
                    # 向下笔：终点必须低于起点
                    if current["price"] < current_start["price"]:
                        valid_stroke = True

                if valid_stroke:
                    # 添加有效笔
                    stroke = {
                        "direction": current_direction,
                        "start_index": current_start["index"],
                        "end_index": current["index"],
                        "start_price": current_start["price"],
                        "end_price": current["price"],
                        "start_time": current_start["time"],
                        "end_time": current["time"],
                    }

                    # 计算笔的高低点
                    if current_direction == Direction.UP:
                        stroke["high"] = current["price"]
                        stroke["low"] = current_start["price"]
                    else:
                        stroke["high"] = current_start["price"]
                        stroke["low"] = current["price"]

                    self.strokes.append(stroke)

                    # 更新当前方向和起点
                    current_direction = (
                        Direction.UP
                        if current_direction == Direction.DOWN
                        else Direction.DOWN
                    )
                    current_start = current

        print(f"构建了{len(self.strokes)}笔")

    def _identify_hubs(self):
        """识别中枢"""
        print("开始识别中枢...")

        if len(self.strokes) < self.hub_strokes:
            print(f"笔的数量不足，无法识别中枢，至少需要{self.hub_strokes}笔")
            return

        # 遍历笔，寻找可能的中枢
        i = 0
        while i <= len(self.strokes) - self.hub_strokes:
            # 取连续的n笔
            stroke_window = self.strokes[i : i + self.hub_strokes]

            # 获取这些笔的高点和低点
            highs = [stroke["high"] for stroke in stroke_window]
            lows = [stroke["low"] for stroke in stroke_window]

            # 计算中枢区间 - 上边界是次高点，下边界是次低点
            highs.sort(reverse=True)
            lows.sort()

            hub_top = highs[1]  # 次高点
            hub_bottom = lows[1]  # 次低点

            # 判断是否形成有效中枢
            if hub_top > hub_bottom:
                # 记录中枢信息
                hub = {
                    "top": hub_top,
                    "bottom": hub_bottom,
                    "start_index": stroke_window[0]["start_index"],
                    "end_index": stroke_window[-1]["end_index"],
                    "start_time": stroke_window[0]["start_time"],
                    "end_time": stroke_window[-1]["end_time"],
                    "strokes": self.hub_strokes,
                }

                # 尝试向后扩展中枢
                next_idx = i + self.hub_strokes
                while next_idx < len(self.strokes):
                    next_stroke = self.strokes[next_idx]

                    # 判断下一笔是否在中枢区间内or与中枢有重叠
                    if (
                        next_stroke["low"] <= hub_top
                        and next_stroke["high"] >= hub_bottom
                    ):
                        # 更新中枢边界
                        all_highs = highs + [next_stroke["high"]]
                        all_lows = lows + [next_stroke["low"]]
                        all_highs.sort(reverse=True)
                        all_lows.sort()

                        new_hub_top = all_highs[1]  # 更新的次高点
                        new_hub_bottom = all_lows[1]  # 更新的次低点

                        if new_hub_top > new_hub_bottom:
                            hub_top = new_hub_top
                            hub_bottom = new_hub_bottom
                            hub["top"] = hub_top
                            hub["bottom"] = hub_bottom
                            hub["end_index"] = next_stroke["end_index"]
                            hub["end_time"] = next_stroke["end_time"]
                            hub["strokes"] += 1
                            next_idx += 1
                        else:
                            break
                    else:
                        # 笔完全在中枢上方或下方，中枢结束
                        break

                # 添加到中枢列表
                self.hubs.append(hub)

                # 从中枢结束后的下一笔继续寻找新中枢
                i = next_idx
            else:
                # 未形成有效中枢，向后移动一笔
                i += 1

        print(f"识别到{len(self.hubs)}个中枢")

    def get_current_hub(self):
        """获取当前中枢信息"""
        if not self.hubs:
            return None

        return self.hubs[-1]

    def _identify_macd_divergence(self):
        """识别MACD与价格走势的背离"""
        print("开始识别MACD背离...")

        # 计算MACD
        exp12 = self.data["Close"].ewm(span=12, adjust=False).mean()
        exp26 = self.data["Close"].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal

        # 存储背离信息
        self.divergences = []

        # 筛选顶分型和底分型
        top_fractals = [f for f in self.fractals if f["type"] == FractalType.TOP]
        bottom_fractals = [f for f in self.fractals if f["type"] == FractalType.BOTTOM]

        # 识别顶背离
        for i in range(1, len(top_fractals)):
            curr = top_fractals[i]
            prev = top_fractals[i - 1]

            # 价格创新高但MACD没有创新高
            if (
                curr["price"] > prev["price"]
                and macd[self.data.index[curr["index"]]]
                <= macd[self.data.index[prev["index"]]]
            ):

                # 记录顶背离
                divergence = {
                    "type": "顶背离",
                    "first_idx": prev["index"],
                    "second_idx": curr["index"],
                    "first_time": prev["time"],
                    "second_time": curr["time"],
                    "first_price": prev["price"],
                    "second_price": curr["price"],
                    "first_macd": macd[self.data.index[prev["index"]]],
                    "second_macd": macd[self.data.index[curr["index"]]],
                }

                self.divergences.append(divergence)

        # 识别底背离
        for i in range(1, len(bottom_fractals)):
            curr = bottom_fractals[i]
            prev = bottom_fractals[i - 1]

            # 价格创新低但MACD没有创新低
            if (
                curr["price"] < prev["price"]
                and macd[self.data.index[curr["index"]]]
                >= macd[self.data.index[prev["index"]]]
            ):

                # 记录底背离
                divergence = {
                    "type": "底背离",
                    "first_idx": prev["index"],
                    "second_idx": curr["index"],
                    "first_time": prev["time"],
                    "second_time": curr["time"],
                    "first_price": prev["price"],
                    "second_price": curr["price"],
                    "first_macd": macd[self.data.index[prev["index"]]],
                    "second_macd": macd[self.data.index[curr["index"]]],
                }

                self.divergences.append(divergence)

        print(f"识别到{len(self.divergences)}个MACD背离")

    def plot_analysis(self, symbol_code=None, symbol_name=None):

        plt.rcParams["font.sans-serif"] = [
            "Arial Unicode MS",
            "SimHei",
            "Microsoft YaHei",
            "WenQuanYi Micro Hei",
        ]  # 优先使用的中文字体
        plt.rcParams["axes.unicode_minus"] = (
            False  # 解决保存图像时负号'-'显示为方块的问题
        )
        plt.rcParams["font.family"] = "sans-serif"  # 使用sans-serif字体

        """绘制分析结果"""
        fig = plt.figure(figsize=(16, 9))

        # 绘制K线图
        ax1 = plt.subplot(2, 1, 1)
        ax1.plot(self.data.index, self.data["Close"], "k-", linewidth=1)

        # 设置标题，如果有股票代码和名称则显示，否则使用默认标题
        title = "股票价格走势与缠论分析"
        if symbol_code and symbol_name:
            title = f"{symbol_name}（{symbol_code}）- 缠论分析"
        elif symbol_code:
            title = f"（{symbol_code}）- 缠论分析"

        ax1.set_title(title)

        # 绘制分型
        top_fractals = [f for f in self.fractals if f["type"] == FractalType.TOP]
        bottom_fractals = [f for f in self.fractals if f["type"] == FractalType.BOTTOM]

        plt.scatter(
            [self.data.index[f["index"]] for f in top_fractals],
            [f["price"] for f in top_fractals],
            marker="^",
            color="red",
            s=50,
            label="顶分型",
        )

        plt.scatter(
            [self.data.index[f["index"]] for f in bottom_fractals],
            [f["price"] for f in bottom_fractals],
            marker="v",
            color="green",
            s=50,
            label="底分型",
        )

        # 绘制笔
        for stroke in self.strokes:
            plt.plot(
                [stroke["start_time"], stroke["end_time"]],
                [stroke["start_price"], stroke["end_price"]],
                "b-",
                linewidth=1.5,
            )

        # 绘制中枢
        for hub in self.hubs:
            plt.axhline(
                y=hub["top"],
                color="r",
                linestyle="--",
                xmin=hub["start_index"] / len(self.data),
                xmax=hub["end_index"] / len(self.data),
            )
            plt.axhline(
                y=hub["bottom"],
                color="g",
                linestyle="--",
                xmin=hub["start_index"] / len(self.data),
                xmax=hub["end_index"] / len(self.data),
            )
            plt.axvspan(
                hub["start_time"],
                hub["end_time"],
                ymin=0,
                ymax=1,
                alpha=0.1,
                color="yellow",
            )

        plt.legend()

        # 绘制MACD辅助判断
        ax2 = plt.subplot(2, 1, 2)

        # 计算MACD
        exp12 = self.data["Close"].ewm(span=12, adjust=False).mean()
        exp26 = self.data["Close"].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal

        plt.plot(self.data.index, macd, "b-", label="MACD")
        plt.plot(self.data.index, signal, "r-", label="Signal")
        plt.bar(
            self.data.index,
            histogram,
            color=["red" if h < 0 else "green" for h in histogram],
            label="Histogram",
        )

        plt.title("MACD")
        plt.legend()

        # 在plot_analysis方法中添加以下代码
        # 绘制MACD背离
        if hasattr(self, "divergences") and self.divergences:
            # 绘制顶背离
            top_divs = [d for d in self.divergences if d["type"] == "顶背离"]
            for div in top_divs:
                # 价格面板中连线
                plt.subplot(2, 1, 1)
                plt.plot(
                    [div["first_time"], div["second_time"]],
                    [div["first_price"], div["second_price"]],
                    "r--",
                    linewidth=1.5,
                )
                plt.annotate(
                    "顶背离",
                    xy=(div["second_time"], div["second_price"]),
                    xytext=(10, 10),
                    textcoords="offset points",
                    color="red",
                    fontsize=8,
                )

                # MACD面板中连线
                plt.subplot(2, 1, 2)
                plt.plot(
                    [div["first_time"], div["second_time"]],
                    [div["first_macd"], div["second_macd"]],
                    "r--",
                    linewidth=1.5,
                )
                # 在MACD面板中添加MACD值标注
                plt.annotate(
                    f"MACD: {div['first_macd']:.4f}",
                    xy=(div["first_time"], div["first_macd"]),
                    xytext=(-55, 10),
                    textcoords="offset points",
                    color="red",
                    fontsize=8,
                )
                plt.annotate(
                    f"MACD: {div['second_macd']:.4f}",
                    xy=(div["second_time"], div["second_macd"]),
                    xytext=(10, 10),
                    textcoords="offset points",
                    color="red",
                    fontsize=8,
                )

            # 绘制底背离
            bottom_divs = [d for d in self.divergences if d["type"] == "底背离"]
            for div in bottom_divs:
                # 价格面板中连线
                plt.subplot(2, 1, 1)
                plt.plot(
                    [div["first_time"], div["second_time"]],
                    [div["first_price"], div["second_price"]],
                    "g--",
                    linewidth=1.5,
                )
                plt.annotate(
                    "底背离",
                    xy=(div["second_time"], div["second_price"]),
                    xytext=(10, -15),
                    textcoords="offset points",
                    color="green",
                    fontsize=8,
                )

                # MACD面板中连线
                plt.subplot(2, 1, 2)
                plt.plot(
                    [div["first_time"], div["second_time"]],
                    [div["first_macd"], div["second_macd"]],
                    "g--",
                    linewidth=1.5,
                )
                # 在MACD面板中添加MACD值标注
                plt.annotate(
                    f"MACD: {div['first_macd']:.4f}",
                    xy=(div["first_time"], div["first_macd"]),
                    xytext=(-55, -15),
                    textcoords="offset points",
                    color="green",
                    fontsize=8,
                )
                plt.annotate(
                    f"MACD: {div['second_macd']:.4f}",
                    xy=(div["second_time"], div["second_macd"]),
                    xytext=(10, -15),
                    textcoords="offset points",
                    color="green",
                    fontsize=8,
                )

        # 添加鼠标悬停显示信息的功能
        annotation = ax1.annotate(
            "",
            xy=(0, 0),
            xytext=(20, 20),
            textcoords="offset points",
            bbox={"boxstyle": "round", "fc": "w", "alpha": 0.8},
            arrowprops={"arrowstyle": "->"},
            zorder=10,
        )
        annotation.set_visible(False)

        # 鼠标移动事件处理函数
        def hover(event):
            if event.inaxes == ax1:
                # 获取鼠标所在位置的x坐标(时间)
                x = event.xdata
                y = event.ydata
                if x is None:
                    return

                # 找到最近的数据点
                index = np.argmin(
                    np.abs([mdates.date2num(date) - x for date in self.data.index])
                )
                date = self.data.index[index]
                price = self.data["Close"].iloc[index]

                # 更新注释的位置和内容
                annotation.xy = (date, price)

                # 使用明确的日期格式化，确保显示年-月-日
                date_str = date.strftime("%Y-%m-%d")
                annotation.set_text(f"日期: {date_str}\n价格: {price:.2f}")

                # 动态调整注释框的位置，防止在图表边缘溢出

                # 获取图形的像素尺寸
                fig_width_px = fig.get_figwidth() * fig.dpi
                fig_height_px = fig.get_figheight() * fig.dpi

                # 获取当前数据点在显示坐标系中的位置（像素坐标）
                display_pos = ax1.transData.transform((mdates.date2num(date), price))

                # 获取坐标轴在图形中的位置和大小
                bbox = ax1.get_position()
                ax_width_px = bbox.width * fig_width_px

                # 简化水平位置判断：在右半部分则显示在左边，在左半部分则显示在右边
                mid_point = bbox.x0 * fig_width_px + (ax_width_px / 2)
                if display_pos[0] > mid_point:
                    x_offset = -80  # 右半边时，显示在左侧
                    annotation.set_ha("right")  # 水平对齐方式改为右对齐
                else:
                    x_offset = 20  # 左半边时，显示在右侧
                    annotation.set_ha("left")  # 水平对齐方式改为左对齐

                # 垂直方向调整
                if display_pos[1] < 50:
                    y_offset = 20  # 如果靠近顶部，则显示在下方
                else:
                    y_offset = -20  # 否则显示在上方

                # 应用计算的偏移量
                annotation.xytext = (x_offset, y_offset)

                # 确保注释框完全可见
                annotation.set_visible(True)
                fig.canvas.draw_idle()
            else:
                annotation.set_visible(False)
                fig.canvas.draw_idle()

        # 连接鼠标移动事件
        fig.canvas.mpl_connect("motion_notify_event", hover)

        plt.tight_layout()
        plt.show()

    def print_current_status(self):
        """打印当前市场状态与中枢信息"""
        print("\n当前市场状态分析:")

        # 获取最新价格
        current_price = self.data["Close"].iloc[-1]
        print(f"最新收盘价: {current_price:.2f}")

        # 获取当前中枢
        current_hub = self.get_current_hub()
        if current_hub:
            print("\n当前中枢信息:")
            print(f"中枢上边界: {current_hub['top']:.2f}")
            print(f"中枢下边界: {current_hub['bottom']:.2f}")
            print(f"中枢区间: {current_hub['bottom']:.2f} - {current_hub['top']:.2f}")
            print(
                f"中枢宽度: {(current_hub['top'] - current_hub['bottom']) / current_hub['bottom'] * 100:.2f}%"
            )
            print(
                f"中枢形成时间: {current_hub['start_time']} 至 {current_hub['end_time']}"
            )
            print(f"中枢包含笔数: {current_hub['strokes']}")

            # 判断当前价格相对于中枢的位置
            if current_price > current_hub["top"]:
                distance = (
                    (current_price - current_hub["top"]) / current_hub["top"] * 100
                )
                print(f"当前价格位于中枢上方 {distance:.2f}%")
            elif current_price < current_hub["bottom"]:
                distance = (current_hub["bottom"] - current_price) / current_price * 100
                print(f"当前价格位于中枢下方 {distance:.2f}%")
            else:
                # 计算在中枢内的相对位置(0-100%)
                relative_pos = (
                    (current_price - current_hub["bottom"])
                    / (current_hub["top"] - current_hub["bottom"])
                    * 100
                )
                print(f"当前价格位于中枢内 {relative_pos:.2f}%")
        else:
            print("未检测到有效中枢")

        # 获取最近的笔
        if self.strokes:
            last_stroke = self.strokes[-1]
            print("\n最近一笔:")
            print(
                f"方向: {'向上' if last_stroke['direction'] == Direction.UP else '向下'}"
            )
            print(
                f"起始价: {last_stroke['start_price']:.2f}, 结束价: {last_stroke['end_price']:.2f}"
            )
            print(
                f"幅度: {abs(last_stroke['end_price'] - last_stroke['start_price']) / last_stroke['start_price'] * 100:.2f}%"
            )
            print(f"时间: {last_stroke['start_time']} 至 {last_stroke['end_time']}")


def get_stock_data(
    symbol,
    period="-1y",
    interval="1d",
    influx_url="http://localhost:8086",
    influx_token="Pf4Rb2r0X7H5KscNkKMI3z9T4y7gZqGHoRGdE9hK9jqiihf2fKm2lTUa_qiQqWNMHBX-dXPYMIORMPMXf2j2Eg==",
    influx_org="yml",
    influx_bucket="hloc",
    influx_measurement="hloc_data",
):
    """从本地InfluxDB获取股票历史数据"""
    print(f"从InfluxDB获取 {symbol} 的历史数据...")

    # 计算时间范围
    end_time = datetime.now()

    if period.startswith("-"):  # 处理负数周期（如"-1y"表示过去一年）
        period = period[1:]

    if period.endswith("y"):
        years = int(period[:-1])
        start_time = end_time - timedelta(days=years * 365)
    elif period.endswith("mo"):
        months = int(period[:-2])
        start_time = end_time - timedelta(days=months * 30)
    elif period.endswith("w"):
        weeks = int(period[:-1])
        start_time = end_time - timedelta(weeks=weeks)
    elif period.endswith("d"):
        days = int(period[:-1])
        start_time = end_time - timedelta(days=days)
    else:
        print(f"不支持的周期格式: {period}")
        return None

    # 转换时间格式为RFC3339
    start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        # 创建InfluxDB客户端
        client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
        query_api = client.query_api()

        # 构建基础Flux查询
        flux_query = f"""
        from(bucket: "{influx_bucket}")
            |> range(start: {start_time_str}, stop: {end_time_str})
            |> filter(fn: (r) => r["_measurement"] == "{influx_measurement}")
            |> filter(fn: (r) => r.symbol_code == "{symbol}")
        """

        # 根据请求的K线周期处理聚合
        if interval != "1d":
            aggregation_period = ""

            # 确定聚合周期
            if interval == "1w":
                aggregation_period = "1w"
            elif interval == "1mo":
                aggregation_period = "1mo"
            elif interval == "1y":
                aggregation_period = "1y"
            else:
                # 处理其他间隔，如"5d", "4h"等
                unit = interval[-1]
                value = int(interval[:-1])

                if unit == "d":
                    aggregation_period = f"{value}d"
                elif unit == "h":
                    aggregation_period = f"{value}h"
                elif unit == "m":
                    aggregation_period = f"{value}m"

            if aggregation_period:
                # OHLCV聚合策略
                flux_query += f"""
                // 分别进行开、高、低、收、量的聚合
                open_data = (tables=<-) 
                    |> filter(fn: (r) => r["_field"] == "open")
                    |> aggregateWindow(every: {aggregation_period}, fn: first, createEmpty: false)
                    |> set(key: "_field", value: "open")
                
                high_data = (tables=<-) 
                    |> filter(fn: (r) => r["_field"] == "high")
                    |> aggregateWindow(every: {aggregation_period}, fn: max, createEmpty: false)
                    |> set(key: "_field", value: "high")
                
                low_data = (tables=<-) 
                    |> filter(fn: (r) => r["_field"] == "low")
                    |> aggregateWindow(every: {aggregation_period}, fn: min, createEmpty: false)
                    |> set(key: "_field", value: "low")
                
                close_data = (tables=<-) 
                    |> filter(fn: (r) => r["_field"] == "close")
                    |> aggregateWindow(every: {aggregation_period}, fn: last, createEmpty: false)
                    |> set(key: "_field", value: "close")
                
                volume_data = (tables=<-) 
                    |> filter(fn: (r) => r["_field"] == "volume")
                    |> aggregateWindow(every: {aggregation_period}, fn: sum, createEmpty: false)
                    |> set(key: "_field", value: "volume")
                
                // 合并所有数据
                union(tables: [open_data, high_data, low_data, close_data, volume_data])
                    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                """
            else:
                # 对于无法识别的间隔，使用默认查询
                flux_query += """
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                """
        else:
            # 日K线不需要聚合，直接使用原始数据
            flux_query += """
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            """

        # 执行查询
        result = query_api.query_data_frame(flux_query)

        if result is None or (isinstance(result, pd.DataFrame) and result.empty):
            print(f"未能获取到 {symbol} 的数据")
            return None

        # 转换为DataFrame
        df = result.copy()

        # 设置索引
        if "_time" in df.columns:
            df.set_index("_time", inplace=True)

        # 确保数据包含必要的列
        required_columns = ["open", "high", "low", "close", "volume"]
        for col in required_columns:
            if col not in df.columns:
                print(f"警告: 数据中缺少 {col} 列")

        # 关闭客户端连接
        client.close()

        print(f"成功获取 {len(df)} 条历史数据 (间隔: {interval})")
        return df

    except Exception as e:
        print(f"从InfluxDB获取数据时出错: {e}")
        import traceback

        traceback.print_exc()
        return None


def identify_market_type(symbol):
    """识别股票代码的市场类型

    参数:
    symbol: str - 股票代码，可能带有后缀(.SH, .SZ, .HK, .US等)

    返回:
    tuple - (市场类型, 处理后的代码)
    """
    # 初始化为默认A股市场
    market_type = "A"
    ts_code = symbol

    # 根据代码特征判断市场类型
    if symbol.endswith(".HK"):
        market_type = "HK"
        ts_code = symbol  # 港股代码保持原样
    elif symbol.endswith(".US"):
        market_type = "US"
        ts_code = symbol[:-3]  # 去掉.US后缀
    elif symbol.startswith("6"):
        market_type = "A"
        ts_code = f"{symbol}.SH"  # 上海证券交易所
    else:
        market_type = "A"
        ts_code = f"{symbol}.SZ"  # 深圳证券交易所

    return market_type, ts_code


def get_tushare_data(pro, market_type, ts_code, interval, start_date, end_date):
    """根据市场类型和K线间隔获取数据

    参数:
    pro - TuShare API实例
    market_type: str - 市场类型 ("US", "HK", "A")
    ts_code: str - 股票代码
    interval: str - K线间隔
    start_date: str - 开始日期
    end_date: str - 结束日期

    返回:
    pandas.DataFrame - 获取的数据
    """
    if interval == "1d":
        # 日线数据
        if market_type == "US":
            return pro.us_daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )
        elif market_type == "HK":
            return pro.hk_daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )
        else:  # A股
            return pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    elif interval == "1w":
        # 周线数据
        if market_type == "US":
            print("美股暂不支持周线数据，将使用日线数据代替")
            return pro.us_daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )
        elif market_type == "HK":
            print("港股暂不支持周线数据，将使用日线数据代替")
            return pro.hk_daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )
        else:  # A股
            return pro.weekly(ts_code=ts_code, start_date=start_date, end_date=end_date)
    elif interval == "1mo":
        # 月线数据
        if market_type == "US":
            print("美股暂不支持月线数据，将使用日线数据代替")
            return pro.us_daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )
        elif market_type == "HK":
            print("港股暂不支持月线数据，将使用日线数据代替")
            return pro.hk_daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )
        else:  # A股
            return pro.monthly(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )
    else:
        # 默认使用日线数据
        print(f"不支持的K线间隔: {interval}，使用默认日线数据")
        return get_tushare_data(pro, market_type, ts_code, "1d", start_date, end_date)


def get_stock_data_from_tushare(
    symbol,
    period="-1y",
    interval="1d",
    tushare_token="d00a9271e726db72d5dcbc6edeabc9abeba3b4102aa1bb26cdadb20c",
):
    """从TuShare获取股票历史数据

    参数:
    symbol: str - 股票代码 (例如: "600519", "000001", "AAPL.US", "00700.HK")
    period: str - 时间周期 (例如: "-1y"表示过去一年, 支持y, mo, w, d单位)
    interval: str - K线间隔 ("1d"=日线, "1w"=周线, "1mo"=月线)
    tushare_token: str - TuShare API token

    返回:
    pandas.DataFrame - 包含股票数据的DataFrame，索引为日期，列包含OHLCV
    """
    print(f"从TuShare获取 {symbol} 的历史数据...")

    # 初始化TuShare API
    try:
        pro = ts.pro_api(tushare_token)
    except Exception as e:
        print(f"初始化TuShare API出错: {e}")
        return None

    # 计算时间范围
    end_time = datetime.now()

    if period.startswith("-"):  # 处理负数周期（如"-1y"表示过去一年）
        period = period[1:]

    if period.endswith("y"):
        years = int(period[:-1])
        start_time = end_time - timedelta(days=years * 365)
    elif period.endswith("mo"):
        months = int(period[:-2])
        start_time = end_time - timedelta(days=months * 30)
    elif period.endswith("w"):
        weeks = int(period[:-1])
        start_time = end_time - timedelta(weeks=weeks)
    elif period.endswith("d"):
        days = int(period[:-1])
        start_time = end_time - timedelta(days=days)
    else:
        print(f"不支持的周期格式: {period}")
        return None

    # 格式化日期为TuShare支持的格式
    start_date = start_time.strftime("%Y%m%d")
    end_date = end_time.strftime("%Y%m%d")

    try:
        # 识别市场类型和标准化代码
        market_type, ts_code = identify_market_type(symbol)

        # 获取数据
        df = get_tushare_data(pro, market_type, ts_code, interval, start_date, end_date)

        if df is None or df.empty:
            print(f"未能获取到 {symbol} 的数据")
            return None

        # 处理返回的数据，TuShare API返回的数据需要转换
        # 将trade_date列转换为datetime并设为索引
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        # 按日期升序排序
        df = df.sort_values("trade_date")
        # 设置日期为索引
        df = df.set_index("trade_date")

        # 重命名列以匹配ChartAnalyzer需要的格式
        df = df.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "vol": "Volume",
                "change": "change",
                "pct_chg": "pct_change",
            }
        )

        print(f"成功获取 {len(df)} 条历史数据 (间隔: {interval})")
        return df

    except Exception as e:
        print(f"从TuShare获取数据时出错: {e}")
        traceback.print_exc()
        return None


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="基于缠论理论分析股票中枢")
    parser.add_argument("symbol", type=str, help="股票代码 (例如: 600519, 000001)")
    parser.add_argument("--period", type=str, default="1y", help="数据周期 (默认: 1y)")
    parser.add_argument("--interval", type=str, default="1d", help="K线间隔 (默认: 1d)")
    parser.add_argument(
        "--source",
        type=str,
        default="tushare",
        help="数据源 (默认: tushare, 可选: influx)",
    )
    parser.add_argument("--token", type=str, help="TuShare API Token")
    args = parser.parse_args()

    # 获取数据
    if args.source.lower() == "influx":
        # 从InfluxDB获取数据
        data = get_stock_data(
            symbol=args.symbol,
            period=args.period,
            interval=args.interval,
            # influx_bucket="bssaa",
            # influx_measurement="stock_index",
        )
    else:
        # 从TuShare获取数据
        data = get_stock_data_from_tushare(
            symbol=args.symbol,
            period=args.period,
            interval=args.interval,
            tushare_token=(
                args.token
                if args.token
                else "d00a9271e726db72d5dcbc6edeabc9abeba3b4102aa1bb26cdadb20c"
            ),
        )

    if data is None:
        return

    # 创建分析器
    analyzer = ChartAnalyzer(data)

    # 打印当前状态
    analyzer.print_current_status()  # 尝试获取股票名称 (仅当使用 TuShare 时)
    symbol_name = None
    # if args.source.lower() != "influx":
    #     try:
    #         # 初始化TuShare API
    #         token = (
    #             args.token
    #             if args.token
    #             else "d00a9271e726db72d5dcbc6edeabc9abeba3b4102aa1bb26cdadb20c"
    #         )
    #         pro = ts.pro_api(token)

    #         # 使用辅助函数识别市场类型和处理代码
    #         market_type, ts_code = identify_market_type(args.symbol)

    #     # 根据市场类型获取股票名称
    #     if market_type == "HK":
    #         # 港股
    #         try:
    #             stock_info = pro.hk_basic(ts_code=ts_code, fields="ts_code,name")
    #         except:
    #             print("获取港股名称失败，可能接口不存在")
    #             stock_info = pd.DataFrame()
    #     elif market_type == "US":
    #         # 美股
    #         try:
    #             stock_info = pro.us_basic(ts_code=ts_code, fields="ts_code,name")
    #         except:
    #             print("获取美股名称失败，可能接口不存在")
    #             stock_info = pd.DataFrame()
    #     elif market_type == "A":
    #         # A股
    #         stock_info = pro.stock_basic(ts_code=ts_code, fields="ts_code,name")
    #     else:
    #         print(f"无法识别的市场类型: {market_type}")
    #         stock_info = pd.DataFrame()
    #     if not stock_info.empty:
    #         symbol_name = stock_info["name"].iloc[0]
    #         print(f"股票名称: {symbol_name}")
    # except Exception as e:
    #     print(f"获取股票名称失败: {e}")

    # 绘制分析结果
    analyzer.plot_analysis(symbol_code=args.symbol, symbol_name=symbol_name)


if __name__ == "__main__":
    main()
