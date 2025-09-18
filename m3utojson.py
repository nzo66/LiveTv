import re
import json

def parse_event_info(name):
    parts = [p.strip() for p in name.split('|')]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return parts[0], parts[1], ""
    else:
        return parts[0], "", ""

def m3u_to_nested_json_with_condition(m3u_content):
    lines = m3u_content.strip().splitlines()
    result = {
        "name": "DADDYLIVE",
        "author": "nzo66",
        "image": "https://www.kodi-tipps.de/wp-content/uploads/2023/01/daddylive-kodi-addon-installieren-banner.jpg",
        "info": "",
        "groups": []
    }

    groups_level1 = {}

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            group_title_match = re.search(r'group-title="([^"]+)"', line)
            group_title = group_title_match.group(1) if group_title_match else "Other"

            channel_full_name = line.split(",")[-1].strip() if "," in line else "Unknown"
            i += 1
            url = lines[i].strip() if i < len(lines) else ""

            # Headers di default
            user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            origin = "https://jxoxkplay.xyz"
            referer = "https://jxoxkplay.xyz/"

            for j in range(3):
                if i + 1 + j < len(lines):
                    next_line = lines[i+1+j].strip()
                    if next_line.startswith("#EXTINF"):
                        break
                    if next_line.lower().startswith("user-agent:"):
                        user_agent = next_line[len("user-agent:"):].strip()
                    elif next_line.lower().startswith("origin:"):
                        origin = next_line[len("origin:"):].strip()
                    elif next_line.lower().startswith("referer:"):
                        referer = next_line[len("referer:"):].strip()

            i = i + 3

            if group_title not in groups_level1:
                groups_level1[group_title] = {
                    "name": group_title,
                    "groups": [],
                    "stations": []
                }
                result["groups"].append(groups_level1[group_title])
            level1_group = groups_level1[group_title]

            if group_title == "Live Events":
                # Solo per Live Events struttura annidata
                main_event, sub_event, channel_name = parse_event_info(channel_full_name)

                level2_group = next((g for g in level1_group["groups"] if g["name"] == main_event), None)
                if level2_group is None:
                    level2_group = {
                        "name": main_event,
                        "groups": []
                    }
                    level1_group["groups"].append(level2_group)

                level3_group = next((g for g in level2_group["groups"] if g["name"] == sub_event), None)
                if level3_group is None:
                    level3_group = {
                        "name": sub_event,
                        "stations": []
                    }
                    level2_group["groups"].append(level3_group)

                station = {
                    "name": channel_name,
                    "url": url,
                    "userAgent": user_agent,
                    "origin": origin,
                    "referer": referer
                }

                level3_group["stations"].append(station)
            else:
                # Per altri group_title inserisci direttamente nei stations di primo livello
                station = {
                    "name": channel_full_name,
                    "url": url,
                    "userAgent": user_agent,
                    "origin": origin,
                    "referer": referer
                }
                level1_group.setdefault("stations", []).append(station)

        else:
            i += 1

    return result

if __name__ == "__main__":
    filename = "dlhd.m3u"
    with open(filename, "r", encoding="utf-8") as f:
        m3u_content = f.read()

    json_result = m3u_to_nested_json_with_condition(m3u_content)
    with open("dlhd.json", "w", encoding="utf-8") as f:
        json.dump(json_result, f, indent=2, ensure_ascii=False)

    print("Conversione completata: dlhd.json")
