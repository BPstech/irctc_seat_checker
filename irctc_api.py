"""
irctc_api.py - Direct IRCTC Online Charts automation engine.
Uses a headless browser session to securely communicate with IRCTC/CRIS internal APIs.
"""

import os
import json
import re
import time
import threading
import logging
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BERTH_TYPE_MAP = {
    'L': 'Lower Berth',
    'M': 'Middle Berth',
    'U': 'Upper Berth',
    'SL': 'Side Lower',
    'SU': 'Side Upper',
    'SM': 'Side Middle',
    'CB': 'Cabin',
    'CP': 'Coupe',
    'W': 'Window Seat',
    'A': 'Aisle Seat',
    'P': 'Coupe / Berth',
    'R': 'Cabin Berth'
}

CLASS_NAME_MAP = {
    '1A': 'AC First Class (1A)',
    '2A': 'AC 2 Tier (2A)',
    '3A': 'AC 3 Tier (3A)',
    '3E': 'AC 3 Economy (3E)',
    'SL': 'Sleeper (SL)',
    'CC': 'AC Chair Car (CC)',
    '2S': 'Second Sitting (2S)',
    'EC': 'Exec. Chair Car (EC)',
    'EA': 'Anubhuti (EA)',
    'EV': 'Vistadome AC (EV)',
    'FC': 'First Class (FC)',
    'VS': 'Vistadome Non-AC (VS)',
    'VC': 'Vistadome Chair Car (VC)'
}

def coach_sort_key(coach_str):
    """
    Naturally sorts coach codes (e.g. 'B2' before 'B10'):
    1. By class prefix priority: H (1A), A (2A), B (3A), M (3E), C (CC), E (EC), S (SL), D (2S)
    2. By integer coach number: 1, 2, 3 ... 9, 10, 11, 12 ...
    """
    m = re.match(r'([A-Za-z]+)(\d+)', str(coach_str).strip())
    if m:
        pfx, num = m.groups()
        prefix_order = {'H': 0, 'HA': 1, 'A': 2, 'B': 3, 'M': 4, 'C': 5, 'E': 6, 'EA': 7, 'EV': 8, 'S': 9, 'D': 10}
        return (prefix_order.get(pfx.upper(), 50), pfx.upper(), int(num))
    return (99, str(coach_str), 0)

class IRCTCService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(IRCTCService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.driver = None
        self.driver_lock = threading.Lock()
        self.schedule_cache = {}
        self.classes_cache = {}
        self._load_cache()
        self._init_driver()
        self._initialized = True

    def _load_cache(self):
        """Preload schedule cache from disk if available"""
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schedule_cache.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    now = time.time()
                    for k, v in data.items():
                        self.schedule_cache[str(k).strip()] = (now, v)
                logger.info(f"Loaded {len(self.schedule_cache)} train schedules from disk cache.")
            except Exception as e:
                logger.warning(f"Could not load schedule_cache.json: {e}")

    def _save_cache(self, train_no, data):
        """Persist schedule to disk cache"""
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schedule_cache.json')
        try:
            existing = {}
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                except Exception:
                    existing = {}
            existing[str(train_no).strip()] = data
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save to schedule_cache.json: {e}")

    def _init_driver(self):
        try:
            logger.info("Initializing headless Chrome driver for IRCTC...")
            opts = Options()
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--disable-gpu')
            opts.add_argument('--disable-software-rasterizer')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_argument('--log-level=3')
            opts.add_argument('--silent')
            opts.add_experimental_option('excludeSwitches', ['enable-logging'])
            opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            import shutil
            from selenium.webdriver.chrome.service import Service

            # Detect Linux/Docker Chromium binary location if available
            chrome_bin = (
                shutil.which('chromium') or 
                shutil.which('chromium-browser') or 
                shutil.which('google-chrome') or
                shutil.which('google-chrome-stable')
            )
            if chrome_bin:
                opts.binary_location = chrome_bin

            driver_bin = shutil.which('chromedriver')
            if driver_bin:
                self.driver = webdriver.Chrome(service=Service(executable_path=driver_bin), options=opts)
            else:
                self.driver = webdriver.Chrome(options=opts)

            self.driver.get('https://www.irctc.co.in/online-charts/')
            time.sleep(2)
            logger.info("Chrome driver initialized and navigated to IRCTC online charts.")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            self.driver = None

    def ensure_driver(self):
        try:
            if not self.driver:
                self._init_driver()
            else:
                # Quick health check
                _ = self.driver.title
                if 'online-charts' not in getattr(self.driver, 'current_url', ''):
                    logger.warning("Driver not on online-charts page, navigating back...")
                    self.driver.get('https://www.irctc.co.in/online-charts/')
                    time.sleep(2)
        except Exception:
            logger.warning("Driver health check failed, re-initializing...")
            self._init_driver()

    def get_train_schedule(self, train_no):
        """Fetch train schedule containing list of stations with memory caching"""
        t_key = str(train_no).strip()
        now = time.time()
        cached = self.schedule_cache.get(t_key)
        if not cached:
            self._load_cache()
            cached = self.schedule_cache.get(t_key)
        if cached and (now - cached[0] < 43200):
            return cached[1]

        with self.driver_lock:
            cached = self.schedule_cache.get(t_key)
            if cached and (now - cached[0] < 43200):
                return cached[1]

            self.ensure_driver()
            js = """
            const callback = arguments[arguments.length - 1];
            const trainNo = arguments[0];
            fetch('https://www.irctc.co.in/eticketing/protected/mapps1/trnscheduleenquiry/' + trainNo, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'greq': new Date().getTime(),
                    'bmirak': 'webbm'
                }
            })
            .then(async r => {
                const text = await r.text();
                try {
                    const data = JSON.parse(text);
                    callback({success: r.ok, data: data, status: r.status});
                } catch(e) {
                    if (text.includes('MAINTENANCE') || text.includes('maintenance')) {
                        callback({
                            success: false,
                            status: r.status,
                            isMaintenance: true,
                            error: 'IRCTC servers are currently under daily maintenance downtime (23:45 to 00:20 hrs IST). Normal chart queries resume automatically at 00:20 IST.'
                        });
                    } else {
                        callback({
                            success: false,
                            status: r.status,
                            error: 'IRCTC server returned non-JSON response (Status ' + r.status + ')'
                        });
                    }
                }
            })
            .catch(err => callback({success: false, error: err.toString()}));
            """
            try:
                res = self.driver.execute_async_script(js, t_key)
                # If Failed to fetch occurred (e.g. session stale), refresh session and retry once
                if not res.get('success') and 'Failed to fetch' in str(res.get('error', '')):
                    logger.warning("Fetch failed in driver, refreshing online-charts session and retrying...")
                    self.driver.get('https://www.irctc.co.in/online-charts/')
                    time.sleep(2)
                    res = self.driver.execute_async_script(js, t_key)

                if res.get('success'):
                    data = res.get('data', {})
                    if data.get('errorMessage'):
                        return {'success': False, 'message': data['errorMessage']}
                    result = {
                        'success': True,
                        'trainName': data.get('trainName', ''),
                        'stationList': data.get('stationList', [])
                    }
                    if result['stationList']:
                        self.schedule_cache[t_key] = (now, result)
                        self._save_cache(t_key, result)
                    return result
                return {'success': False, 'message': res.get('error', 'Failed to fetch schedule')}
            except Exception as e:
                logger.error(f"Error in get_train_schedule: {e}")
                return {'success': False, 'message': str(e)}

    def get_train_composition(self, train_no, journey_date, boarding_stn):
        """Fetch coach composition and chart preparation status"""
        with self.driver_lock:
            self.ensure_driver()
            js = """
            const callback = arguments[arguments.length - 1];
            const payload = arguments[0];
            fetch('/online-charts/api/trainComposition', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(payload)
            })
            .then(async r => {
                const text = await r.text();
                try {
                    const data = JSON.parse(text);
                    callback({success: r.ok, data: data, status: r.status});
                } catch(e) {
                    if (text.includes('MAINTENANCE') || text.includes('maintenance')) {
                        callback({
                            success: false,
                            status: r.status,
                            isMaintenance: true,
                            error: 'IRCTC servers are currently under daily maintenance downtime (23:45 to 00:20 hrs IST). Normal chart queries resume automatically at 00:20 IST.'
                        });
                    } else {
                        callback({
                            success: false,
                            status: r.status,
                            error: 'IRCTC server returned non-JSON response (Status ' + r.status + ')'
                        });
                    }
                }
            })
            .catch(err => callback({success: false, error: err.toString()}));
            """
            try:
                res = self.driver.execute_async_script(js, {
                    "trainNo": str(train_no).strip(),
                    "jDate": str(journey_date).strip(),
                    "boardingStation": str(boarding_stn).strip()
                })
                if res.get('success'):
                    data = res.get('data', {})
                    return {'success': True, 'data': data}
                return {'success': False, 'message': res.get('error', 'Failed to fetch train composition')}
            except Exception as e:
                logger.error(f"Error in get_train_composition: {e}")
                return {'success': False, 'message': str(e)}

    def get_train_classes(self, train_no, journey_date=None, boarding_stn=None, station_list=None):
        """
        Dynamically determine available travel classes for a specific train with memory caching.
        Tries current journey date composition, then falls back to recent days (yesterday).
        Returns a list of dicts: [{'code': '3A', 'name': 'AC 3 Tier (3A)'}, ...]
        """
        t_key = str(train_no).strip()
        now = time.time()
        cached = self.classes_cache.get(t_key)
        if cached and (now - cached[0] < 43200):
            return cached[1]

        source_stn = boarding_stn
        if not source_stn:
            if not station_list:
                sched = self.get_train_schedule(t_key)
                station_list = sched.get('stationList', [])
            if station_list:
                source_stn = station_list[0].get('stationCode')
        
        if not source_stn:
            return []

        if not journey_date:
            journey_date = datetime.now().strftime('%Y-%m-%d')

        classes_found = []
        
        # 1. Try specified journey date
        comp = self.get_train_composition(t_key, journey_date, source_stn)
        cdd = comp.get('data', {}).get('cdd') or []
        raw_classes = set(c['classCode'] for c in cdd if c.get('classCode'))
        if raw_classes:
            classes_found = sorted(list(raw_classes))

        # 2. If chart not prepared or cdd empty, check yesterday (fast 1-day fallback)
        if not classes_found:
            prev_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            prev_comp = self.get_train_composition(t_key, prev_date, source_stn)
            prev_cdd = prev_comp.get('data', {}).get('cdd') or []
            prev_classes = set(c['classCode'] for c in prev_cdd if c.get('classCode'))
            if prev_classes:
                classes_found = sorted(list(prev_classes))

        # 3. Graceful fallback to standard classes if not prepared yet or during maintenance
        if not classes_found:
            classes_found = ['1A', '2A', '3A', '3E', 'SL', '2S']

        # Standard class sorting order
        class_order = ['1A', '2A', '3A', '3E', 'EC', 'EA', 'CC', 'EV', 'SL', 'FC', '2S', 'VS', 'VC']
        def sort_key(c):
            return class_order.index(c) if c in class_order else 99

        classes_found.sort(key=sort_key)

        result = [
            {
                'code': cls_code,
                'name': CLASS_NAME_MAP.get(cls_code, f"{cls_code} Class")
            }
            for cls_code in classes_found
        ]
        if result:
            self.classes_cache[t_key] = (now, result)
        return result

    def get_vacant_berths_batch(self, train_no, boarding_stn, remote_stn, source_stn, j_date, classes):
        """Fetch all vacant berths for multiple classes concurrently in a single browser roundtrip."""
        if not classes:
            return {}
        with self.driver_lock:
            self.ensure_driver()
            js = """
            const callback = arguments[arguments.length - 1];
            const p = arguments[0];
            const promises = p.classes.map(cls =>
                fetch('/online-charts/api/vacantBerth', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({
                        trainNo: p.trainNo,
                        boardingStation: p.boardingStation,
                        remoteStation: p.remoteStation,
                        trainSourceStation: p.sourceStation,
                        jDate: p.jDate,
                        cls: cls,
                        chartType: 1
                    })
                })
                .then(async r => {
                    const text = await r.text();
                    try {
                        const data = JSON.parse(text);
                        return { cls: cls, vbd: data.vbd || [] };
                    } catch {
                        return { cls: cls, vbd: [] };
                    }
                })
                .catch(() => ({ cls: cls, vbd: [] }))
            );

            Promise.all(promises)
                .then(results => callback({ success: true, results: results }))
                .catch(err => callback({ success: false, error: err.toString() }));
            """
            try:
                res = self.driver.execute_async_script(js, {
                    "trainNo": str(train_no).strip(),
                    "boardingStation": str(boarding_stn).strip(),
                    "remoteStation": remote_stn,
                    "sourceStation": source_stn,
                    "jDate": str(j_date).strip(),
                    "classes": classes
                })
                out = {}
                if res.get('success'):
                    for item in res.get('results', []):
                        out[item['cls']] = item.get('vbd', [])
                return out
            except Exception as e:
                logger.error(f"Error in get_vacant_berths_batch: {e}")
                return {}

    def get_vacant_berths_for_class(self, train_no, boarding_stn, remote_stn, source_stn, j_date, cls):
        """Fetch all vacant berths for a specific class"""
        with self.driver_lock:
            self.ensure_driver()
            js = """
            const callback = arguments[arguments.length - 1];
            const payload = arguments[0];
            fetch('/online-charts/api/vacantBerth', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(payload)
            })
            .then(async r => {
                const text = await r.text();
                try {
                    const data = JSON.parse(text);
                    callback({success: r.ok, data: data, status: r.status});
                } catch(e) {
                    if (text.includes('MAINTENANCE') || text.includes('maintenance')) {
                        callback({
                            success: false,
                            status: r.status,
                            isMaintenance: true,
                            error: 'IRCTC servers are currently under daily maintenance downtime (23:45 to 00:20 hrs IST). Normal chart queries resume automatically at 00:20 IST.'
                        });
                    } else {
                        callback({
                            success: false,
                            status: r.status,
                            error: 'IRCTC server returned non-JSON response (Status ' + r.status + ')'
                        });
                    }
                }
            })
            .catch(err => callback({success: false, error: err.toString()}));
            """
            try:
                res = self.driver.execute_async_script(js, {
                    "trainNo": str(train_no).strip(),
                    "boardingStation": str(boarding_stn).strip(),
                    "remoteStation": remote_stn,
                    "trainSourceStation": source_stn,
                    "jDate": str(j_date).strip(),
                    "cls": str(cls).strip(),
                    "chartType": 1
                })
                if res.get('success'):
                    data = res.get('data', {})
                    return data.get('vbd', [])
                return []
            except Exception as e:
                logger.error(f"Error in get_vacant_berths_for_class: {e}")
                return []

    def find_station_match(self, query, station_list):
        """Match station input (code or name) against train schedule stations"""
        query_norm = query.strip().upper()
        # 1. Exact match on stationCode
        for s in station_list:
            if s.get('stationCode', '').upper() == query_norm:
                return s
        # 2. Exact match on stationName
        for s in station_list:
            if s.get('stationName', '').upper() == query_norm:
                return s
        # 3. Substring match
        for s in station_list:
            if query_norm in s.get('stationCode', '').upper() or query_norm in s.get('stationName', '').upper():
                return s
            if s.get('stationName', '').upper() in query_norm:
                return s
        return None

    def search_seats(self, train_no, origin_input, destination_input, journey_date, requested_class="ALL"):
        """
        Complete end-to-end seat availability check.
        Returns detailed vacant berths categorized by journey coverage.
        """
        # 1. Get train schedule
        sched_res = self.get_train_schedule(train_no)
        if not sched_res.get('success'):
            return {
                'success': False,
                'message': f"Could not find schedule for Train {train_no}: {sched_res.get('message', 'Invalid train number')}"
            }

        station_list = sched_res.get('stationList', [])
        train_name = sched_res.get('trainName', '')
        if not station_list:
            return {'success': False, 'message': f"No route stations found for Train {train_no}."}

        # 2. Match Origin and Destination
        origin_stn = self.find_station_match(origin_input, station_list)
        if not origin_stn:
            valid_stns = ", ".join([f"{s['stationName']} ({s['stationCode']})" for s in station_list[:8]])
            return {
                'success': False,
                'message': f"Origin station '{origin_input}' is not on the route of Train {train_no}. Stations include: {valid_stns}..."
            }

        dest_stn = self.find_station_match(destination_input, station_list)
        if not dest_stn:
            valid_stns = ", ".join([f"{s['stationName']} ({s['stationCode']})" for s in station_list[:8]])
            return {
                'success': False,
                'message': f"Destination station '{destination_input}' is not on the route of Train {train_no}. Stations include: {valid_stns}..."
            }

        route_codes = [s['stationCode'] for s in station_list]
        station_name_map = {s['stationCode']: s['stationName'] for s in station_list}

        orig_idx = route_codes.index(origin_stn['stationCode'])
        dest_idx = route_codes.index(dest_stn['stationCode'])

        if orig_idx >= dest_idx:
            return {
                'success': False,
                'message': f"Origin {origin_stn['stationName']} appears after destination {dest_stn['stationName']} on this train's route."
            }

        source_station_code = station_list[0]['stationCode']
        logger.info(f"Checking Train {train_no} ({train_name}) from {origin_stn['stationCode']} to {dest_stn['stationCode']} on {journey_date}")

        # 3. Fetch train composition (start with origin station or source station)
        comp_res = self.get_train_composition(train_no, journey_date, origin_stn['stationCode'])
        if not comp_res.get('success'):
            return {
                'success': False,
                'chartPrepared': False,
                'message': comp_res.get('message', 'Failed to retrieve train composition from IRCTC.')
            }
        comp_data = comp_res.get('data', {})

        # If chart not prepared from origin, try source station
        if comp_data.get('error') == "Chart not prepared" and origin_stn['stationCode'] != source_station_code:
            logger.info("Origin chart not prepared, checking source station chart...")
            src_comp = self.get_train_composition(train_no, journey_date, source_station_code)
            if src_comp.get('success') and not src_comp.get('data', {}).get('error'):
                comp_data = src_comp['data']

        if comp_data.get('error'):
            chart_error = comp_data['error']
            if "not prepared" in chart_error.lower():
                return {
                    'success': True,
                    'chartPrepared': False,
                    'trainNo': train_no,
                    'trainName': train_name,
                    'origin': origin_stn,
                    'destination': dest_stn,
                    'journeyDate': journey_date,
                    'greenSeats': [],
                    'totalVacant': 0,
                    'message': f"Chart is not prepared yet for Train {train_no} ({train_name}) on {journey_date}. IRCTC charts are typically prepared 4 hours before departure."
                }
            return {
                'success': False,
                'message': f"IRCTC Error: {chart_error}"
            }

        # 4. Extract available classes
        cdd = comp_data.get('cdd') or []
        available_classes = sorted(list(set(c['classCode'] for c in cdd if c.get('classCode'))))
        train_actual_name = comp_data.get('trainName') or train_name

        classes_to_check = []
        if requested_class and requested_class.upper() != "ALL":
            req_cls = requested_class.upper().strip()
            if req_cls in available_classes:
                classes_to_check = [req_cls]
            else:
                classes_to_check = available_classes
        else:
            classes_to_check = available_classes

        # 5. Fetch vacant berths across requested classes in parallel
        all_vacant_berths = []
        remote = comp_data.get('remote') or origin_stn['stationCode']
        from_stn = comp_data.get('from') or source_station_code
        train_start_date = comp_data.get('trainStartDate') or journey_date

        batch_results = self.get_vacant_berths_batch(
            train_no, origin_stn['stationCode'], remote, from_stn, train_start_date, classes_to_check
        )
        for cls in classes_to_check:
            vb_list = batch_results.get(cls, [])
            for item in vb_list:
                item['classCode'] = cls
                item['className'] = CLASS_NAME_MAP.get(cls, cls)
                all_vacant_berths.append(item)

        # 6. Categorize vacant berths according to journey coverage
        categorized_seats = []
        full_journey_count = 0
        origin_partial_count = 0
        dest_partial_count = 0
        intermediate_count = 0

        for b in all_vacant_berths:
            b_from = b.get('from', '')
            b_to = b.get('to', '')
            if b_from not in route_codes or b_to not in route_codes:
                continue

            b_from_idx = route_codes.index(b_from)
            b_to_idx = route_codes.index(b_to)

            # Check if this berth segment is relevant to our journey [orig_idx, dest_idx]
            # It is relevant if it overlaps with [orig_idx, dest_idx]
            overlap_start = max(orig_idx, b_from_idx)
            overlap_end = min(dest_idx, b_to_idx)

            if overlap_start >= overlap_end:
                # No overlap with the user's travel segment
                continue

            berth_code = b.get('berthCode', '')
            berth_type_desc = BERTH_TYPE_MAP.get(berth_code, berth_code)

            seat_info = {
                'coach': b.get('coachName', 'N/A'),
                'berth': str(b.get('berthNumber', 'N/A')),
                'seat_number': str(b.get('berthNumber', 'N/A')),
                'berth_code': berth_code,
                'berth_type': berth_type_desc,
                'cabin_coupe': b.get('cabinCoupeNo') or 'N/A',
                'class_type': b.get('classCode', 'N/A'),
                'class_name': b.get('className', 'N/A'),
                'vacant_from': b_from,
                'vacant_from_name': station_name_map.get(b_from, b_from),
                'vacant_to': b_to,
                'vacant_to_name': station_name_map.get(b_to, b_to),
                'boarding_station': b_from,
                'class': 'green-seat'
            }

            if b_from_idx <= orig_idx and b_to_idx >= dest_idx:
                seat_info['coverage'] = 'full'
                seat_info['coverage_label'] = f"Direct Full Journey ({origin_stn['stationCode']} to {dest_stn['stationCode']})"
                seat_info['is_direct'] = True
                full_journey_count += 1
            elif b_from_idx <= orig_idx and b_to_idx > orig_idx and b_to_idx < dest_idx:
                seat_info['coverage'] = 'origin_partial'
                seat_info['coverage_label'] = f"Origin to {b_to} ({origin_stn['stationCode']} -> {b_to})"
                seat_info['is_direct'] = False
                origin_partial_count += 1
            elif b_from_idx > orig_idx and b_from_idx < dest_idx and b_to_idx >= dest_idx:
                seat_info['coverage'] = 'dest_partial'
                seat_info['coverage_label'] = f"{b_from} to Destination ({b_from} -> {dest_stn['stationCode']})"
                seat_info['is_direct'] = False
                dest_partial_count += 1
            else:
                seat_info['coverage'] = 'intermediate'
                seat_info['coverage_label'] = f"Segment: {b_from} -> {b_to}"
                seat_info['is_direct'] = False
                intermediate_count += 1

            seat_info['seat_id'] = f"{seat_info['class_type']}_{seat_info['coach']}_{seat_info['berth']}_{b_from}_{b_to}"
            seat_info['raw_text'] = f"Coach {seat_info['coach']} Berth {seat_info['berth']} ({berth_type_desc}) from {b_from} to {b_to}"
            categorized_seats.append(seat_info)

        # Sort so full journey seats appear first, then origin partial, dest partial, intermediate
        order_priority = {'full': 0, 'origin_partial': 1, 'dest_partial': 2, 'intermediate': 3}
        categorized_seats.sort(key=lambda x: (
            order_priority.get(x['coverage'], 4),
            x['class_type'],
            coach_sort_key(x['coach']),
            int(x['berth']) if str(x['berth']).isdigit() else 999
        ))

        return {
            'success': True,
            'chartPrepared': True,
            'trainNo': train_no,
            'trainName': train_actual_name,
            'origin': origin_stn,
            'destination': dest_stn,
            'journeyDate': journey_date,
            'availableClasses': available_classes,
            'totalVacant': len(categorized_seats),
            'fullJourneyCount': full_journey_count,
            'originPartialCount': origin_partial_count,
            'destPartialCount': dest_partial_count,
            'intermediateCount': intermediate_count,
            'greenSeats': categorized_seats,
            'stationList': station_list,
            'message': f"Found {len(categorized_seats)} vacant green seats on Train {train_no} ({train_actual_name})! (Full Journey: {full_journey_count}, Segments: {len(categorized_seats) - full_journey_count})"
        }

    def compute_split_journeys(self, train_no, origin_input, destination_input, journey_date, class_type="ALL", passengers=1, max_options=5):
        """
        Calculates split-journey itineraries (seat hopping) from Origin to Destination (or closest reachable).
        Prioritizes:
          1. 100% destination coverage
          2. Same Coach across legs (so passengers don't move luggage between coaches)
          3. Keeping all passengers together if passengers > 1
          4. Minimal splits (direct > 1-split > 2-split)
        """
        search_res = self.search_seats(train_no, origin_input, destination_input, journey_date, class_type)
        if not search_res.get('success') or not search_res.get('chartPrepared'):
            return {
                'success': search_res.get('success', False),
                'chartPrepared': search_res.get('chartPrepared', False),
                'message': search_res.get('message', 'Chart not prepared or train not found'),
                'trainNo': train_no,
                'trainName': search_res.get('trainName', ''),
                'origin': search_res.get('origin'),
                'destination': search_res.get('destination'),
                'journeyDate': journey_date,
                'passengers': passengers,
                'totalFound': 0,
                'splitOptions': [],
                'greenSeats': []
            }

        raw_seats = search_res.get('greenSeats', [])
        stations = search_res.get('stationList') or self.get_train_schedule(train_no).get('stationList', [])
        route_codes = [s['stationCode'] for s in stations]
        station_names = {s['stationCode']: s['stationName'] for s in stations}

        orig_stn = search_res['origin']['stationCode']
        dest_stn = search_res['destination']['stationCode']
        orig_idx = route_codes.index(orig_stn)
        dest_idx = route_codes.index(dest_stn)

        sub_route = route_codes[orig_idx : dest_idx + 1]
        m = len(sub_route) - 1  # total hops from origin to destination

        # Filter seats to sub_route intervals
        berths = []
        for s in raw_seats:
            f_code = s['vacant_from']
            t_code = s['vacant_to']
            if f_code not in route_codes or t_code not in route_codes:
                continue
            f_idx = route_codes.index(f_code)
            t_idx = route_codes.index(t_code)

            f_local = max(0, f_idx - orig_idx)
            t_local = min(m, t_idx - orig_idx)
            if f_local < t_local:
                berths.append({
                    'seat_id': s.get('seat_id') or f"{s['class_type']}_{s['coach']}_{s['berth']}_{f_code}_{t_code}",
                    'coach': s['coach'],
                    'berth': s['berth'],
                    'berth_type': s['berth_type'],
                    'class_type': s['class_type'],
                    'class_name': s['class_name'],
                    'from_code': f_code,
                    'to_code': t_code,
                    'f_local': f_local,
                    't_local': t_local,
                    'raw_text': s.get('raw_text', '')
                })

        candidate_options = []

        # Find maximum stretch options from start_idx to end_idx
        # start_idx = 0 is from boarding station; start_idx > 0 is closest after passing boarding!
        # end_idx = m is reaching destination; end_idx < m is closest before reaching destination!
        for start_idx in range(0, m):
            for end_idx in range(m, start_idx, -1):
                hops_covered = end_idx - start_idx
                cov_pct = round((hops_covered / m) * 100, 1)

                # Base score proportional to coverage of total journey
                base_score = int(cov_pct * 400)
                if start_idx == 0 and end_idx == m:
                    base_score += 25000  # 100% full journey bonus
                else:
                    # Penalize distance missed before start and after end
                    base_score -= (start_idx * 750) + ((m - end_idx) * 750)

                # --- 1. SINGLE CONTINUOUS SEAT (from start_idx to end_idx) ---
                direct_pool = [b for b in berths if b['f_local'] <= start_idx and b['t_local'] >= end_idx]
                direct_by_coach = {}
                for b in direct_pool:
                    direct_by_coach.setdefault(b['coach'], []).append(b)

                for coach in sorted(direct_by_coach.keys(), key=coach_sort_key):
                    b_list = direct_by_coach[coach]
                    if len(b_list) >= passengers:
                        chosen = b_list[:passengers]
                        candidate_options.append({
                            'type': 'single-leg',
                            'splits_count': 0,
                            'legs_count': 1,
                            'same_coach_overall': True,
                            'coach_summary': f"Coach {coach}",
                            'has_seat_switch': False,
                            'start_station': sub_route[start_idx],
                            'start_station_name': station_names.get(sub_route[start_idx], sub_route[start_idx]),
                            'end_station': sub_route[end_idx],
                            'end_station_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                            'start_offset_stops': start_idx,
                            'end_offset_stops': m - end_idx,
                            'hops_covered': hops_covered,
                            'total_journey_hops': m,
                            'coverage_pct': cov_pct,
                            'dest_reached': (end_idx == m),
                            'boarding_reached': (start_idx == 0),
                            'furthest_station': sub_route[end_idx],
                            'furthest_station_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                            'score': base_score + 10000 + (len(chosen) * 50),
                            'legs': [
                                {
                                    'leg_num': 1,
                                    'from_code': sub_route[start_idx],
                                    'from_name': station_names.get(sub_route[start_idx], sub_route[start_idx]),
                                    'to_code': sub_route[end_idx],
                                    'to_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                                    'coach': coach,
                                    'same_coach_next': True,
                                    'seats': chosen
                                }
                            ]
                        })

                # --- 2. 1-SPLIT OPTIONS (2 legs: [start_idx -> k] and [k -> end_idx]) ---
                for k in range(start_idx + 1, end_idx):
                    leg1_pool = [b for b in berths if b['f_local'] <= start_idx and b['t_local'] >= k]
                    leg2_pool = [b for b in berths if b['f_local'] <= k and b['t_local'] >= end_idx]
                    if len(leg1_pool) < passengers or len(leg2_pool) < passengers:
                        continue

                    coaches1 = set(b['coach'] for b in leg1_pool)
                    coaches2 = set(b['coach'] for b in leg2_pool)
                    common_coaches = coaches1.intersection(coaches2)

                    # A. Same Coach across both legs (HIGHEST PRIORITY FOR SPLIT!)
                    for coach in sorted(common_coaches, key=coach_sort_key):
                        c1 = [b for b in leg1_pool if b['coach'] == coach][:passengers]
                        c2 = [b for b in leg2_pool if b['coach'] == coach][:passengers]
                        if len(c1) == passengers and len(c2) == passengers:
                            diff_seats = [s['berth'] for s in c1] != [s['berth'] for s in c2]
                            candidate_options.append({
                                'type': '1-split',
                                'splits_count': 1,
                                'legs_count': 2,
                                'same_coach_overall': True,
                                'coach_summary': f"Coach {coach} (Seat change inside coach)",
                                'has_seat_switch': diff_seats,
                                'start_station': sub_route[start_idx],
                                'start_station_name': station_names.get(sub_route[start_idx], sub_route[start_idx]),
                                'end_station': sub_route[end_idx],
                                'end_station_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                                'switch_station': sub_route[k],
                                'switch_station_name': station_names.get(sub_route[k], sub_route[k]),
                                'start_offset_stops': start_idx,
                                'end_offset_stops': m - end_idx,
                                'hops_covered': hops_covered,
                                'total_journey_hops': m,
                                'coverage_pct': cov_pct,
                                'dest_reached': (end_idx == m),
                                'boarding_reached': (start_idx == 0),
                                'furthest_station': sub_route[end_idx],
                                'furthest_station_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                                'score': base_score + 8000 + (500 if diff_seats else 0),
                                'legs': [
                                    {
                                        'leg_num': 1,
                                        'from_code': sub_route[start_idx],
                                        'from_name': station_names.get(sub_route[start_idx], sub_route[start_idx]),
                                        'to_code': sub_route[k],
                                        'to_name': station_names.get(sub_route[k], sub_route[k]),
                                        'coach': coach,
                                        'same_coach_next': True,
                                        'seats': c1
                                    },
                                    {
                                        'leg_num': 2,
                                        'from_code': sub_route[k],
                                        'from_name': station_names.get(sub_route[k], sub_route[k]),
                                        'to_code': sub_route[end_idx],
                                        'to_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                                        'coach': coach,
                                        'same_coach_next': True,
                                        'seats': c2
                                    }
                                ]
                            })

                    # B. Coach Transfer across legs
                    for c1_code in sorted(coaches1, key=coach_sort_key):
                        for c2_code in sorted(coaches2, key=coach_sort_key):
                            if c1_code == c2_code:
                                continue
                            c1 = [b for b in leg1_pool if b['coach'] == c1_code][:passengers]
                            c2 = [b for b in leg2_pool if b['coach'] == c2_code][:passengers]
                            if len(c1) == passengers and len(c2) == passengers:
                                candidate_options.append({
                                    'type': '1-split',
                                    'splits_count': 1,
                                    'legs_count': 2,
                                    'same_coach_overall': False,
                                    'coach_summary': f"Coach {c1_code} ➔ Coach {c2_code}",
                                    'has_seat_switch': True,
                                    'start_station': sub_route[start_idx],
                                    'start_station_name': station_names.get(sub_route[start_idx], sub_route[start_idx]),
                                    'end_station': sub_route[end_idx],
                                    'end_station_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                                    'switch_station': sub_route[k],
                                    'switch_station_name': station_names.get(sub_route[k], sub_route[k]),
                                    'start_offset_stops': start_idx,
                                    'end_offset_stops': m - end_idx,
                                    'hops_covered': hops_covered,
                                    'total_journey_hops': m,
                                    'coverage_pct': cov_pct,
                                    'dest_reached': (end_idx == m),
                                    'boarding_reached': (start_idx == 0),
                                    'furthest_station': sub_route[end_idx],
                                    'furthest_station_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                                    'score': base_score + 2000,
                                    'legs': [
                                        {
                                            'leg_num': 1,
                                            'from_code': sub_route[start_idx],
                                            'from_name': station_names.get(sub_route[start_idx], sub_route[start_idx]),
                                            'to_code': sub_route[k],
                                            'to_name': station_names.get(sub_route[k], sub_route[k]),
                                            'coach': c1_code,
                                            'same_coach_next': False,
                                            'seats': c1
                                        },
                                        {
                                            'leg_num': 2,
                                            'from_code': sub_route[k],
                                            'from_name': station_names.get(sub_route[k], sub_route[k]),
                                            'to_code': sub_route[end_idx],
                                            'to_name': station_names.get(sub_route[end_idx], sub_route[end_idx]),
                                            'coach': c2_code,
                                            'same_coach_next': False,
                                            'seats': c2
                                        }
                                    ]
                                })

        # Sort all candidate options by score descending, then coverage % descending, then natural coach order
        def option_sort_key(opt):
            first_coach = opt['legs'][0]['coach'] if opt.get('legs') else ''
            c_key = coach_sort_key(first_coach)
            return (opt['score'], opt['coverage_pct'], -c_key[0], -c_key[2])

        candidate_options.sort(key=option_sort_key, reverse=True)

        # Deduplicate candidate options so user gets genuinely distinct itineraries
        unique_options = []
        seen_sigs = set()
        for opt in candidate_options:
            sig = (
                opt['start_station'], opt['end_station'],
                tuple(
                    (leg['from_code'], leg['to_code'], tuple(s['seat_id'] for s in leg['seats']))
                    for leg in opt['legs']
                )
            )
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                unique_options.append(opt)
            if len(unique_options) >= max_options:
                break

        same_coach_count = sum(1 for o in unique_options if o.get('same_coach_overall'))
        dest_reached_count = sum(1 for o in unique_options if o.get('dest_reached'))
        boarding_reached_count = sum(1 for o in unique_options if o.get('boarding_reached'))

        return {
            'success': True,
            'chartPrepared': True,
            'trainNo': train_no,
            'trainName': search_res.get('trainName'),
            'origin': search_res['origin'],
            'destination': search_res['destination'],
            'journeyDate': journey_date,
            'passengers': passengers,
            'requestedOptions': max_options,
            'totalFound': len(unique_options),
            'destReachedCount': dest_reached_count,
            'boardingReachedCount': boarding_reached_count,
            'sameCoachCount': same_coach_count,
            'splitOptions': unique_options,
            'greenSeats': raw_seats,
            'message': f"Found {len(unique_options)} optimal journey itineraries ({same_coach_count} in same coach, {dest_reached_count} reaching destination)."
        }

    def close(self):
        with self.driver_lock:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
