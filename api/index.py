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
@app.get("/")
async def root():
    return {"message": "Welcome to the Hotel Recommendations API!"}

@app.get("/api/recommendations/{user_id}")
async def get_dynamic_recommendations(user_id: str):
    try:
        try:
            obj_user_id = ObjectId(user_id)
        except Exception:
            return [{"title": "Trending hotels near you"}]

        # Fetch bookings
        bookings = list(db['Bookings'].find({"userId": obj_user_id}).sort("createdAt", -1).limit(3))
        
        if not bookings:
            return [{"title": "Trending hotels near you"}]

        # Fetch all hotel listings
        hotels = list(db['Hotels'].find({}, {"title": 1, "price_per_night": 1}))
        
        if not hotels:
            return [{"title": "Trending hotels near you"}]

        # Clean and isolate hotel titles for the vectorizer
        hotel_titles = [str(h.get('title', '')).strip() for h in hotels if h.get('title')]
        
        # CRITICAL FIX: If your database has hotel entries but they lack titles, fall back safely
        if not hotel_titles:
            return [{"title": "Trending hotels in your area"}]

        # Initialize and fit the vectorizer
        vectorizer = TfidfVectorizer(stop_words='english')
        hotel_matrices = vectorizer.fit_transform(hotel_titles)

        queries = []
        
        for b in bookings:
            # Check if your Booking collection uses 'title' or 'hotelName'
            original_title = b.get('title') or b.get('hotelName') or b.get('hotel_title') or "Premium Hotel"
            original_title = str(original_title).strip()

            try:
                user_spend = float(b.get('amount_paid', 0))
            except (ValueError, TypeError):
                user_spend = 0.0

            city = extract_city(original_title)
            
            # Vectorize user booking title
            booking_vector = vectorizer.transform([original_title])
            
            # Compute similarity scores
            text_similarities = cosine_similarity(booking_vector, hotel_matrices).flatten()
            
            scored_hotels = []
            for idx, hotel_name in enumerate(hotel_titles):
                text_score = float(text_similarities[idx])
                
                try:
                    # Look up corresponding price from the original fetched list object safely
                    hotel_price = float(hotels[idx].get('price_per_night', 0))
                except (ValueError, TypeError, IndexError):
                    hotel_price = 0.0

                price_delta = abs(user_spend - hotel_price) / max(user_spend, 1.0)
                price_score = 1.0 / (1.0 + price_delta) 
                
                final_score = (text_score * 0.7) + (price_score * 0.3)
                scored_hotels.append((final_score, hotel_name))

            # Sort hotels by recommendation score highest to lowest
            scored_hotels.sort(key=lambda x: x[0], reverse=True)
            
            # Extract absolute top vectors
            top_similar_hotel = scored_hotels[0][1] if scored_hotels else original_title
            alt_hotel = scored_hotels[1][1] if len(scored_hotels) > 1 else top_similar_hotel
            
            # Look for city keyword match
            city_matches = [name for _, name in scored_hotels if city.lower() in name.lower()]
            
            # CRITICAL FIX: If no hotel title contains the city name, use the top neural match instead of leaving it blank!
            best_city_hotel = city_matches[0] if city_matches else top_similar_hotel
            
            # Append formatted output strings back to array loop
            queries.append({"title": f"Best boutique hotels in {city} like {best_city_hotel}"})
            queries.append({"title": f"Hotels similar to {top_similar_hotel}"})
            queries.append({"title": f"Top rated stays near {alt_hotel}"})

        unique_queries = {q['title']: q for q in queries}.values()
        return list(unique_queries)[:5]

    except Exception as e:
        print(f"Neural Engine Logic Error: {e}")
        return [{"title": "Global trending destinations"}]
