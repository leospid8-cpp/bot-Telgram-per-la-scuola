# Bot Orario Telegram

Bot semplice per mostrare l'orario scolastico da Telegram. Scrivi una classe/prof/aula e il bot risponde con la lezione corrente oppure l'orario del giorno.

## Requisiti
- Python 3.11+ (testato su Windows)
- Token di un bot Telegram (`BOT_TOKEN`)
- URL della pagina indice dell'orario (`URL_INDICE`)

## Installazione rapida
```bash
cd bot-Telgram-per-la-scuola
python -m venv .venv
.venv\Scripts\Activate      # su PowerShell
pip install -r requirements.txt
```

## Variabili d'ambiente
Impostare prima di avviare:
```bash
set BOT_TOKEN=il_tuo_token
set URL_INDICE=https://esempio.it/orario/Index.html
```

## Avvio
```bash
cd bot-Telgram-per-la-scuola
.venv\Scripts\Activate
python orario_beta_cli.py
```
Il bot parte in polling e logga su stdout.

## Note
- La cache dell'indice dura 6 ore; regola con `secondi_cache` in `orario_bot/config.py` se serve.
- In caso di errori lato scraping vengono loggati i dettagli, mentre all'utente arriva un messaggio generico.
