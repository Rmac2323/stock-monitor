# Stock Monitor

A real-time stock price monitoring tool with colorful terminal display.

## Features

- Real-time stock price updates every 30 seconds
- Color-coded price changes (green for up, red for down)
- Visual progress bar showing position within day's trading range
- Clean, easy-to-read terminal interface
- Formatted volume display (K/M/B)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/stock-monitor.git
cd stock-monitor
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
- Windows: `venv\Scripts\activate`
- Linux/Mac: `source venv/bin/activate`

4. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Run directly:
```bash
python main.py
```

### Run in a new terminal window (Windows):
```bash
run_monitor.bat
```

### Default Configuration
- Symbol: AAPL (Apple Inc.)
- Update Interval: 30 seconds

Press `Ctrl+C` to stop monitoring.

## Requirements

- Python 3.7+
- yfinance
- colorama

## Screenshot

```
============================================================
  STOCK PRICE MONITOR - AAPL
============================================================

  Last Update: 2025-08-04 13:14:08

------------------------------------------------------------

  Current Price:     $203.35
  Previous Close:    $202.38

  Change:           ^ +$0.97 (+0.48%)

  Day Range:        $201.68 - $207.88
  Volume:           62.48M

------------------------------------------------------------

  Day Range Progress:
  Low $201.68 [##########------------------------------] High $207.88

============================================================
```

## License

MIT License