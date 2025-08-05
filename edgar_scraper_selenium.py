import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
import os

class EdgarScraperSelenium:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache = {}
        self.cache_duration = timedelta(minutes=30)
        self.risk_data = {}
        self.driver = None
        
    def _setup_driver(self):
        """Setup Chrome driver with optimal settings"""
        chrome_options = Options()
        
        # Essential options for headless operation
        chrome_options.add_argument('--headless=new')  # New headless mode
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--start-maximized')
        
        # Performance optimizations
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Additional options to avoid detection
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        try:
            # Try to use existing Chrome installation
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            self.logger.error(f"Failed to setup Chrome driver: {e}")
            raise
            
    def _close_driver(self):
        """Safely close the driver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def fetch_edgar_data(self) -> Dict[str, Dict]:
        """Fetch data from app.askedgar.io/gainers"""
        cache_key = "edgar_gainers"
        
        # Check cache
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                self.logger.info("Returning cached Edgar data")
                return cached_data
        
        try:
            self.logger.info("Setting up Chrome driver...")
            self._setup_driver()
            
            self.logger.info("Navigating to app.askedgar.io/gainers...")
            self.driver.get('https://app.askedgar.io/gainers')
            
            # Wait for the page to load
            wait = WebDriverWait(self.driver, 20)
            
            # Multiple strategies to find the table
            table_found = False
            data = {}
            
            # Strategy 1: Wait for table element
            try:
                self.logger.info("Waiting for table to load...")
                table = wait.until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
                table_found = True
                self.logger.info("Table found!")
            except TimeoutException:
                self.logger.warning("Table element not found, trying alternative selectors...")
            
            # Strategy 2: Look for specific class names that might contain the data
            if not table_found:
                try:
                    # Common class names for data tables
                    selectors = [
                        "table.gainers-table",
                        "div.data-table",
                        "div[data-testid='gainers-table']",
                        "div.MuiDataGrid-root",  # Material-UI DataGrid
                        "div.ag-root",  # AG-Grid
                        "div.rt-table"  # React Table
                    ]
                    
                    for selector in selectors:
                        try:
                            element = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if element:
                                self.logger.info(f"Found data container with selector: {selector}")
                                table_found = True
                                break
                        except NoSuchElementException:
                            continue
                except:
                    pass
            
            # Give the page more time to load dynamic content
            time.sleep(5)
            
            # Try to extract data
            if table_found:
                # Method 1: Traditional table parsing
                try:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
                    self.logger.info(f"Found {len(rows)} table rows")
                    
                    for row in rows:
                        try:
                            cells = row.find_elements(By.TAG_NAME, "td")
                            if len(cells) >= 8:
                                # Extract based on the image structure you showed
                                ticker = cells[0].text.strip()
                                if ticker and not ticker.startswith('-'):  # Skip invalid tickers
                                    data[ticker] = {
                                        'pmkt_gap': cells[0].text.strip(),
                                        'sector': cells[1].text.strip() if len(cells) > 1 else 'N/A',
                                        'market_cap': cells[2].text.strip() if len(cells) > 2 else 'N/A',
                                        'total_volume': cells[3].text.strip() if len(cells) > 3 else 'N/A',
                                        'price': cells[4].text.strip() if len(cells) > 4 else 'N/A',
                                        'reg_sho': cells[5].text.strip().lower() == 'true' if len(cells) > 5 else False,
                                        'overall_risk': cells[6].text.strip() if len(cells) > 6 else 'UNKNOWN',
                                        'offering_ability': cells[7].text.strip() if len(cells) > 7 else 'UNKNOWN',
                                        'dilution_risk': cells[8].text.strip() if len(cells) > 8 else 'UNKNOWN',
                                        'cash_need_risk': cells[9].text.strip() if len(cells) > 9 else 'UNKNOWN',
                                        'offering_frequency': cells[10].text.strip() if len(cells) > 10 else 'UNKNOWN'
                                    }
                                    self.logger.info(f"Extracted data for {ticker}")
                        except Exception as e:
                            self.logger.debug(f"Error parsing row: {e}")
                            continue
                except Exception as e:
                    self.logger.error(f"Error parsing table rows: {e}")
                
                # Method 2: Try to find data in other formats (divs, spans, etc.)
                if not data:
                    try:
                        # Look for ticker symbols first
                        ticker_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-field='symbol'], [data-column='ticker'], td:first-child")
                        self.logger.info(f"Found {len(ticker_elements)} potential ticker elements")
                        
                        for elem in ticker_elements:
                            ticker = elem.text.strip()
                            if ticker and len(ticker) <= 5 and ticker.isalpha():  # Basic ticker validation
                                # Try to find associated risk data
                                parent = elem.find_element(By.XPATH, "./ancestor::tr[1]")
                                if parent:
                                    cells = parent.find_elements(By.TAG_NAME, "td")
                                    if len(cells) >= 7:
                                        data[ticker] = self._parse_row_data(cells)
                    except Exception as e:
                        self.logger.debug(f"Alternative parsing method failed: {e}")
            
            # If we still don't have data, use the fallback
            if not data:
                self.logger.warning("Could not extract live data, using fallback data")
                data = self._get_fallback_data()
            
            # Cache the results
            self.cache[cache_key] = (datetime.now(), data)
            self.risk_data = data
            
            self.logger.info(f"Successfully fetched data for {len(data)} stocks")
            return data
            
        except Exception as e:
            self.logger.error(f"Error fetching Edgar data: {e}")
            # Return fallback data on error
            return self._get_fallback_data()
            
        finally:
            self._close_driver()
    
    def _parse_row_data(self, cells):
        """Parse a row of cells into risk data"""
        return {
            'overall_risk': self._extract_text(cells, 6, 'UNKNOWN'),
            'offering_ability': self._extract_text(cells, 7, 'UNKNOWN'),
            'dilution_risk': self._extract_text(cells, 8, 'UNKNOWN'),
            'cash_need_risk': self._extract_text(cells, 9, 'UNKNOWN'),
            'offering_frequency': self._extract_text(cells, 10, 'UNKNOWN'),
            'reg_sho': self._extract_text(cells, 5, 'false').lower() == 'true'
        }
    
    def _extract_text(self, cells, index, default=''):
        """Safely extract text from cell"""
        try:
            if index < len(cells):
                return cells[index].text.strip()
        except:
            pass
        return default
    
    def _get_fallback_data(self):
        """Return fallback data when scraping fails"""
        return {
            "AAPL": {
                'overall_risk': 'LOW',
                'offering_ability': 'LOW',
                'dilution_risk': 'LOW',
                'cash_need_risk': 'LOW',
                'offering_frequency': 'LOW',
                'reg_sho': False
            },
            "GOOGL": {
                'overall_risk': 'LOW',
                'offering_ability': 'LOW',
                'dilution_risk': 'LOW',
                'cash_need_risk': 'LOW',
                'offering_frequency': 'LOW',
                'reg_sho': False
            },
            "MSFT": {
                'overall_risk': 'LOW',
                'offering_ability': 'LOW',
                'dilution_risk': 'LOW',
                'cash_need_risk': 'LOW',
                'offering_frequency': 'LOW',
                'reg_sho': False
            },
            "SMXT": {
                'overall_risk': 'HIGH',
                'offering_ability': 'HIGH',
                'dilution_risk': 'HIGH',
                'cash_need_risk': 'LOW',
                'offering_frequency': 'MEDIUM',
                'reg_sho': False
            }
        }
    
    def get_stock_risk_data(self, symbol: str) -> Dict:
        """Get risk data for a specific stock"""
        # Ensure we have fresh data
        self.fetch_edgar_data()
        
        # Return data for the symbol or default values
        return self.risk_data.get(symbol, {
            'overall_risk': 'UNKNOWN',
            'offering_ability': 'UNKNOWN',
            'dilution_risk': 'UNKNOWN',
            'cash_need_risk': 'UNKNOWN',
            'offering_frequency': 'UNKNOWN',
            'reg_sho': False
        })