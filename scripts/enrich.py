"""
Radar-Alternance — Pipeline d'enrichissement des contacts recruteurs
====================================================================
Pour chaque offre dans window.injectOffers('indeed', [...]) :
  1. Cherche le(s) responsable(s) LinkedIn via SerpApi (ville + service)
  2. Trouve leur email pro via Hunter.io (domain-search puis email-finder)
  3. Injecte les contacts dans index.html (champ hrContacts)

Secrets GitHub requis : HUNTER_API_KEY, SERPAPI_KEY
"""

import os
import re
import time
import requests

# ── Config ─────────────────────────────────────────────────────────────────
HUNTER_KEY   = os.getenv("HUNTER_API_KEY", "")
SERPAPI_KEY  = os.getenv("SERPAPI_KEY", "")
HTML_FILE    = "index.html"
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

        # Fenêtre de 800 chars : couvre tous les champs sauf coverLetter
        window = html[pos: pos + 800]

        def field(key: str) -> str | None:
            m = re.search(rf'{key}:\s*["\']([^"\']+)["\']', window)
            return m.group(1).strip() if m else None

        company  = field("company")
        title    = field("title")
        location = field("location")

        if not company:
            continue

        # Ville depuis location  →  "Brunoy (91) · ~30 km"  →  "Brunoy"
        city = None
        if location:
            m = re.match(r"^([A-Za-zÀ-ÿ\- ]+)", location)
            if m:
                city = m.group(1).strip()

        offers.append({
            "id":         oid,
            "company":    company,
            "title":      title or "",
            "location":   location or "",
            "city":       city,
            "department": _detect_department(title or ""),
        })

    return offers


# ══════════════════════════════════════════════════════════════════════════
# 2. RECHERCHE LINKEDIN VIA SERPAPI
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


def _build_queries(company: str, city: str | None, dept: str | None) -> list[str]:
    """
    Génère jusqu'à 3 requêtes Google du plus précis au plus large.
    On retire les doublons en conservant l'ordre.
    """
    c = _clean_company(company)
    pool = []

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


def find_linkedin_profiles(company: str, city: str | None, dept: str | None) -> list[str]:
    """
    Retourne jusqu'à MAX_CONTACTS URLs LinkedIn.
    Essaie chaque requête en cascade et s'arrête au premier succès.
    """
    if not SERPAPI_KEY:
        print("  ⚠  SERPAPI_KEY manquante")
        return []

    queries = _build_queries(company, city, dept)
    labels  = ["précis", "intermédiaire", "large"]

    for i, query in enumerate(queries):
        label = labels[i] if i < len(labels) else "large"
        print(f"  🔍 [{label}] {query[:85]}...")

        params = {
            "engine":  "google",
            "q":       query,
            "api_key": SERPAPI_KEY,
            "num":     MAX_CONTACTS + 2,
            "gl":      "fr",
            "hl":      "fr",
        }

        try:
            r = requests.get("https://serpapi.com/search", params=params, timeout=15)
            r.raise_for_status()
            results = r.json().get("organic_results", [])

            profiles = []
            seen = set()
            for res in results:
                url = res.get("link", "")
                if "linkedin.com/in/" in url and url not in seen:
                    seen.add(url)
                    profiles.append(url)

            if profiles:
                print(f"  ✔  {len(profiles)} profil(s) trouvé(s)")
                return profiles[:MAX_CONTACTS]

        except Exception as e:
            print(f"  ✗  SerpApi : {e}")

        time.sleep(DELAY)

    print("  ✗  Aucun profil LinkedIn trouvé")
    return []


# ══════════════════════════════════════════════════════════════════════════
# 3. RÉSOLUTION EMAIL VIA HUNTER.IO
# ══════════════════════════════════════════════════════════════════════════

def _domain_matches_company(domain: str, company: str) -> bool:
    """
    Vérifie que le domaine retourné par Hunter correspond bien à l'entreprise.
    Évite les faux positifs (ex: Hunter renvoie elior.fr pour Carrefour).

    Stratégie : au moins UN mot significatif du nom de l'entreprise
    doit apparaître dans le domaine (après normalisation).
    """
    # Normalisation : minuscules, suppression accents basiques
    def norm(s: str) -> str:
        s = s.lower()
        for a, b in [("é","e"),("è","e"),("ê","e"),("à","a"),("â","a"),("ô","o"),("û","u"),("î","i")]:
            s = s.replace(a, b)
        return s

    domain_n  = norm(domain)
    company_n = norm(company)

    # Mots significatifs de l'entreprise (≥ 4 chars, hors mots génériques)
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
        domain = r.json().get("data", {}).get("domain")
        if domain:
            if _domain_matches_company(domain, company):
                print(f"     🌐 Domaine : {domain}")
                return domain
            # Domaine incohérent → on ne l'utilise pas
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
        data  = r.json().get("data", {})
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


def name_from_linkedin_url(url: str) -> tuple[str | None, str | None]:
    """
    /in/jean-dupont-abc123  →  ("Jean", "Dupont")
    Gère les slugs avec tirets multiples et identifiants de sécurité.
    """
    try:
        slug = url.rstrip("/").split("/in/")[-1]
        # Retire l'identifiant de sécurité : suite alphanum 4+ chars en fin de slug
        slug = re.sub(r"-[a-z0-9]{4,}$", "", slug)
        parts = [p for p in slug.split("-") if p and not p.isdigit()]
        if len(parts) >= 2:
            return parts[0].capitalize(), parts[1].capitalize()
    except Exception:
        pass
    return None, None


# ══════════════════════════════════════════════════════════════════════════
# 4. INJECTION DANS INDEX.HTML
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
    - 1er contact  →  hrEmail  (email principal, affiché en badge vert)
    - Contacts suivants  →  hrContacts  (contacts supplémentaires)

    Structure injectée :
        hrEmail: "jean.dupont@company.fr",
        hrContacts: [{name: "Marie Martin", email: "m.martin@company.fr"}],
        logo: "🏦",
    """
    if not contacts:
        return html

    m = re.search(rf"id:\s*['\"]({re.escape(offer_id)})['\"]", html)
    if not m:
        print(f"  ⚠  id '{offer_id}' introuvable, injection ignorée")
        return html

    id_pos = m.start()

    # hrEmail ← 1er contact
    first_email = contacts[0]["email"]
    html = _replace_or_insert_field(html, id_pos, "hrEmail", f'"{first_email}"')

    # hrContacts ← contacts suivants
    if len(contacts) > 1:
        m2 = re.search(rf"id:\s*['\"]({re.escape(offer_id)})['\"]", html)
        if m2:
            id_pos = m2.start()
            items_js = ", ".join(
                f'{{name: "{c["name"]}", email: "{c["email"]}", linkedin: "{c.get("linkedin", "")}"}}'  for c in contacts[1:]
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
# 5. PIPELINE PRINCIPAL
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

    for offer in offers:
        oid  = offer["id"]
        comp = offer["company"]
        city = offer["city"]
        dept = offer["department"]

        print(f"▶ {comp}  [{oid}]")
        print(f"  📍 {city or '?'}  |  🗂  {dept or 'service non détecté'}")

        # Étape A — LinkedIn
        profiles = find_linkedin_profiles(comp, city, dept)
        if not profiles:
            print()
            continue

        # Étape B — Hunter.io pour chaque profil
        contacts = []
        for url in profiles:
            first, last = name_from_linkedin_url(url)
            if not (first and last):
                print(f"  ✗  Nom non extractible depuis : {url}")
                continue

            print(f"  👤 {first} {last}...")
            email = resolve_email(first, last, comp)

            print(f"  👤 {first} {last}...")
            email = resolve_email(first, last, comp)

            if email:
                print(f"  ✉  {email}")
                contacts.append({"name": f"{first} {last}", "email": email, "linkedin": url})
            else:
                print(f"  ✗  {first} {last} — pas d'email")
                contacts.append({"name": f"{first} {last}", "email": "", "linkedin": url})

            time.sleep(DELAY)

        # Étape C — Injection dans index.html
        if contacts:
            html = inject_contacts(html, oid, contacts)
            print(f"  ✅ {len(contacts)} contact(s) injecté(s)")
            enriched += 1
        else:
            print("  ✗  Aucun email récupérable")

        print()

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(SEP)
    print(f"  ✅ {enriched}/{len(offers)} offre(s) enrichie(s)  —  index.html mis à jour")
    print(SEP)


if __name__ == "__main__":
    run()
