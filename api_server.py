if __name__ == '__main__':
    print("🚀 Sermon Knowledge Base API - AI Enhanced")
    port = int(os.environ.get('PORT', 5001))
    print(f"Server: Port {port}")
    print(f"AI Status: {'Enabled' if client else 'Disabled (add OPENAI_API_KEY to .env)'}")
    app.run(host='0.0.0.0', port=port, debug=False)
