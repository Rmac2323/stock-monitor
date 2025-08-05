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
import traceback
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
from news_fetcher import NewsFetcher
try:
    from edgar_scraper_selenium import EdgarScraperSelenium as EdgarScraper
except ImportError:
    # Fallback to simple scraper if Selenium fails
    from edgar_scraper_simple import EdgarScraper

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


def calculate_vwap(df):
    """Calculate Volume Weighted Average Price
    
    For intraday data: Calculate VWAP for the current trading day
    For daily data: Use the day's VWAP (approximated from OHLC)
    """
    if df.empty or len(df) == 0:
        return None
    
    # Check if this is intraday data (index has time component)
    is_intraday = hasattr(df.index[0], 'hour')
    
    if is_intraday:
        # Get today's data only
        today = df.index[-1].date()
        today_data = df[df.index.date == today]
        
        if today_data.empty:
            return None
    else:
        # For daily data, just use the last day
        today_data = df.tail(1)
    
    # Calculate typical price (high + low + close) / 3
    typical_price = (today_data['High'] + today_data['Low'] + today_data['Close']) / 3
    
    # Calculate VWAP
    cumulative_tpv = (typical_price * today_data['Volume']).cumsum()
    cumulative_volume = today_data['Volume'].cumsum()
    
    if cumulative_volume.iloc[-1] == 0:
        return None
    
    vwap = cumulative_tpv.iloc[-1] / cumulative_volume.iloc[-1]
    return vwap


def calculate_trend_strength(prices, period=20):
    """Calculate trend strength using linear regression slope"""
    if len(prices) < period:
        return None, None
    
    recent_prices = prices[-period:]
    x = np.arange(len(recent_prices))
    
    # Calculate linear regression
    slope, intercept = np.polyfit(x, recent_prices, 1)
    
    # Calculate R-squared for trend strength
    y_pred = slope * x + intercept
    ss_tot = np.sum((recent_prices - np.mean(recent_prices))**2)
    ss_res = np.sum((recent_prices - y_pred)**2)
    
    if ss_tot == 0:
        r_squared = 0
    else:
        r_squared = 1 - (ss_res / ss_tot)
    
    # Normalize slope relative to price
    normalized_slope = (slope / np.mean(recent_prices)) * 100
    
    # Trend strength from 0-100
    trend_strength = abs(r_squared) * 100
    
    return normalized_slope, trend_strength


def identify_bar_pattern(open_price, high, low, close, prev_close=None):
    """Identify common candlestick patterns"""
    body = abs(close - open_price)
    upper_shadow = high - max(close, open_price)
    lower_shadow = min(close, open_price) - low
    total_range = high - low
    
    if total_range == 0:
        return "Neutral"
    
    body_ratio = body / total_range
    
    # Doji - very small body
    if body_ratio < 0.1:
        if upper_shadow > body * 2 and lower_shadow > body * 2:
            return "Doji"
        elif upper_shadow > body * 3:
            return "Gravestone"
        elif lower_shadow > body * 3:
            return "Dragonfly"
    
    # Hammer or Shooting Star
    if body_ratio < 0.3:
        if lower_shadow > body * 2 and upper_shadow < body * 0.5:
            return "Hammer" if close > open_price else "InvHammer"
        elif upper_shadow > body * 2 and lower_shadow < body * 0.5:
            return "Shooting Star"
    
    # Marubozu - no or very small shadows
    if body_ratio > 0.9:
        return "Bullish Marubozu" if close > open_price else "Bearish Marubozu"
    
    # Engulfing patterns (needs previous candle)
    if prev_close is not None:
        if close > open_price and open_price < prev_close and close > prev_close:
            return "Bullish Engulf"
        elif close < open_price and open_price > prev_close and close < prev_close:
            return "Bearish Engulf"
    
    return "Normal"


def calculate_support_resistance(df, lookback=20):
    """Calculate support and resistance levels using recent highs/lows"""
    if len(df) < lookback:
        return None, None
    
    recent_data = df.tail(lookback)
    
    # Find local highs and lows
    highs = recent_data['High'].values
    lows = recent_data['Low'].values
    
    # Simple method: use recent peaks and troughs
    # Resistance: highest high in the period
    resistance = np.max(highs)
    
    # Support: lowest low in the period
    support = np.min(lows)
    
    # More sophisticated: find levels that were tested multiple times
    # Group prices into bins and find most frequent levels
    all_prices = np.concatenate([highs, lows])
    hist, bins = np.histogram(all_prices, bins=10)
    
    # Find the two most frequent price levels
    sorted_indices = np.argsort(hist)[::-1]
    if len(sorted_indices) >= 2:
        # Get the price levels for the top 2 bins
        level1 = (bins[sorted_indices[0]] + bins[sorted_indices[0] + 1]) / 2
        level2 = (bins[sorted_indices[1]] + bins[sorted_indices[1] + 1]) / 2
        
        # Assign as support/resistance based on current price
        current_price = df['Close'].iloc[-1]
        if level1 > current_price and level2 > current_price:
            resistance = min(level1, level2)
        elif level1 < current_price and level2 < current_price:
            support = max(level1, level2)
        else:
            support = min(level1, level2)
            resistance = max(level1, level2)
    
    return support, resistance


def log_error(error_msg, error_log_file='error_log.txt', console_output=True):
    """Log errors to file with timestamp and optional console output"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted_msg = f"{timestamp} - {error_msg}"
    
    # Log to file
    try:
        with open(error_log_file, 'a') as f:
            f.write(f"{formatted_msg}\n")
    except Exception as e:
        if console_output:
            console.print(f"[red]Failed to write to error log: {e}[/red]")
    
    # Log to console if requested
    if console_output:
        console.print(f"[red]ERROR:[/red] {error_msg}")


def fetch_timeframe_data(symbol, interval, period=None):
    """Fetch data for a specific timeframe"""
    # Adjust period based on interval if not specified
    if period is None:
        if interval in ["1m", "5m", "15m", "30m", "60m", "90m"]:
            if interval == "1m":
                period = "5d"
            else:
                period = "1mo"
        else:
            period = "3mo"
    
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period=period, interval=interval)
        return hist
    except Exception as e:
        log_error(f"Failed to fetch {interval} data for {symbol}: {e}", console_output=False)
        return None


def get_stock_data(symbol, retry_count=0, max_retries=3, timeframes=None):
    """Fetch stock data with retry logic and comprehensive error handling
    
    Args:
        symbol: Stock symbol to fetch
        retry_count: Current retry attempt
        max_retries: Maximum number of retries
        timeframes: Dict of timeframe configurations for each indicator
    """
    # Calculate retry delay with exponential backoff
    retry_delay = min(5 * (2 ** retry_count), 30)  # Max 30 seconds
    
    # Default timeframes if not provided
    if timeframes is None:
        timeframes = {
            "price": "1d",
            "rsi": {"interval": "1d", "period": 14},
            "sma": {"interval": "1d", "period": 20},
            "vwap": "1d",
            "support_resistance": {"interval": "1d", "lookback": 20},
            "trend": {"interval": "1d", "period": 20},
            "patterns": "1d"
        }
    
    try:
        # Collect all unique intervals we need to fetch
        intervals_to_fetch = set()
        
        # Price data interval
        price_interval = timeframes.get("price", "1d")
        intervals_to_fetch.add(price_interval)
        
        # Add other intervals
        for key in ["rsi", "sma", "support_resistance", "trend"]:
            if key in timeframes:
                if isinstance(timeframes[key], dict):
                    intervals_to_fetch.add(timeframes[key].get("interval", "1d"))
                else:
                    intervals_to_fetch.add(timeframes[key])
        
        if "vwap" in timeframes:
            intervals_to_fetch.add(timeframes.get("vwap", price_interval))
        
        if "patterns" in timeframes:
            intervals_to_fetch.add(timeframes.get("patterns", price_interval))
        
        # Fetch data for all required intervals
        data_by_interval = {}
        stock = yf.Ticker(symbol)
        
        for interval in intervals_to_fetch:
            hist = fetch_timeframe_data(symbol, interval)
            if hist is not None and not hist.empty:
                data_by_interval[interval] = hist
        
        # Check if we have the primary price data
        if price_interval not in data_by_interval or len(data_by_interval[price_interval]) < 1:
            if retry_count < max_retries:
                log_error(f"{symbol}: No price data available, retry {retry_count + 1}/{max_retries} in {retry_delay}s", console_output=False)
                time.sleep(retry_delay)
                return get_stock_data(symbol, retry_count + 1, max_retries, timeframes)
            log_error(f"{symbol}: No data available after {max_retries} retries")
            return {'symbol': symbol, 'status': 'NO_DATA', 'error': 'No historical data available'}
            
        # Get price data from the specified interval
        price_data = data_by_interval[price_interval]
        current_price = price_data['Close'].iloc[-1]
        previous_close = price_data['Close'].iloc[-2] if len(price_data) > 1 else current_price
        
        change = current_price - previous_close
        change_percent = (change / previous_close) * 100 if previous_close != 0 else 0
        
        # Today's data from price interval
        info = stock.info
        day_high = info.get('dayHigh', price_data['High'].iloc[-1])
        day_low = info.get('dayLow', price_data['Low'].iloc[-1])
        volume = info.get('volume', price_data['Volume'].iloc[-1])
        
        # Calculate technical indicators using their specific timeframes
        
        # SMA calculation
        sma_config = timeframes.get("sma", {"interval": "1d", "period": 20})
        if isinstance(sma_config, dict):
            sma_interval = sma_config.get("interval", "1d")
            sma_period = sma_config.get("period", 20)
        else:
            sma_interval = sma_config
            sma_period = 20
        
        sma_data = data_by_interval.get(sma_interval)
        if sma_data is not None and len(sma_data) >= sma_period:
            sma_20 = sma_data['Close'].tail(sma_period).mean()
        else:
            sma_20 = current_price
        
        # RSI calculation
        rsi_config = timeframes.get("rsi", {"interval": "1d", "period": 14})
        if isinstance(rsi_config, dict):
            rsi_interval = rsi_config.get("interval", "1d")
            rsi_period = rsi_config.get("period", 14)
        else:
            rsi_interval = rsi_config
            rsi_period = 14
        
        rsi_data = data_by_interval.get(rsi_interval)
        if rsi_data is not None and len(rsi_data) >= rsi_period + 1:
            rsi = calculate_rsi(rsi_data['Close'].values, period=rsi_period)
        else:
            rsi = None
        
        # Volume average from price data
        vol_avg_20 = price_data['Volume'].tail(20).mean()
        vol_ratio = (volume / vol_avg_20) if vol_avg_20 > 0 else 1
        
        # Distance from high/low as percentage
        day_range = day_high - day_low
        if day_range > 0:
            pct_from_high = ((day_high - current_price) / day_high) * 100
            pct_from_low = ((current_price - day_low) / day_low) * 100
        else:
            pct_from_high = 0
            pct_from_low = 0
        
        # VWAP calculation
        vwap_interval = timeframes.get("vwap", price_interval)
        vwap_data = data_by_interval.get(vwap_interval)
        if vwap_data is not None:
            vwap = calculate_vwap(vwap_data)
            vwap_distance = ((current_price - vwap) / vwap * 100) if vwap else None
        else:
            vwap = None
            vwap_distance = None
        
        # Trend strength
        trend_config = timeframes.get("trend", {"interval": "1d", "period": 20})
        if isinstance(trend_config, dict):
            trend_interval = trend_config.get("interval", "1d")
            trend_period = trend_config.get("period", 20)
        else:
            trend_interval = trend_config
            trend_period = 20
        
        trend_data = data_by_interval.get(trend_interval)
        if trend_data is not None and len(trend_data) >= trend_period:
            trend_slope, trend_strength = calculate_trend_strength(trend_data['Close'].values, period=trend_period)
        else:
            trend_slope, trend_strength = None, None
        
        # Bar pattern
        pattern_interval = timeframes.get("patterns", price_interval)
        pattern_data = data_by_interval.get(pattern_interval)
        if pattern_data is not None and len(pattern_data) > 0:
            open_price = pattern_data['Open'].iloc[-1]
            pattern_high = pattern_data['High'].iloc[-1]
            pattern_low = pattern_data['Low'].iloc[-1]
            pattern_close = pattern_data['Close'].iloc[-1]
            prev_close = pattern_data['Close'].iloc[-2] if len(pattern_data) > 1 else None
            bar_pattern = identify_bar_pattern(open_price, pattern_high, pattern_low, pattern_close, prev_close)
        else:
            bar_pattern = "Unknown"
        
        # Support and Resistance
        sr_config = timeframes.get("support_resistance", {"interval": "1d", "lookback": 20})
        if isinstance(sr_config, dict):
            sr_interval = sr_config.get("interval", "1d")
            sr_lookback = sr_config.get("lookback", 20)
        else:
            sr_interval = sr_config
            sr_lookback = 20
        
        sr_data = data_by_interval.get(sr_interval)
        if sr_data is not None and len(sr_data) >= sr_lookback:
            support, resistance = calculate_support_resistance(sr_data, lookback=sr_lookback)
        else:
            support, resistance = None, None
        
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
            'vwap': vwap,
            'vwap_distance': vwap_distance,
            'trend_slope': trend_slope,
            'trend_strength': trend_strength,
            'bar_pattern': bar_pattern,
            'support': support,
            'resistance': resistance,
            'timestamp': datetime.now(),
            'status': 'OK'
        }
        
    except (socket.timeout, urllib.error.URLError, ConnectionError, OSError) as e:
        # Network-related errors
        error_type = type(e).__name__
        error_msg = f"{symbol}: Network error - {error_type}: {str(e)}"
        
        if retry_count < max_retries:
            log_error(f"{error_msg}, retry {retry_count + 1}/{max_retries} in {retry_delay}s", console_output=False)
            time.sleep(retry_delay)
            return get_stock_data(symbol, retry_count + 1, max_retries, timeframes)
        
        log_error(f"{error_msg} after {max_retries} retries")
        return {'symbol': symbol, 'status': 'NETWORK_ERROR', 'error': error_type, 'message': str(e)}
        
    except Exception as e:
        # Other errors
        error_type = type(e).__name__
        error_msg = f"{symbol}: {error_type} - {str(e)}"
        
        # Don't retry for certain types of errors
        non_retryable_errors = ['ValueError', 'KeyError', 'AttributeError']
        if error_type in non_retryable_errors:
            log_error(f"{error_msg} (non-retryable)")
            return {'symbol': symbol, 'status': 'ERROR', 'error': error_type, 'message': str(e)}
        
        if retry_count < max_retries:
            log_error(f"{error_msg}, retry {retry_count + 1}/{max_retries} in {retry_delay}s", console_output=False)
            time.sleep(retry_delay)
            return get_stock_data(symbol, retry_count + 1, max_retries, timeframes)
        
        log_error(f"{error_msg} after {max_retries} retries")
        return {'symbol': symbol, 'status': 'ERROR', 'error': error_type, 'message': str(e)}


def format_number(num):
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.2f}K"
    else:
        return f"{num:.2f}"


def create_stock_tables(stocks_data):
    """Create two rich tables with stock data"""
    # First table: Price and Volume
    price_table = Table(
        title="Price & Volume",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title_style="bold white"
    )
    
    price_table.add_column("Symbol", style="bold white", width=8)
    price_table.add_column("Price", justify="right", width=10)
    price_table.add_column("Change", justify="right", width=10)
    price_table.add_column("%Chg", justify="right", width=8)
    price_table.add_column("Volume", justify="right", width=10)
    price_table.add_column("VWAP", justify="right", width=10)
    price_table.add_column("VWAP Dist", justify="right", width=10)
    price_table.add_column("Pattern", justify="center", width=15)
    
    # Second table: Technical Indicators
    tech_table = Table(
        title="Technical Indicators",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        title_style="bold white"
    )
    
    tech_table.add_column("Symbol", style="bold white", width=8)
    tech_table.add_column("RSI(14)", justify="right", width=8)
    tech_table.add_column("Trend", justify="center", width=10)
    tech_table.add_column("Strength", justify="right", width=10)
    tech_table.add_column("Support", justify="right", width=10)
    tech_table.add_column("Resistance", justify="right", width=10)
    tech_table.add_column("SMA(20)", justify="right", width=10)
    tech_table.add_column("Range %", justify="center", width=15)
    
    # Add rows to both tables
    for data in stocks_data:
        if not data:
            continue
            
        # Handle error cases
        if 'status' in data and data['status'] != 'OK':
            error_text = "[red]"
            if data['status'] == 'NETWORK_ERROR':
                error_text += "Network Error"
            elif data['status'] == 'NO_DATA':
                error_text += "No Data"
            else:
                error_text += "Error"
            error_text += "[/red]"
            
            # Add error rows to both tables
            price_table.add_row(
                data['symbol'], error_text, "-", "-", "-", "-", "-", "-"
            )
            tech_table.add_row(
                data['symbol'], "-", "-", "-", "-", "-", "-", "-"
            )
            continue
        
        # Format values for price table
        is_up = data['change'] >= 0
        change_color = "green" if is_up else "red"
        arrow = "^" if is_up else "v"
        
        price_str = f"${data['current_price']:.2f}"
        change_str = f"[{change_color}]{arrow} ${abs(data['change']):.2f}[/{change_color}]"
        percent_str = f"[{change_color}]{data['change_percent']:+.2f}%[/{change_color}]"
        
        # Volume formatting
        volume_str = format_number(data['volume'])
        
        # VWAP formatting
        if data.get('vwap'):
            vwap_str = f"${data['vwap']:.2f}"
            vwap_dist = data.get('vwap_distance', 0)
            if vwap_dist > 0:
                vwap_dist_str = f"[green]+{vwap_dist:.2f}%[/green]"
            else:
                vwap_dist_str = f"[red]{vwap_dist:.2f}%[/red]"
        else:
            vwap_str = "N/A"
            vwap_dist_str = "N/A"
        
        # Pattern formatting with color
        pattern = data.get('bar_pattern', 'Normal')
        if 'Bullish' in pattern or 'Hammer' in pattern:
            pattern_str = f"[green]{pattern}[/green]"
        elif 'Bearish' in pattern or 'Shooting' in pattern:
            pattern_str = f"[red]{pattern}[/red]"
        elif 'Doji' in pattern:
            pattern_str = f"[yellow]{pattern}[/yellow]"
        else:
            pattern_str = f"[dim]{pattern}[/dim]"
        
        # Add row to price table
        price_table.add_row(
            data['symbol'],
            price_str,
            change_str,
            percent_str,
            volume_str,
            vwap_str,
            vwap_dist_str,
            pattern_str
        )
        
        # Format values for technical table
        # RSI with color coding
        rsi_val = data.get('rsi')
        if rsi_val is not None:
            if rsi_val >= 70:
                rsi_str = f"[red bold]{rsi_val:.1f}[/red bold]"
            elif rsi_val <= 30:
                rsi_str = f"[green bold]{rsi_val:.1f}[/green bold]"
            else:
                rsi_str = f"{rsi_val:.1f}"
        else:
            rsi_str = "N/A"
        
        # Trend formatting
        trend_slope = data.get('trend_slope', 0)
        trend_strength = data.get('trend_strength', 0)
        
        if trend_slope and trend_slope > 0.5:
            trend_str = "[green]/ UP[/green]"
        elif trend_slope and trend_slope < -0.5:
            trend_str = "[red]\\ DOWN[/red]"
        else:
            trend_str = "[yellow]- FLAT[/yellow]"
        
        if trend_strength:
            strength_str = f"{trend_strength:.1f}%"
            if trend_strength > 70:
                strength_str = f"[bold]{strength_str}[/bold]"
        else:
            strength_str = "N/A"
        
        # Support/Resistance
        support = data.get('support')
        resistance = data.get('resistance')
        support_str = f"${support:.2f}" if support else "N/A"
        resistance_str = f"${resistance:.2f}" if resistance else "N/A"
        
        # SMA
        sma_str = f"${data['sma_20']:.2f}"
        
        # Range position
        pct_from_high = data.get('pct_from_high', 0)
        pct_from_low = data.get('pct_from_low', 0)
        range_position = (pct_from_low / (pct_from_low + pct_from_high) * 100) if (pct_from_low + pct_from_high) > 0 else 50
        range_str = f"{range_position:.0f}% [dim]({pct_from_low:.1f}^/{pct_from_high:.1f}v)[/dim]"
        
        # Add row to technical table
        tech_table.add_row(
            data['symbol'],
            rsi_str,
            trend_str,
            strength_str,
            support_str,
            resistance_str,
            sma_str,
            range_str
        )
    
    return price_table, tech_table


def create_edgar_table(stocks_data):
    """Create table with Edgar risk data"""
    edgar_table = Table(
        title="Risk Analysis (Edgar.io)",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold red",
        title_style="bold white"
    )
    
    edgar_table.add_column("Symbol", style="bold white", width=8)
    edgar_table.add_column("Overall Risk", justify="center", width=12)
    edgar_table.add_column("Offering Ability", justify="center", width=14)
    edgar_table.add_column("Dilution Risk", justify="center", width=12)
    edgar_table.add_column("Cash Need", justify="center", width=12)
    edgar_table.add_column("Off. Frequency", justify="center", width=12)
    edgar_table.add_column("Reg SHO", justify="center", width=8)
    
    # Risk color mapping
    risk_colors = {
        'HIGH': 'red bold',
        'MEDIUM': 'yellow',
        'LOW': 'green',
        'UNKNOWN': 'dim white',
        'N/A': 'dim white'
    }
    
    for data in stocks_data:
        if not data or 'status' in data and data['status'] != 'OK':
            continue
            
        edgar_risk = data.get('edgar_risk', {})
        
        # Format risk levels with color
        def format_risk(risk_level):
            color = risk_colors.get(risk_level.upper() if risk_level else 'UNKNOWN', 'white')
            return f"[{color}]{risk_level or 'N/A'}[/{color}]"
        
        # RegSHO indicator
        reg_sho = edgar_risk.get('reg_sho', False)
        reg_sho_str = "[red bold]YES[/red bold]" if reg_sho else "[green]NO[/green]"
        
        edgar_table.add_row(
            data['symbol'],
            format_risk(edgar_risk.get('overall_risk')),
            format_risk(edgar_risk.get('offering_ability')),
            format_risk(edgar_risk.get('dilution_risk')),
            format_risk(edgar_risk.get('cash_need_risk')),
            format_risk(edgar_risk.get('offering_frequency')),
            reg_sho_str
        )
    
    return edgar_table


def create_news_panel(symbol, news_items):
    """Create a panel with recent news for a stock"""
    if not news_items:
        return None
    
    news_text = Text()
    news_text.append(f"Recent News for {symbol}\n", style="bold cyan")
    
    for i, article in enumerate(news_items[:3]):  # Show top 3 news items
        # Format timestamp
        pub_time = article.get('published_at', '')
        if pub_time:
            try:
                dt = datetime.fromisoformat(pub_time.replace('Z', '+00:00'))
                time_diff = datetime.now(dt.tzinfo) - dt
                if time_diff.days > 0:
                    time_str = f"{time_diff.days}d ago"
                elif time_diff.seconds > 3600:
                    time_str = f"{time_diff.seconds // 3600}h ago"
                else:
                    time_str = f"{time_diff.seconds // 60}m ago"
            except:
                time_str = "N/A"
        else:
            time_str = "N/A"
        
        # Sentiment color
        sentiment = article.get('sentiment', 'neutral')
        sentiment_colors = {
            'positive': 'green',
            'negative': 'red',
            'neutral': 'yellow'
        }
        sentiment_color = sentiment_colors.get(sentiment, 'white')
        
        # Add news item
        news_text.append(f"\n[{sentiment_color}]● [{time_str}][/{sentiment_color}] ", style="dim")
        news_text.append(f"{article.get('title', 'No title')[:80]}...\n", style="white")
        news_text.append(f"  Source: {article.get('source', 'Unknown')}", style="dim cyan")
        
        if i < len(news_items) - 1:
            news_text.append("\n", style="")
    
    return Panel(
        news_text,
        box=box.ROUNDED,
        border_style="cyan",
        padding=(0, 1),
        title=f"[bold]{symbol} News[/bold]",
        title_align="left"
    )


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


def create_status_bar(config, alerts_count, last_update, paused, connection_status=True, error_count=0):
    """Create a status bar with system info"""
    status_items = []
    
    # Connection status
    if connection_status:
        status_items.append("[green]* Connected[/green]")
    else:
        status_items.append("[red]* Disconnected[/red]")
    
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
    
    # Error count
    if error_count > 0:
        status_items.append(f"[red]Errors: {error_count}[/red]")
    
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
                     'pct_from_high', 'pct_from_low', 'vwap', 'vwap_distance',
                     'trend_slope', 'trend_strength', 'bar_pattern', 
                     'support', 'resistance']
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
            'pct_from_low': data['pct_from_low'],
            'vwap': data.get('vwap', ''),
            'vwap_distance': data.get('vwap_distance', ''),
            'trend_slope': data.get('trend_slope', ''),
            'trend_strength': data.get('trend_strength', ''),
            'bar_pattern': data.get('bar_pattern', ''),
            'support': data.get('support', ''),
            'resistance': data.get('resistance', '')
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


def check_network_connection(retry_count=0, max_retries=3):
    """Check if we have internet connectivity with retry logic"""
    hosts = [
        ("8.8.8.8", 53),        # Google DNS
        ("1.1.1.1", 53),        # Cloudflare DNS
        ("208.67.222.222", 53), # OpenDNS
    ]
    
    for host, port in hosts:
        try:
            socket.create_connection((host, port), timeout=3)
            return True
        except (socket.timeout, socket.error) as e:
            if retry_count == 0:
                log_error(f"Network check failed for {host}: {e}", console_output=False)
            continue
    
    # All hosts failed, retry if we haven't exceeded max retries
    if retry_count < max_retries:
        time.sleep(2 * (retry_count + 1))  # Exponential backoff
        return check_network_connection(retry_count + 1, max_retries)
    
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
    
    # Initialize news and Edgar data fetchers
    news_config = config.get('news', {})
    edgar_config = config.get('edgar', {})
    
    news_fetcher = NewsFetcher(api_key=news_config.get('newsapi_key')) if news_config.get('enabled', True) else None
    edgar_scraper = EdgarScraper() if edgar_config.get('enabled', True) else None
    
    # Track last update times for news and Edgar data
    last_news_update = {}
    last_edgar_update = datetime.min
    news_data = {}
    edgar_data = {}
    
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
    
    # Display timeframe configuration
    timeframes = config.get('timeframes', {})
    if timeframes:
        console.print("[cyan]Timeframes:[/cyan]")
        console.print(f"  Price: {timeframes.get('price', '1d')}")
        
        rsi_cfg = timeframes.get('rsi', '1d')
        if isinstance(rsi_cfg, dict):
            console.print(f"  RSI: {rsi_cfg.get('interval', '1d')} (period: {rsi_cfg.get('period', 14)})")
        else:
            console.print(f"  RSI: {rsi_cfg}")
            
        sma_cfg = timeframes.get('sma', '1d')
        if isinstance(sma_cfg, dict):
            console.print(f"  SMA: {sma_cfg.get('interval', '1d')} (period: {sma_cfg.get('period', 20)})")
        else:
            console.print(f"  SMA: {sma_cfg}")
            
        console.print(f"  VWAP: {timeframes.get('vwap', timeframes.get('price', '1d'))}")
        console.print(f"  Patterns: {timeframes.get('patterns', timeframes.get('price', '1d'))}")
    else:
        console.print(f"[cyan]Data Interval:[/cyan] {config.get('interval', '1d')}")
    
    console.print(f"[cyan]Logging:[/cyan] {'Enabled' if logging_enabled else 'Disabled'}")
    console.print(f"[cyan]Market Hours:[/cyan] {config['market_hours']['open_time']} - {config['market_hours']['close_time']} ET")
    console.print(f"[cyan]Alerts:[/cyan] {len(alerts)} stocks configured")
    console.print(create_command_bar())
    
    time.sleep(2)
    
    network_error_count = 0
    last_update = None
    force_refresh = False
    connection_status = True
    total_errors = 0
    consecutive_errors = {}  # Track consecutive errors per symbol
    
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
                connection_status = False
                console.clear()
                console.print(create_header())
                
                # Calculate retry delay with exponential backoff
                retry_delay = min(5 * (2 ** (network_error_count - 1)), 60)  # Max 60 seconds
                
                error_panel = Panel(
                    f"[red bold]NETWORK CONNECTION ERROR[/red bold]\n\n"
                    f"[yellow]Unable to connect to the internet[/yellow]\n"
                    f"Attempt #{network_error_count}\n\n"
                    f"[dim]Tested connections:[/dim]\n"
                    f"  • Google DNS (8.8.8.8)\n"
                    f"  • Cloudflare DNS (1.1.1.1)\n"
                    f"  • OpenDNS (208.67.222.222)\n\n"
                    f"[cyan]Retrying in {retry_delay} seconds...[/cyan]\n\n"
                    f"[dim]Check your internet connection and firewall settings[/dim]",
                    box=box.HEAVY,
                    border_style="red",
                    title="[red]CONNECTION ERROR[/red]",
                    title_align="center"
                )
                console.print(error_panel)
                console.print(create_command_bar())
                
                log_error(f"Network connection lost - attempt #{network_error_count}, retry in {retry_delay}s")
                
                # Show countdown timer
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                    transient=True
                ) as progress:
                    task = progress.add_task(f"[yellow]Retrying in {retry_delay} seconds...", total=retry_delay)
                    
                    for i in range(retry_delay):
                        if not command_queue.empty():
                            break
                        progress.update(task, advance=1, description=f"[yellow]Retrying in {retry_delay - i - 1} seconds...")
                        time.sleep(1)
                
                continue
            else:
                # Reset error count on successful connection
                if network_error_count > 0:
                    console.print(Panel(
                        "[green bold]CONNECTION RESTORED![/green bold]\n"
                        f"Successfully reconnected after {network_error_count} attempts",
                        box=box.ROUNDED,
                        border_style="green",
                        title="[green]SUCCESS[/green]"
                    ))
                    log_error(f"Network connection restored after {network_error_count} attempts")
                    network_error_count = 0
                    connection_status = True
                    time.sleep(2)  # Brief pause to show success message
            
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
            
            # Fetch Edgar data if it's time to update
            if edgar_scraper:
                edgar_interval = edgar_config.get('update_interval', 1800)  # 30 minutes default
                if (datetime.now() - last_edgar_update).total_seconds() > edgar_interval or force_refresh:
                    try:
                        console.print("[yellow]Fetching Edgar risk data...[/yellow]")
                        edgar_data = edgar_scraper.fetch_edgar_data()
                        last_edgar_update = datetime.now()
                    except Exception as e:
                        log_error(f"Failed to fetch Edgar data: {e}", console_output=False)
            
            # Fetch news data if it's time to update
            if news_fetcher:
                news_interval = news_config.get('update_interval', 3600)  # 1 hour default
                for symbol in symbols:
                    if symbol not in last_news_update or \
                       (datetime.now() - last_news_update.get(symbol, datetime.min)).total_seconds() > news_interval or \
                       force_refresh:
                        try:
                            news_data[symbol] = news_fetcher.fetch_stock_news(symbol)
                            last_news_update[symbol] = datetime.now()
                        except Exception as e:
                            log_error(f"Failed to fetch news for {symbol}: {e}", console_output=False)
            
            # Fetch and display data for all stocks
            all_alerts = []
            stocks_data = []
            current_errors = 0
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("[cyan]Fetching stock data...", total=len(symbols))
                
                for symbol in symbols:
                    progress.update(task, advance=1, description=f"[cyan]Fetching {symbol}...")
                    timeframes = config.get('timeframes', None)
                    data = get_stock_data(symbol, timeframes=timeframes)
                    
                    # Add Edgar risk data if available
                    if edgar_scraper and edgar_data:
                        risk_data = edgar_data.get(symbol, {})
                        if risk_data:
                            data['edgar_risk'] = risk_data
                    
                    stocks_data.append(data)
                    
                    # Track errors
                    if data and 'status' in data and data['status'] != 'OK':
                        current_errors += 1
                        consecutive_errors[symbol] = consecutive_errors.get(symbol, 0) + 1
                        log_error(f"{symbol}: {consecutive_errors[symbol]} consecutive errors", console_output=False)
                    elif symbol in consecutive_errors:
                        # Reset consecutive error count on success
                        del consecutive_errors[symbol]
                    
                    # Log data to CSV if enabled
                    if data and logging_enabled:
                        log_to_csv(data, log_dir)
                    
                    # Check for alerts only for successful data fetches
                    if data and data.get('status') == 'OK':
                        new_alerts = check_alerts(data, alerts, triggered_alerts)
                        all_alerts.extend(new_alerts)
            
            # Display header
            console.print(create_header())
            
            # Display tables
            price_table, tech_table = create_stock_tables(stocks_data)
            console.print(price_table)
            console.print("")  # Space between tables
            console.print(tech_table)
            
            # Display Edgar risk table if available
            if edgar_scraper and edgar_data:
                console.print("")  # Space before Edgar table
                edgar_table = create_edgar_table(stocks_data)
                console.print(edgar_table)
            
            # Display news panels for each stock
            if news_fetcher and news_data:
                console.print("")  # Space before news
                news_panels = []
                for symbol in symbols[:3]:  # Show news for first 3 stocks to avoid clutter
                    if symbol in news_data and news_data[symbol]:
                        panel = create_news_panel(symbol, news_data[symbol])
                        if panel:
                            news_panels.append(panel)
                
                if news_panels:
                    # Display news panels in columns
                    console.print(Columns(news_panels, equal=True, expand=True))
            
            # Display status bar
            last_update = datetime.now()
            total_errors = current_errors
            status_bar = create_status_bar(config, len(triggered_alerts), last_update, paused, connection_status, total_errors)
            console.print(f"\n[dim]{status_bar}[/dim]")
            
            # Show logging status
            if logging_enabled:
                date_str = datetime.now().strftime('%Y-%m-%d')
                csv_file = os.path.join(log_dir, f'stock_data_{date_str}.csv')
                console.print(f"[green][OK] Data logged to:[/green] [yellow]{csv_file}[/yellow]")
            
            # Show error summary if there are persistent errors
            if consecutive_errors:
                error_symbols = [f"{sym} ({count}x)" for sym, count in consecutive_errors.items() if count >= 3]
                if error_symbols:
                    console.print(f"[red]Persistent errors:[/red] {', '.join(error_symbols)}")
                    console.print(f"[dim]Check error_log.txt for details[/dim]")
            
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


def run_with_error_recovery():
    """Run the main function with crash recovery"""
    restart_count = 0
    max_restarts = 5
    
    while restart_count < max_restarts:
        try:
            main()
            break  # Normal exit
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Stock monitor stopped by user.[/yellow]")
            break
        except Exception as e:
            restart_count += 1
            error_msg = f"CRITICAL ERROR: {type(e).__name__} - {str(e)}\n{traceback.format_exc()}"
            log_error(error_msg)
            
            console.print(Panel(
                f"[red bold]UNEXPECTED ERROR[/red bold]\n\n"
                f"[yellow]{type(e).__name__}:[/yellow] {str(e)}\n\n"
                f"Restart attempt {restart_count}/{max_restarts}\n"
                f"[dim]Check error_log.txt for details[/dim]",
                box=box.HEAVY,
                border_style="red",
                title="[red]CRASH RECOVERY[/red]"
            ))
            
            if restart_count < max_restarts:
                console.print(f"\n[cyan]Restarting in 10 seconds...[/cyan]")
                time.sleep(10)
            else:
                console.print(f"\n[red]Max restart attempts reached. Please check error_log.txt[/red]")
                break


if __name__ == "__main__":
    run_with_error_recovery()