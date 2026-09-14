import urllib.request
import json
import os
from datetime import datetime, timezone, timedelta

EAT_OFFSET = 3  # East Africa Time = UTC+3

def _eat_time(dt_utc):
    """Convert UTC datetime to EAT (UTC+3) time string."""
    eat = dt_utc + timedelta(hours=EAT_OFFSET)
    return eat.strftime("%H:%M EAT")

class NewsCatalystEngine:
    """
    Real-Time Economic News & Macro Catalyst Engine.
    Fetches official institutional calendar feeds with persistent disk caching.
    Sends daily briefing on startup and 30-minute countdown alerts before each event.
    """
    def __init__(self, high_impact_only=True):
        self.url = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
        self.cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "economic_calendar_cache.json")
        self.high_impact_only = high_impact_only
        self.events = []
        self.last_sync = None
        self._alerted_30min = set()   # tracks event keys already sent 30-min alert
        self._daily_briefing_sent = None  # date string of last briefing sent
        self._load_disk_cache()
        self.sync_calendar()

    def _load_disk_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                parsed = []
                for item in cached:
                    try:
                        dt_utc = datetime.fromtimestamp(item['timestamp'], tz=timezone.utc)
                        item['dt_utc'] = dt_utc
                        parsed.append(item)
                    except Exception:
                        continue
                self.events = parsed
            except Exception:
                pass

    def _save_disk_cache(self):
        try:
            to_save = []
            for ev in self.events:
                to_save.append({
                    'title': ev['title'],
                    'country': ev['country'],
                    'impact': ev['impact'],
                    'forecast': ev.get('forecast', ''),
                    'previous': ev.get('previous', ''),
                    'timestamp': ev['timestamp']
                })
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(to_save, f, indent=2)
        except Exception:
            pass

    def sync_calendar(self, force=False):
        now_utc = datetime.now(timezone.utc)
        if not force and self.last_sync is not None:
            if (now_utc - self.last_sync).total_seconds() < 900: # 15 min cache
                return True
                
        try:
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read().decode())
                
            parsed = []
            for item in raw:
                country = item.get('country')
                if country not in ['USD', 'EUR']:
                    continue
                impact = item.get('impact')
                if self.high_impact_only and impact != 'High':
                    continue
                date_str = item.get('date')
                try:
                    dt = datetime.fromisoformat(date_str)
                    dt_utc = dt.astimezone(timezone.utc)
                except Exception:
                    continue
                parsed.append({
                    'title': item.get('title'),
                    'country': country,
                    'impact': impact,
                    'forecast': item.get('forecast', ''),
                    'previous': item.get('previous', ''),
                    'dt_utc': dt_utc,
                    'timestamp': dt_utc.timestamp()
                })
            self.events = parsed
            self.last_sync = now_utc
            self._save_disk_cache()
            return True
        except Exception:
            # On rate limit or network issue, back off for 15 minutes and use existing cache
            self.last_sync = now_utc
            return False

    def get_upcoming_events(self, symbol, within_minutes=60):
        now_utc = datetime.now(timezone.utc)
        target_curr = 'USD' if 'XAU' in symbol or 'US' in symbol else 'EUR'
        upcoming = []
        for ev in self.events:
            if ev['country'] == target_curr:
                diff_min = (ev['dt_utc'] - now_utc).total_seconds() / 60.0
                if 0 <= diff_min <= within_minutes:
                    upcoming.append({
                        'title': ev['title'],
                        'country': ev['country'],
                        'minutes_away': round(diff_min, 1),
                        'forecast': ev.get('forecast', ''),
                        'previous': ev.get('previous', '')
                    })
        return upcoming

    def get_market_catalyst_status(self, symbol):
        now_utc = datetime.now(timezone.utc)
        target_curr = 'USD' if 'XAU' in symbol or 'US' in symbol else 'EUR'

        for ev in self.events:
            if ev['country'] == target_curr:
                diff_min = (now_utc - ev['dt_utc']).total_seconds() / 60.0

                # 5 min BEFORE news: freeze entries, lock BE on winning trades
                if -5.0 <= diff_min < 0:
                    return {
                        'state': 'PRE_NEWS_FREEZE',
                        'event': ev['title'],
                        'minutes_to_release': abs(round(diff_min, 1)),
                        'action': 'LOCK_BE_NO_NEW_ENTRY'
                    }

                # 0–5 min AFTER news: spike chaos zone — NO entries, price gapping everywhere
                elif 0 <= diff_min < 5.0:
                    return {
                        'state': 'NEWS_SPIKE_BLOCK',
                        'event': ev['title'],
                        'minutes_since_release': round(diff_min, 1),
                        'action': 'NO_ENTRY_SPIKE_DANGER'
                    }

                # 5–25 min AFTER news: direction confirmed, ride momentum with expanded TP
                elif 5.0 <= diff_min <= 25.0:
                    return {
                        'state': 'CATALYST_IMPULSE',
                        'event': ev['title'],
                        'minutes_since_release': round(diff_min, 1),
                        'action': 'EXPAND_TP_RIDE_TREND'
                    }

        return {'state': 'NORMAL', 'action': 'STANDARD_M15_RULES'}

    # ── Telegram helpers ─────────────────────────────────────────────────────────
    def _telegram(self, message):
        """Send to owner DM only — news briefings and alerts are private/operational, not public signals."""
        token   = os.getenv("TELEGRAM_TOKEN",   "8617130364:AAHiEg1W9A-L5f7XkqVzgV6mTotb7TSiJV0")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "915238743")
        if not token or not chat_id:
            return
        url = "https://api.telegram.org/bot" + token + "/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            try:
                payload.pop("parse_mode", None)
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10):
                    pass
            except Exception:
                pass

    def send_daily_briefing(self):
        """
        Sends a daily news briefing via Telegram at bot startup (once per day).
        Lists all high-impact USD & EUR events scheduled for today in EAT time.
        """
        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.strftime("%Y-%m-%d")

        # Only send once per calendar day
        if self._daily_briefing_sent == today_str:
            return

        today_start = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0, tzinfo=timezone.utc)
        today_end   = today_start + timedelta(days=1)

        todays_events = [
            ev for ev in self.events
            if today_start <= ev['dt_utc'] < today_end
        ]

        today_eat = (now_utc + timedelta(hours=EAT_OFFSET)).strftime("%A, %d %b %Y")

        if not todays_events:
            msg = (
                "<b>📅 AlphaEdge Daily News Briefing</b>\n"
                f"<b>{today_eat}</b>\n\n"
                "✅ No high-impact USD/EUR news events scheduled today.\n"
                "Free to trade normally all session."
            )
        else:
            lines = []
            for ev in sorted(todays_events, key=lambda x: x['timestamp']):
                eat_str = _eat_time(ev['dt_utc'])
                flag = "🇺🇸" if ev['country'] == "USD" else "🇪🇺"
                forecast = f" | Forecast: {ev['forecast']}" if ev.get('forecast') else ""
                lines.append(f"  {flag} <b>{eat_str}</b> — {ev['title']}{forecast}")

            msg = (
                "<b>📅 AlphaEdge Daily News Briefing</b>\n"
                f"<b>{today_eat}</b>\n\n"
                "<b>⚠️ High-Impact Events Today:</b>\n"
                + "\n".join(lines)
                + "\n\n"
                "🤖 Bot will auto-freeze entries 5 min before each event.\n"
                "You will receive a 30-min heads-up before each release."
            )

        self._telegram(msg)
        self._daily_briefing_sent = today_str

    def check_and_send_30min_alerts(self):
        """
        Called every bot cycle (~60s). Fires a Telegram alert once per event
        when it is 28–32 minutes away so the trader can prepare for manual entries.
        """
        now_utc = datetime.now(timezone.utc)

        for ev in self.events:
            diff_min = (ev['dt_utc'] - now_utc).total_seconds() / 60.0

            # Window: 28–32 min before (fires once, won't repeat)
            if 28.0 <= diff_min <= 32.0:
                event_key = ev['title'] + ev['dt_utc'].strftime("%Y%m%d%H%M")
                if event_key in self._alerted_30min:
                    continue  # already sent for this event

                eat_str = _eat_time(ev['dt_utc'])
                flag = "🇺🇸" if ev['country'] == "USD" else "🇪🇺"
                forecast = f"\nForecast: <b>{ev['forecast']}</b>" if ev.get('forecast') else ""
                previous = f" | Prev: {ev['previous']}" if ev.get('previous') else ""

                msg = (
                    "⏰ <b>30-Minute News Alert</b>\n\n"
                    f"{flag} <b>{ev['title']}</b>\n"
                    f"Releases at: <b>{eat_str}</b>{forecast}{previous}\n\n"
                    "🤖 Bot will freeze new entries at T-5 min.\n"
                    "📊 After release, watch price for confirmed direction before entering manually.\n"
                    "⚡ Bot resumes with expanded TP at T+5 min."
                )
                self._telegram(msg)
                self._alerted_30min.add(event_key)

