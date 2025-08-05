import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import re
import logging
from collections import defaultdict

class SECRiskAnalyzer:
    """
    Analyzes SEC filings to calculate offering and dilution risk metrics
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache = {}
        self.cache_duration = timedelta(hours=24)
        
        # SEC API base URL
        self.sec_api_base = "https://data.sec.gov"
        self.headers = {
            'User-Agent': 'StockMonitor/1.0 (contact@example.com)',
            'Accept': 'application/json'
        }
        
    def calculate_risk_metrics(self, symbol: str) -> Dict:
        """
        Calculate comprehensive risk metrics for a stock based on SEC filings
        """
        cache_key = f"sec_risk_{symbol}"
        
        # Check cache
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data
        
        try:
            # Get company CIK
            cik = self._get_company_cik(symbol)
            if not cik:
                return self._default_risk_metrics()
            
            # Analyze different filing types
            s3_filings = self._get_filings(cik, 'S-3')  # Shelf registrations
            s1_filings = self._get_filings(cik, 'S-1')  # IPO registrations
            f424b_filings = self._get_filings(cik, '424B')  # Prospectus
            effect_filings = self._get_filings(cik, 'EFFECT')  # Effectiveness notices
            _8k_filings = self._get_filings(cik, '8-K')  # Current reports
            _10q_filings = self._get_filings(cik, '10-Q')  # Quarterly reports
            
            # Calculate metrics
            metrics = {
                'offering_frequency': self._calculate_offering_frequency(s3_filings, s1_filings, f424b_filings),
                'dilution_risk': self._calculate_dilution_risk(s3_filings, effect_filings),
                'cash_burn_rate': self._calculate_cash_burn(_10q_filings),
                'shelf_registration_active': self._check_active_shelf(s3_filings, effect_filings),
                'recent_offerings': self._get_recent_offerings(f424b_filings, _8k_filings),
                'warrants_outstanding': self._check_warrants(_10q_filings)
            }
            
            # Convert to risk levels
            risk_assessment = self._assess_risk_levels(metrics)
            
            # Cache results
            self.cache[cache_key] = (datetime.now(), risk_assessment)
            
            return risk_assessment
            
        except Exception as e:
            self.logger.error(f"Error analyzing SEC filings for {symbol}: {e}")
            return self._default_risk_metrics()
    
    def _get_company_cik(self, symbol: str) -> str:
        """Get CIK number for a ticker symbol"""
        try:
            # Use SEC's company tickers endpoint
            url = f"{self.sec_api_base}/submissions/CIK{symbol}.json"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('cik', '')
            
            # Alternative: Use ticker mapping
            tickers_url = "https://www.sec.gov/files/company_tickers.json"
            response = requests.get(tickers_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                tickers = response.json()
                for company in tickers.values():
                    if company.get('ticker', '').upper() == symbol.upper():
                        return str(company.get('cik_str', '')).zfill(10)
                        
        except Exception as e:
            self.logger.debug(f"Error getting CIK for {symbol}: {e}")
            
        return None
    
    def _get_filings(self, cik: str, form_type: str, limit: int = 100) -> List[Dict]:
        """Get recent filings of a specific type"""
        try:
            url = f"{self.sec_api_base}/submissions/CIK{cik}.json"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                recent_filings = data.get('filings', {}).get('recent', {})
                
                # Filter by form type
                filings = []
                forms = recent_filings.get('form', [])
                dates = recent_filings.get('filingDate', [])
                
                for i, form in enumerate(forms[:limit]):
                    if form_type in form:
                        filings.append({
                            'form': form,
                            'date': dates[i] if i < len(dates) else None
                        })
                
                return filings
                
        except Exception as e:
            self.logger.debug(f"Error fetching {form_type} filings: {e}")
            
        return []
    
    def _calculate_offering_frequency(self, s3_filings, s1_filings, f424b_filings) -> str:
        """Calculate how frequently the company does offerings"""
        # Count offerings in last 2 years
        two_years_ago = datetime.now() - timedelta(days=730)
        
        offering_count = 0
        all_filings = s3_filings + s1_filings + f424b_filings
        
        for filing in all_filings:
            try:
                filing_date = datetime.strptime(filing.get('date', ''), '%Y-%m-%d')
                if filing_date > two_years_ago:
                    offering_count += 1
            except:
                continue
        
        # Determine frequency level
        if offering_count >= 6:
            return "VERY_HIGH"  # More than quarterly
        elif offering_count >= 4:
            return "HIGH"  # Quarterly
        elif offering_count >= 2:
            return "MEDIUM"  # Semi-annual
        elif offering_count >= 1:
            return "LOW"  # Annual or less
        else:
            return "NONE"
    
    def _calculate_dilution_risk(self, s3_filings, effect_filings) -> str:
        """Calculate dilution risk based on shelf registrations"""
        # Check for active shelf registration
        has_active_shelf = False
        shelf_size = "UNKNOWN"
        
        # Look for recent S-3 with matching EFFECT
        for s3 in s3_filings[:5]:  # Check recent 5
            filing_date = s3.get('date')
            if filing_date:
                # Check if there's an EFFECT filing after this S-3
                for effect in effect_filings:
                    if effect.get('date', '') >= filing_date:
                        has_active_shelf = True
                        break
                        
        if has_active_shelf:
            # TODO: Parse filing content to determine shelf size
            return "HIGH"
        else:
            return "LOW"
    
    def _calculate_cash_burn(self, quarterly_filings) -> float:
        """Calculate quarterly cash burn rate from 10-Q filings"""
        # This would require parsing the actual filing content
        # For now, return a placeholder
        return 0.0
    
    def _check_active_shelf(self, s3_filings, effect_filings) -> bool:
        """Check if company has active shelf registration"""
        if not s3_filings:
            return False
            
        # Get most recent S-3
        latest_s3_date = s3_filings[0].get('date', '')
        
        # Check if it's been declared effective
        for effect in effect_filings:
            if effect.get('date', '') >= latest_s3_date:
                return True
                
        return False
    
    def _get_recent_offerings(self, f424b_filings, _8k_filings) -> List[Dict]:
        """Get list of recent offerings"""
        offerings = []
        
        # Check 424B filings (prospectus supplements)
        for filing in f424b_filings[:5]:
            offerings.append({
                'type': 'Public Offering',
                'date': filing.get('date'),
                'form': filing.get('form')
            })
        
        # Check 8-K for private placements
        for filing in _8k_filings[:10]:
            # Would need to parse content to identify offering-related 8-Ks
            pass
            
        return offerings
    
    def _check_warrants(self, quarterly_filings) -> bool:
        """Check if company has outstanding warrants"""
        # This would require parsing filing content
        return False
    
    def _assess_risk_levels(self, metrics: Dict) -> Dict:
        """Convert raw metrics to risk level assessments"""
        risk_levels = {}
        
        # Offering Frequency Risk
        freq = metrics.get('offering_frequency', 'UNKNOWN')
        freq_map = {
            'VERY_HIGH': 'HIGH',
            'HIGH': 'HIGH',
            'MEDIUM': 'MEDIUM',
            'LOW': 'LOW',
            'NONE': 'LOW',
            'UNKNOWN': 'UNKNOWN'
        }
        risk_levels['offering_frequency'] = freq_map.get(freq, 'UNKNOWN')
        
        # Dilution Risk
        dilution = metrics.get('dilution_risk', 'UNKNOWN')
        if metrics.get('shelf_registration_active'):
            dilution = 'HIGH'
        risk_levels['dilution_risk'] = dilution
        
        # Cash Need Risk
        # Based on cash burn and recent offerings
        recent_offerings = len(metrics.get('recent_offerings', []))
        if recent_offerings >= 2:
            risk_levels['cash_need_risk'] = 'HIGH'
        elif recent_offerings >= 1:
            risk_levels['cash_need_risk'] = 'MEDIUM'
        else:
            risk_levels['cash_need_risk'] = 'LOW'
        
        # Overall Risk
        high_count = sum(1 for v in risk_levels.values() if v == 'HIGH')
        if high_count >= 2:
            risk_levels['overall_risk'] = 'HIGH'
        elif high_count >= 1:
            risk_levels['overall_risk'] = 'MEDIUM'
        else:
            risk_levels['overall_risk'] = 'LOW'
        
        # Offering Ability (inverse of restrictions)
        # Companies with active shelfs have HIGH ability to offer
        if metrics.get('shelf_registration_active'):
            risk_levels['offering_ability'] = 'HIGH'
        else:
            risk_levels['offering_ability'] = 'LOW'
        
        # Add RegSHO placeholder
        risk_levels['reg_sho'] = False
        
        return risk_levels
    
    def _default_risk_metrics(self) -> Dict:
        """Return default risk metrics when analysis fails"""
        return {
            'overall_risk': 'UNKNOWN',
            'offering_ability': 'UNKNOWN',
            'dilution_risk': 'UNKNOWN',
            'cash_need_risk': 'UNKNOWN',
            'offering_frequency': 'UNKNOWN',
            'reg_sho': False
        }