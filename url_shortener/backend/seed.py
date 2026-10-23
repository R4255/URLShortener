import uuid
import string
import random
from app import app, db, URL, text

def generate_random_code(length=6):
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))

def seed_database(num_records=50000):
    with app.app_context():
        print(f"Starting seeding of {num_records} URLs...")
        try:
            db.session.execute(text("TRUNCATE TABLE url_access CASCADE;"))
            db.session.execute(text("TRUNCATE TABLE url CASCADE;"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error truncating tables: {str(e)}")
            
        urls = []
        codes = set()
        
        for i in range(num_records):
            while True:
                code = generate_random_code()
                if code not in codes:
                    codes.add(code)
                    break
            
            original_url = f"https://example.com/long-url-{i}-{uuid.uuid4()}"
            urls.append(URL(
                id=str(uuid.uuid4()),
                original_url=original_url,
                short_code=code,
                clicks=0
            ))
            
            if len(urls) >= 5000:
                db.session.bulk_save_objects(urls)
                db.session.commit()
                print(f"Inserted {i + 1} URLs...")
                urls = []
                
        if urls:
            db.session.bulk_save_objects(urls)
            db.session.commit()
            print(f"Inserted all {num_records} URLs.")

if __name__ == "__main__":
    seed_database()
