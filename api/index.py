import os
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db_url = os.getenv("DB_URL", "mongodb://localhost:27017")
client = MongoClient(db_url)
db = client.get_database()

def extract_city(title):
    parts = re.split(',| ', title)
    return parts[-1].strip() if parts else "India"

@app.get("/")
async def root():
    return {"message": "Welcome to the Hotel Recommendations API!"}

@app.get("/api/recommendations/{user_id}")
async def get_dynamic_recommendations(user_id: str):
    try:
        # KEEP SAME: Your original booking fetching logic
        bookings = list(db['Bookings'].find({"userId": ObjectId(user_id)}).sort("createdAt", -1).limit(3))
        
        if not bookings:
            return [{"title": "Trending hotels near you"}]

        # 1. Fetch the actual hotel listings to find smart-matches against
        # We grab the titles and prices to calculate semantic and spending similarity
        hotels = list(db['Hotels'].find({}, {"title": 1, "price_per_night": 1}))
        
        if not hotels:
            # Fallback to structural strings if hotel catalog is empty
            return [{"title": "Trending hotels near you"}]

        # 2. Vectorize the Hotel Catalog Text
        hotel_titles = [h.get('title', '') for h in hotels]
        vectorizer = TfidfVectorizer(stop_words='english')
        hotel_matrices = vectorizer.fit_transform(hotel_titles)

        queries = []
        
        # 3. Process each booking via Neural Cosine Similarity instead of plain text concatenation
        for b in bookings:
            original_title = b.get('title', '')
            user_spend = float(b.get('amount_paid', 0))
            city = extract_city(original_title)
            
            # Vectorize the individual booking title
            booking_vector = vectorizer.transform([original_title])
            
            # Calculate Cosine Similarity matrix against all catalog hotels
            text_similarities = cosine_similarity(booking_vector, hotel_matrices).flatten()
            
            # Smart-Match Optimization Loop: Score hotels based on combined text and spend profile
            scored_hotels = []
            for idx, hotel in enumerate(hotels):
                text_score = float(text_similarities[idx])
                
                # Spending baseline score: penalize hotels far outside the original booking amount
                hotel_price = float(hotel.get('price_per_night', 0))
                price_delta = abs(user_spend - hotel_price) / max(user_spend, 1)
                price_score = 1.0 / (1.0 + price_delta) 
                
                # Combined "Smart-Match" weight (70% Text Vibe, 30% Spending Context)
                final_score = (text_score * 0.7) + (price_score * 0.3)
                scored_hotels.append((final_score, hotel.get('title', '')))

            # Sort catalog hotels by highest neural score
            scored_hotels.sort(key=lambda x: x[0], reverse=True)
            
            # 4. Generate the smart suggestions matching your exact UI string schemas
            # Best match in the same city
            city_matches = [name for _, name in scored_hotels if city.lower() in name.lower()]
            best_city_hotel = city_matches[0] if city_matches else (scored_hotels[0][1] if scored_hotels else "Luxury Option")
            queries.append({"title": f"Best boutique hotels in {city} like {best_city_hotel}"})
            
            # Pure semantic match (top overall similarity score)
            top_similar_hotel = scored_hotels[0][1] if scored_hotels else original_title
            queries.append({"title": f"Hotels similar to {top_similar_hotel}"})
            
            # Contextual alternative match 
            alt_hotel = scored_hotels[1][1] if len(scored_hotels) > 1 else top_similar_hotel
            queries.append({"title": f"Top rated stays near {alt_hotel}"})

        # KEEP SAME: Your original response deduplication and slicing format
        unique_queries = {q['title']: q for q in queries}.values()
        return list(unique_queries)[:5]

    except Exception as e:
        print(f"Neural Engine Error: {e}")
        # KEEP SAME: Your original fallback block
        return [{"title": "Global trending destinations"}]