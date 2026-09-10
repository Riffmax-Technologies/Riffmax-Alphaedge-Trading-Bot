import urllib.request
import json
import os
from datetime import datetime, timezone, timedelta

class NewsCatalystEngine:
    """
    Real-Time Economic News & Macro Catalyst Engine.
    Fetches official institutional calendar feeds with persistent disk caching.
    """
    def __init__(self, high_impact_only=True):
        self.url = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
        self.cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "economic_calendar_cache.json")
        self.high_impact_only = high_impact_only
        self.events = []
        self.last_sync = None
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
                if -5.0 <= diff_min < 0:
                    return {
                        'state': 'PRE_NEWS_FREEZE',
                        'event': ev['title'],
                        'minutes_to_release': abs(round(diff_min, 1)),
                        'action': 'LOCK_BE_NO_NEW_ENTRY'
                    }
                elif 0 <= diff_min <= 25.0:
                    return {
                        'state': 'CATALYST_IMPULSE',
                        'event': ev['title'],
                        'minutes_since_release': round(diff_min, 1),
                        'action': 'EXPAND_TP_RIDE_TREND'
                    }
        return {'state': 'NORMAL', 'action': 'STANDARD_M15_RULES'}
