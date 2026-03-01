# AutoBrickogniser

AutoBrickogniser captures a frame from your webcam, sends it to the Brickognize API for LEGO part recognition, then enriches the result with:

- Whether the part appears in any NINJAGO minifigure.
- Average **new** and **used** prices for the detected part.
- Average **new** and **used** prices for minifigures that contain the part.

## Tech stack

- Backend: Flask (`app.py`)
- Frontend: Plain HTML/CSS/JS (`templates/index.html`, `static/app.js`)
- Recognition: Brickognize (`/predict/parts/`)
- Pricing + relationships: BrickLink catalog pages (scraped server-side)

## Quick start

1. Create and activate a Python virtual environment.
2. Install dependencies:

	```bash
	pip install -r requirements.txt
	```

3. Run the app:

	```bash
	python app.py
	```

4. Open http://127.0.0.1:5000
5. Click **Start Camera**, then **Analyze Current Frame**.

## How it works

1. Frontend captures the current video frame into a JPEG blob.
2. Blob is posted to `POST /api/analyze`.
3. Backend forwards image to Brickognize parts prediction.
4. Best prediction is used to locate the BrickLink part ID.
5. Backend scrapes BrickLink for:
	- Part average new/used prices.
	- Minifigures that contain the part.
	- Each minifigure’s average new/used prices.
6. Frontend renders piece details, NINJAGO flag, and minifigure table.

## Notes and limitations

- Brickognize endpoint used here is the currently documented legacy endpoint.
- BrickLink enrichment uses HTML scraping (no official API key needed), so page structure changes can impact parsing.
- NINJAGO detection is based on minifigure name text containing `NINJAGO`.

## Next improvements

- Add still-frame quality checks before sending to API.
- Cache BrickLink lookups to speed up repeated scans.
- Add sorting/filtering in UI (e.g., NINJAGO only, highest used price).
