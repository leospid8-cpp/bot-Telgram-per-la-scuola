import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
URL_INDICE = os.environ.get("URL_INDICE")


HEADER = {"User-Agent": "Mozilla/5.0 (OrarioBot/1.0)"}

GIORNI = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB"]

# Cache in memoria per non riscaricare l'indice ogni volta
CACHE_INDICE = {"ts": None, "data": None}
TZ = ZoneInfo("Europe/Rome")


def pulisci(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()

def scarica_html(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADER, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")
def scarica_bytes(url: str) -> bytes:
    r = requests.get(url, headers=HEADER, timeout=25)
    r.raise_for_status()
    return r.content

def crea_indice():
    pagina = scarica_html(URL_INDICE)
    indice = {"classe": {}, "prof": {}, "aula": {}}

    for link in pagina.select("a[href]"):
        href = link.get("href", "")
        nome = pulisci(link.get_text(" ", strip=True)).upper()
        if not nome:
            continue
        url = urljoin(URL_INDICE, href)

        if "Classi/" in href:
            indice["classe"][nome] = url
        elif "Docenti/" in href:
            indice["prof"][nome] = url
        elif "Aule/" in href:
            indice["aula"][nome] = url

    return indice

def get_indice_cached(max_age_seconds=6 * 60 * 60):
    now = datetime.now(TZ).timestamp()
    if CACHE_INDICE["data"] and CACHE_INDICE["ts"] and (now - CACHE_INDICE["ts"] < max_age_seconds):
        return CACHE_INDICE["data"]

    indice = crea_indice()
    CACHE_INDICE["data"] = indice
    CACHE_INDICE["ts"] = now
    return indice

def categoriaricerca(nome: str, indice: dict) -> str:
    nome = nome.upper().strip()
    for categoria in ("classe", "prof", "aula"):
        for chiave in indice[categoria]:
            if nome in chiave:
                return categoria
            
    return "classe"

def scegli_url(elenco: dict, chiave: str):
    chiave = chiave.upper().strip()
    if chiave in elenco:
        return elenco[chiave]

    trovati = sorted([k for k in elenco if chiave in k])
    if len(trovati) == 1:
        return elenco[trovati[0]]

    # su Telegram non facciamo menu interattivo: se ci sono più risultati, li elenchiamo
    return None, trovati

def trova_immagine_orario(url: str) -> str | None:
    pagina = scarica_html(url)
    imgs = pagina.find_all("img", src=True)
    if not imgs:
        return None

    # preferisci immagini che sembrano un orario
    def punteggio(img):
        src = img.get("src", "").lower()
        alt = (img.get("alt") or "").lower()
        score = 0
        if "orario" in src or "orario" in alt:
            score += 2
        if "timetable" in src or "timetable" in alt:
            score += 1
        if src.endswith((".png", ".jpg", ".jpeg", ".webp")):
            score += 1
        return score

    imgs_sorted = sorted(imgs, key=punteggio, reverse=True)
    best = imgs_sorted[0]
    return urljoin(url, best["src"])

async def testo_libero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = (update.message.text or "").strip()
    if not testo:
        return

    # opzionale: ignora messaggi troppo lunghi
    if len(testo) > 60:
        await update.message.reply_text("Scrivi solo classe/prof/aula, es: 4F oppure ROSSI oppure AULA 69.")
        return

    # Se la prima parola è "orario", invia l'immagine settimanale
    if testo.lower().startswith("orario"):
        nome = testo[6:].strip()  # tutto dopo "orario"
        if not nome:
            await update.message.reply_text("Scrivi: orario <classe|prof|aula>")
            return

        try:
            indice = get_indice_cached()
            categoria = categoriaricerca(nome, indice)
            res = scegli_url(indice[categoria], nome)
            if isinstance(res, tuple):
                url, trovati = res
            else:
                url, trovati = res, []

            if not url:
                if trovati:
                    await update.message.reply_text(
                        "Ho trovato più risultati, sii più preciso:\n" + "\n".join(trovati[:30])
                    )
                else:
                    await update.message.reply_text("Non trovato. Scrivi un nome più simile a quello sul sito.")
                return

            img_url = trova_immagine_orario(url)
            if not img_url:
                await update.message.reply_text("Immagine orario non trovata in quella pagina.")
                return

            img_bytes = scarica_bytes(img_url)
            bio = io.BytesIO(img_bytes)
            bio.name = "orario.jpg"
            await update.message.reply_photo(photo=bio)
            return
        except Exception as e:
            await update.message.reply_text(f"Errore: {e}")
            return

    nome = testo  # qui la "chiave" è direttamente il messaggio

    giorno = giorno_oggi_sigla()
    if giorno is None:
        await update.message.reply_text("Oggi è domenica: non c’è orario.")
        return

    ora = ora_corrente_numero()
    if ora is None:
        await update.message.reply_text("Fuori fascia orario lezioni (07:00–13:25).")
        return

    try:
        indice = get_indice_cached()
        categoria = categoriaricerca(nome, indice)

        res = scegli_url(indice[categoria], nome)

        # nel tuo codice scegli_url può restituire (None, trovati)
        if isinstance(res, tuple):
            url, trovati = res
        else:
            url, trovati = res, []

        if not url:
            if trovati:
                await update.message.reply_text(
                    "Ho trovato più risultati, sii più preciso:\n" + "\n".join(trovati[:30])
                )
            else:
                await update.message.reply_text("Non trovato. Scrivi un nome più simile a quello sul sito.")
            return

        orari, griglia = carica_orario(url)
        msg = formatta_slot(orari, griglia, giorno, ora)
        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"Errore: {e}")


def leggi_cella(td):
    testi = [pulisci(p.get_text(" ", strip=True)) for p in td.find_all("p")]
    testi = [t for t in testi if t and t != "\xa0"]

    classi, prof, aule = [], [], []
    for a in td.find_all("a", href=True):
        txt = pulisci(a.get_text(" ", strip=True)).upper()
        href = a["href"]
        if "Classi/" in href:
            classi.append(txt)
        elif "Docenti/" in href:
            prof.append(txt)
        elif "Aule/" in href:
            aule.append(txt)

    return {
        "testo": testi,
        "classi": sorted(set(classi)),
        "prof": sorted(set(prof)),
        "aule": sorted(set(aule)),
    }

def carica_orario(url: str):
    pagina = scarica_html(url)
    tabella = pagina.find("table", attrs={"border": "2"})
    if not tabella:
        raise RuntimeError("Tabella orario non trovata.")

    righe = tabella.find_all("tr")
    orari, griglia = [], {}
    trascina = [(0, None) for _ in GIORNI]

    ora = 0
    for r in righe[1:]:
        celle = r.find_all("td")
        if not celle:
            continue

        inizio = pulisci(celle[0].get_text(" ", strip=True))
        if not inizio:
            continue

        ora += 1
        orari.append(inizio)

        celle_giorni = celle[1:]
        i = 0
        for gi, giorno in enumerate(GIORNI):
            restanti, precedente = trascina[gi]
            if restanti > 0 and precedente is not None:
                griglia[(giorno, ora)] = precedente
                trascina[gi] = (restanti - 1, precedente)
                continue

            cella = celle_giorni[i] if i < len(celle_giorni) else None
            if cella is not None:
                i += 1

            if cella is None:
                vuoto = {"testo": [], "classi": [], "prof": [], "aule": []}
                griglia[(giorno, ora)] = vuoto
                trascina[gi] = (0, None)
                continue

            slot = leggi_cella(cella)
            griglia[(giorno, ora)] = slot

            rs = cella.get("rowspan")
            span = int(rs) if rs and rs.isdigit() else 1
            trascina[gi] = (span - 1, slot) if span > 1 else (0, None)

    return orari, griglia

def giorno_oggi_sigla():
    i = datetime.now(TZ).weekday()
    # 0=Lun ... 5=Sab ... 6=Dom
    if i >= 6:
        return None
    return GIORNI[i]

def ora_corrente_numero():
    hhmm = datetime.now(TZ).strftime("%H:%M")
    if "07:00" <= hhmm < "08:50":
        return 1
    elif "08:50" <= hhmm < "09:45":
        return 2
    elif "09:45" <= hhmm < "10:40":
        return 3
    elif "10:40" <= hhmm < "11:35":
        return 4
    elif "11:35" <= hhmm < "12:30":
        return 5
    elif "12:30" <= hhmm < "13:25":
        return 6
    return None

def formatta_slot(orari, griglia, giorno, ora):
    inizio = orari[ora - 1] if 1 <= ora <= len(orari) else "?"
    slot = griglia.get((giorno, ora))

    titolo = f"{giorno} — ora {ora} (inizio {inizio})"

    if not slot or (not slot["testo"] and not slot["prof"] and not slot["aule"] and not slot["classi"]):
        return titolo + "\n— libero / vuoto —"

    righe = [titolo]
    if slot["aule"]:
        righe.append("Aula: " + ", ".join(slot["aule"]))
    if slot["prof"]:
        righe.append("Prof: " + ", ".join(slot["prof"]))
    if slot["classi"]:
        righe.append("Classe: " + ", ".join(slot["classi"]))

    return "\n".join(righe)

# =========================
# HANDLER TELEGRAM
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ciao! Sono il bot dell’orario.\n\n"
        "Usa:\n"
        "/oggi 4F\n"
        "/oggi ROSSI\n"
        "/oggi AULA 69\n\n"
        "Ti rispondo con la lezione dell’ora attuale."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandi:\n"
        "/oggi <classe|prof|aula>\n"
        "Esempi: /oggi 4F  — /oggi Burgio — /oggi AULA 69\n"
    )

async def oggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Scrivi così: /oggi 4F (oppure prof/aula)")
        return

    nome = " ".join(context.args).strip()

    giorno = giorno_oggi_sigla()
    if giorno is None:
        await update.message.reply_text("Oggi è domenica: non c’è orario.")
        return

    ora = ora_corrente_numero()
    if ora is None:
        await update.message.reply_text("Fuori fascia orario lezioni (07:00–13:25).")
        return

    try:
        indice = get_indice_cached()
        categoria = categoriaricerca(nome, indice)

        url = None
        trovati = []
        res = scegli_url(indice[categoria], nome)
        if isinstance(res, tuple):
            url, trovati = res
        else:
            url = res

        if not url:
            if trovati:
                await update.message.reply_text(
                    "Ho trovato più risultati, sii più preciso:\n" + "\n".join(trovati[:30])
                )
            else:
                await update.message.reply_text("Non trovato. Scrivi un nome più simile a quello sul sito.")
            return

        orari, griglia = carica_orario(url)
        msg = formatta_slot(orari, griglia, giorno, ora)
        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"Errore: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("oggi", oggi))

    print("BOT AVVIATO: sto ascoltando Telegram...")
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, testo_libero))

    app.run_polling()

if __name__ == "__main__":
    main()
