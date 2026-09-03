import httpx

urls = [
    "https://zakupki.mos.ru/cms/media/docs/%D1%80%D1%83%D0%BA%D0%BE%D0%B2%D0%BE%D0%B4%D1%81%D1%82%D0%B2%D0%BE_%D0%BF%D0%BE%D0%BB%D1%8C%D0%B7%D0%BE%D0%B2%D0%B0%D1%82%D0%B5%D0%BB%D1%8F_%D0%BF%D1%80%D0%BE%D0%B8%D0%B7%D0%B2%D0%BE%D0%B4%D0%B8%D1%82%D0%B5%D0%BB%D1%8C_v41_03_05_23.docx",
    "https://zakupki.mos.ru/cms/Media/docs/%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F%20%D0%BF%D0%BE%20%D1%80%D0%B5%D0%B3%D0%B8%D1%81%D1%82%D1%80%D0%B0%D1%86%D0%B8%D0%B8%20%D0%BD%D0%B0%20%D0%9F%D0%BE%D1%80%D1%82%D0%B0%D0%BB%D0%B5.pdf",
    "https://zakupki.mos.ru/static/media/offer_yml_sku_howto.6a3b8d81.pdf",
    "https://zakupki.mos.ru/static/media/yml_instruction.1510c09b.pdf",
    "https://zakupki.mos.ru/newapi/api/FileStorage/Download?id=2118416529"
]

headers = {"User-Agent": "Mozilla/5.0"}
with httpx.Client(headers=headers, timeout=15.0, verify=False, follow_redirects=True) as client:
    for u in urls:
        try:
            r = client.get(u)
            ct = r.headers.get("content-type", "")
            print(f"{u[:70]}... -> {r.status_code}, len={len(r.content)}, type={ct}")
        except Exception as e:
            print(f"{u[:70]}... -> Error: {e}")
