# AI Interview Analyser

Simple Flask app that evaluates interview answers using OpenRouter (or mock mode).

Quick start

1. Create and activate a Python virtualenv.

```powershell
python -m venv venv
& .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Create a `.env` file with your OpenRouter key (optional if using mock mode):

```
OPENROUTER_API_KEY=sk-or-...
# or to force mock mode for development
MOCK_MODE=1
```

3. Run the app:

```powershell
& .\venv\Scripts\python.exe app.py
```

4. Visit `http://127.0.0.1:5000` and try the analyzer.

Features added by the helper agent:
- CSV export (`/export_csv`)
- Per-item delete from history
- Per-item copy buttons in history
- Mock mode for offline development
# AI Interview Analyser

A small Flask app that evaluates interview answers using OpenRouter.

## Setup

1. Create a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
3. Add your OpenRouter API key to `.env`:
   ```text
   OPENROUTER_API_KEY=your_openrouter_api_key_here
   ```
4. Run the app:
   ```powershell
   python app.py
   ```

## Usage

- Open `http://127.0.0.1:5000/`
- Paste your interview answer into the textarea
- Click `Analyze Answer`
- Review the score, strengths, weaknesses, and improved answer

## New UI features

- Better styling: the app uses Bootstrap for a cleaner UI.
- Dark mode: toggle with the moon button in the header; preference is saved locally.
- Charts: the history page shows a trend line of saved scores (Chart.js).
- Optional login: enable a simple session-based login via environment variables.

To enable login, create a `.env` (copy `.env.example`) and set `LOGIN_ENABLED=1`, and set `ADMIN_USER`/`ADMIN_PASS`.

Example `.env` values:

```
LOGIN_ENABLED=1
ADMIN_USER=admin
ADMIN_PASS=supersecret
SECRET_KEY=replace-with-random-secret
```

Notes:
- Chart rendering uses a CDN-hosted Chart.js; no extra Python dependency is required.
- For production, run behind a WSGI server (e.g. `gunicorn`) and set a strong `SECRET_KEY`.
## Notes

- This app now uses OpenRouter instead of Google Gemini.
- If you do not have an OpenRouter key, sign up at `https://openrouter.ai/` and create a free API key.
- Keep `debug=True` only for development.

## Docker

Run the app using Docker (recommended for consistent environments):

Build the image:

```bash
docker build -t ai-interview-analyser:latest .
```

Run with Docker:

```bash
docker run -p 5000:5000 -e MOCK_MODE=1 ai-interview-analyser:latest
```

Or use `docker-compose` for development (mounts current directory):

```bash
docker-compose up --build
```

The app will then be available at `http://127.0.0.1:5000`.

## Deployment notes

- The Docker image runs the app with `gunicorn`.
- For production, provide a secure `SECRET_KEY` and configure environment variables (do not commit secrets).
- Consider placing the app behind a reverse proxy (nginx) and enabling TLS.

