"""
bruteforce_seat_check.py

Command-line and module tool to check IRCTC vacant berths (green seats).
Powered by direct CRIS/IRCTC online charts engine via irctc_api.
"""

import sys
import os
import time
from datetime import datetime

# Ensure standard UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from irctc_api import IRCTCService, CLASS_NAME_MAP, BERTH_TYPE_MAP

def print_banner():
    print("=" * 65)
    print("        🚂 IRCTC VACANT BERTH (GREEN SEAT) FINDER")
    print("=" * 65)

def run_interactive_cli():
    print_banner()
    service = IRCTCService()
    
    try:
        train_no = input("Train number (e.g., 12301, 12345): ").strip()
        if not train_no:
            print("Train number is required.")
            return

        print(f"\n🔍 Fetching route and stations for Train {train_no}...")
        sched = service.get_train_schedule(train_no)
        if not sched.get('success'):
            print(f"❌ Error: {sched.get('message')}")
            return

        train_name = sched.get('trainName', '')
        stations = sched.get('stationList', [])
        print(f"✅ Found Train: {train_no} - {train_name}")
        print("Stations on route: " + ", ".join([f"{s['stationName']} ({s['stationCode']})" for s in stations[:10]]))
        if len(stations) > 10:
            print(f"... and {len(stations) - 10} more stations up to {stations[-1]['stationName']} ({stations[-1]['stationCode']})")

        origin = input(f"\nOrigin station code or name (e.g., {stations[0]['stationCode']}): ").strip()
        dest = input(f"Destination station code or name (e.g., {stations[-1]['stationCode']}): ").strip()
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        date_prompt = f"Journey date [YYYY-MM-DD] (default: today {today_str}): "
        journey_date = input(date_prompt).strip()
        if not journey_date:
            journey_date = today_str
        else:
            try:
                datetime.strptime(journey_date, "%Y-%m-%d")
            except ValueError:
                print("❌ Invalid date format. Please use YYYY-MM-DD.")
                return

        cls_choice = input("Class filter [ALL, SL, 3A, 2A, 1A, 2S, CC] (default: ALL): ").strip().upper()
        if not cls_choice:
            cls_choice = "ALL"

        pax_input = input("Number of passengers traveling together (default: 1): ").strip()
        passengers = int(pax_input) if pax_input.isdigit() and int(pax_input) > 0 else 1

        opts_input = input("Number of journey options to display (default: 5): ").strip()
        max_options = int(opts_input) if opts_input.isdigit() and int(opts_input) > 0 else 5

        print(f"\n🚀 Computing smart split options and vacant berths for {passengers} passenger(s)...")
        start_time = time.time()
        result = service.compute_split_journeys(train_no, origin, dest, journey_date, cls_choice, passengers, max_options)
        elapsed = round(time.time() - start_time, 2)

        if not result.get('success'):
            print(f"\n❌ {result.get('message')}")
            return

        if not result.get('chartPrepared'):
            print(f"\n⚠️ {result.get('message')}")
            return

        split_opts = result.get('splitOptions', [])
        seats = result.get('greenSeats', [])
        
        print("\n" + "=" * 65)
        print(f"✅ RESULTS: {train_no} - {result.get('trainName')}")
        print(f"   Route: {result['origin']['stationName']} ({result['origin']['stationCode']}) ➔ {result['destination']['stationName']} ({result['destination']['stationCode']})")
        print(f"   Journey Date: {journey_date} | Passengers: {passengers} | Search took: {elapsed}s")
        print(f"   Total Vacant Berths: {len(seats)} | Smart Itineraries: {len(split_opts)}")
        print("=" * 65)

        # 1. SMART SPLIT-JOURNEY ITINERARIES
        if split_opts:
            print(f"\n✨ SMART JOURNEY ITINERARIES ({len(split_opts)} options for {passengers} pax):")
            for idx, opt in enumerate(split_opts, 1):
                same_c_tag = "🏆 SAME COACH (Seat change only)" if opt['same_coach_overall'] else f"🔄 COACH CHANGE ({opt['coach_summary']})"
                dest_tag = "🟢 100% TO DESTINATION" if opt['dest_reached'] else f"🟡 COVERS {opt['coverage_pct']}% (To {opt['furthest_station']})"
                print(f"\n--- [Option {idx}] {dest_tag} | {same_c_tag} ---")
                for leg in opt['legs']:
                    pax_seats = ", ".join([f"P{p_idx+1}: {s['coach']}-{s['berth']} ({s['berth_type']}, {s['class_type']})" for p_idx, s in enumerate(leg['seats'])])
                    print(f"    Leg {leg['leg_num']}: {leg['from_code']} ➔ {leg['to_code']} | Coach {leg['coach']} | Seats: {pax_seats}")

        # 2. DIRECT FULL JOURNEY SEATS
        direct_seats = [s for s in seats if s.get('is_direct')]
        if direct_seats:
            print(f"\n🟢 DIRECT FULL-JOURNEY GREEN SEATS ({len(direct_seats)} available):")
            print(f"{'Class':<8} {'Coach':<8} {'Berth':<8} {'Type':<18} {'From ➔ To':<20}")
            print("-" * 65)
            for s in direct_seats[:15]:
                print(f"{s['class_type']:<8} {s['coach']:<8} {s['berth']:<8} {s['berth_type']:<18} {s['vacant_from']} ➔ {s['vacant_to']}")
            if len(direct_seats) > 15:
                print(f"... and {len(direct_seats) - 15} more direct seats.")

        print("\n" + "=" * 65)

    except KeyboardInterrupt:
        print("\nSearch cancelled by user.")
    finally:
        service.close()

def main():
    # If stdin is not a tty (e.g. piped or redirected)
    if not sys.stdin.isatty() or os.getenv("NON_INTERACTIVE", "0") == "1":
        # Handle non-interactive piped input: train_no\norigin\ndest\ndate\n
        lines = [line.strip() for line in sys.stdin.readlines() if line.strip()]
        if len(lines) >= 4:
            train_no, origin, dest, journey_date = lines[0], lines[1], lines[2], lines[3]
            cls = lines[4] if len(lines) > 4 else "ALL"
            service = IRCTCService()
            try:
                res = service.search_seats(train_no, origin, dest, journey_date, cls)
                if res.get('success') and res.get('greenSeats'):
                    print(f"GREEN_SEATS_FOUND: {len(res['greenSeats'])} seats")
                    for i, s in enumerate(res['greenSeats'], 1):
                        print(f"Green Seat {i}: Coach {s['coach']} - Berth {s['berth']} - Seat {s['berth']}")
                        print(f"  Class: {s['class_type']} | Available from: {s['vacant_from']} to {s['vacant_to']}")
                elif res.get('success') and not res.get('chartPrepared'):
                    print("CHART_NOT_PREPARED")
                    print(res.get('message'))
                else:
                    print("NO_DATA")
                    print(res.get('message', 'No seats found'))
            finally:
                service.close()
            return
    
    run_interactive_cli()

if __name__ == "__main__":
    main()
