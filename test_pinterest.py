import requests
import json
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}
url = "https://www.pinterest.com/search/pins/?q=football"
r = requests.get(url, headers=HEADERS)
soup = BeautifulSoup(r.text, 'html.parser')
script = soup.find('script', id='__PWS_DATA__')
if script:
    data = json.loads(script.string)
    print("Found PWS_DATA, keys:", data.keys())
    # Try to find pin images
    # The JSON is complex, let's just dump a small portion or search for 'images'
    s = json.dumps(data)
    print("Contains 'pinimg.com':", 'pinimg.com' in s)
else:
    print("No PWS_DATA found.")
