import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError
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

def scrape_wef():
    outlet = 'World Economic Forum'
    results = []
    AUTHOR = 'Chris Hamill-Stewart'
    FEED_URL = 'https://www.weforum.org/feed/'
    try:
        xml = fetch(FEED_URL)
        ns = {'dc': 'http://purl.org/dc/elements/1.1/'}
        root = ET.fromstring(xml)
        channel = root.find('channel')
        for item in channel.findall('item'):
            creator = item.findtext('dc:creator', namespaces=ns) or ''
            if AUTHOR.lower() not in creator.lower():
                continue
            title = item.findtext('title', '').strip()
            url = item.findtext('link', '').strip()
            pub_date = item.findtext('pubDate', '').strip()
            year = pub_date.split()[-2] if pub_date else str(datetime.now().year)
            if title and url:
                results.append({'title': title, 'url': url, 'year': year})
        print(f'WEF: found {len(results)} articles')
    except Exception as e:
        print(f'WEF scrape error: {e}')
    return outlet, results

def scrape_computer_weekly():
    outlet = 'Computer Weekly'
    results = []
    AUTHOR_SLUG = 'chris-hamill-stewart'
    RSS_URL = f'https://www.computerweekly.com/author/{AUTHOR_SLUG}/rss'
    try:
        xml = fetch(RSS_URL)
        root = ET.fromstring(xml)
        channel = root.find('channel')
        for item in channel.findall('item'):
            title = item.findtext('title', '').strip()
            url = item.findtext('link', '').strip()
            pub_date = item.findtext('pubDate', '').strip()
            year = pub_date.split()[-2] if pub_date else str(datetime.now().year)
            if title and url:
                results.append({'title': title, 'url': url, 'year': year})
        print(f'Computer Weekly RSS: found {len(results)} articles')
    except Exception as e:
        print(f'Computer Weekly RSS error ({e}), trying author page scrape...')
        try:
            html = fetch(f'https://www.computerweekly.com/author/{AUTHOR_SLUG}')
            results = _parse_cw_author_page(html)
            print(f'Computer Weekly fallback: found {len(results)} articles')
        except Exception as e2:
            print(f'Computer Weekly scrape error: {e2}')
    return outlet, results

class _CWParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.articles = []
        self._in_article = False
        self._current_url = None
        self._current_title = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'article':
            self._in_article = True
        if self._in_article and tag == 'a' and 'href' in attrs:
            href = attrs['href']
            if '/news/' in href or '/feature/' in href or '/opinion/' in href:
                self._current_url = href if href.startswith('http') else f'https://www.computerweekly.com{href}'

    def handle_data(self, data):
        if self._in_article and self._current_url and not self._current_title:
            text = data.strip()
            if len(text) > 20:
                self._current_title = text

    def handle_endtag(self, tag):
        if tag == 'article' and self._in_article:
            if self._current_url and self._current_title:
                self.articles.append({'title': self._current_title, 'url': self._current_url, 'year': str(datetime.now().year)})
            self._in_article = False
            self._current_url = None
            self._current_title = None

def _parse_cw_author_page(html):
    parser = _CWParser()
    parser.feed(html)
    return parser.articles

def scrape_agbi():
    outlet = 'AGBI'
    results = []
    try:
        html = fetch('https://www.agbi.com/author/chrishamillstewart/')
        results = _parse_agbi_author_page(html)
        print(f'AGBI: found {len(results)} articles')
    except Exception as e:
        print(f'AGBI scrape error: {e}')
    return outlet, results

class _AGBIParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.articles = []
        self._in_article = False
        self._capture_link = False
        self._current_url = None
        self._current_title = None
        self._current_year = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'article':
            self._in_article = True
        if self._in_article:
            if tag == 'a' and 'href' in attrs:
                href = attrs['href']
                if 'agbi.com' in href and not self._current_url:
                    self._current_url = href
                    self._capture_link = True
            if tag == 'time' and 'datetime' in attrs:
                dt = attrs['datetime']
                self._current_year = dt[:4] if dt else str(datetime.now().year)

    def handle_data(self, data):
        if self._capture_link and not self._current_title:
            text = data.strip()
            if len(text) > 20:
                self._current_title = text

    def handle_endtag(self, tag):
        if tag == 'a':
            self._capture_link = False
        if tag == 'article' and self._in_article:
            if self._current_url and self._current_title:
                self.articles.append({'title': self._current_title, 'url': self._current_url, 'year': self._current_year or str(datetime.now().year)})
            self._in_article = False
            self._current_url = None
            self._current_title = None
            self._current_year = None
            self._capture_link = False

def _parse_agbi_author_page(html):
    parser = _AGBIParser()
    parser.feed(html)
    return parser.articles

def scrape_wired_me():
    outlet = 'Wired Middle East'
    results = []
    try:
        html = fetch('https://www.wired.me/author/chris-hamill-stewart/')
        results = _parse_wired_me_author_page(html)
        print(f'Wired ME: found {len(results)} articles')
    except Exception as e:
        print(f'Wired ME scrape error: {e}')
    return outlet, results

class _WiredMEParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.articles = []
        self._seen = set()
        self._pending_url = None
        self._pending_title = None
        self._capture = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'href' in attrs:
            href = attrs['href']
            if ('wired.me' in href or href.startswith('/')) and '/author/' not in href and '/tag/' not in href:
                full = href if href.startswith('http') else f'https://www.wired.me{href}'
                if full not in self._seen and full != 'https://www.wired.me/':
                    self._pending_url = full
                    self._capture = True

    def handle_data(self, data):
        if self._capture and self._pending_url:
            text = data.strip()
            if len(text) > 25 and not self._pending_title:
                self._pending_title = text

    def handle_endtag(self, tag):
        if tag == 'a' and self._pending_url and self._pending_title:
            if self._pending_url not in self._seen:
                self._seen.add(self._pending_url)
                self.articles.append({'title': self._pending_title, 'url': self._pending_url, 'year': str(datetime.now().year)})
            self._pending_url = None
            self._pending_title = None
            self._capture = False

def _parse_wired_me_author_page(html):
    parser = _WiredMEParser()
    parser.feed(html)
    return parser.articles

def main():
    clips = load_clips()
    changed = False
    for scraper in [scrape_wef, scrape_computer_weekly, scrape_agbi, scrape_wired_me]:
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
