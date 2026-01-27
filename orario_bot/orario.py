import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

# user agent dedicato per evitare blocchi banali lato server
HEADER = {"User-Agent": "Mozilla/5.0 (OrarioBot/1.0)"}
# sigle dei giorni usate nelle chiavi della griglia
GIORNI = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB"]
# fuso orario coerente con l'orario scolastico
TZ = ZoneInfo("Europe/Rome")


def pulisci(t: str) -> str:
    # compatta spazi e trimma
    return re.sub(r"\s+", " ", t).strip()


def scarica_html(url: str) -> BeautifulSoup:
    # richiede la pagina con timeout per evitare attese infinite
    r = requests.get(url, headers=HEADER, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


# tiene in memoria indice e timestamp per invalidare la cache
@dataclass
class CacheIndice:
    ts: float | None = None
    data: dict | None = None


class ServizioOrario:
    # incapsula cache, download e parsing dell'orario
    """Scarica, cachea e formatta l'orario."""

    def __init__(self, url_indice: str, secondi_cache: int = 6 * 60 * 60):
        # url_indice: pagina con i link a tutte le tabelle (classi, docenti, aule)
        # secondi_cache: durata della cache dell'indice in memoria
        self.url_indice = url_indice
        self.secondi_cache = secondi_cache
        self._cache = CacheIndice()

    def crea_indice(self) -> dict:
        # scarica la pagina indice e costruisce tre dizionari separati
        # per classi, docenti e aule con url alle rispettive tabelle
        pagina = scarica_html(self.url_indice)
        indice = {"classe": {}, "prof": {}, "aula": {}}

        for link in pagina.select("a[href]"):
            href = link.get("href", "")
            nome = pulisci(link.get_text(" ", strip=True)).upper()
            if not nome:
                continue
            url = urljoin(self.url_indice, href)

            if "Classi/" in href:
                indice["classe"][nome] = url
            elif "Docenti/" in href:
                indice["prof"][nome] = url
            elif "Aule/" in href:
                indice["aula"][nome] = url

        return indice

    def ottieni_indice(self) -> dict:
        # usa la cache se non è troppo vecchia, altrimenti rigenera l'indice
        now = datetime.now(TZ).timestamp()
        if (
            self._cache.data
            and self._cache.ts
            and (now - self._cache.ts < self.secondi_cache)
        ):
            return self._cache.data

        indice = self.crea_indice()
        self._cache.data = indice
        self._cache.ts = now
        return indice

    def leggi_cella(self, td) -> dict:
        # estrae le informazioni da una singola cella della tabella oraria
        # restituisce liste di classi, prof, aule e testo libero presenti
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

    def carica_orario(self, url: str) -> Tuple[List[str], Dict[Tuple[str, int], dict]]:
        # converte la tabella html in due strutture:
        # orari come lista delle ore di inizio
        # griglia come dizionario con chiave (giorno, numero_ora)
        # gestisce le celle con rowspan usando il vettore trascina
        pagina = scarica_html(url)
        tabella = pagina.find("table", attrs={"border": "2"}) or pagina.find("table")
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

                slot = self.leggi_cella(cella)
                griglia[(giorno, ora)] = slot

                rs = cella.get("rowspan")
                span = int(rs) if rs and rs.isdigit() else 1
                trascina[gi] = (span - 1, slot) if span > 1 else (0, None)

        return orari, griglia

    def categoriaricerca(self, nome: str, indice: dict) -> str:
        # cerca prima un match esatto, poi un match parziale; default su classe
        nome = nome.upper().strip()
        # match esatto
        for categoria in ("classe", "prof", "aula"):
            if nome in indice[categoria]:
                return categoria
        # fallback: substring
        for categoria in ("classe", "prof", "aula"):
            for chiave in indice[categoria]:
                if nome in chiave:
                    return categoria
        return "classe"

    def scegli_url(self, elenco: dict, chiave: str):
        # ritorna l'url se la chiave corrisponde, altrimenti una lista di possibili match
        chiave = chiave.upper().strip()
        if chiave in elenco:
            return elenco[chiave]

        trovati = sorted([k for k in elenco if chiave in k])
        if len(trovati) == 1:
            return elenco[trovati[0]]

        return None, trovati


def giorno_oggi_sigla() -> str | None:
    # restituisce la sigla del giorno corrente o none di domenica
    i = datetime.now(TZ).weekday()
    # 0=lun ... 5=sab ... 6=dom
    if i >= 6:
        return None
    return GIORNI[i]


def ora_corrente_numero() -> int | None:
    # mappa l'orario locale al numero dell'ora scolastica
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
    # compone il messaggio per una singola ora
    inizio = orari[ora - 1] if 1 <= ora <= len(orari) else "?"
    slot = griglia.get((giorno, ora))

    titolo = f"{giorno} - ora {ora} (inizio {inizio})"

    if slot_vuoto(slot):
        return titolo + "\n- libero / vuoto -"

    righe = [titolo]
    if slot["aule"]:
        righe.append("Aula: " + ", ".join(slot["aule"]))
    if slot["prof"]:
        righe.append("Prof: " + ", ".join(slot["prof"]))
    if slot["classi"]:
        righe.append("Classe: " + ", ".join(slot["classi"]))

    return "\n".join(righe)


def formatta_giorno(orari, griglia, giorno):
    # compone il messaggio per l'intera giornata
    righe = [f"{giorno} - orario giornaliero"]
    for ora, inizio in enumerate(orari, start=1):
        slot = griglia.get((giorno, ora))
        if slot_vuoto(slot):
            righe.append(f"{ora}. {inizio} - libero / vuoto")
            continue

        dettagli = []
        if slot["aule"]:
            dettagli.append("Aula: " + ", ".join(slot["aule"]))
        if slot["prof"]:
            dettagli.append("Prof: " + ", ".join(slot["prof"]))
        if slot["classi"]:
            dettagli.append("Classe: " + ", ".join(slot["classi"]))

        righe.append(f"{ora}. {inizio} - " + " | ".join(dettagli))

    return "\n".join(righe)


def slot_vuoto(slot: dict | None) -> bool:
    # considera vuoto se non esiste o non ha testo/prof/aule/classi
    return not slot or (not slot["testo"] and not slot["prof"] and not slot["aule"] and not slot["classi"])
