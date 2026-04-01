import os, requests, re, time
import urllib.parse
from duckduckgo_search import DDGS

# --- CONFIGURATION GLOBALE ---
API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html" 

# ... (Ici commence ta fonction clean_company_name) ...

def clean_company_name(name):
    """ Nettoie le nom de l'entreprise pour optimiser les recherches """
    name = name.lower()
    # ⚠️ CORRECTION : On ajoute le tiret long (–) et le tiret cadratin (—) dans la Regex
    name = re.split(r'[-–—/(/|]', name)[0] 
    junk = ['france', 'groupe', 'group', 'sas', 'sa', 'sarl', 'europe', 'services', 'solutions', 'technologies']
    for word in junk:
        name = re.sub(rf'\b{word}\b', '', name)
    return re.sub(r'\s+', ' ', name).strip()

# ... (extract_name_from_linkedin_url ne change pas)

def osint_dork_linkedin(company_name):
    """ Fait une recherche DuckDuckGo ciblée (Contourne le blocage IP Google) """
    query = f'site:linkedin.com/in/ "recrutement" "{company_name}"'
    print(f"   🔎 OSINT (DuckDuckGo) : Recherche profil pour {company_name}...")
    
    try:
        # Utilisation de DuckDuckGo au lieu de Google
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=1, region='fr-fr'))
            if results and len(results) > 0:
                return results[0].get('href')
    except Exception as e:
        print(f"   ⚠️ Erreur DDG : {e}")
    return None

def get_direct_email_finder(company_name, first_name, last_name):
    """ Utilise l'API Email Finder pour trouver l'email exact de la personne """
    safe_company = urllib.parse.quote(company_name)
    safe_first = urllib.parse.quote(first_name)
    safe_last = urllib.parse.quote(last_name)
    
    url = f"https://api.hunter.io/v2/email-finder?company={safe_company}&first_name={safe_first}&last_name={safe_last}&api_key={API_KEY}"
    
    try:
        res = requests.get(url, timeout=10).json()
        email = res.get('data', {}).get('email')
        score = res.get('data', {}).get('score', 0)
        
        if email and score >= 50:
            return email, score
    except:
        pass
    return None, 0

def get_domain_search_fallback(company_name):
    """ STRATÉGIE DE REPLI : Recherche classique par domaine si le profil exact échoue """
    safe_company = urllib.parse.quote(company_name)
    url = f"https://api.hunter.io/v2/domain-search?company={safe_company}&api_key={API_KEY}"
    
    try:
        res = requests.get(url, timeout=10).json()
        emails = res.get('data', {}).get('emails', [])
        
        target_keywords = ['recrut', 'rh', 'hr', 'talent', 'it ', 'infra', 'reseau', 'system', 'admin']
        vip_keywords = ['head of', 'director', 'president', 'vp ']

        best_email, max_score, best_pos = None, 0, ""

        for e in emails:
            email_val = e.get('value', '').lower()
            position = (e.get('position') or "").lower()
            profil = f"{email_val} {position}"

            score = 10 if email_val.endswith('.fr') else 0
            if any(word in profil for word in target_keywords): score += 30
            if any(word in profil for word in vip_keywords): score -= 40

            if score > max_score and score >= 10:
                max_score, best_email, best_pos = score, email_val, position

        if best_email:
            return best_email, best_pos
            
    except:
        pass
    return None, None

# --- 3. LOGIQUE ORCHESTRALE (LE MOTEUR) ---

def process_company(original_name):
    cleaned_name = clean_company_name(original_name)
    
    # ÉTAPE 1 : Trouver la personne via Google Dorking
    linkedin_url = google_dork_linkedin(cleaned_name)
    
    if linkedin_url:
        first_name, last_name = extract_name_from_linkedin_url(linkedin_url)
        if first_name and last_name:
            print(f"   👤 Cible identifiée : {first_name.capitalize()} {last_name.capitalize()}")
            
            # ÉTAPE 2 : Trouver son email direct avec Hunter
            direct_email, confidence = get_direct_email_finder(cleaned_name, first_name, last_name)
            if direct_email:
                print(f"   🎯 BINGO (Mail Direct) : {direct_email} (Confiance: {confidence}%)")
                return direct_email
            else:
                print("   ⚠️ L'API Finder n'a pas pu valider le mail exact.")
    
    # ÉTAPE 3 : Fallback (Plan B) - Si pas de profil ou pas de mail direct
    print("   🔄 Activation du Plan B (Recherche générique de domaine)...")
    fallback_email, position = get_domain_search_fallback(cleaned_name)
    
    if fallback_email:
        print(f"   ✅ Plan B Réussi : {fallback_email} (Poste: {position})")
        return fallback_email
        
    print(f"   ❌ Échec total pour {cleaned_name}. Aucun contact trouvé.")
    return None

# --- 4. EXÉCUTION SUR LE FICHIER ---

try:
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex pour cibler les offres où l'email est vide
    pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
    matches = list(re.finditer(pattern, content, re.DOTALL))

    print(f"\n🚀 Démarrage du Pipeline SISR...")
    print(f"📊 {len(matches)} entreprises à enrichir.\n" + "-"*40)

    found_count = 0
    for match in matches:
        name = match.group(1)
        print(f"\n🏢 Traitement de : {name}")
        
        final_email = process_company(name)
        
        if final_email:
            old_block = match.group(0)
            new_block = old_block.replace('hrEmail: ""', f'hrEmail: "{final_email}"')
            content = content.replace(old_block, new_block)
            found_count += 1
        
        # Pause obligatoire pour ne pas se faire bloquer par Google et Hunter
        time.sleep(2) 

    # Sauvegarde si modifications
    if found_count > 0:
        with open(FILE_PATH, 'w', encoding='utf-8') as f: 
            f.write(content)
        print(f"\n🎉 SUCCÈS : {found_count} nouveaux contacts injectés dans {FILE_PATH} !")
    else:
        print("\nℹ️ Traitement terminé. Aucun nouveau contact trouvé.")

except FileNotFoundError:
    print(f"❌ Erreur critique : Le fichier {FILE_PATH} est introuvable.")
except Exception as e:
    print(f"❌ Une erreur inattendue a stoppé le script : {e}")
