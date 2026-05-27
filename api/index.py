import os
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

# Change: Set explicit docs configurations for Vercel routing
app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Change: Provide a local fallback string to prevent deployment crash if env loads late
db_url = os.getenv("DB_URL", "mongodb://localhost:27017")
client = MongoClient(db_url)
db = client.get_database()

def extract_city(title):
    parts = re.split(',| ', title)
    return parts[-1].strip() if parts else "India"

@app.get("/api/recommendations/{user_id}")
async def get_dynamic_recommendations(user_id: str):
    try:
        # Convert string ID to MongoDB ObjectId safely
        bookings = list(db['Bookings'].find({"userId": ObjectId(user_id)}).sort("createdAt", -1).limit(3))
        
        if not bookings:
            return [{"title": "Trending hotels near you"}]

        queries = []
        for b in bookings:
            original_title = b.get('title', '')
            city = extract_city(original_title)
            
            queries.append({"title": f"Best boutique hotels in {city}"})
            queries.append({"title": f"Hotels similar to {original_title}"})
            queries.append({"title": f"Top rated stays in {city} city center"})

        unique_queries = {q['title']: q for q in queries}.values()
        return list(unique_queries)[:5]

    except Exception as e:
        print(f"Error: {e}")
        return [{"title": "Global trending destinations"}]

# Note: You can keep the 'if __name__ == "__main__"' block; Vercel will ignore it,
# but it allows you to still test locally using 'python api/index.py'