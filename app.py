import os
import uuid
import json
from flask import Flask, render_template, request, Response, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
# Use /tmp for Vercel Serverless environment
app.config['OUTPUT_DIR'] = os.path.join('/tmp', 'output')

# Ensure output directory exists
os.makedirs(app.config['OUTPUT_DIR'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/pinterest/scrape')
def scrape():
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({'error': 'Keyword is required'}), 400

    from scraper import scrape_and_generate_generator
    
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(app.config['OUTPUT_DIR'], session_id)
    
    def event_stream():
        try:
            # We call the generator
            for event in scrape_and_generate_generator(keyword, session_dir):
                # Format event for Server-Sent Events (SSE)
                parsed = json.loads(event)
                # the scraper now directly yields Vercel Blob URLs in 'download_url' and 'image_urls' for the 'complete' event
                yield f"data: {event}\n\n"
        except Exception as e:
            err_event = json.dumps({'type': 'error', 'error_type': 'general', 'message': str(e)})
            yield f"data: {err_event}\n\n"

    return Response(event_stream(), content_type='text/event-stream')

if __name__ == '__main__':
    # Run server locally on 5002
    app.run(host='0.0.0.0', port=5002, debug=True)
