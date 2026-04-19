"""
🤖 ALPHA BOT v4.2 — PERSONAL ALERTS EDITION
Sends alerts to your personal chat only (no group spam)
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
# CONFIG — PASTE YOUR TOKEN HERE
# ═══════════════════════════════════════════════════════════════════

CONFIG = {
    # 🔒 PASTE YOUR TOKEN HERE (from @BotFather)
    "TELEGRAM_TOKEN": "8523640322:AAELyEo-IQnxv4roetJGgkoNypZr_zeRLqA",  # ← YOUR TOKEN
    
    # Get your personal ID from @userinfobot (no minus sign!)
    "TELEGRAM_CHAT_ID": "-5241445521",  # ← LEAVE EMPTY, bot will auto-detect
    
    "PAPER_TRADING": True,
    "MAX_POSITION_USD": 500,
    "MAX_DAILY_TRADES": 5,
    "SCAN_INTERVAL_MINUTES": 10,
    "MIN_VOLUME_USD": 10_000_000,
    
    "STRONG_BUY_SCORE": 80,
    "BUY_SCORE": 65,
    
    "STOP_LOSS_PCT": 5,
    "TAKE_PROFIT_PCT": 15,
    "TRAILING_STOP": True,
    "MAX_CONSECUTIVE_LOSSES": 3,
}

# ═══════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

try:
    from telegram import Bot, Update
    from telegram.constants import ParseMode
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False
    logger.warning("Telegram not installed")

# ═══════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════

class AlphaDB:
    def __init__(self, db_path="alpha.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT,
                alpha_score REAL, price REAL, recommendation TEXT,
                breakdown TEXT, executed INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY, symbol TEXT, entry_price REAL,
                size_usd REAL, entry_time TEXT, stop_loss REAL,
                take_profit REAL, trailing_stop REAL, highest_price REAL,
                exit_time TEXT, exit_price REAL, exit_reason TEXT,
                pnl_pct REAL, pnl_usd REAL, status TEXT DEFAULT 'OPEN'
            )
        """)
        self.conn.commit()
    
    def log_signal(self, data: Dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO signals (timestamp, symbol, alpha_score, price, recommendation, breakdown)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(), data['symbol'], data['alpha_score'],
            data['price'], data['recommendation'], json.dumps(data['breakdown'])
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def add_position(self, symbol: str, price: float, size: float):
        stop = price * 0.95
        target = price * 1.15
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO positions (symbol, entry_price, size_usd, entry_time, stop_loss, take_profit, trailing_stop, highest_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, price, size, datetime.now().isoformat(), stop, target, stop, price, 'OPEN'))
        self.conn.commit()
    
    def get_open_positions(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE status = 'OPEN'")
        return cursor.fetchall()
    
    def update_position_price(self, pos_id: int, current_price: float):
        cursor = self.conn.cursor()
        cursor.execute("SELECT highest_price, trailing_stop FROM positions WHERE id = ?", (pos_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        highest, trail_stop = row['highest_price'], row['trailing_stop']
        
        if current_price > highest:
            new_trail = current_price * 0.95
            if new_trail > trail_stop:
                cursor.execute("UPDATE positions SET highest_price = ?, trailing_stop = ? WHERE id = ?", 
                              (current_price, new_trail, pos_id))
                self.conn.commit()
                return new_trail
            else:
                cursor.execute("UPDATE positions SET highest_price = ? WHERE id = ?", (current_price, pos_id))
                self.conn.commit()
        return None
    
    def close_position(self, pos_id: int, exit_price: float, reason: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT entry_price, size_usd FROM positions WHERE id = ?", (pos_id,))
        row = cursor.fetchone()
        if not row:
            return (0, 0)
        
        entry, size = row['entry_price'], row['size_usd']
        pnl_pct = (exit_price - entry) / entry * 100
        pnl_usd = size * (pnl_pct / 100)
        
        cursor.execute("""
            UPDATE positions SET exit_time = ?, exit_price = ?, exit_reason = ?, pnl_pct = ?, pnl_usd = ?, status = 'CLOSED'
            WHERE id = ?
        """, (datetime.now().isoformat(), exit_price, reason, pnl_pct, pnl_usd, pos_id))
        self.conn.commit()
        return (pnl_pct, pnl_usd)

# ═══════════════════════════════════════════════════════════════════
# COINGECKO API
# ═══════════════════════════════════════════════════════════════════

class MarketData:
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        self.session = requests.Session()
        self.cache = {}
        self.last_fetch = datetime.now() - timedelta(minutes=5)
    
    async def get_top_coins(self, limit: int = 50) -> List[Dict]:
        try:
            if (datetime.now() - self.last_fetch).seconds < 60 and self.cache:
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
                        'price_change_percentage': '24h'
                    },
                    timeout=15
                )
            )
            
            if r.status_code == 429:
                logger.warning("Rate limit, using cache")
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
                
                coins.append({
                    'symbol': item['symbol'].upper(),
                    'price': price,
                    'volume': vol,
                    'change_24h': item.get('price_change_percentage_24h', 0) or 0,
                    'volatility': volatility,
                    'high': high,
                    'low': low,
                    'open': price,
                    'id': item['id']
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
                    timeout=5
                )
            )
            data = r.json()
            return data.get(coin_id, {}).get('usd')
        except:
            return None

# ═══════════════════════════════════════════════════════════════════
# ANALYZER
# ═══════════════════════════════════════════════════════════════════

class Analyzer:
    def analyze_coin(self, coin: Dict) -> Optional[Dict]:
        symbol = coin['symbol']
        
        if coin['volatility'] > 20:
            return None
        
        # Technical score from price position
        price = coin['price']
        high = coin['high']
        low = coin['low']
        
        if high == low:
            tech_score = 50
        else:
            position = (price - low) / (high - low) * 100
            if position < 30:
                tech_score = 75
            elif position > 70:
                tech_score = 25
            else:
                tech_score = 50
        
        # News sentiment from momentum
        mom = coin['change_24h']
        if mom > 10:
            news_score = 0.6
        elif mom > 5:
            news_score = 0.3
        elif mom < -10:
            news_score = -0.6
        elif mom < -5:
            news_score = -0.3
        else:
            news_score = 0.0
        
        # Volume score
        vol_score = min(100, max(0, (np.log10(coin['volume']) - 7) * 25))
        
        # Momentum score
        mom_score = 50 + (mom * 2)
        mom_score = max(0, min(100, mom_score))
        
        # Volatility penalty
        vol_penalty = max(0, (coin['volatility'] - 8) * 3)
        
        # Alpha score
        alpha_score = (
            0.45 * tech_score +
            0.25 * ((news_score + 1) * 50) +
            0.15 * vol_score +
            0.15 * mom_score -
            vol_penalty
        )
        
        alpha_score = max(0, min(100, alpha_score))
        
        if alpha_score >= CONFIG['STRONG_BUY_SCORE'] and news_score > 0:
            rec = "🚀 STRONG BUY"
        elif alpha_score >= CONFIG['BUY_SCORE']:
            rec = "📈 BUY"
        else:
            rec = "⏸️ WATCH"
        
        return {
            'symbol': symbol,
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
            'news_headlines': [f"{symbol}: ${coin['volume']/1e6:.1f}M vol, {mom:+.2f}% 24h"],
            'volatility_24h': round(coin['volatility'], 2)
        }

# ═══════════════════════════════════════════════════════════════════
# ALERTS — PERSONAL ONLY
# ═══════════════════════════════════════════════════════════════════

class AlertManager:
    def __init__(self):
        self.bot = None
        self.chat_id = None
        
        if TELEGRAM_OK and CONFIG['TELEGRAM_TOKEN']:
            try:
                self.bot = Bot(token=CONFIG['TELEGRAM_TOKEN'])
                # Auto-detect chat ID from recent messages
                self._detect_chat_id()
                logger.info("✅ Telegram ready")
            except Exception as e:
                logger.error(f"Telegram init failed: {e}")
    
    def _detect_chat_id(self):
        """Auto-detect your personal chat ID"""
        try:
            # Get recent updates to find your chat
            updates = self.bot.get_updates(limit=10)
            for update in updates:
                if update.message and update.message.chat.type == "private":
                    self.chat_id = update.message.chat.id
                    logger.info(f"📱 Found personal chat: {self.chat_id}")
                    return
            
            # Fallback to config if no messages yet
            if CONFIG['TELEGRAM_CHAT_ID']:
                self.chat_id = CONFIG['TELEGRAM_CHAT_ID']
                logger.info(f"📱 Using configured chat: {self.chat_id}")
            else:
                logger.warning("⚠️  No chat ID found! Message your bot first.")
        except Exception as e:
            logger.error(f"Chat detection failed: {e}")
            self.chat_id = CONFIG['TELEGRAM_CHAT_ID'] or None
    
    async def send(self, opp: Dict, is_entry: bool = False, exit_data: Dict = None):
        if not self.bot or not self.chat_id:
            # Console only
            msg = self._format_console(opp, is_entry, exit_data)
            print("\n" + "🔔" * 20)
            print(msg)
            print("🔔" * 20 + "\n")
            return
        
        # Format message
        if is_entry:
            msg = self._format_entry(opp)
        elif exit_data:
            msg = self._format_exit(exit_data)
        else:
            msg = self._format_opportunity(opp)
        
        # Console
        print("\n" + "🔔" * 20)
        print(msg)
        print("🔔" * 20 + "\n")
        
        # Telegram (personal only)
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=msg,
                parse_mode=ParseMode.HTML
            )
            logger.info("📱 Personal alert sent")
        except Exception as e:
            logger.error(f"Telegram failed: {e}")
    
    def _format_opportunity(self, opp: Dict) -> str:
        emoji = "🚀" if opp['alpha_score'] >= 85 else "📈" if opp['alpha_score'] >= 70 else "⚡"
        return f"""
{emoji} <b>ALPHA: {opp['symbol']}</b> | Score: <code>{opp['alpha_score']}/100</code>
Signal: {opp['recommendation']} | Price: ${opp['price']:.4f}

Tech: {opp['breakdown']['technical']}/100 | News: {opp['breakdown']['news']}/100
Vol: {opp['breakdown']['volume']}/100 | Mom: {opp['breakdown']['momentum']}/100

24h Volatility: {opp['volatility_24h']}%

<i>{datetime.now().strftime('%H:%M:%S')}</i>
"""
    
    def _format_entry(self, opp: Dict) -> str:
        return f"✅ <b>ENTERED {opp['symbol']}</b> @ ${opp['price']:.4f}"
    
    def _format_exit(self, data: Dict) -> str:
        emoji = "🟢" if data['pnl_pct'] > 0 else "🔴"
        return f"{emoji} <b>CLOSED {data['symbol']}</b> | P&L: {data['pnl_pct']:+.2f}%"
    
    def _format_console(self, opp, is_entry, exit_data):
        if is_entry:
            return f"✅ ENTERED {opp['symbol']} @ ${opp['price']:.4f}"
        elif exit_data:
            return f"{'🟢' if exit_data['pnl_pct'] > 0 else '🔴'} CLOSED {exit_data['symbol']} | {exit_data['pnl_pct']:+.2f}%"
        else:
            return f"🚀 {opp['symbol']} | Score: {opp['alpha_score']} | {opp['recommendation']}"

# ═══════════════════════════════════════════════════════════════════
# EXECUTION
# ═══════════════════════════════════════════════════════════════════

class ExecutionEngine:
    def __init__(self, db: AlphaDB, alerts: AlertManager):
        self.db = db
        self.alerts = alerts
        self.daily_trades = 0
        self.last_date = datetime.now().date()
    
    def can_trade(self):
        today = datetime.now().date()
        if today != self.last_date:
            self.daily_trades = 0
            self.last_date = today
        return self.daily_trades < CONFIG['MAX_DAILY_TRADES']
    
    async def enter_position(self, signal_id: int, opp: Dict):
        if not self.can_trade():
            return
        
        symbol = opp['symbol']
        open_pos = self.db.get_open_positions()
        if any(p['symbol'] == symbol for p in open_pos):
            return
        
        size = min(CONFIG['MAX_POSITION_USD'], CONFIG['MAX_POSITION_USD'] * (opp['alpha_score'] / 100))
        self.db.add_position(symbol, opp['price'], size)
        self.daily_trades += 1
        
        await self.alerts.send(opp, is_entry=True)
        logger.info(f"🎯 Entered {symbol}")
    
    async def check_positions(self, market: MarketData):
        positions = self.db.get_open_positions()
        for pos in positions:
            coin_id = pos['symbol'].lower()
            current = await market.get_current_price(coin_id)
            if not current:
                continue
            
            new_stop = self.db.update_position_price(pos['id'], current)
            if new_stop:
                logger.info(f"📈 {pos['symbol']} trailing stop: ${new_stop:.4f}")
            
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
                await self.alerts.send(None, exit_data={
                    'symbol': pos['symbol'], 'exit_price': current,
                    'reason': reason, 'pnl_pct': pnl_pct, 'pnl_usd': pnl_usd
                })
                logger.info(f"🔒 Exited {pos['symbol']}: {pnl_pct:+.2f}%")

# ═══════════════════════════════════════════════════════════════════
# MAIN BOT
# ═══════════════════════════════════════════════════════════════════

class AlphaBot:
    def __init__(self):
        self.db = AlphaDB()
        self.market = MarketData()
        self.analyzer = Analyzer()
        self.alerts = AlertManager()
        self.executor = ExecutionEngine(self.db, self.alerts)
        self.running = False
        
        print("""
        ╔══════════════════════════════════════════╗
        ║   🤖 ALPHA BOT v4.2 — PERSONAL EDITION    ║
        ╠══════════════════════════════════════════╣
        ║  Alerts: Personal chat only (no groups)  ║
        ║  Mode: PAPER TRADING                     ║
        ╚══════════════════════════════════════════╝
        """)
        
        if not self.alerts.chat_id:
            print("""
        ⚠️  FIRST TIME SETUP:
            1. Message your bot: https://t.me/YOUR_BOT_NAME
            2. Send /start
            3. Restart this bot
            4. It will auto-detect your chat ID
            """)
    
    async def run(self):
        self.running = True
        while self.running:
            try:
                await self._scan()
                await asyncio.sleep(CONFIG['SCAN_INTERVAL_MINUTES'] * 60)
            except KeyboardInterrupt:
                print("\n👋 Stopped")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(60)
    
    async def _scan(self):
        logger.info("🔍 Scanning...")
        
        coins = await self.market.get_top_coins(30)
        logger.info(f"   Analyzing {len(coins)} coins...")
        
        opportunities = []
        for coin in coins:
            try:
                result = self.analyzer.analyze_coin(coin)
                if result and result['alpha_score'] >= CONFIG['BUY_SCORE']:
                    opportunities.append(result)
            except Exception as e:
                continue
        
        opportunities.sort(key=lambda x: x['alpha_score'], reverse=True)
        
        for opp in opportunities[:3]:
            signal_id = self.db.log_signal(opp)
   
