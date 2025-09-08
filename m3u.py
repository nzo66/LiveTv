import requests
import os
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def dlhd():
    """
    Estrae canali 24/7 e eventi live da DaddyLive e li salva in un unico file M3U.
    Rimuove automaticamente i canali duplicati.
    """
    print("Eseguendo dlhd...")
    import requests
    import re
    from bs4 import BeautifulSoup
    import json
    import urllib.parse
    from datetime import datetime, timedelta
    from dateutil import parser
    import os
    from dotenv import load_dotenv
    import time

    # Carica le variabili d'ambiente
    load_dotenv()

    LINK_DADDY = os.getenv("LINK_DADDY", "https://daddylive.sx").strip()
    JSON_FILE = "daddyliveSchedule.json"
    OUTPUT_FILE = "dlhd.m3u"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
    }

    # ========== FUNZIONI DI SUPPORTO ==========
    def clean_category_name(name):
        return re.sub(r'<[^>]+>', '', name).strip()

    def clean_tvg_id(tvg_id):
        cleaned = re.sub(r'[^a-zA-Z0-9À-ÿ]', '', tvg_id)
        return cleaned.lower()

    def get_stream_from_channel_id(channel_id):
        return f"{LINK_DADDY}/stream/stream-{channel_id}.php"

    # ========== ESTRAZIONE CANALI 24/7 ==========
    print("Estraendo canali 24/7...")
    url = "https://daddylive.sx/24-7-channels.php"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        channels_247 = []
        seen_names = set()

        grid_items = soup.find_all("div", class_="grid-item")

        for div in grid_items:
            a = div.find("a", href=True)
            if not a:
                continue
            href = a["href"].strip()
            href = href.replace(" ", "").replace("//", "/")
            strong = a.find("strong")
            if strong:
                name = strong.get_text(strip=True)
            else:
                name = a.get_text(strip=True)

            if name == "LA7d HD+ Italy":
                name = "Canale 5 Italy"

            if name == "Sky Calcio 7 (257) Italy":
                name = "DAZN"

            match = re.search(r'stream-(\d+)\.php', href)
            if not match:
                continue
            channel_id = match.group(1)
            stream_url = f"https://daddylive.sx/stream/stream-{channel_id}.php"
            channels_247.append((name, stream_url))

        # Conta le occorrenze di ogni nome di canale
        name_counts = {}
        for name, _ in channels_247:
            name_counts[name] = name_counts.get(name, 0) + 1

        # Aggiungi un contatore ai nomi duplicati
        final_channels = []
        name_counter = {}

        for name, stream_url in channels_247:
            if name_counts[name] > 1:
                if name not in name_counter:
                    # Prima occorrenza di un duplicato, mantieni il nome originale
                    name_counter[name] = 1
                    final_channels.append((name, stream_url))
                else:
                    # Occorrenze successive, aggiungi contatore
                    name_counter[name] += 1
                    new_name = f"{name} ({name_counter[name]})"
                    final_channels.append((new_name, stream_url))
            else:
                final_channels.append((name, stream_url))

        channels_247.sort(key=lambda x: x[0].lower())
        print(f"Trovati {len(channels_247)} canali 24/7")
        channels_247 = final_channels
    except Exception as e:
        print(f"Errore nell'estrazione dei canali 24/7: {e}")
        channels_247 = []

    # ========== ESTRAZIONE EVENTI LIVE ==========
    print("Estraendo eventi live...")
    live_events = []

    if os.path.exists(JSON_FILE):
        try:
            now = datetime.now()
            yesterday_date = (now - timedelta(days=1)).date()

            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            categorized_channels = {}

            for date_key, sections in data.items():
                date_part = date_key.split(" - ")[0]
                try:
                    date_obj = parser.parse(date_part, fuzzy=True).date()
                except Exception as e:
                    print(f"Errore parsing data '{date_part}': {e}")
                    continue

                process_this_date = False
                is_yesterday_early_morning_event_check = False

                if date_obj == now.date():
                    process_this_date = True
                elif date_obj == yesterday_date:
                    process_this_date = True
                    is_yesterday_early_morning_event_check = True
                else:
                    continue

                if not process_this_date:
                    continue

                for category_raw, event_items in sections.items():
                    category = clean_category_name(category_raw)
                    if category.lower() == "tv shows":
                        continue
                    if category not in categorized_channels:
                        categorized_channels[category] = []

                    for item in event_items:
                        time_str = item.get("time", "00:00")
                        event_title = item.get("event", "Evento")

                        try:
                            original_event_time_obj = datetime.strptime(time_str, "%H:%M").time()
                            event_datetime_adjusted_for_display_and_filter = datetime.combine(date_obj, original_event_time_obj)

                            if is_yesterday_early_morning_event_check:
                                start_filter_time = datetime.strptime("00:00", "%H:%M").time()
                                end_filter_time = datetime.strptime("04:00", "%H:%M").time()
                                if not (start_filter_time <= original_event_time_obj <= end_filter_time):
                                    continue
                            else:
                                if now - event_datetime_adjusted_for_display_and_filter > timedelta(hours=2):
                                    continue

                            time_formatted = event_datetime_adjusted_for_display_and_filter.strftime("%H:%M")
                        except Exception as e_time:
                            print(f"Errore parsing orario '{time_str}' per evento '{event_title}' in data '{date_key}': {e_time}")
                            time_formatted = time_str

                        for ch in item.get("channels", []):
                            channel_name = ch.get("channel_name", "")
                            channel_id = ch.get("channel_id", "")

                            tvg_name = f"{event_title} ({time_formatted})"
                            categorized_channels[category].append({
                                "tvg_name": tvg_name,
                                "channel_name": channel_name,
                                "channel_id": channel_id,
                                "event_title": event_title,
                                "category": category
                            })

            # Converti in lista per il file M3U
            for category, channels in categorized_channels.items():
                for ch in channels:
                    try:
                        stream = get_stream_from_channel_id(ch["channel_id"])
                        if stream:
                            live_events.append((f"{category} | {ch['tvg_name']} | {ch['channel_name']}", stream))
                    except Exception as e:
                        print(f"Errore su {ch['tvg_name']}: {e}")

            print(f"Trovati {len(live_events)} eventi live")

        except Exception as e:
            print(f"Errore nell'estrazione degli eventi live: {e}")
            live_events = []
    else:
        print(f"File {JSON_FILE} non trovato, eventi live saltati")

    # ========== GENERAZIONE FILE M3U UNIFICATO ==========
    print("Generando file M3U unificato...")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        # Aggiungi eventi live se presenti
        if live_events:
            f.write(f'#EXTINF:-1 group-title="Live Events",DADDYLIVE\n')
            f.write("https://example.com.m3u8\n\n")

            for name, url in live_events:
                f.write(f'#EXTINF:-1 group-title="Live Events",{name}\n{url}\n\n')

        # Aggiungi canali 24/7
        if channels_247:
            for name, url in channels_247:
                f.write(f'#EXTINF:-1 group-title="DLHD 24/7",{name}\n{url}\n\n')

    total_channels = len(channels_247) + len(live_events)
    print(f"Creato file {OUTPUT_FILE} con {total_channels} canali totali:")
    print(f"  - {len(channels_247)} canali 24/7")
    print(f"  - {len(live_events)} eventi live")

# Funzione per il quarto script (schedule_extractor.py)
def schedule_extractor():
    # Codice del quarto script qui
    # Aggiungi il codice del tuo script "schedule_extractor.py" in questa funzione.
    print("Eseguendo lo schedule_extractor.py...")
    # Il codice che avevi nello script "schedule_extractor.py" va qui, senza modifiche.
    from playwright.sync_api import sync_playwright
    import os
    import json
    from datetime import datetime
    import re
    from bs4 import BeautifulSoup
    from dotenv import load_dotenv
    
    # Carica le variabili d'ambiente dal file .env
    load_dotenv()
    
    LINK_DADDY = os.getenv("LINK_DADDY", "https://daddylive.sx").strip()
    
    def html_to_json(html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        result = {}
        
        date_rows = soup.find_all('tr', class_='date-row')
        if not date_rows:
            print("AVVISO: Nessuna riga di data trovata nel contenuto HTML!")
            return {}
    
        current_date = None
        current_category = None
    
        for row in soup.find_all('tr'):
            if 'date-row' in row.get('class', []):
                current_date = row.find('strong').text.strip()
                result[current_date] = {}
                current_category = None
    
            elif 'category-row' in row.get('class', []) and current_date:
                current_category = row.find('strong').text.strip() + "</span>"
                result[current_date][current_category] = []
    
            elif 'event-row' in row.get('class', []) and current_date and current_category:
                time_div = row.find('div', class_='event-time')
                info_div = row.find('div', class_='event-info')
    
                if not time_div or not info_div:
                    continue
    
                time_strong = time_div.find('strong')
                event_time = time_strong.text.strip() if time_strong else ""
                event_info = info_div.text.strip()
    
                event_data = {
                    "time": event_time,
                    "event": event_info,
                    "channels": []
                }
    
                # Cerca la riga dei canali successiva
                next_row = row.find_next_sibling('tr')
                if next_row and 'channel-row' in next_row.get('class', []):
                    channel_links = next_row.find_all('a', class_='channel-button-small')
                    for link in channel_links:
                        href = link.get('href', '')
                        channel_id_match = re.search(r'stream-(\d+)\.php', href)
                        if channel_id_match:
                            channel_id = channel_id_match.group(1)
                            channel_name = link.text.strip()
                            channel_name = re.sub(r'\s*\(CH-\d+\)$', '', channel_name)
    
                            event_data["channels"].append({
                                "channel_name": channel_name,
                                "channel_id": channel_id
                            })
    
                result[current_date][current_category].append(event_data)
    
        return result
    
    def modify_json_file(json_file_path):
        with open(json_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        current_month = datetime.now().strftime("%B")
    
        for date in list(data.keys()):
            match = re.match(r"(\w+\s\d+)(st|nd|rd|th)\s(\d{4})", date)
            if match:
                day_part = match.group(1)
                suffix = match.group(2)
                year_part = match.group(3)
                new_date = f"{day_part}{suffix} {current_month} {year_part}"
                data[new_date] = data.pop(date)
    
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
        print(f"File JSON modificato e salvato in {json_file_path}")
    
    def extract_schedule_container():
        url = f"{LINK_DADDY}/"
    
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_output = os.path.join(script_dir, "daddyliveSchedule.json")
    
        print(f"Accesso alla pagina {url} per estrarre il main-schedule-container...")
    
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
    
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                try:
                    print(f"Tentativo {attempt} di {max_attempts}...")
                    page.goto(url)
                    print("Attesa per il caricamento completo...")
                    page.wait_for_timeout(30000)  # 10 secondi
    
                    schedule_content = page.evaluate("""() => {
                        const container = document.getElementById('main-schedule-container');
                        return container ? container.outerHTML : '';
                    }""")
    
                    if not schedule_content:
                        print("AVVISO: main-schedule-container non trovato o vuoto!")
                        if attempt == max_attempts:
                            browser.close()
                            return False
                        else:
                            continue
    
                    print("Conversione HTML in formato JSON...")
                    json_data = html_to_json(schedule_content)
    
                    with open(json_output, "w", encoding="utf-8") as f:
                        json.dump(json_data, f, indent=4)
    
                    print(f"Dati JSON salvati in {json_output}")
    
                    modify_json_file(json_output)
                    browser.close()
                    return True
    
                except Exception as e:
                    print(f"ERRORE nel tentativo {attempt}: {str(e)}")
                    if attempt == max_attempts:
                        print("Tutti i tentativi falliti!")
                        browser.close()
                        return False
                    else:
                        print(f"Riprovando... (tentativo {attempt + 1} di {max_attempts})")
    
            browser.close()
            return False
    
    if __name__ == "__main__":
        success = extract_schedule_container()
        if not success:
            exit(1)

def vavoo_channels():
    # Codice del settimo script qui
    # Aggiungi il codice del tuo script "world_channels_generator.py" in questa funzione.
    print("Eseguendo vavoo_channels...")
    # Il codice che avevi nello script "world_channels_generator.py" va qui, senza modifiche.
    import requests
    import time
    import re
    
    def getAuthSignature():
        headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "content-length": "1106",
            "accept-encoding": "gzip"
        }
        data = {
            "token": "tosFwQCJMS8qrW_AjLoHPQ41646J5dRNha6ZWHnijoYQQQoADQoXYSo7ki7O5-CsgN4CH0uRk6EEoJ0728ar9scCRQW3ZkbfrPfeCXW2VgopSW2FWDqPOoVYIuVPAOnXCZ5g",
            "reason": "app-blur",
            "locale": "de",
            "theme": "dark",
            "metadata": {
                "device": {
                    "type": "Handset",
                    "os": "Android",
                    "osVersion": "10",
                    "model": "Pixel 4",
                    "brand": "Google"
                }
            }
        }
        resp = requests.post("https://vavoo.to/mediahubmx-signature.json", json=data, headers=headers, timeout=10)
        return resp.json().get("signature")
    
    def vavoo_groups():
        # Puoi aggiungere altri gruppi per più canali
        return [""]
    
    def clean_channel_name(name):
        """Rimuove i suffissi .a, .b, .c dal nome del canale"""
        # Rimuove .a, .b, .c alla fine del nome (con o senza spazi prima)
        cleaned_name = re.sub(r'\s*\.(a|b|c|s|d|e|f|g|h|i|j|k|l|m|n|o|p|q|r|t|u|v|w|x|y|z)\s*$', '', name, flags=re.IGNORECASE)
        return cleaned_name.strip()
    
    def get_channels():
        signature = getAuthSignature()
        headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "accept-encoding": "gzip",
            "mediahubmx-signature": signature
        }
        all_channels = []
        for group in vavoo_groups():
            cursor = 0
            while True:
                data = {
                    "language": "de",
                    "region": "AT",
                    "catalogId": "iptv",
                    "id": "iptv",
                    "adult": False,
                    "search": "",
                    "sort": "name",
                    "filter": {"group": group},
                    "cursor": cursor,
                    "clientVersion": "3.0.2"
                }
                resp = requests.post("https://vavoo.to/mediahubmx-catalog.json", json=data, headers=headers, timeout=10)
                r = resp.json()
                items = r.get("items", [])
                all_channels.extend(items)
                cursor = r.get("nextCursor")
                if not cursor:
                    break
        return all_channels
    
    def save_as_m3u(channels, filename="vavoo.m3u"):
        # 1. Raccogli tutti i canali in una lista flat
        all_channels_flat = []
        for ch in channels:
            original_name = ch.get("name", "SenzaNome")
            name = clean_channel_name(original_name)
            url = ch.get("url", "")
            category = ch.get("group", "Generale")
            if url:
                all_channels_flat.append({'name': name, 'url': url, 'category': category})

        # 2. Conta le occorrenze di ogni nome
        name_counts = {}
        for ch_data in all_channels_flat:
            name_counts[ch_data['name']] = name_counts.get(ch_data['name'], 0) + 1

        # 3. Rinomina i duplicati
        final_channels_data = []
        name_counter = {}
        for ch_data in all_channels_flat:
            name = ch_data['name']
            if name_counts[name] > 1:
                if name not in name_counter:
                    name_counter[name] = 1
                    new_name = name  # Mantieni il nome originale per la prima occorrenza
                else:
                    name_counter[name] += 1
                    new_name = f"{name} ({name_counter[name]})"
            else:
                new_name = name
            final_channels_data.append({'name': new_name, 'url': ch_data['url'], 'category': ch_data['category']})

        # 4. Raggruppa i canali per categoria per la scrittura del file
        channels_by_category = {}
        for ch_data in final_channels_data:
            category = ch_data['category']
            if category not in channels_by_category:
                channels_by_category[category] = []
            channels_by_category[category].append((ch_data['name'], ch_data['url']))

        # 5. Scrivi il file M3U
        with open(filename, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for category in sorted(channels_by_category.keys()):
                channel_list = sorted(channels_by_category[category], key=lambda x: x[0].lower())
                f.write(f"\n# {category.upper()}\n")
                for name, url in channel_list:
                    f.write(f'#EXTINF:-1 group-title="{category} VAVOO",{name}\n{url}\n')

        print(f"Playlist M3U salvata in: {filename}")
        print(f"Canali organizzati in {len(channels_by_category)} categorie:")
        for category, channel_list in channels_by_category.items():
            print(f"  - {category}: {len(channel_list)} canali")
    
    if __name__ == "__main__":
        channels = get_channels()
        print(f"Trovati {len(channels)} canali. Creo la playlist M3U con i link proxy...")
        save_as_m3u(channels) 
def tvtap():
    import requests
    import json
    import sys
    import concurrent.futures
    import argparse
    from base64 import b64decode, b64encode
    from binascii import a2b_hex
    import re
    
    # Flag per controllare l'output di debug.
    # Può essere attivato con l'argomento --debug o --verbose
    DEBUG_MODE = False
    
    def logga(messaggio):
        """Funzione di logging per debug"""
        if DEBUG_MODE:
            print(f"[DEBUG] {messaggio}", file=sys.stderr)
    
    # Controllo delle dipendenze critiche all'avvio
    try:
        from Crypto.Cipher import PKCS1_v1_5 as Cipher_PKCS1_v1_5
        from Crypto.PublicKey import RSA
        from pyDes import des, PAD_PKCS5
        PYCRYPTO_AVAILABLE = True
    except ImportError:
        PYCRYPTO_AVAILABLE = False
    
    # Inizializzazione del cifrario RSA una sola volta per efficienza
    _pubkey = RSA.importKey(
        a2b_hex(
            "30819f300d06092a864886f70d010101050003818d003081890281"
            "8100bfa5514aa0550688ffde568fd95ac9130fcdd8825bdecc46f1"
            "8f6c6b440c3685cc52ca03111509e262dba482d80e977a938493ae"
            "aa716818efe41b84e71a0d84cc64ad902e46dbea2ec61071958826"
            "4093e20afc589685c08f2d2ae70310b92c04f9b4c27d79c8b5dbb9"
            "bd8f2003ab6a251d25f40df08b1c1588a4380a1ce8030203010001"
        )
    )
    _msg = a2b_hex(
        "7b224d4435223a22695757786f45684237686167747948392b58563052513d3d5c6e222c22534"
        "84131223a2242577761737941713841327678435c2f5450594a74434a4a544a66593d5c6e227d"
     )
    _rsa_cipher = Cipher_PKCS1_v1_5.new(_pubkey)
    
    def payload():
        """Genera payload per le richieste TVTap - esatto come nel codice originale"""
        return b64encode(_rsa_cipher.encrypt(_msg))
    
    def get_tvtap_channels():
        """Ottiene la lista dei canali italiani da TVTap usando il metodo originale"""
        # Controlla se pycryptodome è disponibile prima di procedere
        try:
            from Crypto.Cipher import PKCS1_v1_5 as Cipher_PKCS1_v1_5
        except ImportError:
            # Questo blocco non è più necessario grazie al controllo globale
            pass
        user_agent = 'USER-AGENT-tvtap-APP-V2'
        
        headers = {
            'User-Agent': user_agent,
            'app-token': '37a6259cc0c1dae299a7866489dff0bd',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Host': 'taptube.net',
        }
        
        try:
            payload_data = payload()
            r = requests.post('https://rocktalk.net/tv/index.php?case=get_all_channels', 
                             headers=headers, 
                             data={"payload": payload_data, "username": "603803577"}, 
                             timeout=15)
            
            logga(f'Response status: {r.status_code}')
            
            if r.status_code != 200:
                logga(f'HTTP error: {r.status_code}')
                return [] # Non usare la lista statica in caso di errore
                
            response_json = r.json()
            logga(f'Got response with keys: {list(response_json.keys()) if isinstance(response_json, dict) else "not a dict"}')
            
            # Controlla se c'è un errore nella risposta
            if isinstance(response_json, dict) and "msg" in response_json:
                msg = response_json["msg"]
                if isinstance(msg, str) and ("error" in msg.lower() or "occured" in msg.lower()):
                    logga(f'API returned error: {msg}')
                    return [] # Non usare la lista statica in caso di errore
            
            # Prende tutti i canali dalla risposta
            all_channels = []
            
            if isinstance(response_json, dict) and "msg" in response_json:
                msg = response_json["msg"]
                if isinstance(msg, dict) and "channels" in msg:
                    base_logo_url = "https://rocktalk.net/tv/"
                    channels = msg["channels"]
                    logga(f'Found {len(channels)} total channels in API response')
                    
                    for channel in channels:
                        if isinstance(channel, dict) and channel.get("country"): # Assicuriamoci che il canale abbia un paese
                            relative_logo_path = channel.get("img")
                            full_logo_url = base_logo_url + relative_logo_path if relative_logo_path else ""
    
                            all_channels.append({
                                "id": channel.get("pk_id"),
                                "name": channel.get("channel_name"),
                                "country": channel.get("country"),
                                "thumbnail": full_logo_url
                            })
                    
                    logga(f'Processed {len(all_channels)} channels from API')
                    return all_channels # Restituisce tutti i canali trovati
                else:
                    logga(f'Unexpected msg structure: {type(msg)}, falling back to static list')
                    return [] # Non usare la lista statica
            else:
                logga(f'Unexpected response structure: {type(response_json)}, falling back to static list')
                return [] # Non usare la lista statica
            
        except ImportError as ie:
            logga(f'Import error: {ie}')
            print("ERROR: Missing required library", file=sys.stderr)
            return []
        except Exception as e:
            logga(f'Error getting channels from API: {e}')
            return [] # Non usare la lista statica in caso di errore
    
    def get_tvtap_stream(channel_id):
        """Ottiene lo stream di un canale specifico usando il metodo originale"""
        logga(f'Stream request for channel {channel_id}')
        try:
            payload_data = payload()
            r = requests.post('https://rocktalk.net/tv/index.php?case=get_channel_link_with_token_latest', 
                headers={"app-token": "37a6259cc0c1dae299a7866489dff0bd"},
                data={"payload": payload_data, "channel_id": channel_id, "username": "603803577"},
                timeout=15)
    
            logga(f'Stream request for channel {channel_id}: {r.status_code}')
            
            if r.status_code != 200:
                logga(f'HTTP error: {r.status_code}')
                return None
                
            response_json = r.json()
            logga(f'Response keys: {list(response_json.keys()) if isinstance(response_json, dict) else "not a dict"}')
            
            if "msg" not in response_json:
                logga('No msg in response')
                return None
                
            msgRes = response_json["msg"]
            logga(f'Message response type: {type(msgRes)}, content: {str(msgRes)[:50]}...')
            
            if isinstance(msgRes, str):
                if "error" in msgRes.lower() or "occured" in msgRes.lower():
                    logga(f'API returned error: {msgRes}')
                    return None
                else:
                    logga(f'Got string response: {msgRes}')
                    return None
            
            if not isinstance(msgRes, dict) or "channel" not in msgRes:
                logga('No channel in response')
                return None
                
            # Prova a decrittare usando pyDes (come nel codice originale)
            try:
                key = b"98221122"
                jch = msgRes["channel"][0]
                
                for stream in jch.keys():
                    if "stream" in stream or "chrome_cast" in stream:
                        d = des(key)
                        link = d.decrypt(b64decode(jch[stream]), padmode=PAD_PKCS5)
                
                        if link:
                            link = link.decode("utf-8")
                            if not link == "dummytext" and link:
                                logga(f'Found stream link for channel {channel_id}')
                                return link
                
            except Exception as e:
                logga(f'Decryption error: {e}')
                return None
        except Exception as e:
            logga(f'Error getting stream: {e}')
            return None
        
        logga('Failed to get stream for TVTap ID')
        return None
    
    def normalize_channel_name(name):
        """Normalizza il nome del canale per matching flessibile"""
        if not name:
            return ""
        
        # Converte in maiuscolo e rimuove spazi extra
        name = name.strip().upper()
        
        # Rimuove suffissi comuni
        name = re.sub(r'\s+(HD|FHD|4K|\.A|\.B|\.C)$', '', name)
        
        # Rimuove caratteri speciali per matching più flessibile
        name = re.sub(r'[^\w\s]', '', name)
        
        return name
    
    def find_channel_by_name(channel_name, channels):
        """Trova un canale per nome con matching flessibile"""
        if not channel_name or not channels:
            return None
        
        normalized_search = normalize_channel_name(channel_name)
        logga(f'Looking for normalized name: {normalized_search}')
        
        # Matching esatto
        for channel in channels:
            normalized_channel = normalize_channel_name(channel.get("name", ""))
            if normalized_channel == normalized_search:
                logga(f'Exact match found: {channel.get("name")}')
                return channel
        
        # Matching parziale - cerca se il nome cercato è contenuto nel nome del canale
        for channel in channels:
            normalized_channel = normalize_channel_name(channel.get("name", ""))
            if normalized_search in normalized_channel or normalized_channel in normalized_search:
                logga(f'Partial match found: {channel.get("name")}')
                return channel
        
        # Matching ancora più flessibile - rimuove spazi e caratteri speciali
        search_simple = re.sub(r'[^A-Z0-9]', '', normalized_search)
        for channel in channels:
            channel_simple = re.sub(r'[^A-Z0-9]', '', normalize_channel_name(channel.get("name", "")))
            if search_simple in channel_simple or channel_simple in search_simple:
                logga(f'Flexible match found: {channel.get("name")}')
                return channel
        
        logga(f'No match found for: {channel_name}')
        return None
    
    def normalize_name_for_tvg_id(name):
        """Normalizza il nome per la corrispondenza con l'EPG, come in Untitled."""
        if not name:
            return ""
        # Converte in minuscolo, rimuove spazi e suffissi comuni
        name = re.sub(r"\s+", "", name.strip().lower())
        name = re.sub(r"\.it\b", "", name)
        name = re.sub(r"hd|fullhd", "", name)
        return name
    
    def create_tvg_id_map(epg_file="epg.xml"):
        """
        Crea una mappa di tvg-id dai nomi normalizzati dei canali in un file EPG.
        """
        import xml.etree.ElementTree as ET
        import os
    
        tvg_id_map = {}
        if not os.path.exists(epg_file):
            logga(f"File EPG '{epg_file}' non trovato. I tvg-id non verranno generati.")
            return tvg_id_map
    
        try:
            tree = ET.parse(epg_file)
            root = tree.getroot()
            for channel in root.findall('channel'):
                tvg_id = channel.get('id')
                display_name_element = channel.find('display-name')
                if tvg_id and display_name_element is not None and display_name_element.text:
                    normalized_name = normalize_name_for_tvg_id(display_name_element.text)
                    tvg_id_map[normalized_name] = tvg_id
            logga(f"Mappa tvg-id creata con successo da '{epg_file}'. Trovati {len(tvg_id_map)} ID.")
        except Exception as e:
            logga(f"ERRORE durante la lettura di {epg_file}: {e}")
        return tvg_id_map
    
    def validate_stream_url(url, timeout=15):
        """
        Verifica se un URL di streaming è valido, controllando anche il contenuto.
        Restituisce True se l'URL è raggiungibile e sembra una playlist M3U valida.
        """
        if not url or not url.startswith('http'):
            logga(f"URL non valido per la validazione: {url}")
            return False
        try:
            # Usiamo gli header che mimano un player Android, come suggerito
            # dal codice originale, per massima compatibilità. Molti server
            # richiedono User-Agent e Referer specifici.
            headers = {
                'User-Agent': 'mediaPlayerhttp/1.8 (Linux;Android 7.1.2) ExoPlayerLib/2.5.3',
                'Referer': 'https://rocktalk.net/'
            }
            with requests.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True) as response:
                if 200 <= response.status_code < 300:
                    # Leggiamo solo i primi byte per verificare se è un M3U8 valido.
                    # Questo evita di considerare valide pagine di errore HTML con status 200.
                    try:
                        first_chunk = next(response.iter_content(chunk_size=256))
                        content_start = first_chunk.decode('utf-8', errors='ignore')
                        if '#EXTM3U' in content_start:
                            logga(f"Validazione URL -> Successo (Status: {response.status_code}, Contenuto M3U8 valido)")
                            return True
                        else:
                            logga(f"Validazione URL -> Fallito (Status: {response.status_code}, Contenuto non M3U8 o non valido)")
                            return False
                    except StopIteration:
                        logga(f"Validazione URL -> Fallito (Status: {response.status_code}, Risposta vuota)")
                        return False
                else:
                    logga(f"Validazione URL -> Fallito (Status: {response.status_code})")
                    return False
        except requests.exceptions.Timeout:
            logga(f"Validazione URL -> Fallito (Timeout dopo {timeout}s)")
            return False
        except requests.exceptions.RequestException as e:
            # Gestisce altri errori di rete (es. DNS, connessione rifiutata)
            logga(f"Validazione URL -> Fallito (Errore di rete: {type(e).__name__})")
            return False
    
    COUNTRY_CODE_MAP = {
        "AF": "AFGHANISTAN", "AL": "ALBANIA", "DZ": "ALGERIA", "AR": "ARGENTINA", "AM": "ARMENIA",
        "AU": "AUSTRALIA", "AT": "AUSTRIA", "AZ": "AZERBAIJAN", "BH": "BAHRAIN", "BD": "BANGLADESH",
        "BY": "BELARUS", "BE": "BELGIUM", "BA": "BOSNIA AND HERZEGOVINA", "BR": "BRAZIL", "BG": "BULGARIA",
        "KH": "CAMBODIA", "CM": "CAMEROON", "CA": "CANADA", "CL": "CHILE", "CO": "COLOMBIA",
        "HR": "CROATIA", "CU": "CUBA", "CY": "CYPRUS", "CZ": "CZECH REPUBLIC", "DK": "DENMARK",
        "EC": "ECUADOR", "EG": "EGYPT", "EE": "ESTONIA", "FI": "FINLAND", "FR": "FRANCE",
        "GE": "GEORGIA", "DE": "GERMANY", "GH": "GHANA", "GR": "GREECE", "GT": "GUATEMALA",
        "HT": "HAITI", "HN": "HONDURAS", "HK": "HONG KONG", "HU": "HUNGARY", "IS": "ICELAND",
        "IN": "INDIA", "ID": "INDONESIA", "IR": "IRAN", "IQ": "IRAQ", "IE": "IRELAND",
        "IL": "ISRAEL", "IT": "ITALY", "JM": "JAMAICA", "JP": "JAPAN", "JO": "JORDAN",
        "KZ": "KAZAKHSTAN", "KE": "KENYA", "KW": "KUWAIT", "LV": "LATVIA", "LB": "LEBANON",
        "LT": "LITHUANIA", "LU": "LUXEMBOURG", "MK": "NORTH MACEDONIA", "MY": "MALAYSIA", "MT": "MALTA",
        "MX": "MEXICO", "MD": "MOLDOVA", "MA": "MOROCCO", "MM": "MYANMAR", "NP": "NEPAL",
        "NL": "NETHERLANDS", "NZ": "NEW ZEALAND", "NG": "NIGERIA", "NO": "NORWAY", "OM": "OMAN",
        "PK": "PAKISTAN", "PA": "PANAMA", "PY": "PARAGUAY", "PE": "PERU", "PH": "PHILIPPINES",
        "PL": "POLAND", "PT": "PORTUGAL", "PR": "PUERTO RICO", "QA": "QATAR", "RO": "ROMANIA",
        "RU": "RUSSIA", "SA": "SAUDI ARABIA", "SN": "SENEGAL", "RS": "SERBIA", "SG": "SINGAPORE",
        "SK": "SLOVAKIA", "SI": "SLOVENIA", "ZA": "SOUTH AFRICA", "KR": "SOUTH KOREA", "ES": "SPAIN",
        "LK": "SRI LANKA", "SD": "SUDAN", "SE": "SWEDEN", "CH": "SWITZERLAND", "SY": "SYRIA",
        "TW": "TAIWAN", "TZ": "TANZANIA", "TH": "THAILAND", "TN": "TUNISIA", "TR": "TURKEY",
        "UG": "UGANDA", "UA": "UKRAINE", "AE": "UAE", "GB": "UK", "US": "USA",
        "UY": "URUGUAY", "VE": "VENEZUELA", "VN": "VIETNAM", "YE": "YEMEN"
    }
    
    def process_channel(channel, tvg_id_map):
        """
        Elabora un singolo canale: ottiene e valida lo stream, e formatta la riga M3U.
        Restituisce la stringa M3U completa per il canale se funzionante, altrimenti None.
        """
        channel_id = channel.get("id")
        channel_name = channel.get("name", "Sconosciuto")
        channel_logo = channel.get("thumbnail", "")
        country_code = channel.get("country", "Altro")
        group_title = COUNTRY_CODE_MAP.get(country_code, country_code) # Usa il nome completo, altrimenti il codice
    
        if not channel_id:
            logga(f"Canale '{channel_name}' saltato perché non ha un ID.")
            return None, f"ID mancante per {channel_name}"
    
        stream_url = get_tvtap_stream(channel_id)
    
        if stream_url and validate_stream_url(stream_url):
            display_name = f"{channel_name} (TVT)"
            normalized_name = normalize_name_for_tvg_id(channel_name)
            tvg_id = tvg_id_map.get(normalized_name, "")
    
            extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" tvg-logo="{channel_logo}" group-title="{group_title}",{display_name}\n'
            m3u_entry = extinf + stream_url + "\n"
            
            logga(f"Stream per '{channel_name}' (ID: {channel_id}) verificato con successo.")
            return m3u_entry, f"Aggiunto (Verificato): {channel_name}"
        
        elif stream_url:
            logga(f"Stream per '{channel_name}' (ID: {channel_id}) trovato ma la validazione è fallita.")
            return None, f"Saltato (Link non funzionante): {channel_name}"
        
        else:
            logga(f"Stream non trovato per '{channel_name}' (ID: {channel_id}).")
            return None, f"Saltato (Stream non trovato): {channel_name}"
    
    
    def create_m3u_playlist(filename):
        """
        Crea una playlist M3U con tutti i canali italiani e i loro stream.
        """
        import time
        logga(f"Inizio creazione playlist M3U: {filename}")
        
        # 1. Crea la mappa dei tvg-id leggendo il file EPG
        tvg_id_map = create_tvg_id_map()
    
        # 2. Ottieni la lista dei canali
        channels = get_tvtap_channels()
        if not channels:
            logga("ERRORE: Impossibile recuperare la lista dei canali. Interruzione.")
            print("ERRORE: Nessun canale recuperato. Impossibile creare la playlist.", file=sys.stderr)
            return
    
        # 3. Ordina i canali per nome
        sorted_channels = sorted(channels, key=lambda x: x.get('name', '').lower())
        total_channels = len(sorted_channels)
        logga(f"Trovati e ordinati {total_channels} canali totali. Avvio elaborazione parallela.")
    
        # 4. Elaborazione parallela dei canali
        # Usiamo un ThreadPoolExecutor per gestire le richieste di rete in parallelo.
        # MAX_WORKERS limita il numero di thread simultanei per non sovraccaricare l'API.
        MAX_WORKERS = 20
        m3u_entries = []
        processed_count = 0
    
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Sottometti tutti i task di elaborazione dei canali
            future_to_channel = {executor.submit(process_channel, channel, tvg_id_map): channel for channel in sorted_channels}
            
            for future in concurrent.futures.as_completed(future_to_channel):
                processed_count += 1
                m3u_entry, message = future.result()
                
                # Stampa lo stato di avanzamento
                print(f"[{processed_count}/{total_channels}] {message}", flush=True)
                
                if m3u_entry:
                    m3u_entries.append(m3u_entry)
    
        # 5. Scrivi i risultati nel file M3U
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for entry in m3u_entries:
                    f.write(entry)
            
            working_channels_count = len(m3u_entries)
            print(f"\nPlaylist '{filename}' creata con successo. Contiene {working_channels_count} canali funzionanti su {total_channels} totali.")
            logga(f"Playlist M3U '{filename}' salvata correttamente.")
        except Exception as e:
            logga(f"ERRORE CRITICO durante la creazione del file M3U: {e}")
            print(f"\nSi è verificato un errore durante la scrittura del file: {e}", file=sys.stderr)
    
    def main():
        """Funzione principale per creare la playlist M3U."""
        global DEBUG_MODE
        
        # Abilita la modalità debug se viene passato l'argomento --debug o --verbose
        if '--debug' in sys.argv or '--verbose' in sys.argv:
            DEBUG_MODE = True
            logga("Modalità debug attivata.")
    
        if not PYCRYPTO_AVAILABLE:
            logga("FATAL: Le librerie 'pycryptodome' e/o 'pyDes' non sono installate.")
            print("ERRORE: Dipendenze mancanti. Esegui: pip install pycryptodome pyDes", file=sys.stderr)
            sys.exit(1)
        
        # Esegue direttamente la creazione della playlist
        create_m3u_playlist("tvtap.m3u")
    
    if __name__ == "__main__":
        main()
    
def main():
    try:
        try:
            schedule_extractor()
        except Exception as e:
            print(f"Errore durante l'esecuzione di schedule_extractor: {e}")
            return
        try:
            vavoo_channels()
        except Exception as e:
            print(f"Errore durante l'esecuzione di vavoo_channels: {e}")
            return
        try:
            dlhd()
        except Exception as e:
            print(f"Errore durante l'esecuzione di dlhd: {e}")
            return
        try:
            tvtap()
        except Exception as e:
            print(f"Errore durante l'esecuzione di tvtap: {e}")
            return
        print("Tutti gli script sono stati eseguiti correttamente!")
    finally:
        pass

if __name__ == "__main__":
    main()
