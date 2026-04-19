"""
🤖 ALPHA BOT v5.1 — GROUP EDITION
Alerts go to your group: Glass and Glass999
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
# CONFIG — GROUP SETUP
# ═══════════════════════════════════════════════════════════════════

CONFIG = {
    # 🔒 NEW BOT TOKEN (RESET)
    "TELEGRAM_TOKEN": "8523640322:AAFFFZ_w5u5NEIAXLMBVNvie2O41S_iMzOQ",
    
    # 👥 GROUP CHAT ID
    "TELEGRAM_CHAT_ID": "-1003882771949",
    
    # 🎯 SNIPER SETTINGS
    "PAPER_TRADING": True,
    "MAX_POSITION_USD": 1000,
    "MAX_DAILY_TRADES": 3,
    "SCAN_INTERVAL_MINUTES": 15,
    "MIN_VOLUME_USD": 20_000_000,
    
    "STRONG_BUY_SCORE": 85,
    "BUY_SCORE": 75,
    
    "STOP_LOSS_PCT": 4,
    "TAKE_PROFIT_PCT": 20,
    "TRAILING_STOP": True,
    "TRAILING_ACTIVATION": 10,
    "MAX_CONSECUTIVE_LOSSES": 2,
}

# ═══════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
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
# DATABASE
# ═══════════════════════════════════════════════════════════════════

class AlphaDB:
    def __init__(self, db_path="alpha_group.db"):
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
                executed INTEGER DEFAULT 0
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
                status TEXT DEFAULT 'OPEN'
            )
        """)
        
        self.conn.commit()
    
    def log_signal(self, data: Dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO signals (timestamp, symbol, alpha_score, price, recommendation, breakdown)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            data['symbol'],
            data['alpha_score'],
            data['price'],
            data['recommendation'],
            json.dumps(data['breakdown'])
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
    
    def get_open_positions(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE status = 'OPEN'")
        return cursor.fetchall()
    
    def update_trailing_stop(self, pos_id: int, current_price: float) -> Optional[float]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT highest_price, trailing_stop, entry_price FROM positions WHERE id = ?", (pos_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        highest, trail_stop, entry = row['highest_price'], row['trailing_stop'], row['entry_price']
        
        profit_pct = (current_price - entry) / entry * 100
        
        if profit_pct >= CONFIG['TRAILING_ACTIVATION']:
            new_trail = current_price * (1 - CONFIG['STOP_LOSS_PCT']/100)
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

# ═══════════════════════════════════════════════════════════════════
# MARKET DATA — COINGECKO
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
                return self.cache.get('coins', [])[:limit]
            
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.session.get(
                    f"{self.BASE_URL}/coins/markets",
                    params={
                        'vs_currency': 'usd',
                        'order': 'volume_desc',
                        'per_page': limit,
                        'page': 1,
                        'sparkline': 'false',
                        'price_change_percentage': '24h,7d'
                    },
                    timeout=20
                )
            )
            
            if r.status_code == 429:
                logger.warning("Rate limited, using cache")
                return self.cache.get('coins', [])[:limit]
            
            data = r.json()
            coins = []
            
            for item in data:
                vol = item.get('total_volume', 0)
                if vol < CONFIG['MIN_VOLUME_USD']:
                    continue
                
                price = item.get('current_price', 0)
                high = item.get('high_24h', price)
                low = item.get('low_24h', price)
                
                volatility = ((high - low) / price * 100) if price > 0 else 0
                
                change_7d = item.get('price_change_percentage_7d_in_currency', 0) or 0
                
                coins.append({
                    'symbol': item['symbol'].upper(),
                    'name': item['name'],
                    'price': price,
                    'volume': vol,
                    'change_24h': item.get('price_change_percentage_24h', 0) or 0,
                    'change_7d': change_7d,
                    'volatility': volatility,
                    'high': high,
                    'low': low,
                    'id': item['id'],
                    'market_cap': item.get('market_cap', 0)
                })
            
            self.cache['coins'] = coins
            self.last_fetch = datetime.now()
            return coins
            
        except Exception as e:
            logger.error(f"Market error: {e}")
            return self.cache.get('coins', [])
    
    async def get_current_price(self, coin_id: str) -> Optional[float]:
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.session.get(
                    f"{self.BASE_URL}/simple/price",
                    params={'ids': coin_id, 'vs_currencies': 'usd'},
                    timeout=10
                )
            )
            data = r.json()
            return data.get(coin_id, {}).get('usd')
        except:
            return None

# ═══════════════════════════════════════════════════════════════════
# SNIPER ANALYZER
# ═══════════════════════════════════════════════════════════════════

class SniperAnalyzer:
    def analyze_coin(self, coin: Dict) -> Optional[Dict]:
        symbol = coin['symbol']
        
        # FILTERS
        if coin['volatility'] > 15:
            return None
        
        if coin['change_24h'] < 2:
            return None
        
        if coin['change_7d'] < -5:
            return None
        
        # TECHNICAL
        price = coin['price']
        high = coin['high']
        low = coin['low']
        
        if high == low:
            position = 50
        else:
            position = (price - low) / (high - low) * 100
        
        if position < 30:
            tech_score = 80
        elif position > 70:
            tech_score = 30
        else:
            tech_score = 50
        
        # NEWS (momentum-based)
        change = coin['change_24h']
        if change > 8:
            news_score = 0.7
            headlines = [f"{symbol} strong momentum (+{change:.1f}%)", "Volume increasing"]
        elif change > 5:
            news_score = 0.4
            headlines = [f"{symbol} up {change:.1f}% in 24h"]
        elif change > 2:
            news_score = 0.2
            headlines = [f"{symbol} gaining traction"]
        else:
            news_score = 0
            headlines = [f"{symbol} consolidating"]
        
        # VOLUME
        vol_score = min(100, max(0, (np.log10(coin['volume']) - 7) * 25))
        
        # MOMENTUM
        mom = coin['change_24h']
        mom_score = 50 + (mom * 2)
        mom_score = max(0, min(100, mom_score))
        
        # ALPHA SCORE
        alpha_score = (
            0.45 * tech_score +
            0.25 * ((news_score + 1) * 50) +
            0.15 * vol_score +
            0.15 * mom_score
        )
        
        alpha_score = max(0, min(100, alpha_score))
        
        if alpha_score >= CONFIG['STRONG_BUY_SCORE'] and news_score > 0:
            rec = "🎯 SNIPER BUY"
        elif alpha_score >= CONFIG['BUY_SCORE']:
            rec = "📈 QUALITY BUY"
        else:
            rec = "⏸️ PASS"
        
        return {
            'symbol': symbol,
            'name': coin['name'],
            'price': coin['price'],
            'alpha_score': round(alpha_score, 1),
            'recommendation': rec,
            'breakdown': {
                'technical': round(tech_score, 1),
                'news': round((news_score + 1) * 50, 1),
                'volume': round(vol_score, 1),
                'momentum': round(mom_score, 1)
            },
            'raw_sentiment': round(news_score, 2),
            'news_headlines': headlines[:2],
            'volatility_24h': round(coin['volatility'], 2),
            'volume_usd': coin['volume'],
            'trend_7d': round(coin['change_7d'], 2)
        }

# ═══════════════════════════════════════════════════════════════════
# ALERTS — GROUP EDITION
# ═══════════════════════════════════════════════════════════════════

class AlertManager:
    def __init__(self):
        self.bot = None
        self.chat_id = CONFIG['TELEGRAM_CHAT_ID']
        
        if TELEGRAM_OK and CONFIG['TELEGRAM_TOKEN']:
            try:
                self.bot = Bot(token=CONFIG['TELEGRAM_TOKEN'])
                logger.info("✅ Telegram connected to group")
            except Exception as e:
                logger.error(f"Telegram init failed: {e}")
    
    async def send(self, opp: Dict, is_entry: bool = False, exit_data: Dict = None):
        if is_entry:
            msg = self._format_entry(opp)
        elif exit_data:
            msg = self._format_exit(exit_data)
        else:
            msg = self._format_opportunity(opp)
        
        # Console
        print("\n" + "🎯" * 25)
        print(msg)
        print("🎯" * 25 + "\n")
        
        # Telegram Group
        if self.bot and self.chat_id:
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=msg,
                    parse_mode=ParseMode.HTML
                )
                logger.info("📱 Alert sent to group")
            except Exception as e:
                logger.error(f"Telegram failed: {e}")
    
    def _format_opportunity(self, opp: Dict) -> str:
        if opp['alpha_score'] >= 90:
            emoji = "🎯🎯🎯"
        elif opp['alpha_score'] >= 85:
            emoji = "🎯🎯"
        else:
            emoji = "🎯"
        
        return f"""
{emoji} <b>SNIPER: {opp['symbol']}</b> {emoji}

<b>Score:</b> <code>{opp['alpha_score']}/100</code> | <b>Signal:</b> {opp['recommendation']}
<b>Price:</b> ${opp['price']:.4f}

<b>Analysis:</b>
├ Technical: {opp['breakdown']['technical']}/100
├ News: {opp['breakdown']['news']}/100 ({opp['raw_sentiment']:+.2f})
├ Volume: {opp['breakdown']['volume']}/100
└ Momentum: {opp['breakdown']['momentum']}/100

<b>Context:</b>
├ 24h Vol: {opp['volatility_24h']}%
├ 7d Trend: {opp['trend_7d']:+.2f}%
└ Volume: ${opp['volume_usd']/1e6:.1f}M

<b>Intel:</b>
{chr(10).join(['• ' + h for h in opp['news_headlines'][:2]])}

<i>{datetime.now().strftime('%H:%M:%S UTC')}</i>
"""
    
    def _format_entry(self, opp: Dict) -> str:
        size = min(CONFIG['MAX_POSITION_USD'], CONFIG['MAX_POSITION_USD'] * (opp['alpha_score'] / 100))
        return f"""
✅ <b>ENTRY: {opp['symbol']}</b>

Entry: ${opp['price']:.4f}
Size: ${size:.0f}
Stop: ${opp['price'] * (1 - CONFIG['STOP_LOSS_PCT']/100):.4f}
Target: ${opp['price'] * (1 + CONFIG['TAKE_PROFIT_PCT']/100):.4f}

<i>Paper trade active</i>
"""
    
    def _format_exit(self, data: Dict) -> str:
        emoji = "🟢" if data['pnl_pct'] > 0 else "🔴"
        return f"""
{emoji} <b>EXIT: {data['symbol']}</b>

Exit: ${data['exit_price']:.4f}
Reason: {data['reason']}
P&L: <code>{data['pnl_pct']:+.2f}%</code> (${data['pnl_usd']:+.2f})
"""

# ═══════════════════════════════════════════════════════════════════
# EXECUTION
# ═══════════════════════════════════════════════════════════════════

class ExecutionEngine:
    def __init__(self, db: AlphaDB, alerts: AlertManager):
        self.db = db
        self.alerts = alerts
        self.daily_trades = 0
        self.last_date = datetime.now().date()
        self.consecutive_losses = 0
    
    def can_trade(self) -> bool:
        today = datetime.now().date()
        if today != self.last_date:
            self.daily_trades = 0
            self.last_date = today
        
        if self.daily_trades >= CONFIG['MAX_DAILY_TRADES']:
            return False
        
        if self.consecutive_losses >= CONFIG['MAX_CONSECUTIVE_LOSSES']:
            logger.warning(f"🛑 CIRCUIT BREAKER: {self.consecutive_losses} losses")
            return False
        
        return True
    
    def calculate_size(self, score: float, volatility: float) -> float:
        base = CONFIG['MAX_POSITION_USD']
        
        if score >= 90:
            mult = 1.0
        elif score >= 85:
            mult = 0.8
        else:
            mult = 0.6
        
        vol_factor = max(0.4, 1 - (volatility / 20))
        
        return round(base * mult * vol_factor, 2)
    
    async def enter_position(self, signal_id: int, opp: Dict):
        if not self.can_trade():
            return
        
        symbol = opp['symbol']
        
        open_pos = self.db.get_open_positions()
        if any(p['symbol'] == symbol for p in open_pos):
            return
        
        size = self.calculate_size(opp['alpha_score'], opp['volatility_24h'])
        
        self.db.add_position(signal_id, symbol, opp['price'], size)
        self.daily_trades += 1
        
        await self.alerts.alert(opp, is_entry=True)
        logger.info(f"🎯 ENTRY: {symbol} @ ${opp['price']:.4f}")
    
    async def check_positions(self, market: MarketData):
        positions = self.db.get_open_positions()
        for pos in positions:
            coin_id = pos['symbol'].lower()
            current = await market.get_current_price(coin_id)
            
            if not current:
                continue
            
            new_stop = self.db.update_trailing_stop(pos['id'], current)
            if new_stop:
                logger.info(f"📈 {pos['symbol']} trail: ${new_stop:.4f}")
            
            entry = pos['entry_price']
            stop = pos['trailing_stop'] if CONFIG['TRAILING_STOP'] else pos['stop_loss']
            target = pos['take_profit']
            
            reason = None
            if current <= stop:
                reason = "STOP_LOSS"
            elif current >= target:
                reason = "TAKE_PROFIT"
            
            if reason:
                pnl_pct, pnl_usd = self.db.close_position(pos['id'], current, reason)
                
                if pnl_usd < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0
                
                await self.alerts.alert(None, exit_data={
                    'symbol': pos['symbol'],
                    'exit_price': current,
                    'reason': reason,
                    'pnl_pct': pnl_pct,
                    'pnl_usd': pnl_usd
                })
                
                logger.info(f"🔒 EXIT: {pos['symbol']} | {pnl_pct:+.2f}%")

# ═══════════════════════════════════════════════════════════════════
# MAIN BOT
# ═══════════════════════════════════════════════════════════════════

class SniperBot:
    def __init__(self):
        self.db = AlphaDB()
        self.market = MarketData()
        self.analyzer = SniperAnalyzer()
        self.alerts = AlertManager()
        self.executor = ExecutionEngine(self.db, self.alerts)
        self.running = False
        self.scan_count = 0
        
        print("""
        ╔══════════════════════════════════════════════════════╗
        ║     🎯 ALPHA SNIPER v5.1 — GROUP EDITION             ║
        ╠══════════════════════════════════════════════════════╣
        ║  Alerts: Glass and Glass999 Group                    ║
        ║  Mode: PAPER TRADING                                 
 
