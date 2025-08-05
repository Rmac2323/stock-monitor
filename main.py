import yfinance as yf
import time
import os
import sys
from datetime import datetime
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


def main():
    symbols = ["AAPL", "TSLA", "NVDA", "SPY"]
    update_interval = 30
    
    print(f"{Fore.CYAN}{Style.BRIGHT}Starting Stock Market Monitor")
    print(f"{Fore.WHITE}Monitoring: {Fore.YELLOW}{', '.join(symbols)}")
    print(f"{Fore.WHITE}Update Interval: {Fore.YELLOW}{update_interval} seconds")
    print(f"{Fore.WHITE}Press {Fore.RED}Ctrl+C{Fore.WHITE} to stop\n")
    
    time.sleep(2)
    
    try:
        while True:
            clear_screen()
            display_header()
            display_table_header()
            
            # Fetch and display data for all stocks
            for symbol in symbols:
                data = get_stock_data(symbol)
                display_stock_row(data)
            
            display_footer()
            
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