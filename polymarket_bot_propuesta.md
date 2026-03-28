# 🤖 Propuesta: Polymarket Trading Bot — Sistema Multi-Estrategia 2026

> **Basado en research de los bots más exitosos en Polymarket (Q3 2025 – Q1 2026)**

---

## 📌 Resumen Ejecutivo

El ecosistema de bots en Polymarket ha madurado radicalmente. El arbitraje simple (YES+NO < $1.00) ya no es viable para traders manuales: el **92% de los traders pierde dinero**, y las oportunidades de arbitraje duran en promedio **2.7 segundos** (vs 12.3s en 2024). Los bots más exitosos generan entre $50K y $2.2M mensuales usando estrategias multi-capa combinadas con ejecución de baja latencia.

Este documento define la arquitectura completa, las estrategias ganadoras, los módulos de código y las reglas de gestión de riesgo para construir un bot competitivo.

---

## 🏆 Benchmark: Los Bots Más Exitosos

| Bot / Estrategia | Retorno | Win Rate | Estrategia Principal |
|---|---|---|---|
| **gabagool** (BTC 15min) | $313 → $414K en 1 mes | ~98% | Arbitraje asimétrico YES/NO |
| **Igor Mikerin AI Bot** | $2.2M en 2 meses | N/D | Ensemble ML + news sentiment |
| **0xalberto** (BTC-15m) | $764/día con $200 | ~85% | Market making + latency arb |
| **Market Makers generales** | 0.5–2% mensual | 78–85% | Provisión de liquidez (spread) |
| **News-reaction bots** | 3–8% mensual | 65–75% | Arbitraje de información |

### ¿Qué hacen diferente?
- **No predicen dirección.** Explotan ineficiencias de precio, no el resultado del evento.
- **Multi-estrategia:** combinan market making + arbitraje + copy trading.
- **Infraestructura dedicada:** VPS cerca de nodos Polygon, ejecución < 100ms.
- **Gestión de riesgo automatizada:** no más del 5% del portafolio por mercado.

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    POLYMARKET BOT v1.0                      │
├─────────────┬──────────────┬──────────────┬────────────────┤
│  DATA LAYER │ STRATEGY     │ EXECUTION    │ RISK MGMT      │
│             │ ENGINE       │ LAYER        │                │
│ • Gamma API │ • Arbitrage  │ • CLOB API   │ • Position     │
│ • CLOB WS   │   Scanner    │ • FOK Orders │   limits       │
│ • Data API  │ • Market     │ • Batch      │ • Stop-loss    │
│ • News Feed │   Maker      │   orders     │ • Daily cap    │
│ • Whale     │ • Copy       │ • WebSocket  │ • Kill switch  │
│   Tracker   │   Trading    │   streaming  │                │
└─────────────┴──────────────┴──────────────┴────────────────┘
         ↕                                         ↕
┌─────────────────┐                    ┌──────────────────────┐
│   PostgreSQL    │                    │   Monitoring &       │
│   (posiciones,  │                    │   Alertas (Telegram/ │
│    historial)   │                    │   Discord webhook)   │
└─────────────────┘                    └──────────────────────┘
```

---

## 📡 APIs & SDKs Necesarios

### APIs Oficiales de Polymarket

| API | Función | URL Base |
|---|---|---|
| **CLOB API** | Order book, trading, autenticación | `https://clob.polymarket.com` |
| **Gamma API** | Descubrimiento de mercados, metadata | `https://gamma-api.polymarket.com` |
| **Data API** | Posiciones, historial, wallets | `https://data-api.polymarket.com` |
| **WebSocket CLOB** | Stream tiempo real de precios | `wss://ws-subscriptions-clob.polymarket.com` |

### Rate Limits (Marzo 2026)
- Public endpoints: **100 requests/min**
- Trading endpoints: **60 orders/min por API key**
- Batch orders: hasta **15 órdenes por call**
- Gas por tx en Polygon: ~**$0.007**
- Fee taker (mercados generales): **~2%** | Fee maker: **0%**

### Stack Tecnológico Recomendado

```
Lenguaje:     Python 3.11+
SDK oficial:  py-clob-client  (pip install py-clob-client)
Alternativa:  polymarket-apis (pip install polymarket-apis)
DB:           PostgreSQL (historial) + Redis (caché en tiempo real)
Infra:        VPS en región us-east (cerca de nodos Polygon)
Monitoreo:    Prometheus + Grafana / o simple logging en archivo
Alertas:      Telegram Bot API o Discord Webhooks
```

---

## 🎯 Módulo 1: Estrategia de Arbitraje Asimétrico (gabagool-style)

**La estrategia más probada.** Basada en el bot `gabagool` que convirtió $313 en $414K.

### Lógica Central

En mercados binarios: `Precio YES + Precio NO ≈ $1.00`

Cuando traders emocionales distorsionan el precio, aparecen ventanas donde:
- YES cotiza a $0.20 y NO a $0.85 → spread total = $1.05 (sobrevaluado en ambos lados)
- YES cotiza a $0.45 y NO a $0.45 → spread total = $0.90 → **oportunidad de $0.10**

```python
# --- MÓDULO: arbitrage_scanner.py ---

import asyncio
from py_clob_client.client import ClobClient
from dataclasses import dataclass
from typing import Optional

@dataclass
class ArbitrageOpportunity:
    market_id: str
    yes_price: float
    no_price: float
    spread: float        # 1.0 - (yes + no) = ganancia potencial
    net_profit: float    # spread - fees (2% taker)
    
class ArbitrageScanner:
    """
    Escanea mercados buscando YES + NO < $0.97
    (dejando margen para el 2% de fee taker de Polymarket)
    """
    
    TAKER_FEE = 0.02
    MIN_SPREAD_NET = 0.025   # Mínimo 2.5% neto después de fees
    
    def __init__(self, client: ClobClient):
        self.client = client
    
    def scan_market(self, token_yes_id: str, token_no_id: str) -> Optional[ArbitrageOpportunity]:
        yes_ask = float(self.client.get_price(token_yes_id, side="BUY"))
        no_ask  = float(self.client.get_price(token_no_id, side="BUY"))
        
        total_cost = yes_ask + no_ask
        gross_spread = 1.0 - total_cost
        
        # Restar fees de ambas posiciones
        fees = (yes_ask + no_ask) * self.TAKER_FEE
        net_profit = gross_spread - fees
        
        if net_profit >= self.MIN_SPREAD_NET:
            return ArbitrageOpportunity(
                market_id=token_yes_id,
                yes_price=yes_ask,
                no_price=no_ask,
                spread=gross_spread,
                net_profit=net_profit
            )
        return None
    
    async def continuous_scan(self, markets: list[dict], callback):
        """Escaneo continuo con WebSocket para latencia mínima"""
        while True:
            for market in markets:
                opp = self.scan_market(market['yes_token'], market['no_token'])
                if opp:
                    await callback(opp)
            await asyncio.sleep(0.5)  # 500ms polling
```

---

## 💧 Módulo 2: Market Making (Ingresos Pasivos Estables)

**Win rate: 78–85% | Retorno: 0.5–2% mensual | Drawdown: < 1%**

El market maker coloca límit orders en ambos lados del libro, cobrando el spread bid-ask. En Polymarket, el **fee de maker es 0%**, lo que hace esta estrategia especialmente rentable.

```python
# --- MÓDULO: market_maker.py ---

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, Side
import time

class MarketMaker:
    """
    Provisión de liquidez automatizada.
    Coloca órdenes en ambos lados con spread configurable.
    """
    
    def __init__(self, client: ClobClient, config: dict):
        self.client = client
        self.spread_pct = config.get('spread_pct', 0.04)    # 4% spread por defecto
        self.order_size  = config.get('order_size', 50)      # USDC por orden
        self.max_inventory = config.get('max_inventory', 0.5) # Máx 50% del lado
        self.active_orders = {}
    
    def calculate_quotes(self, mid_price: float) -> tuple[float, float]:
        """Calcula bid y ask alrededor del mid-price"""
        half_spread = self.spread_pct / 2
        bid = round(mid_price - half_spread, 2)
        ask = round(mid_price + half_spread, 2)
        # Clampear entre 0.02 y 0.98 (Polymarket tick size)
        bid = max(0.02, min(0.98, bid))
        ask = max(0.02, min(0.98, ask))
        return bid, ask
    
    def refresh_quotes(self, token_id: str):
        """Cancela órdenes viejas y coloca nuevas"""
        # 1. Cancelar órdenes anteriores
        if token_id in self.active_orders:
            for order_id in self.active_orders[token_id]:
                try:
                    self.client.cancel(order_id)
                except Exception:
                    pass
        
        # 2. Obtener mid price actualizado
        mid = float(self.client.get_midpoint(token_id))
        bid, ask = self.calculate_quotes(mid)
        
        # 3. Colocar nuevas órdenes límit (fee = 0% como maker)
        new_orders = []
        
        buy_order = self.client.create_and_post_order(OrderArgs(
            token_id=token_id,
            price=bid,
            size=self.order_size,
            side=Side.BUY
        ))
        new_orders.append(buy_order['orderID'])
        
        sell_order = self.client.create_and_post_order(OrderArgs(
            token_id=token_id,
            price=ask,
            size=self.order_size,
            side=Side.SELL
        ))
        new_orders.append(sell_order['orderID'])
        
        self.active_orders[token_id] = new_orders
        return bid, ask
```

---

## 🐋 Módulo 3: Copy Trading de Wallets Exitosas

**La estrategia más accesible.** Identifica wallets con alto win-rate en blockchain y replica sus trades en milisegundos.

```python
# --- MÓDULO: copy_trader.py ---

import httpx
import asyncio
from typing import Callable

POLYMARKET_DATA_API = "https://data-api.polymarket.com"

class WhaleTracker:
    """
    Monitorea wallets exitosas y copia sus posiciones.
    La transparencia de blockchain hace públicas todas las apuestas.
    """
    
    def __init__(self, target_wallets: list[str], min_win_rate: float = 0.70):
        self.targets = target_wallets
        self.min_win_rate = min_win_rate
        self.known_positions = {}   # wallet → set(market_ids)
    
    async def get_wallet_trades(self, wallet: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{POLYMARKET_DATA_API}/activity",
                params={"user": wallet, "limit": 50}
            )
            return resp.json().get("data", [])
    
    async def get_wallet_performance(self, wallet: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{POLYMARKET_DATA_API}/portfolio-value",
                params={"address": wallet}
            )
            return resp.json()
    
    async def watch_and_copy(self, executor: Callable, poll_interval: float = 1.0):
        """
        Polling de 1s por wallet objetivo.
        Detecta nuevas posiciones y ejecuta réplica.
        """
        print(f"[WhaleTracker] Monitoreando {len(self.targets)} wallets...")
        
        while True:
            for wallet in self.targets:
                trades = await self.get_wallet_trades(wallet)
                
                for trade in trades:
                    market_id = trade.get("market")
                    if market_id not in self.known_positions.get(wallet, set()):
                        # Nueva posición detectada → replicar
                        if wallet not in self.known_positions:
                            self.known_positions[wallet] = set()
                        self.known_positions[wallet].add(market_id)
                        
                        print(f"[COPY] Wallet {wallet[:8]}... → {market_id}")
                        await executor(trade)
            
            await asyncio.sleep(poll_interval)

# Función para encontrar wallets exitosas en Dune Analytics o Data API
async def discover_top_wallets(min_profit_usdc: float = 5000) -> list[str]:
    """
    Filtra wallets con P&L > $5000 USDC para copiar.
    Ajustar threshold según capital disponible.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{POLYMARKET_DATA_API}/leaderboard",
            params={"limit": 100, "window": "1m"}
        )
        wallets = resp.json().get("data", [])
        return [
            w["proxyWallet"] 
            for w in wallets 
            if float(w.get("pnl", 0)) > min_profit_usdc
        ]
```

---

## 🛡️ Módulo 4: Gestión de Riesgo (No Negociable)

```python
# --- MÓDULO: risk_manager.py ---

from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class RiskConfig:
    total_capital: float          # Capital total en USDC
    max_per_market_pct: float = 0.05    # Máx 5% por mercado
    max_daily_loss_pct: float = 0.10    # Stop diario al -10%
    max_open_positions: int = 20        # Máx posiciones simultáneas
    kill_switch_enabled: bool = True
    alert_webhook: str = ""             # URL de Telegram/Discord

@dataclass  
class RiskState:
    daily_pnl: float = 0.0
    open_positions: dict = field(default_factory=dict)
    daily_trades: int = 0
    last_reset: datetime = field(default_factory=datetime.now)

class RiskManager:
    
    def __init__(self, config: RiskConfig):
        self.config = config
        self.state = RiskState()
        self.killed = False
    
    def max_position_size(self) -> float:
        """Calcula el tamaño máximo para una nueva posición"""
        return self.config.total_capital * self.config.max_per_market_pct
    
    def can_open_position(self, market_id: str, size: float) -> tuple[bool, str]:
        """Valida si se puede abrir una posición"""
        
        if self.killed:
            return False, "KILL SWITCH ACTIVO"
        
        if len(self.state.open_positions) >= self.config.max_open_positions:
            return False, f"Máximo de {self.config.max_open_positions} posiciones alcanzado"
        
        if size > self.max_position_size():
            return False, f"Tamaño {size} USDC excede límite de {self.max_position_size()} USDC"
        
        daily_loss = abs(min(0, self.state.daily_pnl))
        max_loss = self.config.total_capital * self.config.max_daily_loss_pct
        if daily_loss >= max_loss:
            self.trigger_kill_switch(f"Daily loss cap alcanzado: -{daily_loss:.2f} USDC")
            return False, "Daily loss cap alcanzado"
        
        return True, "OK"
    
    def update_pnl(self, realized_pnl: float):
        self.state.daily_pnl += realized_pnl
        logger.info(f"P&L diario actualizado: {self.state.daily_pnl:.2f} USDC")
    
    def trigger_kill_switch(self, reason: str):
        self.killed = True
        logger.critical(f"🚨 KILL SWITCH ACTIVADO: {reason}")
        # Aquí: cancelar todas las órdenes abiertas + notificar
        if self.config.alert_webhook:
            import httpx
            httpx.post(self.config.alert_webhook, json={
                "content": f"🚨 BOT DETENIDO: {reason}"
            })
```

---

## ⚡ Módulo 5: Autenticación y Setup Inicial

```python
# --- MÓDULO: setup.py ---
# IMPORTANTE: Nunca hardcodear claves privadas. Usar .env

import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()

def create_client() -> ClobClient:
    """
    Inicializa el cliente con credenciales desde variables de entorno.
    Soporta EOA wallets y proxy wallets (Magic/email).
    """
    HOST       = "https://clob.polymarket.com"
    CHAIN_ID   = 137   # Polygon Mainnet
    PRIVATE_KEY = os.environ["POLYMARKET_PRIVATE_KEY"]
    FUNDER      = os.environ["POLYMARKET_FUNDER_ADDRESS"]
    
    client = ClobClient(
        HOST,
        key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        signature_type=0,  # 0 = EOA estándar, 1 = Magic/email
        funder=FUNDER
    )
    
    # Deriv o cargar credenciales de API
    client.set_api_creds(client.create_or_derive_api_creds())
    
    return client

# .env file (NUNCA subir a GitHub):
# POLYMARKET_PRIVATE_KEY=0x...
# POLYMARKET_FUNDER_ADDRESS=0x...
# TELEGRAM_WEBHOOK=https://api.telegram.org/bot.../sendMessage
```

---

## 🚀 Bot Principal: Orquestador Multi-Estrategia

```python
# --- MÓDULO: main.py ---

import asyncio
import logging
from setup import create_client
from risk_manager import RiskManager, RiskConfig
from arbitrage_scanner import ArbitrageScanner
from market_maker import MarketMaker
from copy_trader import WhaleTracker, discover_top_wallets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PolyBot")

# ── Configuración ──────────────────────────────────────────────────
CAPITAL_USDC = 5_000     # Capital inicial (mínimo recomendado: $5K)

RISK_CONFIG = RiskConfig(
    total_capital=CAPITAL_USDC,
    max_per_market_pct=0.05,   # 5% máx por mercado = $250 por posición
    max_daily_loss_pct=0.10,   # Stop bot si pierde >$500/día
    max_open_positions=15,
    kill_switch_enabled=True,
    alert_webhook="https://hooks.slack.com/..."  # o Telegram
)

# Porcentaje del capital por estrategia
STRATEGY_ALLOCATION = {
    "market_making":  0.40,   # 40% capital → market making estable
    "arbitrage":      0.35,   # 35% capital → arbitraje asimétrico
    "copy_trading":   0.25,   # 25% capital → copy trading
}

async def main():
    logger.info("🤖 Iniciando PolyBot Multi-Strategy...")
    
    client = create_client()
    risk   = RiskManager(RISK_CONFIG)
    
    # ─── Estrategia 1: Market Making ───────────────────────────────
    mm_config = {
        "spread_pct": 0.04,
        "order_size": CAPITAL_USDC * STRATEGY_ALLOCATION["market_making"] / 10,
    }
    market_maker = MarketMaker(client, mm_config)
    
    # ─── Estrategia 2: Arbitraje ────────────────────────────────────
    arb_scanner = ArbitrageScanner(client)
    
    async def on_arbitrage(opp):
        can_trade, reason = risk.can_open_position(opp.market_id, 200)
        if not can_trade:
            logger.warning(f"Oportunidad bloqueada por risk manager: {reason}")
            return
        logger.info(f"💰 ARB detectado: {opp.market_id} | Net: {opp.net_profit:.3f} USDC")
        # Ejecutar compra simultánea YES+NO (Fill or Kill)
        # ...
    
    # ─── Estrategia 3: Copy Trading ─────────────────────────────────
    top_wallets = await discover_top_wallets(min_profit_usdc=10_000)
    whale_tracker = WhaleTracker(top_wallets[:10])  # Top 10 wallets
    
    async def on_copy(trade):
        can_trade, reason = risk.can_open_position(trade["market"], 100)
        if not can_trade:
            return
        logger.info(f"🐋 COPY: mercado {trade['market']} | lado {trade['side']}")
        # Ejecutar réplica...
    
    # ─── Correr todas las estrategias en paralelo ───────────────────
    markets_to_make = []   # Poblar con mercados de alta liquidez
    arb_markets = []       # Poblar con mercados binarios activos
    
    await asyncio.gather(
        whale_tracker.watch_and_copy(on_copy, poll_interval=1.0),
        arb_scanner.continuous_scan(arb_markets, on_arbitrage),
        # Market making: correr en loop separado con refresh cada 30s
    )

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📊 Infraestructura de Producción

### Requisitos Mínimos de Servidor

```yaml
# Para bot competitivo (no HFT extremo):
VPS:
  Region: us-east-1 o eu-west (cerca de nodos Polygon)
  CPU: 4 vCPU
  RAM: 8 GB
  Storage: 50 GB SSD
  Network: < 50ms latency a Polygon RPC
  Uptime: 99.9% garantizado
  
Costo estimado: $40–80/mes (DigitalOcean, Hetzner, Vultr)

# Para HFT/arbitraje de alta frecuencia:
VPS_Premium:
  Region: Dedicado, co-location con nodos Polygon
  CPU: 8+ vCPU (bare metal preferible)
  RAM: 16 GB
  Network: < 10ms a Polygon RPC
  Costo: $150–300/mes (QuantVPS especializado)
```

### Polygon RPC Recomendados

```
Gratis (rate-limitado):
  https://polygon-rpc.com

Premium (para producción):
  Alchemy:   https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
  QuickNode: https://your-endpoint.quiknode.pro/YOUR_KEY
  Chainstack: Más cercano a infraestructura de Polymarket
```

---

## 📈 Modelo de Capital & Proyecciones

| Capital Inicial | Estrategia Recomendada | Retorno Esperado/Mes | Riesgo |
|---|---|---|---|
| $500 – $2K | Copy Trading únicamente | 5–15% (alta varianza) | Alto |
| $2K – $10K | Arbitraje + Copy Trading | 3–8% mensual | Medio |
| $10K – $50K | Multi-estrategia completa | 1.5–5% mensual | Medio-Bajo |
| $50K+ | Market Making dominante | 0.5–2% mensual | Bajo |

> ⚠️ **Nota:** El mínimo recomendado para estrategias multi-mercado es **$5,000–$10,000 USDC**. Con menos capital, los fees del 2% absorben gran parte de las ganancias de arbitraje.

---

## 🔐 Seguridad (Crítico)

```
✅ SIEMPRE:
  - Usar wallet dedicada SOLO para el bot (nunca tu wallet personal)
  - Guardar private key en variable de entorno o secret manager (AWS Secrets, Doppler)
  - Mantener en la wallet solo el capital activo (resto en cold storage)
  - Implementar kill switch con notificación inmediata
  - Logs auditables de todas las transacciones

❌ NUNCA:
  - Hardcodear private keys en código
  - Subir .env a GitHub (agregar a .gitignore)
  - Dejar allowances ilimitadas en contratos no auditados
  - Correr el bot sin límites de pérdida configurados
```

---

## 📦 Estructura del Proyecto

```
polymarket-bot/
├── .env                    # Credenciales (NUNCA en git)
├── .gitignore
├── requirements.txt
├── main.py                 # Orquestador principal
├── setup.py                # Autenticación y cliente
├── config.yaml             # Configuración de estrategias
│
├── strategies/
│   ├── arbitrage_scanner.py
│   ├── market_maker.py
│   └── copy_trader.py
│
├── risk/
│   └── risk_manager.py
│
├── data/
│   ├── market_fetcher.py   # Gamma API wrapper
│   └── websocket_client.py # CLOB WebSocket stream
│
├── monitoring/
│   ├── alerts.py           # Telegram/Discord notifs
│   └── dashboard.py        # Métricas P&L en tiempo real
│
└── tests/
    ├── test_arbitrage.py
    └── test_risk_manager.py
```

---

## 🧪 Proceso de Testeo (Antes de Dinero Real)

### Fase 1: Paper Trading (Semana 1–2)
- Correr el bot en modo simulación sin ejecutar órdenes reales
- Loggear todas las oportunidades detectadas y calcular P&L hipotético
- Validar que la lógica de riesgo funciona correctamente

### Fase 2: Capital Mínimo (Semana 3–4)
- Depósito inicial de $200–500 USDC
- Límites de posición muy conservadores ($10–20 por trade)
- Monitoreo activo 24/7 durante los primeros días

### Fase 3: Escalar Gradualmente
- Incrementar capital solo si Sharpe ratio > 1.5 durante 2 semanas consecutivas
- No escalar durante periodos de alta volatilidad de eventos (elecciones, etc.)

---

## 📋 Checklist de Lanzamiento

- [ ] Wallet dedicada creada con fondos solo del bot
- [ ] `.env` configurado y fuera del repositorio git
- [ ] Allowances de USDC aprobadas en contratos de Polymarket
- [ ] Credenciales CLOB API generadas con `create_or_derive_api_creds()`
- [ ] Kill switch y alertas de Telegram/Discord configurados
- [ ] VPS corriendo con latencia < 50ms a Polygon RPC
- [ ] Base de datos PostgreSQL inicializada para historial
- [ ] Paper trading validado por ≥ 1 semana
- [ ] Límites de riesgo definidos y testeados
- [ ] Backtest de estrategia con datos históricos (mínimo 3 meses)

---

## 📚 Recursos y Referencias

| Recurso | URL |
|---|---|
| Documentación oficial Polymarket | `https://docs.polymarket.com` |
| py-clob-client (GitHub oficial) | `https://github.com/Polymarket/py-clob-client` |
| polymarket-apis (PyPI) | `https://pypi.org/project/polymarket-apis/` |
| NautilusTrader integration | `https://nautilustrader.io/docs/latest/integrations/polymarket/` |
| Guía API completa 2026 | `https://agentbets.ai/guides/polymarket-api-guide/` |
| Ecosystem map de bots | `https://agentbets.ai/platforms/polymarket-bots/` |
| Análisis de estrategias exitosas | `https://www.quantvps.com/blog/polymarket-hft-traders-use-ai-arbitrage-mispricing` |

---

> **⚠️ Disclaimer:** Trading en mercados de predicción conlleva riesgo significativo de pérdida de capital. El 92% de los traders pierde dinero. Esta propuesta es educativa y técnica. Siempre hacer due diligence y nunca arriesgar más del que puedas permitirte perder. Verificar la regulación aplicable en tu jurisdicción.

---

*Propuesta generada con research de Q3 2025 – Q1 2026 | Última actualización: Marzo 2026*

---

## PR2 Runtime (paper-mode) — quick local run

Esta sección documenta el slice implementado en PR #2 (runtime + estrategia determinística + logging/persistencia JSONL), manteniendo límites de alcance.

### Alcance PR2

- ✅ Soportado: ejecución local en **paper mode** con loop acotado por ticks.
- ✅ Soportado: estrategia determinística única y pipeline via `Client.place_order_async`.
- ✅ Soportado: eventos estructurados persistidos en JSONL.
- ❌ No soportado en PR2: modo live / integración real de exchange / expansión de CI.

### Comando de ejecución

```bash
python3 -m polymarket_bot.runtime_main --paper-mode true --interval 1 --max-ticks 3 --market-id demo-market --events-path ./runtime-events.jsonl
```

### Variables de entorno runtime

- `RUNTIME_TICK_SECONDS` (float > 0)
- `RUNTIME_MAX_TICKS` (int > 0)
- `RUNTIME_EVENTS_PATH` (path JSONL)
- `RUNTIME_MARKET_ID` (string)

### Nota de boundary

Si se intenta `--paper-mode false`, el entrypoint falla rápido con error explícito indicando que live mode queda diferido a PR3.
