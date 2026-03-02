from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BRICKOGNIZE_PREDICT_PARTS_URL = "https://api.brickognize.com/predict/parts/"
BRICKOGNIZE_PREDICT_URL = "https://api.brickognize.com/predict/"
BRICKOGNIZE_PREDICT_FIGS_URL = "https://api.brickognize.com/predict/figs/"
REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass
class PriceInfo:
    avg_new: str | None
    avg_used: str | None


def format_money_with_currency(curr: str | None, amount: str | None) -> str | None:
    """Format a numeric string into a currency-prefixed string.

    Prefers GBP when currency token is absent or ambiguous to match BrickLink pages.
    """
    if not amount:
        return None
    val = amount.replace(',', '').strip()
    try:
        f = float(val)
    except Exception:
        try:
            f = float(re.sub(r"[^0-9.]", "", val))
        except Exception:
            return None

    if curr:
        tok = curr.strip().upper()
        if 'GBP' in tok or '£' in curr:
            return f"£{f:.2f}"
        if '$' in tok or 'USD' in tok:
            return f"${f:.2f}"

    # Fallback: prefer GBP
    return f"£{f:.2f}"


def format_money_with_currency(curr: str | None, amount: str | None) -> str | None:
    """Format a numeric string into a currency-prefixed string.

    Prefers GBP when currency token is absent or ambiguous to match BrickLink pages.
    """
    if not amount:
        return None
    val = amount.replace(',', '').strip()
    try:
        f = float(val)
    except Exception:
        try:
            f = float(re.sub(r"[^0-9.]", "", val))
        except Exception:
            return None

    if curr:
        tok = curr.strip().upper()
        if 'GBP' in tok or '£' in curr:
            return f"£{f:.2f}"
        if '$' in tok or 'USD' in tok:
            return f"${f:.2f}"

    # Fallback: prefer GBP
    return f"£{f:.2f}"


session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def query_brickognize(image_bytes: bytes) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    endpoints = [
        BRICKOGNIZE_PREDICT_PARTS_URL,
        BRICKOGNIZE_PREDICT_URL,
        BRICKOGNIZE_PREDICT_FIGS_URL,
    ]

    attempts: list[dict[str, Any]] = []
    last_payload: dict[str, Any] = {}

    for endpoint in endpoints:
        files = {
            "query_image": (
                "capture.jpg",
                io.BytesIO(image_bytes),
                "image/jpeg",
            )
        }

        try:
            response = session.post(
                endpoint,
                files=files,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            attempts.append(
                {
                    "endpoint": endpoint,
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue

        items = payload.get("items", [])
        last_payload = payload
        attempts.append(
            {
                "endpoint": endpoint,
                "ok": True,
                "items_count": len(items),
            }
        )

        if items:
            part_items = [item for item in items if item.get("type") == "part"]
            return (part_items or items), payload, attempts

    return [], last_payload, attempts


def parse_bricklink_part_number(url: str) -> str | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "P" in query and query["P"]:
        return query["P"][0]

    match = re.search(r"[?&]P=([^&]+)", url)
    if match:
        return match.group(1)

    return None


def parse_bricklink_minifig_number(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "M" in query and query["M"]:
        return query["M"][0]

    match = re.search(r"[?&]M=([^&]+)", url)
    if match:
        return match.group(1)

    return None


def parse_bricklink_minifig_number(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "M" in query and query["M"]:
        return query["M"][0]

    match = re.search(r"[?&]M=([^&]+)", url)
    if match:
        return match.group(1)

    return None


def extract_bricklink_url(external_sites: list[dict[str, Any]]) -> str | None:
    for site in external_sites:
        if site.get("name", "").lower() == "bricklink" and site.get("url"):
            return site["url"]
    return None


def scrape_bricklink_image_url(item_url: str) -> str | None:
    try:
        response = session.get(item_url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return None
    try:
        response = session.get(item_url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    og_image = soup.select_one('meta[property="og:image"]')
    if og_image and og_image.get("content"):
        return og_image.get("content")

    image = soup.select_one("img#item-main-image") or soup.select_one("img[id*='item']")
    if image and image.get("src"):
        src = image.get("src")
        if src.startswith("http"):
            return src
        return f"https://www.bricklink.com/{src.lstrip('/')}"

    return None


def scrape_minifig_price_details(item_id: str) -> dict[str, Any]:
    # Scrape Last 6 Months Sales and Current Items for a minifigure using nearer-context parsing.
    url = (
        "https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page"
        f"?M={item_id}&tab=V"
    )
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    result: dict[str, Any] = {
        "last6": {"new": {"times_sold": None, "avg": None, "max": None}, "used": {"times_sold": None, "avg": None, "max": None}},
        "current": {"new": {"avg": None, "max": None}, "used": {"avg": None, "max": None}},
    }

    def format_money_with_currency(curr: str | None, amount: str | None) -> str | None:
        if not amount:
            return None
        val = amount.replace(',', '').strip()
        try:
            f = float(val)
        except Exception:
            try:
                f = float(re.sub(r"[^0-9.]", "", val))
            except Exception:
                return None

        # Determine currency symbol preference from captured token
        if curr:
            tok = curr.strip().upper()
            if 'GBP' in tok or '£' in curr:
                return f"£{f:.2f}"
            if '$' in tok or 'USD' in tok:
                return f"${f:.2f}"

        # Fallback: prefer GBP (many BrickLink pages use GBP). Use £ by default.
        return f"£{f:.2f}"

    # helper for finding a nearby value for a label within a slice
    def find_nearby(pattern: str, slice_text: str) -> str | None:
        m = re.search(pattern, slice_text, re.IGNORECASE)
        if not m:
            return None
        return m.group(1)

    # Collect repeated blocks like: Times Sold: <n> ... Avg Price: <x> ... Max Price: <y>
    # The page contains blocks for Last6 New, Last6 Used, Current New, Current Used in that order.
    block_pattern = re.compile(
        r"Times Sold:\s*([0-9,]+).*?Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?).*?Max Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)",
        re.IGNORECASE | re.DOTALL,
    )

    blocks = list(block_pattern.finditer(text))
    if blocks:
        # Map first four blocks if present
        def num(g: str) -> int | None:
            try:
                return int(g.replace(',', ''))
            except Exception:
                return None

        if len(blocks) >= 1:
            m = blocks[0]
            result["last6"]["new"]["times_sold"] = num(m.group(1))
            result["last6"]["new"]["avg"] = format_money_with_currency(m.group(2), m.group(3))
            result["last6"]["new"]["max"] = format_money_with_currency(m.group(4), m.group(5))

        if len(blocks) >= 2:
            m = blocks[1]
            result["last6"]["used"]["times_sold"] = num(m.group(1))
            result["last6"]["used"]["avg"] = format_money_with_currency(m.group(2), m.group(3))
            result["last6"]["used"]["max"] = format_money_with_currency(m.group(4), m.group(5))

        # For Current items, prefer Avg/Max values that appear within
        # the 'Total Lots' blocks (these correspond to the aggregate
        # "Current Items for Sale" stats). Collect blocks starting at
        # each 'Total Lots' label and extract the Avg/Max within them.
        cur_idx = text.lower().find('current items')
        if cur_idx != -1:
            cur_text = text[cur_idx: cur_idx + 8000]
            totals_positions = [m.start() for m in re.finditer(r"Total Lots:\s*", cur_text, re.IGNORECASE)]

            cur_pairs: list[tuple[str | None, str | None]] = []
            for pos in totals_positions:
                # take a slice after the Total Lots label to find Avg/Max nearby
                slice_text = cur_text[pos: pos + 400]
                a = re.search(r"Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", slice_text, re.IGNORECASE)
                mx = re.search(r"Max Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", slice_text, re.IGNORECASE)
                avg_val = format_money_with_currency(a.group(1) if a else None, a.group(2) if a else None) if a else None
                max_val = format_money_with_currency(mx.group(1) if mx else None, mx.group(2) if mx else None) if mx else None
                cur_pairs.append((avg_val, max_val))

            # Map first Total Lots block -> New, second -> Used (if present)
            if cur_pairs:
                if len(cur_pairs) >= 1:
                    result["current"]["new"]["avg"] = cur_pairs[0][0]
                    result["current"]["new"]["max"] = cur_pairs[0][1]
                if len(cur_pairs) >= 2:
                    result["current"]["used"]["avg"] = cur_pairs[1][0]
                    result["current"]["used"]["max"] = cur_pairs[1][1]

    return result


def scrape_minifig_price_details(item_id: str) -> dict[str, Any]:
    # Scrape Last 6 Months Sales and Current Items for a minifigure using nearer-context parsing.
    url = (
        "https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page"
        f"?M={item_id}&tab=V"
    )
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    result: dict[str, Any] = {
        "last6": {"new": {"times_sold": None, "avg": None, "max": None}, "used": {"times_sold": None, "avg": None, "max": None}},
        "current": {"new": {"avg": None, "max": None}, "used": {"avg": None, "max": None}},
    }

    def format_money_with_currency(curr: str | None, amount: str | None) -> str | None:
        if not amount:
            return None
        val = amount.replace(',', '').strip()
        try:
            f = float(val)
        except Exception:
            try:
                f = float(re.sub(r"[^0-9.]", "", val))
            except Exception:
                return None

        # Determine currency symbol preference from captured token
        if curr:
            tok = curr.strip().upper()
            if 'GBP' in tok or '£' in curr:
                return f"£{f:.2f}"
            if '$' in tok or 'USD' in tok:
                return f"${f:.2f}"

        # Fallback: prefer GBP (many BrickLink pages use GBP). Use £ by default.
        return f"£{f:.2f}"

    # helper for finding a nearby value for a label within a slice
    def find_nearby(pattern: str, slice_text: str) -> str | None:
        m = re.search(pattern, slice_text, re.IGNORECASE)
        if not m:
            return None
        return m.group(1)

    # Collect repeated blocks like: Times Sold: <n> ... Avg Price: <x> ... Max Price: <y>
    # The page contains blocks for Last6 New, Last6 Used, Current New, Current Used in that order.
    block_pattern = re.compile(
        r"Times Sold:\s*([0-9,]+).*?Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?).*?Max Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)",
        re.IGNORECASE | re.DOTALL,
    )

    blocks = list(block_pattern.finditer(text))
    if blocks:
        # Map first four blocks if present
        def num(g: str) -> int | None:
            try:
                return int(g.replace(',', ''))
            except Exception:
                return None

        if len(blocks) >= 1:
            m = blocks[0]
            result["last6"]["new"]["times_sold"] = num(m.group(1))
            result["last6"]["new"]["avg"] = format_money_with_currency(m.group(2), m.group(3))
            result["last6"]["new"]["max"] = format_money_with_currency(m.group(4), m.group(5))

        if len(blocks) >= 2:
            m = blocks[1]
            result["last6"]["used"]["times_sold"] = num(m.group(1))
            result["last6"]["used"]["avg"] = format_money_with_currency(m.group(2), m.group(3))
            result["last6"]["used"]["max"] = format_money_with_currency(m.group(4), m.group(5))

        # For Current items, prefer Avg/Max values that appear within
        # the 'Total Lots' blocks (these correspond to the aggregate
        # "Current Items for Sale" stats). Collect blocks starting at
        # each 'Total Lots' label and extract the Avg/Max within them.
        cur_idx = text.lower().find('current items')
        if cur_idx != -1:
            cur_text = text[cur_idx: cur_idx + 8000]
            totals_positions = [m.start() for m in re.finditer(r"Total Lots:\s*", cur_text, re.IGNORECASE)]

            cur_pairs: list[tuple[str | None, str | None]] = []
            for pos in totals_positions:
                # take a slice after the Total Lots label to find Avg/Max nearby
                slice_text = cur_text[pos: pos + 400]
                a = re.search(r"Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", slice_text, re.IGNORECASE)
                mx = re.search(r"Max Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", slice_text, re.IGNORECASE)
                avg_val = format_money_with_currency(a.group(1) if a else None, a.group(2) if a else None) if a else None
                max_val = format_money_with_currency(mx.group(1) if mx else None, mx.group(2) if mx else None) if mx else None
                cur_pairs.append((avg_val, max_val))

            # Map first Total Lots block -> New, second -> Used (if present)
            if cur_pairs:
                if len(cur_pairs) >= 1:
                    result["current"]["new"]["avg"] = cur_pairs[0][0]
                    result["current"]["new"]["max"] = cur_pairs[0][1]
                if len(cur_pairs) >= 2:
                    result["current"]["used"]["avg"] = cur_pairs[1][0]
                    result["current"]["used"]["max"] = cur_pairs[1][1]

    return result


def scrape_price_guide(item_type: str, item_id: str) -> PriceInfo:
    # Minimal price guide scraper for parts or minifigures.
    # Uses the same pgtab endpoint and extracts the first two "Avg Price" occurrences
    # as New and Used averages respectively.
    # Minimal price guide scraper for parts or minifigures.
    # Uses the same pgtab endpoint and extracts the first two "Avg Price" occurrences
    # as New and Used averages respectively.
    url = (
        "https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page"
        f"?{item_type}={item_id}&tab=V"
    )
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Capture currency token and value
    avg_matches = re.findall(r"Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", text, re.IGNORECASE)

    def to_money_pair(match: tuple[str | None, str] | None) -> str | None:
        if not match:
            return None
        curr, amt = match
        try:
            v = float(amt.replace(',', ''))
        except Exception:
            return None
        if curr:
            tok = curr.strip().upper()
            if 'GBP' in tok or '£' in curr:
                return f"£{v:.2f}"
            if '$' in tok or 'USD' in tok:
                return f"${v:.2f}"
        return f"£{v:.2f}"

    new_avg = to_money_pair(avg_matches[0]) if len(avg_matches) >= 1 else None
    used_avg = to_money_pair(avg_matches[1]) if len(avg_matches) >= 2 else None

    return PriceInfo(avg_new=new_avg, avg_used=used_avg)


def scrape_part_price_details(part_number: str) -> dict[str, Any]:
    # Scrape Last 6 Months Sales and Current Items for a part (P=)
    url = (
        "https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page"
        f"?P={part_number}&tab=V"
    )
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    result: dict[str, Any] = {
        "last6": {"new": {"times_sold": None, "avg": None, "max": None}, "used": {"times_sold": None, "avg": None, "max": None}},
        "current": {"new": {"avg": None, "max": None}, "used": {"avg": None, "max": None}},
    }

    # Reuse the same block pattern approach but tuned for parts
    block_pattern = re.compile(
        r"Times Sold:\s*([0-9,]+).*?Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?).*?Max Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)",
        re.IGNORECASE | re.DOTALL,
    )

    blocks = list(block_pattern.finditer(text))
    def num(g: str) -> int | None:
        try:
            return int(g.replace(',', ''))
        except Exception:
            return None

    if len(blocks) >= 1:
        m = blocks[0]
        result["last6"]["new"]["times_sold"] = num(m.group(1))
        result["last6"]["new"]["avg"] = format_money_with_currency(m.group(2), m.group(3))
        result["last6"]["new"]["max"] = format_money_with_currency(m.group(4), m.group(5))

    if len(blocks) >= 2:
        m = blocks[1]
        result["last6"]["used"]["times_sold"] = num(m.group(1))
        result["last6"]["used"]["avg"] = format_money_with_currency(m.group(2), m.group(3))
        result["last6"]["used"]["max"] = format_money_with_currency(m.group(4), m.group(5))

    # Current items: look for "Total Lots" blocks as with minifigs
    cur_idx = text.lower().find('current items')
    if cur_idx != -1:
        cur_text = text[cur_idx: cur_idx + 8000]
        totals_positions = [m.start() for m in re.finditer(r"Total Lots:\s*", cur_text, re.IGNORECASE)]
        cur_pairs: list[tuple[str | None, str | None]] = []
        for pos in totals_positions:
            slice_text = cur_text[pos: pos + 400]
            a = re.search(r"Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", slice_text, re.IGNORECASE)
            mx = re.search(r"Max Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", slice_text, re.IGNORECASE)
            avg_val = format_money_with_currency(a.group(1) if a else None, a.group(2) if a else None) if a else None
            max_val = format_money_with_currency(mx.group(1) if mx else None, mx.group(2) if mx else None) if mx else None
            cur_pairs.append((avg_val, max_val))

        if cur_pairs:
            if len(cur_pairs) >= 1:
                result["current"]["new"]["avg"] = cur_pairs[0][0]
                result["current"]["new"]["max"] = cur_pairs[0][1]
            if len(cur_pairs) >= 2:
                result["current"]["used"]["avg"] = cur_pairs[1][0]
                result["current"]["used"]["max"] = cur_pairs[1][1]

    return result
    # Capture currency token and value
    avg_matches = re.findall(r"Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", text, re.IGNORECASE)

    def to_money_pair(match: tuple[str | None, str] | None) -> str | None:
        if not match:
            return None
        curr, amt = match
        try:
            v = float(amt.replace(',', ''))
        except Exception:
            return None
        if curr:
            tok = curr.strip().upper()
            if 'GBP' in tok or '£' in curr:
                return f"£{v:.2f}"
            if '$' in tok or 'USD' in tok:
                return f"${v:.2f}"
        return f"£{v:.2f}"

    new_avg = to_money_pair(avg_matches[0]) if len(avg_matches) >= 1 else None
    used_avg = to_money_pair(avg_matches[1]) if len(avg_matches) >= 2 else None

    return PriceInfo(avg_new=new_avg, avg_used=used_avg)


def scrape_part_price_details(part_number: str) -> dict[str, Any]:
    # Scrape Last 6 Months Sales and Current Items for a part (P=)
    url = (
        "https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page"
        f"?P={part_number}&tab=V"
    )
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    result: dict[str, Any] = {
        "last6": {"new": {"times_sold": None, "avg": None, "max": None}, "used": {"times_sold": None, "avg": None, "max": None}},
        "current": {"new": {"avg": None, "max": None}, "used": {"avg": None, "max": None}},
    }

    # Reuse the same block pattern approach but tuned for parts
    block_pattern = re.compile(
        r"Times Sold:\s*([0-9,]+).*?Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?).*?Max Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)",
        re.IGNORECASE | re.DOTALL,
    )

    blocks = list(block_pattern.finditer(text))
    def num(g: str) -> int | None:
        try:
            return int(g.replace(',', ''))
        except Exception:
            return None

    if len(blocks) >= 1:
        m = blocks[0]
        result["last6"]["new"]["times_sold"] = num(m.group(1))
        result["last6"]["new"]["avg"] = format_money_with_currency(m.group(2), m.group(3))
        result["last6"]["new"]["max"] = format_money_with_currency(m.group(4), m.group(5))

    if len(blocks) >= 2:
        m = blocks[1]
        result["last6"]["used"]["times_sold"] = num(m.group(1))
        result["last6"]["used"]["avg"] = format_money_with_currency(m.group(2), m.group(3))
        result["last6"]["used"]["max"] = format_money_with_currency(m.group(4), m.group(5))

    # Current items: look for "Total Lots" blocks as with minifigs
    cur_idx = text.lower().find('current items')
    if cur_idx != -1:
        cur_text = text[cur_idx: cur_idx + 8000]
        totals_positions = [m.start() for m in re.finditer(r"Total Lots:\s*", cur_text, re.IGNORECASE)]
        cur_pairs: list[tuple[str | None, str | None]] = []
        for pos in totals_positions:
            slice_text = cur_text[pos: pos + 400]
            a = re.search(r"Avg Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", slice_text, re.IGNORECASE)
            mx = re.search(r"Max Price:\s*(?:((?:GBP|US\s*\$|USD\s*\$|£|\$))\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", slice_text, re.IGNORECASE)
            avg_val = format_money_with_currency(a.group(1) if a else None, a.group(2) if a else None) if a else None
            max_val = format_money_with_currency(mx.group(1) if mx else None, mx.group(2) if mx else None) if mx else None
            cur_pairs.append((avg_val, max_val))

        if cur_pairs:
            if len(cur_pairs) >= 1:
                result["current"]["new"]["avg"] = cur_pairs[0][0]
                result["current"]["new"]["max"] = cur_pairs[0][1]
            if len(cur_pairs) >= 2:
                result["current"]["used"]["avg"] = cur_pairs[1][0]
                result["current"]["used"]["max"] = cur_pairs[1][1]

    return result


def scrape_minifigs_using_part(part_number: str) -> list[dict[str, str]]:
    # BrickLink catalog relationships page for Minifigures using a part.
    # The page structure is not a public API and may change.
    url = (
        "https://www.bricklink.com/catalogItemIn.asp"
        f"?P={part_number}&in=M"
    )
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    anchors = soup.select("a[href*='catalogitem.page?M=']")

    seen: set[str] = set()
    figs: list[dict[str, str]] = []

    for anchor in anchors:
        href = anchor.get("href", "")
        full_href = href if href.startswith("http") else f"https://www.bricklink.com/{href.lstrip('/')}"

        parsed = urlparse(full_href)
        query = parse_qs(parsed.query)
        fig_id = query.get("M", [None])[0]
        fig_name = anchor.get_text(strip=True)

        if not fig_id or not fig_name:
            continue
        if fig_id in seen:
            continue

        seen.add(fig_id)
        figs.append(
            {
                "id": fig_id,
                "name": fig_name,
                "url": full_href,
            }
        )

    return figs


def scrape_minifig_inventory(minifig_id: str) -> list[dict[str, str]]:
    """Scrape a minifigure page and return a list of parts with item no and image url.

    This uses a best-effort approach: find anchors to part pages and nearby image tags.
    """
    if not minifig_id:
        return []

    # Try multiple endpoints/variants to surface the inventory section. Some BrickLink pages
    # expose the inventory under a separate tab or different URL parameters; try them in order.
    try_urls = [
        f"https://www.bricklink.com/v2/catalog/catalogitem.page?M={minifig_id}",
        f"https://www.bricklink.com/v2/catalog/catalogitem.page?M={minifig_id}&T=I",
        f"https://www.bricklink.com/v2/catalog/catalogitem.page?M={minifig_id}&tab=I",
        f"https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page?M={minifig_id}&tab=I",
    ]

    parts: list[dict[str, str]] = []
    seen: set[str] = set()

    soup = None
    for u in try_urls:
        try:
            response = session.get(u, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException:
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        # Broadly search for anchors that include a ?P= or &P= pattern, not just catalogitem.page
        anchors = [a for a in soup.find_all('a', href=True) if re.search(r"[?&]P=", a.get('href', ''))]
        if anchors:
            # we found candidate anchors on this variant, stop trying further URLs
            break

    if not soup:
        return []

    # Process all discovered anchors and deduplicate by part number
    for a in anchors:
        href = a.get('href', '')
        full_href = href if href.startswith('http') else f"https://www.bricklink.com/{href.lstrip('/')}"
        parsed = urlparse(full_href)
        query = parse_qs(parsed.query)
        p = query.get('P', [None])[0]
        if not p or p in seen:
            continue
        seen.add(p)

        # Try to get a nearby image: prefer img inside the anchor, otherwise look for img sibling or parent
        img = a.find('img') or a.select_one('img')
        image_url = None
        if img and img.get('src'):
            src = img.get('src')
            image_url = src if src.startswith('http') else f"https://www.bricklink.com/{src.lstrip('/')}"
        else:
            parent_img = a.find_parent()
            if parent_img:
                found = parent_img.select_one('img')
                if found and found.get('src'):
                    src = found.get('src')
                    image_url = src if src.startswith('http') else f"https://www.bricklink.com/{src.lstrip('/')}"

        part_name = a.get_text(strip=True) or None
        parts.append({"part_number": p, "name": part_name, "url": full_href, "image_url": image_url})

    return parts


def looks_like_ninjago(text: str) -> bool:
    return "ninjago" in text.lower().replace(" ", "")


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/analyze")
def analyze_piece():
    try:
        image = request.files.get("image")
        if image is None:
            return jsonify({"error": "Missing image file."}), 400
    try:
        image = request.files.get("image")
        if image is None:
            return jsonify({"error": "Missing image file."}), 400

        image_bytes = image.read()
        if not image_bytes:
            return jsonify({"error": "Image is empty."}), 400
        image_bytes = image.read()
        if not image_bytes:
            return jsonify({"error": "Image is empty."}), 400

        items, prediction, attempts = query_brickognize(image_bytes)
        if not items:
            return jsonify(
                {
                    "error": "No match found by Brickognize.",
                    "details": {
                        "attempts": attempts,
                        "tips": [
                            "Ensure the part fills most of the frame.",
                            "Use better lighting and avoid blur.",
                            "Place the part on a plain, high-contrast background.",
                            "Wait 1-2 seconds after camera starts before analyzing.",
                        ],
                    },
                    "brickognize": {
                        "attempts": attempts,
                        "raw_response": prediction,
                    },
                }
            ), 404
        items, prediction, attempts = query_brickognize(image_bytes)
        if not items:
            return jsonify(
                {
                    "error": "No match found by Brickognize.",
                    "details": {
                        "attempts": attempts,
                        "tips": [
                            "Ensure the part fills most of the frame.",
                            "Use better lighting and avoid blur.",
                            "Place the part on a plain, high-contrast background.",
                            "Wait 1-2 seconds after camera starts before analyzing.",
                        ],
                    },
                    "brickognize": {
                        "attempts": attempts,
                        "raw_response": prediction,
                    },
                }
            ), 404

        best = items[0]
        external_sites = best.get("external_sites", [])
        bricklink_item_url = extract_bricklink_url(external_sites)
        bricklink_image_url = None
        best = items[0]
        external_sites = best.get("external_sites", [])
        bricklink_item_url = extract_bricklink_url(external_sites)
        bricklink_image_url = None

        if bricklink_item_url:
            try:
                bricklink_image_url = scrape_bricklink_image_url(bricklink_item_url)
            except requests.RequestException:
                bricklink_image_url = None
        if bricklink_item_url:
            try:
                bricklink_image_url = scrape_bricklink_image_url(bricklink_item_url)
            except requests.RequestException:
                bricklink_image_url = None

        part_number = parse_bricklink_part_number(bricklink_item_url) if bricklink_item_url else None
        minifig_number = parse_bricklink_minifig_number(bricklink_item_url) if bricklink_item_url else None
        part_number = parse_bricklink_part_number(bricklink_item_url) if bricklink_item_url else None
        minifig_number = parse_bricklink_minifig_number(bricklink_item_url) if bricklink_item_url else None

        part_price = PriceInfo(avg_new=None, avg_used=None)
        part_price_details = None
        minifigs: list[dict[str, Any]] = []
        part_price = PriceInfo(avg_new=None, avg_used=None)
        part_price_details = None
        minifigs: list[dict[str, Any]] = []

        if part_number:
            try:
                part_price = scrape_price_guide("P", part_number)
            except requests.RequestException:
                part_price = PriceInfo(avg_new=None, avg_used=None)
        if part_number:
            try:
                part_price = scrape_price_guide("P", part_number)
            except requests.RequestException:
                part_price = PriceInfo(avg_new=None, avg_used=None)

            try:
                part_price_details = scrape_part_price_details(part_number)
            except requests.RequestException:
                part_price_details = None

            try:
                minifigs = scrape_minifigs_using_part(part_number)
            except requests.RequestException:
                minifigs = []
            try:
                part_price_details = scrape_part_price_details(part_number)
            except requests.RequestException:
                part_price_details = None

            try:
                minifigs = scrape_minifigs_using_part(part_number)
            except requests.RequestException:
                minifigs = []

        # Determine whether the BrickLink item is a minifigure, a part, or other
        if minifig_number:
            bricklink_type = "minifigure"
        elif part_number:
            bricklink_type = "minifigure_part"
        else:
            bricklink_type = "other"

        enriched_minifigs: list[dict[str, Any]] = []
        for fig in minifigs:
            prices = PriceInfo(avg_new=None, avg_used=None)
            try:
                prices = scrape_price_guide("M", fig["id"])
            except requests.RequestException:
                pass
        # Determine whether the BrickLink item is a minifigure, a part, or other
        if minifig_number:
            bricklink_type = "minifigure"
        elif part_number:
            bricklink_type = "minifigure_part"
        else:
            bricklink_type = "other"

        enriched_minifigs: list[dict[str, Any]] = []
        for fig in minifigs:
            prices = PriceInfo(avg_new=None, avg_used=None)
            try:
                prices = scrape_price_guide("M", fig["id"])
            except requests.RequestException:
                pass

            # Determine Ninjago by name or by ID prefix (e.g., njo####)
            fid = (fig.get("id") or "").lower()
            is_ninjago = looks_like_ninjago(fig.get("name", "")) or fid.startswith(("njo", "ngo"))

            enriched_minifigs.append(
                {
                    **fig,
                    "is_ninjago": is_ninjago,
                    "avg_new_price": prices.avg_new,
                    "avg_used_price": prices.avg_used,
                }
            )
            enriched_minifigs.append(
                {
                    **fig,
                    "is_ninjago": is_ninjago,
                    "avg_new_price": prices.avg_new,
                    "avg_used_price": prices.avg_used,
                }
            )

        # Sort minifigures: show NJO-prefixed IDs first, then by ID, then by avg_new (descending)
        def parse_currency_to_float(s: str | None) -> float:
            if not s:
                return 0.0
            # strip any currency symbols/letters
            try:
                return float(re.sub(r"[^0-9.]", "", s))
            except Exception:
                return 0.0

        def fig_sort_key(f: dict[str, Any]) -> tuple[int, str, float]:
            fid = (f.get("id") or "").lower()
            pref = 0 if fid.startswith("njo") else 1
            avg_new = parse_currency_to_float(f.get("avg_new_price"))
            # negative avg_new so higher prices appear earlier when IDs tie
            return (pref, fid, -avg_new)

        enriched_minifigs.sort(key=fig_sort_key)

        ninjago_figs = [fig for fig in enriched_minifigs if fig["is_ninjago"]]
        # Sort minifigures: show NJO-prefixed IDs first, then by ID, then by avg_new (descending)
        def parse_currency_to_float(s: str | None) -> float:
            if not s:
                return 0.0
            # strip any currency symbols/letters
            try:
                return float(re.sub(r"[^0-9.]", "", s))
            except Exception:
                return 0.0

        def fig_sort_key(f: dict[str, Any]) -> tuple[int, str, float]:
            fid = (f.get("id") or "").lower()
            pref = 0 if fid.startswith("njo") else 1
            avg_new = parse_currency_to_float(f.get("avg_new_price"))
            # negative avg_new so higher prices appear earlier when IDs tie
            return (pref, fid, -avg_new)

        enriched_minifigs.sort(key=fig_sort_key)

        ninjago_figs = [fig for fig in enriched_minifigs if fig["is_ninjago"]]

        # If the detected BrickLink item is a minifigure, fetch detailed pricing stats
        minifigure_price_details = None
        is_minifigure = False
        minifig_is_ninjago = False
        minifigure_inventory = None

        if bricklink_type == "minifigure" or prediction.get("type") == "fig":
            is_minifigure = True
            mf_id = minifig_number or best.get("id")
            try:
                minifigure_price_details = scrape_minifig_price_details(mf_id)
            except requests.RequestException:
                minifigure_price_details = None

            # Fetch inventory parts for this minifigure (item numbers + images)
            minifigure_inventory = None
            try:
                minifigure_inventory = scrape_minifig_inventory(mf_id)
            except requests.RequestException:
                minifigure_inventory = None

            # determine ninjago by id if available
            if mf_id:
                fid = (mf_id or "").lower()
                minifig_is_ninjago = fid.startswith("njo") or fid.startswith("ngo") or fid.startswith("njo")
        else:
            # If this is a part, determine whether it is part of any Ninjago minifigure
            if enriched_minifigs:
                minifig_is_ninjago = any(f.get("is_ninjago") for f in enriched_minifigs)

        result = {
            "prediction": {
                "id": best.get("id"),
                "name": best.get("name"),
                "type": best.get("type"),
                "score": best.get("score"),
                "image_url": best.get("img_url"),
                "bricklink_url": bricklink_item_url,
                "bricklink_image_url": bricklink_image_url,
                "part_number": part_number,
                "part_price_details": part_price_details,
                "avg_new_price": part_price.avg_new,
                "avg_used_price": part_price.avg_used,
                "bricklink_type": bricklink_type,
                "is_minifigure": is_minifigure,
                "minifigure_price_details": minifigure_price_details,
                "minifigure_is_ninjago": minifig_is_ninjago,
                "minifigure_inventory": minifigure_inventory,
            },
            "brickognize_attempts": attempts,
            "brickognize": {
                "attempts": attempts,
                "raw_response": prediction,
            },
            "ninjago": {
                "is_in_any_ninjago_minifigure": len(ninjago_figs) > 0,
                "matching_minifigures_count": len(ninjago_figs),
            },
            "minifigures": enriched_minifigs,
        }

        return jsonify(result)
    except Exception as exc:
        import traceback

        tb = traceback.format_exc()
        return jsonify({"error": "Internal server error", "message": str(exc), "trace": tb}), 500

    # end of handler
        return jsonify(result)
    except Exception as exc:
        import traceback

        tb = traceback.format_exc()
        return jsonify({"error": "Internal server error", "message": str(exc), "trace": tb}), 500

    # end of handler


if __name__ == "__main__":
    app.run(debug=True)
