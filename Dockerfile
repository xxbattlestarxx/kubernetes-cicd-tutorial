# Gebruik een officiële Python runtime als de basis image.
FROM python:3.12-slim

# Zet de werkmap in de container
WORKDIR /app


# Kopieer het requirements.txt bestand en installeer de afhankelijkheden
# Dit is een aparte stap, zodat Docker deze laag kan cachen
COPY src/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de rest van de applicatie
# (je Python-script)
COPY src/simple_ads.py .

# Voer het Python-script uit als de container start
CMD ["python3", "simple_ads.py"]
