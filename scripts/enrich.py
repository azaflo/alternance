import os, requests, re, time

# --- CONFIGURATION DES CLÉS (RÉCUPÉRÉES DE GITHUB SECRETS) ---
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
FILE_PATH = "index.html"

def clean_company_name(name):
    """ Nettoie le nom de l'entreprise pour optimiser la recherche Google """
    name = name.lower()
    # Supprime tout ce qui est après un tiret ou une parenthèse (ex: Sonepar - France -> Sonepar)
    name = re.split(r'[-–—/(/|]', name)[0] 
    # Supprime les termes juridiques inutiles
    junk = ['france', 'groupe', 'group', 'sas', 'sa', 'sarl', 'europe', 'services', 'solutions']
    for word in junk:
        name = re.sub(rf'\b{word}\b', '', name)
    return re.sub(r'\s+', ' ', name).strip()

def search_linkedin_serpapi(company_name):
    """ Trouve un profil LinkedIn stratégique via SerpApi """
    if not SERPAPI_KEY:
        print("   ⚠️ Erreur : SERPAPI_KEY non configurée.")
        return None

    params = {
        "engine": "google",
        "q": f'site:linkedin.com/in/ ("responsable RH" OR "recrutement" OR "IT Manager" OR "DSI") "{company_name}"',
        "api_key": SERPAPI_KEY,
        "num": 1, # On prend le 1er résultat
        "gl": "fr",
        "hl": "fr"
    }

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
    """ Extrait Prénom et Nom depuis l'URL LinkedIn """
    try:
        # On récupère la fin de l'URL
        slug = url.split('/in/')[-1].strip('/')
        # On enlève les chiffres de sécurité à la fin si présents
        slug = re.sub(r'-[a-z0-9]+$', '', slug)
        parts = slug.split('-')
        if len(parts) >= 2:
            return parts[0].capitalize(), parts[1].capitalize()
    except:
        pass
    return None, None

def get_hunter_email(first_name, last_name, domain):
    """ Utilise Hunter.io pour trouver l'email pro """
    if not HUNTER_API_KEY:
        return None
    url = f"https://api.hunter.io/v2/email-finder?domain={domain}&first_name={first_name}&last_name={last_name}&api_key={HUNTER_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        return res.get('data', {}).get('email')
    except:
        return None

def run_pipeline():
    """ Fonction principale qui traite ton fichier index.html """
    print("🚀 Démarrage du Pipeline SISR (Version SerpApi)...")
    
    if not os.path.exists(FILE_PATH):
        print(f"❌ Erreur : Le fichier {FILE_PATH} est introuvable à la racine.")
        return

    # 1. Lecture du fichier
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 2. Identification des cibles (Cherche les lignes avec "En attente")
    # Format attendu dans ton HTML : <td>Sonepar</td><td>En attente</td>
    pattern = r'<td>(.*?)</td><td>En attente</td>'
    companies = re.findall(pattern, content)
    
    if not companies:
        print("📊 Aucune entreprise avec le statut 'En attente' trouvée.")
        return

    print(f"📊 {len(companies)} entreprises à enrichir.")

    for comp in companies:
        print(f"\n🏢 Traitement de : {comp}")
        cleaned = clean_company_name(comp)
        
        # Étape A : Google via SerpApi
        url = search_linkedin_serpapi(cleaned)
        
        if url:
            print(f"   🔎 Profil LinkedIn trouvé : {url}")
            # Étape B : Extraction du Nom
            fn, ln = extract_name_from_linkedin_url(url)
            
            if fn and ln:
                # Étape C : Deviner le domaine (simplifié)
                domain = cleaned.replace(" ", "") + ".fr"
                # Étape D : Hunter.io
                email = get_hunter_email(fn, ln, domain)
                
                if email:
                    print(f"   ✅ Email trouvé : {email}")
                    # Mise à jour du contenu HTML
                    old_line = f"<td>{comp}</td><td>En attente</td>"
                    new_line = f"<td>{comp}</td><td><a href='mailto:{email}'>{email}</a> ({fn} {ln})</td>"
                    content = content.replace(old_line, new_line)
                    continue
        
        print(f"   ❌ Échec de l'enrichissement pour {comp}")

    # 3. Sauvegarde du fichier mis à jour
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    
    print("\n✅ Travail terminé. Le fichier index.html a été mis à jour.")

# --- DÉMARRAGE DU SCRIPT ---
if __name__ == "__main__":
    run_pipeline()
