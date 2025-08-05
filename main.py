import yfinance as yf
import time
import os
import sys
import csv
import json
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import winsound  # For beep on Windows
from colorama import init, Fore, Style, Back

init(autoreset=True)


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    
    deltas = np.diff(prices)
    gains = deltas.copy()
    losses = deltas.copy()
    gains[gains < 0] = 0
    losses[losses > 0] = 0
    losses = abs(losses)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def get_stock_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        
        # Fetch 30 days of data for technical indicators
        hist = stock.history(period="1mo")
        if hist.empty or len(hist) < 20:
            return None
            
        current_price = hist['Close'].iloc[-1]
        previous_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        
        change = current_price - previous_close
        change_percent = (change / previous_close) * 100 if previous_close != 0 else 0
        
        # Today's data
        info = stock.info
        day_high = info.get('dayHigh', hist['High'].iloc[-1])
        day_low = info.get('dayLow', hist['Low'].iloc[-1])
        volume = info.get('volume', hist['Volume'].iloc[-1])
        
        # Calculate technical indicators
        sma_20 = hist['Close'].tail(20).mean()
        
        # RSI calculation
        rsi = calculate_rsi(hist['Close'].values)
        
        # Volume average (20-day)
        vol_avg_20 = hist['Volume'].tail(20).mean()
        vol_ratio = (volume / vol_avg_20) if vol_avg_20 > 0 else 1
        
        # Distance from high/low as percentage
        day_range = day_high - day_low
        if day_range > 0:
            pct_from_high = ((day_high - current_price) / day_high) * 100
            pct_from_low = ((current_price - day_low) / day_low) * 100
        else:
            pct_from_high = 0
            pct_from_low = 0
        
        return {
            'symbol': symbol,
            'current_price': current_price,
            'previous_close': previous_close,
            'change': change,
            'change_percent': change_percent,
            'day_high': day_high,
            'day_low': day_low,
            'volume': volume,
            'sma_20': sma_20,
            'rsi': rsi,
            'vol_ratio': vol_ratio,
            'pct_from_high': pct_from_high,
            'pct_from_low': pct_from_low,
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
    print(f"\n{Fore.CYAN}{'=' * 150}")
    print(f"{Fore.WHITE}{Style.BRIGHT}{'STOCK MARKET MONITOR WITH TECHNICAL INDICATORS':^150}")
    print(f"{Fore.CYAN}{'=' * 150}")
    print(f"{Fore.WHITE}Last Update: {Fore.YELLOW}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Fore.CYAN}{'-' * 150}\n")


def display_table_header():
    headers = ['Symbol', 'Price', 'Change', '%Chg', 'SMA(20)', 'RSI(14)', 'Vol/Avg', 'Range', '%High', '%Low']
    widths = [8, 10, 10, 8, 10, 8, 8, 18, 8, 8]
    
    header_line = ""
    for header, width in zip(headers, widths):
        header_line += f"{Fore.WHITE}{Style.BRIGHT}{header:^{width}}"
    
    print(header_line)
    print(f"{Fore.CYAN}{'-' * 150}")


def display_stock_row(data):
    if not data:
        return
    
    is_up = data['change'] >= 0
    color = Fore.GREEN if is_up else Fore.RED
    arrow = "^" if is_up else "v"
    
    # Format basic values
    symbol = f"{Fore.WHITE}{Style.BRIGHT}{data['symbol']:<8}"
    price = f"{Fore.WHITE}${data['current_price']:>8.2f}"
    
    change_sign = "+" if is_up else ""
    change = f"{color}{arrow} {change_sign}${abs(data['change']):>6.2f}"
    percent = f"{color}{change_sign}{data['change_percent']:>5.2f}%"
    
    # Format SMA
    sma = f"{Fore.WHITE}${data['sma_20']:>8.2f}"
    
    # Format RSI with color coding
    rsi_val = data['rsi']
    if rsi_val is not None:
        if rsi_val >= 70:
            rsi_color = Fore.RED  # Overbought
        elif rsi_val <= 30:
            rsi_color = Fore.GREEN  # Oversold
        else:
            rsi_color = Fore.WHITE
        rsi = f"{rsi_color}{rsi_val:>6.1f}"
    else:
        rsi = f"{Fore.WHITE}{'N/A':>6}"
    
    # Volume ratio
    vol_ratio = data['vol_ratio']
    if vol_ratio >= 1.5:
        vol_color = Fore.YELLOW  # High volume
    elif vol_ratio <= 0.5:
        vol_color = Fore.CYAN  # Low volume
    else:
        vol_color = Fore.WHITE
    vol_str = f"{vol_color}{vol_ratio:>6.2f}x"
    
    # Day range
    day_range = f"{Fore.WHITE}${data['day_low']:.2f}-${data['day_high']:.2f}"
    
    # Distance from high/low
    pct_high = f"{Fore.RED}{data['pct_from_high']:>6.2f}%"
    pct_low = f"{Fore.GREEN}{data['pct_from_low']:>6.2f}%"
    
    # Headers: ['Symbol', 'Price', 'Change', '%Chg', 'SMA(20)', 'RSI(14)', 'Vol/Avg', 'Range', '%High', '%Low']
    # Widths:  [8, 10, 10, 8, 10, 8, 8, 18, 8, 8]
    
    print(f"{symbol} {price} {change} {percent} {sma} {rsi} {vol_str} {day_range:<18} {pct_high} {pct_low}")


def display_footer():
    print(f"\n{Fore.CYAN}{'=' * 150}\n")


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
        fieldnames = ['timestamp', 'symbol', 'price', 'volume', 'change', 'change_percent', 
                     'day_high', 'day_low', 'sma_20', 'rsi_14', 'volume_ratio', 
                     'pct_from_high', 'pct_from_low']
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
            'day_low': data['day_low'],
            'sma_20': data['sma_20'],
            'rsi_14': data['rsi'] if data['rsi'] is not None else '',
            'volume_ratio': data['vol_ratio'],
            'pct_from_high': data['pct_from_high'],
            'pct_from_low': data['pct_from_low']
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


def load_alerts():
    try:
        with open('alerts.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print(f"{Fore.YELLOW}Warning: alerts.json is invalid. No alerts loaded.")
        return {}


def check_alerts(data, alerts, triggered_alerts):
    if not data or data['symbol'] not in alerts:
        return []
    
    symbol = data['symbol']
    price = data['current_price']
    alert_config = alerts[symbol]
    new_alerts = []
    
    # Check above threshold
    if 'above' in alert_config and price >= alert_config['above']:
        alert_key = f"{symbol}_above_{alert_config['above']}"
        if alert_key not in triggered_alerts:
            new_alerts.append({
                'symbol': symbol,
                'type': 'ABOVE',
                'threshold': alert_config['above'],
                'price': price,
                'timestamp': datetime.now()
            })
            triggered_alerts.add(alert_key)
    
    # Check below threshold
    if 'below' in alert_config and price <= alert_config['below']:
        alert_key = f"{symbol}_below_{alert_config['below']}"
        if alert_key not in triggered_alerts:
            new_alerts.append({
                'symbol': symbol,
                'type': 'BELOW',
                'threshold': alert_config['below'],
                'price': price,
                'timestamp': datetime.now()
            })
            triggered_alerts.add(alert_key)
    
    return new_alerts


def display_alert(alert):
    alert_color = Fore.RED if alert['type'] == 'ABOVE' else Fore.YELLOW
    print(f"\n{alert_color}{Style.BRIGHT}" + "=" * 60)
    print(f"{alert_color}{Style.BRIGHT}🚨 PRICE ALERT: {alert['symbol']} - {alert['type']} ${alert['threshold']:.2f}")
    print(f"{alert_color}{Style.BRIGHT}Current Price: ${alert['price']:.2f}")
    print(f"{alert_color}{Style.BRIGHT}" + "=" * 60 + f"{Style.RESET_ALL}\n")
    
    # Beep sound (Windows)
    try:
        if sys.platform == 'win32':
            winsound.Beep(1000, 300)  # 1000 Hz for 300 ms
    except:
        pass


def log_alert(alert, alert_log_file='alerts_log.txt'):
    with open(alert_log_file, 'a') as f:
        f.write(f"{alert['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} - ")
        f.write(f"{alert['symbol']} {alert['type']} ${alert['threshold']:.2f} ")
        f.write(f"(Price: ${alert['price']:.2f})\n")


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
    alerts = load_alerts()
    triggered_alerts = set()  # Track already triggered alerts
    
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
    print(f"{Fore.WHITE}Alerts: {Fore.YELLOW}{len(alerts)} stocks configured")
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
            all_alerts = []
            for symbol in symbols:
                data = get_stock_data(symbol)
                display_stock_row(data)
                # Log data to CSV if enabled
                if data and logging_enabled:
                    log_to_csv(data, log_dir)
                # Check for alerts
                new_alerts = check_alerts(data, alerts, triggered_alerts)
                all_alerts.extend(new_alerts)
            
            display_footer()
            
            # Display and log any triggered alerts
            for alert in all_alerts:
                display_alert(alert)
                log_alert(alert)
            
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