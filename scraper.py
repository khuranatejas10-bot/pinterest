import os
# Force webdriver-manager and Selenium to use /tmp since Vercel filesystem is read-only
os.environ['WDM_CACHE_DIR'] = '/tmp/.wdm'
os.environ['WDM_LOCAL'] = '1'

import re
import time
import json
import urllib.parse

import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Referer': 'https://www.pinterest.com/'
}

def upload_to_vercel_blob(local_path, remote_path):
    token = os.environ.get('BLOB_READ_WRITE_TOKEN')
    if not token:
        # Fallback for local testing without Vercel Blob
        return f"/api/download_local/{remote_path}"
        
    url = f"https://blob.vercel-storage.com/{remote_path}"
    headers = {
        "authorization": f"Bearer {token}",
        "x-api-version": "7"
    }
    with open(local_path, "rb") as f:
        response = requests.put(url, headers=headers, data=f)
        
    if response.status_code == 200:
        return response.json()["url"]
    else:
        raise Exception(f"Failed to upload {remote_path} to Vercel Blob: {response.text}")

def find_keys_in_dict(d, keys_to_find):
    results = {}
    if isinstance(d, dict):
        for k, v in d.items():
            if k in keys_to_find:
                results[k] = v
            if isinstance(v, (dict, list)):
                res = find_keys_in_dict(v, keys_to_find)
                for rk, rv in res.items():
                    if rk not in results:
                        results[rk] = rv
    elif isinstance(d, list):
        for item in d:
            res = find_keys_in_dict(item, keys_to_find)
            for rk, rv in res.items():
                if rk not in results:
                    results[rk] = rv
    return results

def fetch_pin_engagement(pin_id):
    url = f"https://www.pinterest.com/pin/{pin_id}/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            script = soup.find('script', id='__PWS_DATA__')
            if script:
                data = json.loads(script.string)
                stats = find_keys_in_dict(data, ['repin_count', 'reaction_count', 'saves', 'comment_count'])
                saves = stats.get('saves', stats.get('repin_count', 0))
                reactions = stats.get('reaction_count', 0)
                saves_val = int(saves) if isinstance(saves, (int, float)) or (isinstance(saves, str) and saves.isdigit()) else 0
                reactions_val = int(reactions) if isinstance(reactions, (int, float)) or (isinstance(reactions, str) and reactions.isdigit()) else 0
                return pin_id, saves_val + reactions_val
    except Exception as e:
        print(f"Error fetching engagement for pin {pin_id}: {e}")
    return pin_id, 0

def download_image(url, output_dir, index):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                ext = 'jpg'
                if 'png' in content_type:
                    ext = 'png'
                elif 'webp' in content_type:
                    ext = 'webp'
                path = os.path.join(output_dir, f"img_{index}.{ext}")
                with open(path, 'wb') as f:
                    f.write(response.content)
                return path
    except Exception as e:
        print(f"Failed to download image {url}: {e}")
    return None

def upgrade_image_url(url):
    if 'pinimg.com' in url:
        return re.sub(r'/(?:236x|474x|564x|originals)/', '/736x/', url)
    return url

def scrape_and_generate_generator(keyword, session_dir, hard_timeout=90.0):
    """
    Generator version of the scraper that yields JSON strings for SSE.
    """
    start_time = time.time()
    
    def check_timeout():
        if time.time() - start_time > hard_timeout:
            raise TimeoutError("The scraping operation exceeded the 90-second timeout.")

    yield json.dumps({'type': 'status', 'message': f"Searching Pinterest for '{keyword}'…"})
    
    # Initialize Headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-tools")
    chrome_options.add_argument("--no-zygote")
    chrome_options.add_argument("--js-flags=--max-old-space-size=128")
    chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    
    # Disable image loading in the browser to drastically reduce RAM usage
    # The DOM will still contain the img src URLs which is all we need!
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.cookies": 2,
        "profile.managed_default_content_settings.javascript": 1,
        "profile.managed_default_content_settings.plugins": 2,
        "profile.managed_default_content_settings.popups": 2,
        "profile.managed_default_content_settings.geolocation": 2,
        "profile.managed_default_content_settings.media_stream": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = None
    try:
        driver = setup_driver()
        yield json.dumps({'type': 'status', 'message': "Chrome started successfully..."})
        
        search_query = urllib.parse.quote_plus(keyword)
        search_url = f"https://www.pinterest.com/search/pins/?q={search_query}"
        
        def run_scrape_attempt(scroll_pause):
            driver.get(search_url)
            time.sleep(3.0)
            pins_map = {}
            # Reduce scrolling to 5 to save massive amounts of memory
            for scroll_num in range(5):
                check_timeout()
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(scroll_pause)
                
                anchors = driver.find_elements(By.TAG_NAME, 'a')
                for a in anchors:
                    try:
                        href = a.get_attribute('href')
                        if href and '/pin/' in href:
                            match = re.search(r'/pin/(\d+)/?', href)
                            if match:
                                pin_id = match.group(1)
                                imgs = a.find_elements(By.TAG_NAME, 'img')
                                if imgs:
                                    img_src = imgs[0].get_attribute('src')
                                    if img_src and 'pinimg.com' in img_src:
                                        pins_map[pin_id] = img_src
                    except Exception:
                        continue
            return pins_map

        yield json.dumps({'type': 'status', 'message': "Scrolling and collecting top images…"})
        pins_map = run_scrape_attempt(scroll_pause=2.5)
        
        if not pins_map:
            yield json.dumps({'type': 'status', 'message': "No results found. Retrying once with a 4 second scroll pause…"})
            check_timeout()
            pins_map = run_scrape_attempt(scroll_pause=4.0)
            
        if not pins_map:
            raise ValueError("No results found for keyword.")
            
        driver.quit()
        driver = None
        check_timeout()
        
        yield json.dumps({'type': 'status', 'message': "Analyzing pin engagement and popularity…"})
        pin_ids = list(pins_map.keys())
        pin_engagements = {}
        candidate_pin_ids = pin_ids[:40] # Analyze top 40 candidate pins
        
        # Reduce max_workers to 2 to prevent memory spikes from parallel requests
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_pin = {executor.submit(fetch_pin_engagement, pid): pid for pid in candidate_pin_ids}
            for future in as_completed(future_to_pin):
                check_timeout()
                pid, score = future.result()
                pin_engagements[pid] = score
                
        sorted_pins = sorted(pin_engagements.items(), key=lambda x: x[1], reverse=True)
        
        yield json.dumps({'type': 'status', 'message': "Downloading images…"})
        downloaded_paths = []
        img_idx = 1
        os.makedirs(session_dir, exist_ok=True)
        
        for pin_id, score in sorted_pins:
            check_timeout()
            if img_idx > 10:
                break
            img_url = pins_map[pin_id]
            high_res_url = upgrade_image_url(img_url)
            local_path = download_image(high_res_url, session_dir, img_idx)
            if local_path:
                downloaded_paths.append(local_path)
                img_idx += 1
                
        if len(downloaded_paths) < 10:
            remaining_pins = [pid for pid in pin_ids if pid not in pin_engagements]
            for pid in remaining_pins:
                check_timeout()
                if len(downloaded_paths) >= 10:
                    break
                img_url = pins_map[pid]
                high_res_url = upgrade_image_url(img_url)
                local_path = download_image(high_res_url, session_dir, img_idx)
                if local_path:
                    downloaded_paths.append(local_path)
                    img_idx += 1
                    
        if not downloaded_paths:
            raise ValueError("Failed to download any images for the PowerPoint.")
            
        yield json.dumps({'type': 'status', 'message': "Generating your PowerPoint…"})
        check_timeout()
        
        from ppt_generator import create_pinterest_ppt
        
        safe_keyword = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in keyword)
        safe_keyword = safe_keyword.replace(' ', '_').lower()
        pptx_filename = f"{safe_keyword}_pinterest.pptx"
        pptx_filepath = os.path.join(session_dir, pptx_filename)
        
        num_images, num_slides = create_pinterest_ppt(keyword, downloaded_paths, pptx_filepath)
        
        yield json.dumps({'type': 'status', 'message': "Uploading presentation to Vercel Storage…"})
        check_timeout()
        
        session_id = os.path.basename(session_dir)
        
        blob_image_urls = []
        for local_path in downloaded_paths:
            check_timeout()
            filename = os.path.basename(local_path)
            blob_url = upload_to_vercel_blob(local_path, f"{session_id}/{filename}")
            blob_image_urls.append(blob_url)
            
        check_timeout()
        blob_pptx_url = upload_to_vercel_blob(pptx_filepath, f"{session_id}/{pptx_filename}")
        
        yield json.dumps({
            'type': 'complete',
            'filename': pptx_filename,
            'num_images': num_images,
            'num_slides': num_slides,
            'images': blob_image_urls,
            'download_url': blob_pptx_url,
            'image_urls': blob_image_urls
        })
        
    except TimeoutError as te:
        yield json.dumps({'type': 'error', 'error_type': 'timeout', 'message': str(te)})
    except Exception as e:
        yield json.dumps({'type': 'error', 'error_type': 'general', 'message': str(e)})
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
