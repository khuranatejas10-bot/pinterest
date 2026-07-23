import os
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
    chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    
    driver = None
    try:
        driver_path = ChromeDriverManager().install()
        # If it resolves to the text notice file, find the real chromedriver binary
        if os.path.basename(driver_path) != 'chromedriver':
            parent_dir = os.path.dirname(driver_path)
            possible_path = os.path.join(parent_dir, 'chromedriver')
            if os.path.exists(possible_path):
                driver_path = possible_path
            else:
                for root, dirs, files in os.walk(parent_dir):
                    if 'chromedriver' in files:
                        driver_path = os.path.join(root, 'chromedriver')
                        break
        # Add executable permission
        try:
            import stat
            st = os.stat(driver_path)
            os.chmod(driver_path, st.st_mode | stat.S_IEXEC)
        except Exception as chmod_err:
            print(f"Error changing permissions for chromedriver: {chmod_err}")
            
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        search_query = urllib.parse.quote_plus(keyword)
        search_url = f"https://www.pinterest.com/search/pins/?q={search_query}"
        
        def run_scrape_attempt(scroll_pause):
            driver.get(search_url)
            time.sleep(3.0)
            pins_map = {}
            for scroll_num in range(12):
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
        
        with ThreadPoolExecutor(max_workers=10) as executor:
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
        
        downloaded_filenames = [os.path.basename(p) for p in downloaded_paths]
        yield json.dumps({
            'type': 'complete',
            'filename': pptx_filename,
            'num_images': num_images,
            'num_slides': num_slides,
            'images': downloaded_filenames
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
