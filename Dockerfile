# Bruger Microsofts officielle Playwright image – har Chromium + alle deps pre-installeret
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Installer Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer Chromium browser
RUN playwright install chromium

# Kopiér resten af koden
COPY . .

# Opret data mappe til SQLite database
RUN mkdir -p data

EXPOSE 8000

CMD ["python", "main.py"]
