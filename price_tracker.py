"""
Price Tracker - Mercado Livre & Amazon
----------------------------------------
Le os produtos configurados em products.json, busca o preco atual
em cada site e envia uma mensagem no Telegram com o resultado.

Variaveis de ambiente necessarias:
    TELEGRAM_TOKEN   -> token do bot (via @BotFather)
    TELEGRAM_CHAT_ID -> id do chat/usuario que vai receber a mensagem
"""

import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def send_telegram_message(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não configurados.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=payload, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        print(f"Erro ao enviar mensagem no Telegram: {exc}")


def extract_from_ldjson(soup: BeautifulSoup):
    """Tenta extrair nome e preço dos dados estruturados (schema.org)
    que a maioria dos e-commerces inclui para SEO. É mais estável do
    que depender de classes CSS, que mudam com frequência."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except (TypeError, ValueError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") not in ("Product", ["Product"]):
                continue

            name = item.get("name")
            offers = item.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            price = None
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")

            if price is not None:
                try:
                    return name, float(price)
                except (TypeError, ValueError):
                    pass
    return None, None


def get_price_mercadolivre(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    name, price = extract_from_ldjson(soup)
    if price is not None:
        title_tag = soup.find("h1", class_="ui-pdp-title")
        title = name or (title_tag.get_text(strip=True) if title_tag else "Produto Mercado Livre")
        return title, price

    # Fallback: classes CSS da página (podem mudar sem aviso)
    title_tag = soup.find("h1", class_="ui-pdp-title")
    title = title_tag.get_text(strip=True) if title_tag else "Produto Mercado Livre"

    price_tag = soup.find("span", class_="andes-money-amount__fraction")
    if not price_tag:
        print(f"[debug] status={resp.status_code} tamanho_html={len(resp.text)} url={url}")
        return title, None

    price_text = price_tag.get_text(strip=True)
    price = float(price_text.replace(".", "").replace(",", "."))
    return title, price


def get_price_amazon(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    name, price = extract_from_ldjson(soup)
    if price is not None:
        title_tag = soup.find(id="productTitle")
        title = name or (title_tag.get_text(strip=True) if title_tag else "Produto Amazon")
        return title, price

    # Fallback: classes CSS da página (podem mudar sem aviso)
    title_tag = soup.find(id="productTitle")
    title = title_tag.get_text(strip=True) if title_tag else "Produto Amazon"

    price_tag = (
        soup.find("span", class_="a-price-whole")
        or soup.find(id="priceblock_ourprice")
        or soup.find(id="priceblock_dealprice")
    )
    if not price_tag:
        print(f"[debug] status={resp.status_code} tamanho_html={len(resp.text)} url={url}")
        return title, None

    raw = price_tag.get_text(strip=True)
    cleaned = re.sub(r"[^\d,.]", "", raw).replace(".", "").replace(",", ".")
    try:
        price = float(cleaned)
    except ValueError:
        price = None
    return title, price


def check_product(product: dict) -> None:
    site = product["site"].lower()
    url = product["url"]
    name = product.get("name", "")

    try:
        if site == "mercadolivre":
            title, price = get_price_mercadolivre(url)
        elif site == "amazon":
            title, price = get_price_amazon(url)
        else:
            print(f"Site desconhecido: {site}")
            return
    except Exception as exc:
        print(f"Erro ao buscar {url}: {exc}")
        return

    if price is None:
        print(f"Não consegui localizar o preço de {title} ({url})")
        return

    label = name or title
    mensagem = f"🛒 <b>{label}</b>\nPreço atual: R$ {price:.2f}\n{url}"

    alvo = product.get("preco_alvo")
    if alvo is not None:
        if price <= alvo:
            mensagem += f"\n\n✅ Preço abaixo do alvo (R$ {alvo:.2f})!"
            send_telegram_message(mensagem)
        else:
            print(f"{label}: R$ {price:.2f} (alvo R$ {alvo:.2f}) - ainda não atingiu")
    else:
        send_telegram_message(mensagem)


def main() -> None:
    with open("products.json", "r", encoding="utf-8") as f:
        products = json.load(f)

    for product in products:
        check_product(product)
        time.sleep(3)  # evita martelar os sites com requisições muito rápidas


if __name__ == "__main__":
    main()
