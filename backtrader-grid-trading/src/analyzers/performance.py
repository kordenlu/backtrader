class PerformanceAnalyzer(bt.Analyzer):
    def __init__(self):
        self.total_return = 0.0
        self.max_drawdown = 0.0
        self.pnl = []

    def start(self):
        self.pnl = []

    def next(self):
        if self.strategy.position:
            self.pnl.append(self.strategy.position.pnl)

    def stop(self):
        self.total_return = self.pnl[-1] if self.pnl else 0.0
        self.max_drawdown = self.calculate_max_drawdown(self.pnl)

    def calculate_max_drawdown(self, pnl):
        max_drawdown = 0.0
        peak = pnl[0]
        for value in pnl:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        return max_drawdown

    def get_analysis(self):
        return {
            'total_return': self.total_return,
            'max_drawdown': self.max_drawdown,
        }