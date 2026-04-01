import os, requests, re, time
import urllib.parse

# --- CONFIGURATION ---
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
FILE_PATH = "index.html"

def clean_company_name(name):
    name = name.lower()
    name = re.split(r'[-–—/(/|]', name)[0] 
    junk = ['france', 'groupe', 'group', 'sas', 'sa', 'sarl', 'europe', 'services', 'solutions']
    for word in junk:
        name = re.sub(rf'\b{word}\b', '', name)
    return re.sub(r'\s+', ' ', name).strip()

def search_linkedin_serpapi(company_name):
    """ Recherche LinkedIn via SerpApi (Fiable et rapide) """
    if not SERPAPI_KEY:
        print("   ⚠️ Clé SERPAPI_KEY manquante !")
        return None

    params = {
        "engine": "google",
        "q": f'site:linkedin.com/in/ ("responsable RH" OR "recrutement" OR "IT Manager" OR "DSI") "{company_name}"',
        "api_key": SERPAPI_KEY,
        "num": 1,
        "gl": "fr", # On cherche en France
        "hl": "fr"
    }

    print(f"   🔎 OSINT (SerpApi) : Recherche profil pour {company_name}...")
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=15)
        data = response.json()
        results = data.get("organic_results", [])
        if results and "linkedin.com/in/" in results[0].get("link", ""):
            return results[0].get("link")
    except Exception as e:
        print(f"   ⚠️ Erreur SerpApi : {e}")
    return None

def extract_name_from_linkedin_url(url):
    slug = url.split('/in/')[-1].strip('/')
    slug = re.sub(r'-[a-z0-9]+$', '', slug)
    parts = slug.split('-')
    if len(parts) >= 2:
        return parts[0].capitalize(), parts[1].capitalize()
    return None, None

def get_hunter_email(first_name, last_name, domain):
    if not HUNTER_API_KEY: return None
    url = f"https://api.hunter.io/v2/email-finder?domain={domain}&first_name={first_name}&last_name={last_name}&api_key={HUNTER_API_KEY}"
    try:
        res = requests.get(url).json()
        return res.get('data', {}).get('email')
    except: return None

def process_company(original_name):
    cleaned_name = clean_company_name(original_name)
    linkedin_url = search_linkedin_serpapi(cleaned_name)
    
    if linkedin_url:
        f_name, l_name = extract_name_from_linkedin_url(linkedin_url)
        if f_name and l_name:
            # On tente de deviner le domaine simplement
            domain = cleaned_name.replace(' ', '') + ".fr"
            email = get_hunter_email(f_name, l_name, domain)
            if email:
                print(f"   ✅ Trouvé : {email}")
                return email, f"{f_name} {l_name}"
    
    print(f"   ❌ Aucun contact trouvé pour {cleaned_name}.")
    return None, None

# --- LE RESTE DU SCRIPT (LECTURE/ECRITURE index.html) RESTE PAREIL ---
# (Assure-toi de garder ta logique qui lit le fichier index.html ici)
