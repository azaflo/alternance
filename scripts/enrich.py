import os
import requests
import re
import unicodedata

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_official_domain(company_name):
    # Nettoyage des accents pour l'API
    clean_name = "".join(c for c in unicodedata.normalize('NFD', company_name) if unicodedata.category(c) != 'Mn')
    url = f"https://api.hunter.io/v2/companies/suggest?name={clean_name}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and len(res['data']) > 0:
            return res['data'][0]['domain']
    except:
        pass
    return None

def get_email_from_domain(domain):
    if not domain:
        return None
    
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        emails = res.get('data', {}).get('emails', [])
        if not emails:
            return None

        # Mots-clés pour BTS SIO (SISR) / Licence Info / RH
        it_keywords = ['dsi', 'cto', 'infrastructure', 'infra', 'réseau', 'reseau', 'système', 'systeme', 'cyber', 'sécurité', 'security', 'cloud', 'devops', 'support', 'informatique', 'it ']
        hr_keywords = ['recrutement', 'rh', 'hr', 'talent', 'ressources humaines', 'recruiter']

        # 1. Recherche d'un profil spécifique (Tech ou RH)
        for e in emails:
            email_val = e.get('value', '').lower()
            position = (e.get('position') or "").lower()
            dept = (e.get('department') or "").lower()
            profil = f"{email_val} {position} {dept}"

            if any(word in profil for word in it_keywords):
                print(f"👨‍💻 Manager IT trouvé : {email_val} ({position})")
                return e['value']
            
            if any(word in profil for word in hr_keywords):
                print(f"🎯 Profil RH trouvé : {email_val} ({position})")
                return e['value']
        
        # 2. Si rien de spécifique, on prend le plus fiable
        best_email = emails[0]
        if best_email.get('confidence', 0) > 70:
            print(f"✅ Email fiable trouvé : {best_email['value']}")
            return best_email['value']
            
    except:
        pass
    return None

# --- Logique principale ---
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# On cible les entreprises avec hrEmail vide
pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
matches = list(re.finditer(pattern, content, re.DOTALL))

print(f"📊 {len(matches)} offres à traiter.")

found_count = 0
for match in matches:
    company_name = match.group(1)
    print(f"🔎 Recherche pour : {company_name}")
    
    domain = get_official_domain(company_name)
    if domain:
        email = get_email_from_domain(domain)
        if email:
            old_text = match.group(0)
            new_text = old_text.replace('hrEmail: ""', f'hrEmail: "{email}"')
            content = content.replace(old_text, new_text)
            found_count += 1

if found_count > 0:
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"🚀 Succès : {found_count} emails ajoutés !")
else:
    print("ℹ️ Aucun email n'a pu être ajouté.")
