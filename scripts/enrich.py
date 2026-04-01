import os, requests, re, time
import urllib.parse

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_best_operational_email(company_name):
    # On encode le nom proprement (ex: "Crédit Agricole" devient "Cr%C3%A9dit%20Agricole")
    safe_company = urllib.parse.quote(company_name)
    url = f"https://api.hunter.io/v2/domain-search?company={safe_company}&api_key={API_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        
        # Vérification des erreurs de l'API
        if response.status_code != 200:
            print(f"   ❌ Erreur API Hunter (Code {response.status_code})")
            return None
            
        res = response.json()
        emails = res.get('data', {}).get('emails', [])
        
        # Si la liste est vide
        if not emails: 
            print("   ⚠️ Hunter.io n'a trouvé aucun email pour cette entreprise.")
            return None

        # --- CONFIGURATION DES FILTRES ---
        idf_cities = ['paris', 'idf', 'chatenay', 'nanterre', 'velizy', '92', '75', '94', '78']
        target_keywords = ['recrut', 'rh', 'hr', 'talent', 'it ', 'infra', 'reseau', 'system', 'support', 'informatique', 'admin', 'tech']
        vip_keywords = ['head of', 'director', 'directeur', 'chief', 'president', 'vp ', 'vice president', 'dg ', 'general manager']

        valid_profiles = []

        for e in emails:
            email_val = e.get('value', '').lower()
            position = (e.get('position') or "").lower()
            profil = f"{email_val} {position}"

            score = 0
            
            # 1. Bonus France/IDF (Base 10-20 pts)
            if email_val.endswith('.fr'): score += 10
            if any(city in profil for city in idf_cities): score += 15

            # 2. Bonus Métier Cible (SISR / RH)
            if any(word in profil for word in target_keywords):
                score += 30
            
            # 3. MALUS VIP (On baisse le score des grands chefs)
            if any(word in profil for word in vip_keywords):
                score -= 40
                print(f"   ⚠️ Profil trop haut placé ignoré : {position}")

            if score > 15:
                valid_profiles.append({'email': e['value'], 'score': score, 'pos': position})

        if valid_profiles:
            # On prend celui qui a le meilleur score après malus
            valid_profiles.sort(key=lambda x: x['score'], reverse=True)
            best = valid_profiles[0]
            print(f"   🎯 Match retenu : {best['email']} (Poste: {best['pos']}) [Score: {best['score']}]")
            return best['email']
            
    except Exception as e:
        print(f"   🔥 Script planté sur cette entreprise : {e}")
        
    return None

# --- Logique de mise à jour ---
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
matches = list(re.finditer(pattern, content, re.DOTALL))

print(f"📊 Filtrage de {len(matches)} offres (Focus Opérationnel)...")

found_count = 0
for match in matches:
    name = match.group(1)
    print(f"\n🔎 Recherche pour : {name}")
    email = get_best_operational_email(name)
    
    if email:
        old_block = match.group(0)
        new_block = old_block.replace('hrEmail: ""', f'hrEmail: "{email}"')
        content = content.replace(old_block, new_block)
        found_count += 1
        
    # Pause de 1 seconde pour protéger ton quota d'API
    time.sleep(1)

if found_count > 0:
    with open(FILE_PATH, 'w', encoding='utf-8') as f: 
        f.write(content)
    print(f"\n🚀 SUCCESS : {found_count} mails opérationnels ajoutés.")
else:
    print("\nℹ️ Aucun mail correspondant au profil 'Alternant' trouvé.")
