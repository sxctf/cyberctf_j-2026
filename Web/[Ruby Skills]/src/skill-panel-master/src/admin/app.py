import uuid, json, requests, subprocess
from datetime import datetime
from flask import Flask, request, render_template, jsonify, Response, stream_with_context, render_template_string
from logging_config import logger_admin


app = Flask(__name__)

chat_host = "chat-service"
chat_port = 5000
url = f"http://{chat_host}:{chat_port}"

# API endpoints
@app.route('/admin/api/skills')
def api_skills():
    """API endpoint for dashboard — returns stats, chart data, and recent skills."""
    try:
        r = requests.get(f"{url}/skill-stats-info", timeout=10)
        r.raise_for_status()
        data = r.json()

        stats = {
            'total': int(data.get('total', 0)),
            'approved': int((data.get('breakdown') or {}).get('success', 0)),
            'rejected': int((data.get('breakdown') or {}).get('rejected', 0)),
        }

        raw = data.get('skills', [])
        timestamps = []
        for s in raw:
            ts = s.get('registered_at')
            if ts is not None:
                timestamps.append(float(ts))

        # Last 10 skills with human-readable time
        recent = []
        for s in raw[:10]:
            ts = s.get('registered_at')
            if ts:
                dt = datetime.fromtimestamp(ts)
                human_time = dt.strftime("%d.%m.%Y %H:%M")
            else:
                human_time = "—"

            status_badge = {
                'success': 'success',
                'rejected': 'rejected',
                'pending': 'pending',
            }.get((s.get('status') or '').lower(), 'pending')

            recent.append({
                'name': (s.get('name') or 'Unnamed').strip(),
                'status': status_badge,
                'status_text': (s.get('status') or 'pending').capitalize(),
                'registered_at': human_time,
            })

        return jsonify({
            'stats': stats,
            'timestamps': timestamps,
            'recent': recent,
        })
    except Exception as e:
        app.logger.warning(f"api_skills failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin')
def chat():
    # приветствие по времени суток
    hour = datetime.now().hour
    if 5 <= hour < 12:
        greeting = "Good morning,"
    elif 12 <= hour < 18:
        greeting = "Good afternoon,"
    else:
        greeting = "Good evening,"

    now = datetime.now().strftime("%I:%M %p").lstrip("0")

    stats = {'total': 0, 'approved': 0, 'rejected': 0}
    try:
        r = requests.get(f"{url}/skill-stats-info", timeout=10)
        r.raise_for_status()
        data = r.json()
        stats['total'] = int(data.get('total', 0))
        breakdown = data.get('breakdown') or {}
        stats['approved'] = int(breakdown.get('success', 0))
        stats['rejected'] = int(breakdown.get('rejected', 0))
    except Exception:
        pass

    # Collect timestamps for chart
    timestamps = []
    try:
        r = requests.get(f"{url}/skill-stats-info", timeout=10)
        r.raise_for_status()
        data = r.json()
        for s in data.get('skills', []):
            ts = s.get('registered_at')
            if ts is not None:
                timestamps.append(float(ts))
    except Exception:
        pass

    return render_template(
        'index.html',
        stats=stats,
        timestamps=timestamps,
        greeting=greeting,
        username="Ruby",
        current_time=now,
    )


@app.route('/admin/skills')
def skills():
    """Page showing recent skills list and activity chart."""
    try:
        r = requests.get(f"{url}/skill-stats-info", timeout=10)
        r.raise_for_status()
        data = r.json()
        raw = data.get('skills', [])
    except Exception:
        raw = []

    timestamps = []
    recent = []
    for s in raw:
        ts = s.get('registered_at')
        if ts is not None:
            timestamps.append(float(ts))

    for s in raw[:10]:
        ts = s.get('registered_at')
        if ts:
            dt = datetime.fromtimestamp(ts)
            human_time = dt.strftime("%d.%m.%Y %H:%M")
        else:
            human_time = "—"

        status_badge = {
            'success': 'success',
            'rejected': 'rejected',
            'pending': 'pending',
        }.get((s.get('status') or '').lower(), 'pending')

        recent.append({
            'name': (s.get('name') or 'Unnamed').strip(),
            'status': status_badge,
            'status_text': (s.get('status') or 'pending').capitalize(),
            'registered_at': human_time,
        })

    return render_template('skills.html', recent=recent, timestamps=timestamps)


#Healthcheck
@app.route('/admin/healthcheck', methods=['POST'])
def ping():
    """Check connectivity to a host — used for service health monitoring."""
    data = request.get_json(silent=True)
    if not data or not data.get('host'):
        logger_admin.warning(f"Healthcheck missing host", extra={'detail': f"remote_addr={request.remote_addr}"})
        return "Specify a host in JSON body", 400

    host = data['host']

    try:
        result = subprocess.run(
            f'ping -c 1 -W 3 {host}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        logger_admin.info(f"Healthcheck ping sent", extra={'detail': f"host={host} remote_addr={request.remote_addr}"})
        return result.stdout or result.stderr, 200
    except subprocess.TimeoutExpired:
        logger_admin.warning(f"Healthcheck timeout", extra={'detail': f"host={host}"})
        return "Request timed out", 504
    except Exception as e:
        logger_admin.error(f"Healthcheck error", extra={'detail': f"host={host} error={e}"})
        return f"Error: {e}", 500
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
