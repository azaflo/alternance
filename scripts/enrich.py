"""
Radar-Alternance — Pipeline d'enrichissement des contacts recruteurs
====================================================================
Pour chaque offre dans window.injectOffers('indeed', [...]) :
  1. Tente d'extraire le nom du recruteur depuis la page de l'offre
  2. Cherche le(s) responsable(s) LinkedIn via SerpApi (nom > département > fallback)
  3. Trouve leur email pro via Hunter.io (domain-search puis email-finder)
  4. Injecte les contacts dans index.html (champ hrContacts)
  5. Propage les contacts enrichis vers les entrées liées dans data.json

Secrets GitHub requis : HUNTER_API_KEY, SERPAPI_KEY
"""

import json
import os
import re
import time
import requests
import unicodedata
from urllib.parse import unquote

def remove_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

# ── Config ─────────────────────────────────────────────────────────────────
HUNTER_KEY   = os.getenv("HUNTER_API_KEY", "")
SERPER_KEY   = os.getenv("SERPER_API_KEY", "")
SERPAPI_KEY  = os.getenv("SERPAPI_KEY", "")
HTML_FILE    = "index.html"
DATA_FILE    = "data.json"
MAX_CONTACTS = 3      # profils LinkedIn max par offre
DELAY        = 0.8    # secondes entre appels API


# ══════════════════════════════════════════════════════════════════════════
# 1. LECTURE + PARSING DES OFFRES
# ══════════════════════════════════════════════════════════════════════════

DEPT_KEYWORDS = {
    "soc":            "analyste SOC",
    "cyber":          "responsable cybersécurité",
    "sécurité":       "responsable sécurité SI",
    "réseau":         "responsable réseaux",
    "infrastructure": "responsable infrastructure",
    "support":        "responsable support IT",
    "système":        "responsable systèmes",
    "cloud":          "architecte cloud",
    "dsi":            "DSI",
    "sûreté":         "responsable sûreté",
    "logiciel":       "responsable développement",
}


def _detect_department(title: str) -> str | None:
    t = title.lower()
    for kw, label in DEPT_KEYWORDS.items():
        if kw in t:
            return label
    return None


def parse_offers(html: str) -> list[dict]:
    """
    Extrait toutes les offres du bloc window.injectOffers('indeed', [...]).
    Robuste aux template literals backtick (coverLetter multi-lignes).
    """
    marker = "window.injectOffers('indeed',"
    start = html.find(marker)
    if start == -1:
        start = html.find('window.injectOffers("indeed",')
    if start == -1:
        return []

    # Tous les ids dans l'ordre d'apparition
    ids = re.findall(r"id:\s*['\"]([^'\"]+)['\"]", html[start:])

    offers = []
    for oid in ids:
        pos = html.find(f"id: '{oid}'", start)
        if pos == -1:
            pos = html.find(f'id: "{oid}"', start)
        if pos == -1:
            continue

        # Fenêtre de 800 chars pour champs courts
        window = html[pos: pos + 800]
        # Fenêtre élargie pour url/careerUrl (plus loin dans l'objet)
        window_large = html[pos: pos + 1600]

        def field(key: str, w: str = None) -> str | None:
            src = w if w is not None else window
            m = re.search(rf'{key}:\s*["\']([^"\']+)["\']', src)
            return m.group(1).strip() if m else None

        company        = field("company")
        title          = field("title")
        location       = field("location")
        url            = field("url",           window_large)
        career_url     = field("careerUrl",     window_large)
        recruiter_name = field("recruiterName", window_large)
        hr_email       = field("hrEmail",       window_large)

        # hrContacts : au moins un linkedin non vide dans le tableau
        has_hr_contacts = bool(re.search(r'hrContacts:\s*\[.*?linkedin:\s*"https?://[^"]+', window_large, re.DOTALL))

        if not company:
            continue

        # Ville depuis location  →  "Brunoy (91) · ~30 km"  →  "Brunoy"
        city = None
        if location:
            m = re.match(r"^([A-Za-zÀ-ÿ\- ]+)", location)
            if m:
                city = m.group(1).strip()

        offers.append({
            "id":              oid,
            "company":         company,
            "title":           title or "",
            "location":        location or "",
            "city":            city,
            "department":      _detect_department(title or ""),
            "url":             url,
            "career_url":      career_url,
            "recruiter_name":  recruiter_name,
            "hr_email":        hr_email,
            "has_hr_contacts": has_hr_contacts,
        })

    return offers


# ══════════════════════════════════════════════════════════════════════════
# 2. EXTRACTION DU RECRUTEUR DEPUIS LA PAGE DE L'OFFRE
# ══════════════════════════════════════════════════════════════════════════

# Capture les prénoms/noms composés : "Marie-Claire", "Le Guerneve", "De La Tour", etc.
_NAME = r"[A-ZÀ-Ÿ][a-zà-ÿ\-]+(?:\s+[A-ZÀ-Ÿa-zà-ÿ][a-zà-ÿ\-]+){1,3}"

RECRUITER_PATTERNS = [
    rf"Postulez auprès de\s*[:\-]?\s*({_NAME})",
    rf"Contact\s*[:\-]\s*({_NAME})",
    rf"Responsable\s+(?:RH|recrutement|du recrutement)\s*[:\-]?\s*({_NAME})",
    rf"Recruteur\s*[:\-]\s*({_NAME})",
    rf"Publié par\s*[:\-]?\s*({_NAME})",
    rf"Hiring Manager\s*[:\-]\s*({_NAME})",
]

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def fetch_recruiter_name(url: str | None) -> tuple[str | None, str | None]:
    """
    Télécharge la page de l'offre et tente d'extraire le nom du recruteur.
    Retourne (first_name, last_name) ou (None, None) si introuvable / erreur.
    """
    if not url:
        return None, None
    try:
        r = requests.get(url, headers=_FETCH_HEADERS, timeout=10)
        if not r.ok:
            return None, None
        text = r.text
        for pattern in RECRUITER_PATTERNS:
            m = re.search(pattern, text)
            if m:
                full = m.group(1).strip()
                parts = full.split()
                if len(parts) >= 2:
                    return parts[0], " ".join(parts[1:])
    except Exception:
        pass
    return None, None


# ══════════════════════════════════════════════════════════════════════════
# 3. RECHERCHE LINKEDIN VIA SERPAPI
# ══════════════════════════════════════════════════════════════════════════

def _clean_company(name: str) -> str:
    """Normalise un nom d'entreprise pour la requête Google."""
    name = re.split(r"[-–—/(|]", name)[0]
    junk = [
        "france", "groupe", "group", "sas", "sa", "sarl",
        "europe", "services", "solutions", "technologies",
    ]
    for w in junk:
        name = re.sub(rf"\b{w}\b", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()


def _build_queries(
    company: str,
    city: str | None,
    dept: str | None,
    recruiter_first: str | None = None,
    recruiter_last: str | None = None,
) -> list[str]:
    """
    Génère jusqu'à 4 requêtes Google du plus précis au plus large.
    Priorité : nom recruteur > département > manager IT/RH > fallback.
    """
    c = _clean_company(company)
    pool = []

    # Niveau 0 — Nom du recruteur explicite (le plus précis)
    if recruiter_first and recruiter_last:
        pool.append(
            f'site:linkedin.com/in/ "{recruiter_first} {recruiter_last}" "{c}"'
        )

    # Niveau 1 — département + ville + entreprise
    if dept and city:
        pool.append(
            f'site:linkedin.com/in/ "{dept}" "{c}" "{city}"'
        )

    # Niveau 2 — responsable IT/RH + ville  OU  département seul + IDF
    if city:
        pool.append(
            f'site:linkedin.com/in/ '
            f'("responsable IT" OR "DSI" OR "manager IT" OR "recrutement") '
            f'"{c}" "{city}"'
        )
    if dept:
        pool.append(
            f'site:linkedin.com/in/ "{dept}" "{c}" "Île-de-France"'
        )

    # Niveau 3 — fallback large
    pool.append(
        f'site:linkedin.com/in/ '
        f'("RH" OR "recrutement" OR "DSI" OR "IT") '
        f'"{c}" "Île-de-France"'
    )

    seen, unique = set(), []
    for q in pool:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def _search_profiles(query: str, count: int) -> list[str]:
    """
    Exécute une requête Google et retourne les URLs LinkedIn trouvées.
    Utilise Serper.dev en priorité, SerpApi en fallback.
    """
    if SERPER_KEY:
        try:
            r = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
                json={"q": query, "gl": "fr", "hl": "fr", "num": count},
                timeout=15,
            )
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, dict):
                print(f"  ✗  Serper : réponse inattendue ({type(payload).__name__}) : {str(payload)[:120]}")
                return []
            results = payload.get("organic", [])
            profiles = []
            seen = set()
            for res in results:
                url = res.get("link", "")
                if "linkedin.com/in/" in url and url not in seen:
                    seen.add(url)
                    profiles.append(url)
            return profiles
        except Exception as e:
            print(f"  ✗  Serper : {e}")

    if SERPAPI_KEY:
        try:
            r = requests.get(
                "https://serpapi.com/search",
                params={"engine": "google", "q": query, "api_key": SERPAPI_KEY,
                        "num": count, "gl": "fr", "hl": "fr"},
                timeout=15,
            )
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, dict):
                print(f"  ✗  SerpApi : réponse inattendue ({type(payload).__name__}) : {str(payload)[:120]}")
                return []
            results = payload.get("organic_results", [])
            profiles = []
            seen = set()
            for res in results:
                url = res.get("link", "")
                if "linkedin.com/in/" in url and url not in seen:
                    seen.add(url)
                    profiles.append(url)
            return profiles
        except Exception as e:
            print(f"  ✗  SerpApi : {e}")

    return []


def find_linkedin_profiles(
    company: str,
    city: str | None,
    dept: str | None,
    recruiter_first: str | None = None,
    recruiter_last: str | None = None,
) -> list[str]:
    """
    Retourne jusqu'à MAX_CONTACTS URLs LinkedIn.
    Essaie chaque requête en cascade et s'arrête au premier succès.
    """
    if not SERPER_KEY and not SERPAPI_KEY:
        print("  ⚠  Aucune clé de recherche (SERPER_API_KEY ou SERPAPI_KEY)")
        return []

    queries = _build_queries(company, city, dept, recruiter_first, recruiter_last)
    labels  = ["recruteur", "précis", "intermédiaire", "large"]

    for i, query in enumerate(queries):
        label = labels[i] if i < len(labels) else "large"
        print(f"  🔍 [{label}] {query[:85]}...")

        profiles = _search_profiles(query, MAX_CONTACTS + 2)
        if profiles:
            print(f"  ✔  {len(profiles)} profil(s) trouvé(s)")
            return profiles[:MAX_CONTACTS]

        time.sleep(DELAY)

    print("  ✗  Aucun profil LinkedIn trouvé")
    return []


# ══════════════════════════════════════════════════════════════════════════
# 4. RÉSOLUTION EMAIL VIA HUNTER.IO
# ══════════════════════════════════════════════════════════════════════════

def _domain_matches_company(domain: str, company: str) -> bool:
    """
    Vérifie que le domaine retourné par Hunter correspond bien à l'entreprise.
    Évite les faux positifs (ex: Hunter renvoie elior.fr pour Carrefour).

    Stratégie : au moins UN mot significatif du nom de l'entreprise
    doit apparaître dans le domaine (après normalisation).
    """
    def norm(s: str) -> str:
        s = s.lower()
        for a, b in [("é","e"),("è","e"),("ê","e"),("à","a"),("â","a"),("ô","o"),("û","u"),("î","i")]:
            s = s.replace(a, b)
        return s

    domain_n  = norm(domain)
    company_n = norm(company)

    stopwords = {"group", "groupe", "france", "services", "solutions",
                 "technologies", "federation", "nationale", "internationale"}
    words = [
        w for w in re.split(r"[\s\-–_/|]", company_n)
        if len(w) >= 4 and w not in stopwords
    ]

    if not words:
        return True   # pas de mots discriminants → on ne bloque pas

    matched = any(w in domain_n for w in words)
    if not matched:
        print(f"     ⚠  Domaine rejeté : '{domain}' ne correspond pas à '{company}'")
    return matched


def _find_domain(company: str) -> str | None:
    """
    Hunter.io /domain-search?company=...
    Retourne le domaine email uniquement s'il correspond vraiment à l'entreprise.
    """
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"company": company, "api_key": HUNTER_KEY},
            timeout=10,
        )
        payload = r.json()
        if not isinstance(payload, dict):
            print(f"     ✗  Hunter domain-search : réponse inattendue ({type(payload).__name__}) : {str(payload)[:120]}")
            return None
        domain = payload.get("data", {}).get("domain")
        if domain:
            if _domain_matches_company(domain, company):
                print(f"     🌐 Domaine : {domain}")
                return domain
            return None
    except Exception as e:
        print(f"     ✗  Hunter domain-search : {e}")
    return None


def _find_email(first: str, last: str, domain: str) -> str | None:
    """
    Hunter.io /email-finder — ne retourne l'email que si score >= 50.
    """
    try:
        r = requests.get(
            "https://api.hunter.io/v2/email-finder",
            params={
                "domain":     domain,
                "first_name": first,
                "last_name":  last,
                "api_key":    HUNTER_KEY,
            },
            timeout=10,
        )
        payload = r.json()
        if not isinstance(payload, dict):
            print(f"     ✗  Hunter email-finder : réponse inattendue ({type(payload).__name__}) : {str(payload)[:120]}")
            return None
        data  = payload.get("data", {})
        email = data.get("email")
        score = data.get("score", 0)
        if email and score >= 50:
            return email
    except Exception as e:
        print(f"     ✗  Hunter email-finder : {e}")
    return None


def resolve_email(first: str, last: str, company: str) -> str | None:
    """Point d'entrée : domaine → email."""
    if not HUNTER_KEY:
        return None
    domain = _find_domain(company)
    if not domain:
        return None
    return _find_email(first, last, domain)


def name_from_linkedin_url(url: str):
    try:
        slug = url.rstrip("/").split("/in/")[-1]
        slug = unquote(slug)
        slug = re.sub(r"-[a-z0-9]{4,}$", "", slug)
        parts = [p for p in slug.split("-") if p and not p.isdigit()]
        if len(parts) >= 2:
            return parts[0].capitalize(), parts[1].capitalize()
    except Exception:
        pass
    return None, None


# ══════════════════════════════════════════════════════════════════════════
# 5. INJECTION DANS INDEX.HTML
# ══════════════════════════════════════════════════════════════════════════

def _replace_or_insert_field(html: str, id_pos: int, field_name: str, field_value: str) -> str:
    """
    Dans la zone de l offre (à partir de id_pos) :
    - Remplace le champ s il existe déjà
    - Sinon l insère avant logo:
    """
    zone = html[id_pos: id_pos + 900]
    existing = re.search(rf"{field_name}:\s*['\"]?[^,\n]*['\"]?,?", zone)
    if existing:
        abs_s = id_pos + existing.start()
        abs_e = id_pos + existing.end()
        return html[:abs_s] + f"{field_name}: {field_value}," + html[abs_e:]
    logo_m = re.search(r"\n(\s*)logo:", zone)
    if logo_m:
        insert_at = id_pos + logo_m.start()
        indent    = logo_m.group(1)
        return html[:insert_at] + f"\n{indent}{field_name}: {field_value}," + html[insert_at:]
    print(f"  ⚠  Impossible d inserer '{field_name}' pour cette offre")
    return html


def inject_contacts(html: str, offer_id: str, contacts: list[dict]) -> str:
    """
    - hrEmail     ← email du 1er contact (pour mailto, badge vert)
    - hrContacts  ← TOUS les contacts avec name + email + linkedin
    """
    if not contacts:
        return html

    m = re.search(rf"id:\s*['\"]({re.escape(offer_id)})['\"]", html)
    if not m:
        print(f"  ⚠  id '{offer_id}' introuvable, injection ignorée")
        return html

    id_pos = m.start()

    # hrEmail ← email du 1er contact (pour mailto)
    first_email = contacts[0]["email"]
    html = _replace_or_insert_field(html, id_pos, "hrEmail", f'"{first_email}"')

    # hrContacts ← tous les contacts (LinkedIn conservé pour chacun)
    m2 = re.search(rf"id:\s*['\"]({re.escape(offer_id)})['\"]", html)
    if m2:
        id_pos = m2.start()
        items_js = ", ".join(
            f'{{name: "{c["name"]}", email: "{c["email"]}", linkedin: "{c.get("linkedin", "")}"}}'
            for c in contacts
        )
        new_hrc = f'hrContacts: [{items_js}]'
        zone = html[id_pos: id_pos + 950]
        existing_hrc = re.search(r"hrContacts:\s*\[.*?\]", zone, re.DOTALL)
        if existing_hrc:
            abs_s = id_pos + existing_hrc.start()
            abs_e = id_pos + existing_hrc.end()
            html  = html[:abs_s] + new_hrc + html[abs_e:]
        else:
            logo_m = re.search(r"\n(\s*)logo:", zone)
            if logo_m:
                insert_at = id_pos + logo_m.start()
                indent    = logo_m.group(1)
                html = html[:insert_at] + f"\n{indent}{new_hrc}," + html[insert_at:]
    return html


# ══════════════════════════════════════════════════════════════════════════
# 6. PROPAGATION VERS DATA.JSON (candidatures envoyées)
# ══════════════════════════════════════════════════════════════════════════

def sync_data_json(offer_contacts: dict[str, list[dict]]) -> None:
    """
    Met à jour les entrées de data.json dont le champ offerId correspond
    à une offre qui vient d'être enrichie.

    offer_contacts : { offer_id: [{"name": ..., "email": ..., "linkedin": ...}, ...] }
    """
    if not offer_contacts:
        return
    if not os.path.exists(DATA_FILE):
        print(f"  ℹ  {DATA_FILE} absent, propagation ignorée")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"  ✗  Lecture data.json : {e}")
        return

    # data.json peut être un tableau simple (ancien format) ou {entries, deleted}
    entries = raw.get("entries", raw) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        print(f"  ✗  Format data.json inattendu : {type(entries).__name__}")
        return

    updated = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        offer_id = entry.get("offerId")
        if not offer_id or offer_id not in offer_contacts:
            continue

        contacts = offer_contacts[offer_id]
        if not contacts:
            continue

        # Mise à jour des contacts (même logique qu'inject_contacts)
        first_contact = contacts[0]
        if first_contact.get("email"):
            entry["hrEmail"] = first_contact["email"]

        extra = [
            {"name": c["name"], "email": c["email"], "linkedin": c.get("linkedin", "")}
            for c in contacts[1:]
        ]
        if extra:
            entry["hrContacts"] = extra

        updated += 1

    if updated == 0:
        print(f"  ℹ  Aucune candidature liée dans {DATA_FILE}")
        return

    try:
        # Réécrire en conservant le format d'origine
        output = raw if isinstance(raw, list) else {**raw, "entries": entries}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  ✅ {updated} candidature(s) mise(s) à jour dans {DATA_FILE}")
    except Exception as e:
        print(f"  ✗  Écriture data.json : {e}")


# ══════════════════════════════════════════════════════════════════════════
# 7. PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

def run():
    SEP = "─" * 58
    print(SEP)
    print("  Radar-Alternance · Pipeline contacts recruteurs")
    print(SEP)

    if not os.path.exists(HTML_FILE):
        print(f"✗ Fichier '{HTML_FILE}' introuvable.")
        return

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    offers = parse_offers(html)
    if not offers:
        print("✗ Aucune offre dans window.injectOffers().")
        return

    print(f"\n📋 {len(offers)} offre(s) détectée(s)\n")
    enriched = 0
    offer_contacts: dict[str, list[dict]] = {}  # pour sync data.json

    for offer in offers:
        oid  = offer["id"]
        comp = offer["company"]
        city = offer["city"]
        dept = offer["department"]

        print(f"▶ {comp}  [{oid}]")
        print(f"  📍 {city or '?'}  |  🗂  {dept or 'service non détecté'}")

        # Skip si hrEmail non vide OU au moins un linkedin non vide dans hrContacts
        if offer.get("hr_email") or offer.get("has_hr_contacts"):
            print(f"  ⏭  Déjà enrichi (email ou LinkedIn présent), skip\n")
            continue

        # Étape A — Nom du recruteur : champ manuel > scraping de la page
        manual_name = offer.get("recruiter_name")
        if manual_name:
            parts = manual_name.strip().split(" ", 1)
            rec_first = parts[0]
            rec_last  = parts[1] if len(parts) > 1 else ""
            print(f"  👤 Recruteur (manuel) : {rec_first} {rec_last}")
        else:
            rec_first, rec_last = fetch_recruiter_name(offer.get("url"))
            if rec_first and rec_last:
                print(f"  👤 Recruteur détecté : {rec_first} {rec_last}")
            else:
                print("  👤 Recruteur non détecté, recherche générique")

        # Étape B — LinkedIn
        profiles = find_linkedin_profiles(comp, city, dept, rec_first, rec_last)
        if not profiles:
            print()
            continue

        # Étape C — Hunter.io pour chaque profil
        contacts = []
        for url in profiles:
            # Si le recruteur a été trouvé et c'est la 1ère URL, utiliser son nom exact
            if rec_first and rec_last and url == profiles[0]:
                first, last = rec_first, rec_last
            else:
                first, last = name_from_linkedin_url(url)

            if not (first and last):
                print(f"  ✗  Nom non extractible depuis : {url}")
                continue

            print(f"  👤 {first} {last}...")
            email = resolve_email(first, last, comp)

            if email:
                print(f"  ✉  {email}")
                contacts.append({"name": remove_accents(f"{first} {last}"), "email": email, "linkedin": url})
            else:
                print(f"  ✗  {first} {last} — pas d'email")
                contacts.append({"name": remove_accents(f"{first} {last}"), "email": "", "linkedin": url})

            time.sleep(DELAY)

        # Étape D — Injection dans index.html
        if contacts:
            html = inject_contacts(html, oid, contacts)
            print(f"  ✅ {len(contacts)} contact(s) injecté(s) dans index.html")
            enriched += 1
            offer_contacts[oid] = contacts

        print()

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    # Étape E — Propagation vers les candidatures envoyées (data.json)
    print("── Propagation vers les candidatures ──────────────────────")
    sync_data_json(offer_contacts)

    print(SEP)
    print(f"  ✅ {enriched}/{len(offers)} offre(s) enrichie(s)  —  index.html mis à jour")
    print(SEP)


if __name__ == "__main__":
    run()
