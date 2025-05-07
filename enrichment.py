import pandas as pd
from flask import current_app
from app.models.connection import Connection
from app.models.user_connection import UserConnection
from app.models.enrichment import Enrichment
from app.database import db
import time
import requests
import os
import google.generativeai as genai
from datetime import datetime




def _enrich_connections():
    """
    Pull every Connection that has never been enriched (latest_enrichment->'version' IS NULL),
    fetch Mixrank data, copy the interesting bits onto the record, enrich metadata with Exa and Gemini, 
    create an Enrichment row, and bump latest_enrichment.  Runs in a single transaction per connection so 
    failures never poison the rest of the batch.
    """
    # Get all connections that have never been enriched, connections that haven't been enriched will have an empty latest_enrichment
    connections = Connection.query.filter(
        ~Connection.latest_enrichment.has_key('version')   # noqa: E711
        | Connection.latest_enrichment.is_(None)
    ).all()
    print(f"Found {len(connections)} connections needing enrichment")

    if not connections:
        print("No connections need enrichment.")
        return

    for index, connection in enumerate(connections, start=1):
        try:
            print(f"\n=== Processing connection {index}/{len(connections)} ===")
            print(f"Connection ID: {connection.id}")
            print(f"Current state - Name: {connection.full_name}, Company: {connection.current_company}, Location: {connection.location}")

            # ------------------------------------------------------------------ #
            # 1)  Fetch newest version number for this connection
            # ------------------------------------------------------------------ #
            latest_version = (
                db.session.query(db.func.max(Enrichment.version))
                .filter(Enrichment.connection_id == connection.id)
                .scalar()
            ) or 0
            new_version = latest_version + 1
            print(f"Current version: {latest_version}, New version: {new_version}")

            connection.is_enriching = True
            db.session.commit()


            # ------------------------------------------------------------------ #
            # 2)  MIXRANK – basic person/company + LinkedIn scrape
            # ------------------------------------------------------------------ #
            print(f"\nFetching Mixrank data for URL: {connection.profile_url}")
            mixrank_data = process_basic_enrichment(connection.profile_url)

            if not mixrank_data:
                print("❌ Mixrank returned empty payload")
                continue

            print("✅ Received Mixrank data:")
            print(f"LinkedIn data present: {'linkedin' in mixrank_data}")
            print(f"Company data present: {'company' in mixrank_data}")

            # ------------------------------------------------------------------ #
            # 3)  Map Mixrank fields onto our Connection object
            # ------------------------------------------------------------------ #
            print("\nApplying Mixrank data to connection...")
            _apply_mixrank_to_connection(connection, mixrank_data)

            # ------------------------------------------------------------------ #
            # 4)  Build tags from Exa and Mixrank data
            # ------------------------------------------------------------------ #
            exa_data = process_exa(connection)
            tags = process_tags(exa_data, mixrank_data)
            #print that tags have been generated if the length of tags is greater than 0
            if len(tags) > 0:
                print("✅ Tags generated successfully")
            else:
                print("❌ No tags generated")

            # ------------------------------------------------------------------ #
            # 5)  Build the latest_enrichment blob (store only essential data)
            # ------------------------------------------------------------------ #
            print("\nUpdating latest_enrichment with summary...")
            connection.latest_enrichment = {
                "version": new_version,
                "source": "mixrank",
                "timestamp": datetime.utcnow().isoformat(),
                "enrichment_summary": {
                    "headline": connection.headline,
                    "current_company": connection.current_company,
                    "location": connection.location,
                    "skills_count": len(connection.skills) if connection.skills else 0,
                    "education_count": len(connection.education) if connection.education else 0,
                    "previous_companies_count": len(connection.previous_companies) if connection.previous_companies else 0
                }
            }



            # ------------------------------------------------------------------ #
            # 6)  Create an Enrichment history row
            # ------------------------------------------------------------------ #
            enrichment = Enrichment(
                connection_id=connection.id,
                version=new_version,
                tags=tags
            )
            db.session.add(enrichment)

            # ------------------------------------------------------------------ #
            # 7)  Persist everything
            # ------------------------------------------------------------------ #
            print("\nCommitting changes to database...")
            connection.is_enriching = False
            db.session.commit()
            print("✅ Changes committed successfully")

            if index % 5 == 0:
                print(f"\nProgress: {index}/{len(connections)} connections processed")
                time.sleep(2)  # gentle throttle to keep Mixrank happy

        except Exception as exc:
            print(f"\n❌ Error processing connection: {str(exc)}")
            db.session.rollback()

def _apply_mixrank_to_connection(conn: Connection, data: dict) -> None:
    """
    Map Mixrank data to Connection fields. Only update fields if they're empty or if we have new data.
    """
    if not data:
        print("❌ No data provided to _apply_mixrank_to_connection")
        return

    print("\n=== Applying Mixrank data to connection fields ===")
    
    # Basic profile info
    if data.get("headline"):
        print(f"Found headline: {data['headline']}")
        if not conn.headline:
            conn.headline = data["headline"]
            print("✅ Updated headline")
        else:
            print("⚠️ Headline already exists, skipping")
    
    if data.get("locality"):
        print(f"Found location: {data['locality']}")
        if not conn.location:
            conn.location = data["locality"]
            print("✅ Updated location")
        else:
            print("⚠️ Location already exists, skipping")
    
    # Profile image
    if data.get("picture_url_orig"):
        print(f"Found profile image URL: {data['picture_url_orig']}")
        if not conn.profile_image_url:
            conn.profile_image_url = data["picture_url_orig"]
            print("✅ Updated profile image URL")
        else:
            print("⚠️ Profile image URL already exists, skipping")
    
    # Skills
    if data.get("skills"):
        print(f"Found {len(data['skills'])} skills")
        if not conn.skills:
            conn.skills = data["skills"]
            print("✅ Updated skills")
        else:
            print("⚠️ Skills already exist, skipping")

    # Volunteering
    if data.get("volunteering"):
        print(f"Found {len(data['volunteering'])} volunteering entries")
        if not conn.volunteering:
            conn.volunteering = data["volunteering"]
            print("✅ Updated volunteering")
        else:
            print("⚠️ Volunteering already exists, skipping")

    # Publications
    if data.get("publications"):
        print(f"Found {len(data['publications'])} publications")
        if not conn.publications:
            conn.publications = data["publications"]
            print("✅ Updated publications")
        else:
            print("⚠️ Publications already exist, skipping")
            
    # Awards
    if data.get("awards"):
        print(f"Found {len(data['awards'])} awards")
        if not conn.awards:
            conn.awards = data["awards"]
            print("✅ Updated awards")
        else:
            print("⚠️ Awards already exist, skipping")
    
    
    # Education
    if data.get("education"):
        print(f"Found {len(data['education'])} education entries")
        if not conn.education:
            # Transform education data to match our schema
            education_data = []
            for edu in data["education"]:
                education_data.append({
                    "school_name": edu.get("school_name"),
                    "field_of_study": None,  # Not available in this API
                    "degree": edu.get("degree"),
                    "start_date": edu.get("start_date"),
                    "end_date": edu.get("end_date"),
                    "activities": edu.get("activities")
                })
            conn.education = education_data
            print("✅ Updated education")
        else:
            print("⚠️ Education already exists, skipping")
    
    # Work experience
    experience = data.get("experience", [])
    print(f"Found {len(experience)} positions")
    if experience:
        # Current position
        current_pos = next((p for p in experience if p.get("is_current")), experience[0])
        if current_pos.get("company"):
            print(f"Found current company: {current_pos['company']}")
            if not conn.current_company:
                conn.current_company = current_pos["company"]
                print("✅ Updated current company")
            else:
                print("⚠️ Current company already exists, skipping")
        
        # Previous companies
        if not conn.previous_companies:
            company_names = {p.get("company") for p in experience if p.get("company")}
            if conn.current_company in company_names:
                company_names.remove(conn.current_company)
            if company_names:
                conn.previous_companies = sorted(company_names)
                print(f"✅ Updated previous companies: {company_names}")
        else:
            print("⚠️ Previous companies already exist, skipping")
    
    # Certifications
    if data.get("certifications"):
        print(f"Found {len(data['certifications'])} certifications")
        if not conn.certifications:
            # Transform certifications data to match our schema
            cert_data = []
            for cert in data["certifications"]:
                cert_data.append({
                    "title": cert.get("title"),
                    "company_name": cert.get("company_name"),
                    "date": cert.get("date")
                })
            conn.certifications = cert_data
            print("✅ Updated certifications")
        else:
            print("⚠️ Certifications already exist, skipping")
    
    # Date of birth
    if data.get("dob"):
        print(f"Found date of birth: {data['dob']}")
        if not conn.date_of_birth:
            try:
                conn.date_of_birth = datetime.strptime(data["dob"], "%Y-%m-%d").date()
                print("✅ Updated date of birth")
            except (ValueError, TypeError) as e:
                print(f"❌ Error parsing date of birth: {str(e)}")
        else:
            print("⚠️ Date of birth already exists, skipping")
    
    # Company data
    if data.get("company_name") and not conn.current_company:
        print(f"Found company name: {data['company_name']}")
        conn.current_company = data["company_name"]
        print("✅ Updated current company from company data")
    
    # Industries (not directly available in this API)
    if not conn.industries:
        conn.industries = []  # Initialize empty list since we don't have industry data
        print("⚠️ No industry data available in this API")
    
    print("\n=== Final connection state ===")
    print(f"Headline: {conn.headline}")
    print(f"Current Company: {conn.current_company}")
    print(f"Location: {conn.location}")
    print(f"Skills count: {len(conn.skills) if conn.skills else 0}")
    print(f"Education count: {len(conn.education) if conn.education else 0}")
    print(f"Previous companies count: {len(conn.previous_companies) if conn.previous_companies else 0}")
    print(f"Profile image URL: {conn.profile_image_url}")
    print(f"Date of birth: {conn.date_of_birth}")
    print("=============================\n")

def process_basic_enrichment(url: str) -> dict:
    """
    Tiny wrapper around Mixrank's `/person/match` endpoint.
    Returns {} on error.  Raises nothing – keep calling code simple.
    """
    try:
        mixrank_api_key = os.getenv('MIXRANK_API_KEY', current_app.config.get('MIXRANK_API_KEY'))
        endpoint = f"https://api.mixrank.com/v2/json/{mixrank_api_key}/linkedin/profile"
        resp = requests.get(
            endpoint,
            params={
                "url": url,
                "strategy": "strict",
                "maxage": "1192000"
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json() or {}
    except (requests.RequestException, ValueError) as err:
        current_app.logger.error("Mixrank request failed: %s", str(err))
        return {}
    

def process_exa(connection):
    """
    Search Exa API for additional data about the connection.
    Returns search results or empty dict on error.
    """
    try:
        # Build search query
        search_query = connection.full_name
        search_query += f" {connection.profile_url}"
        
        if connection.education:
            search_query += f" {connection.education[0]['school_name']}"
        elif connection.current_company:
            search_query += f" {connection.current_company}"
        elif connection.headline:
            search_query += f" {connection.headline}"

        # Make request to Exa API
        exa_api_key = os.getenv('EXA_API_KEY', current_app.config.get('EXA_API_KEY'))
        response = requests.post(
            'https://api.exa.ai/search',
            json={
                'query': search_query,
                'numResults': 8,
                'type': 'keyword'
            },
            headers={
                'Authorization': f'Bearer {exa_api_key}',
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    except (requests.RequestException, ValueError) as err:
        current_app.logger.error("Exa API request failed: %s", str(err))
        return {}

def process_tags(exa_data, mixrank_data):

    # Feed Gemini the mixrank data and the exa data
    # Get the tags from Gemini
    # Initialize Gemini
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    model = genai.GenerativeModel('gemini-2.0-flash')

    # Construct prompt with available data
    prompt = f"""
    You are a metadata enrichment assistant. Based on the following search results and linkedin profile about a person, generate 50-100 relevant keywords/metadata terms that describe them.
    Focus on their professional background, skills, interests, and achievements. Make the tags short and concise. Optimize for searchability. Make the majority of the tags one or two words.


    Example output for a software engineer who is a product manager at Facebook:
    ["Facebook," "Meta", "FAANG", "MAANG","Software Engineering", "Product Manager", "Facebook", "Software Development", "Computer Science", "Programming", "Teamwork", "Leadership", "Problem Solving", "Decision Making", "Time Management", "Adaptability", "Teamwork", "Leadership Skills", "Communication Skills", "Leadership", "Team Management", "Project Management", "Problem Solving", "Decision Making", "Time Management", "Adaptability", "Teamwork"]

    Example output for someone who played Lacrosse in college and is now a software engineer at Google:
    ["FAANG", "MAANG", "Software Engineering", "Lacrosse", "Google", "Software Development", "Computer Science", "Programming", "Teamwork", "Leadership", "Problem Solving", "Decision Making", "Time Management", "Adaptability", "Teamwork", "Leadership Skills", "Communication Skills", "Leadership", "Team Management", "Project Management", "Problem Solving", "Decision Making", "Time Management", "Adaptability", "Teamwork"]

    Search results:

    LinkedIn Data:
    {mixrank_data}

    Exa Data:
    {exa_data}

    Return only relevant tags, separated by commas.
    """

    try:
        # Generate tags with Gemini
        response = model.generate_content(prompt)
        if response.candidates[0].content.parts[0].text:
            # Split response into individual tags and clean them
            raw_tags = [tag.strip().lower() for tag in response.candidates[0].content.parts[0].text.split(',')]
            # Remove any empty strings and deduplicate
            tags = set(tag for tag in raw_tags if tag)
            tags = [tag.strip('"') for tag in tags]
            assert isinstance(tags, list)
            assert all(isinstance(tag, str) for tag in tags)
            print(f"Generated {len(tags)} tags from Gemini")
        else:
            print("❌ No tags generated from Gemini")
            tags = []
    except Exception as e:
        print(f"❌ Error generating tags with Gemini: {str(e)}")
        tags = []

    return tags