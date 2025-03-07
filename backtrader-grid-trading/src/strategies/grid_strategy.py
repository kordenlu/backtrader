import backtrader as bt


class GridStrategy(bt.Strategy):
    params = (
        ("grid_size", 0.02),  # 网格大小，以百分比表示
        ("take_profit", 0.05),  # 止盈百分比
        ("stop_loss", 0.03),  # 止损百分比
        ("base_price", None),  # 基准价格
        ("position_size", 100),  # 每格基础仓位大小
        ("position_sizing", "fixed"),  # 仓位计算方式: fixed/percent/pyramiding
        ("percent_cash", 0.1),  # 按资金百分比计算仓位时使用
        ("pyramiding_factor", 0.8),  # 金字塔仓位系数
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.buyprice = None
        self.buycomm = None

        # 初始化网格价格数组
        self.base_price = None
        self.grid_lines = []
        self.current_position = 0
        # 仓位跟踪
        self.grid_positions = {}  # 记录每个网格的持仓量 {grid_index: position_size}
        self.total_position = 0  # 总持仓量

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()}, {txt}")

    def calculate_position_size(self, grid_index):
        """计算特定网格的仓位大小"""
        if self.p.position_sizing == "fixed":
            # 固定仓位大小
            return self.p.position_size

        elif self.p.position_sizing == "percent":
            # 按账户资金百分比计算仓位
            cash = self.broker.getcash()
            current_price = self.dataclose[0]
            return int((cash * self.p.percent_cash) / current_price)

        elif self.p.position_sizing == "pyramiding":
            # 金字塔式仓位：离中心越远，仓位越小
            distance = abs(grid_index - 10)  # 与中心网格的距离
            factor = self.p.pyramiding_factor**distance
            return int(self.p.position_size * factor)

        return self.p.position_size  # 默认返回固定仓位

    def start(self):
        """策略启动时调用，数据已加载但尚未开始处理"""
        # 设置基准价格
        if self.p.base_price is not None:
            self.base_price = self.p.base_price
            # 确保基准价格有效
            if self.base_price <= 0:
                self.base_price = self.data.close[0]  # 使用第一天收盘价

            self.create_grid_lines()
            self.log(f"初始化网格，基准价格(预设): {self.base_price:.2f}")

    def next(self):
        """策略核心，每个交易日调用"""
        # 如果有未完成订单，等待
        if self.order:
            return

        # 检查当前价格是否触发网格交易
        self.check_grid_trading()

    def create_grid_lines(self):
        """创建网格线"""
        # 生成10个向上和10个向下的网格线
        for i in range(-10, 11):
            grid_price = self.base_price * (1 + i * self.p.grid_size)
            self.grid_lines.append(grid_price)
        self.grid_lines.sort()  # 按价格升序排列
        self.current_position = 10  # 中间位置（基准价格的索引）

    def check_grid_trading(self):
        """检查价格是否触发网格交易"""
        current_price = self.dataclose[0]

        # 安全检查：确保网格线已创建且索引有效
        if not self.grid_lines:
            self.log("警告：网格线未初始化，跳过网格交易检查")
            return

        if self.position.size <= 0:  # 没有持仓或空仓
            # 检查是否满足买入条件
            if current_price <= self.grid_lines[self.current_position - 1]:
                self.current_position -= 1

                # 计算买入数量
                size = self.calculate_position_size(self.current_position)

                # 检查是否有足够现金
                value = size * current_price
                if value > self.broker.getcash() * 0.95:  # 保留5%现金缓冲
                    size = int(self.broker.getcash() * 0.95 / current_price)

                if size > 0:
                    self.log(f"网格买入信号，价格: {current_price:.2f}, 数量: {size}")
                    self.order = self.buy(size=size)

                    # 记录此网格的持仓
                    self.grid_positions[self.current_position] = size
                    self.total_position += size

        else:  # 有持仓
            # 检查是否满足卖出条件
            if current_price >= self.grid_lines[self.current_position + 1]:
                self.current_position += 1

                # 获取要卖出的数量
                size_to_sell = self.grid_positions.get(self.current_position - 1, 0)
                if size_to_sell > 0:
                    self.log(
                        f"网格卖出信号，价格: {current_price:.2f}, 数量: {size_to_sell}"
                    )
                    self.order = self.sell(size=size_to_sell)

                    # 更新持仓记录
                    self.grid_positions[self.current_position - 1] = 0
                    self.total_position -= size_to_sell

            # 检查止盈止损
            if self.buyprice:  # 确保有买入价格记录
                profit_pct = (current_price - self.buyprice) / self.buyprice

                if profit_pct >= self.p.take_profit:
                    self.log(f"触发止盈，利润: {profit_pct:.2%}")
                    self.order = self.close()  # 平掉所有仓位
                    self.grid_positions = {}
                    self.total_position = 0

                elif profit_pct <= -self.p.stop_loss:
                    self.log(f"触发止损，亏损: {profit_pct:.2%}")
                    self.order = self.close()  # 平掉所有仓位
                    self.grid_positions = {}
                    self.total_position = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"买入执行，价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}"
                )
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:  # 卖出
                self.log(
                    f"卖出执行，价格: {order.executed.price:.2f}, 价值: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}"
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("订单被取消/保证金不足/拒绝")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"交易利润, 毛利: {trade.pnl:.2f}, 净利: {trade.pnlcomm:.2f}")
