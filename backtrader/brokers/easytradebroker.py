import backtrader as bt
import datetime
import time

import easytrader
import logging
import threading


# 设置日志
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============== 2. 实盘交易Broker ===============
class LiveTradingBroker(bt.brokers.BackBroker):
    """实盘交易Broker，连接真实交易接口"""

    params = (
        ("broker_type", "ths"),  # 券商类型：ths=同花顺, xt=雪球
        ("broker_id", ""),  # 券商账号
        ("broker_pw", ""),  # 券商密码
        ("broker_exe", ""),  # 交易软件路径
        ("trade_delay", 1.0),  # 下单延迟(秒)
        ("sync_interval", 60),  # 持仓同步间隔(秒)
    )

    def __init__(self):
        super(LiveTradingBroker, self).__init__()
        self.trader = None
        self.last_sync = None
        self._cash = 0.0
        self._value = 0.0
        self._positions = {}  # 存储实盘持仓

        # 初始化实盘交易接口
        self._init_trader()

        # 开始持仓同步线程
        self._sync_thread = threading.Thread(target=self._sync_positions_thread)
        self._sync_thread.daemon = True
        self._sync_thread.start()

    def _init_trader(self):
        """初始化实盘交易接口"""
        try:
            # 创建easytrader接口
            self.trader = easytrader.use(self.p.broker_type)

            # 构建配置
            config = {"user": self.p.broker_id, "password": self.p.broker_pw}

            # 如果是同花顺，需要提供exe路径
            if self.p.broker_type == "ths" and self.p.broker_exe:
                config["exe_path"] = self.p.broker_exe

            # 连接交易接口
            self.trader.connect(config)
            logger.info("实盘交易接口连接成功")

            # 初始化同步账户信息
            self._sync_account()

        except Exception as e:
            logger.error(f"初始化交易接口失败: {e}")
            self.trader = None

    def _sync_positions_thread(self):
        """持仓同步线程"""
        while True:
            try:
                # 同步账户和持仓信息
                self._sync_account()
                self._sync_positions()

                # 记录同步时间
                self.last_sync = datetime.datetime.now()

            except Exception as e:
                logger.error(f"同步持仓信息出错: {e}")

            # 等待下次同步
            time.sleep(self.p.sync_interval)

    def _sync_account(self):
        """同步账户资金信息"""
        if self.trader is None:
            return

        try:
            balance = self.trader.balance
            if balance:
                # 更新资金信息
                self._cash = float(balance.get("资金余额", 0.0))
                self._value = float(balance.get("总资产", 0.0))
                logger.debug(
                    f"同步账户信息成功: 现金={self._cash}, 总资产={self._value}"
                )
        except Exception as e:
            logger.error(f"同步账户信息失败: {e}")

    def _sync_positions(self):
        """同步持仓信息"""
        if self.trader is None:
            return

        try:
            positions = self.trader.position
            self._positions.clear()

            for pos in positions:
                stock_code = pos.get("证券代码")
                if stock_code:
                    # 存储持仓信息
                    self._positions[stock_code] = {
                        "size": int(pos.get("股票余额", 0)),
                        "price": float(pos.get("成本价", 0.0)),
                        "current_price": float(pos.get("最新价", 0.0)),
                    }

            logger.debug(f"同步持仓信息成功: {len(self._positions)}个持仓")

        except Exception as e:
            logger.error(f"同步持仓信息失败: {e}")

    def get_cash(self):
        """获取可用资金"""
        return self._cash

    def get_value(self):
        """获取总资产"""
        return self._value

    def getposition(self, data, clone=True):
        """获取特定数据的持仓"""
        # 将data对象映射到股票代码
        stock_code = self._extract_stock_code(data)

        position = self._positions.get(stock_code, None)

        if position is not None:
            # 返回Position对象
            pos = bt.Position(size=position["size"], price=position["price"])
            return pos

        return bt.Position()  # 返回空持仓

    def _extract_stock_code(self, data):
        """从data对象提取股票代码"""
        if hasattr(data, "_name"):
            return data._name
        return None

    def buy(self, owner, data, size, price=None, plimit=None, **kwargs):
        """买入操作"""
        stock_code = self._extract_stock_code(data)

        # 未指定价格时使用市价
        if price is None:
            price = data.close[0]

        if self.trader is None or not stock_code:
            logger.error("交易接口未连接或股票代码无效")
            return None

        try:
            # 转换为easytrader接受的格式
            if stock_code.startswith("6"):
                full_code = f"sh{stock_code}"
            else:
                full_code = f"sz{stock_code}"

            # 执行实盘买入
            logger.info(f"发送买入委托: {full_code}, 价格={price}, 数量={size}")

            # 模拟交易延迟
            time.sleep(self.p.trade_delay)

            result = self.trader.buy(full_code, price=price, amount=size)
            logger.info(f"买入委托结果: {result}")

            # 创建Order对象
            order = bt.Order.Market(*args, **kwargs)
            order.addcomminfo(self.getcommissioninfo(data))
            order.addinfo(**kwargs)

            # 如果开启了延迟执行，请自行实现
            self._ococheck(order)  # 检查OCO订单

            # 计算可能的成交价格（考虑滑点等）
            # 这里简化处理，实际应根据成交回报确定
            executed_price = price

            # 创建执行对象
            order.execute(
                size,
                executed_price,
                0,
                0.0,
                0.0,
                0.0,
                0,
                0.0,
                0.0,
                0.0,
                0.0,
                size,
                executed_price,
            )

            # 发出通知
            self.notify(order)

            return order

        except Exception as e:
            logger.error(f"买入失败: {e}")
            return None

    def sell(self, owner, data, size, price=None, plimit=None, **kwargs):
        """卖出操作"""
        stock_code = self._extract_stock_code(data)

        # 未指定价格时使用市价
        if price is None:
            price = data.close[0]

        if self.trader is None or not stock_code:
            logger.error("交易接口未连接或股票代码无效")
            return None

        try:
            # 转换为easytrader接受的格式
            if stock_code.startswith("6"):
                full_code = f"sh{stock_code}"
            else:
                full_code = f"sz{stock_code}"

            # 执行实盘卖出
            logger.info(f"发送卖出委托: {full_code}, 价格={price}, 数量={size}")

            # 模拟交易延迟
            time.sleep(self.p.trade_delay)

            result = self.trader.sell(full_code, price=price, amount=size)
            logger.info(f"卖出委托结果: {result}")

            # 创建Order对象
            order = bt.Order.Market(*args, **kwargs)
            order.addcomminfo(self.getcommissioninfo(data))
            order.addinfo(**kwargs)

            # 如果开启了延迟执行，请自行实现
            self._ococheck(order)  # 检查OCO订单

            # 计算可能的成交价格（考虑滑点等）
            # 这里简化处理，实际应根据成交回报确定
            executed_price = price

            # 创建执行对象
            order.execute(
                size,
                executed_price,
                0,
                0.0,
                0.0,
                0.0,
                0,
                0.0,
                0.0,
                0.0,
                0.0,
                size,
                executed_price,
            )

            # 发出通知
            self.notify(order)

            return order

        except Exception as e:
            logger.error(f"卖出失败: {e}")
            return None
