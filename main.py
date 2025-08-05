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
import socket
import urllib.error
import threading
import queue
import msvcrt  # Windows keyboard input
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.align import Align
from rich.text import Text
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.columns import Columns
from rich.prompt import Prompt

console = Console()

# Global variables for thread communication
command_queue = queue.Queue()
paused = False
running = True


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


def log_error(error_msg, error_log_file='error_log.txt'):
    """Log errors to file with timestamp"""
    try:
        with open(error_log_file, 'a') as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {error_msg}\n")
    except:
        pass  # Fail silently if we can't write to log


def get_stock_data(symbol, retry_count=0, max_retries=3):
    """Fetch stock data with retry logic and comprehensive error handling"""
    try:
        stock = yf.Ticker(symbol)
        
        # Fetch 30 days of data for technical indicators
        hist = stock.history(period="1mo")
        if hist.empty or len(hist) < 20:
            if retry_count < max_retries:
                time.sleep(2)  # Brief pause before retry
                return get_stock_data(symbol, retry_count + 1, max_retries)
            log_error(f"{symbol}: No data available")
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
            'timestamp': datetime.now(),
            'status': 'OK'
        }
        
    except (socket.timeout, urllib.error.URLError, ConnectionError) as e:
        # Network-related errors
        error_msg = f"{symbol}: Network error - {type(e).__name__}"
        if retry_count < max_retries:
            time.sleep(5)  # Wait 5 seconds before retry
            return get_stock_data(symbol, retry_count + 1, max_retries)
        log_error(error_msg)
        return {'symbol': symbol, 'status': 'NETWORK_ERROR', 'error': str(e)}
        
    except Exception as e:
        # Other errors
        error_msg = f"{symbol}: {type(e).__name__} - {str(e)}"
        log_error(error_msg)
        if retry_count < max_retries:
            time.sleep(2)
            return get_stock_data(symbol, retry_count + 1, max_retries)
        return {'symbol': symbol, 'status': 'ERROR', 'error': str(e)}


def format_number(num):
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.2f}K"
    else:
        return f"{num:.2f}"


def create_stock_table(stocks_data):
    """Create a rich table with stock data"""
    table = Table(
        title="Stock Market Monitor",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title_style="bold white",
        caption=f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        caption_style="dim"
    )
    
    # Add columns
    table.add_column("Symbol", style="bold white", width=8)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Change", justify="right", width=10)
    table.add_column("%Chg", justify="right", width=8)
    table.add_column("SMA(20)", justify="right", style="dim", width=10)
    table.add_column("RSI(14)", justify="right", width=8)
    table.add_column("Vol/Avg", justify="right", style="dim", width=8)
    table.add_column("Range", justify="center", style="dim", width=18)
    table.add_column("%High", justify="right", style="red dim", width=8)
    table.add_column("%Low", justify="right", style="green dim", width=8)
    
    # Add rows
    for data in stocks_data:
        if not data:
            continue
            
        # Handle error cases
        if 'status' in data and data['status'] != 'OK':
            table.add_row(
                data['symbol'],
                "[red]Error[/red]",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-"
            )
            continue
        
        # Format values
        is_up = data['change'] >= 0
        change_color = "green" if is_up else "red"
        arrow = "^" if is_up else "v"
        
        price_str = f"${data['current_price']:.2f}"
        change_str = f"[{change_color}]{arrow} ${abs(data['change']):.2f}[/{change_color}]"
        percent_str = f"[{change_color}]{data['change_percent']:+.2f}%[/{change_color}]"
        
        sma_str = f"${data['sma_20']:.2f}"
        
        # RSI with color coding
        rsi_val = data['rsi']
        if rsi_val is not None:
            if rsi_val >= 70:
                rsi_str = f"[red]{rsi_val:.1f}[/red]"
            elif rsi_val <= 30:
                rsi_str = f"[green]{rsi_val:.1f}[/green]"
            else:
                rsi_str = f"{rsi_val:.1f}"
        else:
            rsi_str = "N/A"
        
        # Volume ratio
        vol_ratio = data['vol_ratio']
        if vol_ratio >= 1.5:
            vol_str = f"[yellow]{vol_ratio:.2f}x[/yellow]"
        elif vol_ratio <= 0.5:
            vol_str = f"[cyan]{vol_ratio:.2f}x[/cyan]"
        else:
            vol_str = f"{vol_ratio:.2f}x"
        
        range_str = f"${data['day_low']:.2f}-${data['day_high']:.2f}"
        pct_high_str = f"{data['pct_from_high']:.2f}%"
        pct_low_str = f"{data['pct_from_low']:.2f}%"
        
        table.add_row(
            data['symbol'],
            price_str,
            change_str,
            percent_str,
            sma_str,
            rsi_str,
            vol_str,
            range_str,
            pct_high_str,
            pct_low_str
        )
    
    return table


def create_header():
    """Create a header panel with current time"""
    now = datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    header_text = Text()
    header_text.append("STOCK MARKET MONITOR ", style="bold cyan")
    header_text.append("WITH TECHNICAL INDICATORS ", style="bold yellow")
    header_text.append(f"| {time_str}", style="dim white")
    
    return Panel(
        Align.center(header_text),
        box=box.DOUBLE,
        border_style="cyan",
        padding=(0, 1)
    )


def create_status_bar(config, alerts_count, last_update, paused):
    """Create a status bar with system info"""
    status_items = []
    
    # Paused status
    if paused:
        status_items.append("[yellow bold]PAUSED[/yellow bold]")
    
    # Market status
    if is_market_hours(config):
        status_items.append("[green]* Market Open[/green]")
    else:
        status_items.append("[red]* Market Closed[/red]")
    
    # Update interval
    status_items.append(f"Update: {config.get('update_interval', 5)}s")
    
    # Alerts
    if alerts_count > 0:
        status_items.append(f"[yellow]Alerts: {alerts_count}[/yellow]")
    
    # Last update
    if last_update:
        status_items.append(f"Last: {last_update.strftime('%H:%M:%S')}")
    
    return " | ".join(status_items)


def create_command_bar():
    """Create command bar showing available commands"""
    commands = [
        "[bold cyan]Q[/bold cyan] Quit",
        "[bold cyan]A[/bold cyan] Add Stock",
        "[bold cyan]R[/bold cyan] Remove Stock",
        "[bold cyan]P[/bold cyan] Pause/Resume",
    ]
    
    return Panel(
        " | ".join(commands),
        box=box.MINIMAL,
        border_style="dim",
        padding=(0, 1)
    )


def display_alert_rich(alert):
    """Display alert using rich formatting"""
    alert_color = "red" if alert['type'] == 'ABOVE' else "yellow"
    
    alert_panel = Panel(
        f"[{alert_color} bold]PRICE ALERT: {alert['symbol']}[/{alert_color} bold]\n"
        f"[{alert_color}]{alert['type']} ${alert['threshold']:.2f}[/{alert_color}]\n"
        f"Current Price: ${alert['price']:.2f}",
        box=box.HEAVY,
        border_style=alert_color,
        title="[bold]ALERT[/bold]",
        title_align="center"
    )
    
    console.print(alert_panel)
    
    # Beep sound (Windows)
    try:
        if sys.platform == 'win32':
            winsound.Beep(1000, 300)  # 1000 Hz for 300 ms
    except:
        pass


def log_to_csv(data, log_dir):
    if not data or 'status' in data and data['status'] != 'OK':
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
        console.print("[red]Error: config.json not found. Using default configuration.[/red]")
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


def save_config(config):
    """Save configuration back to file"""
    try:
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log_error(f"Failed to save config: {e}")


def load_alerts():
    try:
        with open('alerts.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        console.print("[yellow]Warning: alerts.json is invalid. No alerts loaded.[/yellow]")
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


def log_alert(alert, alert_log_file='alerts_log.txt'):
    with open(alert_log_file, 'a') as f:
        f.write(f"{alert['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} - ")
        f.write(f"{alert['symbol']} {alert['type']} ${alert['threshold']:.2f} ")
        f.write(f"(Price: ${alert['price']:.2f})\n")


def check_network_connection():
    """Check if we have internet connectivity"""
    try:
        # Try to connect to a reliable host
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except (socket.timeout, socket.error):
        return False


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


def keyboard_listener():
    """Thread function to listen for keyboard input"""
    global running, paused
    
    while running:
        if msvcrt.kbhit():
            key = msvcrt.getch().decode('utf-8').lower()
            command_queue.put(key)
        time.sleep(0.1)


def handle_add_stock(config):
    """Handle adding a new stock"""
    console.print("\n[cyan]Enter stock symbol to add (or press Enter to cancel):[/cyan]")
    symbol = input("> ").upper().strip()
    
    if symbol and symbol not in config['stocks']:
        config['stocks'].append(symbol)
        save_config(config)
        console.print(f"[green]Added {symbol} to watchlist[/green]")
        return True
    elif symbol in config['stocks']:
        console.print(f"[yellow]{symbol} is already in watchlist[/yellow]")
    
    return False


def handle_remove_stock(config):
    """Handle removing a stock"""
    if not config['stocks']:
        console.print("[yellow]No stocks to remove[/yellow]")
        return False
    
    console.print("\n[cyan]Current stocks:[/cyan]")
    for i, stock in enumerate(config['stocks']):
        console.print(f"{i+1}. {stock}")
    
    console.print("\n[cyan]Enter number to remove (or press Enter to cancel):[/cyan]")
    try:
        choice = input("> ").strip()
        if choice:
            idx = int(choice) - 1
            if 0 <= idx < len(config['stocks']):
                removed = config['stocks'].pop(idx)
                save_config(config)
                console.print(f"[green]Removed {removed} from watchlist[/green]")
                return True
    except (ValueError, IndexError):
        console.print("[red]Invalid selection[/red]")
    
    return False


def main():
    global running, paused
    
    # Start keyboard listener thread
    keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
    keyboard_thread.start()
    
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
    
    console.print(create_header())
    console.print(f"[cyan]Monitoring:[/cyan] {', '.join(symbols)}")
    console.print(f"[cyan]Update Interval:[/cyan] {update_interval} seconds")
    console.print(f"[cyan]Logging:[/cyan] {'Enabled' if logging_enabled else 'Disabled'}")
    console.print(f"[cyan]Market Hours:[/cyan] {config['market_hours']['open_time']} - {config['market_hours']['close_time']} ET")
    console.print(f"[cyan]Alerts:[/cyan] {len(alerts)} stocks configured")
    console.print(create_command_bar())
    
    time.sleep(2)
    
    network_error_count = 0
    last_update = None
    force_refresh = False
    
    try:
        while running:
            # Check for keyboard commands
            while not command_queue.empty():
                cmd = command_queue.get()
                
                if cmd == 'q':
                    running = False
                    break
                elif cmd == 'p':
                    paused = not paused
                    console.print(f"\n[yellow]Updates {'PAUSED' if paused else 'RESUMED'}[/yellow]")
                elif cmd == 'a':
                    if handle_add_stock(config):
                        symbols = config['stocks']
                        force_refresh = True
                elif cmd == 'r':
                    if handle_remove_stock(config):
                        symbols = config['stocks']
                        force_refresh = True
            
            if not running:
                break
            
            # Skip update if paused (unless force refresh)
            if paused and not force_refresh:
                time.sleep(0.5)
                continue
            
            # Check network connectivity
            if not check_network_connection():
                network_error_count += 1
                error_panel = Panel(
                    f"[red bold]NETWORK CONNECTION ERROR[/red bold]\n"
                    f"Attempt #{network_error_count} - Retrying in 10 seconds...",
                    box=box.HEAVY,
                    border_style="red",
                    title="[red]ERROR[/red]"
                )
                console.print(error_panel)
                log_error(f"Network connection lost - attempt #{network_error_count}")
                
                # Wait before retry (but check for commands)
                for i in range(10):
                    if not command_queue.empty():
                        break
                    time.sleep(1)
                continue
            else:
                # Reset error count on successful connection
                if network_error_count > 0:
                    log_error(f"Network connection restored after {network_error_count} attempts")
                    network_error_count = 0
            
            # Check if we're within market hours
            if not is_market_hours(config) and not force_refresh:
                tz = pytz.timezone(config['market_hours']['timezone'])
                now = datetime.now(tz)
                
                console.clear()
                console.print(create_header())
                
                market_panel = Panel(
                    f"[yellow bold]Market is CLOSED[/yellow bold]\n"
                    f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                    f"Market hours: {config['market_hours']['open_time']} - {config['market_hours']['close_time']} ET (Mon-Fri)\n"
                    f"\n[dim]Waiting for market to open...[/dim]",
                    box=box.ROUNDED,
                    border_style="yellow"
                )
                console.print(market_panel)
                console.print(create_command_bar())
                
                # Wait but check for commands
                for i in range(60):
                    if not command_queue.empty():
                        break
                    time.sleep(1)
                continue
            
            # Clear screen and fetch data
            console.clear()
            
            # Fetch and display data for all stocks
            all_alerts = []
            stocks_data = []
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("[cyan]Fetching stock data...", total=len(symbols))
                
                for symbol in symbols:
                    progress.update(task, advance=1, description=f"[cyan]Fetching {symbol}...")
                    data = get_stock_data(symbol)
                    stocks_data.append(data)
                    
                    # Log data to CSV if enabled
                    if data and logging_enabled:
                        log_to_csv(data, log_dir)
                    
                    # Check for alerts only for successful data fetches
                    if data and data.get('status') == 'OK':
                        new_alerts = check_alerts(data, alerts, triggered_alerts)
                        all_alerts.extend(new_alerts)
            
            # Display header
            console.print(create_header())
            
            # Display table
            table = create_stock_table(stocks_data)
            console.print(table)
            
            # Display status bar
            last_update = datetime.now()
            status_bar = create_status_bar(config, len(triggered_alerts), last_update, paused)
            console.print(f"\n[dim]{status_bar}[/dim]")
            
            # Show logging status
            if logging_enabled:
                date_str = datetime.now().strftime('%Y-%m-%d')
                csv_file = os.path.join(log_dir, f'stock_data_{date_str}.csv')
                console.print(f"[green][OK] Data logged to:[/green] [yellow]{csv_file}[/yellow]")
            
            # Display command bar
            console.print(create_command_bar())
            
            # Display and log any triggered alerts
            for alert in all_alerts:
                display_alert_rich(alert)
                log_alert(alert)
            
            force_refresh = False
            
            # Countdown timer (with command checking)
            if not paused:
                for i in range(update_interval):
                    if not command_queue.empty():
                        break
                    time.sleep(1)
                
    except KeyboardInterrupt:
        running = False
    
    console.print("\n\n[yellow]Stock monitor stopped.[/yellow]")
    sys.exit(0)


if __name__ == "__main__":
    main()