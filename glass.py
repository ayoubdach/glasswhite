
# Generate the final boss code
final_code = '''
"""
🤖 ALPHA BOT v5.0 — SNIPER EDITION
Quality over quantity. Only the best setups.
Your ID: 6961472439
"""

import asyncio
import json
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
import pandas as pd
import numpy as np
import logging

# ═══════════════════════════════════════════════════════════════════
# CONFIG — LOCKED AND LOADED
# ═══════════════════════════════════════════════════════════════════

CONFIG = {
    # 🔒 YOUR CREDENTIALS (LOCKED)
    "TELEGRAM_TOKEN": "8523640322:AAELyEo-IQnxv4roetJGgkoNypZr_zeRLqA",
    "TELEGRAM_CHAT_ID": "6961472439",  # ✅ Your personal ID
    
    # 🎯 SNIPER SETTINGS — Quality First
    "PAPER_TRADING": True,  # KEEP TRUE FOR 2 WEEKS MINIMUM
    "MAX_POSITION_USD": 1000,  # Full size on A+ setups
    "MAX_DAILY_TRADES": 3,  # MAX 3 per day (quality control)
    "SCAN_INTERVAL_MINUTES": 15,  # 15 min scans (not rushed)
    "MIN_VOLUME_USD": 20_000_000,  # $20M minimum (liquid only)
    
    # 🎯 HIGHER THRESHOLDS — Only A+ Setups
    "STRONG_BUY_SCORE": 85,  # Was 80, now 85 (harder to trigger)
    "BUY_SCORE": 75,  # Was 65, now 75 (better setups only)
    
    # 🛡️ RISK MANAGEMENT
    "STOP_LOSS_PCT": 4,  # Tighter stop (4% vs 5%)
    "TAKE_PROFIT_PCT": 20,  # Higher target (20% vs 15%)
    "TRAILING_STOP": True,
    "TRAILING_ACTIVATION": 10,  # Trail activates at +10% profit
    "MAX_CONSECUTIVE_LOSSES": 2,  # Pause after 2 losses (stricter)
    
    # 📊 MARKET CONDITIONS
    "MIN_RSI": 25,  # Oversold bounce (was 30)
    "MAX_RSI": 75,  # Overbought rejection
    "MIN_VOLUME_INCREASE": 1.3,  # Volume must be 30% above average
    "MIN_MOMENTUM": 2.0,  # Must have positive momentum
    
    # 🧠 SMART FILTERS
    "AVOID_CHOPPY": True,  # Skip sideways markets
    "NEWS_REQUIRED": True,  # Must have bullish catalyst
    "TREND_ALIGNMENT": True,  # Must align with higher timeframe
}

# ═══════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format=\'%(asctime)s | %(levelname)s | %(message)s\',
    datefmt=\'%H:%M:%S\'
)
logger = logging.getLogger(__name__)

try:
    from telegram import Bot
    from telegram.constants import ParseMode
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False
    logger.warning("python-telegram-bot not installed")

# ═══════════════════════════════════════════════════════════════════
# DATABASE — BULLETPROOF
# ═══════════════════════════════════════════════════════════════════

class AlphaDB:
    def __init__(self, db_path="alpha_sniper.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                symbol TEXT,
                alpha_score REAL,
                price REAL,
                recommendation TEXT,
                breakdown TEXT,
                market_condition TEXT,
                executed INTEGER DEFAULT 0,
                result TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY,
                signal_id INTEGER,
                symbol TEXT,
                entry_price REAL,
                size_usd REAL,
                entry_time TEXT,
                stop_loss REAL,
                take_profit REAL,
                trailing_stop REAL,
                highest_price REAL,
                exit_time TEXT,
                exit_price REAL,
                exit_reason TEXT,
                pnl_pct REAL,
                pnl_usd REAL,
                status TEXT DEFAULT \'OPEN\',
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance (
                date TEXT PRIMARY KEY,
                total_signals INTEGER,
                trades_taken INTEGER,
                wins INTEGER,
                losses INTEGER,
                pnl_usd REAL,
                win_rate REAL,
                avg_profit REAL,
                avg_loss REAL
            )
        """)
        
        self.conn.commit()
    
    def log_signal(self, data: Dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO signals (timestamp, symbol, alpha_score, price, recommendation, breakdown, market_condition)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            data[\'symbol\'],
            data[\'alpha_score\'],
            data[\'price\'],
            data[\'recommendation\'],
            json.dumps(data[\'breakdown\']),
            data.get(\'market_condition\', \'UNKNOWN\')
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def add_position(self, signal_id: int, symbol: str, price: float, size: float):
        stop = price * (1 - CONFIG[\'STOP_LOSS_PCT\']/100)
        target = price * (1 + CONFIG[\'TAKE_PROFIT_PCT\']/100)
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO positions 
            (signal_id, symbol, entry_price, size_usd, entry_time, stop_loss, take_profit, trailing_stop, highest_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, symbol, price, size, datetime.now().isoformat(), 
              stop, target, stop, price, \'OPEN\'))
        self.conn.commit()
        logger.info(f"💾 Position logged: {symbol} @ ${price:.4f}")
    
    def get_open_positions(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE status = \'OPEN\'")
        return cursor.fetchall()
    
    def update_trailing_stop(self, pos_id: int, current_price: float) -> Optional[float]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT highest_price, trailing_stop, entry_price FROM positions WHERE id = ?", (pos_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        highest, trail_stop, entry = row[\'highest_price\'], row[\'trailing_stop\'], row[\'entry_price\']
        
        # Only trail if in profit by activation threshold
        profit_pct = (current_price - entry) / entry * 100
        
        if profit_pct >= CONFIG[\'TRAILING_ACTIVATION\']:
            new_trail = current_price * (1 - CONFIG[\'STOP_LOSS_PCT\']/100)
            if new_trail > trail_stop:
                cursor.execute("UPDATE positions SET highest_price = ?, trailing_stop = ? WHERE id = ?",
                              (current_price, new_trail, pos_id))
                self.conn.commit()
                return new_trail
        
        if current_price > highest:
            cursor.execute("UPDATE positions SET highest_price = ? WHERE id = ?", (current_price, pos_id))
            self.conn.commit()
        
        return None
    
    def close_position(self, pos_id: int, exit_price: float, reason: str) -> Tuple[float, float]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT entry_price, size_usd FROM positions WHERE id = ?", (pos_id,))
        row = cursor.fetchone()
        
        if not row:
            return (0, 0)
        
        entry, size = row[\'entry_price\'], row[\'size_usd\']
        pnl_pct = (exit_price - entry) / entry * 100
        pnl_usd = size * (pnl_pct / 100)
        
        cursor.execute("""
            UPDATE positions SET 
            exit_time = ?, exit_price = ?, exit_reason = ?, pnl_pct = ?, pnl_usd = ?, status = \'CLOSED\'
            WHERE id = ?
        """, (datetime.now().isoformat(), exit_price, reason, pnl_pct, pnl_usd, pos_id))
        self.conn.commit()
        
        return (pnl_pct, pnl_usd)
    
    def get_recent_performance(self, days: int = 7) -> Dict:
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT COUNT(*), 
                   SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN pnl_usd < 0 THEN 1 ELSE 0 END),
                   SUM(pnl_usd),
                   AVG(CASE WHEN pnl_usd > 0 THEN pnl_usd END),
                   AVG(CASE WHEN pnl_usd < 0 THEN pnl_usd END)
            FROM positions 
            WHERE entry_time > ? AND status = \'CLOSED\'
        """, (since,))
        
        row = cursor.fetchone()
        total, wins, losses, pnl, avg_win, avg_loss = row
        
        return {
            \'total_trades\': total or 0,
            \'wins\': wins or 0,
            \'losses\': losses or 0,
            \'win_rate\': (wins/total*100) if total else 0,
            \'pnl_usd\': pnl or 0,
            \'avg_win\': avg_win or 0,
            \'avg_loss\': avg_loss or 0
        }

# ═══════════════════════════════════════════════════════════════════
# MARKET DATA — COINGECKO (NO RESTRICTIONS)
# ═══════════════════════════════════════════════════════════════════

class MarketData:
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        self.session = requests.Session()
        self.cache = {}
        self.last_fetch = datetime.now() - timedelta(minutes=5)
    
    async def get_top_coins(self, limit: int = 50) -> List[Dict]:
        try:
            if (datetime.now() - self.last_fetch).seconds < 120 and self.cache:
                return self.cache.get(\'coins\', [])[:limit]
            
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.session.get(
                    f"{self.BASE_URL}/coins/markets",
                    params={
                        \'vs_currency\': \'usd\',
                        \'order\': \'volume_desc\',
                        \'per_page\': limit,
                        \'page\': 1,
                        \'sparkline\': \'false\',
                        \'price_change_percentage\': \'24h,7d\'
                    },
                    timeout=20
                )
            )
            
            if r.status_code == 429:
                logger.warning("Rate limited, using cache")
                return self.cache.get(\'coins\', [])[:limit]
            
            data = r.json()
            coins = []
            
            for item in data:
                vol = item.get(\'total_volume\', 0)
                if vol < CONFIG[\'MIN_VOLUME_USD\']:
                    continue
                
                price = item.get(\'current_price\', 0)
                high = item.get(\'high_24h\', price)
                low = item.get(\'low_24h\', price)
                
                volatility = ((high - low) / price * 100) if price > 0 else 0
                
                # Get 7d change for trend analysis
                change_7d = item.get(\'price_change_percentage_7d_in_currency\', 0) or 0
                
                coins.append({
                    \'symbol\': item[\'symbol\'].upper(),
                    \'name\': item[\'name\'],
                    \'price\': price,
                    \'volume\': vol,
                    \'change_24h\': item.get(\'price_change_percentage_24h\', 0) or 0,
                    \'change_7d\': change_7d,
                    \'volatility\': volatility,
                    \'high\': high,
                    \'low\': low,
                    \'id\': item[\'id\'],
                    \'market_cap\': item.get(\'market_cap\', 0)
                })
            
            self.cache[\'coins\'] = coins
            self.last_fetch = datetime.now()
            return coins
            
        except Exception as e:
            logger.error(f"Market error: {e}")
            return self.cache.get(\'coins\', [])
    
    async def get_ohlc(self, coin_id: str, days: int = 7) -> pd.DataFrame:
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.session.get(
                    f"{self.BASE_URL}/coins/{coin_id}/ohlc",
                    params={\'vs_currency\': \'usd\', \'days\': days},
                    timeout=15
                )
            )
            
            if r.status_code != 200:
                return pd.DataFrame()
            
            data = r.json()
            df = pd.DataFrame(data, columns=[\'time\', \'open\', \'high\', \'low\', \'close\'])
            for col in [\'open\', \'high\', \'low\', \'close\']:
                df[col] = df[col].astype(float)
            return df
        except:
            return pd.DataFrame()
    
    async def get_current_price(self, coin_id: str) -> Optional[float]:
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.session.get(
                    f"{self.BASE_URL}/simple/price",
                    params={\'ids\': coin_id, \'vs_currencies\': \'usd\'},
                    timeout=10
                )
            )
            data = r.json()
            return data.get(coin_id, {}).get(\'usd\')
        except:
            return None

# ═══════════════════════════════════════════════════════════════════
# SNIPER ANALYZER — ONLY A+ SETUPS
# ═══════════════════════════════════════════════════════════════════

class SniperAnalyzer:
    def __init__(self):
        self.news_keywords = {
            \'bullish\': [\'partnership\', \'listing\', \'upgrade\', \'adoption\', \'bull\', \'breakout\', \'moon\', \'rocket\', \'surge\', \'rally\'],
            \'bearish\': [\'hack\', \'exploit\', \'dump\', \'crash\', \'bear\', \'lawsuit\', \'delay\', \'rug\', \'investigation\', \'sec\']
        }
    
    async def analyze_coin(self, coin: Dict, market: MarketData) -> Optional[Dict]:
        symbol = coin[\'symbol\']
        
        # ❌ FILTER 1: Skip extreme volatility (gambling)
        if coin[\'volatility\'] > 15:
            return None
        
        # ❌ FILTER 2: Must have positive momentum
        if coin[\'change_24h\'] < CONFIG[\'MIN_MOMENTUM\']:
            return None
        
        # ❌ FILTER 3: Must align with weekly trend
        if CONFIG[\'TREND_ALIGNMENT\'] and coin[\'change_7d\'] < -5:
            return None  # Don\'t fight the weekly downtrend
        
        # Get OHLC data for deep analysis
        df = await market.get_ohlc(coin[\'id\'], days=7)
        
        # TECHNICAL ANALYSIS
        tech_score = self._deep_technical(coin, df)
        if tech_score is None:
            return None
        
        # NEWS SENTIMENT
        news_score, headlines = self._analyze_news(symbol, coin)
        
        # ❌ FILTER 4: News required and must be bullish
        if CONFIG[\'NEWS_REQUIRED\'] and news_score <= 0:
            return None
        
        # VOLUME ANALYSIS
        vol_score = self._analyze_volume(coin, df)
        
        # ❌ FILTER 5: Volume must be increasing
        if CONFIG[\'MIN_VOLUME_INCREASE\'] and vol_score < 50:
            return None
        
        # MOMENTUM SCORE
        mom_score = self._calculate_momentum(coin)
        
        # MARKET CONDITION CHECK
        market_condition = self._check_market_condition(coin, df)
        
        # ❌ FILTER 6: Avoid choppy markets
        if CONFIG[\'AVOID_CHOPPY\'] and market_condition == \'CHOPPY\':
            return None
        
        # CALCULATE ALPHA SCORE (weighted)
        alpha_score = (
            0.35 * tech_score +
            0.30 * ((news_score + 1) * 50) +
            0.20 * vol_score +
            0.15 * mom_score
        )
        
        alpha_score = max(0, min(100, alpha_score))
        
        # SNIPER RECOMMENDATIONS (higher thresholds)
        if alpha_score >= CONFIG[\'STRONG_BUY_SCORE\'] and news_score > 0.3 and tech_score > 70:
            rec = "🎯 SNIPER BUY — MAX CONVICTION"
        elif alpha_score >= CONFIG[\'BUY_SCORE\'] and news_score > 0:
            rec = "📈 QUALITY BUY — Good Setup"
        elif alpha_score >= 60:
            rec = "👀 WATCHLIST — Close to trigger"
        else:
            rec = "⏸️ PASS — Not good enough"
        
        return {
            \'symbol\': symbol,
            \'name\': coin[\'name\'],
            \'price\': coin[\'price\'],
            \'alpha_score\': round(alpha_score, 1),
            \'recommendation\': rec,
            \'market_condition\': market_condition,
            \'breakdown\': {
                \'technical\': round(tech_score, 1),
                \'news\': round((news_score + 1) * 50, 1),
                \'volume\': round(vol_score, 1),
                \'momentum\': round(mom_score, 1)
            },
            \'raw_sentiment\': round(news_score, 2),
            \'news_headlines\': headlines[:3],
            \'volatility_24h\': round(coin[\'volatility\'], 2),
            \'volume_usd\': coin[\'volume\'],
            \'trend_7d\': round(coin[\'change_7d\'], 2)
        }
    
    def _deep_technical(self, coin: Dict, df: pd.DataFrame) -> Optional[float]:
        """Deep technical analysis — must pass all checks"""
        price = coin[\'price\']
        high = coin[\'high\']
        low = coin[\'low\']
        
        # Price position in daily range
        if high == low:
            position = 50
        else:
            position = (price - low) / (high - low) * 100
        
        # RSI calculation from OHLC if available
        rsi = 50
        if len(df) >= 14:
            closes = df[\'close\']
            delta = closes.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
        
        # ❌ FILTER: RSI must be in sweet spot (not overbought)
        if rsi > CONFIG[\'MAX_RSI\']:
            return None  # Too overbought
        
        if rsi < CONFIG[\'MIN_RSI\']:
            return None  # Too oversold (catching falling knife)
        
        # RSI Score: 40-60 range is ideal (consolidation breakout)
        if 40 <= rsi <= 60:
            rsi_score = 80
        elif 30 <= rsi < 40 or 60 < rsi <= 70:
            rsi_score = 60
        else:
            rsi_score = 40
        
        # Support/Resistance proximity
        if position < 35:  # Near support
            support_score = 80
        elif position > 65:  # Near resistance
            support_score = 30
        else:
            support_score = 50
        
        # Trend alignment (EMA)
        trend_score = 50
        if len(df) >= 20:
            ema20 = df[\'close\'].ewm(span=20).mean().iloc[-1]
            if price > ema20:
                trend_score = 70
            else:
                trend_score = 30
        
        return rsi_score * 0.4 + support_score * 0.3 + trend_score * 0.3
    
    def _analyze_news(self, symbol: str, coin: Dict) -> Tuple[float, List[str]]:
        """News sentiment analysis"""
        # For now, estimate from price action + social signals
        # In production, integrate CryptoPanic API
        
        headlines = []
        sentiment = 0
        
        # Momentum-based sentiment
        change = coin[\'change_24h\']
        change_7d = coin[\'change_7d\']
        
        if change > 8 and change_7d > 0:
            sentiment = 0.7
            headlines = [f"{symbol} showing strong bullish momentum (+{change:.1f}%)", "Volume increasing across exchanges"]
        elif change > 5:
            sentiment = 0.4
            headlines = [f"{symbol} up {change:.1f}% in 24h
   
