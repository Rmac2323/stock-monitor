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
        print(f"{Fore.RED}Error fetching data: {e}")
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


def display_stock_data(data):
    if not data:
        print(f"{Fore.RED}Unable to fetch stock data")
        return
    
    is_up = data['change'] >= 0
    color = Fore.GREEN if is_up else Fore.RED
    arrow = "^" if is_up else "v"
    
    clear_screen()
    
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"{Fore.WHITE}{Style.BRIGHT}  STOCK PRICE MONITOR - {data['symbol']}")
    print(f"{Fore.CYAN}{'=' * 60}\n")
    
    print(f"{Fore.WHITE}  Last Update: {Fore.YELLOW}{data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n{Fore.CYAN}{'-' * 60}\n")
    
    print(f"{Fore.WHITE}  Current Price:     {Style.BRIGHT}{color}${data['current_price']:.2f}")
    print(f"{Fore.WHITE}  Previous Close:    ${data['previous_close']:.2f}")
    print()
    
    change_sign = "+" if is_up else ""
    print(f"{Fore.WHITE}  Change:           {color}{arrow} {change_sign}${abs(data['change']):.2f} ({change_sign}{data['change_percent']:.2f}%)")
    print()
    
    print(f"{Fore.WHITE}  Day Range:        ${data['day_low']:.2f} - ${data['day_high']:.2f}")
    print(f"{Fore.WHITE}  Volume:           {format_number(data['volume'])}")
    
    print(f"\n{Fore.CYAN}{'-' * 60}")
    
    day_range = data['day_high'] - data['day_low']
    if day_range > 0:
        position = (data['current_price'] - data['day_low']) / day_range
        bar_length = 40
        filled = int(position * bar_length)
        
        print(f"\n{Fore.WHITE}  Day Range Progress:")
        print(f"  Low ${data['day_low']:.2f} ", end="")
        print(f"{Fore.BLUE}[", end="")
        print(f"{color}{'#' * filled}", end="")
        print(f"{Fore.WHITE}{'-' * (bar_length - filled)}", end="")
        print(f"{Fore.BLUE}]", end="")
        print(f" High ${data['day_high']:.2f}")
    
    print(f"\n{Fore.CYAN}{'=' * 60}\n")


def main():
    symbol = "AAPL"
    update_interval = 30
    
    print(f"{Fore.CYAN}{Style.BRIGHT}Starting Stock Price Monitor")
    print(f"{Fore.WHITE}Monitoring: {Fore.YELLOW}{symbol}")
    print(f"{Fore.WHITE}Update Interval: {Fore.YELLOW}{update_interval} seconds")
    print(f"{Fore.WHITE}Press {Fore.RED}Ctrl+C{Fore.WHITE} to stop\n")
    
    time.sleep(2)
    
    try:
        while True:
            data = get_stock_data(symbol)
            display_stock_data(data)
            
            print(f"{Fore.WHITE}  Next update in {update_interval} seconds...")
            
            for i in range(update_interval, 0, -1):
                print(f"\r{Fore.WHITE}  Next update in {i} seconds...  ", end="", flush=True)
                time.sleep(1)
                
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Stock monitor stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()