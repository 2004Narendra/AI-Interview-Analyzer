# AI Interview Analyzer

A Flask-based web application that evaluates interview answers using an LLM API and provides structured feedback such as score, strengths, weaknesses, and improved responses.

This project is designed to help users practice interviews, review their answers, and track performance over time.

## Features

- Interview answer analysis using OpenRouter or mock mode
- Score breakdown with feedback
- Strengths and weaknesses summary
- Improved answer suggestion
- History tracking for previous analyses
- CSV export for saved results
- Optional login for protected access
- Dark mode and improved UI experience
- Chart-based score trend visualization

## Tech Stack

- Python
- Flask
- Bootstrap
- OpenRouter API
- Chart.js
- SQLite / file-based persistence

## Project Structure

```text
.
├── app.py
├── requirements.txt
├── .env.example
├── templates/
│   ├── index.html
│   ├── history.html
│   └── login.html
├── static/
│   ├── css/
│   └── js/
├── README.md
├── Dockerfile
├── docker-compose.yml
└── .env
```

## Setup

1. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment variables:

Create a `.env` file in the project root.

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
# Optional for local testing without API access
MOCK_MODE=1
```

Optional login variables:

```env
LOGIN_ENABLED=1
ADMIN_USER=admin
ADMIN_PASS=supersecret
SECRET_KEY=replace-with-a-random-secret
```

## Run the App

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Usage

- Paste your interview answer into the form
- Click "Analyze Answer"
- Review the evaluation, strengths, weaknesses, and improved answer
- Save and browse your analysis history

## Development Notes

- If no OpenRouter API key is configured, the app can run in mock mode for development.
- For production, set a strong `SECRET_KEY` and avoid storing secrets in source control.
- The project is suitable for local development and can also run using Docker.

## Docker

Build and run:

```bash
docker build -t ai-interview-analyzer:latest .
docker run -p 5000:5000 -e MOCK_MODE=1 ai-interview-analyzer:latest
```

Or use Docker Compose:

```bash
docker-compose up --build
```

## License

This project is currently provided for educational and portfolio use.

## Portfolio Use

This project is a strong example of:
- AI application design
- Python backend development
- UI/UX and interaction workflow design
- practical AI product thinking
