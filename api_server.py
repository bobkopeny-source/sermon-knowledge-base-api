from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os
import re
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)
sermons = []

try:
    import json
    with open('sermons_with_transcripts.json', 'r') as f:
        sermons = json.load(f)
    print(f"✅ Loaded {len(sermons)} sermons on startup")
except FileNotFoundError:
    print("⚠️ sermons_with_transcripts.json not found")
except Exception as e:
    print(f"❌ Error loading sermons: {e}")

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')) if os.getenv('OPENAI_API_KEY') else None

def extract_relevant_timestamp(transcript, query_words):
    timestamps = [(m.group(0), m.start()) for m in re.finditer(r'\[(\d+):(\d+):(\d+)\]|\[(\d+):(\d+)\]', transcript)]
    if not timestamps:
        return None
    query_positions = []
    transcript_lower = transcript.lower()
    for word in query_words:
        pos = transcript_lower.find(word.lower())
        if pos != -1:
            query_positions.append(pos)
    if not query_positions:
        timestamp_str = timestamps[0][0]
    else:
        avg_query_pos = sum(query_positions) / len(query_positions)
        closest_timestamp = min(timestamps, key=lambda t: abs(t[1] - avg_query_pos))
        timestamp_str = closest_timestamp[0]
    match = re.match(r'\[(\d+):(\d+):(\d+)\]|\[(\d+):(\d+)\]', timestamp_str)
    if match:
        if match.group(1):
            return str(int(match.group(1))*3600 + int(match.group(2))*60 + int(match.group(3)))
        else:
            return str(int(match.group(4))*60 + int(match.group(5)))
    return None

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'sermons_loaded': len(sermons), 'ai_enabled': client is not None})

@app.route('/api/sermons/upload', methods=['POST'])
def upload():
    admin_password = os.getenv('ADMIN_PASSWORD', 'default-password')
    provided_password = request.headers.get('X-Admin-Password')
    if provided_password != admin_password:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    global sermons
    sermons = request.get_json().get('sermons', [])
    return jsonify({'status': 'success', 'sermons_loaded': len(sermons)})

@app.route('/api/ask', methods=['POST'])
def ask():
    query = request.get_json().get('query', '')
    query_words = [w.lower() for w in query.split() if len(w) > 3]
    results = []
    for sermon in sermons:
        title = sermon['title'].lower()
        transcript = sermon.get('transcript', '').lower()
        score = 0
        for word in query_words:
            if word in title:
                score += 10
        if query.lower() in transcript:
            score += 50
        for word in query_words:
            count = transcript.count(word)
            score += min(count, 5)
        if score > 0:
            results.append({'sermon': sermon, 'score': score})
    results.sort(key=lambda x: x['score'], reverse=True)
    top_sermons = results[:5]
    if not top_sermons:
        return jsonify({'status': 'success', 'answer': 'No relevant sermons found.', 'sources': []})
    if not client:
        answer = "Found relevant sermons but AI analysis not enabled.\n\n"
        for r in top_sermons:
            answer += f"- {r['sermon']['title']}\n"
        sources = []
        for r in top_sermons:
            url = r['sermon']['url']
            timestamp = extract_relevant_timestamp(r['sermon'].get('transcript', ''), query_words)
            if timestamp:
                url = f"{url}?t={timestamp}"
            sources.append({'title': r['sermon']['title'], 'url': url})
        return jsonify({'status': 'success', 'answer': answer, 'sources': sources})
    context = f"Question: {query}\n\nRelevant sermon excerpts:\n\n"
    for r in top_sermons:
        context += f"Title: {r['sermon']['title']}\n"
        context += f"Content: {r['sermon'].get('transcript', '')[:3000]}\n\n"
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are analyzing sermons from a pastor. Synthesize what the pastor teaches on the given topic based on the sermon excerpts. Answer in first person as if you are the pastor, starting with 'Based on my sermons...' Be specific and cite actual teachings."},
                {"role": "user", "content": context}
            ],
            max_tokens=300,
            temperature=0.7
        )
        answer = response.choices[0].message.content
        sources = []
        for r in top_sermons:
            url = r['sermon']['url']
            timestamp = extract_relevant_timestamp(r['sermon'].get('transcript', ''), query_words)
            if timestamp:
                url = f"{url}?t={timestamp}"
            sources.append({'title': r['sermon']['title'], 'url': url})
        return jsonify({'status': 'success', 'answer': answer, 'sources': sources})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    print("Sermon Knowledge Base API")
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
