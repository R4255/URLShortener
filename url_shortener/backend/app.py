from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.sql import func
import string
import random
import os
from datetime import datetime, timedelta  # Added timedelta import
import hashlib
import logging
import uuid
from prometheus_flask_exporter import PrometheusMetrics
import redis
import json
import threading
import time
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logger = app.logger
metrics=PrometheusMetrics(app)

CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/urlshortener"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 20,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,
}
db = SQLAlchemy(app)

redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0")
)


# Now the Models
class URL(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: (str(uuid.uuid4())))  # Changed to 36 for consistency
    original_url = db.Column(db.String(2048), nullable=False)
    short_code = db.Column(db.String(10), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    clicks = db.Column(db.Integer, default=0)
    user_id = db.Column(db.String(36), nullable=True)


class URLAccess(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    url_id = db.Column(db.String(36), db.ForeignKey("url.id"), nullable=False)
    accessed_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)  # Changed to nullable=True and more realistic size
    user_agent = db.Column(db.String(512), nullable=True)  # Added missing column
    referrer = db.Column(db.String(2048), nullable=True)  # Changed to nullable=True


# Base62 mapping character set: digits, lowercase, uppercase
BASE62_CHARS = string.digits + string.ascii_lowercase + string.ascii_uppercase

def encode_base62(num, length=6):
    """Encodes an integer into a uniform-length Base62 string."""
    arr = []
    for _ in range(length):
        num, rem = divmod(num, 62)
        arr.append(BASE62_CHARS[rem])
    arr.reverse()
    return "".join(arr)

def scramble_id(num):
    """Applies a bijective 32-bit XOR to scramble the counter sequence without collisions."""
    # We restrict to a 32-bit space (limit = 2^32 = 4,294,967,296)
    # Since 2^32 is less than 62^6 (56.8 billion), the scrambled number is guaranteed 
    # to yield a Base62 string of exactly 6 characters or less.
    # Because we do not use the modulo operator here, the XOR is 100% collision-free (bijection).
    mask = 0xFFFFFFFF
    # An arbitrary 32-bit key to scramble the bits
    key = 0x5DB37F9A
    return (num & mask) ^ key

# now the custom URL Generating Function
def generate_short_code():
    """Generates a unique, collision-free short code using a Redis atomic counter."""
    try:
        # Atomic increment from Redis
        counter = redis_client.incr("url_id_counter")
        # Scramble and encode
        scrambled = scramble_id(counter)
        return encode_base62(scrambled)
    except Exception as e:
        logger.error(f"Redis counter failed, falling back to random generator: {str(e)}")
        # Fallback to random alphanumeric string if Redis is unreachable
        chars = string.ascii_letters + string.digits
        return "".join(random.choice(chars) for _ in range(6))


# also we can use the hash based shortening
def hash_url(url, length=6):
    hash_object = hashlib.sha256(url.encode())
    hex_dig = hash_object.hexdigest()
    return hex_dig[:length]

    """
    url = "https://example.com"

# Create a SHA-256 hash object
hash_object = hashlib.sha256(url.encode())

# Get the hexadecimal representation of the hash
hex_dig = hash_object.hexdigest()

print("Hash Object:", hash_object)
print("Hexadecimal Hash:", hex_dig)
Hash Object: <sha256 HASH object @ 0x7f9c8b2d5d70>
Hexadecimal Hash: 563d7f5b5e6a6b8f8e9c3d4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c
"""


# Now Comes to the API Endpoints
@app.route("/health", methods=["GET"])
def health_check():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        logger.error(f"Health Check Failed: {str(e)}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500  # Removed extra {} from str(e)


# API to create a shortened URL
@app.route("/api/shorten", methods=["POST"])
def shorten_url():
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "URL is required"}), 400
    original_url = data["url"]
    # validate the URL Format
    if not original_url.startswith(("http://", "https://")):
        original_url = "https://" + original_url
    # now to check if the url is already present ?
    existing_url = URL.query.filter_by(original_url=original_url).first()
    if existing_url:
        return (
            jsonify(
                {
                    "original_url": existing_url.original_url,
                    "short_code": existing_url.short_code,
                    "short_url": f"{request.host_url}{existing_url.short_code}",
                    "created_at": existing_url.created_at.isoformat(),
                    "clicks": existing_url.clicks,
                }
            ),
            200,
        )
    # now we generate the short code
    custom_code = data.get("custom_code")
    if custom_code:
        if URL.query.filter_by(short_code=custom_code).first():
            return jsonify({"error": "Custom code already in Use"}), 400
        short_code = custom_code
    else:
        short_code = generate_short_code()

    # creating the new url
    new_url = URL(
        original_url=original_url, short_code=short_code, user_id=data.get("user_id")
    )
    try:
        db.session.add(new_url)
        db.session.commit()
        return (
            jsonify(
                {
                    "original_url": new_url.original_url,
                    "short_code": new_url.short_code,
                    "short_url": f"{request.host_url}{new_url.short_code}",
                    "created_at": new_url.created_at.isoformat(),
                    "clicks": new_url.clicks,
                }
            ),
            201,
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error Creating the Shortened URL: {str(e)}")
        return jsonify({"error": "Failed to create the Short URL"}), 500


# Now api to redirect to the original URL
@app.route("/<short_code>", methods=["GET"])  # Changed to GET for proper redirects
def redirect_to_url(short_code):
    try:
        # 1. Try checking Redis Cache first
        cached_data = redis_client.get(f"url:{short_code}")
        if cached_data:
            data = json.loads(cached_data)
            # Push access log to Redis queue to be processed asynchronously
            access_event = {
                "url_id": data["id"],
                "ip_address": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", ""),
                "referrer": request.headers.get("Referer", ""),
                "accessed_at": datetime.utcnow().isoformat()
            }
            redis_client.rpush("url_access_logs", json.dumps(access_event))
            return redirect(data["original_url"])
    except Exception as e:
        logger.error(f"Redis Cache Error: {str(e)}")

    # 2. Cache Miss: Query PostgreSQL
    url_entry = URL.query.filter_by(short_code=short_code).first()
    if not url_entry:
        return jsonify({"error": "URL not Found"}), 404

    # Cache the result in Redis for future reads
    try:
        redis_client.setex(
            f"url:{short_code}",
            3600,
            json.dumps({"id": url_entry.id, "original_url": url_entry.original_url})
        )
    except Exception as e:
        logger.error(f"Redis Cache Set Error: {str(e)}")

    # Record the access synchronously for cache miss
    access_log = URLAccess(
        url_id=url_entry.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
        referrer=request.headers.get("Referer", "")
    )
    url_entry.clicks += 1
    try:
        db.session.add(access_log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error Logging the URL Access: {str(e)}")
    return redirect(url_entry.original_url)


# Now the API to get the URL Statistics
@app.route("/api/stats/<short_code>", methods=["GET"])
def get_url_stats(short_code):
    url_entry = URL.query.filter_by(short_code=short_code).first()
    if not url_entry:
        return jsonify({"error": "URL not Found"}), 404
    access_logs = (
        URLAccess.query.filter_by(url_id=url_entry.id)
        .order_by(URLAccess.accessed_at.desc())
        .limit(100)
        .all()
    )
    # Get Daily Clicks for the past 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)  # Fixed datetime.timedelta
    daily_clicks = (
        db.session.query(
            func.date(URLAccess.accessed_at).label("date"),
            func.count(URLAccess.id).label("count"),
            # SELECT DATE(accessed_at) AS date, COUNT(id) AS count
            # FROM url_access;
        )
        .filter(
            URLAccess.url_id == url_entry.id, URLAccess.accessed_at >= thirty_days_ago
        )
        .group_by(func.date(URLAccess.accessed_at))
        .all()
    )

    daily_stats = [{"date": str(day.date), "clicks": day.count} for day in daily_clicks]
    access_history = [
        {
            "accessed_at": log.accessed_at.isoformat(),
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "referrer": log.referrer,
        }
        for log in access_logs
    ]
    return (
        jsonify(
            {
                "original_url": url_entry.original_url,
                "short_code": url_entry.short_code,
                "short_url": f"{request.host_url}{url_entry.short_code}",
                "created_at": url_entry.created_at.isoformat(),
                "total_clicks": url_entry.clicks,
                "daily_stats": daily_stats,
                "recent_access": access_history,
            }
        ),
        200,
    )

    
# Now we will list all the URLS, with pagination
@app.route("/api/urls", methods=["GET"])
def list_urls():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    user_id = request.args.get("user_id")
    query = URL.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    urls = query.order_by(URL.created_at.desc()).paginate(page=page, per_page=per_page)
    result = {
        "urls": [
            {
                "id": url.id,
                "original_url": url.original_url,
                "short_code": url.short_code,
                "short_url": f"{request.host_url}{url.short_code}",
                "created_at": url.created_at.isoformat(),
                "clicks": url.clicks,
            }
            for url in urls.items
        ],
        "total": urls.total,
        "pages": urls.pages,
        "current_page": urls.page,
    }
    return jsonify(result), 200
'''The paginate() method returns a Pagination object, not the raw query or the results directly.

Pagination Object
The Pagination object contains the following attributes:

items: A list of the actual results for the current page.
page: The current page number.
per_page: The number of items per page.
total: The total number of items across all pages.
pages: The total number of pages.
has_next: A boolean indicating if there is a next page.
has_prev: A boolean indicating if there is a previous page.
'''

# Now the API to delete a URL
@app.route("/api/urls/<short_code>", methods=["DELETE"])
def delete_url(short_code):
    url_entry = URL.query.filter_by(short_code=short_code).first()
    if not url_entry:
        return jsonify({"error": "URL not found"}), 404
    try:
        URLAccess.query.filter_by(url_id=url_entry.id).delete()
        db.session.delete(url_entry)
        db.session.commit()
        return jsonify({"message": "URL Deleted SuccessFully"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error Deleting the URL: {str(e)}")
        return jsonify({"Error": "Failed to Delete the URL"}), 500


def batch_process_logs():
    with app.app_context():
        while True:
            time.sleep(2)  # Process every 2 seconds
            try:
                # Fetch logs from Redis
                logs = []
                # Pop up to 1000 logs at a time
                for _ in range(1000):
                    log_data = redis_client.lpop("url_access_logs")
                    if not log_data:
                        break
                    logs.append(json.loads(log_data))

                if not logs:
                    continue

                # Group click counts to minimize DB writes
                click_increments = {}
                db_logs = []
                for log in logs:
                    url_id = log["url_id"]
                    click_increments[url_id] = click_increments.get(url_id, 0) + 1

                    db_logs.append(URLAccess(
                        url_id=url_id,
                        ip_address=log["ip_address"],
                        user_agent=log["user_agent"],
                        referrer=log["referrer"],
                        accessed_at=datetime.fromisoformat(log["accessed_at"])
                    ))

                # Batch update click counts in Postgres
                for url_id, count in click_increments.items():
                    URL.query.filter_by(id=url_id).update({URL.clicks: URL.clicks + count})

                # Batch insert access logs
                db.session.bulk_save_objects(db_logs)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error in batch logging background task: {str(e)}")

# Lock to ensure the background thread is started only once per worker process
_bg_thread_started = False
_bg_thread_lock = threading.Lock()

def start_background_workers():
    global _bg_thread_started
    with _bg_thread_lock:
        if not _bg_thread_started:
            try:
                with app.app_context():
                    db.create_all()
            except Exception as e:
                logger.error(f"Error creating tables during startup: {str(e)}")
            
            # Initialize Redis counter if it doesn't exist
            try:
                if not redis_client.exists("url_id_counter"):
                    # Start at 10,000,000 to ensure codes are at least 5 characters long
                    redis_client.set("url_id_counter", 10000000)
                    logger.info("Initialized Redis counter 'url_id_counter' to 10,000,000")
            except Exception as e:
                logger.error(f"Failed to initialize Redis counter: {str(e)}")

            # Start background thread
            t = threading.Thread(target=batch_process_logs, daemon=True)
            t.start()
            _bg_thread_started = True
            logger.info("Background click/access log flusher thread started.")

# Start background workers on import
start_background_workers()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=bool(os.getenv("DEBUG", True)),
    )
"""When a Python file is executed, the special variable __name__ is set to '__main__'.
If the file is imported as a module, __name__ is set to the name of the module instead.
"""