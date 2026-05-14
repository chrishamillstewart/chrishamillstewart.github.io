import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

CLIPS_FILE = os.path.join(os.path.dirname(__file__), '..', 'clips.json')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )
}

def fetch(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8', errors='replace')

def load_clips():
    if os.path.exists(CLIPS_FILE):
        with open(CLIPS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_clips(clips):
    with open(CLIPS_FILE, 'w') as f:
        json.dump(clips, f, indent=2, ensure_ascii=False)

def is_new(clips, outlet, url):
    existing_urls = {c['url'] for c in clips.get(outlet, [])}
    return url not in existing_urls

# WEF — author page scrape (may be blocked by Akamai from some IPs;
# works from GitHub Actions). Falls back silently on 403.
def scrape_wef():
    outlet = 'World Economic Forum'
    results = []
    AUTHOR_URL = 'https://www.weforum.org/stories/authors/chris-hamill-stewart/'
    try:
        html = fetch(AUTHOR_URL)
        # Articles appear as links matching /stories/YYYY/MM/slug/
        seen = set()
        for m in re.finditer(
            r'href="(https://www\.weforum\.org/stories/\d{4}/\d{2}/[^"]+)"[^>]*>([^<]{20,})',
            html
        ):
            url, title = m.group(1).rstrip('/') + '/', m.group(2).strip()
            if url in seen:
                continue
            seen.add(url)
            year_m = re.search(r'/stories/(\d{4})/', url)
            year = year_m.group(1) if year_m else str(datetime.now().year)
            results.append({'title': title, 'url': url, 'year': year})
            if len(results) >= 5:
                break
        print(f'WEF: found {len(results)} articles')
    except HTTPError as e:
        print(f'WEF: blocked ({e.code}) — will retry from GitHub Actions')
    except Exception as e:
        print(f'WEF scrape error: {e}')
    return outlet, results

# AGBI — author page, regex extraction of card data
def scrape_agbi():
    outlet = 'AGBI'
    results = []
    try:
        html = fetch('https://www.agbi.com/author/chrishamillstewart/')
        articles_html = re.findall(r'<article[^>]*>.*?</article>', html, re.DOTALL)
        for block in articles_html[:5]:
            href_m = re.search(r'class="card__thumbnail-link" href="([^"]+)"', block)
            title_m = re.search(r'class="card__title">\s*<a[^>]*>\s*([^<]+?)\s*</a>', block)
            date_m = re.search(r'<time[^>]*datetime="([^"]+)"', block)
            if not href_m or not title_m:
                continue
            url = href_m.group(1)
            title = title_m.group(1).strip()
            year = date_m.group(1)[:4] if date_m else str(datetime.now().year)
            results.append({'title': title, 'url': url, 'year': year})
        print(f'AGBI: found {len(results)} articles')
    except Exception as e:
        print(f'AGBI scrape error: {e}')
    return outlet, results

# Wired ME — author page; stories use relative /story/ hrefs with title in sibling <h2>
def scrape_wired_me():
    outlet = 'Wired Middle East'
    results = []
    try:
        html = fetch('https://www.wired.me/author/chris-hamill-stewart/')
        seen = set()
        for m in re.finditer(
            r'href="(/story/[^"]+)"[^>]*><h2[^>]*>([^<]{10,})</h2>',
            html
        ):
            slug, title = m.group(1), m.group(2).strip()
            url = 'https://www.wired.me' + slug
            if url in seen:
                continue
            seen.add(url)
            results.append({'title': title, 'url': url, 'year': str(datetime.now().year)})
            if len(results) >= 5:
                break
        print(f'Wired ME: found {len(results)} articles')
    except Exception as e:
        print(f'Wired ME scrape error: {e}')
    return outlet, results

def main():
    clips = load_clips()
    changed = False
    for scraper in [scrape_wef, scrape_agbi, scrape_wired_me]:
        outlet, articles = scraper()
        if outlet not in clips:
            clips[outlet] = []
        for article in articles:
            if is_new(clips, outlet, article['url']):
                clips[outlet].insert(0, article)
                print(f'  NEW: [{outlet}] {article["title"]}')
                changed = True
    if changed:
        save_clips(clips)
        print('clips.json updated.')
    else:
        print('No new articles found.')

if __name__ == '__main__':
    main()
