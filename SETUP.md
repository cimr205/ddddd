# Setup Guide – Alt er gratis

## 1. Installer dependencies

```bash
pip install -r requirements.txt
```

## 2. Kør setup wizard (anbefalet)

```bash
python setup_wizard.py
```

Wizarden guider dig igennem alle valg trin for trin.

---

## Manuel opsætning

### .env fil

```bash
cp .env.example .env
```

Rediger `.env` med dine valg herunder.

---

## AI til email-skrivning (vælg én)

### Mulighed A: Groq API – GRATIS, ingen kreditkort

1. Gå til **https://console.groq.com**
2. Sign up med email (ingen kreditkort)
3. Gå til **API Keys → Create API Key**
4. Kopiér nøglen

```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
GROQ_MODEL=llama3-8b-8192
```

Inkluderede gratis modeller: `llama3-8b-8192`, `mixtral-8x7b-32768`, `gemma-7b-it`

---

### Mulighed B: Ollama – lokal AI, ingen internet, ingen signup

```bash
# Linux/Mac:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows:
# Download fra https://ollama.ai/download

# Pull model (kræver ~4 GB plads):
ollama pull llama3
```

```env
OLLAMA_ENABLED=true
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

---

### Mulighed C: Templates (ingen setup)

Ingen konfiguration. Systemet bruger automatisk smarte email-skabeloner.
Fungerer altid. Ingen internet eller API-key krævet.

---

## Email Sending (vælg én)

### Gmail – 500 emails/dag gratis

**Kræver App Password (ikke dit normale password):**

1. Gå til https://myaccount.google.com/security
2. Slå **2-Step Verification** til
3. Søg efter **App passwords** på samme side
4. Vælg **Mail** → **Windows Computer** → **Generate**
5. Kopiér den 16-tegns kode

```env
SMTP_ACCOUNTS=dinmail@gmail.com:abcdabcdabcdabcd@smtp.gmail.com:587
```

**Flere konti for højere volumen:**
```env
SMTP_ACCOUNTS=konto1@gmail.com:password1@smtp.gmail.com:587,konto2@gmail.com:password2@smtp.gmail.com:587
```

---

### Brevo (Sendinblue) – 300 emails/dag gratis

1. Signup: https://app.brevo.com
2. Gå til **SMTP & API → SMTP**
3. Kopiér login og SMTP key

```env
SMTP_ACCOUNTS=dinbrevo@email.com:dinSMTPkey@smtp-relay.brevo.com:587
```

---

### Mailersend – 100 emails/dag gratis

1. Signup: https://app.mailersend.com
2. **Email → Domains → Manage → SMTP**

```env
SMTP_ACCOUNTS=bruger@mailersend.net:password@smtp.mailersend.net:587
```

---

## Scraping / Internet-adgang

Scraperen bruger **Playwright Chromium** – en headless browser der kører lokalt.

```bash
playwright install chromium
```

Det downloader Chromium (~120 MB). Herefter bruger scraperen din normale
internet-forbindelse til at tilgå Google Maps. Ingen proxy eller VPN kræves,
men systemet bruger random delays og user-agents for at undgå blokering.

**Virker det ikke?** Google Maps ændrer sine selectors. Åbn en issue eller
kør scraperen med `headless=False` i `scrapers/google_maps.py` for at se hvad der sker.

---

## Start systemet

```bash
python main.py
```

Åbn **http://localhost:8000** i din browser.

---

## Komplet gratis stack

| Komponent | Gratis løsning | Grænse |
|-----------|---------------|--------|
| AI emails | Groq API | Generøst gratis niveau |
| AI lokalt | Ollama + llama3 | Ubegrænset |
| Email SMTP | Gmail App Password | 500/dag |
| Email SMTP | Brevo free | 300/dag |
| Scraping | Playwright Chromium | Ubegrænset |
| Database | SQLite | Ubegrænset |
| Dashboard | FastAPI + WebSocket | Ubegrænset |
