import os
import sys
import time
import threading
import logging

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from irctc_api import IRCTCService

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Global stores for background searches
search_results = {}
search_in_progress = {}

# Initialize shared IRCTC service
irctc_service = IRCTCService()

@app.route('/')
def index():
    return render_template('irctc_frontend.html')

@app.route('/api/train-info/<train_no>', methods=['GET'])
def get_train_info(train_no):
    """Fetch train name, route stations, and available classes for frontend autocomplete/dropdown"""
    try:
        date_param = request.args.get('date')
        res = irctc_service.get_train_schedule(train_no)
        if res.get('success'):
            raw_stations = res.get('stationList', [])
            stations = [
                {
                    'code': s.get('stationCode'),
                    'name': s.get('stationName'),
                    'arrivalTime': s.get('arrivalTime'),
                    'departureTime': s.get('departureTime'),
                    'dayCount': s.get('dayCount')
                }
                for s in raw_stations
            ]
            
            source_stn = stations[0]['code'] if stations else None
            classes = irctc_service.get_train_classes(
                train_no,
                journey_date=date_param,
                boarding_stn=source_stn,
                station_list=raw_stations
            )
            
            return jsonify({
                'success': True,
                'trainNo': train_no,
                'trainName': res.get('trainName', ''),
                'stations': stations,
                'classes': classes
            })
        return jsonify({'success': False, 'message': res.get('message', 'Train not found')}), 200
    except Exception as e:
        logger.error(f"Error fetching train info: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/find-seats', methods=['POST'])
def find_seats():
    data = request.get_json() or {}
    train_no = data.get('trainNo')
    origin = data.get('origin')
    destination = data.get('destination')
    journey_date = data.get('journeyDate')
    class_type = data.get('classType', 'ALL')
    try:
        passengers = max(1, int(data.get('passengers', 1)))
    except (ValueError, TypeError):
        passengers = 1
        
    try:
        max_options = max(1, min(20, int(data.get('maxOptions', 5))))
    except (ValueError, TypeError):
        max_options = 5
    
    if not all([train_no, origin, destination, journey_date]):
        return jsonify({'success': False, 'message': 'Missing required fields (trainNo, origin, destination, journeyDate)'}), 400
    
    # Generate unique search ID
    search_id = f"{train_no}_{origin}_{destination}_{journey_date}_{int(time.time() * 1000)}"
    search_in_progress[search_id] = True
    
    # Run the seat search in a background thread
    thread = threading.Thread(
        target=run_seat_search,
        args=(search_id, train_no, origin, destination, journey_date, class_type, passengers, max_options)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': 'Search started',
        'searchId': search_id
    })

@app.route('/api/search-status/<search_id>', methods=['GET'])
def search_status(search_id):
    if search_id not in search_in_progress:
        return jsonify({'success': False, 'message': 'Invalid search ID'}), 404
    
    if search_in_progress[search_id]:
        return jsonify({'success': True, 'status': 'searching'})
    
    if search_id in search_results:
        return jsonify({
            'success': True, 
            'status': 'completed',
            'results': search_results[search_id]
        })
    
    return jsonify({'success': True, 'status': 'searching'})

@app.route('/api/live-poll', methods=['POST'])
def live_poll():
    """
    Live real-time monitoring endpoint.
    Performs a fast vacancy check and compares against previousSeatIds
    to detect seats allotted by TTE or new vacancies.
    """
    data = request.get_json() or {}
    train_no = data.get('trainNo')
    origin = data.get('origin')
    destination = data.get('destination')
    journey_date = data.get('journeyDate')
    class_type = data.get('classType', 'ALL')
    try:
        passengers = max(1, int(data.get('passengers', 1)))
    except (ValueError, TypeError):
        passengers = 1
        
    try:
        max_options = max(1, min(20, int(data.get('maxOptions', 5))))
    except (ValueError, TypeError):
        max_options = 5

    prev_seat_ids = set(data.get('previousSeatIds', []))

    if not all([train_no, origin, destination, journey_date]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    try:
        # Perform fresh split journey search
        res = irctc_service.compute_split_journeys(
            train_no, origin, destination, journey_date, class_type, passengers, max_options
        )

        curr_seats = res.get('greenSeats', [])
        curr_map = {s.get('seat_id'): s for s in curr_seats if s.get('seat_id')}
        curr_ids = set(curr_map.keys())

        # Determine delta
        allotted_ids = prev_seat_ids - curr_ids
        new_ids = curr_ids - prev_seat_ids

        allotted_seats = [
            {'seat_id': sid, 'label': sid.replace('_', ' ')}
            for sid in allotted_ids
        ]
        new_seats = [curr_map[sid] for sid in new_ids if sid in curr_map]

        has_changes = bool(prev_seat_ids and (allotted_seats or new_seats))

        return jsonify({
            'success': True,
            'timestamp': time.strftime('%H:%M:%S'),
            'hasChanges': has_changes,
            'delta': {
                'allottedCount': len(allotted_seats),
                'allottedSeats': allotted_seats,
                'newCount': len(new_seats),
                'newSeats': new_seats
            },
            'results': res
        })
    except Exception as e:
        logger.error(f"Error in live_poll: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

def run_seat_search(search_id, train_no, origin, destination, journey_date, class_type, passengers, max_options):
    """Execute search using IRCTCService and store results"""
    try:
        logger.info(f"Starting seat search [{search_id}] for Train {train_no}: {origin} -> {destination} on {journey_date} ({class_type}, {passengers} pax, max {max_options} opts)")
        res = irctc_service.compute_split_journeys(
            train_no, origin, destination, journey_date, class_type, passengers, max_options
        )
        search_results[search_id] = res
    except Exception as e:
        logger.error(f"Error in run_seat_search: {e}")
        search_results[search_id] = {
            'success': False,
            'message': f"Internal search error: {str(e)}",
            'greenSeats': [],
            'splitOptions': []
        }
    finally:
        search_in_progress[search_id] = False

@app.route('/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'online',
        'service': 'IRCTC Green Seat Finder API',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    })

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    import shutil
    if os.path.exists('index.html'):
        shutil.copy('index.html', os.path.join('templates', 'irctc_frontend.html'))
        shutil.copy('index.html', 'irctc_frontend.html')
    elif os.path.exists('irctc_frontend.html'):
        shutil.copy('irctc_frontend.html', os.path.join('templates', 'irctc_frontend.html'))
    
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("       [IRCTC] Green Seat Finder Web Server")
    print(f"       Running at: http://localhost:{port}")
    print("=" * 60)
    app.run(debug=False, host='0.0.0.0', port=port)
