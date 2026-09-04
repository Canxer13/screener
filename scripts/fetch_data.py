import argparse
import json
import os
import sys
from datetime import datetime, timedelta
import yfinance as yf
from dotenv import load_dotenv

# Try to import alpaca, but don't fail if it's not configured
try:
    from alpaca_trade_api.rest import REST, TimeFrame
    HAS_ALPACA = True
except ImportError:
    HAS_ALPACA = False

load_dotenv()

def get_alpaca_client():
    if not HAS_ALPACA:
        return None
    api_key = os.getenv('APCA_API_KEY_ID')
    api_secret = os.getenv('APCA_API_SECRET_KEY')
    base_url = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
    if api_key and api_secret:
        return REST(api_key, api_secret, base_url, api_version='v2')
    return None

def format_error(msg, code="INTERNAL_ERROR"):
    return json.dumps({
        "success": False,
        "error": msg,
        "error_code": code
    })

def format_success(data):
    return json.dumps({
        "success": True,
        "data": data
    }, indent=2)

def get_price_data(symbols, timeframe="1Day", start_date=None, end_date=None, limit=100):
    try:
        data = {}
        # Simple mapping for yfinance intervals
        yf_intervals = {
            "1Min": "1m",
            "5Min": "5m",
            "1Hour": "1h",
            "1Day": "1d"
        }
        interval = yf_intervals.get(timeframe, "1d")
        
        for symbol in symbols:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="max" if start_date else f"{limit}d", interval=interval, start=start_date, end=end_date)
            
            # If limited by limit
            if not start_date and not end_date and len(hist) > limit:
                hist = hist.tail(limit)
                
            symbol_data = []
            for date, row in hist.iterrows():
                symbol_data.append({
                    "timestamp": date.isoformat() + "Z" if hasattr(date, "isoformat") else str(date),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"])
                })
            data[symbol] = symbol_data
            
        return format_success(data)
    except Exception as e:
        return format_error(str(e))

def get_latest_news(symbols, limit=10, sources=None):
    client = get_alpaca_client()
    try:
        data = []
        if client:
            news = client.get_news(symbol=",".join(symbols), limit=limit)
            for n in news:
                # Alpaca news object
                for sym in n.symbols:
                    if sym in symbols:
                        data.append({
                            "symbol": sym,
                            "headline": n.headline,
                            "summary": n.summary,
                            "source": n.source,
                            "url": n.url,
                            "published_at": n.created_at.isoformat(),
                            "sentiment": "neutral" # basic sentiment placeholder
                        })
        else:
            # Fallback to yfinance news
            for symbol in symbols:
                ticker = yf.Ticker(symbol)
                news = ticker.news
                if news:
                    for n in news[:limit]:
                        data.append({
                            "symbol": symbol,
                            "headline": n.get("title", ""),
                            "summary": n.get("summary", ""),
                            "source": n.get("publisher", ""),
                            "url": n.get("link", ""),
                            "published_at": datetime.fromtimestamp(n.get("providerPublishTime", 0)).isoformat() + "Z",
                            "sentiment": "neutral"
                        })
        return format_success(data[:limit])
    except Exception as e:
        return format_error(str(e))

def get_fundamentals(symbols, metrics=None):
    try:
        data = {}
        for symbol in symbols:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            data[symbol] = {
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "eps": info.get("trailingEps", 0),
                "dividend_yield": info.get("dividendYield", 0),
                "beta": info.get("beta", 0),
                "52_week_high": info.get("fiftyTwoWeekHigh", 0),
                "52_week_low": info.get("fiftyTwoWeekLow", 0)
            }
        return format_success(data)
    except Exception as e:
        return format_error(str(e))

def get_market_snapshot(symbols):
    try:
        data = {}
        client = get_alpaca_client()
        if client:
            snapshots = client.get_snapshots(symbols)
            for symbol, snap in snapshots.items():
                data[symbol] = {
                    "price": float(snap.latest_trade.p) if snap.latest_trade else 0,
                    "bid": float(snap.latest_quote.bp) if snap.latest_quote else 0,
                    "ask": float(snap.latest_quote.ap) if snap.latest_quote else 0,
                    "bid_size": int(snap.latest_quote.bs) if snap.latest_quote else 0,
                    "ask_size": int(snap.latest_quote.as_) if snap.latest_quote else 0,
                    "last_trade_time": snap.latest_trade.t.isoformat() if snap.latest_trade else "",
                    "volume": int(snap.daily_bar.v) if snap.daily_bar else 0,
                    "vwap": float(snap.daily_bar.vw) if snap.daily_bar else 0
                }
        else:
            for symbol in symbols:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                data[symbol] = {
                    "price": info.get("currentPrice", 0),
                    "bid": info.get("bid", 0),
                    "ask": info.get("ask", 0),
                    "bid_size": info.get("bidSize", 0),
                    "ask_size": info.get("askSize", 0),
                    "last_trade_time": datetime.utcnow().isoformat() + "Z", # Approx
                    "volume": info.get("volume", 0),
                    "vwap": 0 # Not easily available without calculating
                }
        return format_success(data)
    except Exception as e:
        return format_error(str(e))

def main():
    parser = argparse.ArgumentParser(description="Financial Data Fetcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # get_price_data
    parser_price = subparsers.add_parser("get_price_data")
    parser_price.add_argument("--symbols", nargs="+", required=True)
    parser_price.add_argument("--timeframe", default="1Day")
    parser_price.add_argument("--start_date")
    parser_price.add_argument("--end_date")
    parser_price.add_argument("--limit", type=int, default=100)
    
    # get_latest_news
    parser_news = subparsers.add_parser("get_latest_news")
    parser_news.add_argument("--symbols", nargs="+", required=True)
    parser_news.add_argument("--limit", type=int, default=10)
    parser_news.add_argument("--sources", nargs="*")
    
    # get_fundamentals
    parser_fund = subparsers.add_parser("get_fundamentals")
    parser_fund.add_argument("--symbols", nargs="+", required=True)
    parser_fund.add_argument("--metrics", nargs="*")
    
    # get_market_snapshot
    parser_snap = subparsers.add_parser("get_market_snapshot")
    parser_snap.add_argument("--symbols", nargs="+", required=True)
    
    args = parser.parse_args()
    
    if args.command == "get_price_data":
        print(get_price_data(args.symbols, args.timeframe, args.start_date, args.end_date, args.limit))
    elif args.command == "get_latest_news":
        print(get_latest_news(args.symbols, args.limit, args.sources))
    elif args.command == "get_fundamentals":
        print(get_fundamentals(args.symbols, args.metrics))
    elif args.command == "get_market_snapshot":
        print(get_market_snapshot(args.symbols))
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
