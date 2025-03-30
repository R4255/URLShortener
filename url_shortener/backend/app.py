from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
import string
import random
import os
from datetime import datetime, timedelta  # Added timedelta import
import hashlib
import logging
from dotenv import load_dotenv
import uuid
import logger
from prometheus_flask_exporter import PrometheusMetrics

load_dotenv()
app = Flask(__name__)
metrics=PrometheusMetrics(app)

CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/urlshortener"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


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


# now the custom URL Generating Function
def generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    while True:
        short_code = "".join(random.choice(chars) for _ in range(length))
        if not URL.query.filter_by(short_code=short_code).first():
            return short_code


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
        db.session.execute("SELECT 1")
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
    url_entry = URL.query.filter_by(short_code=short_code).first()
    if not url_entry:
        return jsonify({"error": "URL not Found"}), 404
    # Record the access
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


# @app.before_first_request
# def initialize_database():
#     db.create_all()


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=bool(os.getenv("DEBUG", True)),
    )
"""When a Python file is executed, the special variable __name__ is set to '__main__'.
If the file is imported as a module, __name__ is set to the name of the module instead.
"""