import os, requests, re, unicodedata

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_official_domain(company_name):
    clean_name = "".join(c for c in unicodedata.normalize('NFD', company_name) if unicodedata.category(c) != 'Mn')
    url = f"https://api.hunter.io/v2/companies/suggest?name={clean_name}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and len(res['data']) > 0:
            dom = res['data'][0]['domain']
            print(f"   🌐 Domaine identifié : {dom}")
            return dom
    except: pass
    print(f"   ⚠️ Impossible de trouver le domaine pour {company_name}")
    return None

def get_email_from_domain(domain):
    if not domain: return None
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        emails = res.get('data', {}).get('emails', [])
        print(f"   📦 Hunter a trouvé {len(emails)} mails au total sur ce domaine.")
        
        if not emails: return None

        # On élargit les mots-clés pour ne rien rater
        keywords = ['dsi', 'cto', 'infra', 'reseau', 'system', 'cyber', 'it', 'rh', 'hr', 'recrut', 'talent', 'job', 'contact', 'info']

        for e in emails:
            email_val = e.get('value', '').lower()
            position = (e.get('position') or "").lower()
            profil = f"{email_val} {position}"

            if any(word in profil for word in keywords):
                print(f"   🎯 Cible trouvée : {email_val} ({position})")
                return e['value']
        
        # Secours : on prend le 1er mail même s'il n'est pas "IT/RH" si le score est bon
        print(f"   💡 Pas de cible précise, on prend le meilleur mail par défaut.")
        return emails[0]['value']
            
    except Exception as err:
        print(f"   ❌ Erreur API : {err}")
    return None

# --- Logique principale ---
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Debug : On affiche un extrait du fichier pour voir si la Regex va marcher
print(f"🔍 DEBUG : Analyse du fichier {FILE_PATH}...")
pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
matches = list(re.finditer(pattern, content, re.DOTALL))

print(f"📊 Nombre d'offres vides détectées par le radar : {len(matches)}")

found_count = 0
for match in matches:
    company_name = match.group(1)
    print(f"\n🔎 TRAVAIL SUR : {company_name}")
    
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
    print(f"\n🚀 TERMINE : {found_count} mails injectés dans l'index.html !")
else:
    print("\nℹ️ Fin du scan : Aucun mail n'a été retenu.")
