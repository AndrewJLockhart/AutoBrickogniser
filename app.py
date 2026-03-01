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


def extract_bricklink_url(external_sites: list[dict[str, Any]]) -> str | None:
    for site in external_sites:
        if site.get("name", "").lower() == "bricklink" and site.get("url"):
            return site["url"]
    return None


def scrape_bricklink_image_url(item_url: str) -> str | None:
    response = session.get(item_url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

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


def scrape_price_guide(item_type: str, item_id: str) -> PriceInfo:
    # item_type: P = part, M = minifigure
    url = (
        "https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page"
        f"?{item_type}={item_id}&tab=V"
    )
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    avg_new = None
    avg_used = None

    new_match = re.search(r"Avg Price\s*[:]?\s*US \$\s*([0-9]+(?:\.[0-9]{1,2})?)", text)
    if new_match:
        avg_new = f"${new_match.group(1)}"

    # Find used average by narrowing to 'Used' section then reading next Avg Price.
    used_section_idx = text.lower().find("used")
    if used_section_idx != -1:
        used_text = text[used_section_idx: used_section_idx + 3000]
        used_match = re.search(
            r"Avg Price\s*[:]?\s*US \$\s*([0-9]+(?:\.[0-9]{1,2})?)", used_text
        )
        if used_match:
            avg_used = f"${used_match.group(1)}"

    return PriceInfo(avg_new=avg_new, avg_used=avg_used)


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


def looks_like_ninjago(text: str) -> bool:
    return "ninjago" in text.lower().replace(" ", "")


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/analyze")
def analyze_piece():
    image = request.files.get("image")
    if image is None:
        return jsonify({"error": "Missing image file."}), 400

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

    best = items[0]
    external_sites = best.get("external_sites", [])
    bricklink_item_url = extract_bricklink_url(external_sites)
    bricklink_image_url = None

    if bricklink_item_url:
        try:
            bricklink_image_url = scrape_bricklink_image_url(bricklink_item_url)
        except requests.RequestException:
            bricklink_image_url = None

    part_number = parse_bricklink_part_number(bricklink_item_url) if bricklink_item_url else None

    part_price = PriceInfo(avg_new=None, avg_used=None)
    minifigs: list[dict[str, Any]] = []

    if part_number:
        try:
            part_price = scrape_price_guide("P", part_number)
        except requests.RequestException:
            part_price = PriceInfo(avg_new=None, avg_used=None)

        try:
            minifigs = scrape_minifigs_using_part(part_number)
        except requests.RequestException:
            minifigs = []

    enriched_minifigs: list[dict[str, Any]] = []
    for fig in minifigs:
        prices = PriceInfo(avg_new=None, avg_used=None)
        try:
            prices = scrape_price_guide("M", fig["id"])
        except requests.RequestException:
            pass

        is_ninjago = looks_like_ninjago(fig["name"])

        enriched_minifigs.append(
            {
                **fig,
                "is_ninjago": is_ninjago,
                "avg_new_price": prices.avg_new,
                "avg_used_price": prices.avg_used,
            }
        )

    ninjago_figs = [fig for fig in enriched_minifigs if fig["is_ninjago"]]

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
            "avg_new_price": part_price.avg_new,
            "avg_used_price": part_price.avg_used,
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


if __name__ == "__main__":
    app.run(debug=True)
