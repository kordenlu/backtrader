def calculate_grid_levels(entry_price, grid_size, num_levels):
    levels = []
    for i in range(num_levels):
        levels.append(entry_price + (i * grid_size))
    return levels

def log_message(message, log_file='trading.log'):
    with open(log_file, 'a') as f:
        f.write(f"{message}\n")

def calculate_position_size(account_balance, risk_percentage, entry_price):
    risk_amount = account_balance * risk_percentage
    position_size = risk_amount / entry_price
    return position_size

def format_price(price):
    return f"{price:.2f}"