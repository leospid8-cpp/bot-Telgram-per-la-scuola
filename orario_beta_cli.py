import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL_INDICE = "**********"
HEADER = {"User-Agent": "Mozilla/5.0 (OrarioCLI/1.0)"}

GIORNI = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB"]
MAPPA_GIORNI = {
    "lun": "LUN", "lunedi": "LUN", "lunedì": "LUN",
    "mar": "MAR", "martedi": "MAR", "martedì": "MAR",
    "mer": "MER", "mercoledi": "MER", "mercoledì": "MER",
    "gio": "GIO", "giovedi": "GIO", "giovedì": "GIO",
    "ven": "VEN", "venerdi": "VEN", "venerdì": "VEN",
    "sab": "SAB", "sabato": "SAB",
}

def pulisci(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()

def scarica_html(url: str) -> BeautifulSoup:
    #scarico la pagina dal sito
    r = requests.get(url, headers=HEADER, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def crea_indice():
    #costruisco l'elenco di classi/docenti/aule partendo dall'indice
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

def scegli_url(elenco: dict, chiave: str):
    #seleziono la voce giusta (anche con ricerca parziale)
    chiave = chiave.upper().strip()
    if chiave in elenco:
        return elenco[chiave]

    trovati = sorted([k for k in elenco if chiave in k])
    if len(trovati) == 1:
        return elenco[trovati[0]]

    if len(trovati) > 1:
        print("\nHo trovato più risultati:")
        for i, k in enumerate(trovati, 1):
            print(f"  {i}) {k}")
        s = input("Scegli numero: ").strip()
        if s.isdigit() and 1 <= int(s) <= len(trovati):
            return elenco[trovati[int(s) - 1]]

    return None

def leggi_cella(td):
    testi = [pulisci(p.get_text(" ", strip=True)) for p in td.find_all("p")]
    testi = [t for t in testi if t and t != "\xa0"]

    classi, prof, aule = [], [], []
    for a in td.find_all("a", href=True):
        txt = pulisci(a.get_text(" ", strip=True)).upper()
        href = a["href"]
        if "Classi/" in href: classi.append(txt)
        elif "Docenti/" in href: prof.append(txt)
        elif "Aule/" in href: aule.append(txt)

    return {
        "testo": testi,
        "classi": sorted(set(classi)),
        "prof": sorted(set(prof)),
        "aule": sorted(set(aule)),
    }

def carica_orario(url: str):
    #leggo la tabella e gestisco anche le celle doppie (rowspan)
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

def stampa_slot(orari, griglia, giorno, ora):
    inizio = orari[ora - 1] if 1 <= ora <= len(orari) else "?"
    slot = griglia.get((giorno, ora))
    print(f"\n{giorno} ora {ora} (inizio {inizio})")

    if not slot or (not slot["testo"] and not slot["prof"] and not slot["aule"] and not slot["classi"]):
        print("  — libero / vuoto —")
        return

    if slot["aule"]:   print("  Aula  :", ", ".join(slot["aule"]))
    if slot["prof"]:   print("  Prof  :", ", ".join(slot["prof"]))
    if slot["classi"]: print("  Classe:", ", ".join(slot["classi"]))
    if slot["testo"]:  print("  Info  :", " | ".join(slot["testo"]))

def main():
    print("Scarico l'indice dal sito...")
    indice = crea_indice()
    print(f"Ok. Classi={len(indice['classe'])}  Prof={len(indice['prof'])}  Aule={len(indice['aula'])}")

    categoria = input("\nCategoria (classe/prof/aula): ").strip().lower()
    if categoria not in ("classe", "prof", "aula"):
        print("Categoria non valida.")
        return

    nome = input(f"Nome {categoria} (es 4F, ROSSI, AULA 69): ").strip()
    url = scegli_url(indice[categoria], nome)
    if not url:
        print("Non trovato. Scrivi un nome più simile a quello sul sito.")
        return

    print("Scarico l'orario selezionato...")
    orari, griglia = carica_orario(url)

    g = input("Giorno (lun/mar/mer/gio/ven/sab): ").strip().lower()
    giorno = MAPPA_GIORNI.get(g, g.upper())
    if giorno not in GIORNI:
        print("Giorno non valido.")
        return

    s_ora = input("Ora (numero, es 4): ").strip()
    if not s_ora.isdigit():
        print("Ora non valida.")
        return

    stampa_slot(orari, griglia, giorno, int(s_ora))

if __name__ == "__main__":
    main()
