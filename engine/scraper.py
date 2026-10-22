import asyncio
import logging
from typing import Optional, List, Tuple
from urllib.parse import urlparse
import httpx
import trafilatura
from bs4 import BeautifulSoup

from engine.models import ScrapedDocument

logger = logging.getLogger(__name__)

# Trusted domain lists for credibility auditing
ACADEMIC_GOV_TLDS = ('.edu', '.gov', '.ac.uk', '.gov.uk', '.mil')

HIGH_AUTHORITY_DOMAINS = frozenset({
    'apnews.com', 'arxiv.org', 'bbc.com', 'bloomberg.com', 'economist.com',
    'ft.com', 'github.com', 'ieee.org', 'nasa.gov', 'nature.com',
    'nih.gov', 'nytimes.com', 'reuters.com', 'sciencedirect.com',
    'technologyreview.com', 'theguardian.com', 'who.int', 'wikipedia.org', 'wsj.com'
})

MEDIUM_AUTHORITY_DOMAINS = frozenset({
    'arstechnica.com', 'engadget.com', 'forbes.com', 'infoworld.com',
    'medium.com', 'substack.com', 'techcrunch.com', 'theverge.com',
    'venturebeat.com', 'wired.com', 'zdnet.com'
})


def calculate_credibility(url: str, text: str) -> Tuple[float, List[str]]:
    """
    Evaluate credibility score (0.1 to 0.99) based on domain authority,
    text depth, and structural signals.
    """
    score = 0.5
    reasons: List[str] = []

    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        domain = ""

    # 1. Domain TLD Authority
    if any(domain.endswith(tld) for tld in ACADEMIC_GOV_TLDS):
        score += 0.3
        reasons.append("Academic or Government domain (.gov/.edu)")
    elif domain in HIGH_AUTHORITY_DOMAINS:
        score += 0.25
        reasons.append("Peer-reviewed, institutional, or Tier-1 news publisher")
    elif domain in MEDIUM_AUTHORITY_DOMAINS:
        score += 0.15
        reasons.append("Established tech journalism / recognized publication")
    else:
        reasons.append("Standard independent web publication")

    # 2. Text Depth & Substance
    char_len = len(text) if text else 0
    if char_len > 4000:
        score += 0.12
        reasons.append(f"In-depth comprehensive coverage ({char_len:,} chars)")
    elif char_len > 1500:
        score += 0.08
        reasons.append(f"Substantial article length ({char_len:,} chars)")
    elif char_len < 300:
        score -= 0.15
        reasons.append("Brief snippet or thin content")

    # 3. Security Protocol
    if url.startswith("https://"):
        score += 0.03
        reasons.append("Secure HTTPS connection")

    final_score = max(0.1, min(0.98, round(score, 2)))
    return final_score, reasons


async def scrape_single_url(url: str, title: str = "", snippet: str = "") -> Optional[ScrapedDocument]:
    """
    Fetch and extract clean text from a URL using Trafilatura with httpx fallback.
    """
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        domain = "unknown"

    clean_text = ""

    # Primary extractor: Trafilatura in thread executor
    def _extract_via_trafilatura():
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                return trafilatura.extract(
                    downloaded,
                    include_links=False,
                    include_comments=False,
                    no_fallback=False
                )
        except Exception:
            return None
        return None

    loop = asyncio.get_event_loop()
    try:
        clean_text = await loop.run_in_executor(None, _extract_via_trafilatura) or ""
    except Exception as e:
        logger.debug(f"Trafilatura failed for {url}: {e}")

    # Fallback extractor: httpx + BeautifulSoup
    if not clean_text or len(clean_text) < 150:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                        tag.decompose()
                    paragraphs = [p.get_text().strip() for p in soup.find_all(["p", "h1", "h2", "h3", "li"])]
                    extracted = "\n\n".join(p for p in paragraphs if len(p) > 25)
                    if len(extracted) > len(clean_text):
                        clean_text = extracted
        except Exception as e:
            logger.debug(f"HTTP fallback failed for {url}: {e}")

    # Final fallback to search snippet if scraping was blocked or empty
    if not clean_text or len(clean_text) < 100:
        if snippet:
            clean_text = f"{snippet}\n\n[Note: Direct article body extraction restricted on {domain}. Relying on verified search abstract.]"
        else:
            clean_text = f"Content summary could not be directly retrieved from {domain}."

    # Cap text length to avoid token bloat
    if len(clean_text) > 12000:
        clean_text = clean_text[:12000] + "\n...[Content truncated for analysis]..."

    cred_score, reasons = calculate_credibility(url, clean_text)

    return ScrapedDocument(
        url=url,
        title=title or "Source Document",
        snippet=snippet or "",
        clean_text=clean_text,
        domain=domain,
        char_count=len(clean_text),
        credibility_score=cred_score,
        credibility_reasons=reasons
    )


async def scrape_urls_concurrently(items: List[dict], max_concurrency: int = 5) -> List[ScrapedDocument]:
    """
    Scrape multiple search results concurrently with a semaphore to respect rate limits.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _safe_scrape(item: dict) -> Optional[ScrapedDocument]:
        url = item.get("url", "")
        if not url:
            return None
        async with semaphore:
            try:
                return await scrape_single_url(
                    url=url,
                    title=item.get("title", ""),
                    snippet=item.get("snippet", "")
                )
            except Exception as e:
                logger.warning(f"Error scraping {url}: {e}")
                return None

    tasks = [_safe_scrape(item) for item in items]
    results = await asyncio.gather(*tasks)
    return [doc for doc in results if doc is not None]
