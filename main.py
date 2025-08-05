import yfinance as yf
import time
import os
import sys
import csv
import json
from datetime import datetime
import pytz
from colorama import init, Fore, Style, Back

init(autoreset=True)


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def get_stock_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        
        hist = stock.history(period="2d")
        if hist.empty:
            return None
            
        current_price = hist['Close'].iloc[-1]
        previous_close = hist['Close'].iloc[0] if len(hist) > 1 else current_price
        
        change = current_price - previous_close
        change_percent = (change / previous_close) * 100 if previous_close != 0 else 0
        
        info = stock.info
        day_high = info.get('dayHigh', hist['High'].iloc[-1])
        day_low = info.get('dayLow', hist['Low'].iloc[-1])
        volume = info.get('volume', hist['Volume'].iloc[-1])
        
        return {
            'symbol': symbol,
            'current_price': current_price,
            'previous_close': previous_close,
            'change': change,
            'change_percent': change_percent,
            'day_high': day_high,
            'day_low': day_low,
            'volume': volume,
            'timestamp': datetime.now()
        }
        
    except Exception as e:
        return None


def format_number(num):
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.2f}K"
    else:
        return f"{num:.2f}"


def display_header():
    print(f"\n{Fore.CYAN}{'=' * 90}")
    print(f"{Fore.WHITE}{Style.BRIGHT}{'STOCK MARKET MONITOR':^90}")
    print(f"{Fore.CYAN}{'=' * 90}")
    print(f"{Fore.WHITE}Last Update: {Fore.YELLOW}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Fore.CYAN}{'-' * 90}\n")


def display_table_header():
    headers = ['Symbol', 'Price', 'Change', '% Change', 'Volume', 'Day Range', 'Current Position']
    widths = [8, 10, 10, 10, 12, 20, 20]
    
    header_line = ""
    for header, width in zip(headers, widths):
        header_line += f"{Fore.WHITE}{Style.BRIGHT}{header:^{width}}"
    
    print(header_line)
    print(f"{Fore.CYAN}{'-' * 90}")


def display_stock_row(data):
    if not data:
        return
    
    is_up = data['change'] >= 0
    color = Fore.GREEN if is_up else Fore.RED
    arrow = "^" if is_up else "v"
    
    # Format values
    symbol = f"{Fore.WHITE}{Style.BRIGHT}{data['symbol']:<8}"
    price = f"{Fore.WHITE}${data['current_price']:>8.2f}"
    
    change_sign = "+" if is_up else ""
    change = f"{color}{arrow} {change_sign}${abs(data['change']):>6.2f}"
    percent = f"{color}{change_sign}{data['change_percent']:>6.2f}%"
    
    volume = f"{Fore.WHITE}{format_number(data['volume']):>12}"
    day_range = f"{Fore.WHITE}${data['day_low']:.2f}-${data['day_high']:.2f}"
    
    # Calculate position in day range
    day_range_val = data['day_high'] - data['day_low']
    if day_range_val > 0:
        position = (data['current_price'] - data['day_low']) / day_range_val
        bar_length = 15
        filled = int(position * bar_length)
        position_bar = f"{Fore.BLUE}[{color}{'#' * filled}{Fore.WHITE}{'-' * (bar_length - filled)}{Fore.BLUE}]"
    else:
        position_bar = f"{Fore.BLUE}[{Fore.WHITE}{'-' * 15}{Fore.BLUE}]"
    
    print(f"{symbol} {price} {change} {percent} {volume} {day_range:<20} {position_bar}")


def display_footer():
    print(f"\n{Fore.CYAN}{'=' * 90}\n")


def log_to_csv(data, log_dir):
    if not data:
        return
    
    # Create filename based on current date
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = os.path.join(log_dir, f'stock_data_{date_str}.csv')
    
    # Check if file exists to determine if we need to write headers
    file_exists = os.path.exists(filename)
    
    # Write data to CSV
    with open(filename, 'a', newline='') as csvfile:
        fieldnames = ['timestamp', 'symbol', 'price', 'volume', 'change', 'change_percent', 'day_high', 'day_low']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        # Write header if file is new
        if not file_exists:
            writer.writeheader()
        
        # Write the data row
        writer.writerow({
            'timestamp': data['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': data['symbol'],
            'price': data['current_price'],
            'volume': data['volume'],
            'change': data['change'],
            'change_percent': data['change_percent'],
            'day_high': data['day_high'],
            'day_low': data['day_low']
        })


def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"{Fore.RED}Error: config.json not found. Using default configuration.")
        return {
            "stocks": ["AAPL", "GOOGL", "MSFT"],
            "update_interval": 5,
            "logging": {"enabled": True, "directory": "data"},
            "market_hours": {
                "timezone": "America/New_York",
                "open_time": "09:30",
                "close_time": "16:00",
                "monitor_outside_hours": False
            }
        }


def is_market_hours(config):
    market_config = config.get('market_hours', {})
    if market_config.get('monitor_outside_hours', False):
        return True
    
    tz = pytz.timezone(market_config.get('timezone', 'America/New_York'))
    now = datetime.now(tz)
    
    # Check if it's a weekday (Monday = 0, Sunday = 6)
    if now.weekday() > 4:  # Saturday or Sunday
        return False
    
    # Parse market hours
    open_time = datetime.strptime(market_config.get('open_time', '09:30'), '%H:%M').time()
    close_time = datetime.strptime(market_config.get('close_time', '16:00'), '%H:%M').time()
    
    current_time = now.time()
    return open_time <= current_time <= close_time


def main():
    # Load configuration
    config = load_config()
    symbols = config.get('stocks', ["AAPL", "GOOGL", "MSFT"])
    update_interval = config.get('update_interval', 5)
    logging_enabled = config.get('logging', {}).get('enabled', True)
    log_dir = config.get('logging', {}).get('directory', 'data')
    
    # Create log directory if it doesn't exist
    if logging_enabled and log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    print(f"{Fore.CYAN}{Style.BRIGHT}Starting Stock Market Monitor")
    print(f"{Fore.WHITE}Monitoring: {Fore.YELLOW}{', '.join(symbols)}")
    print(f"{Fore.WHITE}Update Interval: {Fore.YELLOW}{update_interval} seconds")
    print(f"{Fore.WHITE}Logging: {Fore.YELLOW}{'Enabled' if logging_enabled else 'Disabled'}")
    print(f"{Fore.WHITE}Market Hours: {Fore.YELLOW}{config['market_hours']['open_time']} - {config['market_hours']['close_time']} ET")
    print(f"{Fore.WHITE}Press {Fore.RED}Ctrl+C{Fore.WHITE} to stop\n")
    
    time.sleep(2)
    
    try:
        while True:
            # Check if we're within market hours
            if not is_market_hours(config):
                clear_screen()
                display_header()
                
                # Get timezone for display
                tz = pytz.timezone(config['market_hours']['timezone'])
                now = datetime.now(tz)
                
                print(f"{Fore.YELLOW}{Style.BRIGHT}Market is CLOSED")
                print(f"{Fore.WHITE}Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"{Fore.WHITE}Market hours: {config['market_hours']['open_time']} - {config['market_hours']['close_time']} ET (Mon-Fri)")
                print(f"\n{Fore.WHITE}Waiting for market to open...")
                
                # Wait 60 seconds before checking again
                for i in range(60, 0, -1):
                    print(f"\r{Fore.WHITE}Checking again in {i} seconds...  ", end="", flush=True)
                    time.sleep(1)
                continue
            
            clear_screen()
            display_header()
            display_table_header()
            
            # Fetch and display data for all stocks
            for symbol in symbols:
                data = get_stock_data(symbol)
                display_stock_row(data)
                # Log data to CSV if enabled
                if data and logging_enabled:
                    log_to_csv(data, log_dir)
            
            display_footer()
            
            # Show logging status
            if logging_enabled:
                date_str = datetime.now().strftime('%Y-%m-%d')
                csv_file = os.path.join(log_dir, f'stock_data_{date_str}.csv')
                print(f"{Fore.GREEN}[OK] Data logged to: {Fore.YELLOW}{csv_file}")
            else:
                print(f"{Fore.YELLOW}[INFO] Data logging is disabled")
            
            print(f"{Fore.WHITE}Next update in {update_interval} seconds...")
            
            # Countdown timer
            for i in range(update_interval, 0, -1):
                print(f"\r{Fore.WHITE}Next update in {i} seconds...  ", end="", flush=True)
                time.sleep(1)
                
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Stock monitor stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()