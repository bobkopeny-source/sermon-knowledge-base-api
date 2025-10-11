from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)
sermons = []
# Load sermons on startup
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

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'sermons_loaded': len(sermons), 'ai_enabled': client is not None})

@app.route('/api/sermons/upload', methods=['POST'])
def upload():
    global sermons
    sermons = request.get_json().get('sermons', [])
    return jsonify({'status': 'success', 'sermons_loaded': len(sermons)})

@app.route('/api/ask', methods=['POST'])
def ask():
    query = request.get_json().get('query', '')
    query_words = [w.lower() for w in query.split() if len(w) > 3]
    
    # Find relevant sermons with better scoring
    results = []
    for sermon in sermons:
        title = sermon['title'].lower()
        transcript = sermon.get('transcript', '').lower()
        
        # Score based on multiple factors
        score = 0
        
        # Title matches are most important (10x weight)
        for word in query_words:
            if word in title:
                score += 10
        
        # Exact phrase match in transcript (5x weight)
        query_lower = query.lower()
        if query_lower in transcript:
            score += 50
        
        # Individual word matches in transcript
        for word in query_words:
            count = transcript.count(word)
            # Diminishing returns - cap contribution per word at 5
            score += min(count, 5)
        
        if score > 0:
            results.append({'sermon': sermon, 'score': score})
    
    results.sort(key=lambda x: x['score'], reverse=True)
    top_sermons = results[:10]
    
    if not top_sermons:
        return jsonify({'status': 'success', 'answer': 'No relevant sermons found.', 'sources': []})
    
    if not client:
        # Fallback without AI
        answer = "Found relevant sermons but AI analysis not enabled. Add OPENAI_API_KEY to .env file.\n\n"
        for r in top_sermons:
            answer += f"• {r['sermon']['title']}\n"
        sources = [{'title': r['sermon']['title'], 'url': r['sermon']['url']} for r in top_sermons]
        return jsonify({'status': 'success', 'answer': answer, 'sources': sources})
    # Build context from top sermons
    context = f"Question: {query}\n\nRelevant sermon excerpts:\n\n"
    for r in top_sermons:
        context += f"Title: {r['sermon']['title']}\n"
        transcript = r['sermon'].get('transcript', '')[:8000]
        context += f"Content: {transcript}\n\n"
    
    # Ask ChatGPT to synthesize
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are summarizing a pastor's teachings. CRITICAL: Only use information from the sermon excerpts provided below - do not add any content not found in the transcripts. Be brief (under 150 words). Answer in first person starting with 'Based on my sermons...' then use bullet points (•) for 2-4 key points Quote or paraphrase specific statements from the transcripts. If the transcripts don't contain enough information, say so rather than making up content."},
                {"role": "user", "content": context}
            ],
            max_tokens=300,
            temperature=0.7
        )
        
        answer = response.choices[0].message.content
        sources = [{'title': r['sermon']['title'], 'url': r['sermon']['url']} for r in top_sermons]
        return jsonify({'status': 'success', 'answer': answer, 'sources': sources})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    print("🚀 Sermon Knowledge Base API - AI Enhanced")
    port = int(os.environ.get('PORT', 5001))
    print(f"Server: Port {port}")
    print(f"AI Status: {'Enabled' if client else 'Disabled (add OPENAI_API_KEY to .env)'}")
    app.run(host='0.0.0.0', port=port, debug=False)


