import os, requests, re, time
import urllib.parse

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def clean_company_name(name):
    """ Nettoie le nom de l'entreprise pour maximiser les chances de l'API """
    # 1. Tout en minuscule
    name = name.lower()
    
    # 2. On retire tout ce qui est après un tiret, une parenthèse ou un slash
    # Exemple : "GL Events - Stade de France" -> "gl events"
    name = re.split(r'[-/(/|]', name)[0]
    
    # 3. On retire les mentions légales et mots parasites (seulement s'ils sont des mots entiers)
    junk = ['france', 'groupe', 'group', 'sas', 'sa', 'sarl', 'europe', 'services', 'solutions', 'technologies']
    for word in junk:
        name = re.sub(rf'\b{word}\b', '', name)
    
    # 4. On retire les doubles espaces et on nettoie les bords
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def get_best_operational_email(original_name):
    # NETTOYAGE DU NOM
    cleaned_name = clean_company_name(original_name)
    if cleaned_name != original_name.lower():
        print(f"   🧹 Nom nettoyé : '{original_name}' -> '{cleaned_name}'")

    # ENCODAGE URL
    safe_company = urllib.parse.quote(cleaned_name)
    url = f"https://api.hunter.io/v2/domain-search?company={safe_company}&api_key={API_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"   ❌ Erreur API Hunter (Code {response.status_code})")
            return None
            
        res = response.json()
        emails = res.get('data', {}).get('emails', [])
        
        if not emails: 
            print(f"   ⚠️ Aucun mail trouvé pour '{cleaned_name}'.")
            return None

        # --- FILTRAGE & SCORING ---
        idf_cities = ['paris', 'idf', 'chatenay', 'nanterre', 'velizy', '92', '75', '94', '78']
        target_keywords = ['recrut', 'rh', 'hr', 'talent', 'it ', 'infra', 'reseau', 'system', 'support', 'informatique', 'admin', 'tech']
        vip_keywords = ['head of', 'director', 'directeur', 'chief', 'president', 'vp ', 'vice president', 'dg ', 'general manager']

        valid_profiles = []

        for e in emails:
            email_val = e.get('value', '').lower()
            position = (e.get('position') or "").lower()
            profil = f"{email_val} {position}"

            score = 0
            if email_val.endswith('.fr'): score += 10
            if any(city in profil for city in idf_cities): score += 15
            if any(word in profil for word in target_keywords): score += 30
            
            # Malus VIP
            if any(word in profil for word in vip_keywords):
                score -= 40
                # On ne l'affiche que si c'est vraiment un gros profil
                # print(f"   ⚠️ VIP ignoré : {position}")

            if score > 15:
                valid_profiles.append({'email': e['value'], 'score': score, 'pos': position})

        if valid_profiles:
            valid_profiles.sort(key=lambda x: x['score'], reverse=True)
            best = valid_profiles[0]
            print(f"   🎯 Match : {best['email']} ({best['pos']}) [Score: {best['score']}]")
            return best['email']
            
    except Exception as e:
        print(f"   🔥 Erreur critique : {e}")
        
    return None

# --- LOGIQUE DE MISE À JOUR ---
try:
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
    matches = list(re.finditer(pattern, content, re.DOTALL))

    print(f"📊 Analyse de {len(matches)} entreprises en attente...")

    found_count = 0
    for match in matches:
        name = match.group(1)
        print(f"\n🔎 Recherche : {name}")
        
        email = get_best_operational_email(name)
        
        if email:
            old_block = match.group(0)
            new_block = old_block.replace('hrEmail: ""', f'hrEmail: "{email}"')
            content = content.replace(old_block, new_block)
            found_count += 1
        
        time.sleep(1.2) # Un peu de délai pour l'API

    if found_count > 0:
        with open(FILE_PATH, 'w', encoding='utf-8') as f: 
            f.write(content)
        print(f"\n🚀 TERMINÉ : {found_count} contacts ajoutés au fichier.")
    else:
        print("\nℹ️ Rien de neuf aujourd'hui.")

except FileNotFoundError:
    print(f"❌ Erreur : Le fichier {FILE_PATH} est introuvable.")
