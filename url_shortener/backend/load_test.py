import urllib.request
import time
import concurrent.futures
from app import app, db, URL, text, redis_client
import json

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        # Override this to prevent following redirects.
        # By raising an HTTPError, we abort the redirect chain and can handle it.
        raise urllib.request.HTTPError(req.full_url, code, msg, hdrs, fp)

# opener will now return the redirect response instead of following it
opener = urllib.request.build_opener(NoRedirectHandler())
opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]

def make_request(url):
    start = time.perf_counter()
    try:
        # urllib.request.urlopen uses the opener we built
        response = opener.open(url, timeout=5)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        return response.getcode(), elapsed
    except urllib.request.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000  # ms
        return e.code, elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000  # ms
        return -1, elapsed

def run_benchmark(urls, num_requests=1000, concurrency=10):
    latencies = []
    statuses = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for i in range(num_requests):
            url = urls[i % len(urls)]
            futures.append(executor.submit(make_request, url))
            
        start_time = time.perf_counter()
        for future in concurrent.futures.as_completed(futures):
            status, elapsed = future.result()
            latencies.append(elapsed)
            statuses[status] = statuses.get(status, 0) + 1
            
    total_time = time.perf_counter() - start_time
    throughput = num_requests / total_time
    
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p90 = latencies[int(len(latencies) * 0.90)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = sum(latencies) / len(latencies)
    
    return {
        "avg": avg,
        "p50": p50,
        "p90": p90,
        "p95": p95,
        "p99": p99,
        "throughput": throughput,
        "statuses": statuses
    }

def main():
    print("Waiting for API server to be warm...")
    time.sleep(3)
    
    with app.app_context():
        db_urls = URL.query.limit(300).all()
        short_codes = [u.short_code for u in db_urls]
        
    print(f"Loaded {len(short_codes)} short codes from the database.")
    
    base_url = "http://localhost:5000"
    
    # ----------------------------------------------------
    # Benchmark 1: Cache Hits (Hot Path)
    # ----------------------------------------------------
    print("\n--- Running Benchmark 1: Cache Hits (Redis Caching) ---")
    warmup_codes = short_codes[:10]
    warmup_urls = [f"{base_url}/{code}" for code in warmup_codes]
    for url in warmup_urls:
        make_request(url)
        
    for code in warmup_codes:
        if redis_client.exists(f"url:{code}") == 0:
            print(f"Warning: Code {code} was not cached!")
            
    print("Warmup complete. Redis cache verified.")
    
    print(f"Running 1000 requests with concurrency=10 on cached redirect path...")
    results_cached = run_benchmark(warmup_urls, num_requests=1000, concurrency=10)
    print(json.dumps(results_cached, indent=2))
    
    # ----------------------------------------------------
    # Benchmark 2: Cache Misses with B-Tree Index (Cold Path)
    # ----------------------------------------------------
    print("\n--- Running Benchmark 2: Cache Misses with B-Tree Index (PostgreSQL) ---")
    postgres_codes = short_codes[10:110]
    postgres_urls = [f"{base_url}/{code}" for code in postgres_codes]
    
    for code in postgres_codes:
        redis_client.delete(f"url:{code}")
        
    print(f"Running 500 requests with concurrency=10 on uncached (database) redirect path...")
    results_indexed = run_benchmark(postgres_urls, num_requests=500, concurrency=10)
    print(json.dumps(results_indexed, indent=2))
    
    # ----------------------------------------------------
    # Benchmark 3: Unindexed Cache Misses (Full Table Scan)
    # ----------------------------------------------------
    print("\n--- Running Benchmark 3: Unindexed Cache Misses ---")
    with app.app_context():
        print("Dropping unique B-Tree index constraint 'url_short_code_key'...")
        db.session.execute(text("ALTER TABLE url DROP CONSTRAINT url_short_code_key;"))
        db.session.commit()
        
    try:
        unindexed_codes = short_codes[110:210]
        unindexed_urls = [f"{base_url}/{code}" for code in unindexed_codes]
        
        for code in unindexed_codes:
            redis_client.delete(f"url:{code}")
            
        print(f"Running 500 requests with concurrency=10 on unindexed (table scan) redirect path...")
        results_unindexed = run_benchmark(unindexed_urls, num_requests=500, concurrency=10)
        print(json.dumps(results_unindexed, indent=2))
    finally:
        with app.app_context():
            print("Recreating unique B-Tree index constraint 'url_short_code_key'...")
            db.session.execute(text("ALTER TABLE url ADD CONSTRAINT url_short_code_key UNIQUE (short_code);"))
            db.session.commit()
            
    print("\n================ BENCHMARK RESULTS SUMMARY ================")
    print("| Metric | Cache Hits (Redis) | Cache Misses (B-Tree Index) | Cache Misses (Table Scan) |")
    print("| --- | --- | --- | --- |")
    print(f"| Avg Latency | {results_cached['avg']:.2f} ms | {results_indexed['avg']:.2f} ms | {results_unindexed['avg']:.2f} ms |")
    print(f"| p50 Latency | {results_cached['p50']:.2f} ms | {results_indexed['p50']:.2f} ms | {results_unindexed['p50']:.2f} ms |")
    print(f"| p90 Latency | {results_cached['p90']:.2f} ms | {results_indexed['p90']:.2f} ms | {results_unindexed['p90']:.2f} ms |")
    print(f"| p95 Latency | {results_cached['p95']:.2f} ms | {results_indexed['p95']:.2f} ms | {results_unindexed['p95']:.2f} ms |")
    print(f"| p99 Latency | {results_cached['p99']:.2f} ms | {results_indexed['p99']:.2f} ms | {results_unindexed['p99']:.2f} ms |")
    print(f"| Throughput | {results_cached['throughput']:.1f} RPS | {results_indexed['throughput']:.1f} RPS | {results_unindexed['throughput']:.1f} RPS |")
    print("===========================================================")

if __name__ == "__main__":
    main()
