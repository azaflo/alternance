import os
import requests
import re
import unicodedata

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_official_domain(company_name):
    # Nettoyage rapide pour l'API
    clean_name = "".join(c for c in unicodedata.normalize('NFD', company_name) if unicodedata.category(c) != 'Mn')
    url = f"https://api.hunter.io/v2/companies/suggest?name={clean_name}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and len(res['data']) > 0:
            return res['data'][0]['domain']
    except: pass
    return None

def get_email_from_domain(domain):
    if not domain: return None
    
    # On enlève le filtre strict "&department=hr" de l'URL pour chercher tout le monde (notamment la DSI)
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        emails = res.get('data', {}).get('emails', [])
        if not emails: return None

        # Nos deux listes de mots-clés "Cibles"
        it_keywords = ['dsi', 'cto', 'infrastructure', 'infra', 'réseau', 'reseau', 'système', 'systeme', 'cyber', 'sécurité', 'security', 'cloud', 'devops', 'support', 'informatique', 'it ']
        hr_keywords = ['recrutement', 'rh', 'hr', 'talent', 'ressources humaines', 'recruiter']

        # 1. On cherche d'abord le Graal : Un manager Tech/SISR ou un RH
        for e in emails:
            email_val = e.get('value', '').lower()
            position = (e.get('position') or "").lower() # Le titre du poste (ex: "Directeur Informatique")
            department = (e.get('department') or "").lower()
            
            # On regroupe tout le profil dans une seule phrase pour chercher nos mots-clés
            profil_complet = f"{email_val} {position} {department}"

            # Est-ce un manager IT / SISR ?
            if any(word in profil_complet for word in it_keywords):
                print(f"👨‍💻 Manager IT trouvé ! (Poste : {position.title()}) -> {email_val}")
                return email_val
            
            # Est-ce un profil RH ?
            if any(word in profil_complet for word in hr_keywords):
                print(f"🎯 Profil RH trouvé ! (Poste : {position.title()}) -> {email_val}")
                return email_val
        
        # 2. Si on n'a ni RH ni Tech, on prend l'e-mail le plus fiable (> 70% de confiance)
        best_email = emails[0]
        if best_email.get('confidence', 0) > 70:
            print(f"✅ E-mail pro fiable (Fiabilité: {best_email['confidence']}%) -> {best_email['value']}")
            return best_email['value']
            
    except: pass
    return None
        
        # 2. Si pas de RH, on prend le mail le plus fiable (> 70% de confiance)
        best_email = emails[0]
        if best_email.get('confidence', 0) > 70:
            print(f"✅ Mail pro trouvé (fiabilité {best_email['confidence']}%): {best_email['value']}")
            return best_email['value']
            
    except: pass
    return None

# --- Logique principale ---
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# On cherche les blocs company + hrEmail vide
pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
matches = list(re.finditer(pattern, content, re.DOTALL))

print(f"📊 {len(matches)} offres vides détectées. Lancement de l'enrichissement...")

found_count = 0
for match in matches:
    company_name = match.group(1)
    print(f"🔎 Analyse de : {company_name}")
    
    domain = get_official_domain(company_name)
    if domain:
        email = get_email_from_domain(domain)
        if email:
            # Remplacement précis dans le texte
            old_text = match.group(0)
            new_text = old_text.replace('hrEmail: ""', f'hrEmail: "{email}"')
            content = content.replace(old_text, new_text)
            found_count += 1

if found_count > 0:
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"🚀 Succès : {found_count} e-mails ajoutés au fichier !")
else:
    print("❌ Aucun e-mail assez fiable n'a été trouvé pour le moment.")
