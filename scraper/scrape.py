import html as htmllib
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

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
    with urlopen(req, timeout=20) as resp:
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

def _wef_title_from_wayback(url):
    """Fetch a single WEF article via Wayback Machine and extract its <title>."""
    wb_url = 'https://web.archive.org/web/2025/' + url
    req = Request(wb_url, headers=HEADERS)
    try:
        with urlopen(req, timeout=15) as r:
            chunk = r.read(8192).decode('utf-8', errors='replace')
        m = re.search(r'<title>([^<]+)</title>', chunk)
        if m:
            return htmllib.unescape(m.group(1).split('|')[0].strip())
    except Exception:
        pass
    return None

# WEF — tries the live author page first; falls back to the most recent
# Wayback Machine snapshot when Akamai blocks the request (common from
# residential IPs; the GitHub Actions runner gets through fine).
def scrape_wef():
    outlet = 'World Economic Forum'
    results = []
    AUTHOR_URL = 'https://www.weforum.org/stories/authors/chris-hamill-stewart/'
    WB_SNAPSHOT  = 'https://web.archive.org/web/20250425090344/' + AUTHOR_URL

    for attempt_url in [AUTHOR_URL, WB_SNAPSHOT]:
        try:
            page = fetch(attempt_url)
            seen = set()
            slugs = re.findall(r'/stories/(\d{4})/(\d{2})/([a-z0-9][a-z0-9-]+)/', page)
            for year, month, slug in slugs:
                url = f'https://www.weforum.org/stories/{year}/{month}/{slug}/'
                if url in seen:
                    continue
                # skip Spanish translations (es.weforum links)
                pos = page.find(f'/stories/{year}/{month}/{slug}/')
                if pos > 0 and 'es.weforum' in page[max(0, pos-60):pos]:
                    continue
                seen.add(url)
                title = _wef_title_from_wayback(url)
                if not title:
                    # derive from slug as fallback
                    title = slug.replace('-', ' ').capitalize()
                results.append({'title': title, 'url': url, 'year': year})
                if len(results) >= 5:
                    break
            if results:
                src = 'live' if attempt_url == AUTHOR_URL else 'Wayback Machine'
                print(f'WEF: found {len(results)} articles (via {src})')
                break
        except HTTPError as e:
            if attempt_url == AUTHOR_URL:
                print(f'WEF: live page blocked ({e.code}), trying Wayback Machine…')
            else:
                print(f'WEF: Wayback Machine also failed ({e.code})')
        except Exception as e:
            print(f'WEF scrape error ({attempt_url}): {e}')
            break

    return outlet, results

# AGBI — author page, regex extraction of card data (newest first on page)
def scrape_agbi():
    outlet = 'AGBI'
    results = []
    try:
        page = fetch('https://www.agbi.com/author/chrishamillstewart/')
        articles_html = re.findall(r'<article[^>]*>.*?</article>', page, re.DOTALL)
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

# Wired ME — /story/ hrefs with title in adjacent <h2> (newest first on page)
def scrape_wired_me():
    outlet = 'Wired Middle East'
    results = []
    try:
        page = fetch('https://www.wired.me/author/chris-hamill-stewart/')
        seen = set()
        for m in re.finditer(
            r'href="(/story/[^"]+)"[^>]*><h2[^>]*>([^<]{10,})</h2>',
            page
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
        # Scrapers return articles newest-first. Collect only genuinely new
        # ones (preserving that order), then prepend the batch so the list
        # stays newest-at-top without the one-by-one insert(0) reversal bug.
        new_articles = [a for a in articles if is_new(clips, outlet, a['url'])]
        if new_articles:
            for a in new_articles:
                print(f'  NEW: [{outlet}] {a["title"]}')
            combined = new_articles + clips[outlet]
            # Sort newest-first by year; stable sort preserves scraper order within a year
            clips[outlet] = sorted(combined, key=lambda x: x.get('year', '0'), reverse=True)
            changed = True
    if changed:
        save_clips(clips)
        print('clips.json updated.')
    else:
        print('No new articles found.')

if __name__ == '__main__':
    main()
