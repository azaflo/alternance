import os, requests, re

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_best_idf_email(company_name):
    url = f"https://api.hunter.io/v2/domain-search?company={company_name}&api_key={API_KEY}"
    
    try:
        res = requests.get(url, timeout=10).json()
        emails = res.get('data', {}).get('emails', [])
        if not emails: return None

        # Lexique IDF : Villes et départements clés de l'informatique
        idf_keywords = ['paris', 'idf', 'ile-de-france', 'nanterre', 'velizy', 'courbevoie', 'la defense', '75', '92', '94', '78', '91']
        it_rh_keywords = ['dsi', 'it', 'tech', 'infra', 'reseau', 'system', 'cyber', 'rh', 'hr', 'recrut', 'talent', 'job']
        
        valid_emails = []

        for e in emails:
            email_val = e.get('value', '').lower()
            position = (e.get('position') or "").lower()
            profil = f"{email_val} {position}"

            score = 0
            
            # CRITÈRE 1 : Bonus FRANCE (.fr)
            if email_val.endswith('.fr'): score += 10
            
            # CRITÈRE 2 : Bonus ILE-DE-FRANCE (Le Graal pour toi)
            if any(city in profil for city in idf_keywords):
                score += 20
                print(f"   📍 Localisation IDF détectée pour : {email_val}")

            # CRITÈRE 3 : Bonus METIER (IT/RH)
            if any(word in profil for word in it_rh_keywords):
                score += 15

            # On ne garde que les profils qui ont au moins un bonus France ou IDF
            if score >= 10:
                valid_emails.append({'email': e['value'], 'score': score, 'pos': position})

        if valid_emails:
            # On trie pour avoir le meilleur score (IDF + IT + FR) en premier
            valid_emails.sort(key=lambda x: x['score'], reverse=True)
            best = valid_emails[0]
            print(f"   🎯 Top match : {best['email']} (Score: {best['score']})")
            return best['email']
            
    except: pass
    return None

# --- Logique de mise à jour (le reste du script est identique) ---
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
matches = list(re.finditer(pattern, content, re.DOTALL))

print(f"📊 Analyse de {len(matches)} offres - Cible : Île-de-France...")

found_count = 0
for match in matches:
    name = match.group(1)
    print(f"\n🔎 Recherche IDF pour : {name}")
    email = get_best_idf_email(name)
    if email:
        old_block = match.group(0)
        new_block = old_block.replace('hrEmail: ""', f'hrEmail: "{email}"')
        content = content.replace(old_block, new_block)
        found_count += 1

if found_count > 0:
    with open(FILE_PATH, 'w', encoding='utf-8') as f: f.write(content)
    print(f"\n🚀 SUCCESS : {found_count} mails localisés ajoutés !")
else:
    print("\nℹ️ Aucun mail IDF trouvé.")
