from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
from exa_py import Exa
from dotenv import load_dotenv
from groq import Groq
import re

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": ["http://localhost:3000", "https://gentle-elegance-production.up.railway.app"]}})

# API keys
MIXRANK_API_KEY = os.getenv('MIXRANK_API_KEY')
GROQ_API_KEY    = os.getenv('GROQ_API_KEY')
EXA_API_KEY     = os.getenv('EXA_API_KEY')

# Clients
exa    = Exa(EXA_API_KEY)
client = Groq(api_key=GROQ_API_KEY)

def get_ip_location(ip_address):
    try:
        # Skip localhost/private IPs
        if ip_address in ('127.0.0.1', 'localhost') or ip_address.startswith(('192.168.', '10.', '172.')):
            return "Unknown Location"
            
        response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                # Format: City, Region, Country
                location_parts = []
                if data.get('city'):
                    location_parts.append(data['city'])
                if data.get('regionName'):
                    location_parts.append(data['regionName'])
                if data.get('country'):
                    location_parts.append(data['country'])
                return ', '.join(location_parts) if location_parts else "Unknown Location"
    except Exception as e:
        print(f"Error getting IP location: {e}")
    return "Unknown Location"

def summarize_candidate_with_groq(candidate_data, queried_name, ip_location):
    prompt = (
        f"""
You are given:
- A user profile result from an Exa query (see below),
- The full name being searched for: "{queried_name}",
- The approximate location based on the user's IP address: "{ip_location}".

YOUR SUMMARY WILL BE SHOWN TO THE USER, SO IT SHOULD NOT REFLECT THAT YOU ARE USING AN AI TO GENERATE IT. (e.g. don't say "Based on the information provided, we believe..." or "This profile seems to be a..." or anything like that. Just give a summary of the profile.)

First, summarize the user profile's background, title, location, etc. If the profile lacks useful data, return an empty summary. The summary should be a short paragraph (string) that is a few sentences long. IF THE DATA IS RANDOM/IRRELEVANT, RETURN AN EMPTY SUMMARY.

Then, based on how well the name and location of the profile match the queried full name and IP location, assign a score from 0 to 10. A 10 means a strong match in name and location; a 0 means clearly irrelevant.

Return everything in the following as a JSON object with keys "summary" and "score", which are the summary and score respectively. ONLY RETURN THE JSON OBJECT, NOTHING ELSE. WE WILL PARSE IT AS JSON. DO NOT RETURN ANYTHING ELSE.

Candidate profile data:
{candidate_data}

Now provide the summary and match score:
"""
    )

    try:
        resp = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": prompt}
            ],
            temperature=0.2,
            max_completion_tokens=128,
            top_p=1,
            stream=False
        ).choices[0].message.content.strip()

        return resp if resp else None
    except Exception as e:
        print(f"Error generating candidate label with Groq: {e}")
        return None
    
def get_candidate_linkedin_url(name, summary, url):
    # make a call to groq to guess the linkedin url
    # make a call to Exa to scrape for the linkedin url
    prompt = f"""
You are given:
- The full name being searched for: "{name}"
- The URL of the profile being searched for: "{url}"
- The summary of the profile being searched for: "{summary}"

You are an expert at guessing the LinkedIn URL for a given person.

Based on the summary, return the LinkedIn URL for the person. If you cannot guess the LinkedIn URL, return None.

ONLY RETURN THE LINKEDIN URL, NOTHING ELSE. RETURN IT AS A STRING. DO NOT RETURN ANYTHING ELSE.
"""
    try:
        resp = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "system", "content": prompt}],
        )
        print("GROQ RESP: ", resp)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating candidate LinkedIn URL with Groq: {e}")
        return None
    

    

@app.route('/api/full_profile', methods=['POST', 'OPTIONS'])
def full_profile():
    if request.method == 'OPTIONS':
        return jsonify({"message": "Preflight check"}), 200

    data = request.get_json() or {}
    name = data.get('name')
    summary = data.get('summary')
    url = data.get('url')
    if not name:
        return jsonify({"error": "Name is required"}), 400
    
    social_url = get_candidate_linkedin_url(name, summary, url)
    if not social_url:
        return jsonify({"error": "Failed to generate LinkedIn URL"}), 500
    
    params = {'name': name, 'social_url': social_url}
    resp = requests.get(
        f"https://api.mixrank.com/v2/json/{MIXRANK_API_KEY}/person/match",
        params=params,
        timeout=20
    )
    resp.raise_for_status()
    mixrank_data = resp.json()
    return jsonify({'all ur data: ': mixrank_data}), 200

@app.route('/api/enrich', methods=['POST', 'OPTIONS'])
def enrich():
    if request.method == 'OPTIONS':
        return jsonify({"message": "Preflight check"}), 200

    data = request.get_json() or {}
    name = data.get('name')
    social_url = data.get('social_url')
    if not name:
        return jsonify({"error": "Name is required"}), 400

    # Disambiguation phase
    if not social_url:
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        location = get_ip_location(ip_address)        
        query = f"{name} site:linkedin.com OR site:crunchbase.com OR site:angel.co OR site:twitter.com"
        try:
            exa_resp = exa.search_and_contents(
                query,
                num_results=10,
                include_domains=["linkedin.com", "crunchbase.com", "angel.co", "twitter.com"]
            )
            print("EXA RESP: ", exa_resp)
            candidates = []
            for result in exa_resp.results:
                url = result.url
                resp = summarize_candidate_with_groq(result, name, location)
                match = re.search(r"\{.*\}", resp, flags=re.S)
                if match:
                    clean_json = match.group(0)
                    data = json.loads(clean_json)
                    print("SUMMARY: ", data)
                    if data and data['summary'] != '':
                        score = data['score']
                        summary = data['summary']
                        candidates.append({
                            'summary': summary,
                            'url': url,
                            'score': score or 0
                        })

            # If no valid labels, ask for social_url
            if not candidates:
                return jsonify({
                    'require_social_url': True,
                    'message': "We couldn't confidently match your profile. Please provide a social media URL."
                }), 200

            # Take top 2 by score
            candidates = sorted(candidates, key=lambda c: c['score'], reverse=True)[:2]
            print("CANDIDATES: ", candidates)
            return jsonify({'candidates': candidates, 'location': location}), 200

        except Exception as e:
            print(f"Error during disambiguation: {e}")
            return jsonify({"error": "Internal Error"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000, host='0.0.0.0')
