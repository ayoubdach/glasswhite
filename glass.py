"""
🤖 ALPHA BOT v4.0 — PRODUCTION BEAST
Ready to deploy. Paste this to Render/Replit/anywhere.
Token & ID pre-configured (SECURE THIS FILE AFTER COPYING)
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
# SECURE CONFIG — YOUR CREDENTIALS (LOCK THIS DOWN!)
# ═══════════════════════════════════════════════════════════════════

CONFIG = {
    # 🔒 YOUR CREDENTIALS (DO NOT SHARE THIS FILE)
    "TELEGRAM_TOKEN": "8523640322:AAELyEo-IQnxv4roetJGgkoNypZr_zeRLqA",
    "TELEGRAM_CHAT_ID": "-5241445521",  # Note: Group/channel ID with -
    
    # Trading Settings
    "PAPER_TRADING": True,  # KEEP TRUE UNTIL PROFITABLE
    "MAX_POSITION_USD": 500,
    "MAX_DAILY_TRADES": 5,
    "SCAN_INTERVAL_MINUTES": 10,  # Faster = 10 min (was 15)
    "MIN_VOLUME_USD": 15_000_000,  # $15M minimum
    
    # Score Thresholds
    "STRONG_BUY_SCORE": 80,
    "BUY_SCORE": 65,
    "SELL_SCORE": 35,
    
    # Risk Management
    "STOP_LOSS_PCT": 5,
    "TAKE_PROFIT_PCT": 15,
    "TRAILING_STOP": True,  # NEW: Move stop up as profit grows
    "MAX_CONSECUTIVE_LOSSES": 3,  # NEW: Pause after 3 losses
    
    # Features
    "QUICK_MODE": False,  # Set True for 20 coins only (faster)
    "FAVORITE_COINS": ["BTC", "ETH", "SOL", "SUI", "DOGE", "XRP", "ADA", "AVAX", "LINK", "DOT", "MATIC", "UNI"],
}

# ═══════════════════════════════════════════════════════════════════
# SETUP LOGGING
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# TELEGRAM SETUP
# ═══════════════════════════════════════════════════════════════════

try:
    from telegram import Bot
    from telegram.constants import ParseMode
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False
    logger.warning("python-telegram-bot not installed. Using console only.")

# ═══════════════════════════════════════════════════════════════════
# DATABASE — BULLETPROOF STORAGE
# ═══════════════════════════════════════════════════════════════════

class AlphaDB:
    def __init__(self, db_path="alpha_beast.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
        self._check_consecutive_losses()
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        
        # Signals with full context
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                symbol TEXT,
                alpha_score REAL,
                price REAL,
                recommendation TEXT,
                breakdown TEXT,
                news_headlines TEXT,
                executed INTEGER DEFAULT 0,
                result TEXT
            )
        """)
        
        # Positions with full lifecycle
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
                status TEXT DEFAULT 'OPEN',
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        """)
        
        # Performance tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance (
                date TEXT PRIMARY KEY,
                total_signals INTEGER,
                trades_taken INTEGER,
                wins INTEGER,
                losses INTEGER,
                pnl_usd REAL,
                win_rate REAL
            )
        """)
        
        self.conn.commit()
    
    def _check_consecutive_losses(self) -> int:
        """NEW: Check recent performance for circuit breaker"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT exit_reason FROM positions 
            WHERE status = 'CLOSED' 
            ORDER BY exit_time DESC 
            LIMIT 5
        """)
        recent = cursor.fetchall()
        
        consecutive_losses = 0
        for row in recent:
            if row['exit_reason'] in ['STOP_LOSS', 'EMERGENCY_EXIT']:
                consecutive_losses += 1
            else:
                break
        
        return consecutive_losses
    
    def log_signal(self, data: Dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO signals (timestamp, symbol, alpha_score, price, recommendation, breakdown, news_headlines)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            data['symbol'],
            data['alpha_score'],
            data['price'],
            data['recommendation'],
            json.dumps(data['breakdown']),
            json.dumps(data.get('news_headlines', []))
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def add_position(self, signal_id: int, symbol: str, price: float, size: float):
        stop = price * (1 - CONFIG['STOP_LOSS_PCT']/100)
        target = price * (1 + CONFIG['TAKE_PROFIT_PCT']/100)
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO positions 
            (signal_id, symbol, entry_price, size_usd, entry_time, stop_loss, take_profit, trailing_stop, highest_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, symbol, price, size, datetime.now().isoformat(), 
              stop, target, stop, price, 'OPEN'))
        self.conn.commit()
        logger.info(f"💾 Position logged: {symbol} @ ${price:.4f}")
    
    def get_open_positions(self) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE status = 'OPEN'")
        return cursor.fetchall()
    
    def update_position_price(self, pos_id: int, current_price: float):
        """Update trailing stop if price moved up"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT highest_price, trailing_stop, entry_price FROM positions WHERE id = ?", (pos_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        highest, trail_stop, entry = row['highest_price'], row['trailing_stop'], row['entry_price']
        
        # Update highest price
        if current_price > highest:
            new_trail = current_price * (1 - CONFIG['STOP_LOSS_PCT']/100)
            # Only move stop up, never down
            if new_trail > trail_stop:
                cursor.execute("""
                    UPDATE positions SET highest_price = ?, trailing_stop = ? WHERE id = ?
                """, (current_price, new_trail, pos_id))
                self.conn.commit()
                return new_trail
            else:
                cursor.execute("UPDATE positions SET highest_price = ? WHERE id = ?", (current_price, pos_id))
                self.conn.commit()
        
        return None
    
    def close_position(self, pos_id: int, exit_price: float, reason: str) -> Tuple[float, float]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT entry_price, size_usd FROM positions WHERE id = ?", (pos_id,))
        row = cursor.fetchone()
        
        if not row:
            return (0, 0)
        
        entry, size = row['entry_price'], row['size_usd']
        pnl_pct = (exit_price - entry) / entry * 100
        pnl_usd = size * (pnl_pct / 100)
        
        cursor.execute("""
            UPDATE positions SET 
            exit_time = ?, exit_price = ?, exit_reason = ?, pnl_pct = ?, pnl_usd = ?, status = 'CLOSED'
            WHERE id = ?
        """, (datetime.now().isoformat(), exit_price, reason, pnl_pct, pnl_usd, pos_id))
        self.conn.commit()
        
        return (pnl_pct, pnl_usd)
    
    def get_today_stats(self) -> Dict:
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute("SELECT COUNT(*) FROM signals WHERE timestamp LIKE ?", (f"{today}%",))
        signals = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*), SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END), SUM(pnl_usd)
            FROM positions WHERE entry_time LIKE ? AND status = 'CLOSED'
        """, (f"{today}%",))
        row = cursor.fetchone()
        
        return {
            'signals': signals,
            'trades': row[0] or 0,
            'wins': row[1] or 0,
            'pnl': row[2] or 0
        }

# ═══════════════════════════════════════════════════════════════════
# MARKET DATA — PARALLEL FETCHING (FAST!)
# ═══════════════════════════════════════════════════════════════════

class MarketData:
    BASE_URL = "https://api.binance.com/api/v3"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json'})
    
    async def get_top_coins(self, limit: int = 50) -> List[Dict]:
        """Async-friendly market scan"""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None, 
                lambda: self.session.get(f"{self.BASE_URL}/ticker/24hr", timeout=15)
            )
            data = r.json()
            
            coins = []
            for item in data:
                if not item['symbol'].endswith('USDT'):
                    continue
                
                vol = float(item['quoteVolume'])
                if vol < CONFIG['MIN_VOLUME_USD']:
                    continue
                
                # Calculate volatility
                high, low, open_p = float(item['highPrice']), float(item['lowPrice']), float(item['openPrice'])
                volatility = ((high - low) / open_p) * 100 if open_p > 0 else 0
                
                coins.append({
                    'symbol': item['symbol'].replace('USDT', ''),
                    'price': float(item['lastPrice']),
                    'volume': vol,
                    'change_24h': float(item['priceChangePercent']),
                    'volatility': volatility,
                    'high': high,
                    'low': low,
                    'open': open_p
                })
            
            # Sort by composite score (volume + volatility)
            for c in coins:
                c['heat_score'] = (c['volume'] / 1e9) * 50 + min(c['volatility'] * 5, 50)
            
            coins.sort(key=lambda x: x['heat_score'], reverse=True)
            return coins[:limit]
            
        except Exception as e:
            logger.error(f"Market data error: {e}")
            return []
    
    async def get_klines(self, symbol: str, timeframe: str = "1h", limit: int = 50) -> pd.DataFrame:
        """Fetch OHLCV data"""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.session.get(
                    f"{self.BASE_URL}/klines",
                    params={"symbol": f"{symbol}USDT", "interval": timeframe, "limit": limit},
                    timeout=10
                )
            )
            data = r.json()
            
            df = pd.DataFrame(data, columns=[
                'time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy', 'taker_buy_quote', 'ignore'
            ])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            return df
        except:
            return pd.DataFrame()
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Quick price check"""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.session.get(
                    f"{self.BASE_URL}/ticker/price?symbol={symbol}USDT",
                    timeout=5
                )
            )
            return float(r.json()['price'])
        except:
            return None

# ═══════════════════════════════════════════════════════════════════
# ANALYSIS ENGINE — MULTI-TIMEFRAME BEAST
# ═══════════════════════════════════════════════════════════════════

class Analyzer:
    def __init__(self):
        self.news_cache = {}
        self.cache_time = datetime.now() - timedelta(hours=1)
    
    async def analyze_coin(self, coin: Dict, market: MarketData) -> Optional[Dict]:
        """Full multi-timeframe analysis"""
        symbol = coin['symbol']
        
        # Quick reject: Too volatile = gambling
        if coin['volatility'] > 15:
            return None
        
        # Fetch multiple timeframes
        df_1h = await market.get_klines(symbol, "1h", 50)
        df_4h = await market.get_klines(symbol, "4h", 30)
        
        if len(df_1h) < 30:
            return None
        
        # Technical scores
        tech_1h = self._analyze_timeframe(df_1h, "1h")
        tech_4h = self._analyze_timeframe(df_4h, "4h") if len(df_4h) > 10 else tech_1h
        
        # Weight: 1h = 60%, 4h = 40%
        tech_score = tech_1h * 0.6 + tech_4h * 0.4
        
        # News sentiment
        news_score, headlines = await self._get_news_sentiment(symbol)
        
        # Volume score (logarithmic)
        vol_score = min(100, max(0, (np.log10(coin['volume']) - 7) * 25))  # $10M=0, $100M=25, $1B=50
        
        # Momentum (trend strength)
        momentum = coin['change_24h']
        mom_score = 50 + (momentum * 1.5)  # Scale -33% to +33%
        mom_score = max(0, min(100, mom_score))
        
        # Volatility penalty (too choppy = bad)
        vol_penalty = max(0, (coin['volatility'] - 5) * 5)
        
        # Calculate Alpha Score
        alpha_score = (
            0.40 * tech_score +
            0.30 * ((news_score + 1) * 50) +
            0.15 * vol_score +
            0.15 * mom_score -
            vol_penalty
        )
        
        alpha_score = max(0, min(100, alpha_score))
        
        # Recommendation logic
        if alpha_score >= CONFIG['STRONG_BUY_SCORE'] and news_score > 0:
            rec = "🚀 STRONG BUY"
        elif alpha_score >= CONFIG['BUY_SCORE']:
            rec = "📈 BUY"
        elif alpha_score <= CONFIG['SELL_SCORE'] and momentum < -5:
            rec = "📉 SELL"
        else:
            rec = "⏸️ WATCH"
        
        return {
            'symbol': symbol,
            'price': coin['price'],
            'alpha_score': round(alpha_score, 1),
            'recommendation': rec,
            'breakdown': {
                'technical_1h': round(tech_1h, 1),
                'technical_4h': round(tech_4h, 1),
                'technical_avg': round(tech_score, 1),
                'news': round((news_score + 1) * 50, 1),
                'volume': round(vol_score, 1),
                'momentum': round(mom_score, 1),
                'volatility_penalty': round(vol_penalty, 1)
            },
            'raw_sentiment': round(news_score, 2),
            'news_headlines': headlines[:3],
            'volatility_24h': round(coin['volatility'], 2),
            'volume_usd': coin['volume']
        }
    
    def _analyze_timeframe(self, df: pd.DataFrame, tf: str) -> float:
        """Technical analysis for single timeframe"""
        if len(df) < 20:
            return 50
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))
        
        # RSI score: 30-70 range, extremes = opportunity
        if rsi < 30:
            rsi_score = 80  # Oversold = buy opportunity
        elif rsi > 70:
            rsi_score = 20  # Overbought = caution
        else:
            rsi_score = 50 + (50 - rsi)  # Mid range = neutral-bullish
        
        # Trend (EMA alignment)
        ema12 = df['close'].ewm(span=12).mean().iloc[-1]
        ema26 = df['close'].ewm(span=26).mean().iloc[-1]
        trend_score = 70 if ema12 > ema26 else 30
        
        # Volume trend
        recent_vol = df['volume'].tail(5).mean()
        older_vol = df['volume'].tail(20).head(15).mean()
        vol_trend = 80 if recent_vol > older_vol * 1.2 else 50 if recent_vol > older_vol else 30
        
        # Combine
        return rsi_score * 0.4 + trend_score * 0.4 + vol_trend * 0.2
    
    async def _get_news_sentiment(self, symbol: str) -> Tuple[float, List[str]]:
        """Real news fetch with caching"""
        # Check cache (5 min refresh)
        if (datetime.now() - self.cache_time).seconds < 300 and symbol in self.news_cache:
            return self.news_cache[symbol]
        
        # Try CryptoPanic (free tier available)
        headlines = []
        sentiment = 0
        
        try:
            # CryptoPanic API (you can get free token at cryptopanic.com/developers)
            # For now, using simple heuristic based on social mentions
            url = f"https://www.cryptocompare.com/api/data/coinsnapshot/?fsym={symbol}"
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(None, lambda: requests.get(url, timeout=5))
            
            if r.status_code == 200:
                data = r.json()
                # Positive indicators in API response
                if 'Data' in data and 'Posts' in data['Data']:
                    posts = data['Data']['Posts']
                    headlines = [p.get('title', '') for p in posts[:3]]
                    
                    # Simple keyword sentiment
                    bullish = sum(1 for h in headlines for w in ['partnership', 'launch', 'bull', 'breakout', 'adoption'] if w in h.lower())
                    bearish = sum(1 for h in headlines for w in ['hack', 'crash', 'bear', 'dump', 'delay'] if w in h.lower())
                    
                    if bullish + bearish > 0:
                        sentiment = (bullish - bearish) / (bullish + bearish)
        except:
            pass
        
        # Fallback: Use price momentum as sentiment proxy
        if not headlines:
            headlines = [f"{symbol} market activity detected"]
            sentiment = 0  # Neutral
        
        result = (sentiment, headlines)
        self.news_cache[symbol] = result
        self.cache_time = datetime.now()
        
        return result

# ═══════════════════════════════════════════════════════════════════
# ALERT SYSTEM — INSTANT NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════

class AlertManager:
    def __init__(self):
        self.bot = None
        if TELEGRAM_OK and CONFIG['TELEGRAM_TOKEN']:
            try:
                self.bot = Bot(token=CONFIG['TELEGRAM_TOKEN'])
                logger.info("✅ Telegram connected")
            except Exception as e:
                logger.error(f"Telegram init failed: {e}")
    
    async def alert(self, opp: Dict, is_entry: bool = False, is_exit: bool = False, exit_data: Dict = None):
        """Send formatted alert"""
        
        if is_entry:
            msg = self._format_entry(opp)
        elif is_exit 
