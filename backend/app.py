import os
import json
import asyncio
import re
import httpx
import openai

from typing import List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from exa_py import Exa

# Load environment
load_dotenv()
EXA_API_KEY = os.getenv("EXA_API_KEY")
MIXRANK_API_KEY = os.getenv("MIXRANK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# FastAPI setup
origins = ["http://localhost:3000", "https://gentle-elegance-production.up.railway.app"]
app = FastAPI()
app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

# Pydantic models
class EnrichRequest(BaseModel):
    name: str
    social_url: Optional[str] = None

class FullProfileRequest(BaseModel):
    name: str
    summary: str
    url: str

class Candidate(BaseModel):
    summary: str
    url: str
    score: float

class ConfirmProfileRequest(BaseModel):
    name: str
    linkedin_url: str


# Clients
exa = Exa(EXA_API_KEY)
openai.api_key = OPENAI_API_KEY
client = openai.AsyncOpenAI()
secondary_client = openai.AsyncOpenAI()

# Helpers

def extract_location_info(data: dict):
    city = data.get('city', '')
    region = data.get('regionName', '')
    country = data.get('country', '')
    display = ", ".join(filter(None, [city, region, country]))
    return {'display': display or 'Unknown', 'city': city.lower()}

def get_ip_location(ip: str) -> dict:
    if ip.startswith(("127.", "192.168.", "10.", "172.")):
        return {"display": "Unknown", "city": ""}
    try:
        resp = httpx.get(f"http://ip-api.com/json/{ip}?fields=status,city,regionName,country", timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            return extract_location_info(data)
    except Exception:
        pass
    return {"display": "Unknown", "city": ""}

# Process all results
async def process_all_results(results: List[dict], query_name: str, ip_display: str) -> List[dict]:
    entries = []
    for idx, r in enumerate(results, start=1):
        title = r.title
        text = r.text
        url = r.url
        highlights = r.highlights
        entries.append(
            f"Result {idx}:\n"
            f"Title: {title}\n"
            f"URL: {url}\n"
            f"Highlights: {highlights}\n"
        )
    prompt = [
        {
            "role": "system",
            "content": (
                f"You are given a query name '{query_name}' and user location '{ip_display}'. "
                "Below are raw search result entries. Identify each unique person, then for each person return an object with 'summary' (which can be incredibly short), 'url', and 'score' (0-10). "
                "The summary should include whatever identifying information you can find about the person. (School, company, etc.)"
                "If there are multiple results that are probably the same person, return a single result with higher score."
                "Output strictly valid JSON: an array of {summary: string, url: string, score: number}."
            )
        },
        {"role": "system", "content": "\n".join(entries)}
    ]
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=prompt,
    )
    raw_content = resp.choices[0].message.content
    match = re.search(r"```(?:json)?(.*)```", raw_content, re.S)
    text = match.group(1).strip() if match else raw_content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON from LLM")
    
# API endpoints
@app.post('/api/enrich')
async def enrich(body: EnrichRequest, request: Request):
    # Extract and validate
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    # If user provided direct URL, skip search
    if body.social_url:
        return {'social_url': body.social_url}


    # Parallel IP + search
    client_ip = request.headers.get('X-Forwarded-For', request.client.host)
    location_info = get_ip_location(client_ip)
    query = f"{name}"
    exa_resp = exa.search(
        query, 
        type="keyword",
        category="linkedin profiles"
    )
    # LLM handles dedupe, summary, scoring
    raw_results = exa_resp.results
    candidates_data = await process_all_results(raw_results, name, location_info['display'])
    candidates: List[Candidate] = []
    for item in candidates_data:
        if len(candidates) >= 5:
            break
        summary = item.get('summary', '').strip()
        url = item.get('url', '').strip()
        score = float(item.get('score', 0))
        if summary and url:
            candidates.append(Candidate(summary=summary, url=url, score=score))

    if not candidates or len(candidates) > 5:
        return {
            'require_social_url': True,
            'message': "Please provide a direct social URL for disambiguation."
        }

    return {
        'candidates': [c.dict() for c in candidates],
        'location': location_info['display']
    }
    
# Once a user confirms a profile, we can enrich them directly
# Automated guessing :)
@app.post('/api/full_profile')
async def full_profile(request: FullProfileRequest):
    name, summary, url = request.name.strip(), request.summary.strip(), request.url.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not summary or not url:
        raise HTTPException(status_code=400, detail="Summary and URL are required")
    print(name, summary, url)
    system_prompt = f"""
    You are given:
    - The full name being searched for
    - The URL of the profile being searched for
    - The summary of the profile being searched for

    You are an expert at guessing the LinkedIn URL for a given person.

    Based on the given information and what you can find on the web, return the most likely LinkedIn URL for the person.
    ONLY return the LinkedIn URL, nothing else. An example output is "https://www.linkedin.com/in/johndoe". Do not include any other text. Do not include explanations. Only the URL.

    """
    user_prompt = f"""
    Name: {name}
    Summary: {summary}
    URL: {url}
    """
    try:
        resp = await client.chat.completions.create(
                model="gpt-4o-mini-search-preview",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        print("error", e)
        raise HTTPException(status_code=500, detail="Failed to generate LinkedIn URL, but it's not you–it's us. Please try again!")
    raw = resp.choices[0].message.content
    print("raw", raw)
    match_url = re.search(r"https?://[\w./%-]+", raw)
    social_url = match_url.group(0) if match_url else None

    if not social_url or "linkedin.com/in/" not in social_url.lower():
        print("Issue with social_url", social_url)
        raise HTTPException(status_code=500, detail="Failed to generate LinkedIn URL, but it's not you–it's us. Please try again!")

    # Enrich via Mixrank
    params = {"name": name, "social_url": social_url}
    async with httpx.AsyncClient() as clint:
        mix_resp = await clint.get(
            f"https://api.mixrank.com/v2/json/{MIXRANK_API_KEY}/person/match",
            params=params,
            timeout=20
        )
    if mix_resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Mixrank enrichment failed")
    return mix_resp.json()

# If a user gives us their linkedin url, we can enrich them directly
@app.post('/api/confirm_profile')
async def confirm_profile(request: ConfirmProfileRequest):
    name, linkedin_url = request.name.strip(), request.linkedin_url.strip()
    if not name or not linkedin_url:
        raise HTTPException(status_code=400, detail="Name and LinkedIn URL are required")

    # Enrich via Mixrank
    params = {"name": name, "social_url": linkedin_url}
    async with httpx.AsyncClient() as clint:
        mix_resp = await clint.get(
            f"https://api.mixrank.com/v2/json/{MIXRANK_API_KEY}/person/match",
            params=params,
            timeout=20
        )
    if mix_resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Mixrank enrichment failed")
    return mix_resp.json()
    
        
        

# run with uvicorn backend:app --reload