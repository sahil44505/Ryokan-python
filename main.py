import os
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Connection
client = MongoClient(os.getenv("DB_URL"))
db = client.get_database()

def extract_city(title):
    """Simple regex to find common city names or just take the last word 
    if the title follows 'Hotel Name, City' format."""
    parts = re.split(',| ', title)
    return parts[-1].strip() if parts else "India"

@app.get("/api/recommendations/{user_id}")
async def get_dynamic_recommendations(user_id: str):
    try:
        # 1. Fetch real booking history
        bookings = list(db['Bookings'].find({"userId": ObjectId(user_id)}).sort("createdAt", -1).limit(3))
        
        if not bookings:
            return [{"title": "Trending hotels near you"}]

        queries = []
        for b in bookings:
            original_title = b.get('title', '')
            city = extract_city(original_title)
            
            # Strategy 1: The "Same City, Different Vibe" Query
            queries.append({"title": f"Best boutique hotels in {city}"})
            
            # Strategy 2: The "Competitor" Query
            # This looks for the same style of hotel in the same area
            queries.append({"title": f"Hotels similar to {original_title}"})
            
            # Strategy 3: Local Area Discovery
            # Uses the title to find the specific neighborhood
            queries.append({"title": f"Top rated stays in {city} city center"})

        # Remove duplicates and limit to 5
        unique_queries = {q['title']: q for q in queries}.values()
        return list(unique_queries)[:5]

    except Exception as e:
        print(f"Error: {e}")
        return [{"title": "Global trending destinations"}]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)